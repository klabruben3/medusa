"""Convert the extraction protocol's optional unknown sentinel, never known facts."""
from typing import get_args
from pydantic import BaseModel

OPTIONAL_REQUIREMENTS = {
    "participationMin": "participation admission threshold",
    "examMin": "exam subminimum",
    "finalMin": "final pass threshold",
    "minimumCompletionPercent": "assessment-completion requirement",
    "dropLowest": "number of dropped assessments",
    "minimumCompleted": "minimum number of completed assessments",
    "totalInCategory": "category assessment count",
    "minimumExamAdmission": "assessment admission requirement",
}


def optional_unknowns(model):
    changed = set()
    def walk(value):
        if isinstance(value, BaseModel):
            updates = {}
            for name, field in type(value).model_fields.items():
                item = getattr(value, name)
                if (name in OPTIONAL_REQUIREMENTS and type(None) in get_args(field.annotation)
                        and isinstance(item, (int, float)) and not isinstance(item, bool) and item == -1):
                    updates[name] = None
                    changed.add(name)
                else:
                    replacement = walk(item)
                    if replacement is not item:
                        updates[name] = replacement
            return value.model_copy(update=updates) if updates else value
        if isinstance(value, list):
            items = [walk(item) for item in value]
            return items if any(new is not old for new, old in zip(items, value)) else value
        return value
    result = walk(model)
    return result, sorted(changed)


def unknown_notes(fields):
    return [f"Extraction did not establish the optional {OPTIONAL_REQUIREMENTS[name]}. Review the source rule if it applies."
            for name in fields]
