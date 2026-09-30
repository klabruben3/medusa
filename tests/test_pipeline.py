import io
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from fastapi.testclient import TestClient
from app.main import app
from app.types.schema import Module, ExtractionResult
from app.utils.documents import extract_source, DocumentError
from app.utils.validation import validate_module
from app.ai.generate_module import create_module


def sample():
    return Module(moduleId="abc123", code="ABC123", name="Example", semesterStart="2026-07-01",
                  semesterEnd="2026-11-01", hasExam=False, addedYear=2026,
                  assessments=[dict(id="abc123-test-1", name="Test 1", type="class-test", category="tests", weight=0, maxScore=40)],
                  participationFormula=dict(components=[dict(componentId="abc123-tests", weight=100)], minimumToPass=50))


class ValidationTests(unittest.TestCase):
    def test_category_and_direct_references(self):
        module = sample()
        self.assertEqual(validate_module(module), [])
        module.participationFormula.components[0].componentId = "abc123-test-1"
        self.assertEqual(validate_module(module), [])

    def test_dangling_reference(self):
        module = sample()
        module.participationFormula.components[0].componentId = "missing"
        self.assertTrue(any("no matching" in e for e in validate_module(module)))

    def test_bad_dates_marks_and_drop_rules(self):
        module = sample()
        module.assessments[0].date = "2026-02-30"
        module.assessments[0].maxScore = 0
        module.participationFormula.components[0].dropLowest = 1
        self.assertEqual(len(validate_module(module)), 3)

    def test_completion_not_dropping(self):
        module = sample()
        component = module.participationFormula.components[0]
        component.totalInCategory = 9
        component.minimumCompleted = 7
        self.assertEqual(validate_module(module), [])
        self.assertIsNone(component.dropLowest)

    def test_fractional_or_incomplete_formula_totals_are_rejected(self):
        module = sample()
        for weight in (1, 0, 80):
            module.participationFormula.components[0].weight = weight
            self.assertTrue(any("total 100" in error for error in validate_module(module)))


class DocumentTests(unittest.TestCase):
    def test_pdf_all_pages_and_bilingual_text_retained(self):
        from reportlab.pdfgen import canvas
        data = io.BytesIO()
        pdf = canvas.Canvas(data)
        pdf.drawString(40, 700, "Student assessment. Toets: 20%.")
        pdf.showPage()
        pdf.drawString(40, 700, "Final assessment: 80%.")
        pdf.save()
        source, _ = extract_source("plan.pdf", data.getvalue())
        self.assertIn("Student assessment", source["text"])
        self.assertIn("Toets", source["text"])
        self.assertIn("Final assessment", source["text"])

    def test_docx_fixture_retains_content(self):
        from pathlib import Path
        source, _ = extract_source("guide.docx", Path("tests/test_file.docx").read_bytes())
        self.assertGreater(len(source["text"]), 100)

    def test_invalid_files(self):
        for name in ["a.exe", "a.pdf", "a.docx"]:
            with self.subTest(name=name), self.assertRaises(DocumentError):
                extract_source(name, b"not a document")

    def test_image_ocr(self):
        from PIL import Image
        data = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(data, format="PNG")
        with patch("app.utils.documents.ocr", return_value="Student assessment: 20%"):
            source, warnings = extract_source("a.png", data.getvalue())
        self.assertIn("Student assessment", source["text"])
        self.assertTrue(warnings)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        auth = patch("app.main.authorize", new=AsyncMock(return_value="test-user"))
        auth.start()
        self.addCleanup(auth.stop)

    def test_success_contract(self):
        result = ExtractionResult(module=sample())
        with patch("app.main.extract_source", return_value=({"filename": "x.pdf", "text": "facts"}, ["Review OCR"])), patch("app.main.create_module", new=AsyncMock(return_value=result)):
            response = self.client.post("/process-documents", files=[("files", ("x.pdf", b"pdf", "application/pdf"))])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["module"]["id"], "")
        self.assertNotIn("score", response.json()["module"]["assessments"][0])
        self.assertEqual(response.json()["warnings"], ["Review OCR"])

    def test_empty_and_unsupported(self):
        for filename, content, status in [("a.pdf", b"", 422), ("a.exe", b"x", 415)]:
            response = self.client.post("/process-documents", files={"files": (filename, content)})
            self.assertEqual(response.status_code, status)

    def test_ocr_unavailable(self):
        with patch("app.main.extract_source", side_effect=DocumentError("OCR unavailable", 503)):
            response = self.client.post("/process-documents", files={"files": ("a.png", b"image")})
        self.assertEqual(response.status_code, 503)


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reservation = patch("app.ai.provider.limiter.reserve", new=AsyncMock())
        reservation.start()
        self.addCleanup(reservation.stop)

    async def test_repairs_invalid_worker_schema(self):
        import json
        from app.ai.generate_module import run_worker
        def response(value):
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(value)))])
        client = AsyncMock()
        client.chat.completions.create.side_effect = [response({"code": 123}), response({"code": "ABC123", "name": "Example"})]
        result = await run_worker(client, "identity", [])
        self.assertEqual(client.chat.completions.create.await_count, 2)
        self.assertEqual(result.code, "ABC123")

    async def test_truncated_model_response_is_not_success(self):
        client = AsyncMock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content="{}"))])
        from app.ai.generate_module import run_worker
        with self.assertRaises(DocumentError):
            await run_worker(client, "identity", [])


if __name__ == "__main__":
    unittest.main()
