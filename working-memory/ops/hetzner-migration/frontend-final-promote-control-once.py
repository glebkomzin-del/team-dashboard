"""Finite frozen promotion. Root supplies actual SHA-bound observations, not promises.

Gate JSON: problem_id/phase/action/run_dir/issued_at/expires_at, script_hashes,
receipt_hashes, independent_review and proof refs. proof.refs names are REFS below.
Each live observation has observed_at and primary_receipts. Backup/Mac observations
contain actual FULL archive ref and complete files inventory plus executed restores.
No collected observation or review is manufactured by this helper. Owner action uses
same prerequisite contract, with a SHA-bound canonical promotion receipt instead of
original aliases. This file does not execute Source return or open writers.
"""
import argparse
import base64
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
import final_owner_link_once as owner
import final_prewrite_rollback_once as late
import final_writer_open_once as writer
import n8n_dashboard_pause_once as n8n

OPS=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_frontend_promote',OPS/'frontend-final-promote-once.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
PROBLEM='HZ-MIGRATION-20261003-FINAL-CUTOVER'
PHASE='PROMOTE_FROZEN_FRONTEND_OWNER_FLOW'
ALIASES=original.ALIASES
PREVIEW=original.PREVIEW
ROLLBACK=original.ROLLBACK
ARTIFACT_SHA='f1c11b1f683f53b0dbc5e6c793350a25b9156a957787f0b0c335a1029c95829f'
ORIGINAL_SHA='face0473a52f55d7555604f2d3959673bfa51c5a4466e3d3f09085a3f79c4bb2'
OWNER_SHA='b2c3907652a69bb52e2f303e9e77ebdae0eb51be17c3da9542c70a6ac3b04c50'
REFS={'runtime_recovery','runtime_projection','runtime_failure','runtime_error','live',
      'baseline','source','target','vault_auth','workflows','writers','full_backup','mac_copy',
      'frontend','source_archive','return_contract','anon_key'}
SCRIPTS=(Path(__file__).name,'final_owner_link_recovered_once.py','test_final_frontend_control.py',
         'frontend-final-promote-once.py','final_owner_link_once.py','final_prewrite_rollback_once.py',
         'final_writer_open_once.py','final_phase_common.py','n8n_dashboard_pause_once.py')
ENV_FLAGS={'VITE_SUPABASE_URL':'url_env_added','VITE_SUPABASE_ANON_KEY':'anon_env_added'}
require=writer.require
sha=lambda body:hashlib.sha256(body).hexdigest()

def raw(path):
    path=Path(path);require(path.is_absolute() and path.is_file() and not path.is_symlink(),'Unsafe bound file')
    return path.read_bytes()

def digest(path):return sha(raw(Path(path).resolve()))

def private_dir(path):
    path=Path(path);path.mkdir(mode=0o700,parents=True,exist_ok=True)
    require(not path.is_symlink() and path.stat().st_mode&0o077==0,'Unsafe private directory')
    return path

def save(path,value,*,exclusive=True):
    """Exclusive immutable records; atomic snapshots are private and fsynced."""
    path=Path(path)
    if path.parent==OPS:
        require(path==original.RECEIPT and not path.parent.is_symlink(),'Noncanonical repo write')
    else:private_dir(path.parent)
    body=(json.dumps(value,indent=2)+'\n').encode()
    if exclusive:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
    else:
        require(not path.is_symlink(),'Unsafe receipt')
        tmp=path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def bound(ref,gate):
    require(re.fullmatch('[a-f0-9]{64}',ref['sha256']) and gate['receipt_hashes'].get(ref['path'])==ref['sha256'],'Unbound primary')
    body=raw(ref['path']);require(sha(body)==ref['sha256'],'Primary changed');return body

def fresh(data,gate,now):
    require(data['problem_id']==PROBLEM and data['run_dir']==gate['run_dir'] and
            0<=(now-writer.stamp(data['observed_at'])).total_seconds()<=300,'Stale/foreign actual observation')
    require(data['primary_receipts'],'No actual primary receipts')
    for ref in data['primary_receipts']:bound(ref,gate)

