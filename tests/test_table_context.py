import json
import unittest
from app.ai.table_context import analyze_rows, enrich_sections, parsed_date, schedule_candidates
from app.ai.evidence import sections
from app.utils.documents import Blocks


def timetable():
    return [['ABC123 2026 (Group A)', '', '', '', ''],
        ['Week', 'Day', 'Date', 'Period', 'Content'],
        ['1', 'Tues', '17-Feb', '14:30-16:00', 'Lecture'],
        ['', '', '', '16:15-17:45', 'TUT + TEST 1'],
        ['2', 'Tues', '24-Feb', '14:30-16:00', 'Lecture'],
        ['', '', '', '16:15-17:45', 'TUT + TEST 2']]


class TableContextTests(unittest.TestCase):
    def test_merged_date_uses_previous_date_but_current_own_period(self):
        result = analyze_rows(timetable(), 'ABC123 2026.pdf')['rows'][3]
        self.assertEqual(result['date'], '2026-02-17')
        self.assertEqual(result['period_start'], '16:15')
        self.assertEqual(result['period_end'], '17:45')
        self.assertEqual(result['date_source_rows'], [2])
        self.assertEqual(result['event_keys'], ['test-1'])
        self.assertTrue(result['session_only'])

    def test_changed_weekday_is_ambiguous_not_a_silent_previous_date_copy(self):
        rows = timetable()[:3] + [['', 'Wed', '', '09:15-10:45', 'TUT + TEST 4'],
                                  ['', '', '18-Feb', '11:00-12:30', 'Lecture']]
        result = analyze_rows(rows, 'ABC123 2026.pdf')['rows'][3]
        self.assertIsNone(result['date'])
        self.assertEqual(result['date_state'], 'ambiguous')
        self.assertEqual(result['possible_dates'], ['2026-02-18'])

    def test_wik_and_aleks_shared_row_is_not_invented_test_three(self):
        rows = timetable()
        rows[3][-1] = 'WIK/MIC TEST & ALEKS 1'
        self.assertEqual(analyze_rows(rows, 'ABC123 2026.pdf')['rows'][3]['event_keys'], ['aleks-1', 'mic-1'])

    def test_simple_date_table_compacts_only_when_logical_column_counts_match(self):
        rows = [['', 'Toets/Test', '', 'Datum/Date', '', 'Study units'],
                ['1', '', '', '17/02', '', '1–2'], ['2', '', '', '24/02', '', '2–3']]
        result = analyze_rows(rows, 'ABC123 2026.pdf')
        self.assertTrue(result['compacted'])
        self.assertEqual(result['rows'][1]['date'], '2026-02-17')
        self.assertEqual(result['rows'][2]['event_keys'], ['test-2'])
        rows[2][3] = ''
        self.assertFalse(analyze_rows(rows, 'ABC123 2026.pdf')['compacted'])

    def test_split_table_keeps_all_original_cells_and_cross_chunk_date_context(self):
        rows = timetable() + [['', 'Fri', '27-Feb', '09:15-10:45', 'Long source content ' * 4]]
        source = Blocks('ABC123 2026.pdf')
        source.add(json.dumps({'rows': rows}), 1, 'table')
        chunks = sections([{'blocks': source.items}], max_bytes=250)
        self.assertGreater(len(chunks), 1)
        result = enrich_sections(chunks, max_bytes=250)
        self.assertEqual([b['content'] for b in result], [b['content'] for b in chunks])
        slots = schedule_candidates(result)
        self.assertEqual(len(slots), 2)
        self.assertEqual([slot['date'] for slot in slots], ['2026-02-17', '2026-02-24'])
        self.assertTrue(all(slot['session_start'] == '16:15' for slot in slots))

    def test_source_year_is_required_and_numeric_order_is_not_guessed(self):
        self.assertIsNone(parsed_date('3-Mar'))
        self.assertIsNone(parsed_date('03/04', 2026))
        self.assertEqual(parsed_date('03/04', 2026, 'DMY'), '2026-04-03')
        self.assertIsNone(analyze_rows(timetable(), 'ABC123 2025.pdf')['rows'][3]['date'])

    def test_missing_date_in_an_assessment_list_is_not_automatically_inherited(self):
        rows = [['Test', 'Date'], ['Test 1', '17-Feb'], ['Test 2', '']]
        self.assertIsNone(analyze_rows(rows, 'ABC123 2026.pdf')['rows'][2]['date'])
