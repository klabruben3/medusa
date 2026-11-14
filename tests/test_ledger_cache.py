import unittest
from unittest.mock import patch
from app.ai.ledger_cache import checkpoint_key
from test_fact_ledger import block


class CheckpointTests(unittest.TestCase):
    def key(self, *, review=None, inputs=None, model='openai/gpt-oss-20b', owner='synthetic-owner-a'):
        return checkpoint_key(review or {'reference': 'synthetic-review', 'apiKeySha256': 'a' * 64},
            inputs or [{'file': 'guide.pdf', 'sha256': 'b' * 64}], model, [block()], owner_scope=owner)

    def test_owner_credential_model_and_source_boundaries_are_separate(self):
        first = self.key()
        self.assertEqual(first, self.key())
        for other in (self.key(owner='synthetic-owner-b'), self.key(model='openai/gpt-oss-120b'),
                      self.key(review={'reference': 'synthetic-review', 'apiKeySha256': 'c' * 64}),
                      self.key(inputs=[{'file': 'guide.pdf', 'sha256': 'd' * 64}])):
            self.assertNotEqual(first, other)
        with self.assertRaises(ValueError):
            self.key(owner='')

    def test_unrelated_file_does_not_buy_the_same_batch_again(self):
        self.assertEqual(self.key(), self.key(inputs=[{'file': 'guide.pdf', 'sha256': 'b' * 64},
            {'file': 'other.pdf', 'sha256': 'c' * 64}]))
        with self.assertRaises(ValueError):
            self.key(inputs=[{'file': 'other.pdf', 'sha256': 'b' * 64}])

    def test_prompt_change_invalidates_request_checkpoint(self):
        first = self.key()
        with patch('app.ai.fact_ledger.PROMPT', 'Changed extraction instructions'):
            self.assertNotEqual(first, self.key())
