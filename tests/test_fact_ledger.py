import json
import unittest
from unittest.mock import AsyncMock, patch
from app.ai.fact_ledger import (FactBatch, compact_sources, validate_batch, parse_value,
    reduce_ledger, plan_batches, extract_ledger, request_cost)
from app.utils.documents import DocumentError
from test_evidence import response


def block(identifier='a', content='Class test 1: 40 marks, 30%.', file='guide.pdf'):
    return {'id': identifier, 'source_file': file, 'page': 1, 'type': 'paragraph', 'content': content}


def fact(identifier='a', value='40', quote='40 marks'):
    return {'kind': 'assessment', 'key': 'class-test-1', 'values': [{'field': 'maxScore', 'value': value}],
            'evidence': [{'block': identifier, 'quote': quote}]}


def batch(observations=None, covered=None):
    return FactBatch.model_validate({'covered': covered or ['a'], 'observations': observations or [fact()]})


class LedgerTests(unittest.IsolatedAsyncioTestCase):
    def test_source_packing_is_lossless_in_order_and_does_not_mutate(self):
        blocks = [block(), block('b', 'Unicode 文本'), block('c', file='other.pdf'), block('d')]
        packed = compact_sources(blocks)
        restored = [{**item, 'source_file': group['file']} for group in packed for item in group['blocks']]
        self.assertEqual(restored, blocks)
        self.assertEqual([group['file'] for group in packed], ['guide.pdf', 'other.pdf', 'guide.pdf'])
        self.assertEqual(blocks[0], block())

    def test_coverage_foreign_quote_and_wrong_numeric_value_fail_closed(self):
        for value in (batch(covered=['wrong']), batch(covered=['a', 'a']),
                      batch([fact(identifier='foreign')]), batch([fact(quote='invented')]), batch([fact(value='99')])):
            with self.subTest(value=value.model_dump()), self.assertRaises(ValueError):
                validate_batch(value, [block()])

    def test_typed_fields_reject_unknown_ownership_progress_and_sentinels(self):
        for kind, field, value in [('assessment', 'maxScore', '-1'), ('assessment', 'maxScore', 'true'),
                                   ('module', 'maxScore', '40'), ('assessment', 'score', '30'),
                                   ('formula', 'weight', 'NaN'), ('module', 'hasExam', '"true"')]:
            with self.subTest(field=field, value=value), self.assertRaises((ValueError, KeyError)):
                parse_value(kind, field, value)

    def test_duplicate_observation_fields_are_rejected(self):
        value = fact()
        value['values'] *= 2
        with self.assertRaises(ValueError):
            validate_batch(batch([value]), [block()])

    def test_formula_and_entity_keys_are_restricted(self):
        for key in ('https://bad.example', '../../secret', 'another-module'):
            value = {'kind': 'formula', 'key': key, 'values': [{'field': 'weight', 'value': '30'}],
                     'evidence': [{'block': 'a', 'quote': '30%'}]}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_batch(batch([value]), [block()])

    def test_dedup_retains_both_sources_and_conflicts_do_not_pick_a_winner(self):
        first = validate_batch(batch(), [block()])
        second = validate_batch(batch([fact('b')], ['b']), [block('b')])
        result = reduce_ledger([first, second])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['candidates']), 1)
        self.assertEqual(len(result[0]['candidates'][0]['evidence']), 2)
        third = validate_batch(batch([fact('c', '50', '50 marks')], ['c']), [block('c', '50 marks')])
        self.assertEqual({v['value'] for v in reduce_ledger([first, third])[0]['candidates']}, {40, 50})

    def test_planner_covers_all_blocks_without_cropping(self):
        blocks = [block(str(i), 'Source text. ' * 100) for i in range(12)]
        batches = plan_batches(blocks)
        self.assertGreater(len(batches), 1)
        self.assertEqual([b for group in batches for b in group], blocks)
        self.assertTrue(all(request_cost(group) <= 7500 for group in batches))

    async def test_oversize_job_rejected_before_provider(self):
        with patch('app.ai.fact_ledger.MAX_RESERVED_TOKENS', 1), patch('app.ai.fact_ledger.complete', new=AsyncMock()) as provider:
            with self.assertRaises(DocumentError) as error:
                await extract_ledger(None, [block()])
            self.assertEqual(error.exception.code, 'ledger_job_budget_exceeded')
            provider.assert_not_awaited()

    async def test_verified_fact_batch_calls_provider_once(self):
        with patch('app.ai.fact_ledger.complete', new=AsyncMock(return_value=response(batch().model_dump()))) as provider:
            result = await extract_ledger(None, [block()])
        self.assertEqual(result, [batch()])
        self.assertEqual(provider.await_count, 1)

    async def test_cache_is_revalidated_and_uses_no_provider_calls(self):
        with patch('app.ai.fact_ledger.complete', new=AsyncMock()) as provider:
            result = await extract_ledger(None, [block()], load_batch=AsyncMock(return_value=batch()))
            self.assertEqual(result, [batch()])
            provider.assert_not_awaited()
            with self.assertRaises(ValueError):
                await extract_ledger(None, [block()], load_batch=AsyncMock(return_value=batch([fact(value='99')])))
            provider.assert_not_awaited()

    async def test_bad_single_block_output_is_not_repaired_into_facts(self):
        with patch('app.ai.fact_ledger.complete', new=AsyncMock(return_value=response(batch([fact(value='99')]).model_dump()))) as provider:
            with self.assertRaises(DocumentError) as error:
                await extract_ledger(None, [block()])
        self.assertEqual(error.exception.code, 'ledger_unverified')
        self.assertEqual(provider.await_count, 1)