def validate_recovery(data,values,gate):
    recovery,projection,failure=data['runtime_recovery'],data['runtime_projection'],data['runtime_failure']
    require(recovery['status']=='RecoveredRuntime' and recovery['problem_id']==PROBLEM and recovery['run_dir']==gate['run_dir']
            and recovery['original_runtime_status']=='FAILED' and recovery['original_runtime_attempts']==1
            and recovery['original_helper_sha256']=='e301b63688dfc56ac9339b0bd4152648c41ee66a54f0df6d318c2dc8aaa90a0c'
            and recovery['writers_opened'] is False,'Real recovery absent')
    require(failure['status']=='FAILED' and failure['original_runtime_attempts']==1 and
            failure['primary_response']['sha256']==sha(values['runtime_error'])==recovery['original_error_sha256'], 'Original failure/error differs')
    require(bound(failure['primary_response'],gate)==values['runtime_error'],'Original error not bound')
    require(projection['status']=='TARGET_READONLY_RUNTIME_ACTIVE' and projection['state_kind']=='CURRENT_OPERATIONAL_STATE'
            and projection['original_runtime_attempt_status']=='FAILED' and projection['recovery_status']=='RecoveredRuntime'
            and projection['recovery_receipt_sha256']==sha(values['runtime_recovery'])
            and projection['original_error_sha256']==recovery['original_error_sha256']
            and projection['target_image']==recovery['corrected_image'] and projection['backend_origin']==owner.TARGET
            and projection['writers_opened'] is False,'Current recovery projection unbound')
    require(projection['closed_flags']==recovery['closed_flags']==owner.CLOSED_FLAGS,'Recovered flags open')
    require(projection['readonly'] is True and all(projection[k] is False for k in ('intake','automatic','qa','original_deletion')),'Projection open')
    for key in ('vault_plaintext_equal','vault_metadata_preserved','original_acl_restored','original_config_enabled_restored'):
        require(projection[key] is True,'Restored native prerequisite absent')
    live=data['live']
    require(live['running'] is True and live['image']==recovery['corrected_image'] and
            live['host_flags']==live['container_flags']==owner.CLOSED_FLAGS and live['health']['status']=='ok'
            and live['backend_origin']==owner.TARGET,'Actual native backend not healthy/closed')
    require(recovery['health']['status']==projection['health']['status']=='ok','Recovery unhealthy')

