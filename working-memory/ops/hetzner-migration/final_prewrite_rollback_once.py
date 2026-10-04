"""Late prewrite Source return on Mac. Imports are pure; future primary gates required.

No Target data rollback and never the early final_source_rollback_once.py. The
local --run-dir is PRIVATE/final-export-UTC; gate.run_dir is the matching host run.
All inputs in proof.refs are path/SHA references bound individually by the gate.
"""
import argparse
import ast
import base64
import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import urllib.error
import uuid
import final_phase_common as c
from final_writer_open_once import (PROBLEM, ROOT, LIVE, CANONICAL, DB, CLOSED,
    ORIGINAL, BASE, NGINX_SHA, SCOPES_SHA, ALIASES, HOST_FILES, SOURCE_ORIGIN,
    require, stamp, digest, sha_bytes, read_json, PreconditionsError, validate_host_binding)

QUERY_SHA = 'e8ca7870cc965f15fdf1c95ad9d8394a12b04e43eacc08ab49d70853be326254'
ACL_RESTORE_SHA = '26c34f43afa8408e933589b6ce705bf09bd3e36234904de81166b26dd1955f02'
OLD_DEPLOYMENT = 'dpl_84v5UqEaCs5TnRsb6QzahSNxeNxL'
FRONT_BUILD = Path('/private/tmp/hz-frontend-build-ejf6dx_r')
REFS = {'query', 'baseline', 'host_primary', 'acl_original', 'acl_frozen', 'acl_restore',
        'config', 'scopes_restore', 'scope_key', 'frontend', 'frontend_original_env',
        'project_link', 'nginx_original', 'nginx_maintenance', 'runtime'}
# Fixed actual table inventory, not a self-reported count or arbitrary query result.
TABLES = ('activity_log blockers cleanup_backup_20260708 commitments decisions embeddings '
          'eval_questions eval_results eval_runs inbox_items meeting_links meeting_topics meetings '
          'memory_metrics open_items open_loops project_meetings projects team_members todos transcript_chunks '
          'wm_archive_documents wm_archive_notes wm_conversations wm_generation_reviews wm_job_decisions '
          'wm_jobs wm_journal wm_model_calls wm_pipeline_recoveries wm_processing_config wm_question_calls '
          'wm_questions wm_search_documents wm_search_results wm_search_snapshots wm_source_deletion_checks '
          'wm_source_deletion_plan wm_source_deletion_versions wm_source_deletions '
          'wm_source_reimport_authorizations wm_source_versions wm_spaces').split()
# The inventory is verified against the actual hash-bound query bytes.


def private_error(error):
    body = error.read() if isinstance(error, urllib.error.HTTPError) else getattr(error, 'body', None)
    return c.private_failure('LATE_SOURCE_RETURN_STOP', error_type=type(error).__name__,
        primary_error=str(error), stdout=getattr(error, 'stdout', None), stderr=getattr(error, 'stderr', None),
        body=body, status=getattr(error, 'code', getattr(error, 'returncode', None)),
        headers=list(error.headers.items()) if getattr(error, 'headers', None) is not None else None,
        command=getattr(error, 'cmd', None), timeout=getattr(error, 'timeout', None))


def durable(run, name, value):
    fd = os.open(run/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())


def projection(value, names):
    require(isinstance(value, list) and len(value) == len(names), 'Business table coverage differs')
    require(sorted(row['table_name'] for row in value) == sorted(names), 'Missing/extra business table')
    for row in value:
        require(set(row) == {'table_name', 'rows', 'sha256'} and type(row['rows']) is int and row['rows'] >= 0
                and re.fullmatch('[a-f0-9]{64}', row['sha256']), 'Incomplete business fingerprint')
    return sorted(value, key=lambda row: row['table_name'])


