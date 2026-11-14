import unittest
from app.ai.source_ranges import source_range_errors
from app.utils.documents import DocumentError
from test_grading_links import grading

class SourceRangeTests(unittest.TestCase):
    def part(self,start="2027-03-02",end="2027-03-05"):
        part=grading((100,))
        part.assessments[0].type="semester-test"
        part.assessments[0].date=start
        part.assessments[0].dateEnd=end
        return part

    def test_explicit_range_is_preserved_and_bilingual_copies_deduplicate(self):
        blocks=[{"content":"Semester test (2–5 March 2027, 50 marks). Semestertoets (2-5 Maart 2027, 50 punte)."}]
        self.assertEqual(source_range_errors(self.part(),blocks),[])
        part=self.part(end=None)
        self.assertTrue(source_range_errors(part,blocks))
        self.assertIsNone(part.assessments[0].dateEnd)

    def test_opposing_explicit_ranges_fail_without_choosing(self):
        with self.assertRaises(DocumentError) as error:
            source_range_errors(self.part(),[{"content":"Semester test (2-5 March 2027). Semester test (3-6 March 2027)."}])
        self.assertEqual(error.exception.code,"ambiguous_assessment_range")

    def test_generic_week_missing_year_and_multiple_assessments_are_not_guessed(self):
        for text in ("Assessment week: 2-5 March 2027", "Semester test (2-5 March)"):
            self.assertEqual(source_range_errors(self.part(end=None),[{"content":text}]),[])
        part=self.part(end=None)
        part.assessments.append(part.assessments[0].model_copy(update={"id":"other"}))
        self.assertEqual(source_range_errors(part,[{"content":"Semester test (2-5 March 2027)"}]),[])
