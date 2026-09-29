"""A private in-memory Chroma collection exists only during this retrieval job."""
import asyncio
import logging
import os
import re
from time import monotonic
from uuid import uuid4

from .documents import Blocks, DocumentError, MAX_BLOCK_TEXT, MAX_TEXT
from ..ai.partials import QUERIES

logger = logging.getLogger(__name__)
MAX_CONTEXT = 48_000


async def blocking_job(function, *args):
    # asyncio cancellation must not abandon a thread that still owns private data.
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(task)
        except Exception:
            pass
        raise


def chroma_client():
    import chromadb
    from chromadb.config import Settings
    return chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False, is_persistent=False))


def embedder():
    import voyageai
    if not os.getenv("VOYAGE_API_KEY"):
        raise DocumentError("The extraction service is not configured.", 503, "not_configured")
    return voyageai.Client(timeout=45, max_retries=1)


def normalize_sources(sources):
    blocks = []
    for source_index, source in enumerate(sources):
        source_blocks = source.get("blocks")
        if source_blocks is None:  # Synthetic smoke-test/backward-compatible call boundary.
            normalized = Blocks(source["filename"])
            for paragraph in re.split(r"\n\s*\n", source.get("text", "")):
                normalized.add(paragraph, 0)
            source_blocks = normalized.items
        for block in source_blocks:
            blocks.append({**block, "id": f"s{source_index}-b{block['order']}", "source_index": source_index})
    if not blocks:
        raise DocumentError("No readable document blocks were found.", 422, "empty_document")
    if sum(len(b["content"]) for b in blocks) > MAX_TEXT or any(len(b["content"]) > MAX_BLOCK_TEXT for b in blocks):
        raise DocumentError("Document text exceeds the extraction limit.", 413, "text_too_large")
    return blocks


def retrieve_contexts(sources, job_id=None, client=None, embeddings=None):
    started = monotonic()
    blocks = normalize_sources(sources)
    client = client if client is not None else chroma_client()
    embeddings = embeddings if embeddings is not None else embedder()
    model = os.getenv("VOYAGE_EMBEDDING_MODEL", "voyage-4-lite")
    # Never accept a caller-supplied collection name; concurrent jobs cannot collide.
    name = "extraction-" + uuid4().hex
    created = False
    def embed(texts, input_type):
        try:
            return embeddings.embed(texts, model=model, input_type=input_type, truncation=False)
        except Exception as exc:
            category = type(exc).__name__
            if "RateLimit" in category:
                raise DocumentError("The embedding provider is busy. Please retry shortly.", 429, "rate_limited") from exc
            if "Timeout" in category:
                raise DocumentError("Document retrieval timed out. Please retry.", 504, "timeout") from exc
            raise
    try:
        collection = client.create_collection(name=name, embedding_function=None)
        created = True
        batch, characters = [], 0

        def insert(items):
            result = embed([b["content"] for b in items], "document")
            collection.add(ids=[b["id"] for b in items], documents=[b["content"] for b in items],
                           embeddings=result.embeddings,
                           metadatas=[{"source_file": b["source_file"], "source_index": b["source_index"],
                                       "page": b["page"], "order": b["order"], "type": b["type"],
                                       "origin": b["metadata"].get("origin", "native")} for b in items])

        for block in blocks:
            if batch and (characters + len(block["content"]) > 24_000 or len(batch) >= 64):
                insert(batch)
                batch, characters = [], 0
            batch.append(block)
            characters += len(block["content"])
        if batch:
            insert(batch)
        logger.info("stage=chroma_insert job=%s blocks=%d", job_id, len(blocks))
        contexts, notes = {}, []
        by_id = {b["id"]: b for b in blocks}
        neighbors = {(b["source_index"], b["order"]): b for b in blocks}
        # One embedding request for all purposes; retrieval still runs independently.
        # This matters for accounts with a small requests-per-minute allocation.
        query_vectors = embed([query for queries in QUERIES.values() for query in queries], "query").embeddings
        query_offset = 0
        for purpose, queries in QUERIES.items():
            vectors = query_vectors[query_offset:query_offset + len(queries)]
            query_offset += len(queries)
            results = collection.query(query_embeddings=vectors, n_results=min(16, len(blocks)), include=["distances"])
            selected = {}
            for ids in results["ids"]:
                for block_id in ids:
                    block = by_id[block_id]
                    selected[block_id] = block
                    # Nearby headings/continuation rows keep retrieved evidence intelligible.
                    for offset in (-1, 1):
                        neighbor = neighbors.get((block["source_index"], block["order"] + offset))
                        if neighbor and neighbor["page"] == block["page"]:
                            selected[neighbor["id"]] = neighbor
            ordered = sorted(selected.values(), key=lambda b: (b["source_index"], b["order"]))
            unique, seen = [], set()
            for block in ordered:
                key = re.sub(r"\s+", " ", block["content"]).strip().casefold()
                if key in seen:
                    continue  # Exact normalized duplicate only: differing marks/dates are evidence.
                seen.add(key)
                unique.append({k: block[k] for k in ("id", "content", "page", "order", "source_file", "type")})
            if sum(len(b["content"]) for b in unique) > MAX_CONTEXT:
                raise DocumentError("Relevant document sections are too large. Upload a smaller document set.", 413, "context_too_large")
            contexts[purpose] = unique
            if len(selected) < len(blocks):
                notes.append("Extraction uses selected relevant sections; review all assessments and grading rules against the original documents.")
            logger.info("stage=retrieval job=%s purpose=%s blocks=%d", job_id, purpose, len(unique))
        return contexts, list(dict.fromkeys(notes))
    finally:
        if created:
            # Synchronous local deletion completes before models run or any result is returned.
            for attempt in range(3):
                try:
                    client.delete_collection(name)
                    break
                except Exception:
                    if attempt == 2:
                        logger.error("stage=cleanup_failed job=%s", job_id)
                        raise DocumentError("Extraction cleanup failed. Please retry later.", 503, "cleanup_failed") from None
            logger.info("stage=cleanup job=%s duration_ms=%d", job_id, (monotonic() - started) * 1000)
