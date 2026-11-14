import unittest
from pydantic import ValidationError
from app.ai.partials import GRADING_EXTRACTION, ASSESSMENT_DEFINITION
from app.ai.generate_module import project_grading

class WeightProjectionTests(unittest.TestCase):
    def part(self,components):
        return GRADING_EXTRACTION(hasExam=True,assessments=[
            {"id":"abc123-test-1","name":"Test 1","type":"class-test","category":"tests","maxScore":40},
            {"id":"abc123-test-2","name":"Test 2","type":"class-test","category":"tests","maxScore":40},
            {"id":"abc123-exam","name":"Exam","type":"exam","maxScore":100}],
            participationFormula={"components":components,"minimumToPass":40},
            finalMarkFormula={"participationWeight":50,"examWeight":50})

    def test_individual_weights_come_from_participation_not_the_final_split(self):
        part=self.part([{"componentId":"abc123-test-1","weight":40},{"componentId":"abc123-test-2","weight":60}])
        result=project_grading(part,{"code":"ABC123"})
        self.assertEqual([a.weight for a in result.assessments],[40,60,0])
        self.assertEqual(result.participationFormula,part.participationFormula)
        self.assertEqual(result.finalMarkFormula,part.finalMarkFormula)
        self.assertNotIn("weight",part.assessments[0].model_dump())

    def test_pooled_weights_stay_in_the_formula_without_per_assessment_duplication(self):
        part=self.part([{"componentId":"abc123-tests","weight":100,"dropLowest":1}])
        result=project_grading(part,{"code":"ABC123","moduleId":"abc123"})
        self.assertEqual([a.weight for a in result.assessments],[0,0,0])
        self.assertEqual(result.participationFormula.components[0].weight,100)
        self.assertEqual(result.participationFormula.components[0].dropLowest,1)

    def test_unknown_source_weights_are_not_normalized_or_made_positive(self):
        part=self.part([{"componentId":"abc123-test-1","weight":-1}])
        result=project_grading(part,{"code":"ABC123"})
        self.assertEqual(result.assessments[0].weight,-1)
        self.assertEqual(result.participationFormula.components[0].weight,-1)

    def test_definition_schema_forbids_competing_weights_and_personal_progress(self):
        base={"id":"x","name":"Test","type":"class-test","maxScore":40}
        for field,value in (("weight",30),("score",10),("completed",True)):
            with self.assertRaises(ValidationError):
                ASSESSMENT_DEFINITION.model_validate({**base,field:value})
