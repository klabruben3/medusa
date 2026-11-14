import unittest
from app.ai.source_rules import link_source_rules
from app.types.schema import FinalMarkFormula
from app.utils.documents import DocumentError
from test_grading_links import grading


class SourceRulesTests(unittest.TestCase):
    def blocks(self):
        return [{"source_file": "guide.pdf", "page": 6, "content": text} for text in [
            "Requirements for successful completion: final module mark at least 50%.",
            "Each of the following marks will be 50%", "of the final mark:",
            "Participation mark (minimum 40%).", "Examination mark (minimum 40%).",
            "Participation as a mark out of five will be used to supplement marks between 35 and 39.5.",
            "It will be used only once."]]

    def test_explicit_equal_split_and_conditional_clause_are_linked_without_mutating_input(self):
        original = grading()
        result = link_source_rules(original, self.blocks())
        self.assertEqual(result.finalMarkFormula, FinalMarkFormula(participationWeight=50, examWeight=50))
        self.assertIn("35 and 39.5", result.dataNote)
        self.assertIn("only once", result.dataNote)
        self.assertIsNone(original.finalMarkFormula)
        self.assertEqual(result.assessments, original.assessments)
        self.assertEqual(link_source_rules(result, self.blocks()).model_dump(), result.model_dump())

    def test_existing_disagreement_is_not_overwritten(self):
        original = grading().model_copy(update={"finalMarkFormula": FinalMarkFormula(participationWeight=40, examWeight=60)})
        with self.assertRaises(DocumentError) as error:
            link_source_rules(original, self.blocks())
        self.assertEqual(error.exception.code, "invalid_grading")
        self.assertEqual(original.finalMarkFormula.examWeight, 60)

    def test_percentage_alone_and_no_exam_do_not_create_a_default_split(self):
        part = grading()
        self.assertIsNone(link_source_rules(part, [{"source_file": "x", "page": 1, "content": "50% of skills are introductory"}]).finalMarkFormula)
        self.assertIsNone(link_source_rules(part.model_copy(update={"hasExam": False}), self.blocks()).finalMarkFormula)
