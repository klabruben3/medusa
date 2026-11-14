"""Validate explicit, uniquely associated source ranges without inventing dates."""
import re
from datetime import date
from .source_calendar import MONTHS
from ..utils.documents import DocumentError

MONTH_INDEX = {name: number for number, names in enumerate(MONTHS, 1) for name in names}
RANGE = re.compile(r"\b(?:semester[ -]test|semestertoets)\s*\(\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*(" +
                   "|".join(sorted(MONTH_INDEX, key=len, reverse=True)) + r")\.?\s+(\d{4})\b", re.I)


def source_range_errors(part, blocks):
    tests = [assessment for assessment in part.assessments if assessment.type == "semester-test"]
    if len(tests) != 1:
        return []  # Do not guess which assessment an unnumbered source clause means.
    ranges = set()
    for block in blocks:
        for match in RANGE.finditer(block["content"]):
            first, last, month, year = match.groups()
            try:
                start = date(int(year), MONTH_INDEX[month.lower()], int(first)).isoformat()
                end = date(int(year), MONTH_INDEX[month.lower()], int(last)).isoformat()
            except ValueError:
                continue
            if start <= end:
                ranges.add((start, end))
    if len(ranges) > 1:
        raise DocumentError("More than one explicit semester-test range is stated. Confirm its course/group association before importing; no range was selected.", 422, "ambiguous_assessment_range")
    if ranges:
        start, end = next(iter(ranges))
        if tests[0].date != start or tests[0].dateEnd != end:
            return [f"The explicit source semester-test range is {start} through {end}; preserve both date and dateEnd. Do not collapse the range to its first day."]
    return []
