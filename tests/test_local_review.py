import hashlib
import os
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.local_review import local_document_review
from app.ai.provider import verify_processing_review
from app.utils.documents import DocumentError


class LocalReviewTests(unittest.TestCase):
    def fixture(self):
        inputs = [{"file": "schedule.pdf", "sha256": "a" * 64}]
        key = "disposable-fixture-credential"
        record = {"scope": "local-nwu-acceptance", "ownerApproved": True,
                  "dataClassification": "institutional-course-documents-no-student-records",
                  "noTrainingTermsReviewed": True, "usProcessingReviewed": True,
                  "retentionReviewed": "standard-up-to-30-days-not-zdr-attested",
                  "reference": "local-nwu:fixture", "inputs": inputs,
                  "expiresAt": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                  "apiKeySha256": hashlib.sha256(key.encode()).hexdigest()}
        return record, inputs, key

    def test_context_covers_only_matching_files_key_origin_and_lifetime(self):
        record, inputs, key = self.fixture()
        client = SimpleNamespace(api_key=key, base_url="https://api.groq.com/")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DocumentError):
                verify_processing_review(client)
            with local_document_review(record, inputs, key):
                verify_processing_review(client)
                for invalid in (SimpleNamespace(api_key="wrong", base_url=client.base_url),
                                SimpleNamespace(api_key=key, base_url="https://evil.example/")):
                    with self.assertRaises(DocumentError):
                        verify_processing_review(invalid)
            with self.assertRaises(DocumentError):
                verify_processing_review(client)

    def test_changed_source_expired_and_broader_review_cannot_enter(self):
        record, inputs, key = self.fixture()
        for changed in ({**record, "inputs": [{"file": "other.pdf", "sha256": "a" * 64}]},
                        {**record, "expiresAt": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
                        {**record, "scope": "production"}, {**record, "ownerApproved": False}):
            with self.assertRaises(DocumentError), local_document_review(changed, inputs, key):
                self.fail("Review should not activate")

    def test_copying_local_reference_to_service_environment_does_not_approve_users(self):
        settings = {**{f"AI_GROQ_{k}_VERIFIED": "true" for k in
                      ("NO_TRAINING", "RETENTION", "INTERNATIONAL_TRANSFER", "MINOR_SAFEGUARDS")},
                    "AI_GROQ_REVIEW_REFERENCE": "local-nwu:fixture"}
        with patch.dict(os.environ, settings, clear=True), self.assertRaises(DocumentError):
            verify_processing_review()
