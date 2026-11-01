"""Synthetic tests: exact actions, positive endform proof and a control-based gate."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import tempfile
from contextlib import redirect_stdout
from io import StringIO

spec = importlib.util.spec_from_file_location('compare_filtered_test_module', Path(__file__).with_name('compare_filtered.py'))
compare = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = compare
spec.loader.exec_module(compare)


def schema(indices):
    observation = {'type': 'object', 'required': ['source_index', 'update_target', 'update', 'kind'],
        'properties': {'source_index': {'type': 'integer'}, 'update_target': {'type': ['null', 'string']},
                       'update': {'type': 'boolean'}, 'kind': {'type': 'string'}}}
    return {'type': 'object', 'required': ['observations', 'work_results', 'open_ids'],
        'properties': {'observations': {'type': 'array', 'items': observation},
            'work_results': {'type': 'object', 'additionalProperties': False, 'required': indices,
                'properties': {i: {'anyOf': [{'type': 'string', 'enum': ['unchanged']},
                    {'type': 'object', 'required': ['action'], 'properties': {'action': {'type': 'string'}}}]} for i in indices}},
            'open_ids': {'type': 'array'}}}


def output(action='close', target='W1', n=1):
    return {'observations': [{'source_index': i, 'update_target': target, 'update': True, 'kind': 'task'} for i in range(n)],
            'work_results': {'7': {'action': action}, '11': 'unchanged'}, 'open_ids': []}


def fixture(n=1):
    ref = output(n=n)
    original_schema = schema(['7', '11'])
    requests, results = [], []
    for i in range(4):
        control = i > 0
        request = {'replay_id': str(i), 'replay_variant': 'control' if control else 'filtered',
            'request_json': {'schema': original_schema}, 'original_request_json': {'schema': original_schema},
            'reference_text': json.dumps(ref), 'reference_micro_usd': 100,
            'filter_metadata': {'alias_work_indices': {'W1': '7', 'W2': '11'},
                                'kept_aliases': ['W1', 'W2'], 'removed_aliases': []}}
        result = {'replay_id': str(i), 'status': 'ok', 'response': {'status': 'completed'},
                  'text': json.dumps(ref), 'actual_micro_usd': 80, 'usage': {'input_tokens': 1, 'output_tokens': 1}}
        requests.append(request)
        results.append(result)
    return requests, results


class FilteredComparisonTests(unittest.TestCase):
    def test_multiple_result_files_and_repeated_option(self):
        requests,results=fixture()
        root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(dir=root) as temp:
            paths=[Path(temp)/name for name in ('requests.jsonl','run1.jsonl','run2.jsonl')]
            for path,rows in zip(paths,(requests,results[:1],results[1:])):
                path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            merged=compare.merged_results(paths[1:])
            self.assertEqual(len(merged),4)
            self.assertEqual(compare.compare_records(requests,merged)['passed'],1)
            for args in (['--results',str(paths[1]),str(paths[2])],
                         ['--results',str(paths[1]),'--results',str(paths[2])]):
                captured=StringIO()
                with redirect_stdout(captured):status=compare.main(['--requests',str(paths[0])]+args)
                self.assertEqual(status,0)
                self.assertEqual(json.loads(captured.getvalue())['total']['attempts'],4)

    def test_result_merge_identical_duplicate_once_conflict_rejected(self):
        _,results=fixture()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            a=Path(temp)/'a.jsonl';b=Path(temp)/'b.jsonl'
            a.write_text(json.dumps(results[0])+'\n');b.write_text(a.read_text())
            self.assertEqual(len(compare.merged_results([a,b,a])),1)
            other=dict(results[0],actual_micro_usd=81)
            b.write_text(json.dumps(other)+'\n')
            with self.assertRaises(ValueError):compare.merged_results([a,b])

    def test_historical_unknown_cost_derived_only_with_confirmed_usage(self):
        usage={'input_tokens':36808,'input_tokens_details':{'cached_tokens':0,'cache_write_tokens':36805},
               'output_tokens':3152,'output_tokens_details':{'reasoning_tokens':379}}
        result={'replay_id':'synthetic','actual_micro_usd':None,'model':'gpt-6.1-sol','usage':usage,
            'response':{'status':'completed','service_tier':'default','model':'gpt-6.1-sol','usage':usage}}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            path=Path(temp)/'run1.jsonl';raw=json.dumps(result)+'\n';path.write_text(raw)
            self.assertEqual(compare.merged_results([path])[0]['actual_micro_usd'],123539)
            self.assertEqual(path.read_text(),raw)
            for change in ({'service_tier':'flex'},{'usage':{}},{'status':'incomplete'}):
                bad=copy.deepcopy(result);bad['response'].update(change)
                path.write_text(json.dumps(bad)+'\n')
                self.assertIsNone(compare.merged_results([path])[0]['actual_micro_usd'])

    def test_bool_numeric_evidence_is_conflicting_in_either_order(self):
        _,results=fixture();good=copy.deepcopy(results[0])
        good['usage']['input_tokens_details']={'cached_tokens':0}
        bad=copy.deepcopy(good);bad['usage']['input_tokens_details']['cached_tokens']=False
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            a=Path(temp)/'a.jsonl';b=Path(temp)/'b.jsonl'
            a.write_text(json.dumps(good)+'\n');b.write_text(json.dumps(bad)+'\n')
            for paths in ([a,b],[b,a]):
                with self.assertRaises(ValueError):compare.merged_results(paths)

    def test_historical_cost_requires_type_identical_final_usage(self):
        usage={'input_tokens':10,'output_tokens':1,'input_tokens_details':{'cached_tokens':0}}
        result={'replay_id':'synthetic','actual_micro_usd':None,'model':'gpt-6.1-sol','usage':usage,
            'response':{'status':'completed','service_tier':'default','model':'gpt-6.1-sol','usage':copy.deepcopy(usage)}}
        result['response']['usage']['input_tokens_details']['cached_tokens']=False
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            path=Path(temp)/'result.jsonl';path.write_text(json.dumps(result)+'\n')
            self.assertIsNone(compare.merged_results([path])[0]['actual_micro_usd'])

    def test_exact_match_and_numeric_privacy(self):
        requests, results = fixture()
        report = compare.compare_records(requests, results)
        self.assertEqual(report['passed'], 1)
        self.assertEqual(report['filtered']['recall_hits'], 1)
        self.assertEqual(report['filtered']['cost_delta_micro_usd'], -20)
        def numeric_leaves(value):
            if isinstance(value, dict):
                for item in value.values(): numeric_leaves(item)
            elif isinstance(value, list):
                for item in value: numeric_leaves(item)
            else: self.assertTrue(value is None or type(value) in (int, float))
        numeric_leaves(report)
        self.assertNotIn('W1', json.dumps(report))

    def test_wrong_action_is_not_recall(self):
        requests, results = fixture()
        candidate = output(action='reopen')
        results[0]['text'] = json.dumps(candidate)
        report = compare.compare_records(requests, results)
        self.assertEqual(report['filtered']['recall_hits'], 0)
        self.assertEqual(report['filtered']['additional_flags'], 1)
        self.assertEqual(report['passed'], 0)

    def test_filter_loss_cannot_hide_behind_retained_recall(self):
        requests, results = fixture()
        requests[0]['filter_metadata'].update(kept_aliases=['W2'], removed_aliases=['W1'])
        requests[0]['request_json'] = {'schema': schema(['11'])}
        candidate = output(target=None)
        del candidate['work_results']['7']
        results[0]['text'] = json.dumps(candidate)
        report = compare.compare_records(requests, results)
        self.assertEqual(report['filtered']['recall_total'], 0)
        self.assertEqual(report['filtered']['filter_loss'], 1)
        self.assertEqual(report['filtered']['lifecycle_filter_loss'], 1)
        self.assertEqual(report['filtered']['observation_filter_loss'], 1)
        self.assertEqual(report['filter_loss_pass'], 0)
        self.assertEqual(report['passed'], 0)

    def test_additional_flag(self):
        requests, results = fixture()
        candidate = output()
        candidate['work_results']['11'] = {'action': 'close'}
        results[0]['text'] = json.dumps(candidate)
        report = compare.compare_records(requests, results)
        self.assertEqual(report['filtered']['additional_flags'], 1)
        self.assertEqual(report['filtered']['recall_hits'], 1)

    def test_two_percentage_points_and_control_noise(self):
        requests, results = fixture(n=100)
        candidate = output(n=100)
        for obs in candidate['observations'][:2]: obs['update_target'] = None
        results[0]['text'] = json.dumps(candidate)
        self.assertEqual(compare.compare_records(requests, results)['passed'], 1)
        candidate['observations'][2]['update_target'] = None
        results[0]['text'] = json.dumps(candidate)
        self.assertEqual(compare.compare_records(requests, results)['passed'], 0)
        for item in results[1:]: item['text'] = json.dumps(candidate)
        self.assertEqual(compare.compare_records(requests, results)['passed'], 1)

    def test_missing_controls_is_unknown(self):
        requests, results = fixture()
        report = compare.compare_records(requests[:1], results[:1])
        self.assertEqual(report['evidence_known'], 0)
        self.assertEqual(report['passed'], 0)

    def test_missing_observation_open_ids_and_work_index(self):
        for mutation in ('observations', 'open_ids', 'work_results'):
            with self.subTest(mutation=mutation):
                requests, results = fixture()
                candidate = output()
                if mutation == 'observations': candidate[mutation] = []
                elif mutation == 'open_ids': candidate[mutation] = ['synthetic']
                else: candidate[mutation] = {'0': {'action': 'close'}, '11': 'unchanged'}
                results[0]['text'] = json.dumps(candidate)
                report = compare.compare_records(requests, results)
                self.assertEqual(report['passed'], 0)
                self.assertEqual(report['calls'][0]['endform_ok'], 0)

    def test_malformed_schema_reference_result(self):
        for mutation in ('schema', 'reference', 'text', 'response'):
            with self.subTest(mutation=mutation):
                requests, results = fixture()
                if mutation == 'schema': requests[0]['original_request_json']['schema'] = {'unsupported': 1}
                elif mutation == 'reference': requests[0]['reference_text'] = '{}'
                elif mutation == 'text': results[0]['text'] = 'not json'
                else: results[0]['response']['status'] = 'incomplete'
                report = compare.compare_records(requests, results)
                self.assertEqual(report['passed'], 0)
                self.assertEqual(report['evidence_known'], 0)

    def test_costs_include_duplicates_orphans_and_unknown(self):
        requests, results = fixture()
        duplicate = copy.deepcopy(results[0])
        orphan = copy.deepcopy(results[0]); orphan['replay_id'] = 'orphan'; orphan['actual_micro_usd'] = 7
        report = compare.compare_records(requests, results + [duplicate, orphan])
        self.assertEqual(report['total']['actual_micro_usd'], 407)
        self.assertEqual(report['passed'], 0)
        orphan['actual_micro_usd'] = None
        report = compare.compare_records(requests, results + [orphan])
        self.assertIsNone(report['total']['actual_micro_usd'])
        self.assertEqual(report['total']['cost_unknown_attempts'], 1)

    def test_unknown_cost_separates_quality_from_complete_acceptance(self):
        requests, results = fixture()
        results[0]['actual_micro_usd'] = None
        report = compare.compare_records(requests, results)
        self.assertEqual(report['quality_pass'], 1)
        self.assertEqual(report['cost_complete'], 0)
        self.assertEqual(report['passed'], 0)
        self.assertIsNone(report['filtered']['actual_micro_usd'])
        requests, results = fixture()
        requests[0]['reference_micro_usd'] = None
        report = compare.compare_records(requests, results)
        self.assertEqual(report['quality_pass'], 1)
        self.assertEqual(report['cost_complete'], 0)
        self.assertEqual(report['passed'], 0)

    def test_gate_fields_literal_and_missing_result(self):
        requests, results = fixture()
        candidate = output(); candidate['observations'][0].update(update=False, kind='risk')
        results[0]['text'] = json.dumps(candidate)
        report = compare.compare_records(requests, results)
        self.assertEqual(report['filtered']['update_matches'], 0)
        self.assertEqual(report['filtered']['kind_matches'], 0)
        report = compare.compare_records(requests, results[1:])
        self.assertEqual(report['passed'], 0)
        self.assertIsNone(report['filtered']['recall_hits'])


if __name__ == '__main__':
    unittest.main()
