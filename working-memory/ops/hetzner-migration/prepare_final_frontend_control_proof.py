"""LOCAL ONLY assembler for Root's actual read-only observations; never collects remotely.

Usage: --inputs /absolute/private/input.json --output /new/private/phase-dir
       --finalize /private/candidate-gate.json --review /actual/astra-review.json
                  --output /new/private/reviewed-dir
       --owner-bundle /private/OWNER-candidate.json --host-directory /opt/.../new-bundle
                      --host-files /private/mac-to-host-map.json --output /new/private/staging

Input schema (all refs are {path: absolute, sha256: exact bytes}):
 action PROMOTE|OWNER; run_dir; observations {source,native,frontend}: refs to
 Root envelopes {problem_id,run_dir,observed_at,payload,primary_receipts:[refs]}.
 source.payload is the read-only source query map business/auth/state/roles/acl/cron
 (Management API arrays; value rows where appropriate). native.payload contains
 target business/auth/state/acl/cron/vault, workflows, n8n_running, outboxes,
 canonical_inspect (raw Docker object), host_config (parsed actual service.env),
 health (actual HTTP JSON), container_inventory (all bounded running dashboard
 Docker objects), marker_checks (exact MARKERS basename -> exists bool),
 archive_current {archive,bytes,sha256,mac_sha256,manifest_sha256}.
 frontend.payload contains production_env plus actual inspect JSON by alias.
 originals refs: runtime_recovery,runtime_projection,runtime_failure,runtime_error,
 baseline,auth_original,cron_original,vault_original,config_original,
 full_status,mac_status,bundle_manifest,runtime_images,selfhost_restore,
 canonical_restore,n8n_restore,source_archive,anon_key.
 archives refs: full,mac. OWNER additionally promotion_receipt ref, containing
 actual canonical receipt and its bound primary_receipts, never a proposed result.
 All historical immutable originals retain bytes and provenance. Freshness comes
 from actual current observation envelopes, not timestamp renewal of old proofs.
 No operational GO is emitted without a real review and existing control.load.
 Host staging rewrites only generated wrappers; exact raw originals remain exact.
 host-files maps large archive Mac paths to existing native Host absolute paths;
 the Host must run this same --finalize/load after upload before Owner invocation.
 local_receipts maps immutable original Host paths to exact Mac refs where needed;
 all transitive original reference bytes must be available and SHA-equal.
 """
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

OPS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frontend_actual_control', OPS/'frontend-final-promote-control-once.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
MARKERS = ('writer-open-attempt.marker', 'owner-magiclink-attempt.marker',
           'owner-link-receipt.json', 'owner-recovered-control-attempt.marker',
           'frontend-final-promotion-evidence.json', 'frontend-final-promotion-started',
           'frontend-control-attempt.marker','promotion-INTENT.marker',
           'VITE_SUPABASE_URL-INTENT.json','VITE_SUPABASE_ANON_KEY-INTENT.json')
FRONTEND_MARKERS=set(MARKERS[4:])
ORIGINALS = {'runtime_recovery','runtime_projection','runtime_failure','runtime_error',
             'baseline','auth_original','cron_original','vault_original','config_original',
             'full_status','mac_status','bundle_manifest','runtime_images','selfhost_restore',
             'canonical_restore','n8n_restore','source_archive','anon_key'}
OBSERVATIONS = {'source','native','frontend'}
PROJECT = {'projectId':'prj_pWCB8TaGLQesLsT9me0jgT0FqcC5','orgId':'team_xbeBltwkXhOuVc8JUUR0CqoF'}
ERROR_SHA = '7a56d9ba20549a9dc50426563cd639f4bfb61258220249ebce65245846022f45'

def need(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path):
    path = Path(path)
    need(path.is_absolute() and path.is_file() and not path.is_symlink(), 'Unsafe primary path')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()

def read(ref):
    need(set(ref) == {'path','sha256'} and re.fullmatch('[a-f0-9]{64}',ref['sha256']), 'Invalid ref')
    need(digest(ref['path']) == ref['sha256'], 'Primary SHA mismatch')
    return Path(ref['path']).read_bytes()

