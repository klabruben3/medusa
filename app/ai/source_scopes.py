"""Preserve differing literal class-test coverage as review notes, not a winner.

This deliberately recognizes only numbered class-test clauses with explicit
numeric study-unit coverage. It is not a general contradiction detector.
"""
import json
import re

TEST = re.compile(r"\b(?:class\s*tests?|klastoets)\s*(\d+)\b", re.I)
NUMBER = r"\d+(?:\.\d+)*(?:\s*[-–—]\s*\d+(?:\.\d+)*)?"
UNITS = re.compile(r"\bstudy\s*units?\s+(" + NUMBER + r")\b", re.I)
DIRECT = re.compile(r"\s*[:(]\s*(" + NUMBER + r")(?=\s*(?:[)\n]|$))")


def review_source_scopes(part, blocks):
    facts = {}
    for block in blocks:
        texts = [block["content"]]
        try:
            rows = json.loads(block["content"])["rows"]
            texts = [str(cell) for row in rows for cell in row]
        except (ValueError, KeyError, TypeError):
            pass
        for text in texts:
            matches = list(TEST.finditer(text))
            for i, match in enumerate(matches):
                clause = text[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
                # Do not borrow coverage from the following semester-test clause.
                clause = re.split(r"\b(?:semester[ -]test|semestertoets)\b", clause, maxsplit=1, flags=re.I)[0]
                scope = UNITS.search(clause) or DIRECT.match(clause)
                if not scope:
                    continue
                literal = scope.group(1)
                normalized = re.sub(r"\s", "", literal).replace("–", "-").replace("—", "-")
                reference = f"{block['source_file']}, PDF page {block['page']}, block {block['id']}"
                facts.setdefault(match.group(1), {}).setdefault(normalized, set()).add((literal, reference))
    assessments = list(part.assessments)
    notes = []
    for number, descriptions in facts.items():
        candidates = [a for a in assessments if a.type == "class-test" and
                      any(m.group(1) == number for m in TEST.finditer(a.name))]
        if len(descriptions) < 2 or len(candidates) != 1:
            continue
        assessment = candidates[0]
        source_notes = "; ".join(f"{literal} ({reference})" for values in descriptions.values()
                                 for literal, reference in sorted(values))
        note = (f"Class Test {number} study coverage requires source review: {source_notes}. "
                "These descriptions may differ in scope or granularity. No source was selected; "
                "studyUnits is unset until the course coverage is confirmed.")
        assessments = [a.model_copy(update={"studyUnits": None}) if a.id == assessment.id else a for a in assessments]
        notes.append(note)
    if not notes:
        return part
    return part.model_copy(update={"assessments": assessments,
        "warnings": list(dict.fromkeys([*part.warnings, *notes])),
        "dataNote": "\n\n".join(filter(None, [part.dataNote, *(note for note in notes if note not in (part.dataNote or ""))]))})
