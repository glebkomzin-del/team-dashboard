"""Mac-only entrypoint for OWN partial Target return, before any writer opening.

Root proof contract: target-partial-source-return-proof.json uses the existing
LateReturn refs except runtime, plus timer_pause and stage_manifest. Every ref,
primary baseline response, original_host_sources (five immutable ORIGINAL bytes),
and original_host_files (five expected snapshot path/SHA pairs; may be absent
only with unchanged live host) is individually gate-bound. Host copy of the gate
is prewrite-return-gate.json, also consumed by the supported n8n helper. No
Target runtime PASS receipt is required or manufactured. Timer pause primary:
problem_id/run_dir/status=OWN_TIMER_PAUSED, original_active=true,
original_enabled=true, timer_unit_sha256=TIMER_SHA, code_sha256=BACKUP_SHA.
External Target writers must be positively excluded by a fresh Root primary:
external_target_writers={observed_at, known_writers:[], primary_response:{path,sha256}};
this is a bounded Root observation, never worldwide absence proof.
"""
import argparse, ast, base64, datetime as dt, json, os, re, shlex, uuid
from pathlib import Path
import final_phase_common as c
import final_prewrite_rollback_once as r
import final_writer_open_once as w
from final_prewrite_rollback_once import (PROBLEM, ROOT, LIVE, CANONICAL, DB,
    CLOSED, ORIGINAL, BASE, NGINX_SHA, SCOPES_SHA, ALIASES, HOST_FILES,
    SOURCE_ORIGIN, require, stamp, digest, sha_bytes, read_json,
    PreconditionsError, QUERY_SHA, ACL_RESTORE_SHA, FRONT_BUILD, TABLES, projection, durable)
from final_target_runtime_once import SERVER_SHA
STAGE_PATCHES={'access.py':{'before_sha256':'6bf63cb14037daecd52a7e67493afcdf0b8e42e95b7eaa1bafd5349e3ba0b918','after_sha256':'58164da22cfd7d8ff8cf5e6727a0e69e856e5c33906944470394555551f9a14b'},'gateway_journal.py':{'before_sha256':'ac00662a53d08c8a521a9087d0bec8c54f76d3ae9441b9c232d6eb026bc45313','after_sha256':'5713cb5bb663cf17bbdea17f4f74cd78f6798f81a130106f72daa1b391bfab5d'}}
TIMER_SHA='bb148fb19b1776e4546a0d3c940762db92cf7e76422087e9e018de0c6951a5b3'
SCRIPTS=('final_target_partial_source_return_once.py','final_prewrite_rollback_once.py',
         'final_writer_open_once.py','final_phase_common.py','final_target_runtime_once.py',
         'n8n_dashboard_pause_once.py','final_quiescence_once.py','final_restore_once.py')
STAGE_MANIFEST='/opt/dashboard-memory-stage-read-20261003/build-manifest.json'
API_IMAGES={'auth':'supabase/gotrue:v2.196.0@sha256:93bfec0a41cfe3ed81d03c9c1c8807fd230b8ecea260cf999b8a7204ccc7d5cf','rest':'postgrest/postgrest:v16.4@sha256:c3638ac25258ede665db66a4052b6fd30db4f22789327dce84599409136da35f','api-gw':'envoyproxy/envoy:v1.39.1@sha256:b21240e552b588017072424716c0bce30000f49deed6262bde55b042b5acfd97','functions':'supabase/edge-runtime:v1.76.2@sha256:3115aa7254d84e35704fad8abbcef7e759b645213ffb3b9238a7862659b704c2'}
API_NETWORKS={
    'auth':{'dashboard-supabase-20261003_restore','dashboard-supabase-20261003_smtp-egress'},
    'rest':{'dashboard-supabase-20261003_restore'},
    'api-gw':{'dashboard-supabase-20261003_restore','dashboard-supabase-20261003_api-ingress'},
    'functions':{'dashboard-supabase-20261003_restore'},
}
REFS=(r.REFS-{'runtime'})|{'timer_pause','stage_manifest'}

