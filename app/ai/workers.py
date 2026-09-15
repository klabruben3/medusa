import json
from typing import List, Optional

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel
from .stats import token_count


class FormulaComponent(BaseModel):
    componentId: str
    weight: float
    dropLowest: Optional[int] = None
    minimumCompleted: Optional[int] = None
    totalInCategory: Optional[int] = None
    useAll: Optional[bool] = None


class ParticipationFormula(BaseModel):
    components: List[FormulaComponent]
    minimumToPass: float


load_dotenv()
client = Groq()

MODEL = "openai/gpt-oss-safeguard-20b"

# Real example pulled from module_templates (fklg222) — exercises dropLowest-free
# plain weights, useAll+totalInCategory pairing, and the componentId slug format.
FEW_SHOT_EXAMPLE = {
    "input": (
        "Module code fklg222. Class test 1 is 18.33%, class test 2 is 18.33%, "
        "class test 3 is 18.34%. Semester test is 30%. MCQs are 6%, all 4 count. "
        "Quizzes are 4%, all 4 count. Attendance is 5%. Minimum to pass is 40%."
    ),
    "output": {
        "components": [
            {"componentId": "fklg222-clt01", "weight": 18.33},
            {"componentId": "fklg222-clt02", "weight": 18.33},
            {"componentId": "fklg222-clt03", "weight": 18.34},
            {"componentId": "fklg222-semester-test", "weight": 30},
            {"componentId": "fklg222-mcq", "weight": 6,
                "totalInCategory": 4, "useAll": True},
            {"componentId": "fklg222-quiz", "weight": 4,
                "totalInCategory": 4, "useAll": True},
            {"componentId": "fklg222-attendance", "weight": 5},
        ],
        "minimumToPass": 40,
    },
}

SYSTEM_PROMPT = (
    "Extract the grading/participation formula as schema-valid JSON. "
    "Never guess, infer, calculate, or redistribute; omit unstated optionals. "
    "componentId: <module_code>-<kebab-case-description>, never invent. "
    "weight: exact stated value; don't confuse marks with weights. "
    "dropLowest: N only if explicitly dropped. "
    "minimumCompleted: N only if explicitly required to qualify. "
    "totalInCategory: N only if explicitly stated, including 'all N'. "
    "useAll: true only for explicitly all N/items used; false only if explicitly not all; otherwise omit. "
    "minimumToPass: explicit overall passing %. "
    "Extract every distinct weighted component; merge only if source does. "
    "Resolve ambiguity literally, never by convention.\n\n"
    f"Example input: {FEW_SHOT_EXAMPLE['input']}\n"
    f"Example output: {json.dumps(FEW_SHOT_EXAMPLE['output'], separators=(',', ':'))}"
)


def extract_participation_formula(text: str) -> ParticipationFormula:
    schema = ParticipationFormula.model_json_schema()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Module data: {text}"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "ParticipationFormula", "schema": schema},
        },
        temperature=0,
    )

    token_count(response, "extract_participation_formula")

    raw = response.choices[0].message.content
    return ParticipationFormula.model_validate_json(raw)


def to_db_json(formula: ParticipationFormula) -> str:
    """Serialize matching Supabase shape — omits unset optional fields instead of nulling them."""
    return formula.model_dump_json(exclude_none=True)


if __name__ == "__main__":
    example = (
        "Homework is worth 30% of the grade, drop the lowest 2 scores out of 10. "
        "Quizzes are worth 20%, all 8 must be completed. Final exam is 50%. "
        "You need at least 60% overall to pass."
    )

    result = extract_participation_formula(example)
    print(to_db_json(result))
