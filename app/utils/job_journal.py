"""Optional durable journal using the existing Supabase user session.

Only the per-job completion capability survives session expiry. It never reaches
the browser and cannot read results, start processing, or affect another job.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import secrets

import httpx

logger = logging.getLogger(__name__)
COMPLETION_URL = "https://academiq.studio/api/native/documents/complete"
RESULT_LIMIT = 262144


def enabled():
    return os.getenv("ACADEMIQ_DURABLE_JOBS", "").strip().lower() in {"1", "true"}


async def start(request, job_id, file_count):
    if not enabled():
        return None
    proof = secrets.token_hex(32)
    origin = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    headers = {"Authorization": request.headers.get("authorization", ""),
               "apikey": os.getenv("SUPABASE_ANON_KEY", "").strip()}
    body = {"p_id": job_id, "p_proof_hash": hashlib.sha256(proof.encode()).hexdigest(),
            "p_file_count": file_count}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            for attempt in range(3):
                try:
                    response = await client.post(origin + "/rest/v1/rpc/academiq_start_document_job",
                                                 headers=headers, json=body)
                    if response.status_code < 500 and response.status_code != 429:
                        response.raise_for_status()
                        if response.json() != job_id:
                            raise ValueError("Unexpected journal identity")
                        return {"id": job_id, "proof": proof}
                except (httpx.TransportError, ValueError):
                    pass
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
    except (httpx.HTTPError, ValueError):
        pass
    # Preserve ordinary extraction if durable storage is temporarily unavailable.
    # The response explicitly tells the browser to remain open in this case.
    logger.warning("stage=journal_unavailable job=%s", job_id)
    return None


async def finish(job):
    journal = job.get("journal")
    if not journal or job.get("status") not in {"completed", "failed"}:
        return False
    body = {"jobId": journal["id"], "status": job["status"]}
    if job["status"] == "completed":
        result = job.get("result")
        if len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= RESULT_LIMIT:
            body["result"] = result
        else:
            body["errorCode"] = "result_not_retained"
    else:
        code = job.get("error", {}).get("code", "processing_error")
        body["errorCode"] = code if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,80}", code) else "processing_error"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            for attempt in range(3):
                try:
                    response = await client.post(COMPLETION_URL, headers={"Authorization": "Bearer " + journal["proof"]}, json=body)
                    if response.status_code == 200 and response.json().get("accepted") is True:
                        return True
                    if response.status_code < 500 and response.status_code != 429:
                        break  # Expired/rejected capabilities must not retry indefinitely.
                except (httpx.TransportError, ValueError):
                    pass
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
    except httpx.HTTPError:
        pass
    logger.warning("stage=journal_completion_unconfirmed job=%s", job["id"])
    return False