def phase_gate(gate, now):
    require(gate.get('problem_id')==PROBLEM and gate.get('phase')=='TARGET_PARTIAL_SOURCE_RETURN'
            and gate.get('decision')=='CONTINUE_BOUNDED','Partial return gate absent')
    require(re.fullmatch(r'/opt/dashboard-supabase-20261003/final-export-\d{8}T\d{6}Z',gate['run_dir']), 'Wrong run')
    issued,expires=stamp(gate['issued_at']),stamp(gate['expires_at'])
    require(issued<=now<expires and 0<(expires-issued).total_seconds()<=600,'Gate stale')

def bound(ref,gate,ops):
    require(Path(ref['path']).is_absolute() and gate['receipt_hashes'].get(ref['path'])==ref['sha256'],'Unbound primary')
    raw=ops.read_stage(ref) if ref['path']==STAGE_MANIFEST else ops.read(ref['path']);require(sha_bytes(raw)==ref['sha256'],'Primary changed');return raw

def original_binding(gate,ops):
    ref=gate['original_host_primary'];require(ref['sha256']==w.HOST_PRIMARY_SHA,'Original host primary differs')
    original=json.loads(bound(ref,gate,ops))
    require(original['original_image']==BASE and original['original_origin']==SOURCE_ORIGIN
            and original['original_flags']==ORIGINAL,'Original identity differs')
    require(set(gate['original_host_sources'])==set(HOST_FILES)
            and set(gate['original_host_files'])==set(HOST_FILES),'Five original refs required')
    for name in HOST_FILES:
        src=gate['original_host_sources'][name];snap=gate['original_host_files'][name]
        expected=original['original_file_sha256'][name]
        require(src['sha256']==snap['sha256']==expected,'Original file binding differs')
        require(snap['path']==gate['run_dir']+'/host-runtime-original/'+name
                and gate['receipt_hashes'].get(snap['path'])==expected,'Snapshot binding differs')
        bound(src,gate,ops)
    return original

def load(run, gate_path, ops, now):
    gate = read_json(gate_path); phase_gate(gate, now)
    require(run.name == Path(gate['run_dir']).name and run.parent == c.PRIVATE and not run.is_symlink(), 'Local run differs')
    path = run/'target-partial-source-return-proof.json'
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
    for name in SCRIPTS:
        local = Path(__file__).with_name(name)
        require(gate['script_hashes'].get(name) == digest(local), 'Helper SHA differs')
        require(sha_bytes(ops.read(gate['run_dir']+'/'+name)) == digest(local), 'Host helper SHA differs')
    original_binding(gate, ops)
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


