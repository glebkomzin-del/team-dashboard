"""Synthetic offline checks; fixtures use aliases, never meeting contents.

Question: can invalid/missing evidence or lexical class changes falsely pass?
Criterion: complete positive baselines pass; each countercase blocks and retains
its expected denominator. Scope: stdlib unit and CLI, no providers/production.
Failure means comparison is not ready for a paid replay decision.
"""
import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('compare_stage', ROOT / 'compare_stage.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

OBSERVATION = {'type': 'object', 'properties': {
    'kind': {'type': 'string', 'enum': ['commitment', 'fact', 'decision']},
    'commitment_strength': {'type': 'string', 'enum': ['explicit', 'not_applicable']},
    'title': {'type': 'string'}, 'claim': {'type': 'string'},
    'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
    'state_evidence_ids': {'type': 'array', 'items': {'type': 'string'}}},
    'required': ['kind', 'commitment_strength', 'title', 'claim', 'evidence_ids', 'state_evidence_ids']}
EXTRACT_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'properties': {'observations': {'type': 'array', 'items': OBSERVATION},
        'meeting_summary': {'type': 'array', 'items': {'type': 'object',
            'properties': {'text': {'type': 'string'}, 'evidence_ids': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['text', 'evidence_ids']}}},
    'required': ['observations', 'meeting_summary']}
GATE_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'properties': {'verdicts': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False, 'properties': {
            'index': {'type': 'integer'},
            'verdict': {'type': 'string', 'enum': ['supported', 'unsupported', 'ambiguous', 'already_done', 'duplicate']},
            'reason': {'type': 'string'},
            'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
            'duplicate_of': {'type': ['integer', 'null']},
            'due_role': {'type': 'string', 'enum': ['work_deadline', 'event_time', 'data_reference', 'unclear', 'none']},
            'action_uncertainty': {'type': ['string', 'null']}},
        'required': ['index', 'verdict', 'reason', 'evidence_ids', 'duplicate_of', 'due_role', 'action_uncertainty']}}},
    'required': ['verdicts']}


def observation(label='alias alpha', kind='commitment', ids=None):
    return {'kind': kind, 'commitment_strength': 'explicit' if kind == 'commitment' else 'not_applicable',
            'title': label, 'claim': label, 'evidence_ids': ['E0'] if ids is None else ids,
            'state_evidence_ids': []}


def extraction(observations=None, summary='alias summary'):
    return {'observations': [observation()] if observations is None else observations,
            'meeting_summary': [{'text': summary, 'evidence_ids': ['E0']}]}


def verdict(index=0, value='supported'):
    return {'index': index, 'verdict': value, 'reason': 'alias reason', 'evidence_ids': ['E0'],
            'duplicate_of': None, 'due_role': 'none',
            'action_uncertainty': 'alias uncertainty' if value == 'ambiguous' else None}


def request(stage, value, prompt=None, call=None):
    if prompt is None:
        prompt = ('Kandidaten:\n' + json.dumps([{'index': v['index']} for v in value['verdicts']]) +
                  '\nBestehende Arbeit:\n[]') if stage == 'gate' else 'alias prompt'
    return {'job_id': 'J0', 'call_index': (0 if stage == 'extract' else 1) if call is None else call,
            'stage': stage, 'request_json': {'model': c.SOL, 'schema': EXTRACT_SCHEMA if stage == 'extract' else GATE_SCHEMA,
            'prompt': prompt}, 'reference_text': json.dumps(value), 'reference_model': c.SOL,
            'reference_stop_reason': 'end_turn'}


def result(req, value=None):
    return {k: req[k] for k in ('job_id', 'call_index', 'stage')} | {
            'model': c.LUNA, 'status': 'ok', 'text': req['reference_text'] if value is None else json.dumps(value)}


def fixtures():
    requests = [request('extract', extraction()), request('gate', {'verdicts': [verdict()]})]
    return requests, [result(r) for r in requests]


