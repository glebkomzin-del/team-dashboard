"""One gated source pause/freeze. Failure retains receipts; never forces a call to zero."""
import argparse, ast, json, os, re, shlex, time
from pathlib import Path
from final_phase_common import *

NGINX='/etc/nginx/sites-available/alexa'
NGINX_SHA='7cfba8642673162a182f67926bc26dbb0def8bdafecd7952e7ee5c524511fe51'
def acl_query():
    tree=ast.parse((HERE/'prepare_business_freeze_acl.py').read_text())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id=='query' for t in n.targets))

def state():
    rows=sql("""SELECT json_build_object(
      'jobs',(SELECT coalesce(json_agg(x),'[]') FROM (SELECT space_id,state,reason,count(*) AS count FROM public.wm_jobs GROUP BY 1,2,3 ORDER BY 1,2,3) x),
      'running',(SELECT count(*) FROM public.wm_jobs WHERE state IN ('running','prepared')),
      'unknown_model',(SELECT count(*) FROM public.wm_model_calls WHERE received_at IS NULL AND redaction_id IS NULL),
      'unknown_question',(SELECT count(*) FROM public.wm_question_calls WHERE response_json IS NULL AND redaction_id IS NULL),
      'config',(SELECT coalesce(json_agg(c ORDER BY space_id),'[]') FROM public.wm_processing_config c)) AS value""")
    v=rows[0]['value']
    v['n8n_active']=int(n8n_sql('SELECT count(*) FROM execution_entity WHERE "workflowId" IN (\'nzyaKxs5Om9wuPEc\',\'dashboardDriveMove\',\'dashboardDriveWatch\') AND status IN (\'new\',\'running\',\'waiting\');').strip())
    # Exactly the runtime's live paths, including post-stop host paths; no historical caches.
    code="import json;from pathlib import Path;print(json.dumps({str(p):len(list(p.rglob('*.json'))) for p in [Path('/opt/dashboard-memory-canonical-draft/.local/projections-rc1-20260919/response-outbox'),Path('/opt/dashboard-memory-canonical-draft/.local/question-outbox')]}))"
    v['outboxes']=json.loads(shell('python3 -c '+shlex.quote(code)))
    return v

