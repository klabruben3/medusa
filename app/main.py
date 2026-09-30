import asyncio
import logging
import os
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import APIError, RateLimitError, APITimeoutError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .ai.generate_module import create_module
from .types.schema import ExtractionResult
from .utils.auth import authorize
from .utils.documents import DocumentError, extract_source, MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_FILES, MAX_TEXT
from .utils.retrieval import blocking_job

app = FastAPI()
app.add_middleware(CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,https://academiq-nwu.vercel.app").split(","),
    allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
logger = logging.getLogger(__name__)
MAX_REQUEST_BYTES = MAX_TOTAL_BYTES + 1024 * 1024
PROCESSING_TIMEOUT = 240
active_jobs = set()


async def process_documents(files: list[UploadFile], job_id=None):
    if not files or len(files) > MAX_FILES:
        raise DocumentError(f"Upload between 1 and {MAX_FILES} documents.", 413, "file_count")
    sources, warnings, total = [], [], 0
    for upload in files:
        content = await upload.read(MAX_FILE_BYTES + 1)
        if not content:
            raise DocumentError("Uploaded documents must not be empty.", 422, "empty_document")
        total += len(content)
        if len(content) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise DocumentError("Upload limit: 50 MB per file and 100 MB in total.", 413, "file_too_large")
        started = monotonic()
        source, notes = await blocking_job(extract_source, upload.filename or "document", content, upload.content_type)
        sources.append(source)
        warnings.extend(notes)
        blocks = source.get("blocks", [])
        logger.info("stage=normalized job=%s blocks=%d native=%d ocr=%d tables=%d pages=%d duration_ms=%d",
                    job_id, len(blocks), sum(b["metadata"]["origin"] == "native" for b in blocks),
                    sum(b["metadata"]["origin"] == "ocr" for b in blocks), sum(b["type"] == "table" for b in blocks),
                    max((b["page"] for b in blocks), default=0), (monotonic() - started) * 1000)
        if sum(len(s["text"]) for s in sources) > MAX_TEXT:
            raise DocumentError("Combined document text is too large. Split the upload.", 413, "text_too_large")
    result = await create_module(sources, job_id)
    result.warnings = list(dict.fromkeys(warnings + result.warnings))
    return result


@app.get("/")
async def root():
    return {"status": "ok", "service": "academiq-api"}


async def uploaded_documents(request, job_id):
    # Bound actual streamed bytes, including chunked requests, before multipart spooling.
    received = 0
    async def stream():
        nonlocal received
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_REQUEST_BYTES:
                raise MultiPartException("Upload limit exceeded")
            yield chunk
    parser = MultiPartParser(request.headers, stream(), max_files=MAX_FILES, max_fields=0, max_part_size=1024)
    form = None
    try:
        form = await parser.parse()
        files = form.getlist("files")
        if any(key != "files" or not isinstance(value, UploadFile) for key, value in form.multi_items()):
            raise DocumentError("Submit documents using the files field.", 400, "invalid_request")
        return await process_documents(files, job_id)
    except MultiPartException as exc:
        if received > MAX_REQUEST_BYTES:
            raise DocumentError("The combined upload is too large.", 413, "file_too_large") from exc
        raise DocumentError("Invalid multipart upload or too many documents.", 400, "invalid_request") from exc
    finally:
        if form is not None:
            await form.close()
        else:
            # Starlette only closes these for MultiPartException, not cancellation
            # or disconnects. Close partial spooled files on every exit path.
            for temporary in parser._files_to_close_on_error:
                temporary.close()


@app.post("/process-documents", response_model=ExtractionResult, response_model_exclude_none=True)
async def main(request: Request):
    job_id, started, owner = uuid4().hex, monotonic(), None
    admitted = False
    try:
        owner = await authorize(request)  # Verify session before reading file data.
        # Bound OCR/embedding memory on a single Render instance; quota is cross-instance.
        if owner in active_jobs or len(active_jobs) >= int(os.getenv("MAX_CONCURRENT_EXTRACTIONS", "2")):
            raise DocumentError("Extraction is busy. Please retry shortly.", 429, "rate_limited")
        active_jobs.add(owner)
        admitted = True
        logger.info("stage=started job=%s", job_id)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError as exc:
            raise DocumentError("Invalid upload request.", 400, "invalid_request") from exc
        if length > MAX_REQUEST_BYTES:
            raise DocumentError("The combined upload is too large.", 413, "file_too_large")
        return await asyncio.wait_for(uploaded_documents(request, job_id), timeout=PROCESSING_TIMEOUT)
    except DocumentError as exc:
        logger.warning("stage=failed job=%s code=%s status=%d", job_id, exc.code, exc.status)
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=exc.status)
    except RateLimitError:
        return JSONResponse({"detail": "The extraction provider is busy. Try again shortly.", "code": "rate_limited"}, status_code=429)
    except (APITimeoutError, TimeoutError):
        return JSONResponse({"detail": "Document processing timed out. Try fewer documents.", "code": "timeout"}, status_code=504)
    except APIError:
        return JSONResponse({"detail": "The extraction provider could not complete the request.", "code": "provider_error"}, status_code=502)
    except Exception as exc:
        # Exception strings and tracebacks can include OCR/source/model data.
        logger.warning("stage=failed job=%s exception_type=%s", job_id, type(exc).__name__)
        return JSONResponse({"detail": "Document processing failed. Please retry.", "code": "processing_error"}, status_code=502)
    finally:
        if admitted:
            active_jobs.discard(owner)
        logger.info("stage=finished job=%s duration_ms=%d", job_id, (monotonic() - started) * 1000)
