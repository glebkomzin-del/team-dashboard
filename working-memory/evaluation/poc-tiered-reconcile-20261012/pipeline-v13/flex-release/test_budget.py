"""Offline cost/reservation checks, only synthetic data and in-memory SQLite.

Question: does actual tier determine cost while reservation stays Standard?
Passing permits local accounting acceptance; failures block accounting acceptance.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRODUCTION = Path('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/prod')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


budget = load('release_budget_test', ROOT / 'call_budget.py')
production = load('production_budget_test', PRODUCTION / 'call_budget.py')
MODEL = 'gpt-6.1-sol'


def response(tier='flex', tokens=100, output=10, cached=20, written=30):
    return {'returned_service_tier': tier, 'usage_final': True, 'usage': {
        'input_tokens': tokens, 'output_tokens': output,
        'input_tokens_details': {'cached_tokens': cached, 'cache_write_tokens': written}}}


class BudgetTests(unittest.TestCase):
    def test_actual_flex_standard_cache_writes_and_ceiling(self):
        self.assertEqual(budget.usage_micro_usd(response(), MODEL), 139)
        self.assertEqual(budget.usage_micro_usd(response('default'), MODEL), 277)
        self.assertEqual(budget.usage_micro_usd(response(tokens=1, output=0, cached=1, written=0), MODEL), 1)
        self.assertEqual(budget.usage_micro_usd(response(tokens=1, output=0, cached=0, written=1), MODEL), 2)
        self.assertEqual(budget.usage_micro_usd(response(tokens=300000, output=10, cached=0, written=0), MODEL), 600075)

    def test_unknown_actual_tier_and_usage(self):
        for tier in [None, '', 'auto', 'priority', 'FLEX']:
            self.assertIsNone(budget.usage_micro_usd(response(tier), MODEL))
        for field, value in [('usage_final', False), ('usage', None)]:
            result = response(); result[field] = value
            self.assertIsNone(budget.usage_micro_usd(result, MODEL))
        for changed in [{'cached_tokens':101}, {'cache_write_tokens': True}, {'cache_write_tokens': -1}]:
            result = response(); result['usage']['input_tokens_details'].update(changed)
            self.assertIsNone(budget.usage_micro_usd(result, MODEL))

    def test_standard_reservations_other_models_unchanged(self):
        for model in budget.RATES:
            prompt = '["synthetic"]' if model == 'text-embedding-3-small' else 'synthetic'
            for counted in ([None, 300000] if model in ('gpt-6.1-sol','gpt-5.6-terra','gpt-5.6-luna') else [None]):
                expected = production.reserve_micro_usd(prompt, model, 10, {}, counted_input_tokens=counted)
                self.assertEqual(budget.reserve_micro_usd(prompt, model, 10, {}, counted_input_tokens=counted), expected)
                self.assertIs(type(expected), int)
            if model != MODEL:
                self.assertEqual(budget.usage_micro_usd(response(), model), production.usage_micro_usd(response(), model))
        self.assertEqual(budget.reserve_micro_usd('synthetic', MODEL, 10, {}, counted_input_tokens=1), 11377)

    def test_reservation_exists_before_call_and_unknown_keeps_it(self):
        store = budget.CallBudget(':memory:', 1)
        try:
            observed = []
            def api(*args, **kwargs):
                observed.append(store.db.execute('SELECT state,reserved_usd,actual_usd FROM call_reservations').fetchone())
                return {'error': 'HTTP 500', 'usage_final': False, 'returned_service_tier': None}
            store.wrap(api, {})('synthetic', MODEL, 10)
            self.assertEqual(observed[0][0], 'reserved')
            self.assertIsNone(observed[0][2])
            after = store.db.execute('SELECT state,reserved_usd,actual_usd FROM call_reservations').fetchone()
            self.assertEqual(after[0], 'usage_unknown')
            self.assertEqual(store.total(), observed[0][1])
            self.assertIsNone(after[2])
        finally:
            store.close()

    def test_known_actual_and_insufficient_budget(self):
        store = budget.CallBudget(':memory:', 1)
        try:
            store.wrap(lambda *a, **k: response(), {})('synthetic', MODEL, 10)
            self.assertEqual(store.total(), 139 / 1000000)
        finally:
            store.close()
        store = budget.CallBudget(':memory:', 0.000001)
        try:
            called = []
            with self.assertRaises(budget.BudgetExceeded):
                store.wrap(lambda *a, **k: called.append(1), {})('synthetic', MODEL, 10)
            self.assertFalse(called)
            self.assertEqual(store.total(), 0)
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
