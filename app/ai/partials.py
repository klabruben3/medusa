"""Worker fields are selected from Module, never maintained as duplicate schemas."""
from copy import deepcopy
from pydantic import create_model, Field
from ..types.schema import BaseModel, Module

FIELDS = {
    "identity": ("code", "name", "lecturer", "email", "office", "consultationHours", "groups"),
    "grading": ("assessments", "participationFormula", "passRequirements", "finalMarkFormula", "hasExam", "examInfo"),
    "calendar": ("semesterStart", "semesterEnd", "examDate", "examDateEnd", "examOpportunities", "recessPeriods"),
}


def partial_model(purpose):
    fields = {name: (Module.model_fields[name].annotation, deepcopy(Module.model_fields[name]))
              for name in FIELDS[purpose]}
    fields["warnings"] = (list[str], Field(default_factory=list))
    # Conflicting numeric/identity facts cannot safely be represented as one answer.
    fields["conflicts"] = (list[str], Field(default_factory=list))
    return create_model(purpose.title() + "Part", __base__=BaseModel, **fields)


PARTIALS = {purpose: partial_model(purpose) for purpose in FIELDS}

QUERIES = {
    "identity": [
        "Module code and full module name study guide title module identification",
        "Lecturer dosent email office consultation hours contact details",
        "Class groups language lecturers venues periods tutorial practical groups",
    ],
    "grading": [
        "All assessments tests assignments practicals quizzes names categories dates deadlines times maximum marks weights",
        "Participation mark calculation category weighting drop lowest best tests minimum completion exam admission pass requirements",
        "Final module mark exam participation split exam subminimum final pass threshold examination papers duration study units",
    ],
    "calendar": [
        "Semester start end dates academic calendar teaching term recess holidays",
        "Examination first second opportunity dates exam timetable date ranges",
    ],
}
