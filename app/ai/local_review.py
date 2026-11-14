"""Explicit, bounded CLI review context. No HTTP route or environment enables it."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
import hashlib
import re

from ..utils.documents import DocumentError

_active = ContextVar("medusa_local_document_review", default=None)


def reject():
    raise DocumentError("The local document review does not cover this request.", 503, "provider_review_required")


def verify_local_review(client=None):
    value = _active.get()
    if value is None:
        return False
    expiry, key_hash = value
    if datetime.now(timezone.utc) >= expiry:
        reject()
    if client is not None:
        if hashlib.sha256(str(getattr(client, "api_key", "")).encode()).hexdigest() != key_hash:
            reject()
        # The installed Groq SDK uses the API root and adds /openai/v1 itself.
        if str(getattr(client, "base_url", "")).rstrip("/") != "https://api.groq.com":
            reject()
    return True


@contextmanager
def local_document_review(record, inputs, api_key):
    """Enter only after matching the reviewed original files and credential.

    Input hashes are computed by the trusted local runner from original bytes.
    This approval never sets the general service's verification environment.
    """
    try:
        expiry = datetime.fromisoformat(record["expiresAt"])
        now = datetime.now(timezone.utc)
        expected = sorted((item["file"], item["sha256"]) for item in record["inputs"])
        actual = sorted((item["file"], item["sha256"]) for item in inputs)
        valid = (record["scope"] == "local-nwu-acceptance" and record["ownerApproved"] is True
                 and record["dataClassification"] == "institutional-course-documents-no-student-records"
                 and record["noTrainingTermsReviewed"] is True and record["usProcessingReviewed"] is True
                 and record["retentionReviewed"] == "standard-up-to-30-days-not-zdr-attested"
                 and record["reference"].startswith("local-nwu:")
                 and now < expiry <= now + timedelta(days=2)
                 and bool(expected) and expected == actual and len(set(expected)) == len(expected)
                 and all(re.fullmatch(r"[a-f0-9]{64}", digest) for _, digest in expected)
                 and bool(api_key) and hashlib.sha256(api_key.encode()).hexdigest() == record["apiKeySha256"])
    except (KeyError, TypeError, ValueError):
        reject()
    if not valid:
        reject()
    token = _active.set((expiry, record["apiKeySha256"]))
    try:
        yield
    finally:
        _active.reset(token)
