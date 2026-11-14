"""Validate explicit, uniquely associated source ranges without inventing dates."""
import re
from datetime import date
from .source_calendar import MONTHS
from ..utils.documents import DocumentError

MONTH_INDEX = {name: number for number, names in enumerate(MONTHS, 1) for name in names}
RANGE = re.compile(r"\b(?:semester[ -]test|semestertoets)\s*\(\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*(" +
                   "|".join(sorted(MONTH_INDEX, key=len, reverse=True)) + r")\.?\s+(\d{4})\b", re.I)


def explicit_semester_range(part, blocks):
    tests = [assessment for assessment in part.assessments if assessment.type == "semester-test"]
    if len(tests) != 1:
        return None  # Do not guess which assessment an unnumbered source clause means.
    ranges = {}
    for block in blocks:
        for match in RANGE.finditer(block["content"]):
            first, last, month, year = match.groups()
            try:
                start = date(int(year), MONTH_INDEX[month.lower()], int(first)).isoformat()
                end = date(int(year), MONTH_INDEX[month.lower()], int(last)).isoformat()
            except ValueError:
                continue
            if start <= end:
                ranges.setdefault((start, end), block)
    if len(ranges) > 1:
        raise DocumentError("More than one explicit semester-test range is stated. Confirm its course/group association before importing; no range was selected.", 422, "ambiguous_assessment_range")
    if not ranges:
        return None
    (start, end), block = next(iter(ranges.items()))
    return tests[0], start, end, block


def link_source_ranges(part, blocks):
    source = explicit_semester_range(part, blocks)
    if source is None:
        return part
    test, start, end, block = source
    if ((test.date and test.date != start) or (test.dateEnd and test.dateEnd != end)
            or (test.date and test.dateEnd)):
        return part  # Preserve actual disagreement for validation; no silent winner.
    reference = block.get("source_file", "supplied source")
    if block.get("page", 0) > 0:
        reference += f", PDF page {block['page']}"
    note = f"Semester-test range {start} through {end} linked to its explicit source statement ({reference}); review before saving."
    linked = test.model_copy(update={"date": test.date or start, "dateEnd": test.dateEnd or end})
    return part.model_copy(update={
        "assessments": [linked if assessment.id == test.id else assessment for assessment in part.assessments],
        "warnings": list(dict.fromkeys([*part.warnings, note])),
        "dataNote": "\n\n".join(filter(None, [part.dataNote, note]))})


def source_range_errors(part, blocks):
    source = explicit_semester_range(part, blocks)
    if source is not None:
        test, start, end, _ = source
        if test.date != start or test.dateEnd != end:
            return [f"The explicit source semester-test range is {start} through {end}; preserve both date and dateEnd. Do not collapse the range to its first day."]
    return []
