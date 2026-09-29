"""Verify the same Supabase session Academiq uses; never trust a browser user ID."""
import os
from urllib.parse import urlparse
import httpx
from fastapi import Request
from .documents import DocumentError


async def authorize(request: Request):
    token = request.headers.get("authorization", "")
    if not token.startswith("Bearer ") or len(token) > 8192:
        raise DocumentError("Sign in to extract a module.", 401, "unauthorized")
    origin = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    parsed = urlparse(origin)
    if not key or parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise DocumentError("The extraction service is not configured.", 503, "not_configured")
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            headers = {"Authorization": token, "apikey": key}
            response = await client.get(origin + "/auth/v1/user", headers=headers)
            if response.status_code in {401, 403}:
                raise DocumentError("Your session expired. Sign in again.", 401, "unauthorized")
            response.raise_for_status()
            user = response.json()
            if not user.get("id") or user.get("is_anonymous", False):
                raise DocumentError("Sign in with a registered account to extract modules.", 403, "unauthorized")
            # Reuse Academiq's existing atomic per-user AI quota, including RLS.
            quota = await client.post(origin + "/rest/v1/rpc/consume_ai_quota", headers=headers, json={})
            quota.raise_for_status()
            if quota.json() is not True:
                raise DocumentError("Your AI request limit has been reached. Try again later.", 429, "account_limit")
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, DocumentError):
            raise
        raise DocumentError("Sign-in verification is temporarily unavailable.", 503, "auth_unavailable") from exc
    return user["id"]
