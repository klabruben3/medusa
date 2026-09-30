import asyncio
import hashlib
import io
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from app.main import app
from app.ai.partials import FIELDS, PARTIALS
from app.ai.generate_module import merge_parts, create_module
from app.utils.documents import Blocks, DocumentError, extract_source, sentences
from app.utils.retrieval import chroma_client, retrieve_contexts, blocking_job
from test_pipeline import sample


class Embeddings:
    def embed(self, texts, **kwargs):
        return SimpleNamespace(embeddings=[[v / 255 for v in hashlib.sha256(t.encode()).digest()] for t in texts])


def source(text="ABC123. Test 1 contributes 100%. Passing requires 50%."):
    blocks = Blocks("synthetic.pdf")
    blocks.add(text, 1, "text")
    return [{"filename": "synthetic.pdf", "blocks": blocks.items, "text": text}]


def parts():
    module = sample().model_dump(exclude_none=True)
    return {purpose: PARTIALS[purpose].model_validate({k: v for k, v in module.items() if k in fields})
            for purpose, fields in FIELDS.items()}


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.client = chroma_client()
        self.before = {c.name for c in self.client.list_collections()}

    def assert_clean(self):
        self.assertEqual({c.name for c in self.client.list_collections()}, self.before)

    def test_real_chroma_success_and_provenance(self):
        embeddings = Embeddings()
        with patch.object(embeddings, "embed", wraps=embeddings.embed) as embed:
            contexts, _ = retrieve_contexts(source(), client=self.client, embeddings=embeddings)
        self.assertEqual(embed.call_count, 2)  # One document batch + all purpose queries.
        self.assertEqual(set(contexts), set(FIELDS))
        self.assertEqual(contexts["grading"][0]["source_file"], "synthetic.pdf")
        self.assertEqual(contexts["grading"][0]["page"], 1)
        self.assert_clean()

    def test_cleanup_after_embedding_failure(self):
        embeddings = Embeddings()
        embeddings.embed = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("private source must not escape"))
        with self.assertRaises(RuntimeError):
            retrieve_contexts(source(), client=self.client, embeddings=embeddings)
        self.assert_clean()

    def test_concurrent_users_cannot_retrieve_other_documents(self):
        def run(marker):
            contexts, _ = retrieve_contexts(source(marker), client=self.client, embeddings=Embeddings())
            for context in contexts.values():
                self.assertEqual([b["content"] for b in context], [marker])
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run, ["PRIVATE_USER_A", "PRIVATE_USER_B"]))
        self.assert_clean()


