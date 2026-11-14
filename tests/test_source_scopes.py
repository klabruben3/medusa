import json
import unittest
from app.ai.partials import PARTIALS
from app.ai.source_scopes import review_source_scopes
from test_pipeline import sample


class SourceScopeTests(unittest.TestCase):
    def grading(self):
        data = sample().model_dump()
        data['assessments'][0].update(name='Class test 2', type='class-test', studyUnits='4')
        return PARTIALS['grading'].model_validate({k: data[k] for k in PARTIALS['grading'].model_fields if k in data})

    def block(self, identifier, text, file='info.pdf'):
        return {'id': identifier, 'source_file': file, 'page': 2, 'content': text}

    def test_differing_coverage_is_unset_with_both_original_references(self):
        part = self.grading()
        part.dataNote = 'Existing course conditions remain.'
        blocks = [self.block('a', 'Class test 2 (12 Oct 2026, study unit 4, 40 marks)'),
                  self.block('b', json.dumps({'rows': [['12-Oct', 'Class test 2 (4.2.2–5.2)']]}), 'plan.pdf')]
        result = review_source_scopes(part, blocks)
        self.assertIsNone(result.assessments[0].studyUnits)
        self.assertEqual(part.assessments[0].studyUnits, '4')
        self.assertEqual(result.participationFormula, part.participationFormula)
        for value in ('4.2.2–5.2', 'info.pdf', 'plan.pdf', 'block a', 'block b'):
            self.assertIn(value, result.dataNote)
        self.assertEqual(review_source_scopes(result, blocks), result)

    def test_equivalent_descriptions_and_unlinked_assessments_are_unchanged(self):
        part = self.grading()
        blocks = [self.block('a', 'Class test 2 (study units 4–5)'),
                  self.block('b', 'Class test 2: 4-5', 'plan.pdf')]
        self.assertEqual(review_source_scopes(part, blocks), part)
        blocks[1]['content'] = 'Class test 3: 6-7'
        self.assertEqual(review_source_scopes(part, blocks), part)

    def test_following_semester_test_does_not_supply_class_test_coverage(self):
        part = self.grading()
        blocks = [self.block('a', 'Class test 2 (40 marks), semester test (study units 1-4)'),
                  self.block('b', 'Class test 2 (4.2.2-5.2)', 'plan.pdf')]
        self.assertEqual(review_source_scopes(part, blocks), part)
