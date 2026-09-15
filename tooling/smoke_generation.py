import asyncio
from app.ai.generate_module import create_module

async def main():
    result = await create_module([{"filename": "synthetic-assessment-plan.txt", "text": """ABC123: Example Module. Semester starts 2026-07-01 and ends 2026-11-01.
There is no examination. The final module mark is the participation mark, with a minimum pass mark of 50%.
Class Test 1 on 2026-08-01 at 10:00 has a maximum of 40 marks and contributes 100% of the module mark.
No other assessments or pass requirements apply."""}])
    assert result.module.moduleId == 'abc123'
    assert len(result.module.assessments) == 1
    assert result.module.assessments[0].maxScore == 40
    assert result.module.participationFormula.components[0].weight == 100
    assert result.module.participationFormula.minimumToPass == 50
    assert result.module.id == ''
    print('Live Groq smoke test passed: complete module, linked assessment/formula, correct marks and threshold.')

asyncio.run(main())