def refs(value):
    """Provenance origin_refs are documentary; current operational refs are bound."""
    if isinstance(value, dict):
        if set(value) == {'path','sha256'} and Path(value['path']).is_absolute():
            yield value
        else:
            for key, item in value.items():
                if key != 'origin_refs':
                    yield from refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from refs(item)

def fresh(envelope, run, now):
    need(envelope['problem_id']==c.PROBLEM and envelope['run_dir']==run, 'Foreign primary envelope')
    need(0 <= (now-c.writer.stamp(envelope['observed_at'])).total_seconds() <= 300, 'Stale primary envelope')
    need(bool(envelope['primary_receipts']), 'No underlying primary receipts')
    payload_present=False
    for ref in envelope['primary_receipts']:
        body=read(ref)
        try: payload_present = payload_present or json.loads(body)==envelope['payload']
        except (ValueError,UnicodeDecodeError): pass
    need(payload_present, 'Envelope payload differs from underlying actual raw JSON')

def private_new(directory):
    directory = Path(directory)
    need(directory.is_absolute() and not directory.exists() and not directory.is_symlink(), 'Output must be exclusive/new')
    need(not any(p.is_symlink() for p in directory.parents), 'Symlink output ancestor')
    directory.mkdir(mode=0o700, parents=True)
    return directory

def write(directory, name, value):
    body = value if isinstance(value, bytes) else (json.dumps(value,indent=2)+'\n').encode()
    path = directory/name
    fd = os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(body); stream.flush(); os.fsync(stream.fileno())
    return {'path':str(path),'sha256':hashlib.sha256(body).hexdigest()}

def jsonref(ref): return json.loads(read(ref))
def one(rows):
    need(isinstance(rows,list) and len(rows)==1 and set(rows[0])=={'value'}, 'Expected exact API value row')
    return rows[0]['value']
def env(container): return dict(x.split('=',1) for x in container['Config']['Env'] if '=' in x)
def zero(value): return type(value) is int and value == 0

