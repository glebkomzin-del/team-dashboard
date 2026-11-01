"""Offline v2 representation gates; no provider or meeting data."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'overlay') not in sys.path:
    sys.path.insert(0, str(ROOT / 'overlay'))
from delta_codec import equal, to_delta, from_delta
from hybrid_schema import delta_schema


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.obs = [{'title': 'synthetic', 'matter_id': 'M0', 'update_target': 'W0', 'update': 'none', 'evidence_ids': []}]
        self.work = [{'work_index': '0'}, {'work_index': '1'}]
        self.full = {'open_ids': [], 'coverage_notes': [], 'observations': [dict(self.obs[0], source_index=0, matter_id=None, update_target=None)],
                     'work_results': {'0': 'unchanged', '1': {'action': 'progress'}}}
        self.delta = to_delta(self.full, self.obs, self.work)

    def test_exact_roundtrip(self):
        self.assertTrue(equal(self.full, from_delta(self.delta, self.obs, self.work)))

    def test_decision_is_explicit_even_unchanged(self):
        self.assertEqual(set(self.delta['observations'][0]['decision']), {'matter_id', 'update_target', 'update'})
        self.assertIsNone(from_delta(self.delta, self.obs, self.work)['observations'][0]['matter_id'])

    def test_decision_missing_rejected(self):
        del self.delta['observations'][0]['decision']['matter_id']
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_decision_fields_not_in_changes(self):
        self.delta['observations'][0]['changes'].append({'matter_id': 'M1'})
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_missing_observation_rejected(self):
        self.delta['observations'] = []
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_duplicate_observation_rejected(self):
        self.delta['observations'] *= 2
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_unknown_observation_rejected(self):
        self.delta['observations'][0]['source_index'] = 9
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_missing_unchanged_list_rejected(self):
        del self.delta['unchanged_work_indices']
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_missing_slot_rejected(self):
        self.delta['unchanged_work_indices'] = []
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_overlapping_slot_rejected(self):
        self.delta['unchanged_work_indices'].append('1')
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_duplicate_unchanged_rejected(self):
        self.delta['unchanged_work_indices'] *= 2
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_duplicate_work_result_rejected(self):
        self.delta['work_results'] *= 2
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_unknown_slot_rejected(self):
        self.delta['unchanged_work_indices'] = ['99']
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_no_implicit_unchanged(self):
        self.delta['work_results'] = []
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_expansion_roundtrip(self):
        full = {'open_ids': ['H0'], 'observations': [], 'work_results': None, 'coverage_notes': []}
        self.assertTrue(equal(full, from_delta(to_delta(full, self.obs, self.work), self.obs, self.work)))

    def test_archived_expansion_empty_projection_roundtrip(self):
        full = {'open_ids': ['H0'], 'observations': [], 'work_results': {}, 'coverage_notes': []}
        self.assertTrue(equal(full, from_delta(to_delta(full, self.obs, self.work, archive=True), self.obs, self.work, archive=True)))

    def test_archive_marker_rejected_live(self):
        full = {'open_ids': ['H0'], 'observations': [], 'work_results': {}}
        archived = to_delta(full, self.obs, self.work, archive=True)
        with self.assertRaises(ValueError): from_delta(archived, self.obs, self.work)
        with self.assertRaises(ValueError): to_delta(full, self.obs, self.work)

    def test_expansion_partial_rejected(self):
        self.delta['open_ids'] = ['H0']
        with self.assertRaises(ValueError): from_delta(self.delta, self.obs, self.work)

    def test_empty_final(self):
        full = {'open_ids': [], 'observations': [], 'work_results': {}}
        self.assertTrue(equal(full, from_delta(to_delta(full, [], []), [], [])))

    def test_null_and_array_changes(self):
        self.full['observations'][0].update(title=None, evidence_ids=['U0'])
        self.assertTrue(equal(self.full, from_delta(to_delta(self.full, self.obs, self.work), self.obs, self.work)))

    def test_type_strict_equality(self):
        self.assertFalse(equal({'x': 1}, {'x': True}))

    def test_schema_decision_and_coverage(self):
        fields = {'source_index': {'type':'integer','enum':[0]}, 'update_target': {'type':['string','null']}, 'update':{'type':'string'}, 'matter_id':{'type':['string','null']}, 'title':{'type':'string'}}
        full = {'properties': {'observations':{'items':{'properties':fields}}, 'work_results':{'anyOf':[{'properties':{'0':{},'1':{}}}, {'type':'null'}]}}, 'required':['observations','work_results'], '$defs':{'lifecycle_result':{'anyOf':[{}, {'type':'object','properties':{'action':{'type':'string'}}}]}}}
        original = copy.deepcopy(full)
        result = delta_schema(full)
        self.assertEqual(full, original)
        patch = result['properties']['observations']['items']
        self.assertEqual(patch['required'], ['source_index','decision','changes'])
        self.assertEqual(set(patch['properties']['decision']['required']), {'update_target','update','matter_id'})
        self.assertEqual(len(patch['properties']['changes']['items']['anyOf']), 1)
        self.assertIn('unchanged_work_indices', result['required'])

if __name__ == '__main__': unittest.main()
