import asyncio
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from app.main import app, active_jobs, extraction_jobs
from app.types.schema import ExtractionResult
from app.utils.documents import DocumentError
from test_pipeline import sample


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        active_jobs.clear()
        extraction_jobs.clear()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        tasks = [j["task"] for j in extraction_jobs.values()]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        active_jobs.clear()
        extraction_jobs.clear()
        await self.client.aclose()

    async def test_owner_polling_no_extra_quota_and_upload_cleanup(self):
        handles = []
        async def process(files, job_id):
            handles.extend(f.file for f in files)
            return ExtractionResult(module=sample())
        with patch("app.main.authorize", new=AsyncMock(return_value="owner")) as auth, patch("app.main.process_documents", side_effect=process):
            started = await self.client.post("/extractions", files={"files": ("x.pdf", b"fixture")})
            self.assertEqual(started.status_code, 202, started.text)
            job_id = started.json()["jobId"]
            await extraction_jobs[job_id]["task"]
            polled = await self.client.get("/extractions/" + job_id)
            self.assertEqual(polled.json()["status"], "completed")
            self.assertEqual(polled.json()["result"]["module"]["code"], "ABC123")
            self.assertEqual(sum(c.kwargs.get("consume_quota", True) for c in auth.call_args_list), 1)
            self.assertTrue(all(h.closed for h in handles))
            self.assertNotIn("owner", active_jobs)
            auth.return_value = "different-user"
            denied = await self.client.get("/extractions/" + job_id)
            self.assertEqual(denied.status_code, 404)
            self.assertNotIn("ABC123", denied.text)

    async def test_failure_closes_upload_and_preserves_safe_error(self):
        handles = []
        async def process(files, job_id):
            handles.extend(f.file for f in files)
            raise DocumentError("Missing facts", 422, "missing_facts")
        with patch("app.main.authorize", new=AsyncMock(return_value="owner")), patch("app.main.process_documents", side_effect=process):
            started = await self.client.post("/extractions", files={"files": ("x.pdf", b"fixture")})
            job_id = started.json()["jobId"]
            await extraction_jobs[job_id]["task"]
            result = await self.client.get("/extractions/" + job_id)
            self.assertEqual(result.json()["error"]["code"], "missing_facts")
            self.assertTrue(all(h.closed for h in handles))

    async def test_busy_request_cannot_release_existing_admission(self):
        active_jobs.add("owner")
        with patch("app.main.authorize", new=AsyncMock(return_value="owner")) as auth:
            response = await self.client.post("/extractions", files={"files": ("x.pdf", b"fixture")})
            self.assertEqual(response.status_code, 429)
            self.assertIn("owner", active_jobs)
            self.assertEqual(auth.await_count, 1)
            self.assertFalse(auth.call_args.kwargs["consume_quota"])

    async def test_restart_or_unknown_job_is_explicit(self):
        with patch("app.main.authorize", new=AsyncMock(return_value="owner")):
            response = await self.client.get("/extractions/unknown")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["code"], "job_not_found")
