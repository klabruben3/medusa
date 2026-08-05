# extract_modules.py
import json
from groq import Groq
from ..ai import ModuleList

from datetime import date

current_year = date.today().year

from dotenv import load_dotenv
load_dotenv()

client = Groq()


def _make_strict_compatible(schema: dict) -> dict:
    """Recursively make a Pydantic JSON schema compatible with Groq's
    strict structured output mode:
      1. additionalProperties: false on every object
      2. every property listed in `required` (optional fields stay
         "optional" via their type already allowing null, from
         Optional[X] in the Pydantic model)
    """
    if isinstance(schema, dict):
        if schema.get("type") == "object" or "properties" in schema:
            schema["additionalProperties"] = False
            if "properties" in schema:
                schema["required"] = list(schema["properties"].keys())
        for value in schema.values():
            _make_strict_compatible(value)
    elif isinstance(schema, list):
        for item in schema:
            _make_strict_compatible(item)
    return schema


def extract_modules() -> list[dict]:
    schema = ModuleList.model_json_schema()
    schema = _make_strict_compatible(schema)

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        max_tokens=4000,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "module_list",
                "strict": True,
                "schema": schema,
            },
        },
        messages=[
            {"role": "system", "content": "You extract structured academic module data from documents."},
            {
                "role": "user",
                "content": (
                    "Create exactly one placeholder Module object to test the schema. "
                    "For every string field, use an empty string \"\", "
                    "except: for `color`, use a random hex color code, "
                    "For every required number field, use 0, "
                    f"except: for `addedYear`, use the current year, {current_year}. "
                    "For every nullable/optional field, use null. "
                    "Do not invent realistic data otherwise — this is a structural test only."
                ),
            },
        ],
    )

    raw_json = response.choices[0].message.content
    parsed = ModuleList.model_validate(json.loads(raw_json))
    return [m.model_dump(exclude_none=True) for m in parsed.modules]