def load(gate_path,action,now=None):
    now=now or dt.datetime.now(dt.timezone.utc);gate=json.loads(raw(Path(gate_path).resolve()))
    require(gate['problem_id']==PROBLEM and gate['phase']==PHASE and gate['action']==action
            and gate['decision']=='CONTINUE_BOUNDED' and gate['operational_frontend_go'] is True,'No bounded frontend gate')
    require(re.fullmatch('/opt/dashboard-supabase-20261003/final-export-\\d{8}T\\d{6}Z',gate['run_dir']),'Foreign run')
    issued,expires=writer.stamp(gate['issued_at']),writer.stamp(gate['expires_at'])
    require(issued<=now<expires and 0<(expires-issued).total_seconds()<=600,'Gate expired')
    for name in SCRIPTS:require(gate['script_hashes'].get(name)==digest(OPS/name),'Unreviewed code')
    require(digest(OPS/'frontend-final-promote-once.py')==ORIGINAL_SHA and digest(OPS/'final_owner_link_once.py')==OWNER_SHA,'Original changed')
    require(digest(OPS/'frontend-target-artifact.json')==ARTIFACT_SHA==gate['artifact_sha256'],'Unpinned artifact')
    require(gate['project']=={'projectId':'prj_pWCB8TaGLQesLsT9me0jgT0FqcC5','orgId':'team_xbeBltwkXhOuVc8JUUR0CqoF'} and
            gate['preview']==PREVIEW and gate['budget']=={'env_add_each':1,'promotions':1,'owner_links':1,'automatic_retries':0},'Wrong project/artifact/budget')
    review=json.loads(bound(gate['independent_review'],gate))
    require(review['problem_id']==PROBLEM and review['scope']==PHASE and review['decision'] in ('ACCEPT','CONTINUE_BOUNDED')
            and review['conditional_technical_go'] is True and review['script_hashes']==gate['script_hashes']
            and review['artifact_sha256']==ARTIFACT_SHA and review['provenance']['model']=='gpt-6-astra'
            and review['provenance']['effort']=='high' and review['provenance']['sandbox']=='read-only'
            and bool(review['provenance']['session']) and 0<=(now-writer.stamp(review['reviewed_at'])).total_seconds()<=600,'Fresh actual-hash Astra review absent')
    proof=json.loads(bound(gate['proof'],gate));fresh(proof,gate,now)
    require(set(proof['refs'])==REFS,'Incomplete Root prerequisite refs')
    values={k:bound(ref,gate) for k,ref in proof['refs'].items()}
    data={k:json.loads(v) for k,v in values.items() if k not in ('runtime_error','source_archive','anon_key')}
    for name in ('live','source','target','vault_auth','workflows','writers','full_backup','mac_copy','frontend','return_contract'):
        fresh(data[name],gate,now)
    validate_recovery(data,values,gate)
    frozen=late.projection(data['baseline']['tables'],late.TABLES)
    require(data['baseline']['status']=='FROZEN_SOURCE_BUSINESS_BASELINE' and data['baseline']['captured_after_freeze'] is True
            and data['baseline']['query_sha256']==late.QUERY_SHA,'No postfreeze baseline')
    for name in ('source','target'):
        current=data[name];require(late.projection(current['tables'],late.TABLES)==frozen and current['query_sha256']==late.QUERY_SHA,'Source43/Target43 changed')
        require(all(type(current[k]) is int and current[k]==0 for k in ('running','unknown_model','unknown_question','cron')) and
                current['outboxes_empty'] is True,'Pending writes')
    source=data['source'];require(source['backend_running'] is False and source['roles']==[
        {'role':role,'writable_tables':0,'executable_writers':0} for role in ('anon','authenticated','service_role')], 'Source unfrozen')
    require(source['config'] and all(x['enabled'] is False for x in source['config']),'Source config open')
    require(data['writers']['known_writers']==[] and data['writers']['writer_attempts']==0 and
            data['writers']['writer_marker_absent'] is True,'Writer started')
    require(data['workflows']['versions']==n8n.VERSIONS and data['workflows']['active']==[] and data['workflows']['running']==0,'n8n not closed')
    auth=data['vault_auth'];require(auth['vault_plaintext_equal'] is True and auth['vault_metadata_preserved'] is True and
        auth['source_user_hashes']==auth['target_user_hashes']==auth['original_user_hashes'] and bool(auth['original_user_hashes']), 'Native Vault/Auth differs')
    require(len(data['live']['allowed_users'])==1 and re.fullmatch('[0-9a-f-]{36}',data['live']['allowed_users'][0]),'Owner allowlist differs')
    backup,mac=data['full_backup'],data['mac_copy']
    require(backup['status']=='PASS' and backup['kind']=='FULL' and backup['origin']=='CURRENT_RECOVERED_TARGET'
            and backup['runtime_recovery_sha256']==sha(values['runtime_recovery']) and
            all(backup['isolated_restores'][k]=='PASS' for k in ('selfhost','canonical','n8n')),'Actual Target FULL isolated restores absent')
    require(backup['files'] and len({x['path'] for x in backup['files']})==len(backup['files']) and all(re.fullmatch('[a-f0-9]{64}',x['sha256']) for x in backup['files']),'FULL file inventory absent')
    require(sha(bound(backup['archive'],gate))==backup['archive']['sha256'] and
            mac['status']=='PASS' and mac['same_archive'] is True and mac['all_files_verified'] is True and
            mac['files']==backup['files'] and mac['archive']['sha256']==backup['archive']['sha256']
            and sha(bound(mac['archive'],gate))==backup['archive']['sha256'],'Actual same Mac FULL archive absent')
    require(data['return_contract']['mode']=='HEALTH_BOUND_LATE_SOURCE_RETURN_ONLY' and
            data['return_contract']['helper_sha256']==digest(OPS/'final_prewrite_rollback_once.py') and
            data['return_contract']['partial_return_after_frontend_forbidden'] is True and
            data['return_contract']['fresh_actual_gate_required'] is True and data['return_contract']['writer_opened'] is False,'Late return contract absent')
    archive=data['frontend']['source104_archive']
    require(archive['files']==104 and archive['sha256']==sha(values['source_archive']) and gate['source104_archive_sha256']==archive['sha256'],'Source104 archive unbound')
    require(original.artifact['source_manifest_count']==104 and len(original.artifact['current_static_hashes'])==7,'Frozen inventory differs')
    key=values['anon_key'].decode().strip();require(sha(key.encode())==original.artifact['target_key_sha256'],'Native anon key differs')
    require(json.loads(base64.urlsafe_b64decode(key.split('.')[1]+'==='))['role']=='anon','Wrong key role')
    if action=='PROMOTE':
        front=data['frontend'];require(front['promotion_attempts']==0 and front['url_env_added'] is False and front['anon_env_added'] is False,'Prior frontend mutation')
        check_old(front['aliases']);require(not any(x['key'] in ENV_FLAGS for x in front['production_env']['envs']),'Original ENV present')
    else:
        promotion=json.loads(bound(data['frontend']['promotion_receipt'],gate))
        require(promotion['status']=='PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED' and promotion['promotion_attempts']==1 and
                promotion['url_env_added'] is True and promotion['anon_env_added'] is True and promotion['artifact_sha256']==ARTIFACT_SHA and
                promotion['runtime_recovery_sha256']==sha(values['runtime_recovery']),'Actual canonical promotion absent')
        check_production(data['frontend']['aliases'])
    return gate,values,data,key