class MergeTests(unittest.TestCase):
    def test_deterministic_merge_and_progress_removed(self):
        values = parts()
        values["grading"].assessments[0].score = 30
        values["grading"].assessments[0].completed = True
        first = merge_parts(values)
        self.assertEqual(first.module.id, "")
        self.assertIsNone(first.module.assessments[0].score)
        self.assertIsNone(first.module.assessments[0].completed)
        self.assertEqual(first, merge_parts(values))

    def test_conflict_rejected(self):
        values = parts()
        values["identity"].conflicts = ["code conflicts"]
        with self.assertRaises(DocumentError) as caught:
            merge_parts(values)
        self.assertEqual(caught.exception.code, "conflicting_sources")

    def test_unlinked_formula_rejected_without_echoing_source(self):
        values = parts()
        values["grading"].participationFormula.components[0].componentId = "SECRET_FROM_SOURCE"
        with self.assertRaises(DocumentError) as caught:
            merge_parts(values)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_workers_cannot_override_each_others_fields(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            PARTIALS["identity"].model_validate({"code": "ABC123", "name": "Example", "hasExam": True})


class NormalizationTests(unittest.TestCase):
    def test_sentences_preserve_titles_decimals_and_structures(self):
        self.assertEqual(sentences("Dr. Smith teaches. Tests count 12.5%. Exams follow."),
                         ["Dr. Smith teaches.", "Tests count 12.5%.", "Exams follow."])
        blocks = Blocks("source")
        blocks.add("- First item. Second sentence.\n- Second item.", 1)
        blocks.add("PM = test * 0.5 + exam * 0.5", 1)
        self.assertEqual([b["type"] for b in blocks.items], ["list", "structured"])

    def test_native_pdf_and_table_not_ocr_or_sentence_split(self):
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib import colors
        data = io.BytesIO()
        pdf = canvas.Canvas(data)
        pdf.drawString(40, 760, "ABC123 Module assessment guide. This is native text.")
        table = Table([["Assessment", "Marks", "Weight"], ["Test 1", "40", "100%"]], colWidths=[130, 70, 70])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
        table.wrapOn(pdf, 300, 100)
        table.drawOn(pdf, 40, 600)
        pdf.save()
        with patch("app.utils.documents.ocr", side_effect=AssertionError("native text must not require OCR")):
            result, _ = extract_source("guide.pdf", data.getvalue())
        tables = [b for b in result["blocks"] if b["type"] == "table"]
        self.assertEqual(len(tables), 1)
        self.assertEqual(json.loads(tables[0]["content"])["rows"][1], ["Test 1", "40", "100%"])
        self.assertEqual(sum("Test 1" in b["content"] for b in result["blocks"]), 1)

    def test_mime_mismatch_and_image_format(self):
        with self.assertRaises(DocumentError) as caught:
            extract_source("x.pdf", b"%PDF-invalid", "image/png")
        self.assertEqual(caught.exception.status, 415)

    def test_mixed_pdf_ocr_is_cropped_and_decorative_images_skipped(self):
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        data = io.BytesIO()
        pdf = canvas.Canvas(data)
        pdf.drawString(40, 760, "ABC123 Native text that must remain available.")
        picture = ImageReader(Image.new("RGB", (200, 100), "white"))
        pdf.drawImage(picture, 40, 500, width=200, height=100)
        pdf.drawImage(picture, 40, 450, width=10, height=10)
        pdf.save()
        with patch("app.utils.documents.ocr", return_value="Scanned test date 2026-08-01.") as mocked:
            result, _ = extract_source("mixed.pdf", data.getvalue())
        self.assertEqual(mocked.call_count, 1)
        image = mocked.call_args.args[0]
        self.assertLess(image.width, 500)
        self.assertLess(image.height, 250)
        self.assertIn("Native text", result["text"])
        self.assertIn("Scanned test", result["text"])
        self.assertEqual([b["metadata"]["origin"] for b in result["blocks"]], ["native", "ocr"])

    def test_encrypted_pdf_rejected(self):
        from reportlab.lib.pdfencrypt import StandardEncryption
        data = io.BytesIO()
        pdf = canvas.Canvas(data, encrypt=StandardEncryption("password"))
        pdf.drawString(40, 760, "Private guide")
        pdf.save()
        with self.assertRaises(DocumentError) as caught:
            extract_source("encrypted.pdf", data.getvalue())
        self.assertEqual(caught.exception.code, "encrypted_pdf")


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_waits_for_collection_cleanup(self):
        client = chroma_client()
        before = client.count_collections()
        entered, release = threading.Event(), threading.Event()
        class Slow(Embeddings):
            def embed(self, *args, **kwargs):
                entered.set()
                release.wait(3)
                return super().embed(*args, **kwargs)
        task = asyncio.create_task(blocking_job(lambda: retrieve_contexts(source(), client=client, embeddings=Slow())))
        await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(client.count_collections(), before)

    async def test_semantic_grading_repair_uses_source_and_validates_again(self):
        values = parts()
        bad = values["grading"].model_dump()
        bad["finalMarkFormula"] = {"participationWeight": 100, "examWeight": 0}
        payloads = [values["identity"].model_dump(), bad, values["calendar"].model_dump(), values["grading"].model_dump()]
        client = AsyncMock()
        client.chat.completions.create.side_effect = [SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(value)))]) for value in payloads]
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        contexts = {purpose: [{"content": "original evidence"}] for purpose in FIELDS}
        with patch.dict("os.environ", {"GROQ_API_KEY": "test"}), patch("app.ai.generate_module.AsyncGroq", return_value=manager), patch("app.ai.generate_module.collect_evidence", new=AsyncMock(return_value=(contexts, []))), patch("app.ai.provider.limiter.reserve", new=AsyncMock()):
            result = await create_module(source())
        self.assertFalse(result.module.hasExam)
        self.assertIsNone(result.module.finalMarkFormula)
        final_messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertIn("original evidence", final_messages[1]["content"])
        self.assertIn("Final mark weights", final_messages[2]["content"])

    async def test_three_focused_calls_use_preserved_default_and_overrides(self):
        values = parts()
        responses = [SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=values[p].model_dump_json()))]) for p in FIELDS]
        client = AsyncMock()
        client.chat.completions.create.side_effect = responses
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        contexts = {purpose: [{"content": purpose + " evidence"}] for purpose in FIELDS}
        with patch.dict("os.environ", {"GROQ_API_KEY": "test", "GROQ_CALENDAR_MODEL": "configured-calendar"}), patch("app.ai.generate_module.AsyncGroq", return_value=manager), patch("app.ai.generate_module.collect_evidence", new=AsyncMock(return_value=(contexts, []))), patch("app.ai.provider.limiter.reserve", new=AsyncMock()):
            result = await create_module(source())
        calls = client.chat.completions.create.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].kwargs["model"], "openai/gpt-oss-20b")
        self.assertEqual(calls[1].kwargs["model"], "openai/gpt-oss-120b")
        self.assertEqual(calls[2].kwargs["model"], "configured-calendar")
        self.assertNotIn("grading evidence", calls[0].kwargs["messages"][1]["content"])
        self.assertEqual(result.module.moduleId, "abc123")


