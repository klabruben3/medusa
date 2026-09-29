import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from starlette.requests import Request
from app.utils.auth import authorize
from app.utils.documents import DocumentError
from app.main import uploaded_documents


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def auth(self, user_status=200, user=None, quota=True):
        user = user if user is not None else {"id": "verified-owner", "is_anonymous": False}
        client = AsyncMock()
        client.get.return_value = httpx.Response(user_status, json=user, request=httpx.Request("GET", "https://example.supabase.co/auth/v1/user"))
        client.post.return_value = httpx.Response(200, json=quota, request=httpx.Request("POST", "https://example.supabase.co/rest/v1/rpc/consume_ai_quota"))
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        request = Request({"type": "http", "headers": [(b"authorization", b"Bearer test-token")]})
        with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "test-key"}), patch("app.utils.auth.httpx.AsyncClient", return_value=manager):
            return await authorize(request), client

    async def test_verified_owner_and_existing_quota(self):
        owner, client = await self.auth()
        self.assertEqual(owner, "verified-owner")
        self.assertEqual(client.post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")

    async def test_expired_anonymous_and_quota(self):
        for kwargs, status in [({"user_status": 401}, 401), ({"user": {"id": "x", "is_anonymous": True}}, 403), ({"quota": False}, 429)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(DocumentError) as caught:
                await self.auth(**kwargs)
            self.assertEqual(caught.exception.status, status)


class UploadCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_during_parse_closes_partial_file(self):
        handles = []
        class Parser:
            def __init__(self, *args, **kwargs):
                handle = io.BytesIO(b"private upload")
                handles.append(handle)
                self._files_to_close_on_error = [handle]
            async def parse(self):
                raise asyncio.CancelledError()
        request = Request({"type": "http", "headers": []})
        with patch("app.main.MultiPartParser", Parser), self.assertRaises(asyncio.CancelledError):
            await uploaded_documents(request, "job")
        self.assertTrue(handles[0].closed)

    async def test_chunked_limit_closes_spooled_file(self):
        from starlette.datastructures import Headers
        boundary = b"testboundary"
        chunks = [b"--" + boundary + b'\r\nContent-Disposition: form-data; name="files"; filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\nabc', b"x" * 1000]
        async def receive():
            return {"type": "http.request", "body": chunks.pop(0), "more_body": bool(chunks)}
        request = Request({"type": "http", "headers": Headers({"content-type": "multipart/form-data; boundary=testboundary"}).raw}, receive)
        with patch("app.main.MAX_REQUEST_BYTES", 200), self.assertRaises(DocumentError) as caught:
            await uploaded_documents(request, "job")
        self.assertEqual(caught.exception.status, 413)
