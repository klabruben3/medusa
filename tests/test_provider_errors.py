import json
import unittest
import httpx
from groq import APIStatusError
from app.main import groq_failure


class ProviderErrorTests(unittest.TestCase):
    def test_safe_actionable_provider_errors(self):
        for status, provider_code, expected in [
            (401, None, "groq_auth_failed"),
            (403, None, "groq_access_denied"),
            (400, "model_decommissioned", "groq_model_unavailable"),
            (400, "json_validate_failed", "groq_schema_failed"),
            (400, "context_length_exceeded", "groq_context_limit"),
            (413, None, "groq_request_too_large"),
            (400, "SECRET_DOCUMENT", "groq_request_rejected"),
            (503, None, "groq_unavailable"),
        ]:
            with self.subTest(status=status, code=provider_code):
                response = httpx.Response(status, request=httpx.Request("POST", "https://api.groq.com"))
                exc = APIStatusError("SECRET_DOCUMENT", response=response, body={"error": {
                    "code": provider_code, "message": "SECRET_DOCUMENT", "failed_generation": "SECRET_DOCUMENT"}})
                with self.assertLogs("app.main", level="WARNING") as logs:
                    result = groq_failure(exc, "test-job")
                self.assertEqual(json.loads(result.body)["code"], expected)
                self.assertNotIn("SECRET_DOCUMENT", result.body.decode() + str(logs.output))
