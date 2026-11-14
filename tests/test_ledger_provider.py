import unittest
from unittest.mock import AsyncMock, patch
import httpx
from groq import APIStatusError, RateLimitError
from app.ai.fact_ledger import ObservationBatch, messages_for, request_cost
from app.ai.provider import complete
from test_evidence import response
from test_fact_ledger import block
from app.main import provider_limit_message


class LedgerProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_and_long_retry_limits_do_not_send_premature_second_request(self):
        review = {f'AI_GROQ_{name}_VERIFIED': 'true' for name in
                  ('NO_TRAINING', 'RETENTION', 'INTERNATIONAL_TRANSFER', 'MINOR_SAFEGUARDS')}
        review['AI_GROQ_REVIEW_REFERENCE'] = 'synthetic-ledger-limit-test'
        for message, retry in [('PRIVATE_ORG tokens per day', '61'), ('PRIVATE_ORG tokens per minute', '180')]:
            error = RateLimitError('PRIVATE_ORG', response=httpx.Response(429, headers={'retry-after': retry},
                request=httpx.Request('POST', 'https://api.groq.com')), body={'error': {'message': message}})
            client = AsyncMock()
            client.chat.completions.create.side_effect = error
            with self.subTest(message=message), patch.dict('os.environ', review), patch('app.ai.provider.limiter.reserve', new=AsyncMock()), patch('app.ai.provider.asyncio.sleep', new=AsyncMock()) as sleep:
                with self.assertRaises(RateLimitError):
                    await complete(client, 'facts', messages_for([block()]), ObservationBatch.model_json_schema(), 2600)
                self.assertEqual(client.chat.completions.create.await_count, 1)
                sleep.assert_not_awaited()
                self.assertNotIn('PRIVATE_ORG', provider_limit_message(error))
                if 'per day' in message:
                    self.assertIn('daily', provider_limit_message(error))

    async def test_actual_repair_request_matches_planned_budget_and_asks_for_data(self):
        review = {f'AI_GROQ_{name}_VERIFIED': 'true' for name in
                  ('NO_TRAINING', 'RETENTION', 'INTERNATIONAL_TRANSFER', 'MINOR_SAFEGUARDS')}
        review['AI_GROQ_REVIEW_REFERENCE'] = 'synthetic-ledger-provider-test'
        raw = '{"observations": []}'
        error = APIStatusError('PRIVATE_ERROR', response=httpx.Response(400,
            request=httpx.Request('POST', 'https://api.groq.com')), body={'error': {
                'code': 'json_validate_failed', 'failed_generation': raw}})
        client = AsyncMock()
        client.chat.completions.create.side_effect = [error, response({'observations': []})]
        capture = AsyncMock()
        with patch.dict('os.environ', review), patch('app.ai.provider.limiter.reserve', new=AsyncMock()) as reserve:
            with self.assertLogs('app.ai.provider', level='WARNING') as logs:
                await complete(client, 'facts', messages_for([block()]), ObservationBatch.model_json_schema(),
                               2600, on_rejected=capture)
        self.assertEqual(reserve.await_args_list[0].args[1], request_cost([block()]))
        self.assertEqual(reserve.await_args_list[1].args[1], request_cost([block()], retry=True))
        instruction = client.chat.completions.create.call_args.kwargs['messages'][-1]['content']
        self.assertIn('JSON DATA OBJECT', instruction)
        self.assertIn('NEVER return the schema definition', instruction)
        self.assertTrue(instruction.endswith('observations.'))
        capture.assert_awaited_once_with(raw, 'provider_schema')
        self.assertNotIn('PRIVATE_ERROR', str(logs.output))
