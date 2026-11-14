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
    def test_calendar_only_table_retains_assessment_scope_and_adjacent_dates(self):
        from app.ai.evidence import preserve_continuations
        rows = [["Group A"], ["Date", "Topic"], ["11-Oct", "Vectors"],
                ["12-Oct", "Class test 2 (4.2.2–5.2)"], ["13-Oct", "Continuation"],
                ["28-Oct", "Examination starts"]]
        block = {"id": "s1-b2-part0", "type": "table", "source_file": "plan.pdf", "page": 2,
                 "content": json.dumps({"rows": rows}, ensure_ascii=False)}
        contexts = {"identity": [], "calendar": [block], "grading": []}
        result = preserve_continuations(contexts, [block])
        selected = result["grading"][0]
        self.assertEqual(selected["sourceRowIndices"], [0, 1, 2, 3, 4])
        self.assertEqual(json.loads(selected["content"])["rows"], rows[:5])
        self.assertEqual((selected["sourceBlockId"], selected["source_file"], selected["page"]),
                         (block["id"], "plan.pdf", 2))
        self.assertEqual(contexts["grading"], [])
        self.assertEqual(preserve_continuations(result, [block]), result)

    def test_complete_grading_table_is_not_added_twice(self):
        from app.ai.evidence import preserve_continuations
        block = {"id": "table", "type": "table", "source_file": "plan.pdf", "page": 1,
                 "content": json.dumps({"rows": [["Date", "Assessment"], ["3-Mar", "ALEKS 1"]]})}
        contexts = {"identity": [], "calendar": [], "grading": [block]}
        self.assertEqual(preserve_continuations(contexts, [block])["grading"], [block])

    def test_assessment_table_header_preserves_bare_numbered_rows(self):
        from app.ai.evidence import preserve_continuations
        rows = [['Group A'], ['Toets/Test', 'Datum/Date', 'Leereenhede/Study units'],
                ['1', '17/02', '1.1–1.4'], ['2', '24/02', '1.1–1.9'],
                ['3', '10/03', '2.1–2.6'], ['4', '17/03', '2.6–3.2']]
        block = {'id': 'table', 'type': 'table', 'source_file': 'plan.pdf', 'page': 1,
                 'content': json.dumps({'rows': rows}, ensure_ascii=False)}
        result = preserve_continuations({'identity': [], 'grading': [], 'calendar': [block]}, [block])
        self.assertEqual(json.loads(result['grading'][0]['content'])['rows'], rows)
        self.assertEqual(result['grading'][0]['sourceRowIndices'], list(range(len(rows))))

    def test_general_exam_period_alone_is_not_a_specific_assessment(self):
        from app.ai.evidence import preserve_continuations
        block = {"id": "table", "type": "table", "source_file": "plan.pdf", "page": 1,
                 "content": json.dumps({"rows": [["Date", "Topic"], ["28-Oct", "Examination starts"]]})}
        self.assertEqual(preserve_continuations({"identity": [], "calendar": [block], "grading": []}, [block])["grading"], [])

    def test_grading_sentence_continuation_keeps_source_order_without_crossing_pages(self):
        from app.ai.evidence import preserve_continuations
        def block(identifier, text, page=1):
            return {"id": identifier, "content": text, "type": "paragraph", "source_file": "guide.pdf", "page": page}
        start = block("s0-b0-part0", "Each of the following marks will be 50%")
        continuation = block("s0-b1-part0", "of the final mark:")
        end = block("s0-b2-part0", "Participation mark and examination mark.")
        contexts = {"identity": [], "calendar": [], "grading": [end, start]}
        result = preserve_continuations(contexts, [start, continuation, end])
        self.assertEqual([b["id"] for b in result["grading"]], [start["id"], continuation["id"], end["id"]])
        other_page = {**continuation, "page": 2}
        self.assertNotIn(other_page, preserve_continuations(contexts, [start, other_page, end])["grading"])
        self.assertEqual(contexts["grading"], [end, start])
    async def test_review_and_budget_failures_are_not_masked_as_schema_retries(self):
        block = {"id": "a", "content": "Synthetic evidence", "source_file": "fixture", "page": 1}
        for code in ("provider_review_required", "request_budget_exceeded"):
            with self.subTest(code=code), patch("app.ai.evidence.complete", side_effect=DocumentError("Unavailable", 503, code)) as request:
                with self.assertRaises(DocumentError) as caught:
                    await extract_batch(None, [block])
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(request.call_count, 1)

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
        chunks = []
        for block in result:
            section_rows = json.loads(block["content"])["rows"]
            self.assertEqual(section_rows[0], rows[0])
            chunks.append(section_rows)
            tail = section_rows[1:]
            if found and tail and tail[0] == found[-1]:
                tail = tail[1:]  # One source row provides boundary context.
            found.extend(tail)
            self.assertLessEqual(len(block["content"].encode()), 600)
        self.assertEqual(found, rows[1:])
        for previous, following in zip(rows[1:], rows[2:]):
            self.assertTrue(any(previous in chunk and following in chunk for chunk in chunks),
                            "A timetable date row must stay with its continuation at a split")

    async def test_course_year_heading_reaches_grading_and_calendar(self):
        from app.utils.documents import Blocks
        blocks = Blocks("schedule.pdf")
        blocks.add("ABC123 2026", 1, "heading")
        blocks.add("\n".join(f"Test {i} on a stated course date." for i in range(200)), 1, "paragraph")
        async def classify(client, batch):
            return [{"purpose": "identity" if block["type"] == "heading" else "grading",
                     **{key: block[key] for key in ("id", "content", "source_file", "page")}}
                    for block in batch]
        with patch("app.ai.evidence.extract_batch", side_effect=classify):
            contexts, _ = await collect_evidence(None, [{"blocks": blocks.items}])
        for purpose in ("identity", "grading", "calendar"):
            heading = [block for block in contexts[purpose] if block["content"] == "ABC123 2026"]
            self.assertEqual(len(heading), 1, purpose)
            self.assertEqual((heading[0]["source_file"], heading[0]["page"]), ("schedule.pdf", 1))

    async def test_table_size_retry_preserves_continuation_context(self):
        rows = [["Date", "Assessment"]] + [[str(i), f"Test {i}"] for i in range(8)]
        block = {"id": "table", "type": "table", "content": json.dumps({"rows": rows}),
                 "source_file": "schedule.pdf", "page": 1}
        calls = []
        async def answer(client, purpose, messages, schema, output_tokens):
            batch = json.loads(messages[1]["content"])
            calls.append(batch)
            if len(calls) == 1:
                return response({}, finish="length")
            return response({"decisions": [{"blockId": item["id"], "purposes": ["grading"]} for item in batch]})
        with patch("app.ai.evidence.complete", side_effect=answer):
            facts = await extract_batch(None, [block])
        chunks = [json.loads(item["content"])["rows"] for item in facts]
        self.assertEqual(len(calls), 3)
        for previous, following in zip(rows[1:], rows[2:]):
            self.assertTrue(any(any(a == previous and b == following for a, b in zip(chunk[1:], chunk[2:])) for chunk in chunks))

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
    def setUp(self):
        review = patch.dict("os.environ", {**{f"AI_GROQ_{key}_VERIFIED": "true" for key in ("NO_TRAINING", "RETENTION", "INTERNATIONAL_TRANSFER", "MINOR_SAFEGUARDS")}, "AI_GROQ_REVIEW_REFERENCE": "synthetic-test-review"})
        review.start()
        self.addCleanup(review.stop)

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