def empty(v): return not any(v[k] for k in ['running','unknown_model','unknown_question','n8n_active']) and not any(v['outboxes'].values())

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--gate-receipt');a=p.parse_args();os.umask(0o077)
    local,remote=paths(a.name)
    if a.prepare:
        local.mkdir(mode=0o700)
        original=shell('cat '+NGINX);assert __import__('hashlib').sha256(original).hexdigest()==NGINX_SHA
        (local/'nginx-original.conf').write_bytes(original)
        changed=original.decode()
        for prefix in ['/dashboard-memory/','/dashboard-memory-draft/']:
            header='location '+prefix+' {';assert changed.count(header)==1
            changed=changed.replace(header,header+'\n        return 503; # migration drain; original block preserved',1)
        (local/'nginx-maintenance.conf').write_text(changed)
        baseline=state();assert baseline['config']
        save(local/'source-preflight-private.json',baseline)
        current=sql(acl_query());expected=json.loads((PRIVATE/'source/freeze-business-original-acl.json').read_text());assert current==expected
        save(local/'source-original-config-private.json',baseline['config'])
        save(local/'preparation.json',{'prepared':True,'source_unchanged':True,'nginx_original_sha256':NGINX_SHA,'drain_seconds':600})
        print(json.dumps({'prepared':True,'running':baseline['running'],'unknown_model':baseline['unknown_model'],'unknown_question':baseline['unknown_question'],'n8n_active':baseline['n8n_active'],'outboxes':baseline['outboxes']}));return
    gate_check(a.gate_receipt,a.name)
    save(local/'freeze-attempt.json',{'attempt':1,'phase':'started'})
    assert sql(acl_query())==json.loads((PRIVATE/'source/freeze-business-original-acl.json').read_text())
    assert shell('sha256sum '+NGINX).decode().split()[0]==NGINX_SHA
    assert shell('systemctl show dashboard-job-backup.service -p ActiveState --value').strip()==b'inactive'
    image=shell('docker inspect -f '+shlex.quote('{{.Image}}')+' '+CANONICAL).decode().strip()
    assert image=='sha256:15a6a820f9d887fac5f0bcd3e2dd29c477d4d5f6a7e82db41bb83cd899f43a2f'
    shell('umask 077; mkdir '+shlex.quote(remote))
    upload(a.gate_receipt,remote+'/gate.json')
    for file in ['nginx-original.conf','nginx-maintenance.conf','source-original-config-private.json']:
        upload(local/file,remote+'/'+file)
    scope=PRIVATE/'current-evidence/n8n-scope-plan-1/add-scopes.sql'
    assert digest(scope)=='c7b3dfe4ac75688121c89f79f80014494d4ca3cb6a620beb94e5b2682a96b9ca'
    n8n_sql(scope.read_text())
    upload(HERE/'n8n_dashboard_pause_once.py',remote+'/n8n_dashboard_pause_once.py')
    result=shell('python3 '+remote+'/n8n_dashboard_pause_once.py --action pause --run-dir '+remote+' --gate-receipt '+remote+'/gate.json')
    assert json.loads(result)['status']=='PASSED'
    # Test complete candidate before replacing live config. Failure restores original immediately.
    candidate=remote+'/nginx-maintenance-test.conf'
    shell('umask 077; sed '+shlex.quote('s@include /etc/nginx/sites-enabled/\\*;@include '+remote+'/nginx-maintenance.conf;@')+' /etc/nginx/nginx.conf > '+candidate)
    shell('nginx -t -c '+candidate)
    shell('cp '+remote+'/nginx-maintenance.conf '+NGINX+' && (nginx -t && systemctl reload nginx || { cp '+remote+'/nginx-original.conf '+NGINX+'; nginx -t; systemctl reload nginx; exit 1; })')
    original=json.loads((local/'source-original-config-private.json').read_text())
    encoded=literal(json.dumps(original))
    sql("BEGIN; LOCK TABLE public.wm_processing_config IN EXCLUSIVE MODE; DO $m$ BEGIN IF (SELECT jsonb_agg(to_jsonb(c) ORDER BY space_id) FROM public.wm_processing_config c) IS DISTINCT FROM "+encoded+"::jsonb THEN RAISE EXCEPTION 'Config changed'; END IF; END $m$; UPDATE public.wm_processing_config SET enabled=false; COMMIT;")
    after=state();assert [{**c,'enabled':False} for c in original]==after['config']
    save(local/'after-config-disable-private.json',after)
    end=time.monotonic()+600; samples=[]
    while True:
        v=state();samples.append(v)
        if empty(v):break
        if time.monotonic()>=end:
            save(local/'drain-failed-private.json',samples);raise RuntimeError('Drain boundary reached; no stop, freeze or dump')
        time.sleep(10)
    save(local/'drain-private.json',samples)
    shell('docker stop --time 120 '+CANONICAL,timeout=135)
    post=state();save(local/'after-stop-private.json',post);assert empty(post)
    assert shell('docker inspect -f '+shlex.quote('{{.State.Running}}')+' '+CANONICAL).strip()==b'false'
    freeze=HERE/'freeze-business.sql';assert digest(freeze)=='bbaeadd9a668377f2bdd3bb938f1fe968755a969e5919bc500df54d4fdc85dcc'
    assert sql(acl_query())==json.loads((PRIVATE/'source/freeze-business-original-acl.json').read_text())
    sql(freeze.read_text())
    objects=json.loads((PRIVATE/'source/freeze-business-original-acl.json').read_text())
    functions=sorted(set(r['object'] for r in objects if r['kind']=='FUNCTION'))
    # All public table direct DML and every reviewed business writer function: effective privileges.
    function_ids=','.join(literal(x)+'::regprocedure' for x in functions)
    effective=sql("SELECT r.rolname AS role,(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') AND has_table_privilege(r.rolname,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')) AS writable_tables,(SELECT count(*) FROM pg_proc p WHERE p.oid IN ("+function_ids+") AND has_function_privilege(r.rolname,p.oid,'EXECUTE')) AS executable_writers FROM pg_roles r WHERE r.rolname IN ('anon','authenticated','service_role') ORDER BY r.rolname")
    assert len(effective)==3 and all(not r['writable_tables'] and not r['executable_writers'] for r in effective)
    final=state();assert empty(final)
    receipt={'status':'FROZEN','attempt':1,'run_dir':remote,'effective_privileges':effective,'post_stop_empty':True,'config_disabled':True,'ingress_maintenance':True,'source_password_unchanged':True,'runtime_enforcement':'RULES_ONLY','dump_attempts':0}
    save(local/'freeze-receipt.json',receipt);upload(local/'freeze-receipt.json',remote+'/freeze-receipt.json')
    print(json.dumps(receipt))

if __name__=='__main__':main()
