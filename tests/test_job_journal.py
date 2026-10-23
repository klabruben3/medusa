import hashlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from app.utils import job_journal


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return httpx.Response(response[0], json=response[1], request=httpx.Request("POST", url))


class JournalTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_configuration_preserves_the_existing_processing_path(self):
        with patch.dict(os.environ, {"ACADEMIQ_DURABLE_JOBS": "false"}), patch.object(job_journal.httpx, "AsyncClient") as client:
            self.assertIsNone(await job_journal.start(SimpleNamespace(headers={}), "a" * 32, 1))
            client.assert_not_called()

    async def test_admission_retries_the_same_owner_scoped_identity_and_hash(self):
        identifier = "a" * 32
        client = Client([httpx.ReadTimeout("fixture"), (200, identifier)])
        with patch.dict(os.environ, {"ACADEMIQ_DURABLE_JOBS": "true", "SUPABASE_URL": "https://project.example.test", "SUPABASE_ANON_KEY": "public-fixture"}), patch.object(job_journal.httpx, "AsyncClient", return_value=client), patch.object(job_journal.asyncio, "sleep", new=AsyncMock()):
            ticket = await job_journal.start(SimpleNamespace(headers={"authorization": "Bearer owner-session-fixture"}), identifier, 2)
        self.assertIsNotNone(ticket)
        self.assertEqual(len(client.calls), 2)
        first, second = (call[1] for call in client.calls)
        self.assertEqual(first["json"], second["json"])
        self.assertEqual(first["headers"]["Authorization"], "Bearer owner-session-fixture")
        self.assertEqual(first["json"]["p_proof_hash"], hashlib.sha256(ticket["proof"].encode()).hexdigest())
        self.assertNotIn("p_user", first["json"])

    async def test_completion_uses_only_the_job_capability_and_a_fixed_destination(self):
        client = Client([(200, {"accepted": True})])
        job = {"id": "a" * 32, "status": "completed", "result": {"module": {}, "warnings": []}, "journal": {"id": "a" * 32, "proof": "b" * 64}}
        with patch.object(job_journal.httpx, "AsyncClient", return_value=client):
            self.assertTrue(await job_journal.finish(job))
        url, sent = client.calls[0]
        self.assertEqual(url, "https://academiq.studio/api/native/documents/complete")
        self.assertEqual(sent["headers"]["Authorization"], "Bearer " + "b" * 64)
        self.assertNotIn("proof", sent["json"])
        self.assertNotIn("owner", sent["json"])

    async def test_oversized_results_remain_completed_without_silently_truncating_content(self):
        client = Client([(200, {"accepted": True})])
        original = {"module": {"name": "x" * (job_journal.RESULT_LIMIT + 1)}, "warnings": []}
        job = {"id": "a" * 32, "status": "completed", "result": original, "journal": {"id": "a" * 32, "proof": "b" * 64}}
        with patch.object(job_journal.httpx, "AsyncClient", return_value=client):
            self.assertTrue(await job_journal.finish(job))
        self.assertNotIn("result", client.calls[0][1]["json"])
        self.assertEqual(client.calls[0][1]["json"]["errorCode"], "result_not_retained")
        self.assertIs(job["result"], original)
        self.assertEqual(job["status"], "completed")

    async def test_expired_capability_does_not_retry(self):
        client = Client([(409, {"error": "Unavailable"})])
        job = {"id": "a" * 32, "status": "failed", "error": {"code": "timeout"}, "journal": {"id": "a" * 32, "proof": "b" * 64}}
        with patch.object(job_journal.httpx, "AsyncClient", return_value=client), patch.object(job_journal.asyncio, "sleep", new=AsyncMock()) as sleep:
            self.assertFalse(await job_journal.finish(job))
        self.assertEqual(len(client.calls), 1)
        sleep.assert_not_awaited()

    async def test_uncertain_transport_has_bounded_retries_and_redacted_diagnostics(self):
        client = Client([httpx.ReadTimeout("fixture")] * 3)
        job = {"id": "a" * 32, "status": "failed", "error": {"code": "timeout"}, "journal": {"id": "a" * 32, "proof": "b" * 64}}
        with patch.object(job_journal.httpx, "AsyncClient", return_value=client), patch.object(job_journal.asyncio, "sleep", new=AsyncMock()) as sleep, self.assertLogs(job_journal.logger, level="WARNING") as logs:
            self.assertFalse(await job_journal.finish(job))
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(sleep.await_count, 2)
        self.assertNotIn(job["journal"]["proof"], " ".join(logs.output))
