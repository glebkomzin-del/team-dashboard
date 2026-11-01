"""Bounded component comparison: saved extraction, new compact reconciliation.

Does not publish, regenerate embeddings, change the ledger ceiling, or pretend
that these component checks replace an end-to-end real-meeting comparison.
"""
import json
from pathlib import Path
import tempfile
import sys
from compact_reconcile import run
from evaluation_budget import EvaluationCalls
from hybrid_pipeline import CONFIDENCE, decoded, version
from hybrid_index import encode
from memory import connect, known_work_ids, ValidationError, validate
from openai_provider import request, count_input_tokens
from processor import units
from quality_cases import CASES
from run_quality_cases import seed
from run_hybrid_validation import ROOT, setup
import reconcile


def main(model='gpt-5.6-terra', case_ids=(), ceiling=10000000):
    if set(case_ids)-{case['id'] for case in CASES}:
        raise ValueError('Unknown requested quality case')
    store = setup()
    results = []
    target = ROOT.parent/'cost-optimization-20260908'/'cases'/model
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for case in CASES:
        if case_ids and case['id'] not in case_ids:
            continue
        calls = EvaluationCalls(ROOT/'budget.sqlite', store, request, {},
            {'case': case['id'], 'pipeline': version(model, compact=True), 'component': 'compact'},ceiling=ceiling,token_counter=count_input_tokens)
        extracted = None
        for req, res in calls.db.execute("SELECT request,response FROM calls WHERE model='gpt-5.6-terra' AND response IS NOT NULL ORDER BY created"):
            req = json.loads(req)
            if isinstance(req['scope'], dict) and req['scope'].get('case') == case['id'] and 'STUFE 1:' in req['prompt']:
                response = json.loads(res)
                if response.get('stop_reason') == 'end_turn':
                    extracted = decoded(response); break
        if extracted is None:
            raise ValueError('Missing paid reference extraction; do not regenerate')
        before = calls.total()
        with tempfile.TemporaryDirectory() as tmp:
            db = connect(Path(tmp)/'db.sqlite')
            seed(db, case)
            meeting = {'title': case['id'], 'meeting_date': '2026-09-08', 'raw_transcript': case['text']}
            work = reconcile.candidates(db, meeting, {'observations': []})
            hits = {w['id']: {'id': w['id'], 'kind': 'work', 'target_id': w['id'], 'metadata': {},
                              'text': w['claim']} for w in work}
            originals = units(case['text'])
            def stage(name, prompt, schema, check, output_limit):
                for attempt in range(2):
                    response = calls(prompt, model, max_tokens=output_limit, schema=schema)
                    raw = decoded(response)
                    try:
                        return check(raw)
                    except (ValidationError, ValueError, KeyError) as error:
                        if attempt:
                            raise
                        prompt += '\nVertragsfehler korrigieren: '+str(error)+'\nVorherige Antwort:\n'+encode(raw)
            try:
                proposal, stats = run(raw=extracted, work=work, hits=hits, query_hits={}, originals=originals,
                    meeting=meeting, known=known_work_ids(db, '2026-09-08'), stage=stage,
                    rules=(Path(__file__).parent/'evaluation/prompt-v9.txt').read_text(),
                    base='\nMeeting: '+case['id']+'\nDatum: 2026-09-08\nVollständiges Original:\n'+encode(originals),
                    confidence_rules=CONFIDENCE)
                items = validate(proposal, case['text'], known_work_ids(db, '2026-09-08'))
                new = [o for o in items if o.get('creates_work')]
                done = [o for o in items if o.get('update') == 'done' and not o.get('required_review')]
                checks = {'new_tasks': len(new) == case['tasks'], 'done': len(done) == case['done'],
                          'no_unsupported_change': all(not o.get('required_review') for o in items if o.get('update') != 'none')}
                if 'due' in case:
                    checks['due'] = all(o.get('due_text') == case['due'] for o in new)
                if case.get('condition_retained'):
                    checks['condition'] = all(o.get('update') not in ('done', 'condition_met') for o in items)
                if case['id'] == 'same_topic_different_action':
                    wanted = next(w['id'] for w in work if w['title'] == 'Monatsbericht senden')
                    checks['target'] = len(done) == 1 and done[0]['update_target'] == wanted
                result = {'id': case['id'], 'model': model, 'passed': all(checks.values()), 'checks': checks,
                          'statistics': stats, 'proposal': proposal}
            except Exception as error:
                result = {'id': case['id'], 'passed': False, 'error': type(error).__name__+': '+str(error)}
            finally:
                db.close()
        result['incremental_upper_usd'] = (calls.total()-before)/1e6
        result['ledger_upper_usd'] = calls.total()/1e6
        calls.close()
        (target/(case['id']+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        results.append({k: v for k, v in result.items() if k != 'proposal'})
        print(encode(results[-1]), flush=True)
        if not result['passed']:
            break  # Diagnose the first failure before spending on more cases.
    (target/'summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['gpt-5.6-terra','gpt-5.6-luna'], default='gpt-5.6-terra')
    parser.add_argument('case_ids', nargs='*')
    parser.add_argument('--ceiling-micro-usd',type=int,default=10000000)
    args = parser.parse_args()
    main(args.model, args.case_ids,args.ceiling_micro_usd)
