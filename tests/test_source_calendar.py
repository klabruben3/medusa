import unittest
from app.ai.partials import PARTIALS
from app.ai.source_calendar import ground_semester_end, ground_exam_dates

class SourceCalendarTests(unittest.TestCase):
    def exam(self, quote, end=None):
        part=PARTIALS["calendar"].model_validate({"semesterStart":"", "semesterEnd":"", "examDate":"2026-10-28", "examDateEnd":end,
            "examDateSource":{"blockId":"source-1","quote":quote}})
        return part,[{"id":"source-1","content":quote,"source_file":"ABC123 guide.pdf"}]

    def test_general_exam_period_is_not_a_module_exam_slot(self):
        for quote in ("Examination period starts 28 October 2026.", "ABC123 examination period: 28 October 2026."):
            part,blocks=self.exam(quote)
            self.assertIsNone(ground_exam_dates(part,blocks,"ABC123").examDate)

    def test_explicit_exam_slot_and_range_are_retained(self):
        part,blocks=self.exam("Exam date: 28 October 2026.")
        self.assertEqual(ground_exam_dates(part,blocks,"ABC123").examDate,"2026-10-28")
        part,blocks=self.exam("ABC123 examination: 28 October 2026 – 29 October 2026.", "2026-10-29")
        self.assertEqual(ground_exam_dates(part,blocks,"ABC123").examDateEnd,"2026-10-29")

    def test_wrong_module_or_unstated_range_end_is_not_retained(self):
        part,blocks=self.exam("Exam date: 28 October 2026.", "2026-10-29")
        self.assertIsNone(ground_exam_dates(part,blocks,"ABC123").examDateEnd)
        self.assertIsNone(ground_exam_dates(part,blocks,"OTHER456").examDate)

    def part(self, quote, day="2026-10-28", block="source-1"):
        return PARTIALS["calendar"].model_validate({"semesterStart":"", "semesterEnd":day,
            "semesterEndSource":{"blockId":block,"quote":quote}})

    def test_exam_start_and_unanchored_dates_are_left_blank_with_warning(self):
        for quote in ("Examination period starts 28 October 2026.", "Last class test: 28 October 2026.",
                      "Semester starts in July. Exams end 28 October 2026.",
                      "Semester ends not on 28 October 2026.", "Semester ends before 28 October 2026.",
                      "Semester ends 28 October 2025.", "Semester ends 28/10/2025."):
            part=self.part(quote)
            result=ground_semester_end(part,[{"id":"source-1","content":quote}])
            self.assertEqual(result.semesterEnd, "")
            self.assertTrue(result.warnings)
            self.assertEqual(part.semesterEnd,"2026-10-28")

    def test_explicit_matching_verbatim_end_is_preserved_in_supported_source_forms(self):
        for quote in ("Semester ends 28 October 2026.", "End of the second semester: 2026-10-28.",
                      "Semester eindig 28 Oktober 2026.", "Semestereinde: 28/10/2026."):
            self.assertEqual(ground_semester_end(self.part(quote),[{"id":"source-1","content":quote}]).semesterEnd,"2026-10-28")

    def test_wrong_source_fabricated_quote_and_wrong_day_are_not_accepted(self):
        quote="Semester ends 28 October 2026."
        for part, blocks in ((self.part(quote,block="other"),[{"id":"source-1","content":quote}]),
                             (self.part(quote),[{"id":"source-1","content":"Unrelated text"}]),
                             (self.part(quote,day="2026-10-29"),[{"id":"source-1","content":quote}])):
            self.assertEqual(ground_semester_end(part,blocks).semesterEnd,"")
