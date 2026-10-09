import unittest
from unittest.mock import patch, AsyncMock
from app.ai.partials import PARTIALS
from app.ai.generate_module import link_individual_weights, merge_parts
from app.ai.evidence import collect_evidence
from app.utils.validation import validate_module, safe_validation_issues
from app.utils.documents import DocumentError
from test_pipeline import sample


def grading(weights=(30, 30, 40)):
    return PARTIALS['grading'](hasExam=True,
        assessments=[dict(id=f'abc123-test-{i}', name=f'Test {i}', type='class-test', weight=weight, maxScore=40) for i, weight in enumerate(weights)],
        participationFormula=dict(components=[], minimumToPass=40),
        dataNote='A conditional supplementary bonus is available; review source conditions.')


class GradingLinkTests(unittest.TestCase):
    def test_complete_plan_is_linked_without_changing_source_weights(self):
        part = link_individual_weights(grading())
        self.assertEqual([c.weight for c in part.participationFormula.components], [30, 30, 40])
        self.assertEqual([c.componentId for c in part.participationFormula.components], [a.id for a in part.assessments])
        self.assertEqual(part.participationFormula.minimumToPass, 40)
        self.assertIsNone(part.finalMarkFormula)
        module = sample().model_copy(update={'assessments': part.assessments, 'participationFormula': part.participationFormula})
        self.assertEqual(validate_module(module), [])
        self.assertIn('conditional', part.dataNote)

    def test_incomplete_fractional_unknown_or_existing_plans_are_not_rewritten(self):
        for weights in [(30, 30), (.3, .3, .4), (-1, 100), (0, 0)]:
            with self.subTest(weights=weights):
                part = grading(weights)
                self.assertIs(link_individual_weights(part), part)
        part = grading()
        part.participationFormula.components = sample().participationFormula.components
        self.assertIs(link_individual_weights(part), part)

    def test_exam_and_unweighted_supplement_are_not_participation_components(self):
        part = grading((30, 30, 40, 0, 100))
        part.assessments[-1].type = 'exam'
        linked = link_individual_weights(part)
        self.assertEqual(len(linked.participationFormula.components), 3)
        part = grading((50, 50))
        part.assessments[-1].type = 'exam'
        self.assertIs(link_individual_weights(part), part)

    def test_wholly_unknown_placeholder_can_use_explicit_individual_plan(self):
        from app.types.schema import FormulaComponent
        part = grading()
        part.participationFormula.components = [FormulaComponent(componentId='abc123-participation', weight=-1)]
        self.assertEqual([c.weight for c in link_individual_weights(part).participationFormula.components], [30, 30, 40])
        part.participationFormula.components[0].dropLowest = 1
        self.assertIs(link_individual_weights(part), part)

    def test_null_diagnostics_do_not_create_schema_retries(self):
        part = grading().model_dump()
        part.update(warnings=None, conflicts=None)
        parsed = PARTIALS['grading'].model_validate(part)
        self.assertEqual(parsed.warnings, [])
        self.assertEqual(parsed.conflicts, [])
        part['conflicts'] = ['Conflicting percentages']
        self.assertEqual(PARTIALS['grading'].model_validate(part).conflicts, part['conflicts'])

    def test_explicit_admission_threshold_can_fill_only_unknown_duplicate(self):
        from app.types.schema import PassRequirements
        part = grading()
        part.passRequirements = PassRequirements(participationMin=40)
        part.participationFormula.minimumToPass = -1
        self.assertEqual(link_individual_weights(part).participationFormula.minimumToPass, 40)
        part.participationFormula.minimumToPass = 45
        self.assertEqual(link_individual_weights(part).participationFormula.minimumToPass, 45)
        part.participationFormula.minimumToPass = -1
        part.passRequirements = None
        self.assertEqual(link_individual_weights(part).participationFormula.minimumToPass, -1)

    def test_invalid_marks_still_fail_and_public_issues_do_not_expose_ids(self):
        module = sample()
        module.assessments[0].maxScore = 0
        self.assertTrue(validate_module(module))
        issues = safe_validation_issues(['Formula PRIVATE-ID has no matching assessment/category.'])
        self.assertNotIn('PRIVATE-ID', str(issues))
        self.assertEqual(issues[0]['code'], 'formula_links')

    def test_merge_reports_safe_issues_and_preserves_conditional_notes(self):
        parts = {'identity': dict(code='ABC123', name='Example'), 'grading': grading(), 'calendar': dict(semesterStart='', semesterEnd='')}
        result = merge_parts(parts)
        self.assertEqual(validate_module(result.module), [])
        self.assertIn('conditional', result.module.dataNote)
        parts['grading'] = grading((30, 30))
        with self.assertRaises(DocumentError) as caught:
            merge_parts(parts)
        self.assertEqual(caught.exception.code, 'invalid_grading')
        self.assertTrue(caught.exception.issues)


class IdentityRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_module_reference_in_grading_is_retained_for_identity(self):
        blocks = [dict(id='current', source_file='guide.pdf', page=1, content='Exam admission for ABC123 requires 40%.'),
                  dict(id='other', source_file='guide.pdf', page=1, content='Prerequisite OLD111. ' + 'Detailed source. ' * 220)]
        facts = [{**b, 'purpose': 'grading'} for b in blocks]
        with patch('app.ai.evidence.sections', return_value=blocks), patch('app.ai.evidence.extract_batch', new=AsyncMock(return_value=facts)):
            contexts, _ = await collect_evidence(None, [])
        self.assertEqual([b['id'] for b in contexts['identity']].count('current'), 1)
        self.assertEqual(contexts['identity'][0]['content'], blocks[0]['content'])
