import json
import unittest
from app.ai.fact_ledger import FactBatch
from app.ai.ledger_assembly import assemble_ledger
from app.utils.documents import DocumentError


def fixture(missing_maximum=False, conflict=False):
    observations = []
    text = 'ABC123 Example. No exam. Test 1 maximum 40. Test 1 contributes 100%. Final pass 50%. Another source states 60%.'
    def observation(kind, key, values, quote=text):
        observations.append({'kind': kind, 'key': key,
            'values': [{'field': field, 'value': value} for field, value in values.items()],
            'evidence': [{'block': 'a', 'quote': quote}]})
    observation('module', 'module', {'code': 'ABC123', 'name': 'Example', 'hasExam': False})
    values = {'name': 'Test 1', 'type': 'class-test', 'category': 'tests'}
    if not missing_maximum:
        values['maxScore'] = 40
    observation('assessment', 'class-test-1', values)
    observation('formula', 'category:tests', {'weight': 100})
    observation('pass', 'module', {'finalMin': 50})
    if conflict:
        observation('pass', 'module', {'finalMin': 60}, quote='Another source states 60%.')
    block = {'id': 'a', 'content': text, 'source_file': 'synthetic.pdf', 'page': 1}
    return [FactBatch.model_validate({'covered': ['a'], 'observations': observations})], [block]


class AssemblyTests(unittest.TestCase):
    def test_valid_ledger_preserves_existing_unsaved_module_contract(self):
        ledger, blocks = fixture()
        value = assemble_ledger(ledger, blocks)
        self.assertEqual(value['issues'], [])
        self.assertEqual(value['status'], 'draft_requires_source_review')
        module = value['result']['module']
        self.assertEqual(module['id'], '')
        self.assertEqual(module['moduleId'], 'abc123')
        self.assertEqual(module['assessments'][0]['maxScore'], 40)
        self.assertEqual(module['participationFormula']['components'][0]['weight'], 100)
        self.assertEqual(module['participationFormula']['minimumToPass'], 50)
        self.assertNotIn('score', module['assessments'][0])

    def test_missing_maximum_retains_proposal_and_never_invents_100(self):
        ledger, blocks = fixture(missing_maximum=True)
        value = assemble_ledger(ledger, blocks)
        self.assertEqual(value['status'], 'needs_review')
        self.assertIsNone(value['result'])
        self.assertNotIn('maxScore', value['proposal']['grading']['assessments'][0])
        self.assertTrue(any(i['code'] == 'missing_assessment_field' for i in value['issues']))

    def test_conflicting_thresholds_retain_both_sources_and_no_accepted_result(self):
        ledger, blocks = fixture(conflict=True)
        value = assemble_ledger(ledger, blocks)
        self.assertIsNone(value['result'])
        issue = next(i for i in value['issues'] if i['code'] == 'differing_source_values')
        self.assertEqual({candidate['value'] for candidate in issue['candidates']}, {50, 60})
        self.assertNotIn('finalMin', value['proposal']['grading']['passRequirements'] or {})

    def test_incomplete_or_duplicate_coverage_is_not_accepted(self):
        ledger, blocks = fixture()
        with self.assertRaises(DocumentError):
            assemble_ledger(ledger + ledger, blocks)
        with self.assertRaises(DocumentError):
            assemble_ledger(ledger, blocks + [{'id': 'b', 'content': 'Another source section'}])
