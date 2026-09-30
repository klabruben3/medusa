"""Semantic checks for the relationships consumed by Academiq calculations."""
import math
import re
from datetime import date


def validate_module(module):
    errors = []
    data = module.model_dump(exclude_none=True)
    def walk(value, path="module"):
        if isinstance(value, dict):
            for key, item in value.items():
                location = f"{path}.{key}"
                if key in {"date", "dateEnd", "dateAvailable", "semesterStart", "semesterEnd", "examDate", "examDateEnd", "start", "end"} and item:
                    try:
                        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item):
                            raise ValueError()
                        date.fromisoformat(item)
                    except (ValueError, TypeError):
                        errors.append(f"{location} must be an ISO calendar date.")
                if key == "time" and item and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item):
                    errors.append(f"{location} must be HH:mm.")
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    if not math.isfinite(item) or item < 0:
                        errors.append(f"{location} must be finite and nonnegative.")
                    if key in {"weight", "minimumToPass", "participationMin", "examMin", "finalMin", "minimumCompletionPercent", "minimumExamAdmission"} and item > 100:
                        errors.append(f"{location} must be at most 100.")
                    if key == "maxScore" and item <= 0:
                        errors.append(f"{location} must be positive.")
                walk(item, location)
            for start, end in [("date", "dateEnd"), ("dateAvailable", "date"), ("semesterStart", "semesterEnd"), ("examDate", "examDateEnd"), ("start", "end")]:
                if value.get(start) and value.get(end) and value[start] > value[end]:
                    errors.append(f"{path}: {end} precedes {start}.")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{path}[{i}]")
    walk(data)
    ids = [a.id for a in module.assessments]
    if not ids or not module.participationFormula.components:
        errors.append("At least one assessment and a participation formula are required.")
    if abs(sum(c.weight for c in module.participationFormula.components) - 100) > .1:
        errors.append("Participation formula component weights must total 100 percent; retain source percentages, not decimal fractions.")
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        errors.append("Assessment IDs must be unique and nonempty.")
    component_ids = [c.componentId for c in module.participationFormula.components]
    if len(component_ids) != len(set(component_ids)):
        errors.append("Formula component IDs must be unique.")
    for comp in module.participationFormula.components:
        slug = comp.componentId.removeprefix(module.moduleId + "-")
        matches = [a for a in module.assessments if a.category == slug] or [a for a in module.assessments if a.id == comp.componentId]
        if not matches:
            errors.append(f"Formula {comp.componentId} has no matching assessment/category.")
        total = comp.totalInCategory or len(matches)
        if comp.dropLowest is not None and comp.dropLowest >= total:
            errors.append(f"{comp.componentId}: dropLowest must be less than the category size.")
        if comp.minimumCompleted is not None and comp.minimumCompleted > total:
            errors.append(f"{comp.componentId}: minimumCompleted exceeds category size.")
    assigned = {}
    for comp in module.participationFormula.components:
        slug = comp.componentId.removeprefix(module.moduleId + "-")
        matches = [a for a in module.assessments if a.category == slug] or [a for a in module.assessments if a.id == comp.componentId]
        for assessment in matches:
            if assessment.id in assigned:
                errors.append(f"{assessment.id} is counted in multiple formula components.")
            assigned[assessment.id] = comp.componentId
    if module.finalMarkFormula:
        formula = module.finalMarkFormula
        if not module.hasExam or abs(formula.participationWeight + formula.examWeight - 100) > .01:
            errors.append("Final mark weights require an exam and must total 100.")
    return errors
