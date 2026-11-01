"""One Source-only partial recovery. Unknown mutation replies require actual readback."""
import argparse, json, os, shlex
from final_phase_common import *
from final_quiescence_once import acl_query, state, NGINX, NGINX_SHA
from n8n_dashboard_pause_once import durable

IMAGE='sha256:15a6a820f9d887fac5f0bcd3e2dd29c477d4d5f6a7e82db41bb83cd899f43a2f'
FLAGS=['MEMORY_READ_ONLY','MEMORY_INTAKE_ENABLED','MEMORY_AUTOMATIC_ENABLED','MEMORY_QA_ENABLED','MEMORY_ORIGINAL_DELETION_ENABLED']

def runtime_snapshot():
    code="""import json,hashlib,subprocess
from pathlib import Path
d=json.loads(subprocess.check_output(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0]
env=dict(x.split('=',1) for x in d['Config']['Env'])
raw=Path('/opt/dashboard-memory-canonical-draft/.local/service.env').read_bytes()
host=dict(x.split('=',1) for x in raw.decode().splitlines() if x and not x.startswith('#'))
keys=['MEMORY_READ_ONLY','MEMORY_INTAKE_ENABLED','MEMORY_AUTOMATIC_ENABLED','MEMORY_QA_ENABLED','MEMORY_ORIGINAL_DELETION_ENABLED']
print(json.dumps({'image':d['Image'],'running':d['State']['Running'],
'env_sha256':hashlib.sha256(json.dumps(sorted(env.items())).encode()).hexdigest(),
'host_sha256':hashlib.sha256(raw).hexdigest(),'origin':env['SUPABASE_URL'].rstrip('/'),
'host_origin':host['SUPABASE_URL'].rstrip('/'),'flags':{k:env.get(k,'0') for k in keys},
'host_flags':{k:host.get(k,'0') for k in keys}}))"""
    return json.loads(shell('python3 -c '+shlex.quote(code)))

def verify_runtime(v):
    assert v['image']==IMAGE
    assert v['origin']==v['host_origin']=='https://lghwikeotbkmojyyjglz.supabase.co'
    assert v['flags']==v['host_flags'] and set(v['flags'])==set(FLAGS)
    assert all(x in ('0','1') for x in v['flags'].values())
    assert {k:v['flags'][k] for k in FLAGS[:3]}==dict(zip(FLAGS[:3],['0','1','1']))

def target_guard(remote):
    shell('test ! -e '+remote+'/final-restore-attempt.json && test ! -e '+remote+'/target-runtime-attempt.marker && test ! -e /opt/dashboard-memory-canonical-draft/.local/selfhost-backup.json')

def scope_state():
    key=json.loads((PRIVATE/'current-evidence/n8n-pause-access-1/existing-api-key-private.json').read_text())
    # The guarded restore SQL also verifies owner and secret MD5 in the same transaction.
    rows=json.loads(n8n_sql('SELECT json_build_object(\'scopes\',scopes,\'userId\',"userId",\'md5\',md5("apiKey")) FROM user_api_keys WHERE id='+literal(key['id'])+';'))
    assert rows['userId']==key['userId'] and rows['md5']==__import__('hashlib').md5(key['apiKey'].encode()).hexdigest()
    return rows['scopes'],key['scopes']

def workflow_action(remote,action):
    result=json.loads(shell('python3 '+remote+'/n8n_dashboard_pause_once.py --action '+action+' --run-dir '+remote+' --gate-receipt '+remote+'/gate.json'))
    assert result['status']=='PASSED'
    return result

def health(remote):
    # No second start: GET observations only, retaining every failed primary response privately.
    code="""import sys,time,json,urllib.request
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from n8n_dashboard_pause_once import http_read
end=time.monotonic()+90
while True:
 try:
  body,status,_=http_read(urllib.request.Request('http://127.0.0.1:8798/health',method='GET'),operation='source-recovery-health',private_errors=Path(sys.argv[1])/'private-errors',timeout=5)
  assert status==200
  print(body.decode());break
 except Exception:
  if time.monotonic()>=end:raise RuntimeError('Source readiness deadline; ingress stays closed') from None
  time.sleep(2)"""
    return json.loads(shell('python3 -c '+shlex.quote(code)+' '+shlex.quote(remote),timeout=100))