class CompareTests(unittest.TestCase):
    def test_positive_complete(self):
        requests, results = fixtures()
        report = c.compare(requests, results)
        self.assertTrue(report['passed'])
        self.assertEqual(report['metrics']['commitment_recall'], 1)
        self.assertEqual(report['metrics']['gate_agreement'], 1)
        self.assertEqual(report['metrics']['extract_schema_valid_rate'], 1)

    def test_class_changed_presence_not_recall(self):
        requests, results = fixtures()
        results[0]['text'] = json.dumps(extraction([observation(kind='fact')]))
        report = c.compare(requests, results)
        self.assertFalse(report['passed'])
        self.assertEqual(report['metrics']['commitment_presence_rate'], 1)
        self.assertEqual(report['metrics']['commitment_recall'], 0)
        self.assertEqual(report['counts']['kind_agreement'], 0)
        self.assertEqual(report['counts']['strength_agreement'], 0)

    def test_missing_verdict_retains_denominator_and_loss(self):
        requests, results = fixtures()
        requests[1] = request('gate', {'verdicts': [verdict(0), verdict(1)]})
        results[1] = result(requests[1], {'verdicts': [verdict(0)]})
        report = c.compare(requests, results)
        self.assertFalse(report['passed'])
        self.assertEqual(report['counts']['gate_candidates'], 2)
        self.assertEqual(report['metrics']['gate_agreement'], .5)
        self.assertEqual(report['counts']['sol_supported_luna_different'], 1)
        self.assertIn('invalid_luna_gate_coverage', report['blockers'])

    def test_candidate_verdicts_exact_loss_reverse_missing(self):
        requests, results = fixtures()
        requests[1] = request('gate', {'verdicts': [verdict(3), verdict(1),
                                                   verdict(2, 'unsupported'), verdict(0)]})
        results[1] = result(requests[1], {'verdicts': [verdict(2), verdict(0),
                                                    verdict(1, 'unsupported')]})
        report = c.compare(requests, results)
        row = next(row for row in report['rows'] if row['stage'] == 'gate')
        candidates = row['candidate_verdicts']
        self.assertEqual([v['index'] for v in candidates], [0, 1, 2, 3])
        self.assertEqual(candidates, [
            {'index': 0, 'sol_verdict': 'supported', 'luna_verdict': 'supported',
             'same_verdict': True, 'sol_supported_luna_different': False,
             'luna_supported_sol_different': False},
            {'index': 1, 'sol_verdict': 'supported', 'luna_verdict': 'unsupported',
             'same_verdict': False, 'sol_supported_luna_different': True,
             'luna_supported_sol_different': False},
            {'index': 2, 'sol_verdict': 'unsupported', 'luna_verdict': 'supported',
             'same_verdict': False, 'sol_supported_luna_different': False,
             'luna_supported_sol_different': True},
            {'index': 3, 'sol_verdict': 'supported', 'luna_verdict': None,
             'same_verdict': False, 'sol_supported_luna_different': True,
             'luna_supported_sol_different': False}])
        self.assertEqual(row['gate_candidates'], 4)
        self.assertEqual(row['sol_supported_luna_different'], 2)
        self.assertEqual(row['luna_supported_sol_different'], 1)
        self.assertFalse(report['passed'])

    def test_duplicate_verdict_is_not_arbitrary_winner(self):
        requests, results = fixtures()
        results[1]['text'] = json.dumps({'verdicts': [verdict(), verdict()]})
        report = c.compare(requests, results)
        self.assertFalse(report['passed'])
        self.assertEqual(report['counts']['gate_exact_agreement'], 0)
        self.assertEqual(report['counts']['sol_supported_luna_different'], 1)

    def test_losses_limit_and_reverse(self):
        requests, results = fixtures()
        baseline = {'verdicts': [verdict(i) for i in range(3)] + [verdict(3, 'unsupported')]}
        requests[1] = request('gate', baseline)
        results[1] = result(requests[1], {'verdicts': [verdict(i, 'unsupported') for i in range(3)] + [verdict(3)]})
        report = c.compare(requests, results, gate_agreement=0)
        self.assertEqual(report['counts']['sol_supported_luna_different'], 3)
        self.assertEqual(report['counts']['luna_supported_sol_different'], 1)
        self.assertIn('gate_losses_above_limit', report['blockers'])

    def test_one_loss_boundary_does_not_overwrite_agreement(self):
        requests, results = fixtures()
        requests[1] = request('gate', {'verdicts': [verdict(i) for i in range(20)]})
        results[1] = result(requests[1], {'verdicts': [verdict(i, 'unsupported' if i == 0 else 'supported') for i in range(20)]})
        report = c.compare(requests, results)
        self.assertTrue(report['passed'])
        self.assertEqual(report['metrics']['gate_agreement'], .95)
        self.assertEqual(report['counts']['sol_supported_luna_different'], 1)

    def test_missing_execution_does_not_subset(self):
        requests, results = fixtures()
        report = c.compare(requests, results[:1])
        self.assertFalse(report['passed'])
        self.assertEqual(report['counts']['gate_candidates'], 1)
        self.assertEqual(report['counts']['missing_executions'], 1)
        self.assertEqual(report['counts']['sol_supported_luna_different'], 1)

    def test_empty_results_and_zero_commitments_unknown(self):
        requests, results = fixtures()
        self.assertFalse(c.compare(requests, [])['passed'])
        requests[0] = request('extract', extraction([observation(kind='fact')]))
        results[0] = result(requests[0])
        report = c.compare(requests, results)
        self.assertIsNone(report['metrics']['commitment_recall'])
        self.assertFalse(report['passed'])

    def test_malformed_reference_blocks_even_good_luna(self):
        requests, results = fixtures()
        requests[0]['reference_text'] = '{alias malformed'
        report = c.compare(requests, results)
        self.assertFalse(report['passed'])
        self.assertIn('reference_invalid_json', report['blockers'])

    def test_malformed_luna_and_schema_are_invalid(self):
        for text in ('{alias malformed', '{"observations": [], "meeting_summary": "alias"}',
                     '{"observations": [], "observations": [], "meeting_summary": []}'):
            requests, results = fixtures()
            results[0]['text'] = text
            report = c.compare(requests, results)
            self.assertFalse(report['passed'])
            self.assertEqual(report['metrics']['extract_schema_valid_rate'], 0)

    def test_invalid_sol_gate_coverage_blocks(self):
        requests, results = fixtures()
        requests[1]['request_json']['prompt'] = 'Kandidaten:\n[{"index":0},{"index":1}]'
        report = c.compare(requests, results)
        self.assertFalse(report['passed'])
        self.assertEqual(report['counts']['gate_candidates'], 2)
        self.assertIn('invalid_reference_gate_coverage', report['blockers'])

    def test_gate_reference_fallback_and_invalid_candidates(self):
        requests, results = fixtures()
        requests[1]['request_json']['prompt'] = 'alias no candidates'
        self.assertTrue(c.compare(requests, results)['passed'])
        for prompt in ('Kandidaten:\n{alias malformed}', 'Kandidaten:\n[{"index":0},{"index":0}]'):
            requests[1]['request_json']['prompt'] = prompt
            report = c.compare(requests, results)
            self.assertFalse(report['passed'])
            self.assertIsNone(report['metrics']['gate_agreement'])

    def test_source_shared_does_not_match_unrelated_claims(self):
        left = observation('alpha alpha alpha')
        right = observation('omega omega omega')
        self.assertEqual(c.match_observations([left], [right]), [])

    def test_source_span_and_no_source_quote_fallback(self):
        left, right = observation(ids=[]), observation(ids=[])
        left['source_spans'] = [{'start': 10, 'end': 20, 'quote': 'alias quote'}]
        right['source_spans'] = [{'start': 15, 'end': 25, 'quote': 'alias quote'}]
        self.assertEqual(c.match_observations([left], [right]), [(0, 0)])
        left, right = observation(ids=[]), observation(ids=[])
        left['quotes'] = right['quotes'] = ['alias quote']
        self.assertEqual(c.match_observations([left], [right]), [(0, 0)])

    def test_text_fallback_and_conflicting_source_not_match(self):
        left, right = observation(ids=[]), observation(ids=[])
        self.assertEqual(c.match_observations([left], [right]), [(0, 0)])
        left['evidence_ids'], right['evidence_ids'] = ['E0'], ['E1']
        self.assertEqual(c.match_observations([left], [right]), [])

    def test_maximum_cardinality_not_greedy(self):
        # Sol0 can match either Luna; Sol1 only Luna0.
        scores = {(0, 0): 2, (0, 1): 1, (1, 0): 1}
        with patch.object(c, 'match_score', side_effect=lambda a, b, t: scores.get((a, b))):
            self.assertEqual(c.match_observations([0, 1], [0, 1]), [(0, 1), (1, 0)])

    def test_additions_summary_lengths_and_empty_summary(self):
        requests, results = fixtures()
        results[0] = result(requests[0], extraction([observation(), observation('omega omega', ids=['E1'])], 'alias summaryalias summary'))
        report = c.compare(requests, results)
        self.assertTrue(report['passed'])
        self.assertEqual(report['counts']['additional_luna_observations'], 1)
        self.assertEqual(report['metrics']['summary_length_ratio'], 2)
        results[0]['text'] = json.dumps(extraction(summary=''))
        self.assertFalse(c.compare(requests, results)['passed'])

    def test_identity_models_and_completion_reject(self):
        requests, results = fixtures()
        for duplicate in (True, False):
            with self.assertRaises(ValueError):
                c.compare(requests + [requests[0]] if duplicate else requests,
                          results if duplicate else results + [results[0]])
        results[0]['model'] = c.SOL
        with self.assertRaises(ValueError):
            c.compare(requests, results)
        requests, results = fixtures()
        requests[0]['reference_model'] = 'other'
        self.assertFalse(c.compare(requests, results)['passed'])
        requests, results = fixtures()
        requests[0]['reference_stop_reason'] = 'max_tokens'
        self.assertFalse(c.compare(requests, results)['passed'])
        requests, results = fixtures()
        requests[0]['request_json']['model'] = 'other'
        self.assertFalse(c.compare(requests, results)['passed'])
        requests, results = fixtures()
        results[0]['status'] = 'error'
        self.assertFalse(c.compare(requests, results)['passed'])

    def test_selection_explicit_not_automatic(self):
        requests, results = fixtures()
        extra = request('extract', extraction(), call=3)
        report = c.compare(requests + [extra], results,
                           selection=[{k: r[k] for k in ('job_id', 'call_index', 'stage')} for r in requests])
        self.assertTrue(report['passed'])
        self.assertFalse(c.compare(requests + [extra], results)['passed'])

    def test_output_redacted(self):
        requests, results = fixtures()
        report = json.dumps(c.compare(requests, results))
        for token in ('alias alpha', 'alias summary', 'alias reason', 'alias prompt', 'J0', 'E0'):
            self.assertNotIn(token, report)

    def test_missing_reference_model_blocks_positive_baseline(self):
        requests, results = fixtures()
        del requests[0]['reference_model']
        report = c.compare(requests, results)
        self.assertFalse(report['passed'])
        self.assertFalse(report['rows'][0]['reference_valid'])

    def test_missing_reference_completion_blocks_positive_baseline(self):
        requests, results = fixtures()
        del requests[1]['reference_stop_reason']
        report = c.compare(requests, results)
        self.assertFalse(report['passed'])
        self.assertIn('invalid_request_contract', report['blockers'])

    def test_same_quote_unrelated_claim_without_source_cannot_recall(self):
        requests, results = fixtures()
        left, right = observation('alpha alpha alpha', ids=[]), observation('omega omega omega', ids=[])
        left['quotes'] = right['quotes'] = ['shared source quote alias']
        requests[0] = request('extract', extraction([left]))
        results[0] = result(requests[0], extraction([right]))
        report = c.compare(requests, results)
        self.assertFalse(report['passed'])
        self.assertEqual(report['metrics']['commitment_recall'], 0)
        self.assertEqual(report['counts']['matched_observations'], 0)

    def test_threshold_invalid(self):
        requests, results = fixtures()
        for kwargs in ({'match_threshold': float('nan')}, {'extract_recall': -1}, {'max_gate_losses': True}):
            with self.assertRaises(ValueError):
                c.compare(requests, results, **kwargs)

    def test_cli_and_redacted_failure(self):
        requests, results = fixtures()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            directory = Path(directory)
            req, res, output = directory / 'r.jsonl', directory / 'l.jsonl', directory / 'o.json'
            req.write_text('\n'.join(json.dumps(r) for r in requests))
            res.write_text('\n'.join(json.dumps(r) for r in results))
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                code = c.main(['--requests', str(req), '--results', str(res), '--output', str(output)])
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output.read_text())['passed'])
            req.write_text('{private prose bad JSON')
            with contextlib.redirect_stdout(capture):
                code = c.main(['--requests', str(req), '--results', str(res), '--output', str(output)])
            self.assertEqual(code, 2)
            self.assertNotIn('private prose', capture.getvalue())


if __name__ == '__main__':
    unittest.main()
