"""Offline pricing, conservative reservations and durable reuse contracts."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import call_budget
from durable_calls import DurableCalls, encode, sha
from question_calls import QuestionCalls
import hybrid_pipeline


def result(tier='default', model='gpt-6.1-sol'):
    return {'model': model, 'returned_service_tier': tier, 'usage_final': True,
            'stop_reason': 'end_turn', 'content': [],
            'usage': {'input_tokens': 1000, 'output_tokens': 100,
                      'input_tokens_details': {'cached_tokens': 200, 'cache_write_tokens': 100}}}


class Ledger:
    space_id = 'synthetic-space'

    def __init__(self, saved=None):
        self.saved = saved
        self.requests = []
        self.receipts = []

    def call(self, op, **fields):
        if op in ('reserve_call', 'question_reserve'):
            self.requests.append(fields)
            return {'request_hash': sha(fields['request_json']), 'send': self.saved is None,
                    'response_json': self.saved,
                    'response_hash': sha(self.saved) if self.saved else None,
                    'call_index': fields['call_index']}
        if op in ('receive_call', 'question_receive'):
            self.receipts.append(fields)
            self.saved = fields['response_json']
            return {'saved': True}
        raise AssertionError('Unexpected ledger operation')


class PricingTests(unittest.TestCase):
    def test_sol_standard_and_flex_including_cache_writes(self):
        self.assertEqual(call_budget.usage_micro_usd(result(), 'gpt-6.1-sol'), 2670)
        self.assertEqual(call_budget.usage_micro_usd(result('flex'), 'gpt-6.1-sol'), 1335)

    def test_luna_standard_and_flex(self):
        self.assertEqual(call_budget.usage_micro_usd(result(model='gpt-6-luna'), 'gpt-6-luna'), 135)
        self.assertEqual(call_budget.usage_micro_usd(result('flex', 'gpt-6-luna'), 'gpt-6-luna'), 68)

    def test_cost_uses_returned_not_requested_tier(self):
        value = result('flex')
        value['requested_service_tier'] = 'default'
        self.assertEqual(call_budget.usage_micro_usd(value, 'gpt-6.1-sol'), 1335)

    def test_unknown_and_missing_tier_costs_remain_unknown(self):
        for model in ('gpt-6.1-sol', 'gpt-6-luna'):
            for tier in (None, 'priority', '', 42):
                with self.subTest(model=model, tier=tier):
                    self.assertIsNone(call_budget.usage_micro_usd(result(tier, model), model))

    def test_invalid_usage_remains_unknown(self):
        cases = [dict(result(), usage_final=False), dict(result(), usage={}),
                 dict(result(), usage={'input_tokens': True, 'output_tokens': 1}),
                 dict(result(), usage={'input_tokens': 1, 'output_tokens': 1,
                                      'input_tokens_details': {'cached_tokens': 2}})]
        for value in cases:
            self.assertIsNone(call_budget.usage_micro_usd(value, 'gpt-6.1-sol'))

    def test_reservation_is_standard_in_both_modes(self):
        costs = []
        for mode in ('default', 'flex_fallback'):
            with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': mode}):
                costs.append(call_budget.reserve_micro_usd('fixture', 'gpt-6.1-sol', 100, {}, counted_input_tokens=1000))
        self.assertEqual(costs, [15114, 15114])

    def test_luna_reserves_standard_including_assumed_write_premium(self):
        self.assertEqual(call_budget.reserve_micro_usd('fixture', 'gpt-6-luna', 100, {}, counted_input_tokens=1000), 687)

    def test_original_standard_reservation_and_cost_preserved(self):
        source = ROOT.parents[2] / 'sol-operational-release-20261006/backend/call_budget.py'
        spec = importlib.util.spec_from_file_location('original_call_budget', source)
        original = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(original)
        for model in original.RATES:
            prompt = '["fixture"]' if model == 'text-embedding-3-small' else 'fixture'
            self.assertEqual(call_budget.reserve_micro_usd(prompt, model, 100, {}),
                             original.reserve_micro_usd(prompt, model, 100, {}))
            self.assertEqual(call_budget.usage_micro_usd(result(model=model), model),
                             original.usage_micro_usd(result(model=model), model))

    def test_local_ledger_reserves_before_call_and_settles_flex(self):
        budget = call_budget.CallBudget(':memory:', 1)
        self.addCleanup(budget.close)
        def api(*args, **kwargs):
            row = budget.db.execute('SELECT reserved_usd, actual_usd, state FROM call_reservations').fetchone()
            self.assertGreater(row[0], .002670)
            self.assertEqual(row[1:], (None, 'reserved'))
            return result('flex')
        budget.wrap(api, {})('fixture', 'gpt-6.1-sol', max_tokens=100)
        actual, state = budget.db.execute('SELECT actual_usd, state FROM call_reservations').fetchone()
        self.assertEqual(actual, .001335)
        self.assertEqual(state, 'known')

    def test_local_ledger_unknown_tier_keeps_reservation(self):
        budget = call_budget.CallBudget(':memory:', 1)
        self.addCleanup(budget.close)
        budget.wrap(lambda *a, **k: result('priority'), {})('fixture', 'gpt-6.1-sol', max_tokens=100)
        reserved, actual, state = budget.db.execute('SELECT reserved_usd, actual_usd, state FROM call_reservations').fetchone()
        self.assertIsNone(actual)
        self.assertEqual(state, 'usage_unknown')
        self.assertEqual(budget.total(), reserved)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.job = {'id': 'synthetic-job', 'lease_token': 'synthetic-lease',
                    'pipeline': 'synthetic-pipeline', 'expected_revision': 1}

    def test_request_identity_matches_original_and_is_mode_independent(self):
        source = ROOT.parents[2] / 'sol-operational-release-20261006/backend/durable_calls.py'
        spec = importlib.util.spec_from_file_location('original_durable_calls', source)
        original = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(original)
        requests = []
        for cls, mode in ((original.DurableCalls, 'default'), (DurableCalls, 'default'), (DurableCalls, 'flex_fallback')):
            store = Ledger(encode(result('flex')))
            api = Mock(side_effect=AssertionError('Paid response must be reused'))
            with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': mode}):
                cls(store, self.job, api, {}, ROOT/'unused-outbox')('fixture', 'gpt-6.1-sol', 100)
            api.assert_not_called()
            requests.append(store.requests[0]['request_json'])
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(requests[1], requests[2])

    def test_fallback_receipt_reused_without_paid_resend(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = Ledger()
            value = dict(result(), requested_service_tier='default', flex_attempts=3)
            api = Mock(return_value=value)
            with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': 'flex_fallback'}):
                DurableCalls(store, self.job, api, {}, directory, prior_calls=[])('fixture', 'gpt-6.1-sol', 100)
            prior = [{'index': 0, 'request_hash': sha(store.requests[0]['request_json'])}]
            with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': 'default'}):
                second = DurableCalls(store, self.job, api, {}, directory, prior_calls=prior, start_index=7)
                self.assertEqual(second('fixture', 'gpt-6.1-sol', 100), value)
            self.assertEqual(api.call_count, 1)
            self.assertEqual(store.requests[0]['request_json'], store.requests[1]['request_json'])
            self.assertEqual(store.receipts[0]['actual_micro_usd'], 2670)
            self.assertEqual(second.index, 7)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_durable_receipt_settles_flex_tariff(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = Ledger()
            DurableCalls(store, self.job, Mock(return_value=result('flex')), {}, directory)('fixture', 'gpt-6.1-sol', 100)
            self.assertEqual(store.receipts[0]['actual_micro_usd'], 1335)

    def test_question_identity_is_mode_independent(self):
        requests = []
        for mode in ('default', 'flex_fallback'):
            store = Ledger(encode(result('flex')))
            api = Mock(side_effect=AssertionError('No paid resend'))
            with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': mode}):
                QuestionCalls(store, question_id='fixture', actor_id='fixture', api=api,
                              outbox=ROOT/'unused-outbox', budget_micro_usd=100000)('fixture', 'gpt-6.1-sol', 100, {})
            requests.append(store.requests[0]['request_json'])
            api.assert_not_called()
        self.assertEqual(*requests)

    def test_pipeline_version_mode_independent_with_missing_asset_simulated(self):
        # Source release omits source-corrections.json. Do not invent deployment data.
        # Simulate only that missing asset; version source reads otherwise stay real.
        read_text = Path.read_text
        def read(path, *a, **k):
            return '{}' if path.name == 'source-corrections.json' else read_text(path, *a, **k)
        with patch.object(Path, 'read_text', read):
            for compact in (False, True):
                with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': 'default'}):
                    standard = hybrid_pipeline.version('gpt-6.1-sol', compact=compact)
                with patch.dict(os.environ, {'DASHBOARD_SERVICE_TIER': 'flex_fallback'}):
                    self.assertEqual(standard, hybrid_pipeline.version('gpt-6.1-sol', compact=compact))


if __name__ == '__main__':
    unittest.main()