def check_old(aliases):
    require(set(aliases)==ALIASES and all(v['id']==ROLLBACK and v['readyState']=='READY' for v in aliases.values()),'Original aliases differ')

def check_production(aliases):
    require(set(aliases)==ALIASES and {x['id'] for x in aliases.values()}=={PREVIEW} and
            all(x['readyState']=='READY' and x['target']=='production' and ALIASES.issubset(set(x['aliases'])) for x in aliases.values()),'Production aliases/artifact differ')

class Operations:
    def __init__(self,directory):self.directory=private_dir(directory)
    def cli(self,args,value=None):
        """Preserve all success/error output BEFORE caller parses or records ownership."""
        record={'args':args,'stdout_b64':None,'stderr_b64':None,'exit_code':None,'timeout':False}
        try:
            result=subprocess.run(['vercel',*args],cwd=original.BUILD,input=value,capture_output=True,text=True,timeout=240)
            record.update(stdout_b64=enc(result.stdout),stderr_b64=enc(result.stderr),exit_code=result.returncode)
        except Exception as error:
            record.update(stdout_b64=enc(getattr(error,'stdout',None)),stderr_b64=enc(getattr(error,'stderr',None)),
                          timeout=isinstance(error,subprocess.TimeoutExpired),error_type=type(error).__name__,error_text=str(error))
            save(self.directory/('cli-'+uuid.uuid4().hex+'.json'),record)
            raise RuntimeError('CLI ambiguous; private primary retained') from None
        save(self.directory/('cli-'+uuid.uuid4().hex+'.json'),record)
        require(result.returncode==0,'CLI failed; private primary retained')
        return result.stdout
    def aliases(self):return {a:json.loads(self.cli(['inspect',a,'--format','json'])) for a in sorted(ALIASES)}
    def env(self):return json.loads(self.cli(['env','ls','production','--format','json']))
    def http(self,url):
        body,status,headers=original.http_read(url,operation='frontend-control-http',private_errors=self.directory,timeout=45,preserve_success=True)
        return body,status,headers

