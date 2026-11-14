import unittest
from app.ai.optional_unknowns import optional_unknowns
from app.ai.generate_module import merge_parts
from app.ai.partials import PARTIALS
from app.types.schema import PassRequirements
from test_grading_links import grading
from test_pipeline import sample

class OptionalUnknownTests(unittest.TestCase):
    def test_optional_unknown_is_unset_without_mutating_known_rules(self):
        part=grading()
        part.passRequirements=PassRequirements(participationMin=40,examMin=40,finalMin=50,minimumCompletionPercent=-1)
        result,fields=optional_unknowns(part)
        self.assertEqual(fields,["minimumCompletionPercent"])
        self.assertIsNone(result.passRequirements.minimumCompletionPercent)
        self.assertEqual(part.passRequirements.minimumCompletionPercent,-1)
        self.assertEqual(result.passRequirements.examMin,40)
        self.assertEqual(result.assessments,part.assessments)
        self.assertEqual(result.participationFormula,part.participationFormula)

    def test_required_maxima_and_weights_remain_unknown_and_known_optional_values_remain(self):
        part=grading((-1,100))
        part.assessments[0].maxScore=-1
        part.participationFormula.minimumToPass=-1
        part.passRequirements=PassRequirements(minimumCompletionPercent=80)
        result,fields=optional_unknowns(part)
        self.assertIs(result,part)
        self.assertEqual(fields,[])
        self.assertEqual(result.assessments[0].maxScore,-1)
        self.assertEqual(result.assessments[0].weight,-1)
        self.assertEqual(result.participationFormula.minimumToPass,-1)
        self.assertEqual(result.passRequirements.minimumCompletionPercent,80)

    def test_unknown_optional_rule_does_not_discard_a_valid_formula_at_assembly(self):
        module=sample().model_dump()
        parts={purpose:PARTIALS[purpose].model_validate({key:module[key] for key in PARTIALS[purpose].model_fields if key in module}) for purpose in PARTIALS}
        parts["grading"].passRequirements=PassRequirements(finalMin=50,minimumCompletionPercent=-1)
        result=merge_parts(parts)
        self.assertEqual(result.module.participationFormula,parts["grading"].participationFormula)
        self.assertIsNone(result.module.passRequirements.minimumCompletionPercent)
        self.assertIn("optional assessment-completion requirement",result.module.dataNote)
        self.assertEqual(parts["grading"].passRequirements.minimumCompletionPercent,-1)
