"""Narrow source-backed links for explicit rules, never inferred default splits."""
import re
from collections import defaultdict
from ..types.schema import FinalMarkFormula
from ..utils.documents import DocumentError


def link_source_rules(part, blocks):
    pages = defaultdict(list)
    for block in blocks:
        pages[(block["source_file"], block["page"])].append(block["content"])
    warnings = list(part.warnings)
    notes = [part.dataNote] if part.dataNote else []
    final = part.finalMarkFormula
    for (filename, page), items in pages.items():
        text = " ".join(items)
        for match in re.finditer(r"\bEach\s+of\s+the\s+following\s+marks\s+will\s+be\s+(\d+(?:[.,]\d+)?)\s*%\s+of\s+the\s+final\s+mark\s*:", text, re.I):
            weight = float(match.group(1).replace(",", "."))
            before, after = text[max(0, match.start()-400):match.start()], text[match.end():match.end()+500]
            if (not part.hasExam or abs(weight * 2 - 100) > .01
                    or not re.search(r"assessment|completion|pass|module mark", before, re.I)
                    or not re.search(r"participation\s+mark", after, re.I)
                    or not re.search(r"examination\s+mark", after, re.I)):
                continue
            if final is not None and (abs(final.participationWeight-weight) > .01 or abs(final.examWeight-weight) > .01):
                error = DocumentError("The extracted final-mark rule disagrees with an explicit source statement.", 422, "invalid_grading")
                error.validation_errors = ["Final mark weights contradict the explicit equal participation/examination statement; verify the original source blocks."]
                error.issues = [{"code": "final_weights", "message": "Final-mark weights disagree with an explicit source rule."}]
                raise error
            if final is None:
                final = FinalMarkFormula(participationWeight=weight, examWeight=weight)
                warnings = [note for note in warnings if not (re.search(r"final.*(?:split|weight)", note, re.I)
                            and re.search(r"not\s+(?:specified|provided|stated)", note, re.I))]
                warnings.append(f"Final-mark split linked to the explicit equal-weight source rule ({filename}, page {page}); review before saving.")
        for index, content in enumerate(items):
            if re.search(r"\bparticipation\b.*\bsupplement\b.*\bbetween\b", content, re.I) and re.search(r"\d", content):
                clause = content
                if index + 1 < len(items) and re.search(r"\bonly once\b", items[index+1], re.I):
                    clause += " " + items[index+1]
                quote = f"Source condition ({filename}, page {page}): {clause}"
                if quote not in "\n\n".join(notes):
                    notes.append(quote)
    return part.model_copy(update={"finalMarkFormula": final, "dataNote": "\n\n".join(notes) or None,
                                   "warnings": list(dict.fromkeys(warnings))})
