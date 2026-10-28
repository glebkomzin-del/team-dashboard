"""Existing PostgreSQL and container operations for the 22 authorized originals."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

CT = 'dashboard-memory-canonical-draft-canonical-draft-1'
DB = 'dashboard-supabase-20261003-db-1'
ROOT = Path('/opt/dashboard-memory-canonical-draft/.local/recovery/reprocess22-20261028')
REVIEWED_FAILURE = {
    'job_id': 'f09befd74b16f5d6032a56de408f17aeb1abf458d0f0b828ddcab36534f435ae',
    'revision': 354, 'start_index': 67,
    'updated_at': '2026-10-28T19:00:16.227267+00:00',
    'request_hash': 'c623e43b2f8ed7d5cd25ff87e27b04570637ffed14b320fdfe3e251e5bdc4731',
    'response_hash': '3d47b003cdf39c2e836575122fcfe0fe3beec9c6598810d2e4201bbb1180ca5e',
    'finding': 'Date change requires a quoted new due expression; conversation event_time is not the invitation obligation.'}
TOKEN_FAILURE = {
    'job_id': '9266439fe8c4bb320db97d2a4bb1c4f16b5badb43f9bebf51c2f2191df6a61f7',
    'revision': 355, 'start_index': 2,
    'updated_at': '2026-10-28T19:49:05.965092+00:00',
    'request_hash': '825d696d562fc164874de3d44bcd70541c3ab17ac165308f4ef567e5a48a9b59',
    'response_hash': '955a4f691e8ac47b3c97861886e13d8351cb0a24713feea55e89ecb5d3ac1a94',
    'reason': 'provider_outcome_unknown',
    'finding': 'Known final max_output_tokens completion at 24000; actual cost 149115 micro USD retained.',
    'token_override': {'request_hash': '825d696d562fc164874de3d44bcd70541c3ab17ac165308f4ef567e5a48a9b59',
                       'from_max_tokens': 24000, 'to_max_tokens': 48000}}
REVIEWED_FAILURES = {case['job_id']: case for case in (REVIEWED_FAILURE, TOKEN_FAILURE)}
CONTEXT_ATTEMPT = 'e9a2a394-dab8-5585-b7ee-7570223ac4b8'
CONTEXT_PIPELINE = 'v11:compact1:gate1:gpt-6.1-sol:1b0547b903630200:hotset1:age=30:rank=8:wait1:delta2:canonical1:d6198b7958d46e3e'
CONTEXT_FAILURE = {'updated_at': '2026-10-28T20:18:07.253703+00:00',
                   'calls_hash': 'c0ae6f2cb016070c62e7c0ad4d22c1333665d0970000210fca046b5d0b058e98'}
CONTEXT_CAPTURE = {'prompt_sha256': 'd4c9b6455bc0e221b1e87ab34fe2b713f121631cb236daa3db7c34641f039073',
                   'schema_sha256': 'c5c64bd2012db4c6c937910cce3782f8e30e8457868e7cdf9595257f2fc71f07',
                   'prompt_chars': 958227, 'prompt_utf8_bytes': 968641, 'schema_utf8_bytes': 30139,
                   'max_output_tokens': 59736, 'framing_tokens': 4096, 'conservative_total_tokens': 1062612}
CODE_WRITER = ('import sys;from pathlib import Path;name=sys.argv[1];'
               'assert name in ("paid_calls.py","container_worker.py");'
               '(Path("/tmp/owner-reprocess22")/name).write_bytes(sys.stdin.buffer.read())')


def lit(value):
    return "convert_from(decode('" + base64.b64encode(str(value).encode()).decode() + "','base64'),'UTF8')"


def command(args, data=None, *, persist_errors=True):
    result = subprocess.run(args, input=data, capture_output=True)
    if result.returncode:
        if persist_errors and ROOT.exists():
            path = ROOT / ('command-error-' + str(time.time_ns()) + '.log')
            path.write_bytes(result.stderr); path.chmod(0o600)
        raise RuntimeError('Operation failed; private diagnostic retained' if persist_errors else 'Read-only operation failed; no diagnostic persisted')
    return result.stdout


def sql(query, *, persist_errors=True):
    return command(['docker', 'exec', '-i', DB, 'psql', '-U', 'postgres', '-d', 'postgres',
                    '-XqAt', '-v', 'ON_ERROR_STOP=1'], query.encode(), persist_errors=persist_errors).decode().strip()


def snapshot(space, job_id, *, persist_errors=True):
    sp, jo = lit(space) + '::uuid', lit(job_id)
    return json.loads(sql("BEGIN READ ONLY; SELECT json_build_object('space',(SELECT row_to_json(s) FROM wm_spaces s WHERE id=" + sp +
                         "),'config',(SELECT row_to_json(c) FROM wm_processing_config c WHERE space_id=" + sp +
                         "),'job',(SELECT row_to_json(j) FROM wm_jobs j WHERE space_id=" + sp + " AND id=" + jo +
                         "),'document',(SELECT row_to_json(d) FROM wm_archive_documents d JOIN wm_jobs j ON j.space_id=d.space_id AND j.document_id=d.id WHERE j.space_id=" + sp + " AND j.id=" + jo +
                         "),'next_call_index',(SELECT coalesce(max(call_index)+1,0) FROM wm_model_calls WHERE space_id=" + sp + ' AND job_id=' + jo + ")); COMMIT;", persist_errors=persist_errors))


def guard(value, target, allow_hold):
    job, document, config = value['job'], value['document'], value['config']
    assert job and document and job['id'] == target['id'] and job['space_id'] == target['space_id']
    assert job['state'] == 'review' and job['reason'] == 'provider_outcome_unknown'
    assert job['updated_at'] == target['updated_at'] and document['body_hash'] == target['body_hash']
    assert document['source_id'] == target['source_id'] and document['id'] == target['document_id']
    assert hashlib.sha256(document['body'].encode()).hexdigest() == document['body_hash']
    if allow_hold: assert config['enabled'] is True, 'Normal ledger processing must be enabled under the verified hold'


def save_state(path, state):
    temporary = path.with_suffix('.new')
    with temporary.open('w') as stream:
        stream.write(json.dumps(state)); stream.flush(); os.fsync(stream.fileno())
    temporary.chmod(0o600); temporary.replace(path)


def claim_run(space, target, targets_hash):
    """Explicit owner full rerun; preserve the old job and immutable call history."""
    value = snapshot(space, target['id'])
    pipeline = value['config']['pipeline']
    doc = value['document']; job = value['job']
    assert job['id'] == target['id'] and job['space_id'] == target['space_id']
    assert job['source_id'] == target['source_id'] and job['document_id'] == target['document_id']
    assert doc['source_id'] == target['source_id'] and doc['id'] == target['document_id']
    assert doc['body_hash'] == target['body_hash'] == hashlib.sha256(doc['body'].encode()).hexdigest()
    command_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'owner-full-reprocess22:' + targets_hash + ':' + target['id'] + ':' + pipeline))
    lease = str(uuid.uuid5(uuid.NAMESPACE_URL, command_id + ':lease'))
    sp, jo, cmd = lit(space) + '::uuid', lit(target['id']), lit(command_id) + '::uuid'
    request = {'execution_path': 'owner_full_reprocess_standard_ledger', 'targets_sha256': targets_hash,
               'job_id': target['id'], 'body_hash': target['body_hash'], 'pipeline': pipeline,
               'original_updated_at': target['updated_at'], 'owner_instruction': 'Die 22 Quellen ganz normal durch die Pipeline verarbeiten.'}
    query = 'BEGIN ISOLATION LEVEL SERIALIZABLE; DO $claim$ DECLARE s public.wm_spaces; c public.wm_processing_config; j public.wm_jobs; old public.wm_job_decisions; r jsonb; n integer; BEGIN '
    query += 'SELECT * INTO STRICT s FROM wm_spaces WHERE id=' + sp + ' FOR UPDATE; '
    query += 'SELECT * INTO STRICT c FROM wm_processing_config WHERE space_id=' + sp + ' FOR UPDATE; '
    query += "IF s.state NOT IN ('draft','active') OR NOT c.enabled OR c.pipeline IS DISTINCT FROM " + lit(pipeline) + " THEN RAISE EXCEPTION 'Normal ledger config changed'; END IF; "
    query += 'SELECT * INTO STRICT j FROM wm_jobs WHERE space_id=' + sp + ' AND id=' + jo + ' FOR UPDATE; '
    query += 'IF j.document_id IS DISTINCT FROM ' + lit(target['document_id']) + ' OR j.source_id IS DISTINCT FROM ' + lit(target['source_id']) + ' OR NOT EXISTS(SELECT 1 FROM wm_archive_documents WHERE space_id=' + sp + ' AND id=j.document_id AND source_id=j.source_id AND event_date=j.event_date AND body_hash=' + lit(target['body_hash']) + ") THEN RAISE EXCEPTION 'Target original changed'; END IF; "
    query += 'IF EXISTS(SELECT 1 FROM wm_jobs WHERE space_id=' + sp + ' AND id<>' + jo + " AND state IN ('running','prepared')) THEN RAISE EXCEPTION 'Another job is active'; END IF; "
    query += 'SELECT * INTO old FROM wm_job_decisions WHERE space_id=' + sp + ' AND command_id=' + cmd + '; '
    query += 'IF FOUND THEN '
    query += "IF old.actor_id<>s.owner_id OR old.action<>'retry' OR old.request IS DISTINCT FROM " + lit(json.dumps(request, ensure_ascii=False)) + "::jsonb OR j.lease_token::text IS DISTINCT FROM old.result->>'lease_token' OR j.expected_revision<>s.revision OR j.pipeline IS DISTINCT FROM c.pipeline OR j.state NOT IN ('running','review') THEN RAISE EXCEPTION 'Audited run changed'; END IF; "
    query += "UPDATE wm_jobs SET state='running',reason=null,lease_until=clock_timestamp()+interval '30 minutes',updated_at=clock_timestamp() WHERE space_id=" + sp + ' AND id=' + jo + '; '
    query += 'ELSE '
    query += "IF j.state<>'review' OR j.reason<>'provider_outcome_unknown' OR j.updated_at IS DISTINCT FROM " + lit(target['updated_at']) + "::timestamptz THEN RAISE EXCEPTION 'Original job changed'; END IF; "
    query += 'SELECT count(*) INTO n FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + '; '
    query += 'IF n<>(SELECT coalesce(max(call_index)+1,0) FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + ') OR EXISTS(SELECT 1 FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + " AND response_json IS NULL) THEN RAISE EXCEPTION 'Old call history incomplete'; END IF; "
    query += "r:=jsonb_build_object('command_id'," + cmd + ",'lease_token'," + lit(lease) + ",'revision',s.revision,'pipeline',c.pipeline,'start_index',n); "
    query += "INSERT INTO wm_job_decisions(space_id,command_id,job_id,actor_id,action,reason,request,previous_job,result) VALUES(" + sp + ',' + cmd + ',' + jo + ",s.owner_id,'retry','Ausdruecklich beauftragter vollstaendiger regulaerer Neulauf mit chronologischer Integration'," + lit(json.dumps(request, ensure_ascii=False)) + '::jsonb,to_jsonb(j),r); '
    query += "UPDATE wm_jobs SET state='running',reason=null,pipeline=c.pipeline,expected_revision=s.revision,lease_token=" + lit(lease) + "::uuid,lease_until=clock_timestamp()+interval '30 minutes',attempts=attempts+1,updated_at=clock_timestamp() WHERE space_id=" + sp + ' AND id=' + jo + '; '
    query += 'END IF; END $claim$; SELECT result FROM wm_job_decisions WHERE space_id=' + sp + ' AND command_id=' + cmd + '; COMMIT;'
    return json.loads(sql(query))


def reviewed_claim(space, target, targets_hash, execute=False):
    """One full normal attempt after the exact failed output was content-reviewed."""
    assert target['id'] in REVIEWED_FAILURES, 'Only the reviewed sources are eligible'
    reviewed = REVIEWED_FAILURES[target['id']]
    value = snapshot(space, target['id'], persist_errors=execute); doc = value['document']; job = value['job']
    assert job['space_id'] == space and job['id'] == target['id']
    assert doc['id'] == target['document_id'] and doc['source_id'] == target['source_id']
    assert doc['body_hash'] == target['body_hash'] == hashlib.sha256(doc['body'].encode()).hexdigest()
    pipeline = value['config']['pipeline']
    previous = str(uuid.uuid5(uuid.NAMESPACE_URL, 'owner-full-reprocess22:' + targets_hash + ':' + target['id'] + ':' + pipeline))
    binding = ':'.join((targets_hash, previous, target['id'], target['body_hash'],
                        str(reviewed['revision']), reviewed['updated_at'], reviewed['response_hash']))
    command_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'owner-full-reprocess22-reviewed:' + binding))
    lease = str(uuid.uuid5(uuid.NAMESPACE_URL, command_id + ':lease'))
    request = {'execution_path': 'owner_full_reprocess_standard_ledger', 'targets_sha256': targets_hash,
               'job_id': target['id'], 'body_hash': target['body_hash'], 'pipeline': pipeline,
               'previous_command_id': previous, 'reviewed_failure': reviewed,
               'owner_instruction': 'Die 22 Quellen ganz normal durch die Pipeline verarbeiten.',
               'reviewed_attempt_limit': 1}
    result = {'command_id': command_id, 'lease_token': lease, 'revision': reviewed['revision'],
              'pipeline': pipeline, 'start_index': reviewed['start_index'], 'cache_scope': command_id,
              'previous_command_id': previous}
    if reviewed.get('token_override'):
        result['token_override'] = reviewed['token_override']
    sp, jo, cmd = lit(space) + '::uuid', lit(target['id']), lit(command_id) + '::uuid'
    lock = ' FOR UPDATE' if execute else ''
    query = 'BEGIN ISOLATION LEVEL SERIALIZABLE' + ('' if execute else ' READ ONLY') + '; '
    query += 'DO $reviewed$ DECLARE s public.wm_spaces; c public.wm_processing_config; j public.wm_jobs; prior public.wm_job_decisions; old public.wm_job_decisions; n integer; BEGIN '
    query += 'SELECT * INTO STRICT s FROM wm_spaces WHERE id=' + sp + lock + '; '
    query += 'SELECT * INTO STRICT c FROM wm_processing_config WHERE space_id=' + sp + lock + '; '
    query += "IF s.state NOT IN ('draft','active') OR s.revision<>" + str(reviewed['revision']) + " OR NOT c.enabled OR c.pipeline IS DISTINCT FROM " + lit(pipeline) + " THEN RAISE EXCEPTION 'Reviewed context changed'; END IF; "
    query += 'SELECT * INTO STRICT j FROM wm_jobs WHERE space_id=' + sp + ' AND id=' + jo + lock + '; '
    query += 'IF j.document_id IS DISTINCT FROM ' + lit(target['document_id']) + ' OR j.source_id IS DISTINCT FROM ' + lit(target['source_id']) + ' OR NOT EXISTS(SELECT 1 FROM wm_archive_documents WHERE space_id=' + sp + ' AND id=j.document_id AND source_id=j.source_id AND event_date=j.event_date AND body_hash=' + lit(target['body_hash']) + ") THEN RAISE EXCEPTION 'Reviewed original changed'; END IF; "
    query += 'IF EXISTS(SELECT 1 FROM wm_jobs WHERE space_id=' + sp + ' AND id<>' + jo + " AND state IN ('running','prepared')) THEN RAISE EXCEPTION 'Another job is active'; END IF; "
    query += 'SELECT * INTO STRICT prior FROM wm_job_decisions WHERE space_id=' + sp + ' AND command_id=' + lit(previous) + '::uuid; '
    query += "IF prior.actor_id<>s.owner_id OR prior.job_id<>j.id OR prior.action<>'retry' OR prior.request->>'execution_path' IS DISTINCT FROM 'owner_full_reprocess_standard_ledger' OR prior.request->>'targets_sha256' IS DISTINCT FROM " + lit(targets_hash) + " OR prior.request->>'body_hash' IS DISTINCT FROM " + lit(target['body_hash']) + " OR (prior.result->>'revision')::bigint IS DISTINCT FROM " + str(reviewed['revision']) + " OR (prior.result->>'start_index')::integer IS DISTINCT FROM 1 OR prior.result->>'pipeline' IS DISTINCT FROM c.pipeline THEN RAISE EXCEPTION 'Previous reviewed attempt changed'; END IF; "
    query += 'IF NOT EXISTS(SELECT 1 FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + " AND call_index=" + str(reviewed['start_index']-1) + " AND request_hash=" + lit(reviewed['request_hash']) + ' AND response_hash=' + lit(reviewed['response_hash']) + " AND response_json IS NOT NULL) THEN RAISE EXCEPTION 'Reviewed response changed'; END IF; "
    if reviewed.get('token_override'):
        query += 'IF NOT EXISTS(SELECT 1 FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + " AND call_index=1 AND actual_micro_usd=149115 AND request_json::jsonb->>'max_tokens'='24000' AND response_json::jsonb->>'terminal_status'='incomplete' AND response_json::jsonb->>'incomplete_reason'='max_output_tokens' AND response_json::jsonb->>'usage_final'='true') THEN RAISE EXCEPTION 'Known token completion changed'; END IF; "
    query += 'SELECT count(*) INTO n FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + '; '
    query += 'IF n<>(SELECT coalesce(max(call_index)+1,0) FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + ") THEN RAISE EXCEPTION 'Call history is not contiguous'; END IF; "
    query += 'SELECT * INTO old FROM wm_job_decisions WHERE space_id=' + sp + ' AND command_id=' + cmd + '; '
    query += 'IF FOUND THEN '
    query += "IF old.actor_id<>s.owner_id OR old.job_id<>j.id OR old.action<>'retry' OR old.request IS DISTINCT FROM " + lit(json.dumps(request, ensure_ascii=False)) + '::jsonb OR old.result IS DISTINCT FROM ' + lit(json.dumps(result)) + "::jsonb OR j.lease_token::text IS DISTINCT FROM old.result->>'lease_token' OR j.expected_revision IS DISTINCT FROM " + str(reviewed['revision']) + " OR j.pipeline IS DISTINCT FROM c.pipeline OR j.attempts<>3 OR NOT (j.state='running' OR (j.state='review' AND j.reason='provider_outcome_unknown')) THEN RAISE EXCEPTION 'Reviewed attempt ended or changed; no further full attempt'; END IF; "
    if reviewed.get('token_override'):
        query += "IF j.state='review' AND EXISTS(SELECT 1 FROM wm_model_calls WHERE space_id=" + sp + ' AND job_id=' + jo + " AND call_index>=2 AND response_json::jsonb->>'terminal_status'='incomplete') THEN RAISE EXCEPTION 'Reviewed token attempt already ended; no new attempt'; END IF; "
    if execute:
        query += "UPDATE wm_jobs SET state='running',reason=null,lease_until=clock_timestamp()+interval '30 minutes',updated_at=clock_timestamp() WHERE space_id=" + sp + ' AND id=' + jo + '; '
    query += 'ELSE '
    query += "IF j.state<>'review' OR j.reason<>" + lit(reviewed.get('reason', 'validation_failed')) + " OR j.attempts<>2 OR j.prepared_payload IS NOT NULL OR j.expected_revision IS DISTINCT FROM " + str(reviewed['revision']) + " OR j.pipeline IS DISTINCT FROM c.pipeline OR j.lease_token::text IS DISTINCT FROM prior.result->>'lease_token' OR j.updated_at IS DISTINCT FROM " + lit(reviewed['updated_at']) + "::timestamptz OR n<>" + str(reviewed['start_index']) + " OR EXISTS(SELECT 1 FROM wm_model_calls WHERE space_id=" + sp + ' AND job_id=' + jo + " AND response_json IS NULL) THEN RAISE EXCEPTION 'Content-reviewed failed state changed'; END IF; "
    if execute:
        query += "INSERT INTO wm_job_decisions(space_id,command_id,job_id,actor_id,action,reason,request,previous_job,result) VALUES(" + sp + ',' + cmd + ',' + jo + ",s.owner_id,'retry','Genau ein vollstaendiger regulaerer Neulauf nach expliziter Inhaltspruefung; kein Schnellretry'," + lit(json.dumps(request, ensure_ascii=False)) + '::jsonb,to_jsonb(j),' + lit(json.dumps(result)) + '::jsonb); '
        query += "UPDATE wm_jobs SET state='running',reason=null,lease_token=" + lit(lease) + "::uuid,lease_until=clock_timestamp()+interval '30 minutes',attempts=3,updated_at=clock_timestamp() WHERE space_id=" + sp + ' AND id=' + jo + '; '
    query += 'END IF; END $reviewed$; SELECT ' + lit(json.dumps(result)) + '::jsonb; COMMIT;'
    return json.loads(sql(query, persist_errors=execute))


def context_capture(*, persist_errors):
    path = '/app/.local/projections-rc1-20260919/worker-reprocess22/' + TOKEN_FAILURE['job_id'] + '/attempts/' + CONTEXT_ATTEMPT + '/context-capture/result.json'
    raw = json.loads(command(['docker', 'exec', CT, 'python', '-B', '-c',
                              'from pathlib import Path; print(Path(' + repr(path) + ').read_text())'],
                             persist_errors=persist_errors))
    keys = ('phase', 'name', 'job', 'revision', 'prompt_sha256', 'schema_sha256', 'prompt_chars',
            'prompt_utf8_bytes', 'schema_utf8_bytes', 'max_output_tokens', 'framing_tokens',
            'conservative_total_tokens', 'limit', 'guard_rejected', 'search_snapshot_id')
    capture = {key: raw[key] for key in keys}
    assert capture['phase'] == 'captured' and capture['name'] == 'compact-0'
    assert capture['job'] == TOKEN_FAILURE['job_id'] and capture['revision'] == 355
    assert {key: capture[key] for key in CONTEXT_CAPTURE} == CONTEXT_CAPTURE
    assert capture['limit'] == 1050000 and capture['framing_tokens'] == 4096 and capture['guard_rejected'] is True
    for key in ('prompt_sha256', 'schema_sha256'):
        assert len(capture[key]) == 64 and set(capture[key]) <= set('0123456789abcdef')
    assert all(type(capture[key]) is int and capture[key] > 0 for key in
               ('prompt_chars', 'prompt_utf8_bytes', 'schema_utf8_bytes', 'max_output_tokens'))
    assert capture['max_output_tokens'] <= 64000
    assert capture['conservative_total_tokens'] == (capture['prompt_utf8_bytes'] + capture['schema_utf8_bytes']
                                                   + 4096 + capture['max_output_tokens']) > 1050000
    return capture


def context_claim(space, target, targets_hash, execute=False):
    """Resume the same known attempt; never create another full-run/cost boundary."""
    assert target['id'] == TOKEN_FAILURE['job_id'], 'Only the reviewed context source is eligible'
    value = snapshot(space, target['id'], persist_errors=execute); doc, job = value['document'], value['job']
    assert job['id'] == target['id'] and job['space_id'] == space
    assert doc['id'] == target['document_id'] and doc['source_id'] == target['source_id']
    assert doc['body_hash'] == target['body_hash'] == hashlib.sha256(doc['body'].encode()).hexdigest()
    assert value['config']['pipeline'] == CONTEXT_PIPELINE
    capture = context_capture(persist_errors=execute)
    capture_hash = hashlib.sha256(json.dumps(capture, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    binding = ':'.join((targets_hash, target['id'], target['body_hash'], CONTEXT_ATTEMPT,
                        CONTEXT_FAILURE['updated_at'], CONTEXT_FAILURE['calls_hash'], capture_hash))
    command_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'owner-reprocess22-context-continuation:' + binding))
    approval = {'execution_path': 'owner_full_reprocess_context_continuation', 'command_id': command_id,
                'attempt_command_id': CONTEXT_ATTEMPT, 'job_id': target['id'], 'revision': 355,
                'pipeline': CONTEXT_PIPELINE, 'targets_sha256': targets_hash, 'body_hash': target['body_hash'],
                'failure_updated_at': CONTEXT_FAILURE['updated_at'], 'calls_hash': CONTEXT_FAILURE['calls_hash'],
                'lease_token': job['lease_token'], 'next_new_call_index': 125, 'capture': capture}
    sp, jo, cmd = lit(space) + '::uuid', lit(target['id']), lit(command_id) + '::uuid'
    lock = ' FOR UPDATE' if execute else ''
    query = 'BEGIN ISOLATION LEVEL SERIALIZABLE' + ('' if execute else ' READ ONLY') + '; '
    query += 'DO $context$ DECLARE s public.wm_spaces; c public.wm_processing_config; j public.wm_jobs; prior public.wm_job_decisions; old public.wm_job_decisions; n integer; h text; BEGIN '
    query += 'SELECT * INTO STRICT s FROM wm_spaces WHERE id=' + sp + lock + '; '
    query += 'SELECT * INTO STRICT c FROM wm_processing_config WHERE space_id=' + sp + lock + '; '
    query += "IF s.state NOT IN ('draft','active') OR s.revision<>355 OR NOT c.enabled OR c.pipeline IS DISTINCT FROM " + lit(CONTEXT_PIPELINE) + " THEN RAISE EXCEPTION 'Context continuation changed'; END IF; "
    query += 'SELECT * INTO STRICT j FROM wm_jobs WHERE space_id=' + sp + ' AND id=' + jo + lock + '; '
    query += 'IF j.document_id IS DISTINCT FROM ' + lit(target['document_id']) + ' OR j.source_id IS DISTINCT FROM ' + lit(target['source_id']) + " OR j.expected_revision IS DISTINCT FROM 355 OR j.attempts<>3 OR j.prepared_payload IS NOT NULL OR j.pipeline IS DISTINCT FROM c.pipeline OR NOT EXISTS(SELECT 1 FROM wm_archive_documents WHERE space_id=" + sp + ' AND id=j.document_id AND source_id=j.source_id AND event_date=j.event_date AND body_hash=' + lit(target['body_hash']) + ") THEN RAISE EXCEPTION 'Context original or attempt changed'; END IF; "
    query += 'IF EXISTS(SELECT 1 FROM wm_jobs WHERE space_id=' + sp + ' AND id<>' + jo + " AND state IN ('running','prepared')) THEN RAISE EXCEPTION 'Another job is active'; END IF; "
    query += 'SELECT * INTO STRICT prior FROM wm_job_decisions WHERE space_id=' + sp + ' AND command_id=' + lit(CONTEXT_ATTEMPT) + '::uuid; '
    query += "IF prior.actor_id<>s.owner_id OR prior.job_id<>j.id OR prior.action<>'retry' OR prior.request->>'execution_path' IS DISTINCT FROM 'owner_full_reprocess_standard_ledger' OR prior.request->>'targets_sha256' IS DISTINCT FROM " + lit(targets_hash) + " OR prior.request->>'body_hash' IS DISTINCT FROM " + lit(target['body_hash']) + " OR prior.result->>'command_id' IS DISTINCT FROM " + lit(CONTEXT_ATTEMPT) + " OR prior.result->>'cache_scope' IS DISTINCT FROM " + lit(CONTEXT_ATTEMPT) + " OR (prior.result->>'revision')::bigint IS DISTINCT FROM 355 OR (prior.result->>'start_index')::integer IS DISTINCT FROM 2 OR prior.result->'token_override' IS DISTINCT FROM " + lit(json.dumps(TOKEN_FAILURE['token_override'])) + "::jsonb OR prior.result->>'pipeline' IS DISTINCT FROM c.pipeline OR j.lease_token::text IS DISTINCT FROM prior.result->>'lease_token' OR j.lease_token::text IS DISTINCT FROM " + lit(job['lease_token']) + " THEN RAISE EXCEPTION 'Known context attempt changed'; END IF; "
    query += 'SELECT count(*), encode(sha256(convert_to(string_agg(call_index::text||\':\'||request_hash||\':\'||response_hash||\':\'||actual_micro_usd::text,\'|\' ORDER BY call_index),\'UTF8\')),\'hex\') INTO n,h FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + ' AND call_index BETWEEN 2 AND 124; '
    query += 'IF n<>123 OR h IS DISTINCT FROM ' + lit(CONTEXT_FAILURE['calls_hash']) + ' OR (SELECT sum(actual_micro_usd) FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + ' AND call_index BETWEEN 2 AND 124) IS DISTINCT FROM 167049::bigint OR EXISTS(SELECT 1 FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + " AND call_index BETWEEN 2 AND 124 AND (response_json IS NULL OR actual_micro_usd IS NULL OR response_json::jsonb->>'stop_reason' IS DISTINCT FROM 'end_turn')) THEN RAISE EXCEPTION 'Known 123 responses changed'; END IF; "
    query += 'SELECT count(*) INTO n FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + '; '
    query += 'IF n<>(SELECT coalesce(max(call_index)+1,0) FROM wm_model_calls WHERE space_id=' + sp + ' AND job_id=' + jo + ") THEN RAISE EXCEPTION 'Context call history is not contiguous'; END IF; "
    query += 'SELECT * INTO old FROM wm_job_decisions WHERE space_id=' + sp + ' AND command_id=' + cmd + '; '
    query += "IF FOUND THEN IF old.actor_id<>s.owner_id OR old.job_id<>j.id OR old.action<>'retry' OR old.request IS DISTINCT FROM " + lit(json.dumps(approval, ensure_ascii=False)) + "::jsonb OR old.result IS DISTINCT FROM old.request OR NOT (j.state='running' OR (j.state='review' AND j.reason IN ('provider_outcome_unknown','transport_failed'))) THEN RAISE EXCEPTION 'Context continuation ended or changed; new semantic failure stays blocked'; END IF; ELSE "
    query += "IF j.state<>'review' OR j.reason<>'validation_failed' OR j.updated_at IS DISTINCT FROM " + lit(CONTEXT_FAILURE['updated_at']) + "::timestamptz OR n<>125 THEN RAISE EXCEPTION 'Reviewed context failure changed'; END IF; "
    if execute:
        query += "INSERT INTO wm_job_decisions(space_id,command_id,job_id,actor_id,action,reason,request,previous_job,result) VALUES(" + sp + ',' + cmd + ',' + jo + ",s.owner_id,'retry','Fortsetzung desselben belegten Versuchs mit exakter Kontextzaehlung; kein neuer Vollversuch'," + lit(json.dumps(approval, ensure_ascii=False)) + '::jsonb,to_jsonb(j),' + lit(json.dumps(approval, ensure_ascii=False)) + '::jsonb); '
    query += 'END IF; '
    if execute:
        query += "UPDATE wm_jobs SET state='running',reason=null,lease_until=clock_timestamp()+interval '30 minutes',updated_at=clock_timestamp() WHERE space_id=" + sp + ' AND id=' + jo + '; '
    query += 'END $context$; SELECT result || jsonb_build_object(\'context_continuation\',' + lit(json.dumps(approval, ensure_ascii=False)) + '::jsonb) FROM wm_job_decisions WHERE space_id=' + sp + ' AND command_id=' + lit(CONTEXT_ATTEMPT) + '::uuid; COMMIT;'
    return json.loads(sql(query, persist_errors=execute))


def adopt(space, target, artifact):
    expected = artifact['expected_revision']; sp = lit(space) + '::uuid'; jo = lit(target['id'])
    assert artifact['job_id'] == target['id'] and artifact['body_hash'] == target['body_hash']
    generation = artifact['generation']; review = artifact['review_id']
    assert len(generation['new_sources']) == 1 and generation['new_sources'][0]['id'] == target['id']
    query = 'BEGIN ISOLATION LEVEL SERIALIZABLE; DO $reprocess$ DECLARE s public.wm_spaces; d jsonb; BEGIN '
    query += 'SELECT * INTO STRICT s FROM wm_spaces WHERE id=' + sp + ' FOR UPDATE; '
    query += 'IF s.revision<>' + str(expected) + ' OR NOT EXISTS(SELECT 1 FROM wm_processing_config WHERE space_id=' + sp + ' AND enabled AND pipeline=' + lit(artifact['pipeline']) + ') OR NOT EXISTS(SELECT 1 FROM wm_jobs WHERE space_id=' + sp + ' AND id=' + jo + " AND state='running' AND lease_token=" + lit(artifact['lease_token']) + "::uuid AND updated_at=" + lit(artifact['expected_updated_at']) + "::timestamptz) OR NOT EXISTS(SELECT 1 FROM wm_job_decisions WHERE space_id=" + sp + ' AND command_id=' + lit(artifact['owner_reprocess_command']) + "::uuid AND actor_id=s.owner_id AND action='retry' AND result->>'lease_token'=" + lit(artifact['lease_token']) + ") THEN RAISE EXCEPTION 'Reprocessing base changed'; END IF; "
    query += 'PERFORM wm_pause_job(' + sp + ',' + jo + ',' + lit(artifact['lease_token']) + "::uuid,'context_changed'); "
    query += 'PERFORM wm_archive_note_put(' + sp + ',' + lit(json.dumps(artifact['note'], ensure_ascii=False)) + '::jsonb); '
    query += 'PERFORM wm_generation_stage(' + sp + ',' + lit(review) + '::uuid,' + str(expected) + ',' + lit('Reguläre Neuverarbeitung ' + target['id'][:8]) + ',' + lit(json.dumps(generation, ensure_ascii=False)) + '::jsonb,' + jo + '); '
    query += 'd:=wm_generation_decide(' + sp + ',' + lit(review) + '::uuid,s.owner_id,' + lit(artifact['command_id']) + '::uuid,' + str(expected) + ',' + lit(generation['review_sha256']) + ",'accept'," + lit(artifact['reason']) + '); '
    query += "IF d->>'state' IS DISTINCT FROM 'accepted' THEN RAISE EXCEPTION 'Generation was not accepted'; END IF; END $reprocess$; COMMIT;"
    sql(query)
    after = snapshot(space, target['id'])
    assert after['space']['revision'] == expected + 1 and after['job']['state'] == 'applied'
    return expected + 1


def run(bundle):
    targets = bundle['targets']; space = bundle['space_id']; action = bundle['action']
    assert len(targets) == 22 and len({t['id'] for t in targets}) == 22
    selected = [t for t in targets if not bundle.get('job_prefix') or t['id'].startswith(bundle['job_prefix'])]
    assert selected
    if action == 'preflight':
        values = [snapshot(space, t['id'], persist_errors=False) for t in selected]
        for value, target in zip(values, selected): guard(value, target, False)
        print(json.dumps({'phase': 'preflight', 'target_count': len(selected), 'revision': values[0]['space']['revision']}))
        return
    assert action in ('claim', 'import', 'one', 'all', 'reviewed-preflight', 'reviewed-claim', 'reviewed-one',
                      'context-preflight', 'context-claim', 'context-one')
    check = 'import os,json,hashlib;print(json.dumps({"flags":{k:os.environ.get(k) for k in ("MEMORY_READ_ONLY","MEMORY_AUTOMATIC_ENABLED","MEMORY_INTAKE_ENABLED","MEMORY_QA_ENABLED","MEMORY_ORIGINAL_DELETION_ENABLED")},"hashes":{k:hashlib.sha256(open("/app/"+k,"rb").read()).hexdigest() for k in ("memory.py","openai_provider.py")}}))'
    runtime = json.loads(command(['docker', 'exec', CT, 'python', '-B', '-c', check], persist_errors=not action.endswith('preflight')))
    assert runtime['flags'] == {'MEMORY_READ_ONLY': '1', 'MEMORY_AUTOMATIC_ENABLED': '0', 'MEMORY_INTAKE_ENABLED': '0', 'MEMORY_QA_ENABLED': '0', 'MEMORY_ORIGINAL_DELETION_ENABLED': '0'}
    assert runtime['hashes'] == {'memory.py': 'e822eb293d6d87cc74f0df5671e4d656c060c81ccce6502860b7c142803c2316', 'openai_provider.py': 'fe6dc8e07c5e90bacca8e1b6b364b97fab2715d1589209ea457a909d4a92c0d3'}
    if action.startswith('reviewed-'):
        assert len(selected) == 1 and selected[0]['id'] in REVIEWED_FAILURES
    if action.startswith('context-'):
        assert len(selected) == 1 and selected[0]['id'] == TOKEN_FAILURE['job_id']
    if action in ('reviewed-preflight', 'context-preflight'):
        claim = context_claim if action.startswith('context-') else reviewed_claim
        result = claim(space, selected[0], bundle['targets_sha256'])
        print(json.dumps({'phase': action.replace('-', '_'), 'job': selected[0]['id'][:8], **result}), flush=True)
        return
    os.umask(0o077); ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (ROOT / 'runner.lock').open('a'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for name, encoded in bundle['code'].items():
        assert name in ('paid_calls.py', 'container_worker.py')
        path = ROOT / name; path.write_bytes(base64.b64decode(encoded)); path.chmod(0o644)
    command(['docker', 'exec', CT, 'mkdir', '-p', '/tmp/owner-reprocess22'])
    for name in bundle['code']:
        command(['docker', 'exec', '-i', CT, 'python', '-c', CODE_WRITER, name], (ROOT / name).read_bytes())
    state_path = ROOT / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'applied': [], 'targets_sha256': bundle['targets_sha256']}
    assert state['targets_sha256'] == bundle['targets_sha256']
    selected = [t for t in selected if t['id'] not in state['applied']]
    if action in ('claim', 'import', 'one'): selected = selected[:1]
    for target in selected:
        if action.startswith('context-'):
            run_info = context_claim(space, target, bundle['targets_sha256'], execute=True)
        elif action.startswith('reviewed-'):
            run_info = reviewed_claim(space, target, bundle['targets_sha256'], execute=True)
        else:
            run_info = claim_run(space, target, bundle['targets_sha256'])
        state.setdefault('runs', {})[target['id']] = run_info
        save_state(state_path, state)
        if action in ('claim', 'reviewed-claim', 'context-claim'):
            print(json.dumps({'phase': 'claimed', 'job': target['id'][:8],
                              'revision': run_info['revision'], 'start_index': run_info['start_index']}), flush=True)
            continue
        value = snapshot(space, target['id'])
        assert value['job']['state'] == 'running' and value['job']['lease_token'] == run_info['lease_token']
        assert value['document']['body_hash'] == target['body_hash'] and value['config']['enabled']
        assert value['space']['revision'] == run_info['revision']
        value['revision'], value['run'] = run_info['revision'], run_info
        value['action'] = action
        print(json.dumps({'phase': 'processing', 'job': target['id'][:8], 'revision': value['revision']}), flush=True)
        stderr_path = ROOT / (target['id'][:8] + ('-' + run_info['cache_scope'] if run_info.get('cache_scope') else '') + '.stderr')
        with stderr_path.open('wb') as errors:
            process = subprocess.Popen(['docker', 'exec', '-i', CT, 'python', '-B', '/tmp/owner-reprocess22/container_worker.py'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
            process.stdin.write(json.dumps(value, ensure_ascii=False).encode()); process.stdin.close()
            last = None
            for line in process.stdout:
                event = json.loads(line); print(json.dumps(event), flush=True); last = event
            result = process.wait()
        if action == 'import' and result == 0 and last and last.get('state') == 'imported':
            print(json.dumps({'phase': 'imported', 'job': target['id'][:8], 'calls': last['imported'],
                              'actual_micro_usd': last['actual_micro_usd']}), flush=True)
            continue
        if result or not last or last.get('state') != 'prepared':
            print(json.dumps({'phase': 'stopped', 'job': target['id'][:8], 'returncode': result}), flush=True)
            raise SystemExit(2)
        artifact_path = last['artifact']
        assert artifact_path.endswith('/' + target['id'] + '/prepared.json') and '..' not in artifact_path
        artifact = json.loads(command(['docker', 'exec', CT, 'cat', artifact_path]))
        revision = adopt(space, target, artifact)
        state['applied'].append(target['id']); save_state(state_path, state)
        print(json.dumps({'phase': 'applied', 'job': target['id'][:8], 'revision': revision,
                          'batch_applied': len(state['applied']), 'actual_micro_usd': last['actual_micro_usd']}), flush=True)
