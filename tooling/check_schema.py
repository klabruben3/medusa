"""Check the Python field contract against Academiq's actual TypeScript interfaces.

Usage: python -m tooling.check_schema /path/to/academiq/types/index.ts
This does not generate a replacement source of truth.
"""
import re
import sys
from pathlib import Path
from typing import get_args
from app.types import schema


def check(path):
    source = Path(path).read_text(encoding="utf-8")
    names = ("AssessmentSlot", "AssessmentComponent", "FormulaComponent", "ParticipationFormula",
             "PassRequirements", "FinalMarkFormula", "ExamOpportunity", "ExamPaper", "ExamInfo",
             "ModuleGroup", "RecessPeriod", "Module")
    for name in names:
        match = re.search(r"export interface " + name + r"\s*\{(.*?)\n\}", source, re.S)
        if not match:
            raise AssertionError(f"Missing TypeScript interface: {name}")
        expected = set(re.findall(r"^\s*(\w+)\??\s*:", match[1], re.M))
        actual = set(getattr(schema, name).model_fields)
        if expected != actual:
            raise AssertionError(f"{name} fields differ: {expected ^ actual}")
    assessment_types = re.search(r"export type AssessmentType\s*=(.*?);", source, re.S).group(1)
    if set(re.findall(r'"([^\"]+)"', assessment_types)) != set(get_args(schema.AssessmentType)):
        raise AssertionError("AssessmentType differs")
    print("Schema parity: 12 interfaces and AssessmentType match Academiq.")


if __name__ == "__main__":
    check(sys.argv[1])
