"""One permissions-only HOST continuation. LOCAL_PREP is not operational GO.

Root supplies target-runtime-permissions-proof.json and an independent fresh
actual-hash gate. Every observation includes hash-bound primary_receipts. This
helper never collects Source/provider facts, repeats DB stages or runs return.
The optional writer-compatible receipt describes CURRENT state, not historical
success. Its provenance preserves original runtime FAILED and recovery SHA.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
import final_target_runtime_once as rt
import final_target_partial_source_return_once as partial
import final_prewrite_rollback_once as r
import final_writer_open_once as w
import n8n_dashboard_pause_once as n8n

PHASE='PERMISSIONS_ONLY_TARGET_COMPLETION'
OLD_SHA='e301b63688dfc56ac9339b0bd4152648c41ee66a54f0df6d318c2dc8aaa90a0c'
PARTIAL_SHA='b04ffb635c314eb70744cff9a9321092134f685e9a95e20ad297710318dfc319'
STATIC='dashboard-memory:hetzner-final-20261003'
GOOD='dashboard-memory:hetzner-final-permissions-20261004'
BAD='dashboard-memory:hetzner-final-permission-failed-20261003'
NGINX=Path('/etc/nginx/sites-available/alexa')
STAGE=Path('/opt/dashboard-memory-stage-read-20261003/build')
OLD_DOCKERFILE=b'FROM dashboard-canonical-baseline:hz20261003\nCOPY access.py gateway_journal.py /app/\n'
DOCKERFILE=('FROM '+rt.BASE+'\nCOPY --chmod=0644 access.py gateway_journal.py /app/\n').encode()
ATTEMPT='target-runtime-permissions-attempt.marker'
RECOVERY='target-runtime-permissions-receipt.json'
PROOF='target-runtime-permissions-proof.json'
REFS={'baseline','source','target','config','vault','auth','workflows','frontend','writers','timer','prior_stages','failure','stage_manifest','nginx_original','nginx_maintenance'}
OBSERVATIONS={'source','target','vault','auth','workflows','frontend','writers','timer'}
require=w.require

def raw(path):
    p=Path(path);require(p.is_file() and not p.is_symlink(),'Unsafe primary file')
    return p.read_bytes()

def env(body):return dict(x.split('=',1) for x in body.decode().splitlines() if x and not x.startswith('#'))

def bound(ref,gate):
    require(Path(ref['path']).is_absolute() and re.fullmatch('[a-f0-9]{64}',ref['sha256'])
            and gate['receipt_hashes'].get(ref['path'])==ref['sha256'],'Unbound primary')
    b=raw(ref['path']);require(w.sha_bytes(b)==ref['sha256'],'Primary changed');return b

def phase_gate(gate,now):
    require(gate.get('problem_id')==w.PROBLEM and gate.get('phase')==PHASE
            and gate.get('decision')=='CONTINUE_BOUNDED' and gate.get('operational_target_go') is True,'No completion GO')
    require(re.fullmatch(re.escape(str(rt.ROOT))+r'/final-export-\d{8}T\d{6}Z',gate['run_dir']),'Wrong run')
    issued,expires=w.stamp(gate['issued_at']),w.stamp(gate['expires_at'])
    require(issued<=now<expires and 0<(expires-issued).total_seconds()<=600,'Gate stale')

def load(run,gate_path,now):
    gate=json.loads(raw(gate_path));phase_gate(gate,now)
    require(str(run)==gate['run_dir'] and run.parent==rt.ROOT and not run.is_symlink()
            and run.is_dir() and run.stat().st_mode&0o077==0,'Unsafe run')
    for name in ('final_target_runtime_once.py','final_target_partial_source_return_once.py',Path(__file__).name,'test_final_target_runtime_permissions_followup.py'):
        expected=w.digest(Path(__file__).with_name(name))
        require(gate['script_hashes'].get(name)==expected and w.digest(run/name)==expected,'Reviewed helper differs')
    require(w.digest(Path(rt.__file__))==OLD_SHA and w.digest(Path(partial.__file__))==PARTIAL_SHA,'Original helper changed')
    review=json.loads(bound(gate['followup_review'],gate))
    require(review['problem_id']==w.PROBLEM and review['scope']==PHASE
            and review['decision'] in ('ACCEPT','CONTINUE_BOUNDED') and review['operational_target_go'] is True
            and review['script_hashes']==gate['script_hashes']
            and review['provenance']['model']=='gpt-6-astra' and review['provenance']['effort']=='high'
            and review['provenance']['session'] and review['provenance']['sandbox']=='read-only'
            and 0<=(now-w.stamp(review['reviewed_at'])).total_seconds()<=600,'Fresh independent review absent')
    proof=json.loads(bound({'path':str(run/PROOF),'sha256':gate['receipt_hashes'][str(run/PROOF)]},gate))
    require(proof['problem_id']==w.PROBLEM and proof['run_dir']==str(run)
            and 0<=(now-w.stamp(proof['observed_at'])).total_seconds()<=300,'Proof stale or foreign')
    require(set(proof['refs'])==REFS,'Incomplete actual Root receipts')
    values={k:bound(v,gate) for k,v in proof['refs'].items()}
    data={k:json.loads(v) for k,v in values.items() if not k.startswith('nginx_')}
    for key in OBSERVATIONS:
        receipt=data[key]
        require(receipt['problem_id']==w.PROBLEM and receipt['run_dir']==str(run)
                and 0<=(now-w.stamp(receipt['observed_at'])).total_seconds()<=300,'Observation stale')
        require(receipt['primary_receipts'],'Actual observation primaries absent')
        for ref in receipt['primary_receipts']:bound(ref,gate)
    frozen=r.projection(data['baseline']['tables'],r.TABLES)
    require(data['baseline']['status']=='FROZEN_SOURCE_BUSINESS_BASELINE'
            and data['baseline']['captured_after_freeze'] is True and data['baseline']['query_sha256']==r.QUERY_SHA
            and data['baseline']['problem_id']==w.PROBLEM and data['baseline']['run_dir']==str(run),'Baseline differs')
    baseline_primary=json.loads(bound(data['baseline']['primary_response'],gate))
    require(baseline_primary==[{'value':data['baseline']['tables']}],'Baseline primary differs')
    source,target=data['source'],data['target']
    require(r.projection(source['tables'],r.TABLES)==frozen==r.projection(target['tables'],r.TABLES),'Source/Target43 differ')
    require(source['query_sha256']==target['query_sha256']==r.QUERY_SHA,'Query differs')
    require(source['roles']==[{'role':role,'writable_tables':0,'executable_writers':0} for role in ('anon','authenticated','service_role')],'Source rights open')
    config=data['config'];require(config and all(type(x['enabled']) is bool for x in config),'Full config missing')
    require(source['config']==[{**x,'enabled':False} for x in config] and target['config']==config,'Full config differs')
    for state in (source,target):
        require(all(type(state[k]) is int and state[k]==0 for k in ('running','unknown_model','unknown_question','cron'))
                and state['outboxes_empty'] is True,'Outstanding work')
    require(source['backend_running'] is False,'Source running')
    vault=data['vault'];original=json.loads(raw(run/'vault-plaintext.json'))[0]
    require(vault['plaintext_sha256']==hashlib.sha256(original['decrypted_secret'].encode()).hexdigest(),'Vault plaintext differs')
    for key in ('id','name','description','nonce_hex'):require(vault['metadata'][key]==original[key],'Vault metadata differs')
    for key in ('created_at','updated_at'):require(w.stamp(vault['metadata'][key])==w.stamp(original[key]),'Vault timestamp differs')
    auth=data['auth'];require(auth['source_user_hashes']==auth['target_user_hashes']==auth['original_user_hashes'] and bool(auth['original_user_hashes']),'Auth hashes differ')
    require(data['workflows']['versions']==n8n.VERSIONS and data['workflows']['active']==[] and data['workflows']['running']==0,'n8n not paused')
    front=data['frontend'];require(front['promotion_attempts']==0 and front['url_env_added'] is False and front['anon_env_added'] is False,'Frontend changed')
    require(set(front['aliases'])==set(w.ALIASES) and all(v=={'id':r.OLD_DEPLOYMENT,'readyState':'READY'} for v in front['aliases'].values())
            and not any(v['key'] in ('VITE_SUPABASE_URL','VITE_SUPABASE_ANON_KEY') for v in front['production_env']['envs'])
            and front['cli_format']=='json','Actual old frontend CLI required')
    require(data['writers']['known_writers']==[] and data['writers']['writer_attempts']==0,'Writer opened')
    require(data['timer']=={**{k:data['timer'][k] for k in ('problem_id','run_dir','observed_at','primary_receipts')},'status':'OWN_TIMER_PAUSED','original_active':True,'original_enabled':True,'timer_unit_sha256':partial.TIMER_SHA,'code_sha256':w.BACKUP_SHA},'Own timer differs')
    prior=data['prior_stages'];require(all(prior[k] is True for k in ('vault_plaintext_equal','vault_metadata_preserved','original_acl_restored','original_config_enabled_restored')) and prior['restore_attempts']==1 and prior['restore_status']=='PASS' and prior['original_runtime_attempts']==1 and prior['original_runtime_status']=='FAILED','Prior stages absent')
    for ref in prior['primary_receipts']:bound(ref,gate)
    require(prior['primary_receipts'],'Prior stages primaries absent')
    failure=data['failure'];require(failure['status']=='FAILED' and failure['failed_line']==131 and failure['cause']=='Permission denied' and failure['original_runtime_attempts']==1,'Original failure differs')
    bound(failure['primary_response'],gate)
    require(data['stage_manifest']['origin_only_changes']==partial.STAGE_PATCHES,'Stage patches differ')
    partial.original_binding(gate,type('Reader',(),{'read':staticmethod(raw),'read_stage':staticmethod(lambda ref:raw(ref['path']))})())
    require(values['nginx_original']==raw(run/'nginx-original.conf') and values['nginx_maintenance']==raw(run/'nginx-maintenance.conf'),'Ingress artifacts differ')
    return gate,values,data

class Operations:
    def __init__(self,run):self.run=run;self.errors=run/'permissions-private-errors'
    def call(self,args,**kw):return rt.run_process(args,operation='permissions-process',private_errors=self.errors,timeout=kw.pop('timeout',60),**kw)
    def inspect(self,name):return json.loads(self.call(['docker','image','inspect',name]))[0]
    def absent_image(self,name):
        require(not self.call(['docker','image','ls','--no-trunc','--quiet',name]).strip(),'Image alias already exists')
    def host(self,gate,values):
        # Existing immutable recovery guard is reused, never weakened.
        return partial.host_check(gate,values)
    def health(self):
        import time
        deadline=time.monotonic()+90
        while True:
            try:
                body,status,_=rt.http_read('http://127.0.0.1:8798/health',operation='permissions-health',private_errors=self.errors,timeout=5)
                require(status==200,'Health not ready');return json.loads(body)
            except RuntimeError:
                if time.monotonic()>=deadline:raise
                time.sleep(2)

def preflight(run,gate,values,data,op):
    require(not any((run/n).exists() for n in (ATTEMPT,RECOVERY,'target-runtime-receipt.json','host-runtime-original','source-original-runtime-flags.json','runtime-permissions-build')),'Completion already started')
    require(not (rt.LIVE/'.local/selfhost-backup.json').exists(),'Backup marker exists')
    require(not any(('writer' in x.name or 'frontend' in x.name) and ('attempt' in x.name or 'marker' in x.name or 'receipt' in x.name) for x in run.iterdir()),'Writer/frontend marker exists')
    require(raw(run/'target-runtime-attempt.marker')==b'single COPY-bound readonly activation','Original runtime marker differs')
    require(raw(run/'runtime-build/Dockerfile')==OLD_DOCKERFILE,'Original Dockerfile differs')
    for name,change in partial.STAGE_PATCHES.items():
        require(w.sha_bytes(raw(run/'runtime-build'/name))==w.sha_bytes(raw(STAGE/name))==change['after_sha256'],'Old code changed')
        require((run/'runtime-build'/name).stat().st_mode&0o777==0o600,'Original failed permissions differ')
    observation=op.host(gate,values)
    require(observation['changed'] is False and observation['canonical_running'] is False and observation['runtime_attempt'] is True,'Host no longer original')
    require(all(x['running'] is True for x in observation['apis']),'Prior APIs not running')
    base=op.inspect(rt.BASE);bad=op.inspect(STATIC)
    require(base['Config']['User']==bad['Config']['User']=='10001:10001','Default user differs')
    require(bad['Id']==data['failure']['bad_image'] and bad['RootFS']['Layers'][:-1]==base['RootFS']['Layers'] and len(bad['RootFS']['Layers'])==len(base['RootFS']['Layers'])+1,'Old bad image differs')
    # No privilege override: failed image content is attested by the original build
    # primary, not an impossible nonroot cat of its unreadable files.
    require(data['failure']['code_sha256']=={n:w.sha_bytes(raw(run/'runtime-build'/n)) for n in partial.STAGE_PATCHES}
            and data['failure']['dockerfile_sha256']==w.sha_bytes(OLD_DOCKERFILE),'Failure code provenance differs')
    op.absent_image(GOOD);op.absent_image(BAD)
    return bad['Id'],base

def activate(run,build,image_name,built_meta,op,counts,guard):
    # Straight copy of original activation contract (rt.main lines132-170).
    guard()
    backup=run/'host-runtime-original';backup.mkdir(mode=0o700)
    for name in w.HOST_FILES:
        source=rt.LIVE/('.local/service.env' if name=='service.env' else name)
        shutil.copyfile(source,backup/name);(backup/name).chmod(0o600)
    manifest=json.loads(raw(rt.LIVE/'build-manifest.json'))
    cfg=env(raw(rt.LIVE/'.local/service.env'));require(cfg['SUPABASE_URL'].rstrip('/')==w.SOURCE_ORIGIN,'Source origin differs')
    private=env(raw(rt.ROOT/'.private.env'))
    image=json.loads(op.call(['docker','inspect',w.CANONICAL]))[0]
    require(image['Image']==rt.BASE and not image['State']['Running'],'Source state changed')
    source_env=dict(item.split('=',1) for item in image['Config']['Env'] if '=' in item)
    original_flags={k:source_env.get(k,'0') for k in rt.CLOSED_FLAGS}
    require(original_flags=={k:cfg.get(k,'0') for k in rt.CLOSED_FLAGS}==w.ORIGINAL,'Original flags differ')
    r.durable(run,'source-original-runtime-flags.json',original_flags)
    cfg.update(rt.CLOSED_FLAGS);cfg.update(SUPABASE_URL=w.ORIGIN,SUPABASE_PUBLISHABLE_KEY=private['ANON_KEY'].strip("'"))
    rt.closed_flags(cfg);require(all('\n' not in x and '\r' not in x for x in cfg.values()),'Invalid env')
    rt.atomic(rt.LIVE/'.local/service.env',''.join(k+'='+v+'\n' for k,v in cfg.items()).encode())
    compose=raw(rt.LIVE/'compose.yaml').decode();require(compose.count('image: dashboard-memory:memory-20260921-compact-guard-final')==1,'Compose differs')
    rt.atomic(rt.LIVE/'compose.yaml',compose.replace('image: dashboard-memory:memory-20260921-compact-guard-final','image: '+image_name).encode())
    for name in partial.STAGE_PATCHES:rt.atomic(rt.LIVE/name,raw(build/name));manifest[name]=w.digest(build/name)
    rt.atomic(rt.LIVE/'build-manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())
    r.durable(rt.LIVE/'.local','selfhost-backup.json',{'enabled':True,'migration_run':run.name})
    guard()
    counts['backend_starts']=1
    op.call(['docker','compose','up','-d','--no-build','canonical-draft'],cwd=rt.LIVE,timeout=120)
    host_cfg=env(raw(rt.LIVE/'.local/service.env'));require(host_cfg==cfg,'Host config differs');rt.closed_flags(host_cfg)
    active=json.loads(op.call(['docker','inspect',w.CANONICAL]))[0]
    require(active['State']['Running'] and active['Image']==built_meta['Id'] and active['Config']['User']=='10001:10001','Runtime differs');rt.verify_container_flags(active)
    for name,expected in [('server.py',rt.SERVER_SHA)]+[(n,w.digest(build/n)) for n in partial.STAGE_PATCHES]:
        require(w.sha_bytes(op.call(['docker','exec',w.CANONICAL,'cat','/app/'+name]))==expected,'Active code differs')
    health=op.health()
    guard()
    nginx=NGINX;require(raw(nginx)==raw(run/'nginx-maintenance.conf'),'Maintenance changed')
    rt.atomic(nginx,raw(run/'nginx-original.conf'));op.call(['nginx','-t']);op.call(['systemctl','reload','nginx'])
    return health,host_cfg

def execute(run,gate_path,operations=None,now=None,project_current=False):
    run=Path(run);gate_path=Path(gate_path);op=operations or Operations(run)
    clock=(lambda:now) if now else (lambda:dt.datetime.now(dt.timezone.utc))
    started=False;counts={'corrected_image_builds':0,'host_completion_dispatches':0,'backend_starts':0}
    old_marker=None
    try:
        gate,values,data=load(run,gate_path,clock());bad,base=preflight(run,gate,values,data,op)
        old_marker=raw(run/'target-runtime-attempt.marker')
        r.durable(run,ATTEMPT,{'problem_id':w.PROBLEM,'gate_sha256':w.digest(gate_path),'helper_sha256':w.digest(__file__),'budget':{'builds':1,'host_completion_dispatches':1}});started=True
        phase_gate(gate,clock())
        op.call(['docker','tag',bad,BAD]);require(op.inspect(BAD)['Id']==bad,'Bad image alias differs')
        r.durable(run,'runtime-permissions-bad-image.json',{'bad_image':bad,'pinned_alias':BAD,'original_error_sha256':data['failure']['primary_response']['sha256']})
        build=run/'runtime-permissions-build';build.mkdir(mode=0o700)
        for name in partial.STAGE_PATCHES:shutil.copyfile(run/'runtime-build'/name,build/name);(build/name).chmod(0o600)
        (build/'Dockerfile').write_bytes(DOCKERFILE);(build/'Dockerfile').chmod(0o600)
        phase_gate(gate,clock());counts['corrected_image_builds']=1
        op.call(['docker','build','--pull=false','-t',GOOD,str(build)],timeout=120)
        good=op.inspect(GOOD)
        require(good['Config']['User']==base['Config']['User']=='10001:10001' and good['RootFS']['Layers'][:-1]==base['RootFS']['Layers'] and len(good['RootFS']['Layers'])==len(base['RootFS']['Layers'])+1,'Corrected image provenance differs')
        for name,expected in [('server.py',rt.SERVER_SHA)]+[(n,w.digest(build/n)) for n in partial.STAGE_PATCHES]:
            require(w.sha_bytes(op.call(['docker','run','--rm','--network=none','--entrypoint','cat',GOOD,'/app/'+name]))==expected,'Default nonroot SHA differs')
        r.durable(run,'runtime-permissions-nonroot-pass.json',{'image':good['Id'],'user':good['Config']['User'],'code_sha256':{n:w.digest(build/n) for n in partial.STAGE_PATCHES},'server_sha256':rt.SERVER_SHA})
        # Revalidate fresh Root evidence and original host immediately before live writes.
        load(run,gate_path,clock());require(op.host(gate,values)['changed'] is False,'Host changed during build')
        op.call(['docker','tag',good['Id'],STATIC]);require(op.inspect(STATIC)['Id']==good['Id'],'Static tag differs')
        counts['host_completion_dispatches']=1
        health,flags=activate(run,build,STATIC,good,op,counts,lambda:load(run,gate_path,clock()))
        require(raw(run/'target-runtime-attempt.marker')==old_marker and raw(run/'runtime-build/Dockerfile')==OLD_DOCKERFILE,'Original failure artifacts changed')
        result={'status':'RecoveredRuntime','problem_id':w.PROBLEM,'run_dir':str(run),'original_runtime_status':'FAILED','original_runtime_attempts':1,'original_error_sha256':data['failure']['primary_response']['sha256'],'bad_image':bad,'bad_image_alias':BAD,'corrected_image':good['Id'],'corrected_image_name':GOOD,'gate_sha256':w.digest(gate_path),'helper_sha256':w.digest(__file__),'original_helper_sha256':OLD_SHA,'closed_flags':{k:flags[k] for k in rt.CLOSED_FLAGS},'health':health,'counters':counts,'writers_opened':False,'prior_stages_ref':json.loads(raw(run/PROOF))['refs']['prior_stages']}
        r.durable(run,RECOVERY,result)
        if project_current:
            current={'status':'TARGET_READONLY_RUNTIME_ACTIVE','state_kind':'CURRENT_OPERATIONAL_STATE','original_runtime_attempt_status':'FAILED','recovery_status':'RecoveredRuntime','recovery_receipt_sha256':w.digest(run/RECOVERY),'original_error_sha256':result['original_error_sha256'],'closed_flags':rt.CLOSED_FLAGS,'base_image':rt.BASE,'target_image':good['Id'],'backend_origin':w.ORIGIN,'readonly':True,'automatic':False,'intake':False,'qa':False,'original_deletion':False,'writers_opened':False,'server_py_sha256':rt.SERVER_SHA,'backup_marker':True,'health':health,'original_flags_receipt':str(run/'source-original-runtime-flags.json'),'prior_stages_ref':result['prior_stages_ref']}
            current.update({k:data['prior_stages'][k] for k in ('vault_plaintext_equal','vault_metadata_preserved','original_acl_restored','original_config_enabled_restored')})
            r.durable(run,'target-runtime-receipt.json',current)
        return result
    except Exception as error:
        failure=rt.private_error('permissions-continuation',error,directory=op.errors,stdout=getattr(error,'stdout',None),stderr=getattr(error,'stderr',None))
        failure['sha256']=w.digest(failure['private_path'])
        r.durable(op.errors,'outcome-'+uuid.uuid4().hex+'.json',{'status':'STOP_RETURN_TO_ROOT','started':started,'counters':counts,'primary_error':failure,'partial_return_executed':False})
        raise w.PreconditionsError(json.dumps(failure)) from None

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',required=True);parser.add_argument('--gate-receipt',required=True);parser.add_argument('--project-current-state',action='store_true')
    args=parser.parse_args(argv);os.umask(0o077)
    try:execute(args.run_dir,args.gate_receipt,project_current=args.project_current_state)
    except Exception as error:print(json.dumps({'status':'STOP_RETURN_TO_ROOT','error_type':type(error).__name__}));return 1
    print(json.dumps({'status':'RecoveredRuntime','writers_opened':False}));return 0
if __name__=='__main__':raise SystemExit(main())