def phase_gate(gate, now):
    require(gate.get('problem_id') == PROBLEM and gate.get('phase') == 'PREWRITE_SOURCE_ROLLBACK'
            and gate.get('decision') == 'CONTINUE_BOUNDED', 'Late return phase gate absent')
    require(re.fullmatch(r'/opt/dashboard-supabase-20261003/final-export-\d{8}T\d{6}Z', gate['run_dir']), 'Wrong return run')
    issued, expires = stamp(gate['issued_at']), stamp(gate['expires_at'])
    require(issued <= now < expires and 0 < (expires-issued).total_seconds() <= 600, 'Return gate stale')


def load(run, gate_path, ops, now):
    gate = read_json(gate_path); phase_gate(gate, now)
    require(run.name == Path(gate['run_dir']).name and run.parent == c.PRIVATE and not run.is_symlink(), 'Local run differs')
    path = run/'prewrite-source-rollback-proof.json'
    require(gate['receipt_hashes'].get(str(path)) == digest(path), 'Return proof SHA differs')
    proof = read_json(path)
    require(proof['problem_id'] == PROBLEM and proof['run_dir'] == gate['run_dir'], 'Proof run differs')
    require(0 <= (now-stamp(proof['observed_at'])).total_seconds() <= 300, 'Return proof stale')
    require(set(proof['refs']) == REFS, 'Complete actual return references required')
    values = {}
    for key, ref in proof['refs'].items():
        require(Path(ref['path']).is_absolute() and gate['receipt_hashes'].get(ref['path']) == ref['sha256'], 'Unbound primary')
        body = ops.read(ref['path'])
        require(sha_bytes(body) == ref['sha256'], 'Primary bytes differ')
        values[key] = body
    for name in ['final_prewrite_rollback_once.py', 'final_writer_open_once.py', 'n8n_dashboard_pause_once.py']:
        local = Path(__file__).with_name(name)
        require(gate['script_hashes'].get(name) == digest(local), 'Helper SHA differs')
        require(sha_bytes(ops.read(gate['run_dir']+'/'+name)) == digest(local), 'Host helper SHA differs')
    validate_host_binding(gate, Path(gate['run_dir']), ops.read)
    require(proof['refs']['host_primary'] == gate['original_host_primary'], 'Original host primary reference differs')
    require(sha_bytes(values['query']) == QUERY_SHA, 'Exact business query bytes required')
    names = re.findall(r"SELECT '([^']+)' AS table_name", values['query'].decode())
    require(len(names) == 43 and len(set(names)) == 43 and set(names) == set(TABLES), 'Query table inventory differs')
    baseline = json.loads(values['baseline'])
    require(baseline['status'] == 'FROZEN_SOURCE_BUSINESS_BASELINE' and baseline['problem_id'] == PROBLEM
            and baseline['run_dir'] == gate['run_dir'] and baseline['query_sha256'] == QUERY_SHA
            and baseline['query_path'] == proof['refs']['query']['path']
            and sorted(baseline['table_names']) == sorted(names), 'Actual frozen baseline absent')
    require(stamp(baseline['observed_at']) <= now and baseline['captured_after_freeze'] is True, 'Baseline not frozen')
    primary = baseline['primary_response']
    require(gate['receipt_hashes'].get(primary['path']) == primary['sha256'], 'Baseline primary not bound')
    body = ops.read(primary['path']); require(sha_bytes(body) == primary['sha256'], 'Baseline primary bytes differ')
    raw = json.loads(body)
    require(isinstance(raw, list) and len(raw) == 1 and set(raw[0]) == {'value'}, 'Baseline Source response shape differs')
    frozen = projection(baseline['tables'], names)
    require(projection(raw[0]['value'], names) == frozen, 'Baseline primary differs')
    require(sha_bytes(values['acl_restore']) == ACL_RESTORE_SHA
            and sha_bytes(values['scopes_restore']) == SCOPES_SHA
            and sha_bytes(values['nginx_original']) == NGINX_SHA, 'Original restore artifact differs')
    require(sha_bytes(values['acl_original']) == '59fc65746e3c97383ab5552f1f48816a7dae37bf0edd408eadc07018d99b9cb8'
            and len(json.loads(values['acl_original'])) == 82 and json.loads(values['acl_frozen']) == [], 'ACL82 freeze contract differs')
    # ACL primary must be the exact original artifact already bound by Source's freeze gate.
    require(proof['refs']['acl_original']['path'] == str(c.PRIVATE/'source/freeze-business-original-acl.json'), 'Wrong ACL original')
    tree = ast.parse(Path(__file__).with_name('n8n_dashboard_pause_once.py').read_text())
    versions = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSIONS' for t in n.targets))
    require(set(versions) == {'nzyaKxs5Om9wuPEc', 'dashboardDriveMove', 'dashboardDriveWatch'} and all(versions.values()), 'Original publication inventory differs')
    config = json.loads(values['config']); require(config and all(type(row['enabled']) is bool for row in config), 'Full original config absent')
    link = json.loads(values['project_link'])
    require(link == {'orgId': 'team_xbeBltwkXhOuVc8JUUR0CqoF', 'projectId': 'prj_pWCB8TaGLQesLsT9me0jgT0FqcC5'}
            or (link.get('orgId') == 'team_xbeBltwkXhOuVc8JUUR0CqoF' and link.get('projectId') == 'prj_pWCB8TaGLQesLsT9me0jgT0FqcC5'), 'Frontend project differs')
    require(proof['refs']['project_link']['path'] == str(FRONT_BUILD/'.vercel/project.json'), 'Frontend build path differs')
    require(not any(line.startswith(('VITE_SUPABASE_URL=', 'VITE_SUPABASE_ANON_KEY='))
                    for line in values['frontend_original_env'].decode().splitlines()), 'Frontend original env was not absent')
    return gate, proof, values, frozen, names


