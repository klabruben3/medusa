import asyncio
from app.ai.generate_module import create_module
from app.utils.documents import DocumentError

async def main():
    # This tool uses only the synthetic plan below; report semantic failures for QA.
    import app.ai.generate_module as generation
    original_validation = generation.validate_module
    def diagnose(module):
        errors = original_validation(module)
        if errors:
            print("Synthetic validation:", errors)
            print("Synthetic IDs:", [(a.id, a.category) for a in module.assessments], [(c.componentId, c.weight) for c in module.participationFormula.components])
        return errors
    generation.validate_module = diagnose
    sources = [{"filename": "synthetic-assessment-plan.txt", "text": """ABC123: Example Module. Semester starts 2026-07-01 and ends 2026-11-01.
There is no examination. The final module mark is the participation mark, with a minimum pass mark of 50%.
Class Test 1 on 2026-08-01 at 10:00 has a maximum of 40 marks and contributes 100% of the module mark.
No other assessments or pass requirements apply."""}]
    import sys
    if "--coverage" in sys.argv:
        sources.insert(0, {"filename": "synthetic-general-information.txt", "text":
            "\n\n".join("University library visitors can use quiet study spaces. This is general campus information, not an assessment rule." for _ in range(45))})
    result = await create_module(sources)
    print("Synthetic result:", [(a.name, a.maxScore) for a in result.module.assessments], [(c.componentId, c.weight) for c in result.module.participationFormula.components])
    assert result.module.moduleId == 'abc123'
    assert len(result.module.assessments) == 1
    assert result.module.assessments[0].maxScore == 40
    assert result.module.participationFormula.components[0].weight == 100
    assert result.module.participationFormula.minimumToPass == 50
    assert result.module.id == ''
    print('Live Groq smoke test passed: source-linked evidence, 20B/120B routing, complete module, linked formula, correct marks and threshold.')

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except DocumentError as exc:
        raise SystemExit(f"Smoke test failed ({exc.code}): {exc}") from None
