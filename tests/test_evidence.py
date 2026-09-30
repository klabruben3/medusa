import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.ai.evidence import sections, collect_evidence, extract_batch
from app.ai.provider import ModelLimiter, complete
from app.utils.documents import DocumentError


def response(value, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=json.dumps(value)))])


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    def test_section_boundaries_cover_all_source_characters(self):
        text = "\n".join(f"Assessment {i}: 40 marks. Toets. 文本" for i in range(200))
        result = sections([{"filename": "plan.txt", "text": text}])
        self.assertGreater(len(result), 1)
        for line in text.splitlines():
            self.assertTrue(any(line in block["content"] for block in result))
        self.assertTrue(all(len(block["content"].encode()) <= 4500 for block in result))

    def test_table_sections_repeat_header_and_preserve_every_row(self):
        rows = [["Assessment", "Marks"]] + [[f"Test {i}", "40"] for i in range(120)]
        from app.utils.documents import Blocks
        blocks = Blocks("plan.pdf")
        blocks.add(json.dumps({"rows": rows}), 1, "table")
        result = sections([{"blocks": blocks.items}], max_bytes=600)
        found = []
        for block in result:
            section_rows = json.loads(block["content"])["rows"]
            self.assertEqual(section_rows[0], rows[0])
            found.extend(section_rows[1:])
        self.assertEqual(found, rows[1:])

    async def test_every_section_is_read_without_embeddings(self):
        reviewed = []
        async def answer(client, purpose, messages, schema, output_tokens):
            blocks = json.loads(messages[1]["content"])
            reviewed.extend(b["id"] for b in blocks)
            return response({"decisions": [{"blockId": b["id"], "purposes": ["grading"]} for b in blocks]})
        sources = [{"filename": "plan.txt", "text": "\n\n".join(f"Test {i} has 40 marks." for i in range(300))}]
        with patch("app.ai.evidence.complete", side_effect=answer):
            contexts, notes = await collect_evidence(None, sources)
        self.assertEqual(set(reviewed), {b["id"] for b in sections(sources)})
        self.assertTrue(any("Test 299" in b["content"] for b in contexts["grading"]))

    async def test_unknown_duplicate_and_missing_ids_fail_closed(self):
        blocks = [{"id": "a", "content": "Test: 40 marks", "source_file": "x", "page": 1}]
        for value in [{"decisions": []}, {"decisions": [{"blockId": "invented", "purposes": ["grading"]}]},
                      {"decisions": [{"blockId": "a", "purposes": []}, {"blockId": "a", "purposes": []}]}]:
            with patch("app.ai.evidence.complete", new=AsyncMock(return_value=response(value))), self.assertRaises(DocumentError):
                await extract_batch(None, blocks)

    async def test_truncation_splits_batch_without_dropping_second_block(self):
        blocks = [{"id": name, "content": "Test " + name, "source_file": "x", "page": 1} for name in ["a", "b"]]
        responses = [response({}, "length")] + [response({"decisions": [
            {"blockId": b["id"], "purposes": ["grading"]}]}) for b in blocks]
        with patch("app.ai.evidence.complete", new=AsyncMock(side_effect=responses)):
            result = await extract_batch(None, blocks)
        self.assertEqual([b["id"] for b in result], ["a", "b"])

    async def test_source_text_is_copied_exactly_including_table_escaping(self):
        text = 'Toets\u00a01\n40 marks — 25%\n{"rows": [["Assessment", "Weight"], ["Test 1", "25%"]]}'
        blocks = [{"id": "a", "content": text, "source_file": "x.pdf", "page": 2}]
        with patch("app.ai.evidence.complete", new=AsyncMock(return_value=response({"decisions": [{"blockId": "a", "purposes": ["grading", "calendar"]}]}))):
            result = await extract_batch(None, blocks)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(item["content"] == text and item["page"] == 2 for item in result))

    async def test_failure_logs_reason_without_source_text(self):
        blocks = [{"id": "a", "content": "PRIVATE_SOURCE", "source_file": "private.pdf", "page": 1}]
        with patch("app.ai.evidence.complete", new=AsyncMock(return_value=response({}))), self.assertLogs("app.ai.evidence", level="WARNING") as logs:
            with self.assertRaises(DocumentError) as caught:
                await extract_batch(None, blocks, depth=3)
        self.assertEqual(caught.exception.code, "evidence_classification_failed")
        self.assertIn("invalid_schema", str(caught.exception))
        self.assertNotIn("PRIVATE_SOURCE", str(logs.output))


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_per_model_and_accounts_for_reserved_output(self):
        now = [0.0]
        waits = []
        async def sleep(delay):
            waits.append(delay)
            now[0] += delay
        limiter = ModelLimiter(clock=lambda: now[0], sleep=sleep)
        with patch.dict("os.environ", {"GROQ_TPM_BUDGET": "8000"}):
            await limiter.reserve("20b", 5000)
            await limiter.reserve("120b", 5000)
            self.assertEqual(waits, [])
            await limiter.reserve("20b", 3000)
            self.assertEqual(waits, [61])
            with self.assertRaises(DocumentError):
                await limiter.reserve("20b", 8000)

    async def test_oversize_rejected_before_provider_request(self):
        client = AsyncMock()
        with patch.dict("os.environ", {"GROQ_TPM_BUDGET": "8000"}), self.assertRaises(DocumentError):
            await complete(client, "grading", [{"role": "user", "content": "x" * 30000}], {}, 2500)
        client.chat.completions.create.assert_not_called()