def recover(local,remote):
    attempted=lambda stage:(local/('source-stage-'+stage+'-attempt.json')).exists()
    durable(local,'source-partial-recovery-attempt.json',{'attempt':1,'source_only':True})
    target_guard(remote)
    original=json.loads((local/'source-original-config-private.json').read_text())
    expected_acl=json.loads((PRIVATE/'source/freeze-business-original-acl.json').read_text());assert len(expected_acl)==82
    nginx=shell('cat '+NGINX);cfg=state()['config'];acl=sql(acl_query());runtime=runtime_snapshot();verify_runtime(runtime)
    original_runtime_path=local/'source-original-runtime-private.json'
    if original_runtime_path.exists():
        saved=json.loads(original_runtime_path.read_text());verify_runtime(saved);assert saved['running']
        assert {k:v for k,v in runtime.items() if k!='running'}=={k:v for k,v in saved.items() if k!='running'}
    else:assert not any(attempted(x) for x in ['scopes','n8n','nginx','config','stop','acl'])
    baseline_nginx=(local/'nginx-original.conf').read_bytes();maintenance=(local/'nginx-maintenance.conf').read_bytes()
    assert __import__('hashlib').sha256(baseline_nginx).hexdigest()==NGINX_SHA
    assert nginx==baseline_nginx or (attempted('nginx') and nginx==maintenance)
    disabled=[{**r,'enabled':False} for r in original]
    assert cfg==original or (attempted('config') and cfg==disabled)
    assert acl==expected_acl or (attempted('acl') and acl==[])
    assert runtime['running'] or attempted('stop')
    scopes,base_scopes=scope_state()
    assert scopes==base_scopes or (attempted('scopes') and scopes==base_scopes+['workflow:activate','workflow:deactivate'])
    if attempted('n8n'):workflow_action(remote,'inspect-partial')
    before={'config':cfg,'acl':acl,'runtime':runtime,'nginx_sha256':__import__('hashlib').sha256(nginx).hexdigest(),'scopes':scopes}
    durable(local,'source-partial-before-private.json',before)
    def mutation(stage,fn):
        target_guard(remote)
        durable(local,'source-partial-'+stage+'-attempt.json',{'stage':stage})
        return fn()
    if acl!=expected_acl:
        restore=HERE/'freeze-business-restore-acl.sql'
        assert digest(restore)=='26c34f43afa8408e933589b6ce705bf09bd3e36234904de81166b26dd1955f02'
        guarded=restore.read_text().replace('BEGIN;','BEGIN; DO $acl$ BEGIN IF EXISTS (SELECT 1 FROM ('+acl_query()+") current_acl) THEN RAISE EXCEPTION 'ACL changed'; END IF; END $acl$;",1)
        mutation('acl',lambda:sql(guarded))
        assert sql(acl_query())==expected_acl
    if cfg!=original:
        updates=''.join('UPDATE public.wm_processing_config SET enabled='+('true' if r['enabled'] else 'false')+' WHERE space_id='+literal(r['space_id'])+'::uuid;' for r in original)
        query="BEGIN; LOCK TABLE public.wm_processing_config IN EXCLUSIVE MODE; DO $m$ BEGIN IF (SELECT jsonb_agg(to_jsonb(c) ORDER BY space_id) FROM public.wm_processing_config c) IS DISTINCT FROM "+literal(json.dumps(disabled))+"::jsonb THEN RAISE EXCEPTION 'Config changed'; END IF; END $m$; "+updates+' COMMIT;'
        mutation('config',lambda:sql(query));assert state()['config']==original
    if not runtime['running']:
        mutation('start',lambda:shell('docker start '+CANONICAL))
    # Health must precede ingress and workflow reactivation, including an already-running process.
    observed_health=health(remote) if any(attempted(x) for x in ['nginx','stop','n8n']) else None
    if nginx!=baseline_nginx:
        mutation('nginx',lambda:shell('cmp -s '+NGINX+' '+remote+'/nginx-maintenance.conf && cp '+remote+'/nginx-original.conf '+NGINX+' && nginx -t && systemctl reload nginx'))
    if attempted('n8n'):mutation('n8n',lambda:workflow_action(remote,'resume-partial'))
    if scopes!=base_scopes:
        restore=PRIVATE/'current-evidence/n8n-scope-plan-1/restore-scopes.sql'
        assert digest(restore)=='c1fa6235bdee05964f84e3e06521278f7ffcdd463340e8d2bb2644d9492d589a'
        mutation('scopes',lambda:n8n_sql(restore.read_text()))
    after={'config':state()['config'],'acl':sql(acl_query()),'runtime':runtime_snapshot(),
           'nginx_sha256':__import__('hashlib').sha256(shell('cat '+NGINX)).hexdigest(),'scopes':scope_state()[0]}
    assert after['config']==original and after['acl']==expected_acl and after['scopes']==base_scopes
    verify_runtime(after['runtime']);assert after['runtime']=={**runtime,'running':True}
    assert after['nginx_sha256']==NGINX_SHA
    durable(local,'source-partial-after-private.json',after)
    receipt={'status':'SOURCE_PARTIAL_ORIGINAL_RESTORED','before':before,'after':after,'health':observed_health,
        'target_writes':0,'freeze_repeated':False,'lease_attempts':0,'dump_attempts':0,'source_freeze_budget':1}
    durable(local,'source-partial-recovery-receipt.json',receipt)
    return receipt

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--gate-receipt',required=True);a=p.parse_args();os.umask(0o077)
    local,remote=paths(a.name);gate_check(a.gate_receipt,a.name)
    try:receipt=recover(local,remote)
    except Exception as error:
        failure=private_failure('SOURCE_PARTIAL_RECOVERY_STOP',error_type=type(error).__name__,primary_error=str(error))
        durable(local,'source-partial-recovery-failure.json',{'failure':str(failure),'status':'STOP','no_automatic_retry':True})
        raise failure from None
    print(json.dumps({'status':receipt['status'],'target_writes':0,'lease_attempts':0,'dump_attempts':0}))
if __name__=='__main__':main()
