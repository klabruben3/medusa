import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.ai.provider import complete
from app.utils.documents import DocumentError


class ProcessingReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_review_or_any_requirement_blocks_before_provider_and_admission(self):
        keys = [f"AI_GROQ_{key}_VERIFIED" for key in ("NO_TRAINING", "RETENTION", "INTERNATIONAL_TRANSFER", "MINOR_SAFEGUARDS")]
        settings = {**{key: "true" for key in keys}, "AI_GROQ_REVIEW_REFERENCE": "synthetic-review"}
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())))
        for missing in [None, *settings]:
            values = {} if missing is None else {key: value for key, value in settings.items() if key != missing}
            with self.subTest(missing=missing), patch.dict(os.environ, values, clear=True), patch("app.ai.provider.limiter.reserve", new=AsyncMock()) as reserve:
                with self.assertRaises(DocumentError) as caught:
                    await complete(client, "identity", [{"role": "user", "content": "PRIVATE"}], {}, 1)
                self.assertEqual(caught.exception.code, "provider_review_required")
                self.assertEqual(caught.exception.status, 503)
                self.assertNotIn("PRIVATE", str(caught.exception))
                reserve.assert_not_awaited()
        client.chat.completions.create.assert_not_awaited()

    async def test_complete_review_preserves_existing_provider_call(self):
        settings = {**{f"AI_GROQ_{key}_VERIFIED": "true" for key in ("NO_TRAINING", "RETENTION", "INTERNATIONAL_TRANSFER", "MINOR_SAFEGUARDS")}, "AI_GROQ_REVIEW_REFERENCE": "synthetic-review"}
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value="synthetic-result"))))
        with patch.dict(os.environ, settings, clear=True), patch("app.ai.provider.limiter.reserve", new=AsyncMock()):
            self.assertEqual(await complete(client, "identity", [], {}, 1), "synthetic-result")
        client.chat.completions.create.assert_awaited_once()