class SecurityTests(unittest.TestCase):
    def test_pdf_to_review_response_full_pipeline(self):
        data = io.BytesIO()
        pdf = canvas.Canvas(data)
        pdf.drawString(40, 760, "ABC123 Example. Class Test 1 has 40 marks and a weight of 100%.")
        pdf.drawString(40, 740, "No exam. Pass mark 50%. Semester: 2026-07-01 to 2026-11-01.")
        pdf.save()
        chroma = chroma_client()
        before = chroma.count_collections()
        values = parts()
        provider = AsyncMock()
        async def answer(**kwargs):
            schema_name = kwargs["response_format"]["json_schema"]["name"]
            if schema_name == "EvidenceExtraction":
                blocks = json.loads(kwargs["messages"][1]["content"])
                value = {"reviewedBlockIds": [b["id"] for b in blocks], "facts": [
                    {"blockId": b["id"], "purpose": purpose, "quote": b["content"]}
                    for b in blocks for purpose in FIELDS]}
                content = json.dumps(value)
            else:
                content = values[schema_name.removesuffix("Extraction").lower()].model_dump_json()
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))])
        provider.chat.completions.create.side_effect = answer
        manager = AsyncMock()
        manager.__aenter__.return_value = provider
        with patch("app.main.authorize", new=AsyncMock(return_value="owner")), patch.dict("os.environ", {"GROQ_API_KEY": "test"}), patch("app.utils.retrieval.embedder", side_effect=AssertionError("Default path must not use embeddings")), patch("app.ai.provider.limiter.reserve", new=AsyncMock()), patch("app.ai.generate_module.AsyncGroq", return_value=manager), TestClient(app) as client:
            response = client.post("/process-documents", files={"files": ("plan.pdf", data.getvalue(), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["module"]["id"], "")
        self.assertEqual(response.json()["module"]["assessments"][0]["maxScore"], 40)
        self.assertEqual(provider.chat.completions.create.call_count, 3)
        self.assertEqual(chroma.count_collections(), before)

    def test_unauthenticated_upload_rejected_before_parsing(self):
        with TestClient(app) as client:
            response = client.post("/process-documents", content=b"not multipart")
        self.assertEqual(response.status_code, 401)

    def test_provider_exception_does_not_leak_contents(self):
        with patch("app.main.authorize", new=AsyncMock(return_value="owner")), patch("app.main.extract_source", side_effect=RuntimeError("SECRET_DOCUMENT")), TestClient(app) as client:
            response = client.post("/process-documents", files={"files": ("a.pdf", b"pdf")})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("SECRET", response.text)

    def test_stream_limit_and_no_paths(self):
        with patch("app.main.authorize", new=AsyncMock(return_value="owner")), patch("app.main.MAX_REQUEST_BYTES", 200), TestClient(app) as client:
            response = client.post("/process-documents", files={"files": ("a.pdf", b"x" * 500)})
        self.assertEqual(response.status_code, 413)
        with patch("app.main.authorize", new=AsyncMock(return_value="owner")), TestClient(app) as client:
            response = client.post("/process-documents", json={"fileReference": "../../secret"})
        self.assertNotEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