class MacReturnOperations:
    """All remote calls are explicit; no Source credentials ever reach the host."""
    def __init__(self, run):
        self.local = run

    def read(self, path):
        if path.startswith(str(ROOT)+'/'):
            return c.shell('test ! -L '+shlex.quote(path)+' && cat '+shlex.quote(path))
        require(not Path(path).is_symlink(), 'Symlink primary refused')
        return Path(path).read_bytes()

    def remote_python(self, code, timeout=60):
        # Preserve nested subprocess/HTTP primary data on host before safe SSH failure.
        wrapper = "import sys\nfrom pathlib import Path\nsys.path.insert(0,"+repr(getattr(self, 'remote', str(ROOT/self.local.name)))+")\nimport final_writer_open_once as w\ntry:\n exec("+repr(code)+")\nexcept Exception as e:\n p=w.private_failure(Path("+repr(getattr(self, 'remote', str(ROOT/self.local.name)))+"),e)\n raise RuntimeError('Native return stopped; private primary: '+p) from None\n"
        return c.shell('python3 -c '+shlex.quote(wrapper), timeout=timeout)

    def target_sql(self, query):
        raw = c.shell('docker exec -i '+DB+' psql -U supabase_admin -d postgres -XqAt -v ON_ERROR_STOP=1', query.encode())
        durable(self.local, 'target-query-'+uuid.uuid4().hex+'.json', {'raw_b64': base64.b64encode(raw).decode()})
        return json.loads(raw)

    def source_sql(self, query):
        # Same Mac Source Management endpoint/credential contract as c.sql;
        # preserve response bytes before JSON parsing rather than losing them.
        token = c.source_token()
        request = c.urllib.request.Request('https://api.supabase.com/v1/projects/'+c.PROJECT+'/database/query',
            data=json.dumps({'query': query}).encode(),
            headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        try:
            with c.urllib.request.urlopen(request, timeout=45) as response:
                body = response.read()
                durable(self.local, 'source-query-'+uuid.uuid4().hex+'.json',
                    {'body_b64': base64.b64encode(body).decode(), 'status': response.status,
                     'headers': list(response.headers.items())})
                return json.loads(body)
        except Exception as error:
            raise private_error(error) from None

    def markers_absent(self, remote):
        # Both known attempt marker and any phase writer marker are fatal.
        code = f"""from pathlib import Path
r=Path({remote!r});assert not any('writer' in p.name and ('marker' in p.name or 'attempt' in p.name) for p in r.iterdir())
"""
        self.remote_python(code)
        require(not any('writer' in p.name and ('marker' in p.name or 'attempt' in p.name)
                        for p in self.local.iterdir()), 'Writer already opened; Source return forbidden')

    def workflows(self, remote, active):
        code = f"""import sys,json,urllib.request
sys.path.insert(0,{remote!r})
from n8n_dashboard_pause_once import VERSIONS,http_read
from pathlib import Path
key=json.loads(Path('/opt/dashboard-supabase-20261003/n8n-pause-access-1/existing-api-key-private.json').read_text())['apiKey']
for w,v in VERSIONS.items():
 b,_,_=http_read(urllib.request.Request('http://127.0.0.1:5678/api/v1/workflows/'+w,headers={{'X-N8N-API-KEY':key}}),operation='late-return-publication',preserve_success=True)
 x=json.loads(b);assert x['active'] is {active!r};assert (x.get('activeVersionId') if {active!r} else x.get('versionId',x.get('activeVersionId')))==v
"""
        self.remote_python(code)

    def preflight(self, gate, values, frozen, names):
        from final_quiescence_once import acl_query, EFFECTIVE_PRIVILEGES_SQL
        remote = gate['run_dir']; self.remote = remote
        require(self.read(remote+'/prewrite-return-gate.json') == Path(self.gate_path).read_bytes(), 'Host gate primary differs')
        self.markers_absent(remote)
        self.workflows(remote, False)
        require(self.source_sql(EFFECTIVE_PRIVILEGES_SQL) == [
            {'role': r, 'writable_tables': 0, 'executable_writers': 0}
            for r in ['anon', 'authenticated', 'service_role']], 'Source API not frozen')
        source_rows = self.source_sql("SELECT json_build_object('running',(SELECT count(*) FROM public.wm_jobs WHERE state IN ('running','prepared')),'unknown_model',(SELECT count(*) FROM public.wm_model_calls WHERE received_at IS NULL AND redaction_id IS NULL),'unknown_question',(SELECT count(*) FROM public.wm_question_calls WHERE response_json IS NULL AND redaction_id IS NULL),'config',(SELECT json_agg(c ORDER BY space_id) FROM public.wm_processing_config c)) AS value")
        require(len(source_rows) == 1 and set(source_rows[0]) == {'value'}, 'Source live state incomplete')
        source_state = source_rows[0]['value']
        require(all(type(source_state[k]) is int and source_state[k] == 0 for k in ['running','unknown_model','unknown_question']), 'Source outstanding work unknown/nonempty')
        cron = self.source_sql('SELECT count(*) AS count FROM cron.job WHERE active')
        require(type(cron) is list and len(cron) == 1 and type(cron[0]) is dict and set(cron[0]) == {'count'} and type(cron[0]['count']) is int and cron[0]['count'] == 0, 'Source scheduled writer unknown/nonempty')
        require(self.source_sql(acl_query()) == json.loads(values['acl_frozen']), 'Source ACL changed')
        config = json.loads(values['config'])
        require(source_state['config'] == [{**r, 'enabled': False} for r in config], 'Source full config changed')
        require(self.target_sql('SELECT json_agg(c ORDER BY space_id) FROM public.wm_processing_config c') == config, 'Target full config changed')
        query = values['query'].decode()
        source = self.source_sql(query)
        require(len(source) == 1 and set(source[0]) == {'value'}, 'Source query response incomplete')
        require(projection(source[0]['value'], names) == frozen and projection(self.target_sql(query), names) == frozen,
                'Source/Target business differs from frozen baseline')
        # Native inspection uses actual runtime, mounts and counters. No worldwide-writer claim.
        code = f"""import sys,json,subprocess
from pathlib import Path
sys.path.insert(0,{remote!r})
from final_writer_open_once import HostOperations,read_json,CLOSED,ROOT,CANONICAL,require
op=HostOperations();op.run=Path({remote!r})
nginx=Path('/etc/nginx/sites-available/alexa').read_bytes();assert nginx in ({values['nginx_original']!r},{values['nginx_maintenance']!r})
op.verify_runtime(Path({remote!r}),{{'runtime':json.loads({values['runtime'].decode()!r}),'config':json.loads({values['config'].decode()!r})}},CLOSED,nginx_sha=__import__('hashlib').sha256(nginx).hexdigest())
assert json.loads(Path('/opt/dashboard-memory-canonical-draft/.local/selfhost-backup.json').read_text())=={{'enabled':True,'migration_run':{Path(remote).name!r}}}
assert op.call(['systemctl','show','dashboard-job-backup.service','-p','ActiveState','--value']).strip()==b'inactive'
x=json.loads(op.call(['docker','inspect',CANONICAL]))[0]
env=dict(i.split('=',1) for i in x['Config']['Env'] if '=' in i)
m=next(m for m in x['Mounts'] if m['Destination']=='/app/.local');assert m['Type']=='bind' and m['Source']=='/opt/dashboard-memory-canonical-draft/.local/cache'
assert [env['MEMORY_CACHE_DIR']+'/response-outbox',env['MEMORY_QA_OUTBOX']]==['/app/.local/projections-rc1-20260919/response-outbox','/app/.local/question-outbox']
for p in [env['MEMORY_CACHE_DIR']+'/response-outbox',env['MEMORY_QA_OUTBOX']]:
 d=Path(m['Source'])/Path(p).relative_to('/app/.local');assert d.is_dir() and not list(d.rglob('*.json'))
assert op.sql("SELECT json_build_object('running',(SELECT count(*) FROM public.wm_jobs WHERE state IN ('running','prepared')),'unknown_model',(SELECT count(*) FROM public.wm_model_calls WHERE received_at IS NULL AND redaction_id IS NULL),'unknown_question',(SELECT count(*) FROM public.wm_question_calls WHERE response_json IS NULL AND redaction_id IS NULL))")=={{'running':0,'unknown_model':0,'unknown_question':0}}
assert op.call(['docker','exec','-i','n8n_postgres','psql','-U','n8n','-d','n8n','-XqAt','-v','ON_ERROR_STOP=1'],input=b\"SELECT count(*) FROM execution_entity WHERE \\\"workflowId\\\" IN ('nzyaKxs5Om9wuPEc','dashboardDriveMove','dashboardDriveWatch') AND status IN ('new','running','waiting');\").strip()==b'0'
cron=op.sql('SELECT count(*) FROM cron.job WHERE active')
assert type(cron) is int and cron==0
"""
        self.remote_python(code, timeout=100)

    def mutation_guard(self, gate, values):
        self.markers_absent(gate['run_dir'])
        require(c.shell('systemctl show dashboard-job-backup.service -p ActiveState --value').strip() == b'inactive', 'Backup service active')
        require(self.read('/opt/dashboard-supabase-20261003/'+Path(gate['run_dir']).name+'/nginx-original.conf') == values['nginx_original'], 'Host original Nginx differs')
        actual = c.shell('cat /etc/nginx/sites-available/alexa')
        require(actual in (values['nginx_original'], values['nginx_maintenance']), 'Foreign ingress')

    def maintenance(self, values):
        original, candidate = values['nginx_original'], values['nginx_maintenance']
        self.remote_python(f"""from pathlib import Path
import subprocess
p=Path('/etc/nginx/sites-available/alexa');assert p.read_bytes() in ({original!r},{candidate!r})
p.write_bytes({candidate!r})
subprocess.run(['nginx','-t'],check=True,capture_output=True)
subprocess.run(['systemctl','reload','nginx'],check=True,capture_output=True)
""")

    def stop_target(self):
        c.shell('docker stop --time 120 '+CANONICAL, timeout=135)
        require(c.shell("docker inspect -f '{{.State.Running}}' "+CANONICAL).strip() == b'false', 'Target stop unproven')

    def restore_host(self, gate):
        # Exact five files only; copy source snapshot, never target data.
        refs = gate['original_host_files']
        code = 'import hashlib,os,subprocess,tempfile,json\nfrom pathlib import Path\n'
        code += f"assert subprocess.check_output(['docker','inspect','-f','{{{{.State.Running}}}}',{CANONICAL!r}]).strip()==b'false'\n"
        for name in HOST_FILES:
            source = refs[name]['path']; dest = str(LIVE/('.local/service.env' if name == 'service.env' else name))
            code += f"s=Path({source!r});assert not s.is_symlink();b=s.read_bytes();assert hashlib.sha256(b).hexdigest()=={refs[name]['sha256']!r}\np=Path({dest!r});fd,t=tempfile.mkstemp(dir=p.parent);os.fchmod(fd,0o600);os.write(fd,b);os.fsync(fd);os.close(fd);os.replace(t,p);assert hashlib.sha256(p.read_bytes()).hexdigest()=={refs[name]['sha256']!r}\n"
        code += f"p=Path({str(LIVE/'.local/selfhost-backup.json')!r});assert not p.is_symlink();x=json.loads(p.read_text());assert x=={{'enabled':True,'migration_run':{Path(gate['run_dir']).name!r}}};p.unlink()\n"
        self.remote_python(code)

    def restore_acl(self, values):
        from final_quiescence_once import acl_query
        require(self.source_sql(acl_query()) == json.loads(values['acl_frozen']), 'Foreign Source ACL; stop')
        # Read and grants are in one transaction guarded against concurrent ACL edits.
        guard = "DO $g$ BEGIN IF (SELECT coalesce(jsonb_agg(to_jsonb(a)),'[]'::jsonb) FROM ("+acl_query()+") a) IS DISTINCT FROM '[]'::jsonb THEN RAISE EXCEPTION 'ACL changed'; END IF; END $g$;"
        restore = values['acl_restore'].decode()
        require(restore.startswith('BEGIN;') and restore.rstrip().endswith('COMMIT;'), 'ACL transaction differs')
        self.source_sql(restore.replace('BEGIN;', 'BEGIN; '+guard, 1))
        require(self.source_sql(acl_query()) == json.loads(values['acl_original']), 'Original ACL82 readback differs')

    def restore_config(self, values):
        original = json.loads(values['config']); frozen = [{**r, 'enabled': False} for r in original]
        guard = "BEGIN; LOCK TABLE public.wm_processing_config IN EXCLUSIVE MODE; DO $g$ BEGIN IF (SELECT jsonb_agg(to_jsonb(c) ORDER BY space_id) FROM public.wm_processing_config c) IS DISTINCT FROM "+c.literal(json.dumps(frozen))+"::jsonb THEN RAISE EXCEPTION 'Full config changed'; END IF; END $g$;"
        updates = ''.join('UPDATE public.wm_processing_config SET enabled='+('true' if r['enabled'] else 'false')+' WHERE space_id='+c.literal(r['space_id'])+'::uuid;' for r in original)
        self.source_sql(guard+updates+'COMMIT;')
        require(self.source_sql('SELECT json_agg(c ORDER BY space_id) AS value FROM public.wm_processing_config c') == [{'value': original}], 'Original full config readback differs')

    def start_source(self, gate):
        self.workflows(gate['run_dir'], False)
        # Compose tag and immutable image are both hard-bound; exactly one up.
        refs = gate['original_host_files']
        code = f"""import subprocess,json,hashlib
from pathlib import Path
p=Path({str(LIVE)!r})
refs={refs!r}
for name,ref in refs.items():
 dest=p/('.local/service.env' if name=='service.env' else name)
 assert not dest.is_symlink();assert hashlib.sha256(dest.read_bytes()).hexdigest()==ref['sha256']
x=json.loads(subprocess.check_output(['docker','image','inspect','dashboard-memory:memory-20260921-compact-guard-final']))[0];assert x['Id']=={BASE!r}
subprocess.run(['docker','compose','up','-d','--no-build','canonical-draft'],cwd=p,check=True,capture_output=True,timeout=120)
x=json.loads(subprocess.check_output(['docker','inspect',{CANONICAL!r}]))[0];assert x['Image']=={BASE!r} and x['State']['Running']
actual=dict(v.split('=',1) for v in x['Config']['Env'] if '=' in v)
expected=dict(v.split('=',1) for v in (p/'.local/service.env').read_text().splitlines() if v and not v.startswith('#'))
assert all(actual.get(k)==v for k,v in expected.items());assert expected['SUPABASE_URL'].rstrip('/')=={SOURCE_ORIGIN!r}
"""
        self.remote_python(code, timeout=135)

    def health(self, gate):
        code = f"""import sys,json,time,urllib.request
from pathlib import Path
sys.path.insert(0,{gate['run_dir']!r})
import final_writer_open_once as w
end=time.monotonic()+90
while True:
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8798/health',method='GET'),timeout=5) as r:
   body=r.read();w.save_private(Path({gate['run_dir']!r})/('return-health-'+w.uuid.uuid4().hex+'.json'),{{'body_b64':w.base64.b64encode(body).decode(),'status':r.status,'headers':list(r.headers.items())}})
   v=json.loads(body);assert r.status==200 and v['status']=='ok'
  break
 except Exception as e:
  w.private_failure(Path({gate['run_dir']!r}),e)
  if time.monotonic()>=end:raise
  time.sleep(min(2,max(0,end-time.monotonic())))
"""
        self.remote_python(code, timeout=100)

    def ingress(self, values):
        self.remote_python(f"""from pathlib import Path
import subprocess
p=Path('/etc/nginx/sites-available/alexa');assert p.read_bytes()=={values['nginx_maintenance']!r}
p.write_bytes({values['nginx_original']!r})
subprocess.run(['nginx','-t'],check=True,capture_output=True);subprocess.run(['systemctl','reload','nginx'],check=True,capture_output=True)
""")

    def resume(self, gate, gate_path, values):
        self.workflows(gate['run_dir'], False)
        # Root must provide the same SHA-bound gate on host, rather than overwriting an existing gate.
        host_gate = gate['run_dir']+'/prewrite-return-gate.json'
        require(self.read(host_gate) == Path(gate_path).read_bytes(), 'Host return gate differs')
        result = c.shell('python3 '+shlex.quote(gate['run_dir']+'/n8n_dashboard_pause_once.py')+
            ' --action resume --run-dir '+shlex.quote(gate['run_dir'])+' --gate-receipt '+shlex.quote(host_gate), timeout=100)
        require(json.loads(result)['status'] == 'PASSED', 'Supported three-publication resume failed')
        self.workflows(gate['run_dir'], True)

    def scopes(self, values):
        key = json.loads(values['scope_key'])
        require('id' in key and 'scopes' in key, 'Original scopes missing')
        c.n8n_sql(values['scopes_restore'].decode())
        require(json.loads(c.n8n_sql('SELECT scopes FROM user_api_keys WHERE id='+c.literal(key['id'])+';')) == key['scopes'], 'Original scopes readback differs')

    def cli(self, args):
        try:
            result = subprocess.run(['vercel', *args], cwd=FRONT_BUILD, capture_output=True, timeout=240)
        except Exception as error:
            raise private_error(error) from None
        # Preserve complete original output even if a following JSON assertion fails.
        durable(self.local, 'frontend-cli-'+uuid.uuid4().hex+'.json', {'stdout_b64': base64.b64encode(result.stdout).decode(),
            'stderr_b64': base64.b64encode(result.stderr).decode(), 'status': result.returncode})
        if result.returncode: raise subprocess.CalledProcessError(result.returncode, ['vercel', *args], result.stdout, result.stderr)
        return result.stdout

    def frontend(self, values):
        receipt = json.loads(values['frontend'])
        require(receipt['problem_id'] == 'HZ-MIGRATION-20261003-FINAL-FRONTEND'
                and type(receipt['promotion_attempts']) is int and receipt['promotion_attempts'] in (0, 1), 'Frontend ownership unknown')
        if receipt['promotion_attempts'] == 1:
            # Durable local return marker prevents retry even after partial official rollback.
            durable(self.local, 'frontend-original-rollback-attempt.marker', {'deployment': OLD_DEPLOYMENT})
            self.cli(['rollback', OLD_DEPLOYMENT, '--yes', '--timeout', '3m'])
        for alias in sorted(ALIASES):
            actual = json.loads(self.cli(['inspect', alias, '--format', 'json']))
            require(actual['id'] == OLD_DEPLOYMENT and actual['readyState'] == 'READY', 'Original alias not READY')
        for flag, name in [('url_env_added', 'VITE_SUPABASE_URL'), ('anon_env_added', 'VITE_SUPABASE_ANON_KEY')]:
            require(type(receipt.get(flag)) is bool, 'Frontend env ownership unknown')
            if receipt.get(flag) is True:
                self.cli(['env', 'rm', name, 'production', '--yes'])


def execute(run, gate_path, operations=None, now=None):
    ops = operations or MacReturnOperations(run)
    clock = (lambda: now) if now is not None else (lambda: dt.datetime.now(dt.timezone.utc))
    started = False; values = None
    try:
        require(not (run/'writer-open-attempt.marker').exists(), 'Writer already opened; Source rollback forbidden')
        gate, proof, values, frozen, names = load(run, gate_path, ops, clock())
        require(not (run/'prewrite-source-return-attempt.marker').exists(), 'Return already attempted')
        ops.gate_path = gate_path
        ops.preflight(gate, values, frozen, names)
        # Every mutation reloads all original artifacts and checks marker absence/fresh gate.
        def guarded(function, *args):
            load(run, gate_path, ops, clock())
            ops.mutation_guard(gate, values)
            return function(*args)
        durable(run, 'prewrite-source-return-attempt.marker', {'problem_id': PROBLEM, 'run_dir': gate['run_dir'], 'gate_sha256': digest(gate_path)})
        started = True
        guarded(ops.maintenance, values)
        guarded(ops.stop_target)  # FIRST activation boundary: before any Source ACL grants.
        guarded(ops.restore_host, gate)
        guarded(ops.restore_acl, values)
        guarded(ops.restore_config, values)
        guarded(ops.start_source, gate)
        ops.health(gate)
        guarded(ops.ingress, values)
        guarded(ops.resume, gate, gate_path, values)
        guarded(ops.scopes, values)
        guarded(ops.frontend, values)
        durable(run, 'prewrite-source-return-receipt.json', {'status': 'SOURCE_ORIGINAL_STATE_RETURNED',
            'problem_id': PROBLEM, 'run_dir': gate['run_dir'], 'target_data_reverted': False,
            'writer_opened': False, 'original_host_files': list(HOST_FILES), 'operational_GO': False})
    except Exception as error:
        failure = private_error(error)  # Primary is durable before any cleanup or outward error.
        if started and values is not None:
            try: ops.maintenance(values)
            except Exception as maintenance_error: private_error(maintenance_error)
            # Stop canonical on activation failure; never continue with ingress/workflow activation.
            try: ops.stop_target()
            except Exception as stop_error: private_error(stop_error)
        raise PreconditionsError(str(failure)) from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True); parser.add_argument('--gate-receipt', required=True)
    args = parser.parse_args(); run = Path(args.run_dir)
    try:
        execute(run, Path(args.gate_receipt))
    except Exception as error:
        print(json.dumps({'status': 'STOP_RETURN_TO_ROOT', 'error_type': type(error).__name__})); return 1
    print(json.dumps({'status': 'SOURCE_ORIGINAL_STATE_RETURNED'})); return 0


if __name__ == '__main__':
    raise SystemExit(main())