def enc(value):return None if value is None else base64.b64encode(value.encode() if isinstance(value,str) else value).decode()

def verify_public(ops,output):
    checks=[];headers_expected=json.loads((output/'config.json').read_text())['routes'][0]['headers']
    for alias in sorted(ALIASES):
        for route in ('/','/memory-next?recovery=1'):
            body,status,headers=ops.http('https://'+alias+route)
            require(status==200 and body==(output/'static/index.html').read_bytes() and sha(body)==original.artifact['current_static_hashes']['static/index.html'],'Index bytes differ')
            require(all(headers.get(k)==v for k,v in headers_expected.items()),'Public headers/CSP differ')
            checks.append({'alias':alias,'route':route,'http':status,'sha256':sha(body),'exact_index':True,'exact_headers':True})
        for name,digest_expected in original.artifact['current_static_hashes'].items():
            if not name.startswith('static/assets/'):continue
            body,status,_=ops.http('https://'+alias+'/'+name.removeprefix('static/'))
            require(status==200 and sha(body)==digest_expected,'Asset bytes differ')
            checks.append({'alias':alias,'route':name,'sha256':sha(body),'exact_asset':True})
    return checks

def reconcile_once(ops,evidence,directory):
    """Finite read-only reconciliation: mere presence never proves ambiguous ownership."""
    result={'aliases':None,'production_env':None,'errors':[]}
    for key,reader in [('aliases',ops.aliases),('production_env',ops.env)]:
        try:result[key]=reader()
        except Exception as error:result['errors'].append({'observation':key,'cause':str(error)})
    save(directory/'reconciliation-once.json',result)
    env=result['production_env']
    if isinstance(env,dict) and isinstance(env.get('envs'),list) and not env.get('pagination',{}).get('next'):
        for name,flag in ENV_FLAGS.items():
            if evidence[flag] is None and not any(x.get('key')==name for x in env['envs']):
                evidence[flag]=False;evidence['ownership'][name]='UNCHANGED_ORIGINAL_ABSENCE'
    evidence['return_ownership_known']=all(type(evidence[k]) is bool for k in ENV_FLAGS.values())
    evidence['unknown_ownership']=[n for n,f in ENV_FLAGS.items() if evidence[f] is None]
    evidence['return_authorization']='REQUIRES_FRESH_HEALTH_BOUND_LATE_RETURN_GATE' if evidence['return_ownership_known'] else 'DENY_RETURN_UNKNOWN_OWNERSHIP'

