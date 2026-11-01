"""Local model comparison. Default is a zero-network preflight; --run spends from one ledger.

The local gateway is the existing QA test double. Its retrieval ranking is not
production-equivalent; real transcript inputs require a separate approved manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
from datetime import date, datetime, timezone
from uuid import uuid5, NAMESPACE_URL

from evaluation_budget import EvaluationCalls
from hybrid_pipeline import process
from hybrid_schema import extraction_schema
from memory import connect, overview, register, claim, apply
from openai_provider import request, count_input_tokens
from quality_cases import CASES as QUALITY
from run_quality_cases import seed
from future_summary import INSTRUCTION
from test_qa_service import Store, Journal, OWNER
from qa_service import QuestionService
from planner import record
from archive_index import connect as archive_connect
from call_budget import RATES

HERE = Path(__file__).parent
SPEC = HERE / 'evaluation/model-comparison-20260924-cases.json'
PRIVATE = HERE / '.local/model-comparison-20260924'
MODELS = {'terra': ('gpt-5.6-terra', None), 'sol': ('gpt-6-sol', None),
          'mixed': ('gpt-6-sol', 'gpt-6-luna'), 'luna': ('gpt-6-luna', None)}
QA_TASKS = (
    ('Budgetbericht abschließen', 'Gleb Komzin', 'Zahlen bis Freitag prüfen'),
    ('Datenmigration vorbereiten', 'Gleb Komzin', 'Toms Freigabe fehlt noch'),
    ('Kundentermin vereinbaren', 'Gleb Komzin', 'Maria zur Abstimmung einladen'),
    ('Monatsbericht senden', 'Gleb Komzin', 'Versand an Maria noch offen'),
)
EXPECTED_SEED_STATUS = {
    'paraphrase': {'Monatsbericht senden': 'done'},
    'old_promise': {'Abstimmung mit Maria organisieren': 'done'},
    'same_topic_different_action': {'Monatsbericht senden': 'done', 'Monatsbericht prüfen': 'open'},
    'partial_condition': {'Daten migrieren': 'waiting'},
    'repeated_promise_no_duplicate': {'Monatsbericht senden': 'open'},
    'contradictory_completion': {'Monatsbericht senden': 'open'},
    'status_without_new_promise': {'Monatsbericht senden': 'open'},
    'completed_then_new_distinct_task': {'Monatsbericht senden': 'done'},
}


def work_rows(state):
    return {row['id']: row for group in ('personal', 'waiting', 'waiting_dependencies', 'completed')
            for row in state[group]}


def call_metrics(calls, before_hashes):
    rows = calls.db.execute('SELECT hash,model,actual,reserved,response FROM calls').fetchall()
    touched = [row for row in rows if row[0] in calls.used_identifiers or row[0] not in before_hashes]
    costs = {}
    provider_seconds = 0.0
    timed = 0
    for identifier, model, actual, reserved, response in touched:
        costs[model] = costs.get(model, 0) + (actual if actual is not None else reserved)
        if response:
            elapsed = json.loads(response).get('elapsed_seconds')
            if type(elapsed) in (int, float) and elapsed >= 0:
                provider_seconds += elapsed
                timed += 1
    return {'used_micro_usd': costs,
            'fresh_call_count': sum(row[0] not in before_hashes for row in touched),
            'reused_call_count': sum(row[0] in before_hashes for row in touched),
            'model_calls': sum(row[1] != 'text-embedding-3-small' for row in touched),
            'provider_elapsed_seconds': round(provider_seconds, 2),
            'provider_timed_call_count': timed}


def comparison_scope(kind, case_id, repeat=0):
    scope = {'comparison': '20260924', kind: case_id}
    if repeat:
        scope['repeat'] = repeat
    return scope


def cases(manifest=None):
    data = json.loads(SPEC.read_text())
    pipeline = [dict(case) for case in QUALITY] + data['semantic']
    if manifest:
        source = Path(manifest).resolve()
        supplied = json.loads(source.read_text())
        if not isinstance(supplied, list) or not supplied:
            raise ValueError('Manifest must contain nonempty case list')
        for item in supplied:
            if not isinstance(item, dict) or not {'id', 'transcript_file', 'sha256', 'tasks', 'done', 'gold_review'} <= item.keys():
                raise ValueError('Real manifest case requires file, hash and gold_review')
            if not isinstance(item.get('meeting_date'), str) or not isinstance(item.get('observed_at'), str):
                raise ValueError('Real manifest requires meeting_date and observed_at')
            try:
                date.fromisoformat(item['meeting_date'])
                observed = datetime.fromisoformat(item['observed_at'].replace('Z', '+00:00'))
                if observed.tzinfo is None:
                    raise ValueError()
            except ValueError as error:
                raise ValueError('Real manifest requires valid dated source') from error
            file = (source.parent / item['transcript_file']).resolve()
            if not file.is_relative_to(source.parent) or not file.is_file():
                raise ValueError('Transcript must be a file beside the manifest')
            raw = file.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('Transcript hash mismatch')
            body = raw.decode('utf-8')
            review = item['gold_review']
            if (not isinstance(review, list) or not review or any(
                not isinstance(row, dict) or not isinstance(row.get('quote'), str)
                or not row['quote'].strip() or row['quote'] not in body
                or not isinstance(row.get('expected'), dict) or not row['expected']
                or not all(key in row['expected'] for key in ('owner', 'status', 'condition_text'))
                for row in review)):
                raise ValueError('Real gold_review requires quoted source and owner/status/condition expectations')
            if any(item.get(key) is not None and (type(item[key]) is not int or item[key] < 0)
                   for key in ('tasks', 'done')):
                raise ValueError('Real count expectations must be nonnegative integers or null')
            prior = None
            if 'real_seed' in item and not isinstance(item['real_seed'], list):
                raise ValueError('Real seed must be a list')
            if item.get('real_seed'):
                prior_file = (source.parent / item.get('prior_transcript_file', '')).resolve()
                if not prior_file.is_relative_to(source.parent) or not prior_file.is_file():
                    raise ValueError('Seed transcript must be a file beside the manifest')
                prior_raw = prior_file.read_bytes()
                if hashlib.sha256(prior_raw).hexdigest() != item.get('prior_sha256'):
                    raise ValueError('Seed transcript hash mismatch')
                prior = prior_raw.decode('utf-8')
                for row in item['real_seed']:
                    if (not isinstance(row, dict) or not all(isinstance(row.get(key), str) and row[key].strip()
                        for key in ('source_quote', 'prior_date', 'matter', 'title', 'claim', 'owner'))
                        or row['source_quote'] not in prior or not isinstance(row.get('quotes'), list)
                        or not row['quotes'] or any(not isinstance(q, str) or q not in prior for q in row['quotes'])
                        or (row.get('condition_text') and not any(row['condition_text'] in q for q in row['quotes']))
                        or row['prior_date'] >= item['meeting_date']):
                        raise ValueError('Real seed requires dated, quoted prior source and complete task fields')
                    try:
                        date.fromisoformat(row['prior_date'])
                    except ValueError as error:
                        raise ValueError('Real seed requires valid prior_date') from error
            pipeline.append({**item, 'text': body, 'prior_text': prior, 'difficulty': 'real'})
    ids = [case['id'] for case in pipeline] + [case['id'] for case in data['qa']]
    if len(ids) != len(set(ids)) or len(QUALITY) != 8 or len(data['semantic']) < 4 or len(data['qa']) != 20:
        raise ValueError('Case inventory or unique IDs invalid')
    for case in pipeline:
        if (not isinstance(case.get('text'), str) or not case['text'].strip() or
            (case.get('difficulty') != 'real' and (type(case.get('tasks')) is not int or type(case.get('done')) is not int))):
            raise ValueError('Pipeline case lacks nonempty input or numeric expectations')
    for case in data['qa']:
        if not case.get('question') or case.get('mode') not in ('retrieval', 'structured_tasks') or not (case.get('contains') or case.get('grounded')):
            raise ValueError('QA case lacks question or expectation')
        if case['mode'] == 'retrieval' and (case.get('expected_task') not in range(len(QA_TASKS)) or not case.get('contains')):
            raise ValueError('Retrieval QA case lacks expected answer and canonical task')
    return pipeline, data['qa']


def preflight(manifest=None):
    pipeline, qa = cases(manifest)
    missing = sorted({model for pair in MODELS.values() for model in pair if model and model not in RATES})
    # No key lookup, provider request, or filesystem writes in preflight.
    long_transcripts = [{'id': case['id'], 'transcript_bytes': len(case['text'].encode())}
                        for case in pipeline if len(case['text']) > 220000]
    return {'pipeline_cases': len(pipeline), 'qa_cases': len(qa),
            'candidate_models': list(MODELS), 'missing_price_contracts': missing,
            'long_transcripts_checked_at_prompt': long_transcripts,
            'search': 'local test gateway; retrieval ranking differs from production',
            'paid_ready': not missing}


def check_pipeline(case, state, before_state=None, result=None, observation_count=None):
    work = list(work_rows(state).values())
    old = len(case.get('real_seed', case.get('seed', [])))
    checks = {}
    if case.get('tasks') is not None:
        checks['new_tasks'] = len(work) - old == case['tasks']
    if case.get('done') is not None:
        checks['done'] = len(state['completed']) == case['done']
    if case.get('difficulty') != 'real' and 'owners' not in case:
        checks['owners'] = all(row.get('owner') == 'Gleb' for row in work)
    if 'owners' in case:
        checks['owners'] = sorted(row.get('owner') for row in work) == sorted(case['owners'])
    if case['id'] == 'same_topic_different_action':
        checks['correct_target'] = (len(state['completed']) == 1 and state['completed'][0]['title'] == 'Monatsbericht senden')
    if 'due' in case:
        checks['deadline'] = all(row.get('due_text') == case['due'] for row in work)
    if case.get('condition_retained'):
        checks['condition_retained'] = any(row.get('condition_text') for row in work)
    if before_state is not None:
        before = work_rows(before_state)
        after = work_rows(state)
        checks['seed_identity'] = before.keys() <= after.keys()
        if case.get('difficulty') != 'real':
            checks['seed_status'] = all(after.get(identifier, {}).get('status') == EXPECTED_SEED_STATUS.get(
                case['id'], {}).get(row['title'], row['status']) for identifier, row in before.items())
            checks['seed_title_owner'] = all(after.get(identifier, {}).get('title') == row['title'] and
                                             after.get(identifier, {}).get('owner') == row.get('owner')
                                             for identifier, row in before.items())
            checks['seed_condition'] = all(after.get(identifier, {}).get('condition_text') == row.get('condition_text')
                                           for identifier, row in before.items())
    if result is not None:
        checks['applied'] = result.get('status') == 'applied'
        checks['observations'] = (type(result.get('observations')) is int and result['observations'] > 0 and
                                  result['observations'] == observation_count)
        if case.get('tasks') is not None:
            checks['created_count'] = result.get('new_work') == case['tasks']
    if not checks:
        raise AssertionError('Vacuous pipeline checks')
    return checks


def seed_real(db, case):
    for index, row in enumerate(case['real_seed']):
        source_id = 'comparison:prior:' + case['id'] + ':' + str(index)
        job = register(db, source_id=source_id,
                       event_date=row['prior_date'], title=case['id'] + ':prior',
                       transcript=case['prior_text'], pipeline='quoted-real-reference-v1')
        item = {'matter': row['matter'], 'matter_id': None, 'kind': 'commitment',
                'title': row['title'], 'claim': row['claim'], 'owner': row['owner'],
                'commitment_strength': 'explicit', 'due_text': None,
                'condition_text': row.get('condition_text'), 'update_target': None,
                'update': 'none', 'quotes': row['quotes'], 'state_quotes': [],
                'uncertainty': None, 'action_uncertainty': None, 'required_review': False,
                'work_state': 'waiting' if row.get('condition_text') else 'open'}
        apply(db, job, claim(db, job), {'observations': [item], 'coverage_notes': []}, model='reference')
        db.execute('UPDATE source_versions SET observed_at=? WHERE source_id=?',
                   (datetime.fromisoformat(row['prior_date']).replace(tzinfo=timezone.utc).timestamp(), source_id))


def pipeline_case(case, model, extraction, ledger, ceiling, folder, repeat=0):
    with tempfile.TemporaryDirectory(dir=PRIVATE) as temp:
        db = connect(Path(temp) / 'memory.sqlite')
        store = Store()
        calls = EvaluationCalls(ledger, store, request, extraction_schema(),
                                comparison_scope('case', case['id'], repeat), ceiling=ceiling,
                                token_counter=count_input_tokens)
        try:
            if case.get('real_seed'):
                seed_real(db, case)
            else:
                seed(db, case)
            meeting = {'id': 'comparison:' + case['id'], 'source_id': 'comparison:' + case['id'],
                       'title': case.get('title', case['id']), 'meeting_date': case.get('meeting_date', '2026-09-08'),
                       'observed_at': case.get('observed_at', '2026-09-08T12:00:00Z'),
                       'raw_transcript': case['text']}
            start = time.monotonic()
            before = calls.total()
            before_hashes = {row[0] for row in calls.db.execute('SELECT hash FROM calls')}
            before_state = overview(db, meeting['meeting_date'])
            result = process(db, meeting, model, api=calls, extra_instruction=INSTRUCTION,
                             extraction_model=extraction, compact=True)
            state = overview(db, meeting['meeting_date'])
            observation_count = db.execute('SELECT count(*) FROM observations WHERE job_id=?',
                                           (result.get('job'),)).fetchone()[0]
            checks = check_pipeline(case, state, before_state, result, observation_count)
            job_row = db.execute('SELECT status FROM jobs WHERE id=?', (result.get('job'),)).fetchone()
            checks['persisted_applied'] = bool(job_row and job_row['status'] == 'applied')
            work = sum((state[group] for group in ('personal', 'waiting', 'waiting_dependencies', 'completed')), [])
            metrics = call_metrics(calls, before_hashes)
            private = {'result': result, 'state': state, 'checks': checks,
                       **({'before_state': before_state, 'gold_review': case['gold_review'],
                           'seed_review': case.get('seed_review')}
                          if case.get('difficulty') == 'real' else {}),
                       **metrics, 'incremental_micro_usd': calls.total() - before,
                       'wall_elapsed_seconds': time.monotonic() - start}
            if case.get('difficulty') == 'real':
                private['observations'] = []
                for raw in db.execute('SELECT * FROM observations WHERE job_id=?', (result.get('job'),)):
                    observation = dict(raw)
                    observation['data'] = json.loads(observation.pop('data_json'))
                    private['observations'].append(observation)
            (folder / (case['id'] + '.json')).write_text(json.dumps(private, ensure_ascii=False, indent=2))
            return {'id': case['id'], 'passed': all(checks.values()) and case.get('difficulty') != 'real',
                    'manual_semantic_review_required': case.get('difficulty') == 'real', 'checks': checks,
                    'repairs': result.get('hybrid', {}).get('repairs'),
                    'review_count': sum(bool(row.get('required_review')) for row in work),
                    'wall_elapsed_seconds': round(private['wall_elapsed_seconds'], 2),
                    **metrics,
                    'incremental_micro_usd': private['incremental_micro_usd']}
        except Exception as error:
            if 'before' in locals():
                failure = {'id': case['id'], 'passed': False, 'error_type': type(error).__name__,
                           'manual_semantic_review_required': case.get('difficulty') == 'real',
                           'error_message': str(error),
                           'incremental_micro_usd': calls.total() - before,
                           'wall_elapsed_seconds': round(time.monotonic() - start, 2),
                           **call_metrics(calls, before_hashes)}
                (folder / (case['id'] + '-failure.json')).write_text(json.dumps(failure, ensure_ascii=False, indent=2))
                error.comparison_result = failure
            raise
        finally:
            calls.close()
            db.close()


def qa_case(case, model, ledger, ceiling, folder, repeat=0):
    with tempfile.TemporaryDirectory(dir=PRIVATE) as temp:
        root = Path(temp)
        db, archive = connect(root / 'memory.sqlite'), archive_connect(root / 'archive.sqlite')
        store = Store()
        calls = EvaluationCalls(ledger, store, request, extraction_schema(),
                                comparison_scope('qa', case['id'], repeat), ceiling=ceiling,
                                token_counter=count_input_tokens)
        try:
            for index, (title, owner, note) in enumerate(QA_TASKS):
                record(db, command_id=str(uuid5(NAMESPACE_URL, case['id'] + ':command:' + str(index))),
                       actor_id=OWNER['id'], command={'action': 'create_task',
                       'target_id': str(uuid5(NAMESPACE_URL, case['id'] + ':task:' + str(index))),
                       'reason': 'Lokaler Vergleichsfall', 'event_date': '2026-09-19',
                       'patch': {'title': title, 'owner': owner, 'note': note}})
            db.commit()
            service = QuestionService(Journal(store, db, archive), calls, model=model,
                                      budget_micro_usd=ceiling, outbox=root / 'question-outbox')
            started = time.monotonic()
            before = calls.total()
            before_hashes = {row[0] for row in calls.db.execute('SELECT hash FROM calls')}
            response = service.answer(OWNER, {'request_id': str(uuid5(NAMESPACE_URL, case['id'] + ':' + model)),
                                              'question': case['question'],
                                              'messages': case.get('messages', [])})
            checks = {'mode': response['coverage']['mode'] == case['mode']}
            if case.get('contains'):
                checks['contains'] = case['contains'].casefold() in response['answer'].casefold()
            if case.get('forbid'):
                checks['forbid'] = all(term.casefold() not in response['answer'].casefold() for term in case['forbid'])
            if case.get('grounded'):
                checks['citations'] = bool(response['citations']) and all(row.get('kind') for row in response['citations'])
                checks['nonempty_answer'] = bool(response['answer'].strip())
            if 'expected_task' in case:
                expected = str(uuid5(NAMESPACE_URL, case['id'] + ':task:' + str(case['expected_task'])))
                checks['expected_source'] = any((row.get('target') or {}).get('params', {}).get('task') == expected
                                                for row in response['citations'])
            if not checks:
                raise AssertionError('Vacuous QA checks')
            metrics = call_metrics(calls, before_hashes)
            private = {'response': response, 'checks': checks,
                       **metrics, 'incremental_micro_usd': calls.total() - before,
                       'wall_elapsed_seconds': time.monotonic() - started}
            (folder / (case['id'] + '.json')).write_text(json.dumps(private, ensure_ascii=False, indent=2))
            return {'id': case['id'], 'passed': all(checks.values()), 'checks': checks,
                    'manual_semantic_review_required': case['mode'] == 'retrieval',
                    'wall_elapsed_seconds': round(private['wall_elapsed_seconds'], 2),
                    **metrics,
                    'incremental_micro_usd': private['incremental_micro_usd']}
        except Exception as error:
            if 'before' in locals():
                failure = {'id': case['id'], 'passed': False, 'error_type': type(error).__name__,
                           'manual_semantic_review_required': case['mode'] == 'retrieval',
                           'incremental_micro_usd': calls.total() - before,
                           'wall_elapsed_seconds': round(time.monotonic() - started, 2),
                           **call_metrics(calls, before_hashes)}
                (folder / (case['id'] + '-failure.json')).write_text(json.dumps(failure, ensure_ascii=False, indent=2))
                error.comparison_result = failure
            raise
        finally:
            calls.close()
            archive.close()
            db.close()


def run(candidate, suite='screening', manifest=None, case_id=None, ceiling=10_000_000, repeat=0):
    if type(repeat) is not int or repeat not in (0, 1, 2):
        raise ValueError('Repeat must be 0, 1 or 2')
    if repeat and (suite not in ('screening', 'pipeline') or case_id not in
                   ('same_topic_different_action', 'partial_condition')):
        raise ValueError('Repeated trials are limited to the two selected hard cases')
    ready = preflight(manifest)
    if not ready['paid_ready']:
        raise RuntimeError('Missing priced model contracts: ' + ', '.join(ready['missing_price_contracts']))
    if ceiling != 10_000_000:
        raise ValueError('Comparison uses the existing $10 shared ledger cap')
    model, extraction = MODELS[candidate]
    pipeline, qa = cases(manifest)
    selected = pipeline[:8] if suite == 'screening' else pipeline if suite == 'pipeline' else qa
    if case_id:
        selected = [case for case in selected if case['id'] == case_id]
    if not selected:
        raise ValueError('No selected cases')
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    candidate_folder = PRIVATE / candidate
    candidate_folder.mkdir(exist_ok=True, mode=0o700)
    candidate_folder.chmod(0o700)
    folder = candidate_folder / ('repeat-' + str(repeat)) if repeat else candidate_folder
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    ledger = PRIVATE / 'budget.sqlite'
    before = 0
    if ledger.exists():
        with sqlite3.connect(ledger) as db:
            before = db.execute('SELECT coalesce(sum(coalesce(actual,reserved)),0) FROM calls').fetchone()[0]
    results = []
    error = None
    try:
        for case in selected:
            # Stop on the first provider/transport/ledger error. The durable request
            # remains reserved; the next invocation cannot silently resend it.
            item = qa_case(case, model, ledger, ceiling, folder, repeat=repeat) if suite == 'qa' else pipeline_case(
                case, model, extraction, ledger, ceiling, folder, repeat=repeat)
            results.append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
    except Exception as failure:
        error = failure
        if hasattr(failure, 'comparison_result'):
            results.append(failure.comparison_result)
    with sqlite3.connect(ledger) as db:
        cumulative = db.execute('SELECT coalesce(sum(coalesce(actual,reserved)),0) FROM calls').fetchone()[0]
    summary = {'candidate': candidate, 'suite': suite, 'repeat': repeat, 'cases': len(results),
               'passed': sum(bool(row['passed']) for row in results),
               'pass_meaning': 'automatic checks only; real transcripts and retrieval answers require manual semantic review',
               'deterministic_controls': sum(row.get('model_calls') == 0 for row in results) if suite == 'qa' else 0,
               'manual_semantic_review_pending': sum(bool(row.get('manual_semantic_review_required')) for row in results),
               'incremental_ledger_micro_usd': cumulative - before,
               'cumulative_ledger_micro_usd': cumulative,
               'wall_time_includes_replay': True,
               'status': 'stopped' if error else 'completed',
               **({'error_type': type(error).__name__} if error else {}),
               'limitations': ready['search'], 'results': results}
    (folder / ('summary-' + suite + '.json')).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
    if error:
        raise error
    return summary


def count_saved_input(path, candidate):
    """Optional read-only count of a saved compact prompt/schema; no generation."""
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict) or not isinstance(payload.get('prompt'), str) or not isinstance(payload.get('schema'), dict):
        raise ValueError('Count input requires JSON with prompt and schema')
    models = list(dict.fromkeys(model for model in MODELS[candidate] if model))
    return {'prompt_sha256': hashlib.sha256(payload['prompt'].encode()).hexdigest(),
            'prompt_bytes': len(payload['prompt'].encode()),
            'input_tokens': {model: count_input_tokens(payload['prompt'], model, payload['schema']) for model in models}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='Enable paid provider calls')
    parser.add_argument('--candidate', choices=MODELS, default='terra')
    parser.add_argument('--suite', choices=('screening', 'pipeline', 'qa'), default='screening')
    parser.add_argument('--case')
    parser.add_argument('--repeat', type=int, default=0, help='Independent trial 1 or 2 for a selected hard case')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--count-input', type=Path, help='JSON file with actual saved prompt and schema; requires --run')
    args = parser.parse_args()
    if args.count_input and not args.run:
        parser.error('--count-input requires --run because it contacts the provider token counter')
    result = (count_saved_input(args.count_input, args.candidate) if args.count_input else
              run(args.candidate, args.suite, args.manifest, args.case, repeat=args.repeat) if args.run else preflight(args.manifest))
    print(json.dumps(result,
                     ensure_ascii=False, indent=2))
