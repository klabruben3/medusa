import json
import unittest
from unittest.mock import AsyncMock, patch
from app.ai.fact_ledger import (FactBatch, compact_sources, validate_batch, parse_value,
    reduce_ledger, plan_batches, extract_ledger, request_cost, ObservationBatch, materialize, indexed_sources, PROMPT)
from app.utils.documents import DocumentError
from test_evidence import response


def block(identifier='a', content='Class test 1: 40 marks, 30%.', file='guide.pdf'):
    return {'id': identifier, 'source_file': file, 'page': 1, 'type': 'paragraph', 'content': content}


def fact(identifier='a', value=40, quote='40 marks'):
    return {'kind': 'assessment', 'key': 'class-test-1', 'values': [{'field': 'maxScore', 'value': value}],
            'evidence': [{'block': identifier, 'quote': quote}]}


def batch(observations=None, covered=None):
    return FactBatch.model_validate({'covered': covered or ['a'], 'observations': observations or [fact()]})


def indexed_batch(value):
    data = value.model_dump(include={'observations'})
    for observation in data['observations']:
        observation['evidence'] = [{'block': cite['block'], 'row': None} for cite in observation['evidence']]
    return data


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
                      batch([fact(identifier='foreign')]), batch([fact(quote='invented')]), batch([fact(value=99)])):
            with self.subTest(value=value.model_dump()), self.assertRaises(ValueError):
                validate_batch(value, [block()])

    def test_typed_fields_reject_unknown_ownership_progress_and_sentinels(self):
        for kind, field, value in [('assessment', 'maxScore', -1), ('assessment', 'maxScore', True),
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
            value = {'kind': 'formula', 'key': key, 'values': [{'field': 'weight', 'value': 30}],
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
        third = validate_batch(batch([fact('c', 50, '50 marks')], ['c']), [block('c', '50 marks')])
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
        with patch('app.ai.fact_ledger.complete', new=AsyncMock(return_value=response(indexed_batch(batch())))) as provider:
            result = await extract_ledger(None, [block()])
        self.assertEqual(result[0].observations[0].values, batch().observations[0].values)
        self.assertEqual(result[0].observations[0].evidence[0].quote, block()['content'])
        self.assertEqual(provider.await_count, 1)

    async def test_cache_is_revalidated_and_uses_no_provider_calls(self):
        with patch('app.ai.fact_ledger.complete', new=AsyncMock()) as provider:
            result = await extract_ledger(None, [block()], load_batch=AsyncMock(return_value=batch()))
            self.assertEqual(result, [batch()])
            provider.assert_not_awaited()
            with self.assertRaises(ValueError):
                await extract_ledger(None, [block()], load_batch=AsyncMock(return_value=batch([fact(value=99)])))
            provider.assert_not_awaited()

    async def test_bad_single_block_output_is_not_repaired_into_facts(self):
        with patch('app.ai.fact_ledger.complete', new=AsyncMock(return_value=response(indexed_batch(batch([fact(value=99)]))))) as provider:
            result = await extract_ledger(None, [block()])
        self.assertEqual(result[0].observations, [])
        self.assertEqual(result[0].rejected_claims[0].reason, 'source_value')
        self.assertEqual(provider.await_count, 1)

    def test_planned_retry_includes_actual_repair_instruction_headroom(self):
        blocks = [block(str(i), 'Source text. ' * 200) for i in range(12)]
        for group in plan_batches(blocks):
            self.assertLessEqual(request_cost(group, retry=True), 7500)
            self.assertGreater(request_cost(group, retry=True), request_cost(group))

    def test_native_value_types_preserve_integer_rules_and_structured_slots(self):
        self.assertEqual(parse_value('formula', 'minimumCompleted', 8), 8)
        self.assertEqual(parse_value('formula', 'minimumCompleted', 8.0), 8)
        with self.assertRaises(ValueError):
            parse_value('formula', 'minimumCompleted', 8.5)
        self.assertEqual(parse_value('module', 'hasExam', True), True)
        self.assertEqual(parse_value('assessment', 'name', 'Class test 1'), 'Class test 1')
        self.assertEqual(parse_value('assessment', 'slots', [{'date': '2026-03-17', 'label': 'Group A'}]),
                         [{'date': '2026-03-17', 'time': None, 'label': 'Group A'}])
        with self.assertRaises(ValueError):
            parse_value('formula', 'weight', float('inf'))

    def test_indexed_tables_keep_cells_and_server_materializes_original_evidence(self):
        rows = [['Assessment', 'Marks'], ['Class test 1', '40']]
        source = {**block(content=json.dumps({'rows': rows}, ensure_ascii=False)), 'type': 'table'}
        sent = indexed_sources([source])[0]['blocks'][0]
        self.assertEqual([row['cells'] for row in sent['rows']], rows)
        data = indexed_batch(batch())
        data['observations'][0]['evidence'][0]['row'] = 1
        result = materialize(ObservationBatch.model_validate(data), [source])
        validate_batch(result, [source])
        self.assertEqual(result.observations[0].evidence[0].quote, json.dumps(rows[1]))
        self.assertEqual(source['content'], json.dumps({'rows': rows}))
        data['observations'][0]['evidence'][0]['row'] = None
        with self.assertRaises(ValueError):
            materialize(ObservationBatch.model_validate(data), [source])
        for row in (-1, 99):
            data['observations'][0]['evidence'][0]['row'] = row
            with self.subTest(row=row), self.assertRaises(ValueError):
                materialize(ObservationBatch.model_validate(data), [source])

    async def test_usage_is_observed_even_when_numeric_grounding_fails(self):
        result = response(indexed_batch(batch([fact(value=99)])))
        from types import SimpleNamespace
        result.usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        usage = AsyncMock()
        with patch('app.ai.fact_ledger.complete', new=AsyncMock(return_value=result)):
            reviewed = await extract_ledger(None, [block()], on_response=usage)
        self.assertEqual(len(reviewed[0].rejected_claims), 1)
        usage.assert_awaited_once_with({'inputTokens': 100, 'outputTokens': 50})

    def test_compact_schema_prompt_still_declares_domain_enums(self):
        from app.types.schema import AssessmentType
        from typing import get_args
        self.assertIn('assessment.type must be one of:', PROMPT)
        for value in get_args(AssessmentType):
            self.assertIn(value, PROMPT)
        with self.assertRaises(ValueError):
            parse_value('assessment', 'type', 'test')

    def test_singleton_identity_is_server_owned_without_changing_source_values(self):
        value = {'observations': [{'kind': 'module', 'key': 'ABC123',
            'values': [{'field': 'code', 'value': 'ABC123'}], 'evidence': [{'block': 'a', 'row': None}]}]}
        sources = [block(content='ABC123 Example.')]
        result = validate_batch(materialize(ObservationBatch.model_validate(value), sources), sources)
        self.assertEqual(result.observations[0].key, 'module')
        self.assertEqual(result.observations[0].values[0].value, 'ABC123')
        self.assertEqual(value['observations'][0]['key'], 'ABC123')

    def test_assessment_title_alias_preserves_text_and_never_overwrites_another_name(self):
        data = indexed_batch(batch())
        data['observations'][0]['values'] = [{'field': 'label', 'value': 'Weekly test1'}]
        sources = [block(content='Weekly test1: 40 marks.')]
        result = materialize(ObservationBatch.model_validate(data), sources)
        self.assertEqual(result.observations[0].values[0].field, 'name')
        self.assertEqual(result.observations[0].values[0].value, 'Weekly test1')
        data['observations'][0]['values'].append({'field': 'name', 'value': 'Different title'})
        with self.assertRaises(ValueError):
            validate_batch(materialize(ObservationBatch.model_validate(data), sources), sources)
        data['observations'][0]['values'] = [{'field': 'label', 'value': 'Group A'}]
        with self.assertRaises(ValueError):
            validate_batch(materialize(ObservationBatch.model_validate(data), sources), sources)
