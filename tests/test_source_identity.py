import unittest
from unittest.mock import AsyncMock, patch
from app.ai.generate_module import run_identity
from app.ai.partials import PARTIALS
from app.utils.documents import DocumentError

class SourceIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_typo_is_reextracted_once_from_original_sources(self):
        typo=PARTIALS["identity"](code="ABX123",name="Example")
        valid=PARTIALS["identity"](code="ABC123",name="Example")
        blocks=[{"content":"ABC123: Example","source_file":"ABC123 guide.pdf"}]
        with patch("app.ai.generate_module.run_worker",new=AsyncMock(side_effect=[typo,valid])) as worker:
            self.assertEqual((await run_identity(None,blocks)).code,"ABC123")
            self.assertEqual(worker.await_count,2)
            self.assertTrue(all(call.args[2] is blocks for call in worker.await_args_list))
        self.assertEqual(typo.code,"ABX123")

    async def test_unverified_code_and_partial_prefix_fail_closed(self):
        for code in ("ABX123","ABC12",""):
            value=PARTIALS["identity"](code=code,name="Example")
            with patch("app.ai.generate_module.run_worker",new=AsyncMock(return_value=value)) as worker:
                with self.assertRaises(DocumentError) as error:
                    await run_identity(None,[{"content":"ABC123: Example"}])
                self.assertEqual(error.exception.code,"unverified_module_identity")
                self.assertEqual(worker.await_count,2)

    async def test_case_spacing_and_original_filename_are_valid_sources(self):
        value=PARTIALS["identity"](code="abc123",name="Example")
        for block in ({"content":"Course ABC 123"},{"content":"Example","source_file":"ABC123 guide.pdf"}):
            with patch("app.ai.generate_module.run_worker",new=AsyncMock(return_value=value)) as worker:
                self.assertEqual((await run_identity(None,[block])).code,"abc123")
                worker.assert_awaited_once()
