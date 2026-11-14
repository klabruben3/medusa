import unittest
from unittest.mock import AsyncMock, patch
from app.ai.generate_module import run_grading, run_worker
from app.ai.partials import PARTIALS, GRADING_PARTIALS
from app.ai.provider import strict_schema
from app.utils.documents import DocumentError
from test_pipeline import sample
from test_evidence import response


class GradingBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_conflict_is_verified_once_and_real_conflicts_still_block(self):
        conflict = {"code": "ABC123", "name": "Example", "conflicts": ["Synthetic opposing source facts"]}
        resolved = {**conflict, "conflicts": []}
        for second, should_fail in ((resolved, False), (conflict, True)):
            with patch("app.ai.generate_module.complete", new=AsyncMock(side_effect=[response(conflict), response(second)])) as request:
                if should_fail:
                    with self.assertRaises(DocumentError) as error:
                        await run_worker(None, "identity", [])
                    self.assertEqual(error.exception.code, "conflicting_sources")
                    self.assertNotIn(conflict["conflicts"][0], str(error.exception))
                else:
                    self.assertEqual((await run_worker(None, "identity", [])).code, "ABC123")
                self.assertEqual(request.await_count, 2)
    async def test_budget_fallback_splits_fields_without_dropping_original_evidence(self):
        module = sample().model_dump()
        grading = PARTIALS["grading"].model_validate({key: module[key] for key in PARTIALS["grading"].model_fields if key in module})
        values = grading.model_dump()
        assessments = GRADING_PARTIALS["assessments"].model_validate({key: values[key] for key in GRADING_PARTIALS["assessments"].model_fields})
        rules = GRADING_PARTIALS["rules"].model_validate({key: values[key] for key in GRADING_PARTIALS["rules"].model_fields})
        blocks = [{"content": "Synthetic original evidence"}]
        with patch("app.ai.generate_module.run_worker", new=AsyncMock(side_effect=[DocumentError("Budget", 413, "request_budget_exceeded"), assessments, rules])) as worker:
            result = await run_grading(None, blocks, {"code": "ABC123", "name": "Example"})
        self.assertEqual(result.model_dump(), grading.model_dump())
        self.assertEqual(worker.await_count, 3)
        self.assertTrue(all(call.args[2] is blocks for call in worker.await_args_list))
        self.assertEqual(worker.await_args_list[-1].args[3]["assessmentReferences"][0]["id"], module["assessments"][0]["id"])
        self.assertNotIn("weight", worker.await_args_list[-1].args[3]["assessmentReferences"][0])

    async def test_unrelated_failures_do_not_trigger_a_second_extraction(self):
        with patch("app.ai.generate_module.run_worker", new=AsyncMock(side_effect=DocumentError("Review", 503, "provider_review_required"))) as worker:
            with self.assertRaises(DocumentError):
                await run_grading(None, [], {})
        worker.assert_awaited_once()

    def test_strict_schema_requires_nullable_fields_without_mutating_the_contract(self):
        original = PARTIALS["grading"].model_json_schema()
        strict = strict_schema(original)
        self.assertEqual(set(strict["required"]), set(strict["properties"]))
        self.assertIn({"type": "null"}, strict["properties"]["passRequirements"]["anyOf"])
        self.assertFalse(strict["additionalProperties"])
        self.assertIn("title", original)
        for definition in strict.get("$defs", {}).values():
            if definition.get("type") == "object":
                self.assertEqual(set(definition["required"]), set(definition["properties"]))
                self.assertFalse(definition["additionalProperties"])

    def test_strict_schema_preserves_properties_named_like_schema_annotations(self):
        original = {"type": "object", "title": "Example", "properties": {
            "title": {"type": "string", "title": "Label"},
            "default": {"type": "string", "default": "example"}}}
        result = strict_schema(original)
        self.assertEqual(set(result["properties"]), {"title", "default"})
        self.assertNotIn("title", result["properties"]["title"])
        self.assertNotIn("default", result["properties"]["default"])
