import asyncio
import logging
import os

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import APIError, RateLimitError, APITimeoutError
from starlette.concurrency import run_in_threadpool

from .ai.generate_module import create_module
from .types.schema import ExtractionResult
from .utils.documents import (
    DocumentError, extract_source, MAX_FILE_BYTES, MAX_TOTAL_BYTES,
    MAX_FILES, MAX_TEXT,
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,https://academiq-nwu.vercel.app").split(","),
    allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["*"],
)
logger = logging.getLogger(__name__)


async def process_documents(files: list[UploadFile]):
    if not files or len(files) > MAX_FILES:
        raise DocumentError(
            f"Upload between 1 and {MAX_FILES} documents.", 413)
    sources, warnings = [], []
    total = 0
    for upload in files:
        content = await upload.read(MAX_FILE_BYTES + 1)
        if not content:
            raise DocumentError("Uploaded documents must not be empty.")
        total += len(content)
        if len(content) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise DocumentError(
                "Upload limit: 50 MB per file and 100 MB in total.", 413)
        source, notes = await run_in_threadpool(extract_source, upload.filename or "document", content)
        sources.append(source)
        warnings.extend(notes)
        if sum(len(s["text"]) for s in sources) > MAX_TEXT:
            raise DocumentError(
                "Combined document text is too large. Split the upload.", 413)
    result = await create_module(sources)
    result.warnings = list(dict.fromkeys(warnings + result.warnings))
    return result


@app.get("/")
async def root():
    return {"status": "ok", "service": "academiq-api"}


@app.post("/process-documents", response_model=ExtractionResult, response_model_exclude_none=True)
async def main(files: list[UploadFile] = File(...)):
    try:
        return await asyncio.wait_for(process_documents(files), timeout=240)
    except DocumentError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(
            429, "The extraction service is busy. Please try again shortly.") from exc
    except (APITimeoutError, TimeoutError) as exc:
        raise HTTPException(
            504, "Document processing timed out. Try fewer documents.") from exc
    except APIError as exc:
        logger.warning("Extraction provider failed: %s", type(exc).__name__)
        raise HTTPException(
            502, "The extraction service could not complete the request. Please retry.") from exc
    finally:
        for upload in files:
            await upload.close()