def execute(gate_path,directory=None,operations=None,now=None,receipt=None):
    directory=private_dir(directory or original.PRIVATE/'final-control')
    gate,values,data,key=load(gate_path,'PROMOTE',now)
    output=original.frozen_checks();ops=operations or Operations(directory/'primaries')
    receipt=Path(receipt) if receipt else original.RECEIPT
    require(not receipt.exists(),'Canonical receipt already exists; no retry')
    save(directory/'frontend-control-attempt.marker',{'gate_sha256':digest(gate_path),'budget':gate['budget']})
    evidence={'problem_id':'HZ-MIGRATION-20261003-FINAL-FRONTEND','cutover_problem_id':PROBLEM,'status':'STARTED',
              'promotion_attempts':0,'auth_calls':0,'source_builds':0,'url_env_added':None,'anon_env_added':None,
              'ownership':{},'unknown_ownership':list(ENV_FLAGS),'return_ownership_known':False,
              'return_authorization':'DENY_RETURN_UNKNOWN_OWNERSHIP','gate_sha256':digest(gate_path),
              'script_hashes':gate['script_hashes'],'artifact_sha256':ARTIFACT_SHA,'preview':PREVIEW,
              'runtime_recovery_sha256':sha(values['runtime_recovery']),'runtime_projection_sha256':sha(values['runtime_projection']),
              'original_runtime_attempt_status':'FAILED','original_error_sha256':sha(values['runtime_error']),
              'full_backup_sha256':sha(values['full_backup']),'mac_copy_sha256':sha(values['mac_copy']), 'intents':{}}
    def persist():save(receipt,evidence,exclusive=False)
    persist()
    try:
        check_old(ops.aliases());env=ops.env()
        require(isinstance(env['envs'],list) and not env.get('pagination',{}).get('next') and not any(x['key'] in ENV_FLAGS for x in env['envs']),'Current original ENV absence unproven')
        evidence.update(url_env_added=False,anon_env_added=False,unknown_ownership=[],return_ownership_known=True)
        evidence['ownership']={n:'ORIGINAL_ABSENCE' for n in ENV_FLAGS};persist()
        for name,value in [('VITE_SUPABASE_URL',original.artifact['target_url']),('VITE_SUPABASE_ANON_KEY',key)]:
            load(gate_path,'PROMOTE',now);original.frozen_checks()
            flag=ENV_FLAGS[name];intent={'name':name,'environment':'production','value_sha256':sha(value.encode()),'budget':1,'gate_sha256':digest(gate_path)}
            save(directory/(name+'-INTENT.json'),intent)
            evidence['intents'][name]=intent;evidence[flag]=None;evidence['ownership'][name]='INTENT_OUTCOME_UNKNOWN'
            evidence['unknown_ownership']=[n for n,f in ENV_FLAGS.items() if evidence[f] is None]
            evidence['return_ownership_known']=False;evidence['return_authorization']='DENY_RETURN_UNKNOWN_OWNERSHIP';persist()
            ops.cli(['env','add',name,'production','--yes']+(['--sensitive'] if name=='VITE_SUPABASE_ANON_KEY' else []),value+'\n')
            evidence[flag]=True;evidence['ownership'][name]='OWN_ADD_CONFIRMED_EXIT_0'
            evidence['unknown_ownership']=[n for n,f in ENV_FLAGS.items() if evidence[f] is None]
            evidence['return_ownership_known']=not evidence['unknown_ownership']
            evidence['return_authorization']='REQUIRES_FRESH_HEALTH_BOUND_LATE_RETURN_GATE' if evidence['return_ownership_known'] else 'DENY_RETURN_UNKNOWN_OWNERSHIP';persist()
        load(gate_path,'PROMOTE',now);original.frozen_checks()
        save(directory/'promotion-INTENT.marker',{'preview':PREVIEW,'promotion_attempts':1,'gate_sha256':digest(gate_path)})
        evidence['promotion_attempts']=1;persist()
        ops.cli(['promote',PREVIEW,'--yes'])
        aliases=ops.aliases();check_production(aliases)
        prod=aliases[sorted(ALIASES)[0]];evidence['production']={k:prod[k] for k in ('id','readyState','target','aliases','url')};persist()
        evidence['checks']=verify_public(ops,output);original.frozen_checks()
        evidence['status']='PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED';persist();return evidence
    except Exception as error:
        save(directory/'primary-control-error.json',{'error_type':type(error).__name__,'cause':str(error)})
        evidence['status']='STOPPED_NO_RETRY';evidence['failure']={'private_path':str(directory/'primary-control-error.json')}
        try:reconcile_once(ops,evidence,directory)
        finally:persist()
        raise RuntimeError('Promotion stopped; durable canonical receipt and private primaries retained') from None

def main():
    p=argparse.ArgumentParser();p.add_argument('--gate-receipt',required=True);p.add_argument('--private-dir');a=p.parse_args()
    os.umask(0o077);result=execute(a.gate_receipt,a.private_dir)
    print(json.dumps({k:result[k] for k in ('status','promotion_attempts','auth_calls','source_builds')}))
if __name__=='__main__':main()