def prepare(input_path, output, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    inputs = json.loads(Path(input_path).read_bytes())
    need(inputs['action'] in ('PROMOTE','OWNER'), 'Unknown action')
    need(set(inputs['originals'])==ORIGINALS and set(inputs['observations'])==OBSERVATIONS, 'Missing/extra inputs')
    run = inputs['run_dir']
    need(re.fullmatch(r'/opt/dashboard-supabase-20261003/final-export-\d{8}T\d{6}Z',run), 'Foreign run')
    original_bytes = {k:read(ref) for k,ref in inputs['originals'].items()}
    originals = {k:json.loads(v) for k,v in original_bytes.items() if k not in ('runtime_error','source_archive','anon_key')}
    transitive=[];seen=set()
    def original_chain(value):
        for ref in refs(value):
            if (ref['path'],ref['sha256']) in seen: continue
            seen.add((ref['path'],ref['sha256']))
            local=inputs.get('local_receipts',{}).get(ref['path'],ref)
            need(local['sha256']==ref['sha256'], 'Original Host/Mac primary SHA differs')
            body=read(local);transitive.append(local)
            try: original_chain(json.loads(body))
            except (ValueError,UnicodeDecodeError) as error:
                # Non-JSON error/archive bytes are legitimate leaf primaries;
                # validation errors from the recursive reference walk propagate.
                if not isinstance(error,(json.JSONDecodeError,UnicodeDecodeError)): raise
    for value in originals.values(): original_chain(value)
    envelopes = {k:jsonref(ref) for k,ref in inputs['observations'].items()}
    for envelope in envelopes.values(): fresh(envelope,run,now)
    source,native,front = (envelopes[k]['payload'] for k in ('source','native','frontend'))
    recovery = originals['runtime_recovery']
    need(hashlib.sha256(original_bytes['runtime_error']).hexdigest()==ERROR_SHA==recovery['original_error_sha256'], 'Exact original Host failure bytes absent')
    need(originals['runtime_failure']['status']=='FAILED' and originals['runtime_failure']['original_runtime_attempts']==1
         and originals['runtime_failure']['primary_response']['sha256']==ERROR_SHA, 'Original FAILED provenance absent')
    frozen = c.late.projection(originals['baseline']['tables'],c.late.TABLES)
    need(originals['baseline']['captured_after_freeze'] is True and originals['baseline']['query_sha256']==c.late.QUERY_SHA,
         'Actual frozen baseline absent')
    tables = {'source':one(source['business']),'target':native['target']['business']}
    states = {'source':one(source['state']),'target':native['target']['state']}
    for name in ('source','target'):
        need(c.late.projection(tables[name],c.late.TABLES)==frozen, 'Source/Target43 differs')
        need(all(zero(states[name][k]) for k in ('running','unknown_model','unknown_question','cron','queued_http')), 'Pending calls/active cron/queue')
    roles = [{'role':role,'writable_tables':0,'executable_writers':0} for role in ('anon','authenticated','service_role')]
    need(source['roles']==roles and all(type(row[k]) is int for row in source['roles']
         for k in ('writable_tables','executable_writers')) and source['acl']==[], 'Source effective ACL not closed')
    need(states['source']['config']==[{**x,'enabled':False} for x in originals['config_original']]
         and bool(states['source']['config']), 'Source actual config not disabled')
    need(one(source['cron'])==native['target']['cron']==originals['cron_original'], 'Original two inactive Cron definitions changed')
    need(len(originals['cron_original'])==2 and all(x['active'] is False for x in originals['cron_original']), 'Inactive Cron contract absent')
    original_auth=originals['auth_original']['original_user_hashes']
    need(one(source['auth'])==native['target']['auth']==original_auth and bool(original_auth), 'Source/Target/original Auth differs')
    vault = originals['vault_original']
    if isinstance(vault,list):
        need(len(vault)==1, 'Original Vault coverage'); vault=vault[0]
    actual_vault=native['target']['vault']; metadata=actual_vault['metadata']
    need(actual_vault['plaintext_sha256']==hashlib.sha256(vault['decrypted_secret'].encode()).hexdigest(), 'Vault plaintext differs')
    need(all(metadata[k]==vault[k] for k in ('id','name','description','nonce_hex')) and
         all(c.writer.stamp(metadata[k])==c.writer.stamp(vault[k]) for k in ('created_at','updated_at')), 'Vault metadata differs')
    canonical=native['canonical_inspect']; actual_env=env(canonical); config=native['host_config']
    need(canonical['State']['Running'] is True and canonical['Image']==recovery['corrected_image'], 'Recovered runtime not running')
    need({k:actual_env[k] for k in c.owner.CLOSED_FLAGS}=={k:config[k] for k in c.owner.CLOSED_FLAGS}==c.owner.CLOSED_FLAGS,
         'Five native flags not closed')
    need(actual_env['SUPABASE_URL']==config['SUPABASE_URL']==c.owner.TARGET and native['health']['status']=='ok', 'Current runtime origin/health differs')
    allowed=config['MEMORY_ALLOWED_USERS'].split(',')
    need(actual_env['MEMORY_ALLOWED_USERS'].split(',')==allowed and len(allowed)==1 and allowed==[original_auth[0]['id']], 'Owner allowlist differs')
    inventory=native['container_inventory']
    need(isinstance(inventory,list) and bool(inventory) and len({x['Id'] for x in inventory})==len(inventory), 'Bounded actual container inventory absent')
    need(any(x['Id']==canonical['Id'] and x==canonical for x in inventory), 'Actual canonical absent from inventory')
    for container in inventory:
        need(container['State']['Running'] is True, 'Running inventory ambiguous')
        e=env(container)
        need(not any(e.get(k) not in ('0',None) for k in ('MEMORY_INTAKE_ENABLED','MEMORY_AUTOMATIC_ENABLED','MEMORY_QA_ENABLED','MEMORY_ORIGINAL_DELETION_ENABLED'))
             and e.get('MEMORY_READ_ONLY')=='1', 'Known running dashboard writer')
        need(e.get('SUPABASE_URL','').rstrip('/')!=c.late.SOURCE_ORIGIN.rstrip('/'), 'Source backend still running')
    markers=native['marker_checks']
    need(set(markers)==set(MARKERS) and all(type(x) is bool for x in markers.values()), 'Exact marker checks absent')
    need(all(markers[k] is False for k in MARKERS if k not in FRONTEND_MARKERS), 'Owner/Writer already attempted')
    if inputs['action']=='PROMOTE': need(all(x is False for x in markers.values()), 'Prior frontend attempt')
    need(set(native['workflows'])==set(c.n8n.VERSIONS) and all(w['id']==key and w['versionId']==c.n8n.VERSIONS[key]
         and w['active'] is False for key,w in native['workflows'].items()) and zero(native['n8n_running']), 'n8n version/active execution differs')
    need(set(native['outboxes'])=={'projections-rc1-20260919/response-outbox','question-outbox'}
         and all(zero(x) for x in native['outboxes'].values()), 'Actual outbox coverage/emptiness absent')
    backup,mac,manifest=originals['full_status'],originals['mac_status'],originals['bundle_manifest']
    ms=mac['status']; archive=native['archive_current']
    need(backup['state']==ms['state']=='ok' and backup['archive']==ms['archive']==archive['archive']
         and backup['bytes']==ms['bytes']==archive['bytes'] and backup['sha256']==ms['sha256']==archive['sha256']==archive['mac_sha256'], 'Current same FULL archive absent')
    need(backup['selfhost']['restore_verified'] is True and backup['canonical']['verified'] is True
         and backup['n8n']['credential_decryption_verified'] is True and backup['n8n']['google_refresh_token_preserved'] is True
         and backup['n8n']['external_network'] is False and zero(backup['n8n']['active']) and zero(backup['n8n']['published']), 'Executed isolated restores absent')
    need(originals['runtime_images']['memory']['image_id']==recovery['corrected_image'], 'FULL archive is not corrected runtime')
    need(manifest['format']=='dashboard-full-backup-v1' and len(manifest['files'])==202==ms['files_verified']
         and archive['manifest_sha256']==inputs['originals']['bundle_manifest']['sha256'], 'Actual 202-file manifest absent')
    for key,member in (('runtime_images','runtime-images.json'),('selfhost_restore','selfhost/restore-check.json'),
                       ('canonical_restore','canonical/restore-check.json'),('n8n_restore','n8n-restore-check.json')):
        need(manifest['files'][member]['sha256']==inputs['originals'][key]['sha256'], 'Archived restore/runtime receipt SHA differs')
    selfhost,canonical_restore,n8n_restore=(originals[k] for k in ('selfhost_restore','canonical_restore','n8n_restore'))
    need(all(selfhost[k] is True for k in ('auth_users_verified','vault_decryption_verified','roles_verified'))
         and selfhost['external_network'] is False and selfhost['services_started']==['postgres'], 'Actual isolated selfhost restore absent')
    need(canonical_restore['verified'] is True and zero(canonical_restore['model_api_calls']), 'Actual isolated canonical restore absent')
    need(n8n_restore==backup['n8n'], 'Actual archived n8n restore differs from successful backup')
    files=[{'path':name,'sha256':value['sha256']} for name,value in sorted(manifest['files'].items())]
    need(all(not Path(x['path']).is_absolute() and '..' not in Path(x['path']).parts and re.fullmatch('[a-f0-9]{64}',x['sha256']) for x in files), 'Unsafe FULL inventory')
    for ref in inputs['archives'].values():
        need(ref['sha256']==archive['sha256'] and digest(ref['path'])==ref['sha256'] and Path(ref['path']).stat().st_size==archive['bytes'], 'Current archive bytes differ')
    need(set(inputs['archives'])=={'full','mac'}, 'Archive coverage differs')
    if inputs['action']=='PROMOTE':
        c.check_old({a:front[a] for a in c.ALIASES})
        need(not front['production_env'].get('pagination',{}).get('next')
             and not any(x['key'] in c.ENV_FLAGS for x in front['production_env']['envs']), 'Frontend ENV absence incomplete')
    else:
        promotion=jsonref(inputs['promotion_receipt'])
        need(promotion['status']=='PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED' and promotion['url_env_added'] is True
             and promotion['anon_env_added'] is True and promotion['promotion_attempts']==1
             and promotion['return_ownership_known'] is True and promotion['unknown_ownership']==[]
             and all(promotion['ownership'][k]=='OWN_ADD_CONFIRMED_EXIT_0' for k in c.ENV_FLAGS), 'Actual ENV ownership/promotion absent')
        c.check_production({a:front[a] for a in c.ALIASES},promotion['production_deployment_id'])
        need(not front['production_env'].get('pagination',{}).get('next')
             and set(c.ENV_FLAGS).issubset({x['key'] for x in front['production_env']['envs']}), 'Current owned frontend ENV absent/incomplete')
    # Only now produce candidate wrappers; no claimed operational approval.
    directory=private_new(output); hashes={}; copied={}
    def retain(ref):
        if ref['path'] in copied: return copied[ref['path']]
        new=write(directory,'primary-'+str(len(copied))+'.raw',read(ref));copied[ref['path']]=new;hashes[new['path']]=new['sha256'];return new
    for group in ('originals','observations'):
        for ref in inputs[group].values(): retain(ref)
    for e in envelopes.values():
        for ref in e['primary_receipts']: retain(ref)
    def observation(group, **values):
        e=envelopes[group]
        return {'problem_id':c.PROBLEM,'run_dir':run,'observed_at':e['observed_at'],
                'primary_receipts':[retain(inputs['observations'][group]),*(retain(x) for x in e['primary_receipts'])],**values}
    raw_refs={k:retain(inputs['originals'][k]) for k in ('runtime_recovery','runtime_projection','runtime_error','baseline','source_archive','anon_key')}
    failure={**originals['runtime_failure'],'primary_response':raw_refs['runtime_error'],
             'origin_refs':[inputs['originals']['runtime_failure'],originals['runtime_failure']['primary_response']]}
    data={'runtime_failure':failure,
          'live':observation('native',running=True,image=canonical['Image'],host_flags={k:config[k] for k in c.owner.CLOSED_FLAGS},
              container_flags={k:actual_env[k] for k in c.owner.CLOSED_FLAGS},health=native['health'],backend_origin=actual_env['SUPABASE_URL'],allowed_users=allowed),
          'source':observation('source',tables=tables['source'],query_sha256=c.late.QUERY_SHA,**{k:states['source'][k] for k in ('running','unknown_model','unknown_question','cron')},
              queued_http=states['source']['queued_http'],outboxes_empty=True,backend_running=False,roles=source['roles'],acl=source['acl'],config=states['source']['config']),
          'target':observation('native',tables=tables['target'],query_sha256=c.late.QUERY_SHA,**{k:states['target'][k] for k in ('running','unknown_model','unknown_question','cron')},
              queued_http=states['target']['queued_http'],outboxes_empty=True),
          'vault_auth':observation('native',vault_plaintext_equal=True,vault_metadata_preserved=True,source_user_hashes=one(source['auth']),target_user_hashes=native['target']['auth'],original_user_hashes=original_auth),
          'workflows':observation('native',versions={k:w['versionId'] for k,w in native['workflows'].items()},active=[],running=native['n8n_running']),
          'writers':observation('native',known_writers=[],writer_attempts=0,writer_marker_absent=True,scope='Root bounded dashboard containers and exact Owner/Writer markers'),
          'full_backup':observation('native',status='PASS',kind='FULL',origin='CURRENT_RECOVERED_TARGET',runtime_recovery_sha256=raw_refs['runtime_recovery']['sha256'],
              isolated_restores={k:'PASS' for k in ('selfhost','canonical','n8n')},files=files,archive=inputs['archives']['full']),
          'mac_copy':observation('native',status='PASS',same_archive=True,all_files_verified=True,files=files,archive=inputs['archives']['mac']),
          'frontend':observation('frontend',promotion_attempts=0 if inputs['action']=='PROMOTE' else 1,url_env_added=inputs['action']=='OWNER',anon_env_added=inputs['action']=='OWNER',
              aliases={a:front[a] for a in c.ALIASES},production_env=front['production_env'],source104_archive={'files':104,'sha256':raw_refs['source_archive']['sha256']}),
          'return_contract':observation('native',mode='HEALTH_BOUND_LATE_SOURCE_RETURN_ONLY',helper_sha256=c.digest(OPS/'final_prewrite_rollback_once.py'),
              partial_return_after_frontend_forbidden=True,fresh_actual_gate_required=True,writer_opened=False,execution_status='PENDING')}
    # Bind all original records used to derive positives, not only convenient ones.
    historical=[retain(ref) for ref in [*inputs['originals'].values(),*transitive]]
    for k,v in data.items():
        if 'primary_receipts' in v: v['primary_receipts'] += historical
    data['source']['primary_receipts'] += data['writers']['primary_receipts']
    data['vault_auth']['primary_receipts'] += data['source']['primary_receipts']
    if inputs['action']=='OWNER':
        data['frontend']['promotion_receipt']=retain(inputs['promotion_receipt'])
        for ref in refs(promotion):
            # Promotion originals remain byte-exact, transitive refs stay bound.
            read(ref);hashes[ref['path']]=ref['sha256']
    for name,value in data.items(): raw_refs[name]=write(directory,name+'.json',value)
    proof=observation('native',refs=raw_refs)
    proof_ref=write(directory,'proof.json',proof)
    for ref in [proof_ref,*raw_refs.values(),*inputs['archives'].values()]: hashes[ref['path']]=ref['sha256']
    gate={'problem_id':c.PROBLEM,'phase':c.PHASE,'action':inputs['action'],'run_dir':run,'decision':'DENY_PENDING_REVIEW',
          'operational_frontend_go':False,'issued_at':now.isoformat(),'expires_at':(now+dt.timedelta(seconds=600)).isoformat(),
          'script_hashes':{n:c.digest(OPS/n) for n in c.SCRIPTS},'receipt_hashes':hashes,'artifact_sha256':c.ARTIFACT_SHA,
          'source104_archive_sha256':raw_refs['source_archive']['sha256'],'preview':c.PREVIEW,'project':PROJECT,
          'budget':{'env_add_each':1,'promotions':1,'owner_links':1,'automatic_retries':0},'proof':proof_ref,
          'preparation_only':True,'collector_sha256':digest(Path(__file__).resolve()),'origin_refs':inputs}
    result=write(directory,'candidate-gate.json',gate)
    write(directory,'preparation-result.json',{'status':'CANDIDATE_ONLY_PENDING_ACTUAL_REVIEW_AND_CONTROL_LOAD','candidate':result,
          'provider_calls':0,'promotion_actions':0,'owner_actions':0,'writer_actions':0,'late_return':'PENDING'})
    return result

def finalize(candidate_path, review_path, output, now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    gate=json.loads(Path(candidate_path).read_bytes())
    need(gate['operational_frontend_go'] is False and gate['decision']=='DENY_PENDING_REVIEW', 'Not an unapproved candidate')
    review_ref={'path':str(Path(review_path).absolute()),'sha256':digest(Path(review_path).absolute())}
    gate['independent_review']=review_ref;gate['receipt_hashes'][review_ref['path']]=review_ref['sha256']
    gate.update(operational_frontend_go=True,decision='CONTINUE_BOUNDED',preparation_only=False)
    directory=private_new(output);pending=write(directory,'validation-only-gate.json',gate)
    # Exact existing validator; does not call CLI, SSH, Auth, or any provider.
    c.load(pending['path'],gate['action'],now)
    path=write(directory,'reviewed-gate.json',gate)
    write(directory,'dry-load-result.json',{'status':'LOCAL_CONTROL_LOAD_VALIDATED','action':gate['action'],
          'gate':path,'validated_at':now.isoformat(),'production_action_executed':False})
    return path

def owner_bundle(candidate_path, host_directory, host_files_path, output):
    gate=json.loads(Path(candidate_path).read_bytes());need(gate['action']=='OWNER' and gate['operational_frontend_go'] is False,'Fresh OWNER candidate required')
    destination=Path(host_directory)
    need(destination.is_absolute() and destination.parent==Path(gate['run_dir']) and '..' not in destination.parts, 'Host bundle must be under actual run')
    aliases=json.loads(Path(host_files_path).read_bytes());directory=private_new(output)
    proof=jsonref(gate['proof'])
    generated={gate['proof']['path'],*(r['path'] for k,r in proof['refs'].items() if k not in ('runtime_recovery','runtime_projection','runtime_error','baseline','source_archive','anon_key'))}
    mapping={};manifest=[]
    for index,(path,sha) in enumerate(gate['receipt_hashes'].items()):
        ref={'path':path,'sha256':sha}
        if path in aliases:
            target=aliases[path];need(Path(target).is_absolute() and '..' not in Path(target).parts,'Unsafe native Host path')
            mapping[path]={'path':target,'sha256':sha};manifest.append({'origin_ref':ref,'host_ref':mapping[path],'existing_host_file':True});continue
        need(Path(path).stat().st_size<32*1024*1024, 'Large input needs explicit existing Host mapping')
        body=read(ref);local=write(directory,'bound-'+str(index)+'.raw',body)
        mapping[path]={'path':str(destination/Path(local['path']).name),'sha256':sha}
        manifest.append({'origin_ref':ref,'staged_ref':local,'host_ref':mapping[path],'existing_host_file':False})
    def remap(value):
        if isinstance(value,dict):
            if set(value)=={'path','sha256'} and Path(value['path']).is_absolute(): return mapping[value['path']]
            return {k:v if k=='origin_refs' else remap(v) for k,v in value.items()}
        if isinstance(value,list): return [remap(v) for v in value]
        return value
    # Bottom-up: rewrite generated observation wrappers, then proof. Originals stay raw.
    for path in [p for p in generated if p!=gate['proof']['path']]+[gate['proof']['path']]:
        old=mapping[path];value=remap(json.loads(Path(path).read_bytes()))
        value['origin_refs']=[{'path':path,'sha256':gate['receipt_hashes'][path]}]
        new=write(directory,'remapped-'+Path(old['path']).name,value)
        mapping[path]={'path':str(destination/Path(new['path']).name),'sha256':new['sha256']}
        manifest.append({'origin_ref':{'path':path,'sha256':gate['receipt_hashes'][path]},'staged_ref':new,'host_ref':mapping[path],'generated_wrapper':True})
    host_gate={**gate,'proof':mapping[gate['proof']['path']],
               'receipt_hashes':{v['path']:v['sha256'] for v in mapping.values()},
               'origin_refs':[{'path':str(candidate_path),'sha256':digest(Path(candidate_path).absolute())}]}
    result=write(directory,'owner-host-candidate-gate.json',host_gate)
    write(directory,'host-bundle-manifest.json',{'status':'STAGED_ONLY_NOT_UPLOADED_NOT_HOST_VALIDATED','destination':str(destination),
          'files':manifest,'candidate':result,'host_finalize_and_readonly_load_required':True,
          'actual_host_runtime_projection_sha256_required':proof['refs']['runtime_projection']['sha256'],
          'actual_host_recovery_sha256_required':proof['refs']['runtime_recovery']['sha256']})
    return result

def main():
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--inputs');group.add_argument('--finalize');group.add_argument('--owner-bundle')
    p.add_argument('--review');p.add_argument('--host-directory');p.add_argument('--host-files');p.add_argument('--output',required=True)
    a=p.parse_args();os.umask(0o077)
    if a.inputs: result=prepare(a.inputs,a.output)
    elif a.finalize: need(bool(a.review),'Actual review path required');result=finalize(a.finalize,a.review,a.output)
    else:
        need(bool(a.host_directory and a.host_files),'Host destination/map required')
        result=owner_bundle(a.owner_bundle,a.host_directory,a.host_files,a.output)
    print(json.dumps({'local_result':result,'production_action_executed':False}))
if __name__=='__main__': main()
