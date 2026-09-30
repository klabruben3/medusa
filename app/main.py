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


def groq_failure(exc, job_id):
    """Expose actionable diagnostics without provider messages or generated content."""
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else {}
    raw_code = error.get("code") if isinstance(error, dict) else None
    safe_code = raw_code if raw_code in {"json_validate_failed", "model_not_found", "model_decommissioned", "invalid_api_key", "context_length_exceeded"} else "unknown"
    logger.warning("stage=groq_failed job=%s exception_type=%s upstream_status=%s provider_code=%s",
                   job_id, type(exc).__name__, status, safe_code)
    if status == 401 or safe_code == "invalid_api_key":
        message, code = "Groq rejected Medusa's GROQ_API_KEY. Replace it in Render with a valid Groq API key and redeploy.", "groq_auth_failed"
    elif status == 403:
        message, code = "Groq denied access. Check the Groq project's permissions for the configured extraction model.", "groq_access_denied"
    elif safe_code in {"model_not_found", "model_decommissioned"} or status == 404:
        message, code = "Groq could not find the requested resource. Check Medusa's GROQ_MODULE_MODEL and worker model overrides.", "groq_model_unavailable"
    elif safe_code == "json_validate_failed":
        message, code = "Groq could not generate output matching the module schema. Retry with one document; repeated failures require checking the worker schema and model.", "groq_schema_failed"
    elif safe_code == "context_length_exceeded":
        message, code = "The extraction context exceeds the Groq model limit. Try fewer documents.", "groq_context_limit"
    elif status == 413:
        message, code = "Groq rejected the request size or token allocation. Check the account token limit and Medusa's request budget.", "groq_request_too_large"
    elif status == 400:
        message, code = "Groq rejected the extraction request. Check the configured model's support for the JSON schema and token limit.", "groq_request_rejected"
    elif isinstance(status, int) and status >= 500:
        message, code = "Groq returned a server error. Try again shortly.", "groq_unavailable"
    else:
        message, code = "The Groq request failed. Check Render logs for stage=groq_failed and its upstream status.", "groq_request_failed"
    return JSONResponse({"detail": message, "code": code}, status_code=502)


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


async def uploaded_documents(request, job_id, accept=None):
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
        if accept is not None:
            result = await accept(files, form)
            form = None  # The admitted background job now owns and closes the form.
            parser._files_to_close_on_error = []
            return result
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
    except APIError as exc:
        return groq_failure(exc, job_id)
    except Exception as exc:
        # Exception strings and tracebacks can include OCR/source/model data.
        logger.warning("stage=failed job=%s exception_type=%s", job_id, type(exc).__name__)
        return JSONResponse({"detail": "Document processing failed. Please retry.", "code": "processing_error"}, status_code=502)
    finally:
        if admitted:
            active_jobs.discard(owner)
        logger.info("stage=finished job=%s duration_ms=%d", job_id, (monotonic() - started) * 1000)


# Single-instance, ephemeral jobs. No source text/results are persisted.
# A restart intentionally loses jobs; clients retain files and receive an explicit 404.
extraction_jobs = {}
JOB_TIMEOUT = 1200
JOB_TTL = 1800


def prune_jobs():
    now = monotonic()
    for key, job in list(extraction_jobs.items()):
        if now - job["created"] > JOB_TTL:
            if not job["task"].done():
                job["task"].cancel()
            del extraction_jobs[key]


async def execute_job(job, files, form):
    try:
        result = await asyncio.wait_for(process_documents(files, job["id"]), JOB_TIMEOUT)
        job.update(status="completed", result=result.model_dump(exclude_none=True))
    except DocumentError as exc:
        logger.warning("stage=job_failed job=%s code=%s", job["id"], exc.code)
        job.update(status="failed", error={"detail": str(exc), "code": exc.code, "status": exc.status})
    except RateLimitError:
        job.update(status="failed", error={"detail": "Groq's account limit was reached. Retry later.", "code": "rate_limited", "status": 429})
    except (APITimeoutError, TimeoutError):
        job.update(status="failed", error={"detail": "Extraction timed out. Try a smaller document set.", "code": "timeout", "status": 504})
    except APIError as exc:
        import json
        response = groq_failure(exc, job["id"])
        job.update(status="failed", error={**json.loads(response.body), "status": response.status_code})
    except asyncio.CancelledError:
        job.update(status="failed", error={"detail": "Extraction was interrupted. Please retry.", "code": "interrupted", "status": 503})
        raise
    except Exception as exc:
        logger.warning("stage=job_failed job=%s exception_type=%s", job["id"], type(exc).__name__)
        job.update(status="failed", error={"detail": "Document processing failed. Please retry.", "code": "processing_error", "status": 502})
    finally:
        await form.close()
        active_jobs.discard(job["owner"])
        # Expire without depending on another request arriving to trigger pruning.
        asyncio.get_running_loop().call_later(JOB_TTL, extraction_jobs.pop, job["id"], None)


@app.post("/extractions", status_code=202)
async def start_extraction(request: Request):
    owner, transferred, admitted = None, False, False
    try:
        owner = await authorize(request, consume_quota=False)
        prune_jobs()
        if owner in active_jobs or len(active_jobs) >= int(os.getenv("MAX_CONCURRENT_EXTRACTIONS", "1")) or len(extraction_jobs) >= 100:
            raise DocumentError("Extraction is busy. Please retry shortly.", 429, "rate_limited")
        active_jobs.add(owner)
        admitted = True
        await authorize(request)  # Charge once, never on polling.
        job_id = uuid4().hex
        async def accept(files, form):
            nonlocal transferred
            if not files or len(files) > MAX_FILES:
                raise DocumentError("Upload between 1 and 10 documents.", 413, "file_count")
            job = {"id": job_id, "owner": owner, "status": "processing", "created": monotonic()}
            job["task"] = asyncio.create_task(execute_job(job, files, form))
            extraction_jobs[job_id] = job
            transferred = True
            return JSONResponse({"jobId": job_id, "status": "processing"}, status_code=202)
        return await uploaded_documents(request, job_id, accept=accept)
    except DocumentError as exc:
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=exc.status)
    finally:
        if admitted and not transferred:
            active_jobs.discard(owner)


@app.get("/extractions/{job_id}")
async def extraction_status(job_id: str, request: Request):
    try:
        owner = await authorize(request, consume_quota=False)
        prune_jobs()
        job = extraction_jobs.get(job_id)
        if not job or job["owner"] != owner:
            raise DocumentError("This extraction expired or the server restarted. Please upload the documents again.", 404, "job_not_found")
        payload = {key: job[key] for key in ("status", "result", "error") if key in job}
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except DocumentError as exc:
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=exc.status)
