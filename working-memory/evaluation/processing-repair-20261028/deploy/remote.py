"""Guarded existing-service deployment. Invoked by run.py through SSH stdin.

No provider requests, secret output, queue reset or direct journal/job updates.
Failure deliberately leaves the already authorised processing hold in place.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

CT = 'dashboard-memory-canonical-draft-canonical-draft-1'
DB = 'dashboard-supabase-20261003-db-1'
SERVICE = 'canonical-draft'
ROOT = Path('/opt/dashboard-memory-canonical-draft')
RUN = ROOT / '.local/recovery/processing-repair-20261028-lead/deployment'
OLD_TAG = 'dashboard-memory:release3-20261013'
NEW_TAG = 'dashboard-memory:processing-repair-20261028'
OLD_HASHES = {'memory.py': 'a09be9c831d2e213858a3d9e2746b4c4bc98e540c03ec4dd1023f5f1b11d4c71',
              'openai_provider.py': 'ebdcb0bb6944f144a34e438103877e68ad66fa89de00de9dca15c4cdef97d5ad'}
HOLD_FLAGS = {'MEMORY_READ_ONLY': '1', 'MEMORY_AUTOMATIC_ENABLED': '0',
              'MEMORY_INTAKE_ENABLED': '0', 'MEMORY_QA_ENABLED': '0',
              'MEMORY_ORIGINAL_DELETION_ENABLED': '0'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_routines():
    expected = {'wm_archive_note_put': 'c17418d2c73818d29a03c0eb224eb0715fa4837a346217f23efcab2ab9aa6e5a',
                'wm_generation_decide': '46efda4980e374b72ed0196f2eb50f42d7739c9b2d018bf3e2f98a1bf1f4d02c',
                'wm_generation_stage': 'f9bd45f2f4f1e8da529260bbf0dfa5de4fccbd00ac227b1b36086e8d0bb35d3f'}
    definitions = data_query("BEGIN READ ONLY; SELECT json_object_agg(proname,pg_get_functiondef(oid)) FROM pg_proc WHERE proname IN ('wm_archive_note_put','wm_generation_decide','wm_generation_stage'); COMMIT;")
    assert {name: sha(value.encode()) for name, value in definitions.items()} == expected, 'Reviewed RPC changed'


def lit(value):
    value = base64.b64encode(str(value).encode()).decode()
    return "convert_from(decode('" + value + "','base64'),'UTF8')"


def call(args, data=None, timeout=180):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        # Never expose SQL literals, source text, Compose output or private diagnostics.
        if RUN.exists():
            target = RUN / ('error-' + str(time.time_ns()) + '.log')
            target.write_bytes(result.stderr + result.stdout)
            target.chmod(0o600)
        raise RuntimeError('Command failed; private server diagnostic retained')
    return result.stdout


def sql(query):
    return call(['docker', 'exec', '-i', DB, 'psql', '-U', 'postgres', '-d', 'postgres',
                 '-XqAt', '-v', 'ON_ERROR_STOP=1'], query.encode(), timeout=180).decode().strip()


def data_query(query):
    return json.loads(sql(query))


def snapshot(space):
    sp = lit(space) + '::uuid'
    return data_query("BEGIN READ ONLY; SELECT json_build_object('space',(SELECT row_to_json(s) FROM wm_spaces s WHERE id=" + sp +
                      "),'config',(SELECT row_to_json(c) FROM wm_processing_config c WHERE space_id=" + sp +
                      "),'jobs',(SELECT coalesce(json_agg(x),'[]') FROM (SELECT id,state,reason,updated_at FROM wm_jobs WHERE space_id=" + sp +
                      " AND (id LIKE '7b4057c2%' OR id LIKE 'a77d73b4%'))x),'busy',(SELECT count(*) FROM wm_jobs WHERE space_id=" + sp +
                      " AND state IN ('running','prepared')),'calls',(SELECT count(*) FROM wm_model_calls WHERE space_id=" + sp +
                      "),'questions',(SELECT count(*) FROM wm_question_calls WHERE space_id=" + sp + ")); COMMIT;")


def write_private(path, value):
    tmp = path.with_name(path.name + '.new')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(path)


def held_compose():
    return ['docker', 'compose', '-f', str(ROOT / 'compose.yaml'), '-f', str(RUN / 'hold.yaml'),
            'up', '-d', '--no-deps', '--no-build', '--pull', 'never', SERVICE]


def health():
    for _ in range(45):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8798/health', timeout=5) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError('Service health not confirmed; processing remains held')


def pipeline():
    return call(['docker', 'exec', CT, 'python', '-B', '-c',
                 'from canonical_worker import pipeline_version;from openai_provider import MODEL;print(pipeline_version(MODEL))']).decode().strip()


def flags():
    names = tuple(HOLD_FLAGS)
    source = 'import json,os;print(json.dumps({k:os.environ.get(k) for k in ' + repr(names) + '}))'
    return json.loads(call(['docker', 'exec', CT, 'python', '-B', '-c', source]))


def verify_hold():
    assert flags() == HOLD_FLAGS


def preserve_original_flags(record):
    if 'original_flags' not in record:
        record['original_flags'] = flags()
    missing = set(HOLD_FLAGS) - set(record['original_flags'])
    if missing:
        # Older first-attempt records have four original flags. Read only the
        # missing setting from original Compose, never from the held container.
        config = json.loads(call(['docker', 'compose', '-f', str(ROOT / 'compose.yaml'),
                                  'config', '--format', 'json']))
        environment = config['services'][SERVICE]['environment']
        for name in missing:
            assert name in environment, 'Missing original Compose flag'
            record['original_flags'][name] = str(environment[name])


def hold_yaml():
    return ('services:\n  canonical-draft:\n    environment:\n' +
            ''.join('      ' + name + ': "' + value + '"\n' for name, value in HOLD_FLAGS.items()))


def verify_code(expected):
    script = 'import hashlib,json;print(json.dumps({n:hashlib.sha256(open("/app/"+n,"rb").read()).hexdigest() for n in ' + repr(list(expected)) + '}))'
    actual = json.loads(call(['docker', 'exec', CT, 'python', '-B', '-c', script]))
    if actual != expected:
        raise RuntimeError('Runtime code hash drift')


def run(bundle):
    action = bundle['action']
    before = bundle['original_config']
    space = before['space_id']
    initial = bundle['steps'][0]['stage_request']['expected_revision']
    new_pipeline = bundle['new_pipeline']
    expected = {name: sha(base64.b64decode(value)) for name, value in bundle['files'].items()}
    if action == 'preflight':
        state = snapshot(space)
        verify_code(OLD_HASHES)
        verify_routines()
        assert state['space']['revision'] == initial and not state['config']['enabled'] and not state['busy']
        assert state['config'] == {**before, 'enabled': False}
        assert pipeline() == before['pipeline']
        print(json.dumps({'phase': 'preflight', 'revision': initial, 'code_hashes': OLD_HASHES, 'paused': True}))
        return
    if action not in ('deploy', 'adopt', 'resume', 'verify'):
        raise ValueError('Unsupported action')
    os.umask(0o077)
    RUN.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = open('/run/lock/dashboard-job-backup.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    record_path = RUN / 'state.json'
    if record_path.exists():
        record = json.loads(record_path.read_text())
        assert record['space_id'] == space and record['new_pipeline'] == new_pipeline and record['hashes'] == expected
    else:
        assert action == 'deploy'
        record = {'space_id': space, 'base_revision': initial, 'original_config': before,
                  'new_pipeline': new_pipeline, 'hashes': expected, 'adopted': []}
    if action == 'deploy':
        assert not record.get('deployed'), 'Already deployed; use adopt or verify'
        state = snapshot(space)
        assert state['space']['revision'] == initial and state['config'] == {**before, 'enabled': False} and not state['busy']
        verify_code(OLD_HASHES)
        assert pipeline() == before['pipeline']
        image = call(['docker', 'inspect', '--format', '{{.Config.Image}}', CT]).decode().strip()
        assert image == OLD_TAG
        backup = ROOT / '.local/recovery/processing-repair-20261028-lead/production-before.dump'
        assert backup.is_file() and backup.stat().st_size > 1000000, 'Lead database backup missing'
        # Lead separately records successful full pg_restore readback; never claim a restored database here.
        record['backup_sha256'] = file_sha(backup)
        assert record['backup_sha256'] == '19662added3659ea456c68084ef76f2813998f98075d87ec849740244acd2178', 'Verified backup drift'
        verify_routines()
        current_image = call(['docker', 'inspect', '--format', '{{.Image}}', CT]).decode().strip()
        assert current_image == call(['docker', 'image', 'inspect', '--format', '{{.Id}}', OLD_TAG]).decode().strip() == 'sha256:fdf0d5e6b59c2985070d90122893037aac9887416948d349ec971b4a8d8cded6'
        compose = ROOT / 'compose.yaml'
        original = compose.read_bytes()
        assert original.decode().count('image: ' + OLD_TAG) == 1
        for name in (*expected, 'build-manifest.json'):
            source = ROOT / name
            if source.exists():
                if name in OLD_HASHES:
                    assert file_sha(source) == OLD_HASHES[name], 'Foreign host source changed'
                (RUN / (name + '.before')).write_bytes(source.read_bytes())
        (RUN / 'compose.yaml.before').write_bytes(original)
        (RUN / 'hold.yaml').write_text(hold_yaml())
        preserve_original_flags(record)
        write_private(record_path, record)
        call(held_compose())
        health()
        verify_hold()
        manifest = json.loads(call(['docker', 'exec', CT, 'cat', '/app/build-manifest.json']))
        assert all(manifest[k] == value for k, value in OLD_HASHES.items())
        contract = json.loads(call(['docker', 'exec', CT, 'cat', '/app/default_contract.json']))
        old_contract = dict(contract)
        old_hash, new_hash = before['pipeline'].split(':')[4], new_pipeline.split(':')[4]
        assert contract['pipeline_version'].count(old_hash) == 1
        contract['pipeline_version'] = contract['pipeline_version'].replace(old_hash, new_hash)
        assert {k: v for k, v in contract.items() if k != 'pipeline_version'} == {k: v for k, v in old_contract.items() if k != 'pipeline_version'}
        context = RUN / 'image'
        context.mkdir(exist_ok=True, mode=0o700)
        for name, value in bundle['files'].items():
            (context / name).write_bytes(base64.b64decode(value))
        (context / 'default_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
        for name in (*expected, 'default_contract.json'):
            manifest[name] = sha((context / name).read_bytes())
        (context / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (context / 'Dockerfile').write_text('FROM ' + OLD_TAG + '\nUSER root\nCOPY --chown=10001:10001 memory.py openai_provider.py default_contract.json build-manifest.json /app/\nUSER 10001:10001\n')
        call(['docker', 'build', '--pull=false', '-t', NEW_TAG, str(context)], timeout=180)
        checks = call(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python', NEW_TAG, '-I', '-B', '/app/offline_check.py'])
        (RUN / 'image-offline-check.txt').write_bytes(checks)
        for name in (*expected, 'default_contract.json', 'build-manifest.json'):
            target = ROOT / name
            tmp = target.with_name(name + '.deploy-new')
            tmp.write_bytes((context / name).read_bytes())
            tmp.replace(target)
        compose.write_bytes(original.replace(('image: ' + OLD_TAG).encode(), ('image: ' + NEW_TAG).encode()))
        call(held_compose())
        health()
        verify_hold()
        verify_code(expected)
        assert pipeline() == new_pipeline
        sp = lit(space) + '::uuid'
        q = "BEGIN ISOLATION LEVEL SERIALIZABLE; SELECT 1 FROM wm_spaces WHERE id=" + sp + " FOR UPDATE; SELECT 1 FROM wm_processing_config WHERE space_id=" + sp + " FOR UPDATE; "
        q += "SELECT 1/CASE WHEN EXISTS(SELECT 1 FROM wm_spaces WHERE id=" + sp + " AND revision=" + str(initial) + ") AND EXISTS(SELECT 1 FROM wm_processing_config WHERE space_id=" + sp + " AND pipeline=" + lit(before['pipeline']) + " AND NOT enabled) THEN 1 ELSE 0 END; "
        q += "UPDATE wm_processing_config SET pipeline=" + lit(new_pipeline) + " WHERE space_id=" + sp + "; COMMIT;"
        sql(q)
        record.update(deployed=True, image=NEW_TAG, calls_before=state['calls'], questions_before=state['questions'])
        write_private(record_path, record)
        print(json.dumps({'phase': 'deployed-held', 'pipeline': new_pipeline, 'hashes': expected, 'backup_sha256': record['backup_sha256']}))
    elif action == 'adopt':
        assert record.get('deployed') and not record.get('resumed')
        verify_code(expected)
        verify_routines()
        verify_hold()
        assert pipeline() == new_pipeline
        owner = snapshot(space)['space']['owner_id']
        for step in bundle['steps']:
            req, decision = step['stage_request'], step['decide_request']
            job, revision = req['job_id'], req['expected_revision']
            if job in record['adopted']:
                continue
            assert step['verified_payload']['review_sha256'] == decision['review_sha256']
            sp = lit(space) + '::uuid'
            q = 'BEGIN ISOLATION LEVEL SERIALIZABLE; DO $repair$ DECLARE n jsonb; g jsonb; d jsonb; BEGIN '
            q += 'PERFORM 1 FROM wm_spaces WHERE id=' + sp + ' FOR UPDATE; '
            q += "IF NOT EXISTS(SELECT 1 FROM wm_spaces WHERE id=" + sp + ' AND revision=' + str(revision) + ") OR NOT EXISTS(SELECT 1 FROM wm_processing_config WHERE space_id=" + sp + ' AND NOT enabled AND pipeline=' + lit(new_pipeline) + ") OR NOT EXISTS(SELECT 1 FROM wm_jobs WHERE space_id=" + sp + ' AND id=' + lit(job) + " AND state='review' AND reason='validation_failed' AND updated_at=" + lit(step['expected_job_updated_at']) + "::timestamptz) THEN RAISE EXCEPTION 'Adoption precondition changed'; END IF; "
            q += 'n:=public.wm_archive_note_put(' + sp + ',' + lit(json.dumps(step['note_put'], ensure_ascii=False)) + '::jsonb); '
            q += 'g:=public.wm_generation_stage(' + sp + ',' + lit(req['review_id']) + '::uuid,' + str(revision) + ',' + lit(req['label']) + ',' + lit(json.dumps(step['verified_payload'], ensure_ascii=False)) + '::jsonb,' + lit(job) + '); '
            q += 'd:=public.wm_generation_decide(' + sp + ',' + lit(req['review_id']) + '::uuid,' + lit(owner) + '::uuid,' + lit(decision['command_id']) + '::uuid,' + str(revision) + ',' + lit(decision['review_sha256']) + ',' + lit(decision['action']) + ',' + lit(decision['reason']) + '); '
            q += "IF d->>'state' IS DISTINCT FROM 'accepted' THEN RAISE EXCEPTION 'Generation not accepted'; END IF; END $repair$; COMMIT;"
            sql(q)
            after = snapshot(space)
            assert after['space']['revision'] == revision + 1
            assert next(x for x in after['jobs'] if x['id'] == job)['state'] == 'applied'
            assert after['calls'] == record['calls_before'] and after['questions'] == record['questions_before']
            record['adopted'].append(job)
            write_private(record_path, record)
            print(json.dumps({'phase': 'source-applied-held', 'job': job[:8], 'revision': revision + 1, 'review_sha256': decision['review_sha256']}), flush=True)
    elif action == 'resume':
        assert record.get('deployed') and len(record['adopted']) == 2 and not record.get('resumed')
        state = snapshot(space)
        assert state['space']['revision'] == initial + 2 and not state['config']['enabled'] and not state['busy']
        assert state['config'] == {**before, 'pipeline': new_pipeline, 'enabled': False}
        assert state['calls'] == record['calls_before'] and state['questions'] == record['questions_before']
        # Restore the exact original Compose flags; only its image reference changed.
        call(['docker', 'compose', '-f', str(ROOT / 'compose.yaml'), 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', SERVICE])
        health()
        assert pipeline() == new_pipeline
        assert flags() == record['original_flags'], 'Original service flags not restored'
        sql('BEGIN; SELECT 1 FROM wm_spaces WHERE id=' + lit(space) + '::uuid FOR UPDATE; SELECT 1/CASE WHEN EXISTS(SELECT 1 FROM wm_processing_config WHERE space_id=' + lit(space) + '::uuid AND pipeline=' + lit(new_pipeline) + ' AND NOT enabled) THEN 1 ELSE 0 END; UPDATE wm_processing_config SET enabled=' + ('true' if before['enabled'] else 'false') + ' WHERE space_id=' + lit(space) + '::uuid; COMMIT;')
        record['resumed'] = True
        write_private(record_path, record)
        print(json.dumps({'phase': 'resumed', 'revision': initial + 2, 'pipeline': new_pipeline}))
    else:
        state = snapshot(space)
        verify_code(expected)
        assert pipeline() == new_pipeline
        print(json.dumps({'phase': 'verify', 'revision': state['space']['revision'], 'enabled': state['config']['enabled'],
                          'jobs': [{'job': x['id'][:8], 'state': x['state'], 'reason': x['reason']} for x in state['jobs']],
                          'calls': state['calls'], 'questions': state['questions'], 'adopted': len(record['adopted'])}))
