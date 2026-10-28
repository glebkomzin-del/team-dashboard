"""Run the unchanged production processor for one explicitly authorized source."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback
import uuid

sys.path.insert(0, '/app')
from paid_calls import PaidCalls, PaidOutcomeUnknown, ContextCountUnavailable, ContextBudgetExceeded, private_json, sha, encode
from gateway_journal import GatewayJournal
from journal_service import JournalService
from generation_review import materialize, compile_generation, verify_generation
from generation_service import make_plan
from journal_projection import prepare_source
from canonical_archive import verify_document, verify_note
from canonical_worker import CanonicalWorker, pipeline_version
from memory import connect
from processor import process, units, PROMPT_VERSION
from openai_provider import MODEL
import future_summary


def checked_generation(base, plan, reviews, current, reason):
    generation, projection, prepared = compile_generation(
        base, plan, source_reviews=reviews, identity_links=[], topic_identity_links=[],
        reason=reason, _retain_projection=True, _base_projection=current)
    try:
        verified, _ = verify_generation(base, generation, _projection=True, _base_projection=current)
        verified.close()
        return generation, prepared
    finally:
        projection.close()


def attempt_paths(cache, job_id, run):
    directory = Path(cache) / 'worker-reprocess22' / job_id
    ledger = Path(cache).parent / 'reprocess22-reservations' / job_id
    scope = run.get('cache_scope')
    if scope:
        assert str(uuid.UUID(scope)) == scope == run['command_id']
        return directory, directory / 'attempts' / scope, ledger / 'attempts' / scope
    return directory, directory, ledger


def failure_reason(error):
    return ('transport_failed' if isinstance(error, ContextCountUnavailable) else
            'budget_exceeded' if isinstance(error, ContextBudgetExceeded) else
            'provider_outcome_unknown' if isinstance(error, PaidOutcomeUnknown) else 'validation_failed')


def run(value):
    job, doc, expected = value['job'], value['document'], value['revision']
    verify_document(doc)
    assert job['state'] == 'running' and job['lease_token'] == value['run']['lease_token']
    assert job['source_id'] == doc['source_id'] and job['document_id'] == doc['id']
    assert value['config']['enabled'] is True
    pipeline = pipeline_version(MODEL)
    assert pipeline == value['config']['pipeline']
    assert doc['event_date'] >= value['config']['automatic_from']
    store = GatewayJournal(os.environ['SUPABASE_URL'], os.environ['SUPABASE_PUBLISHABLE_KEY'],
                           os.environ['MEMORY_JOURNAL_TOKEN'], job['space_id'])
    service = JournalService(store, os.environ.get('MEMORY_CACHE_DIR', '.local/projections'))
    canonical = CanonicalWorker(service, MODEL)
    assert canonical.pipeline == pipeline
    space = store.space(); assert space['revision'] == expected and space['id'] == job['space_id']
    # Existing original-deletion maintenance already removes worker-* sandboxes.
    directory, attempt, ledger = attempt_paths(service.cache, job['id'], value['run'])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    attempt.mkdir(parents=True, exist_ok=True, mode=0o700)
    api = PaidCalls(store, attempt / 'calls', job['id'], pipeline, expected,
                    value['run']['start_index'], canonical.schema,
                    ledger_directory=ledger,
                    lease_token=value['run']['lease_token'],
                    token_override=value['run'].get('token_override'),
                    context_continuation=value['run'].get('context_continuation'))
    imported = api.import_known()
    if value.get('action') == 'import':
        print(encode({'state': 'imported', 'job': job['id'][:8], **imported}), flush=True)
        return
    base = service.generation_base(space)
    assert not any(e['kind'] == 'source' and e['source']['source_id'] == doc['source_id'] for e in base)
    at = next((i for i, e in enumerate(base) if e['kind'] == 'source' and e['source']['event_date'] > doc['event_date']), len(base))
    historical, _ = materialize(base[:at]); current, _ = materialize(base)
    scratch = connect(':memory:'); historical.backup(scratch)
    meeting = {'id': job['id'], 'source_id': doc['source_id'], 'title': doc['title'],
               'meeting_date': doc['event_date'], 'observed_at': doc['observed_at'], 'raw_transcript': doc['body']}
    try:
        owner = {'role': 'owner', 'id': space['owner_id']}
        with service.archive_projection(owner) as (archive, _):
            archive_path = attempt / 'archive.sqlite'
            saved = sqlite3.connect(archive_path); archive.backup(saved); saved.close()
        import hybrid_pipeline
        original_guard = hybrid_pipeline.context_exceeds_budget
        if api.context_continuation:
            hybrid_pipeline.context_exceeds_budget = api.context_guard(original_guard)
        try:
            result = process(scratch, meeting, MODEL, api=api, pipeline=pipeline,
                             archive_db=str(archive_path), extra_instruction=future_summary.INSTRUCTION,
                             extraction_recovery=PROMPT_VERSION in ('v10', 'v11'))
        finally:
            hybrid_pipeline.context_exceeds_budget = original_guard
        assert result['status'] == 'applied' and api.primary_responses
        assert not api.token_override or api.override_used
        row = scratch.execute("SELECT proposal_json FROM runs WHERE job_id=? AND outcome='applied'", (result['job'],)).fetchone()
        assert row
        summary = future_summary.from_response(api.primary_responses[-1], units(doc['body']), doc['title'], doc['body'])
        note_json = encode(summary); note_hash = sha(note_json)
        note = {'document_id': doc['id'], 'origin': 'source_summary', 'origin_id': job['id'],
                'note_json': note_json, 'note_hash': note_hash,
                'id': sha(':'.join((doc['id'], 'source_summary', job['id'], note_hash)))}
        verify_note(note)
        source = {k: doc[k] for k in ('source_id', 'event_date', 'observed_at', 'title')}
        source.update(id=job['id'], content_hash=doc['body_hash'], transcript=doc['body'])
        provenance = {'mode': 'owner_full_reprocess_standard_ledger', 'job_id': job['id'],
                      'context_revision': expected, 'owner_reprocess_command': value['run']['command_id'],
                      'normal_call_indices': [r['call_index'] for r in api.receipts]}
        if api.context_continuation:
            assert api.context_counts, 'Approved compact continuation was not used'
            provenance['context_continuation_command'] = api.context_continuation['command_id']
            provenance['context_count_request_hashes'] = sorted(api.context_counts)
        payload = prepare_source(historical, source, json.loads(row['proposal_json']), pipeline=pipeline,
                                 model=MODEL, provenance=provenance,
                                 usage={'durable_call_count': api.index, 'normal_actual_micro_usd': sum(r['actual_micro_usd'] for r in api.receipts)})
        payload['archive_note'] = note
        reason = 'Vom Eigentümer ausdrücklich beauftragte erneute reguläre Pipelineauswertung dieser Quelle.'
        change = {'source_id': source['source_id'], 'action': 'add',
                  'entry': {'kind': 'source', 'source': source, 'payload': payload}, 'reason': reason}
        plan, reviews = make_plan(base, [change], [], [])
        generation, prepared = checked_generation(base, plan, reviews, current, reason)
        assert generation['personal_decisions_preserved'] == sum(e['kind'] == 'human' for e in base)
        assert [e for e in prepared if e['kind'] == 'human'] == [e for e in base if e['kind'] == 'human']
        assert len(encode(generation).encode()) <= 3700000
        assert store.space()['revision'] == expected
        review_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'regular-reprocess22:' + str(expected) + ':' + job['id'] + ':' + generation['review_sha256']))
        latest_job = store.call('job_detail', job_id=job['id'])['job']
        assert latest_job['state'] == 'running' and latest_job['lease_token'] == value['run']['lease_token']
        artifact = {'job_id': job['id'], 'expected_revision': expected, 'expected_updated_at': latest_job['updated_at'],
                    'lease_token': value['run']['lease_token'], 'owner_reprocess_command': value['run']['command_id'],
                    'pipeline': pipeline,
                    'document_id': doc['id'], 'body_hash': doc['body_hash'], 'note': note,
                    'review_id': review_id, 'command_id': str(uuid.uuid5(uuid.NAMESPACE_URL, review_id + ':accept')),
                    'reason': reason, 'generation': generation}
        if api.context_continuation:
            artifact.update(context_continuation=api.context_continuation,
                            context_counts=list(api.context_counts.values()))
        private_json(directory / 'prepared.json', artifact)
        private_json(attempt / 'status.json', {'state': 'prepared', 'job': job['id'][:8], 'calls': len(api.receipts),
                                                'actual_micro_usd': sum(r['actual_micro_usd'] for r in api.receipts)})
        print(encode({'state': 'prepared', 'job': job['id'][:8], 'artifact': str(directory / 'prepared.json'),
                      'calls': len(api.receipts), 'actual_micro_usd': sum(r['actual_micro_usd'] for r in api.receipts)}), flush=True)
    except Exception as error:
        reason = failure_reason(error)
        try: store.call('pause_job', job_id=job['id'], lease_token=value['run']['lease_token'], reason=reason)
        except Exception: pass
        private_json(attempt / 'status.json', {'state': 'failed', 'job': job['id'][:8],
                                                'error_type': type(error).__name__, **api.last_metadata})
        (attempt / 'failure.txt').write_text(traceback.format_exc()); (attempt / 'failure.txt').chmod(0o600)
        print(encode({'state': 'failed', 'job': job['id'][:8], 'error_type': type(error).__name__, **api.last_metadata}), flush=True)
        raise SystemExit(2)
    finally:
        scratch.close(); historical.close(); current.close()


if __name__ == '__main__':
    run(json.load(sys.stdin))
