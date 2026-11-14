import json
import unittest
from app.ai.fact_ledger import ObservationBatch, review_batch, parse_response
from app.ai.table_context import enrich_sections
from app.ai.ledger_assembly import assemble_ledger
from test_ledger_assembly import fixture


def review(kind, key, values, text, row=None):
    block = {'id': 'a', 'source_file': 'ABC123_2026.pdf', 'page': 1,
             'type': 'table' if row is not None else 'paragraph', 'content': text}
    blocks = enrich_sections([block])
    raw = ObservationBatch.model_validate({'observations': [{'kind': kind, 'key': key,
        'values': [{'field': field, 'value': value} for field, value in values.items()],
        'evidence': [{'block': 'a', 'row': row}]}]})
    return review_batch(raw, blocks)


class GroundingTests(unittest.TestCase):
    def test_duplicate_json_keys_cannot_silently_discard_a_date(self):
        raw = '{"observations": [], "observations": []}'
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            parse_response(raw)
        self.assertEqual(parse_response('{"observations": []}').observations, [])

    def test_absence_of_exam_information_is_unknown_not_no_exam(self):
        for text in ('Weekly tests on 17 February.', 'No exam date is available.', 'Examination starts 1 June.'):
            for value in (True, False):
                result = review('module', 'module', {'hasExam': value}, text)
                self.assertEqual(len(result.rejected_claims), 1)
        self.assertEqual(len(review('module', 'module', {'hasExam': False}, 'No exam.').observations), 1)
        self.assertEqual(len(review('module', 'module', {'hasExam': True}, 'Exam contributes 50%.').observations), 1)

    def test_teaching_rows_do_not_establish_semester_boundaries(self):
        for field in ('semesterStart', 'semesterEnd'):
            self.assertEqual(len(review('module', 'module', {field: '2026-02-17'}, 'Teaching: 17 February.').rejected_claims), 1)
        self.assertEqual(len(review('module', 'module', {'semesterStart': '2026-02-17'}, 'Semester starts 17 February.').observations), 1)
        self.assertEqual(len(review('module', 'module', {'semesterEnd': '2026-05-22'}, 'Semester ends after 22 May.').rejected_claims), 1)
        text = 'Semester starts 17 February and semester ends 22 May.'
        self.assertEqual(len(review('module', 'module', {'semesterStart': '2026-05-22'}, text).rejected_claims), 1)

    def test_unstated_date_and_general_exam_period_are_rejected(self):
        self.assertEqual(len(review('assessment', 'test-1', {'date': '2026-03-14'}, 'Test 1: 10 March.').rejected_claims), 1)
        self.assertEqual(len(review('module', 'module', {'examDate': '2026-06-01'}, 'Examination starts 1 June.').rejected_claims), 1)
        self.assertEqual(len(review('assessment', 'test-1', {'date': '2026-03-10'}, 'Test 1: 10 March.').observations), 1)
        self.assertEqual(len(review('assessment', 'test-2', {'date': '2026-03-10'}, 'Test 1: 10 March.').rejected_claims), 1)

    def test_merged_table_dates_and_tutorial_window_keep_their_roles(self):
        text = json.dumps({'rows': [['Week', 'Day', 'Date', 'Period', 'Content'],
            ['1', 'Tues', '17-Feb', '14:30-16:00', 'Lecture'],
            ['', '', '', '16:15-17:45', 'TUT + TEST 1']]})
        result = review('assessment', 'weekly-test-1', {'date': '2026-02-17', 'time': '14:30'}, text, 2)
        self.assertEqual([v.field for v in result.observations[0].values], ['date'])
        self.assertEqual(len(result.rejected_claims), 1)
        self.assertEqual(len(review('assessment', 'test-1', {'time': '16:15'}, text, 2).rejected_claims), 1)
        self.assertEqual(len(review('assessment', 'test-2', {'date': '2026-02-17'}, text, 2).rejected_claims), 1)
        slot = {'date': '2026-02-17', 'time': '16:15', 'label': 'Group A tutorial session'}
        self.assertEqual(len(review('assessment', 'test-1', {'slots': [slot]}, text, 2).observations), 1)
        slot['label'] = 'Exact test start'
        self.assertEqual(len(review('assessment', 'test-1', {'slots': [slot]}, text, 2).rejected_claims), 1)

    def test_quarantine_retains_valid_fields_without_accepting_a_complete_template(self):
        reviewed = review('assessment', 'test-1', {'name': 'Test 1', 'maxScore': 99}, 'Test 1: 40 marks.')
        self.assertEqual([v.field for v in reviewed.observations[0].values], ['name'])
        ledger, blocks = fixture()
        ledger[0].rejected_claims = reviewed.rejected_claims
        result = assemble_ledger(ledger, blocks)
        self.assertIsNone(result['result'])
        self.assertTrue(any(issue['code'] == 'quarantined_claim' for issue in result['issues']))