# Runs under MacReturnOperations.remote_python's private full-primary wrapper.
# All host process calls use HostOperations (captured output and finite timeout).
def host_check(gate, values, *, stopped=False):
    import hashlib, subprocess
    from pathlib import Path
    import final_writer_open_once as hw
    op=hw.HostOperations();op.run=Path(gate['run_dir'])
    def call(args,**kw):return op.call(args,**kw)
    def read(path):
        p=Path(path);assert not p.is_symlink();return p.read_bytes()
    def h(b):return hashlib.sha256(b).hexdigest()
    def env(raw):return dict(v.split('=',1) for v in raw.decode().splitlines() if v and not v.startswith('#'))
    sources={n:read(gate['original_host_sources'][n]['path']) for n in hw.HOST_FILES}
    for n,b in sources.items():assert h(b)==gate['original_host_sources'][n]['sha256']
    current={n:read(str(hw.LIVE/('.local/service.env' if n=='service.env' else n))) for n in hw.HOST_FILES}
    changed=any(current[n]!=sources[n] for n in hw.HOST_FILES)
    for n in hw.HOST_FILES:
        p=Path(gate['original_host_files'][n]['path'])
        if changed:assert p.is_file(), 'Missing snapshot'
        if p.exists():assert read(p)==sources[n], 'Wrong snapshot'
    cfg=env(sources['service.env'])
    assert cfg['SUPABASE_URL'].rstrip('/')==hw.SOURCE_ORIGIN
    assert {k:cfg[k] for k in hw.ORIGINAL}==hw.ORIGINAL
    original_env=cfg.copy(); planned=sources.copy();target_image=None
    marker=hw.LIVE/'.local/selfhost-backup.json'
    if changed:
        # Exact bytes derived from originals + pinned, independently bound stage patches.
        stage=json.loads(values['stage_manifest'])
        manifest=json.loads(sources['build-manifest.json'])
        for n in ['access.py','gateway_journal.py']:
            change=stage['origin_only_changes'][n]
            assert change['before_sha256']==h(sources[n])==manifest[n]
            patch=read('/opt/dashboard-memory-stage-read-20261003/build/'+n)
            assert h(patch)==change['after_sha256'], 'Wrong stage patch'
            assert read(gate['run_dir']+'/runtime-build/'+n)==patch
            planned[n]=patch;manifest[n]=h(patch)
        assert read(gate['run_dir']+'/runtime-build/Dockerfile')==b'FROM dashboard-canonical-baseline:hz20261003\nCOPY access.py gateway_journal.py /app/\n'
        private=env(read(str(hw.ROOT/'.private.env')))
        cfg.update(hw.CLOSED);cfg.update(SUPABASE_URL=hw.ORIGIN,SUPABASE_PUBLISHABLE_KEY=private['ANON_KEY'].strip("'"))
        assert all('\n' not in v and '\r' not in v for v in cfg.values())
        planned['service.env']=''.join(k+'='+v+'\n' for k,v in cfg.items()).encode()
        compose=sources['compose.yaml'].decode();assert compose.count('image: dashboard-memory:memory-20260921-compact-guard-final')==1
        planned['compose.yaml']=compose.replace('image: dashboard-memory:memory-20260921-compact-guard-final','image: dashboard-memory:hetzner-final-20261003').encode()
        planned['build-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
        for n in hw.HOST_FILES:assert current[n] in (sources[n],planned[n]), 'Foreign host file'
        base=json.loads(call(['docker','image','inspect',hw.BASE]))[0]
        target=json.loads(call(['docker','image','inspect','dashboard-memory:hetzner-final-20261003']))[0]
        assert target['RootFS']['Layers'][:-1]==base['RootFS']['Layers']
        assert len(target['RootFS']['Layers'])==len(base['RootFS']['Layers'])+1
        target_image=target['Id']
        for n,expected in [('server.py',SERVER_SHA),('access.py',h(planned['access.py'])),('gateway_journal.py',h(planned['gateway_journal.py']))]:
            assert h(call(['docker','run','--rm','--network=none','--entrypoint','cat',target_image,'/app/'+n]))==expected
    x=json.loads(call(['docker','inspect',hw.CANONICAL]))[0]
    actual_env=dict(v.split('=',1) for v in x['Config']['Env'] if '=' in v)
    if x['Image']==hw.BASE:
        assert not x['State']['Running'], 'Canonical running'
        assert all(actual_env.get(k)==v for k,v in original_env.items())
        assert {k:actual_env[k] for k in hw.ORIGINAL}==hw.ORIGINAL
    else:
        assert changed and x['Image']==target_image, 'Foreign canonical image'
        assert all(actual_env.get(k)==v for k,v in cfg.items()), 'Foreign canonical environment'
        assert {k:actual_env[k] for k in hw.CLOSED}==hw.CLOSED
        assert marker.exists() and all(current[n]==planned[n] for n in hw.HOST_FILES)
    if stopped:assert not x['State']['Running'], 'Canonical running'
    if marker.exists():
        assert changed and type(json.loads(read(marker))['enabled']) is bool and json.loads(read(marker))=={'enabled':True,'migration_run':Path(gate['run_dir']).name}, 'Foreign marker'
        assert all(current[n]==planned[n] for n in hw.HOST_FILES)
    # Target API identity is pinned even if restore/config stopped halfway.
    services=['auth','rest','api-gw','functions'];apis=[]
    ids=call(['docker','compose','--env-file','.private.env','ps','-aq',*services],cwd=hw.ROOT).decode().split()
    assert len(ids)==4 and len(set(ids))==4
    seen=set()
    for cid in ids:
        a=json.loads(call(['docker','inspect',cid]))[0];labels=a['Config']['Labels']
        assert labels['com.docker.compose.project']=='dashboard-supabase-20261003', 'Foreign API project'
        service=labels['com.docker.compose.service'];assert service in services and service not in seen, 'Foreign API service';seen.add(service)
        assert a['Config']['Image']==API_IMAGES[service], 'Foreign API image'
        expected_image=json.loads(call(['docker','image','inspect',API_IMAGES[service]]))[0]['Id']
        assert a['Image']==expected_image, 'Foreign API image ID'
        assert set(a['NetworkSettings']['Networks'])==API_NETWORKS[service], 'Foreign API network'
        ports={k:v for k,v in a['NetworkSettings']['Ports'].items() if v}
        assert ports==({ '8000/tcp':[{'HostIp':'127.0.0.1','HostPort':'8800'}]} if service=='api-gw' and ports else {}), 'API published port'
        if stopped:assert not a['State']['Running'], 'API still running'
        apis.append({'id':cid,'service':service,'running':a['State']['Running']})
    restore=op.run/'final-restore-attempt.json'
    runtime_marker=op.run/'target-runtime-attempt.marker'
    runtime_attempt=runtime_marker.exists()
    assert restore.exists()
    restore_state=json.loads(read(restore))
    assert restore_state=={'phase':'final','attempt':1,'source_sha256':gate['dump_sha256'],
        'status':restore_state['status']}
    assert restore_state['status'] in ('running','COPY_COMPARE_PASSED_SERVICES_STOPPED')
    if runtime_attempt:
        assert read(runtime_marker)==b'single COPY-bound readonly activation'
        assert restore_state['status']=='COPY_COMPARE_PASSED_SERVICES_STOPPED'
    if not runtime_attempt:
        assert not changed and not marker.exists() and x['Image']==hw.BASE and not x['State']['Running']
    assert call(['systemctl','show','dashboard-job-backup.service','-p','ActiveState','--value']).strip()==b'inactive'
    assert call(['systemctl','show','dashboard-job-backup.timer','-p','ActiveState','--value']).strip()==b'inactive'
    assert call(['systemctl','is-enabled','dashboard-job-backup.timer']).strip()==b'enabled'
    assert h(read('/etc/systemd/system/dashboard-job-backup.timer'))==TIMER_SHA
    assert h(read(str(hw.LIVE/'scheduled_backup.py')))==hw.BACKUP_SHA
    nginx=read('/etc/nginx/sites-available/alexa');assert nginx in (values['nginx_original'],values['nginx_maintenance'])
    mount=next(m for m in x['Mounts'] if m['Destination']=='/app/.local')
    assert mount['Type']=='bind' and mount['Source']==str(hw.LIVE/'.local/cache')
    assert original_env['MEMORY_CACHE_DIR']=='/app/.local/projections-rc1-20260919'
    assert original_env['MEMORY_QA_OUTBOX']=='/app/.local/question-outbox'
    for rel in ['projections-rc1-20260919/response-outbox','question-outbox']:
        d=Path(mount['Source'])/rel;assert d.is_dir() and not list(d.rglob('*.json')), 'Outbox not empty'
    assert call(['docker','exec','-i','n8n_postgres','psql','-U','n8n','-d','n8n','-XqAt','-v','ON_ERROR_STOP=1'],input=b"SELECT count(*) FROM execution_entity WHERE \"workflowId\" IN ('nzyaKxs5Om9wuPEc','dashboardDriveMove','dashboardDriveWatch') AND status IN ('new','running','waiting');").strip()==b'0'
    return {'changed':changed,'canonical_running':x['State']['Running'],'runtime_attempt':runtime_attempt,'apis':apis}


class PartialOperations(r.MacReturnOperations):
    def read_stage(self,ref):
        require(ref['path']==STAGE_MANIFEST and re.fullmatch('[a-f0-9]{64}',ref['sha256']), 'Stage read outside exact contract')
        raw=c.shell('test ! -L '+shlex.quote(STAGE_MANIFEST)+' && cat '+shlex.quote(STAGE_MANIFEST),timeout=60)
        require(sha_bytes(raw)==ref['sha256'],'Stage primary SHA differs')
        return raw

    def observe_host(self,gate,values,stopped=False):
        import inspect
        code='import json\nfrom final_target_partial_source_return_once import SERVER_SHA,TIMER_SHA,API_IMAGES,API_NETWORKS\n'+inspect.getsource(host_check)
        code+='\nprint(json.dumps(host_check('+repr(gate)+','+repr(values)+',stopped='+repr(stopped)+')))'
        raw=self.remote_python(code,timeout=240)
        durable(self.local,'partial-host-observation-'+uuid.uuid4().hex+'.json',{'raw_b64':base64.b64encode(raw).decode()})
        return json.loads(raw)

    def frontend_guard(self,gate,values):
        receipt=json.loads(values['frontend'])
        require(receipt['problem_id']=='HZ-MIGRATION-20261003-FINAL-FRONTEND'
                and type(receipt['promotion_attempts']) is int and receipt['promotion_attempts']==0
                and receipt.get('url_env_added') is False and receipt.get('anon_env_added') is False,'Frontend promoted')
        for alias in sorted(ALIASES):
            x=json.loads(self.cli(['inspect',alias,'--format','json']))
            require(x['id']==r.OLD_DEPLOYMENT and x['readyState']=='READY','Frontend alias changed')
        # Read-only official CLI query, never rollback/promotion/env deletion.
        data=json.loads(self.cli(['env','ls','production','--format','json']))
        require(isinstance(data,dict) and isinstance(data.get('envs'),list),'Frontend env readback incomplete')
        require(not any(v['key'] in ('VITE_SUPABASE_URL','VITE_SUPABASE_ANON_KEY') for v in data['envs']),'Frontend env added')
        self.remote_python("from pathlib import Path\nr=Path("+repr(gate['run_dir'])+")\nassert not any('frontend' in p.name and ('attempt' in p.name or 'promotion' in p.name and 'receipt' in p.name) for p in r.iterdir())")
        require(not any('frontend' in p.name and ('attempt' in p.name or 'promotion' in p.name and 'receipt' in p.name) for p in self.local.iterdir()),'Frontend attempt exists')

    def source_frozen(self,values,frozen,names):
        from final_quiescence_once import acl_query,EFFECTIVE_PRIVILEGES_SQL
        require(self.source_sql(EFFECTIVE_PRIVILEGES_SQL)==[{'role':role,'writable_tables':0,'executable_writers':0} for role in ['anon','authenticated','service_role']],'Source API open')
        require(self.source_sql(acl_query())==json.loads(values['acl_frozen']),'Source ACL changed')
        rows=self.source_sql("SELECT json_build_object('running',(SELECT count(*) FROM public.wm_jobs WHERE state IN ('running','prepared')),'unknown_model',(SELECT count(*) FROM public.wm_model_calls WHERE received_at IS NULL AND redaction_id IS NULL),'unknown_question',(SELECT count(*) FROM public.wm_question_calls WHERE response_json IS NULL AND redaction_id IS NULL),'config',(SELECT json_agg(c ORDER BY space_id) FROM public.wm_processing_config c)) AS value")
        require(len(rows)==1 and set(rows[0])=={'value'},'Source state incomplete');state=rows[0]['value']
        require(all(type(state[k]) is int and state[k]==0 for k in ['running','unknown_model','unknown_question']),'Source calls outstanding')
        require(state['config']==[{**r,'enabled':False} for r in json.loads(values['config'])],'Source full CFG differs')
        cron=self.source_sql('SELECT count(*) AS count FROM cron.job WHERE active')
        require(type(cron) is list and len(cron)==1 and type(cron[0]) is dict and set(cron[0])=={'count'} and type(cron[0]['count']) is int and cron[0]['count']==0,'Source cron writer')
        self.source_projection(values,frozen,names)

    def source_projection(self,values,frozen,names):
        rows=self.source_sql(values['query'].decode())
        require(len(rows)==1 and set(rows[0])=={'value'} and projection(rows[0]['value'],names)==frozen,'Source43 differs')

    def scopes_guard(self,values):
        key=json.loads(values['scope_key'])
        rows=json.loads(c.n8n_sql('SELECT json_build_object(\'scopes\',scopes,\'userId\',"userId",\'md5\',md5("apiKey")) FROM user_api_keys WHERE id='+c.literal(key['id'])+';'))
        import hashlib
        require(rows['userId']==key['userId'] and rows['md5']==hashlib.md5(key['apiKey'].encode()).hexdigest(),'Scope owner changed')
        require(rows['scopes']==key['scopes']+['workflow:activate','workflow:deactivate'],'Own scopes changed')

    def preflight_partial(self,gate,values,frozen,names):
        self.remote=gate['run_dir']
        require(self.read(self.remote+'/prewrite-return-gate.json')==Path(self.gate_path).read_bytes(),'Host gate differs')
        self.markers_absent(self.remote);self.frontend_guard(gate,values)
        self.workflows(self.remote,False);self.scopes_guard(values);self.source_frozen(values,frozen,names)
        observation=self.observe_host(gate,values)
        if observation['runtime_attempt']:
            # APIs may have run: require exact Root ALLCOPY primary and current Target43.
            comparison=json.loads(bound(gate['allcopy_receipt'],gate,self))
            require(gate['allcopy_receipt']['path']==self.remote+'/final-snapshot-comparison.json'
                    and comparison['source_sha256']==gate['dump_sha256'] and not comparison['mismatches']
                    and comparison['comparison_before_auth_vault_acl'] is True,'Root ALLCOPY absent')
            require(projection(self.target_sql(values['query'].decode()),names)==frozen,'Target43 differs')
            require(self.target_sql("SELECT json_build_object('running',(SELECT count(*) FROM public.wm_jobs WHERE state IN ('running','prepared')),'unknown_model',(SELECT count(*) FROM public.wm_model_calls WHERE received_at IS NULL AND redaction_id IS NULL),'unknown_question',(SELECT count(*) FROM public.wm_question_calls WHERE response_json IS NULL AND redaction_id IS NULL))")=={'running':0,'unknown_model':0,'unknown_question':0},'Target calls outstanding')
            cron=self.target_sql('SELECT count(*) FROM cron.job WHERE active')
            require(type(cron) is int and cron==0,'Target cron writer')
        else:
            require(not observation['changed'] and not observation['canonical_running'],'Restore failed branch invalid')
            # host_check pins all four API identities; stop_partial proves actual inactivity
            # before Source grants. An inconsistent disposable DB is never restored here.
        return observation

    def stop_partial(self,gate,values):
        observation=self.observe_host(gate,values)
        if observation['canonical_running']:self.stop_target()
        self.remote_python("import subprocess\nfrom pathlib import Path\nfrom final_writer_open_once import HostOperations,ROOT\nop=HostOperations();op.run=Path("+repr(gate['run_dir'])+")\nop.call(['docker','compose','--env-file','.private.env','stop','auth','rest','api-gw','functions'],cwd=ROOT,timeout=120)",timeout=135)
        return self.observe_host(gate,values,stopped=True)

    def restore_partial_host(self,gate,values):
        self.observe_host(gate,values,stopped=True)
        refs=gate['original_host_sources']
        code='import hashlib,os,tempfile,json\nfrom pathlib import Path\n'
        for name in HOST_FILES:
            dest=str(LIVE/('.local/service.env' if name=='service.env' else name));ref=refs[name]
            code+=f"b=Path({ref['path']!r}).read_bytes();assert hashlib.sha256(b).hexdigest()=={ref['sha256']!r}\np=Path({dest!r});fd,t=tempfile.mkstemp(dir=p.parent);os.fchmod(fd,0o600)\nwith os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())\nos.replace(t,p);assert p.read_bytes()==b\n"
        code+=f"p=Path({str(LIVE/'.local/selfhost-backup.json')!r})\nif p.exists():\n assert json.loads(p.read_bytes())=={{'enabled':True,'migration_run':{Path(gate['run_dir']).name!r}}}\n p.unlink()\n"
        self.remote_python(code)

    def timer(self,gate):
        self.remote_python(f"""import hashlib,json
from pathlib import Path
from final_writer_open_once import HostOperations,LIVE,BACKUP_SHA,BASE,CANONICAL
op=HostOperations();op.run=Path({gate['run_dir']!r})
assert op.call(['systemctl','show','dashboard-job-backup.service','-p','ActiveState','--value']).strip()==b'inactive'
assert op.call(['systemctl','show','dashboard-job-backup.timer','-p','ActiveState','--value']).strip()==b'inactive'
assert op.call(['systemctl','is-enabled','dashboard-job-backup.timer']).strip()==b'enabled'
assert hashlib.sha256(Path('/etc/systemd/system/dashboard-job-backup.timer').read_bytes()).hexdigest()=={TIMER_SHA!r}
assert hashlib.sha256((LIVE/'scheduled_backup.py').read_bytes()).hexdigest()==BACKUP_SHA
op.call(['systemctl','start','dashboard-job-backup.timer'])
assert op.call(['systemctl','show','dashboard-job-backup.timer','-p','ActiveState','--value']).strip()==b'active'
""")


def proof_extra(gate,values,ops,now):
    timer=json.loads(values['timer_pause'])
    require(timer=={'problem_id':PROBLEM,'run_dir':gate['run_dir'],'status':'OWN_TIMER_PAUSED',
        'original_active':True,'original_enabled':True,'timer_unit_sha256':TIMER_SHA,'code_sha256':w.BACKUP_SHA},'Own timer pause absent')
    stage=gate['stage_manifest_ref']
    require(stage['path']==STAGE_MANIFEST,'Stage read outside exact contract')
    require(bound(stage,gate,ops)==values['stage_manifest'],'Stage primary differs')
    require(json.loads(values['stage_manifest'])['origin_only_changes']==STAGE_PATCHES,'Pinned stage patches differ')
    external=gate['external_target_writers']
    require(external['known_writers']==[] and 0<=(now-stamp(external['observed_at'])).total_seconds()<=300,'External writer known or observation stale')
    raw=json.loads(bound(external['primary_response'],gate,ops))
    require(raw=={'problem_id':PROBLEM,'run_dir':gate['run_dir'],'observed_at':external['observed_at'],
                 'known_external_target_writers':[],'scope':'Root inspected external Target writers'},'External writer primary differs')


def execute(run,gate_path,operations=None,now=None):
    run=Path(run);gate_path=Path(gate_path);ops=operations or PartialOperations(run)
    clock=(lambda:now) if now is not None else (lambda:dt.datetime.now(dt.timezone.utc))
    started=False;values=None
    try:
        require(run.is_dir() and not run.is_symlink() and run.stat().st_mode&0o077==0,'Unsafe private run')
        gate,proof,values,frozen,names=load(run,gate_path,ops,clock());proof_extra(gate,values,ops,clock())
        ops.gate_path=gate_path
        require(not (run/'target-partial-source-return-attempt.marker').exists(),'Partial return already attempted')
        ops.preflight_partial(gate,values,frozen,names)
        durable(run,'target-partial-source-return-attempt.marker',{'problem_id':PROBLEM,'run_dir':gate['run_dir'],'gate_sha256':digest(gate_path)})
        started=True
        def guard():
            load(run,gate_path,ops,clock());proof_extra(gate,values,ops,clock());ops.markers_absent(gate['run_dir'])
        guard();ops.maintenance(values)
        guard();ops.stop_partial(gate,values)
        # CURRENT equality immediately before grants, after all known Target processes stop.
        guard();ops.observe_host(gate,values,stopped=True)
        ops.frontend_guard(gate,values);ops.source_frozen(values,frozen,names)
        ops.markers_absent(gate['run_dir']);ops.restore_acl(values)
        guard();ops.restore_config(values)
        guard();ops.restore_partial_host(gate,values)
        source_gate={**gate,'original_host_files':gate['original_host_sources']}
        guard();ops.start_source(source_gate)
        ops.health(gate)
        guard();ops.ingress(values)
        guard();ops.resume(gate,gate_path,values)
        guard();ops.scopes(values)
        ops.frontend_guard(gate,values)
        # Source return proof precedes timer; completion receipt follows successful timer readback.
        durable(run,'target-partial-source-return-core-pass.json',{'status':'SOURCE_RETURN_PASS','problem_id':PROBLEM,
            'run_dir':gate['run_dir'],'target_data_reverted':False,'writer_opened':False})
        guard();ops.timer(gate)
        durable(run,'target-partial-source-return-receipt.json',{'status':'SOURCE_ORIGINAL_STATE_RETURNED',
            'problem_id':PROBLEM,'run_dir':gate['run_dir'],'target_data_reverted':False,'operational_GO':False})
        return 'SOURCE_ORIGINAL_STATE_RETURNED'
    except Exception as error:
        failure=r.private_error(error)
        if started and values is not None:
            try:ops.maintenance(values)
            except Exception as cleanup:r.private_error(cleanup)
        raise PreconditionsError(str(failure)) from None


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--gate-receipt',required=True)
    args=p.parse_args(argv);os.umask(0o077)
    try:execute(Path(args.run_dir),Path(args.gate_receipt))
    except Exception as error:
        print(json.dumps({'status':'STOP_RETURN_TO_ROOT','error_type':type(error).__name__}));return 1
    print(json.dumps({'status':'SOURCE_ORIGINAL_STATE_RETURNED'}));return 0

if __name__=='__main__':raise SystemExit(main())
