"""Require an explicit source anchor for a semester end, never an exam start."""
import re
from datetime import date

MONTHS = (
    ("january", "januarie", "jan"), ("february", "februarie", "feb"),
    ("march", "maart", "mar"), ("april", "apr"), ("may", "mei"),
    ("june", "junie", "jun"), ("july", "julie", "jul"),
    ("august", "augustus", "aug"), ("september", "sep", "sept"),
    ("october", "oktober", "oct", "okt"), ("november", "nov"),
    ("december", "desember", "dec", "des"),
)
END = re.compile(r"\b(?:semester\s*(?:(?:1|2|one|two|first|second)\s*)?(?:ends?|ending|concludes?|eindig)|"
                 r"end\s*(?:date\s*)?of\s+(?:the\s+)?(?:(?:first|second)\s+)?semester|semestereinde)\b", re.I)


def ground_semester_end(part, blocks):
    if not part.semesterEnd:
        return part
    evidence = part.semesterEndSource
    block = next((b for b in blocks if evidence and b["id"] == evidence.blockId), None)
    quote = " ".join(evidence.quote.split()) if evidence else ""
    source = " ".join(block["content"].split()) if block else ""
    supported = False
    try:
        target = date.fromisoformat(part.semesterEnd)
        names = "|".join(MONTHS[target.month - 1])
        day, month = target.day, target.month
        date_pattern = re.compile(rf"(?:\b{re.escape(target.isoformat())}\b|\b0?{day}[./-]0?{month}(?:[./-]{target.year})?(?![./-]\d)\b|\b0?{day}\s+(?:{names})\b(?:\s+{target.year})?(?!\s+\d{{4}})|\b(?:{names})\s+0?{day}\b(?:,?\s+{target.year})?(?!,?\s+\d{{4}}))", re.I)
        supported = (bool(quote) and len(quote) <= 500 and quote in source
                     and any(re.match(r"\s*(?:[:–—-]\s*)?(?:(?:on|op|is)\s+)?" + date_pattern.pattern,
                                      quote[m.end():], re.I) for m in END.finditer(quote)))
    except (ValueError, TypeError):
        pass
    if supported:
        return part
    return part.model_copy(update={"semesterEnd": "", "warnings": [*part.warnings,
        "Semester end lacks a verified explicit source statement and was left blank. Exam-period starts, last assessments and teaching-week ranges do not establish it; enter the confirmed date before saving."]})
