"""Live routing probe using only synthetic bilingual and table fixtures."""
import asyncio
import json
from groq import AsyncGroq
from app.ai.evidence import extract_batch


async def main():
    blocks = [
        {"id": "section-a", "source_file": "synthetic.pdf", "page": 1, "type": "text",
         "content": "MTHS123 Example Module. Toets\u00a01: 40 punte — 25% van die deelnamepunt.\nClass test 1: 40 marks, 25% of the participation mark."},
        {"id": "section-b", "source_file": "synthetic.pdf", "page": 2, "type": "table",
         "content": json.dumps({"rows": [["Assessment", "Maximum", "Weight"], ['Assignment "A"', "60", "75%"]]})},
    ]
    async with AsyncGroq(timeout=60, max_retries=0) as client:
        facts = await extract_batch(client, blocks)
    originals = {b["id"]: b for b in blocks}
    assert {fact["id"] for fact in facts if fact["purpose"] == "grading"} == set(originals)
    assert all(fact["content"] == originals[fact["id"]]["content"] for fact in facts)
    print("Live evidence routing passed: bilingual prose and escaped table text preserved exactly from source IDs.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("Live routing failed:", type(exc).__name__, getattr(exc, "status_code", None), getattr(exc, "code", None))
        raise SystemExit(1) from None
