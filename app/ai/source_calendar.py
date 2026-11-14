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


def source_quote(evidence, blocks):
    block = next((b for b in blocks if evidence and b["id"] == evidence.blockId), None)
    quote = " ".join(evidence.quote.split()) if evidence else ""
    source = " ".join(block["content"].split()) if block else ""
    return (quote, block) if quote and len(quote) <= 500 and quote in source else ("", None)


def date_pattern(value):
    target = date.fromisoformat(value)
    names = "|".join(MONTHS[target.month - 1])
    day, month = target.day, target.month
    return rf"(?:\b{re.escape(target.isoformat())}\b|\b0?{day}[./-]0?{month}(?:[./-]{target.year})?(?![./-]\d)\b|\b0?{day}\s+(?:{names})\b(?:\s+{target.year})?(?!\s+\d{{4}})|\b(?:{names})\s+0?{day}\b(?:,?\s+{target.year})?(?!,?\s+\d{{4}}))"


def ground_semester_end(part, blocks):
    if not part.semesterEnd:
        return part
    quote, _ = source_quote(part.semesterEndSource, blocks)
    supported = False
    try:
        pattern = date_pattern(part.semesterEnd)
        supported = (bool(quote)
                     and any(re.match(r"\s*(?:[:–—-]\s*)?(?:(?:on|op|is)\s+)?" + pattern,
                                      quote[m.end():], re.I) for m in END.finditer(quote)))
    except (ValueError, TypeError):
        pass
    if supported:
        return part
    return part.model_copy(update={"semesterEnd": "", "warnings": [*part.warnings,
        "Semester end lacks a verified explicit source statement and was left blank. Exam-period starts, last assessments and teaching-week ranges do not establish it; enter the confirmed date before saving."]})


def ground_exam_dates(part, blocks, module_code):
    if not part.examDate and not part.examDateEnd:
        return part
    quote, block = source_quote(part.examDateSource, blocks)
    code = re.sub(r"[^a-z0-9]", "", module_code.lower())
    filename = re.sub(r"[^a-z0-9]", "", (block or {}).get("source_file", "").lower())
    scoped = bool(code and (code in filename or code in re.sub(r"[^a-z0-9]", "", quote.lower())))
    match = None
    try:
        # A general institutional examination period is not this module's slot.
        general = re.search(r"\bexam(?:ination)?s?\s+(?:period|week)|eksamen(?:tydperk|periode)", quote, re.I)
        label = rf"(?:\b{re.escape(module_code)}\s+(?:final\s+)?(?:examination|exam|eksamen)(?:\s+(?:date|on|op|datum))?|\b(?:examination|exam|eksamen)\s+(?:date|on|op|datum))"
        if scoped and quote and not general and part.examDate:
            match = re.search(label + r"\s*:?\s*" + date_pattern(part.examDate), quote, re.I)
        if match:
            end_ok = not part.examDateEnd or bool(re.match(r"\s*(?:to|until|tot|–|—|-)\s*" + date_pattern(part.examDateEnd), quote[match.end():], re.I))
            if end_ok:
                return part
            return part.model_copy(update={"examDateEnd": None, "warnings": [*part.warnings,
                "The exam range end lacks verified source support and was omitted; review the module-specific timetable."]})
    except (ValueError, TypeError):
        pass
    return part.model_copy(update={"examDate": None, "examDateEnd": None, "warnings": [*part.warnings,
        "No verified module-specific exam date was found. General examination-period dates are not this module's scheduled exam; check its timetable before saving."]})
