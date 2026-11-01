"""Controlled Mac coordinator: one reviewed resume, existing artifacts only.

Immutable host inputs are fetched in ONE batch. Fresh mutable observations are
collected at each boundary; old timestamps are never renewed. No work on import.
Root supplies the gate/review; this module does not authenticate reviewer identity
outside that trusted-controller contract. Original failed/recovered receipts stay
immutable. Only the explicitly mutable CURRENT_OPERATIONAL_STATE is published.
"""
import argparse
import ast
import base64
import concurrent.futures
import datetime as dt
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shlex
import uuid

import final_phase_common as c
import final_prewrite_rollback_once as r
import final_writer_open_once as w
import final_target_partial_source_return_once as p
from final_quiescence_once import acl_query, EFFECTIVE_PRIVILEGES_SQL
from final_target_runtime_once import SERVER_SHA

PROBLEM = w.PROBLEM
PHASE = 'TARGET_READONLY_RESUME_AFTER_SOURCE_CLOSE'
PARENT_PHASE = 'TARGET_READONLY_RESUME_AFTER_RETURN'
PARENT_PACKAGE = 'target-readonly-resume-replan-1'
PACKAGE = 'target-readonly-resume-replan-2'
IMAGE = 'sha256:7d5e64318a66c3bf0227d694a3d15569263dc96d08b4cd0ae6d8feaeab2a9bcf'
ACL_SHA = '59fc65746e3c97383ab5552f1f48816a7dae37bf0edd408eadc07018d99b9cb8'
MAINTENANCE_SHA = '6e56b539a6964f95d3deda9bffd347933de435d787858b973565775024669e5e'
REQUIRED = {'baseline','query','acl_original','revoke_sql','config','auth_original',
            'cron_original','cron_fingerprint','vault_original','recovered_runtime',
            'runtime_original_failure','full_backup','mac_copy','host_original_primary',
            'runtime_projection','scope_key','parent_attempt','parent_host_attempt',
            'parent_close','parent_failure','functions_contract'}
STABLE_CONTAINERS={'n8n','n8n_postgres','picnic-skill','dashboard-supabase-20261003-db-1','dashboard-memory-stage-read-20261003'}
OUTBOXES={'projections-rc1-20260919/response-outbox','question-outbox'}
ATTEMPT = 'attempt.json'
RECEIPT = 'resume-receipt.json'
PROJECTION = 'runtime-current.json'
STATE_SQL = """SELECT json_build_object('running',(SELECT count(*) FROM public.wm_jobs WHERE state IN ('running','prepared')),'unknown_model',(SELECT count(*) FROM public.wm_model_calls WHERE received_at IS NULL AND redaction_id IS NULL),'unknown_question',(SELECT count(*) FROM public.wm_question_calls WHERE response_json IS NULL AND redaction_id IS NULL),'cron',(SELECT count(*) FROM cron.job WHERE active),'cron_total',(SELECT count(*) FROM cron.job),'queued_http',(SELECT count(*) FROM net.http_request_queue),'config',(SELECT json_agg(c ORDER BY space_id) FROM public.wm_processing_config c)) AS value"""
AUTH_SQL = """SELECT coalesce(json_agg(json_build_object('id',id::text,'email_sha256',encode(extensions.digest(coalesce(email,''),'sha256'),'hex'),'password_sha256',encode(extensions.digest(coalesce(encrypted_password,''),'sha256'),'hex')) ORDER BY id),'[]'::json) AS value FROM auth.users"""
CRON_SQL = "SELECT coalesce(json_agg(to_jsonb(j) ORDER BY jobid),'[]'::json) AS value FROM cron.job j"
VAULT_SQL = "SELECT json_build_object('plaintext_sha256',(SELECT encode(extensions.digest(decrypted_secret,'sha256'),'hex') FROM vault.decrypted_secrets),'metadata',(SELECT row_to_json(s) FROM (SELECT id,name,description,created_at,updated_at,encode(nonce,'hex') AS nonce_hex FROM vault.secrets) s))"
require = w.require


def workflow_versions():
    tree=ast.parse(Path(__file__).with_name('n8n_dashboard_pause_once.py').read_text())
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSIONS' for t in node.targets))


def utc():
    return dt.datetime.now(dt.timezone.utc)


def private_bytes(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Unsafe input file')
    return path.read_bytes()


def exact_zero(value):
    return type(value) is int and value == 0


def fresh(value, now, seconds=300):
    require(0 <= (now-r.stamp(value)).total_seconds() <= seconds, 'Observation stale/unknown')


def gate_check(gate, now):
    require(gate.get('problem_id') == PROBLEM and gate.get('phase') == PHASE
            and gate.get('package_id') == PACKAGE and gate.get('decision') == 'CONTINUE_BOUNDED'
            and gate.get('operational_target_go') is True, 'No scoped operational gate')
    require(re.fullmatch(r'/opt/dashboard-supabase-20261003/final-export-\d{8}T\d{6}Z', gate['run_dir']), 'Wrong run')
    issued, expires = r.stamp(gate['issued_at']), r.stamp(gate['expires_at'])
    require(issued <= now < expires and 0 < (expires-issued).total_seconds() <= 600, 'Gate stale')
    fresh(gate['proof_observed_at'], now)


def validate_inputs(gate, bodies, now):
    gate_check(gate, now)
    require(set(gate['immutable_refs']) == REQUIRED, 'Incomplete immutable contract')
    for key, ref in gate['immutable_refs'].items():
        require(Path(ref['path']).is_absolute() and re.fullmatch('[a-f0-9]{64}', ref['sha256'])
                and r.sha_bytes(bodies[key]) == ref['sha256'], 'Immutable primary SHA changed')
    data = {k:json.loads(b) for k,b in bodies.items() if k not in ('query','revoke_sql','runtime_original_failure')}
    require(r.sha_bytes(bodies['query']) == r.QUERY_SHA, 'Query differs')
    original = data['acl_original']
    require(r.sha_bytes(bodies['acl_original']) == ACL_SHA and len(original) == 82, 'Original ACL82 differs')
    require(gate['immutable_refs']['acl_original']['path'] == str(w.ROOT/'source/freeze-business-original-acl.json'), 'Wrong original ACL path')
    expected = 'BEGIN;\n'+''.join('REVOKE '+x['privilege_type']+' ON '+x['kind']+' '+x['object']+' FROM service_role;\n' for x in original)+'COMMIT;\n'
    require(bodies['revoke_sql'] == expected.encode(), 'Revoke is not exact existing business freeze')
    require(gate['immutable_refs']['revoke_sql']['path'] == str(w.ROOT/'source/freeze-business.sql'), 'Wrong revoke artifact')
    baseline = data['baseline']
    require(baseline['status'] == 'FROZEN_SOURCE_BUSINESS_BASELINE' and baseline['captured_after_freeze'] is True
            and baseline['problem_id'] == PROBLEM and baseline['run_dir'] == gate['run_dir']
            and baseline['query_sha256'] == r.QUERY_SHA, 'Original baseline absent')
    r.projection(baseline['tables'], r.TABLES)
    require(data['config'] and all(type(x['enabled']) is bool for x in data['config']), 'Original full config missing')
    require(data['auth_original']['original_user_hashes'], 'Original Auth missing')
    require(len(data['cron_original']) == 2 and all(x['active'] is False for x in data['cron_original']), 'Original Cron definitions absent')
    require(type(data['cron_fingerprint']['rows']) is int and data['cron_fingerprint']['rows'] == 2 and re.fullmatch('[a-f0-9]{64}', data['cron_fingerprint']['sha256']), 'Original Cron COPY missing')
    recovered = data['recovered_runtime']
    require(recovered['status'] == 'RecoveredRuntime' and recovered['problem_id'] == PROBLEM
            and recovered['run_dir'] == gate['run_dir'] and recovered['original_runtime_status'] == 'FAILED'
            and type(recovered['original_runtime_attempts']) is int and recovered['original_runtime_attempts'] == 1
            and recovered['corrected_image'] == IMAGE and recovered['closed_flags'] == w.CLOSED
            and recovered['writers_opened'] is False, 'Original recovery provenance absent')
    require(gate['immutable_refs']['runtime_original_failure']['sha256'] == recovered['original_error_sha256'], 'Original failure SHA differs')
    prior = data['runtime_projection']
    require(prior['state_kind'] == 'CURRENT_OPERATIONAL_STATE' and prior['original_runtime_attempt_status'] == 'FAILED'
            and prior['recovery_status'] == 'RecoveredRuntime'
            and prior['recovery_receipt_sha256'] == gate['immutable_refs']['recovered_runtime']['sha256']
            and prior['original_error_sha256']==recovered['original_error_sha256']
            and prior['base_image']==w.BASE and prior['backend_origin']==w.ORIGIN
            and prior['server_py_sha256']==SERVER_SHA and prior['target_image'] == IMAGE and prior['closed_flags'] == w.CLOSED
            and prior['writers_opened'] is False, 'Prior current projection differs')
    full, mac = data['full_backup'], data['mac_copy']
    require(full['state'] == 'ok' and full['selfhost']['restore_verified'] is True
            and full['canonical']['verified'] is True and full['restore_barrier']['restore_ledger_persisted'] is True
            and full['sha256'] == mac['status']['sha256'] and full['archive'] == mac['status']['archive']
            and mac['status']['state'] == 'ok' and mac['status']['files_verified'] == 202
            and type(mac['status']['files_verified']) is int and mac['same_archive'] is True
            and mac['all_files_verified'] is True and mac['whole_archive_sha256_rechecked'] is True, 'FULL/Mac provenance missing')
    host = data['host_original_primary']
    require(r.sha_bytes(bodies['host_original_primary']) == w.HOST_PRIMARY_SHA, 'Original host primary changed')
    require(host['original_image'] == w.BASE and host['original_origin'] == w.SOURCE_ORIGIN
            and host['original_flags'] == w.ORIGINAL
            and gate['original_file_sha256'] == host['original_file_sha256']
            and set(gate['live_file_sha256']) == set(w.HOST_FILES), 'Five original/Target files missing')
    require(STABLE_CONTAINERS <= set(gate['other_containers']) and all(set(x)=={'image','started_at'} and x['image'] and x['started_at'] for x in gate['other_containers'].values()), 'Other project/DB/stage baseline missing')
    require(gate['functions_contract']==data['functions_contract'],'Gate infrastructure proof differs')
    validate_parent(gate,data)
    validate_functions_contract(data['functions_contract'],data)
    require(data['functions_contract']['known_token_consumers'][w.CANONICAL]['image']==IMAGE
            and data['functions_contract']['known_token_consumers']['dashboard-memory-stage-read-20261003']['image']==gate['other_containers']['dashboard-memory-stage-read-20261003']['image'],'Caller image baseline differs')
    return data


def validate_parent(gate,data):
    attempt,host,close,failure=(data[k] for k in ('parent_attempt','parent_host_attempt','parent_close','parent_failure'))
    for row in (attempt,host,close):
        require(row['problem_id']==PROBLEM and row['phase']==PARENT_PHASE and row['package_id']==PARENT_PACKAGE,'Wrong parent identity')
    require(type(attempt['attempt']) is int and attempt['attempt']==1 and host['gate_sha256']==attempt['gate_sha256']==close['gate_sha256'],'Parent gate/attempt differs')
    require(close['run_dir']==gate['run_dir'] and close['status']=='SOURCE_CLOSED_READBACK'
            and type(close['revoke_dispatches']) is int and close['revoke_dispatches']==1,'Missing parent Source closure')
    require(failure['problem_id']==PROBLEM and failure['package_id']==PARENT_PACKAGE
            and failure['status']=='STOP_RETURN_TO_ROOT' and failure['cleanup_status']=='STOPPED'
            and failure['source_revoke_dispatched'] is True and failure['source_rollback_executed'] is False
            and failure['counters']=={'resume_attempts':1,'revoke_dispatches':1,'api_start_dispatches':1,'canonical_start_dispatches':0}
            and all(type(v) is int for v in failure['counters'].values())
            and r.stamp(close['observed_at'])<=r.stamp(failure['observed_at']),'Parent failure/cumulative history differs')


def validate_functions_contract(contract,data):
    require(contract['status']=='REACTIVE_FUNCTIONS_WITH_BOUND_CALLERS' and contract['scope']=='KNOWN_DOCKER_TOKEN_CONSUMERS_AND_HELD_APP_CALLERS','Missing bounded infrastructure scope')
    require(contract['functions_image']=='sha256:'+p.API_IMAGES['functions'].split('@sha256:')[1]
            and contract['functions_command']==['start','--user-worker-request-idle-timeout','150000','--main-service','/home/deno/functions/main']
            and contract['functions_entrypoint']==['edge-runtime'],'Functions entrypoint differs')
    files=contract['function_files']
    require(all(Path(k).is_absolute() and k.startswith(str(w.ROOT/'functions')+'/') and re.fullmatch('[a-f0-9]{64}',v) for k,v in files.items())
            and all(str(w.ROOT/'functions'/name) in files for name in ('main/index.ts','working-memory-journal/index.ts','working-memory-journal/handler.ts')),'Mounted functions manifest incomplete')
    scope=contract['scope_definition']
    require(scope['language']=='sql' and scope['volatility']=='s' and scope['security_definer'] is False
            and r.sha_bytes(scope['definition'].encode())==contract['scope_definition_sha256']
            and re.search(r'AS \$function\$\s*select\b',scope['definition'],re.I)
            and not re.search(r'\b(insert|update|delete|truncate|alter|create|drop|grant|revoke|execute|call)\b',scope['definition'].split('AS $function$',1)[1],re.I),'Scope auth is not bound read-only SQL')
    require(contract['scope_rows']==[{'space_id':contract['original_space_id'],'owner_id':contract['original_owner_id']}]
            and contract['original_owner_id'] in [x['id'] for x in data['auth_original']['original_user_hashes']]
            and re.fullmatch('[a-f0-9]{64}',contract['original_token_sha256']),'Original scoped identity absent')
    consumers=contract['known_token_consumers']
    require(set(consumers)=={w.CANONICAL,'dashboard-memory-stage-read-20261003','dashboard-memory-rc1-shadow-20260919'},'Known consumer coverage differs')
    for name in (w.CANONICAL,'dashboard-memory-stage-read-20261003'):
        row=consumers[name]
        require(row['flags']==w.CLOSED and row['matching_env_keys']==['MEMORY_JOURNAL_TOKEN']
                and row['origin']==(w.ORIGIN if name==w.CANONICAL else 'http://api-gw:8000'),'Target caller not closed')
    shadow=consumers['dashboard-memory-rc1-shadow-20260919']
    require(shadow['running'] is False and shadow['origin']==w.SOURCE_ORIGIN and shadow['matching_env_keys']==['MEMORY_JOURNAL_TOKEN'],'Historical Source consumer not stopped')


def validate_reactive_functions(actual,contract,canonical_running):
    require(actual['function_files']==contract['function_files'] and actual['functions_image']==contract['functions_image']
            and actual['functions_command']==contract['functions_command'] and actual['functions_entrypoint']==contract['functions_entrypoint']
            and actual['functions_mount']=={'Type':'bind','Source':str(w.ROOT/'functions'),'Destination':'/home/deno/functions','RW':False}
            and actual['functions_url']=='http://api-gw:8000' and actual['service_role_credential_present'] is True,'Reactive Functions identity/code/auth differs')
    require(actual['scope_definition']==contract['scope_definition'] and actual['scope_rows']==contract['scope_rows']
            and actual['original_token_sha256']==contract['original_token_sha256'],'Missing/drifted scoped token evidence')
    expected={k:dict(v) for k,v in contract['known_token_consumers'].items()}
    expected[w.CANONICAL]['running']=canonical_running
    require(actual['known_token_consumers']==expected
            and all(type(row['running']) is bool for row in actual['known_token_consumers'].values()),'Known caller inventory open/missing/foreign')


def roles(rows, closed):
    expected = [{'role':role,'writable_tables':0,'executable_writers':0} for role in ('anon','authenticated','service_role')]
    if not closed:
        expected[-1].update(writable_tables=23, executable_writers=32)
    require(rows == expected and all(type(row[k]) is int for row in rows for k in ('writable_tables','executable_writers')), 'Effective role rights differ')


def validate_observation(obs, gate, data, now, *, closed, running, prior_close=None, api_running=None):
    fresh(obs['observed_at'], now)
    source, native, front = obs['source'], obs['native'], obs['frontend']
    fresh(native['observed_at'], now)
    target = native['target']
    def value(rows):
        require(type(rows) is list and len(rows) == 1 and set(rows[0]) == {'value'}, 'Unknown Source SQL response')
        return rows[0]['value']
    require(r.projection(value(source['business']), r.TABLES) == r.projection(target['business'], r.TABLES)
            == r.projection(data['baseline']['tables'], r.TABLES), 'Source/Target43 drift')
    require(value(source['auth']) == target['auth'] == data['auth_original']['original_user_hashes'], 'Source/Target/Auth identity differs')
    original_config = data['config']
    for state in (value(source['state']), target['state']):
        require(all(exact_zero(state[k]) for k in ('running','unknown_model','unknown_question','cron','queued_http'))
                and type(state['cron_total']) is int and state['cron_total'] == 2, 'Outstanding/unknown work')
    require(value(source['state'])['config'] == [{**x,'enabled':False} for x in original_config]
            and target['state']['config'] == original_config, 'Full config differs')
    require(value(source['cron']) == target['cron'] == data['cron_original']
            and native['cron_fingerprint'] == data['cron_fingerprint'], 'Full original Cron differs')
    roles(source['roles'], closed)
    roles(target['roles'], False)
    require(source['acl'] == ([] if closed else data['acl_original']) and target['acl'] == data['acl_original'], 'Actual ACL differs')
    if closed:
        prior_close=prior_close or data['parent_close']
        require(prior_close==data['parent_close'],'Parent close primary differs')
        require(prior_close['problem_id'] == PROBLEM and prior_close['run_dir'] == gate['run_dir']
                and prior_close['phase'] == PARENT_PHASE and prior_close['package_id'] == PARENT_PACKAGE and prior_close['status'] == 'SOURCE_CLOSED_READBACK'
                and prior_close['revoke_dispatches'] == 1, 'Closed Source lacks own resume provenance')
    vault = data['vault_original'][0]
    require(target['vault']['plaintext_sha256'] == hashlib.sha256(vault['decrypted_secret'].encode()).hexdigest(), 'Vault plaintext differs')
    for key in ('id','name','description','nonce_hex'):
        require(target['vault']['metadata'][key] == vault[key], 'Vault metadata differs')
    for key in ('created_at','updated_at'):
        require(r.stamp(target['vault']['metadata'][key]) == r.stamp(vault[key]), 'Vault timestamp differs')
    require(native['canonical_image'] == IMAGE and native['canonical_running'] is running
            and native['canonical_user']=='10001:10001' and native['canonical_flags'] == w.CLOSED and native['canonical_origin'] == w.ORIGIN, 'Canonical identity/flags differ')
    require(native['live_files_sha256'] == gate['live_file_sha256'] and native['original_files_sha256'] == gate['original_file_sha256'], 'Host file drift')
    require(native['timer_sha256']==p.TIMER_SHA and native['backup_code_sha256']==w.BACKUP_SHA, 'Held backup identity differs')
    require(native['nginx_sha256'] == MAINTENANCE_SHA and native['timer'] == {'is-active':'inactive','is-enabled':'enabled','service':'inactive'}, 'Maintenance/timer changed')
    require(native['backup_marker'] == {'enabled':True,'migration_run':Path(gate['run_dir']).name}, 'Backup marker differs')
    require(native['other_containers'] == gate['other_containers'], 'Other project restarted/changed')
    require(exact_zero(native['n8n_running']) and set(native['outboxes']) == OUTBOXES and all(exact_zero(x) for x in native['outboxes'].values()), 'n8n/outbox not empty')
    require(not native['markers'] and native['known_external_target_writers'] == [], 'Owner/frontend/writer opened')
    require(set(native['workflows']) == set(w.VERSIONS), 'n8n workflow coverage differs')
    for name, workflow in native['workflows'].items():
        require(workflow['active'] is False and workflow.get('versionId') == workflow_versions()[name], 'n8n publication changed')
    key = data['scope_key']
    require(native['scope'] == {'userId':key['userId'],'md5':hashlib.md5(key['apiKey'].encode()).hexdigest(),
                             'scopes':key['scopes']+['workflow:activate','workflow:deactivate']}, 'Own two scopes changed')
    require(set(native['apis']) == set(p.API_IMAGES), 'Four APIs missing')
    for name, api in native['apis'].items():
        require(api['running'] is (running if api_running is None else api_running) and api['image'] == 'sha256:'+p.API_IMAGES[name].split('@sha256:')[1]
                and api['configured_image'] == p.API_IMAGES[name] and set(api['networks']) == p.API_NETWORKS[name]
                and api['project'] == 'dashboard-supabase-20261003' and api['service'] == name, 'Pinned API differs')
        require(api['ports'] == ({'8000/tcp':[{'HostIp':'127.0.0.1','HostPort':'8800'}]} if name == 'api-gw' and api['ports'] else {}), 'API public port differs')
    require(all(front[a]['id'] == r.OLD_DEPLOYMENT and front[a]['readyState'] == 'READY' for a in w.ALIASES)
            and not any(x['key'] in ('VITE_SUPABASE_URL','VITE_SUPABASE_ANON_KEY') for x in front['production_env']['envs']), 'Frontend changed')
    validate_reactive_functions(native['reactive_functions'],data['functions_contract'],running)
    if running:
        require(native['health_status'] == 200 and type(native['health_status']) is int
                and native['health']['status'] == 'ok', 'Actual health missing')


def host_observe(gate, queries, scope_id):
    """Remote read-only snapshot. One SSH envelope; no host artifact copying."""
    import subprocess, urllib.request, time
    def call(args, **kw):
        return subprocess.check_output(args, timeout=kw.pop('timeout',45), **kw)
    def sql(q, db=w.DB, user='supabase_admin', name='postgres'):
        return json.loads(call(['docker','exec','-i',db,'psql','-U',user,'-d',name,'-XqAt','-v','ON_ERROR_STOP=1'], input=q.encode()))
    def sha(path):
        path=Path(path); require(path.is_file() and not path.is_symlink(), 'Unsafe Host file'); return r.digest(path)
    target={k:sql('SELECT coalesce(json_agg(x),\'[]\'::json) FROM ('+q.rstrip(';')+') x' if k in ('acl','roles') else q) for k,q in queries.items()}
    target['vault']=sql(VAULT_SQL)
    copied=call(['docker','exec','-i',w.DB,'psql','-U','supabase_admin','-d','postgres','-XqAt','-v','ON_ERROR_STOP=1'],input=b'COPY cron.job TO STDOUT;')
    fingerprint={'rows':len(copied.splitlines()),'sha256':hashlib.sha256(b''.join(sorted(hashlib.sha256(x).digest() for x in copied.splitlines(keepends=True)))).hexdigest()}
    key=json.loads(Path('/opt/dashboard-supabase-20261003/n8n-pause-access-1/existing-api-key-private.json').read_bytes())['apiKey']
    workflows={}
    for name in w.VERSIONS:
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:5678/api/v1/workflows/'+name,headers={'X-N8N-API-KEY':key}),timeout=10) as response:
            workflows[name]=json.load(response)
    n8n_running=sql("SELECT count(*) FROM execution_entity WHERE \"workflowId\" IN ('nzyaKxs5Om9wuPEc','dashboardDriveMove','dashboardDriveWatch') AND status IN ('new','running','waiting');",'n8n_postgres','n8n','n8n')
    scope=sql("SELECT json_build_object('scopes',scopes,'userId',\"userId\",'md5',md5(\"apiKey\")) FROM user_api_keys WHERE id="+c.literal(scope_id),'n8n_postgres','n8n','n8n')
    canonical=json.loads(call(['docker','inspect',w.CANONICAL]))[0]
    env=dict(x.split('=',1) for x in canonical['Config']['Env'] if '=' in x)
    mount=next(m for m in canonical['Mounts'] if m['Destination']=='/app/.local')
    require(mount['Type']=='bind' and mount['Source']==str(w.LIVE/'.local/cache'), 'Actual outbox mount differs')
    require(env['MEMORY_CACHE_DIR']=='/app/.local/projections-rc1-20260919' and env['MEMORY_QA_OUTBOX']=='/app/.local/question-outbox', 'Outbox env differs')
    boxes={}
    for rel in ('projections-rc1-20260919/response-outbox','question-outbox'):
        path=Path(mount['Source'])/rel; require(path.is_dir() and not path.is_symlink(), 'Outbox missing'); boxes[rel]=len(list(path.rglob('*.json')))
    timer={k:subprocess.run(['systemctl',k,'dashboard-job-backup.timer'],capture_output=True,timeout=10).stdout.decode().strip() for k in ('is-active','is-enabled')}
    timer['service']=subprocess.run(['systemctl','is-active','dashboard-job-backup.service'],capture_output=True,timeout=10).stdout.decode().strip()
    apis={}
    for name in p.API_IMAGES:
        item=json.loads(call(['docker','inspect','dashboard-supabase-20261003-'+name+'-1']))[0]
        labels=item['Config']['Labels']
        apis[name]={'running':item['State']['Running'],'image':item['Image'],'configured_image':item['Config']['Image'],'networks':list(item['NetworkSettings']['Networks']),
                    'ports':{k:v for k,v in item['NetworkSettings']['Ports'].items() if v},'project':labels['com.docker.compose.project'],'service':labels['com.docker.compose.service']}
    other={}
    for name in gate['other_containers']:
        item=json.loads(call(['docker','inspect',name]))[0]
        require(item['State']['Running'] is True,'Other project stopped')
        other[name]={'image':item['Image'],'started_at':item['State']['StartedAt']}
    foreign=[]
    ids=call(['docker','ps','-q']).decode().split()
    for item in (json.loads(call(['docker','inspect',*ids])) if ids else []):
        e=dict(v.split('=',1) for v in item['Config'].get('Env',[]) if '=' in v)
        origin=e.get('SUPABASE_URL','').rstrip('/')
        if origin==w.SOURCE_ORIGIN: foreign.append(item['Name'])
        if origin in (w.ORIGIN,'http://api-gw:8000'):
            if item['Name']=='/dashboard-supabase-20261003-functions-1':
                require(origin=='http://api-gw:8000','Functions origin differs')
            else:
                require(item['Name'] in ('/'+w.CANONICAL,'/dashboard-memory-stage-read-20261003') and all(e.get(k)==v for k,v in w.CLOSED.items()), 'Known Target runtime writable/foreign')
    contract=gate['functions_contract']
    all_ids=call(['docker','ps','-aq']).decode().split()
    all_containers=json.loads(call(['docker','inspect',*all_ids]))
    original_env=dict(line.split('=',1) for line in (Path(gate['run_dir'])/'host-runtime-original/service.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
    token=original_env['MEMORY_JOURNAL_TOKEN'].strip().strip("'\"")
    token_sha=hashlib.sha256(token.encode()).hexdigest()
    consumers={}
    for item in all_containers:
        e=dict(v.split('=',1) for v in item['Config'].get('Env',[]) if '=' in v)
        matching=sorted(k for k,v in e.items() if v==token)
        if matching:
            consumers[item['Name'].lstrip('/')]={'image':item['Image'],'running':item['State']['Running'],
                'flags':{k:e.get(k) for k in w.CLOSED},'origin':e.get('SUPABASE_URL'),'matching_env_keys':matching}
    functions=next(x for x in all_containers if x['Name']=='/dashboard-supabase-20261003-functions-1')
    fenv=dict(v.split('=',1) for v in functions['Config'].get('Env',[]) if '=' in v)
    fm=next(x for x in functions['Mounts'] if x['Destination']=='/home/deno/functions')
    root=Path(fm['Source'])
    require(root==w.ROOT/'functions' and fm['Type']=='bind' and fm['RW'] is False,'Functions mount differs')
    files={str(x):r.digest(x) for x in sorted(root.rglob('*')) if x.is_file() and not x.is_symlink()}
    require(len(files)<100 and not any(x.is_symlink() for x in root.rglob('*')),'Functions tree unsafe')
    scope_definition=sql("SELECT json_build_object('definition',pg_get_functiondef(p.oid),'language',l.lanname,'volatility',p.provolatile,'security_definer',p.prosecdef) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='public' AND p.proname='wm_service_scope';")
    require(scope_definition==contract['scope_definition'] and token_sha==contract['original_token_sha256'],'Scope definition/token changed; no auth RPC')
    scope_rows=sql("SELECT coalesce(json_agg(t),'[]'::json) FROM public.wm_service_scope("+c.literal(token_sha)+") t;")
    reactive={'function_files':files,'functions_image':functions['Image'],'functions_command':functions['Config']['Cmd'],
              'functions_entrypoint':functions['Config']['Entrypoint'],'functions_url':fenv.get('SUPABASE_URL'),
              'service_role_credential_present':bool(fenv.get('SUPABASE_SERVICE_ROLE_KEY')),
              'functions_mount':{k:fm[k] for k in ('Type','Source','Destination','RW')},
              'scope_definition':scope_definition,'scope_rows':scope_rows,'original_token_sha256':token_sha,'known_token_consumers':consumers}
    markers=[x.name for x in Path(gate['run_dir']).iterdir() if any(k in x.name for k in ('writer','frontend','owner-magiclink')) and any(k in x.name for k in ('attempt','marker'))]
    health,status=None,None
    if canonical['State']['Running']:
        deadline=time.monotonic()+30
        while True:
            gate_check(gate,utc())
            try:
                with urllib.request.urlopen('http://127.0.0.1:8798/health',timeout=3) as response: health,status=json.load(response),response.status
                break
            except (urllib.error.URLError,TimeoutError):
                if time.monotonic()>=deadline:raise
                time.sleep(1)
    return {'target':target,'cron_fingerprint':fingerprint,'workflows':workflows,'scope':scope,'n8n_running':n8n_running,
            'canonical_running':canonical['State']['Running'],'canonical_image':canonical['Image'],'canonical_user':canonical['Config']['User'],'canonical_flags':{k:env.get(k) for k in w.CLOSED},'canonical_origin':env.get('SUPABASE_URL'),
            'outboxes':boxes,'timer':timer,'apis':apis,'other_containers':other,'markers':markers,'known_external_target_writers':foreign,
            'live_files_sha256':{n:sha(w.LIVE/('.local/service.env' if n=='service.env' else n)) for n in w.HOST_FILES},
            'original_files_sha256':{n:sha(Path(gate['run_dir'])/'host-runtime-original'/n) for n in w.HOST_FILES},
            'timer_sha256':sha('/etc/systemd/system/dashboard-job-backup.timer'),'backup_code_sha256':sha(w.LIVE/'scheduled_backup.py'),'nginx_sha256':sha('/etc/nginx/sites-available/alexa'),'backup_marker':json.loads((w.LIVE/'.local/selfhost-backup.json').read_bytes()),
            'reactive_functions':reactive,'health':health,'health_status':status,'observed_at':utc().isoformat()}


def cleanup_status(cleanup):
    """STOPPED requires an actual strict readback for all five own containers."""
    expected={w.CANONICAL:IMAGE,**{'dashboard-supabase-20261003-'+n+'-1':'sha256:'+v.split('@sha256:')[1] for n,v in p.API_IMAGES.items()}}
    if not isinstance(cleanup,dict) or set(cleanup.get('containers',{}))!=set(expected):
        return 'UNKNOWN'
    for name,image in expected.items():
        row=cleanup['containers'][name]
        if row.get('image')!=image or row.get('running') is not False:
            return 'UNKNOWN'
    return 'STOPPED'


def degraded_projection(gate, previous, published, intent, cleanup, current):
    """Pure bound reconciliation; foreign current bytes are never overwritten."""
    require(intent['problem_id']==PROBLEM and intent['phase']==PHASE and intent['package_id']==PACKAGE
            and intent['run_dir']==gate['run_dir']
            and intent['previous_sha256']==r.sha_bytes(previous)==gate['immutable_refs']['runtime_projection']['sha256']
            and intent['published_sha256']==r.sha_bytes(published), 'Publication intent differs')
    require(current in (previous,published), 'Foreign current projection; deny degradation')
    status=cleanup_status(cleanup)
    projection=json.loads(published)
    require(projection['state_kind']=='CURRENT_OPERATIONAL_STATE'
            and projection['resume_receipt_sha256']==intent['resume_receipt_sha256'], 'Not own current publication')
    projection.update(status='TARGET_READONLY_RUNTIME_STOPPED' if status=='STOPPED' else 'TARGET_RUNTIME_UNKNOWN_REPLAN',
                      runtime_active=False if status=='STOPPED' else None, health=None,
                      current_observed_at=cleanup['observed_at'],observed_at=cleanup['observed_at'],
                      cleanup_status=status,requires_replan=True,
                      last_healthy_projection_ref={'path':gate['run_dir']+'/'+PACKAGE+'/'+PROJECTION,'sha256':r.sha_bytes(published)})
    return projection


def host_cleanup_readback():
    """Stop only pinned own containers, then inspect actual state, even on error."""
    import subprocess
    expected={w.CANONICAL:IMAGE,**{'dashboard-supabase-20261003-'+n+'-1':'sha256:'+v.split('@sha256:')[1] for n,v in p.API_IMAGES.items()}}
    names=list(expected)
    before=json.loads(subprocess.check_output(['docker','inspect',*names],timeout=20))
    require({x['Name'].lstrip('/'):x['Image'] for x in before}==expected,'Foreign cleanup container; no stop')
    result=subprocess.run(['docker','stop','--time','15',*names],capture_output=True,timeout=90)
    after=json.loads(subprocess.check_output(['docker','inspect',*names],timeout=20))
    return {'containers':{x['Name'].lstrip('/'):{'image':x['Image'],'running':x['State']['Running']} for x in after},
            'stop_returncode':result.returncode,'stop_stdout_b64':base64.b64encode(result.stdout).decode(),
            'stop_stderr_b64':base64.b64encode(result.stderr).decode(),'observed_at':utc().isoformat()}


def projection_lock(gate):
    """One shared Host lock covers publisher and complete cleanup lifetime."""
    import contextlib
    import fcntl
    @contextlib.contextmanager
    def locked():
        path=Path(gate['run_dir'])/PACKAGE/'current-projection.lock'
        fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)
    return locked()


def replace_current(target, expected, replacement):
    """Durable atomic replacement plus exact actual byte readback."""
    import tempfile
    require(private_bytes(target)==expected,'Current projection changed')
    fd,temp=tempfile.mkstemp(dir=target.parent);os.fchmod(fd,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(replacement);stream.flush();os.fsync(stream.fileno())
        require(private_bytes(target)==expected,'Current projection changed during replacement')
        os.replace(temp,target)
        directory_fd=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
        require(private_bytes(target)==replacement,'Current projection readback differs')
    finally:
        if os.path.exists(temp):os.unlink(temp)


def host_publish(gate, previous, published):
    with projection_lock(gate):
        gate_check(gate,utc())
        directory=Path(gate['run_dir'])/PACKAGE
        intent=json.loads(private_bytes(directory/'publication-intent.json'))
        require(private_bytes(directory/PROJECTION)==published,'Historical own projection changed')
        require(intent['previous_sha256']==r.sha_bytes(previous) and intent['published_sha256']==r.sha_bytes(published),'Publication intent differs')
        degraded_projection(gate,previous,published,intent,{'containers':{},'observed_at':utc().isoformat()},previous)
        target=Path(gate['run_dir'])/'target-runtime-receipt.json'
        require(private_bytes(target)==previous,'Current projection changed before publication')
        with (directory/'previous-runtime-projection.json').open('xb') as stream:
            stream.write(previous);stream.flush();os.fsync(stream.fileno())
        replace_current(target,previous,published)
        return {'sha256':r.sha_bytes(published)}


def host_degrade(gate, previous, published, intent, cleanup=None):
    # The safety publication and stop happen in ONE Host invocation and lock.
    # No stop is dispatched unless UNKNOWN is durably positively read back.
    with projection_lock(gate):
        directory=Path(gate['run_dir'])/PACKAGE
        require(json.loads(private_bytes(directory/'publication-intent.json'))==intent,'Host publication intent changed')
        require(private_bytes(directory/PROJECTION)==published,'Own historical healthy projection changed')
        target=Path(gate['run_dir'])/'target-runtime-receipt.json'
        current=private_bytes(target)
        pending={'observed_at':utc().isoformat(),'containers':{}}
        unknown=degraded_projection(gate,previous,published,intent,pending,current)
        suffix=uuid.uuid4().hex
        with (directory/('cleanup-current-before-'+suffix+'.json')).open('xb') as stream:
            stream.write(current);stream.flush();os.fsync(stream.fileno())
        r.durable(directory,'runtime-unknown-before-stop-'+suffix+'.json',unknown)
        unknown_bytes=json.dumps(unknown).encode()
        replace_current(target,current,unknown_bytes)
        # From here lost transport/final STOPPED write leaves UNKNOWN, never ACTIVE.
        try:
            cleanup=host_cleanup_readback()
        except BaseException as error:
            cleanup={'observed_at':utc().isoformat(),'containers':{},'error_type':type(error).__name__,'error':str(error)}
        r.durable(directory,'cleanup-readback-'+suffix+'.json',cleanup)
        status=cleanup_status(cleanup)
        if status=='STOPPED':
            stopped=degraded_projection(gate,previous,published,intent,cleanup,published)
            r.durable(directory,'runtime-stopped-'+suffix+'.json',stopped)
            replace_current(target,unknown_bytes,json.dumps(stopped).encode())
        actual=private_bytes(target)
        return {'status':json.loads(actual)['status'],'cleanup_status':status,
                'sha256':r.sha_bytes(actual),'observed_at':cleanup['observed_at']}


def actual_pinned_state():
    import subprocess
    expected={w.CANONICAL:IMAGE,**{'dashboard-supabase-20261003-'+n+'-1':'sha256:'+v.split('@sha256:')[1] for n,v in p.API_IMAGES.items()}}
    rows=json.loads(subprocess.check_output(['docker','inspect',*expected],timeout=20))
    require({x['Name'].lstrip('/'):x['Image'] for x in rows}==expected,'Foreign pinned runtime')
    return {'containers':{x['Name'].lstrip('/'):{'image':x['Image'],'running':x['State']['Running']} for x in rows},'observed_at':utc().isoformat()}


def current_projection(previous,status,observed_at,gate):
    projection=json.loads(previous)
    require(projection['state_kind']=='CURRENT_OPERATIONAL_STATE' and projection['original_runtime_attempt_status']=='FAILED'
            and projection['recovery_receipt_sha256']==gate['immutable_refs']['recovered_runtime']['sha256'],'Original provenance differs')
    projection.update(status=status,health=None,current_observed_at=observed_at,observed_at=observed_at,
                      runtime_active=False if status=='TARGET_READONLY_RUNTIME_STOPPED' else None,
                      cleanup_status='STOPPED' if status=='TARGET_READONLY_RUNTIME_STOPPED' else 'UNKNOWN',requires_replan=True,
                      parent_source_close_ref=gate['immutable_refs']['parent_close'],parent_failure_ref=gate['immutable_refs']['parent_failure'])
    return projection


def lifecycle_files(gate,previous):
    directory=Path(gate['run_dir'])/PACKAGE
    require(r.sha_bytes(previous)==gate['immutable_refs']['runtime_projection']['sha256'],'Prior projection changed')
    intent=json.loads(private_bytes(directory/'lifecycle-intent.json'))
    require(intent['problem_id']==PROBLEM and intent['phase']==PHASE and intent['package_id']==PACKAGE
            and intent['previous_sha256']==r.sha_bytes(previous) and intent['parent_refs']=={k:gate['immutable_refs'][k] for k in ('parent_attempt','parent_host_attempt','parent_close','parent_failure')},'Lifecycle intent differs')
    blobs={n:private_bytes(directory/n) for n in ('runtime-stopped-initial.json','runtime-starting.json')}
    require(intent['intermediate_sha256']=={n:r.sha_bytes(b) for n,b in blobs.items()},'Own lifecycle bytes changed')
    require(private_bytes(directory/'previous-runtime-projection.json')==previous,'Historical predecessor changed')
    return directory,intent,blobs


def host_prepare_resume(gate,previous):
    with projection_lock(gate):
        gate_check(gate,utc())
        directory=Path(gate['run_dir'])/PACKAGE
        parent=Path(gate['run_dir'])/PARENT_PACKAGE/'attempt.json'
        require(r.digest(parent)==gate['immutable_refs']['parent_host_attempt']['sha256'],'Actual parent marker changed')
        target=Path(gate['run_dir'])/'target-runtime-receipt.json'
        require(private_bytes(target)==previous,'Foreign current before stopped reconciliation')
        actual=actual_pinned_state();require(cleanup_status(actual)=='STOPPED','STOPPED lacks actual five-container proof')
        stopped=current_projection(previous,'TARGET_READONLY_RUNTIME_STOPPED',actual['observed_at'],gate)
        starting=current_projection(previous,'TARGET_RUNTIME_UNKNOWN_REPLAN',actual['observed_at'],gate)
        with (directory/'previous-runtime-projection.json').open('xb') as stream:
            stream.write(previous);stream.flush();os.fsync(stream.fileno())
        r.durable(directory,'stopped-initial-readback.json',actual)
        r.durable(directory,'runtime-stopped-initial.json',stopped);r.durable(directory,'runtime-starting.json',starting)
        blobs={n:private_bytes(directory/n) for n in ('runtime-stopped-initial.json','runtime-starting.json')}
        intent={'problem_id':PROBLEM,'phase':PHASE,'package_id':PACKAGE,'previous_sha256':r.sha_bytes(previous),
                'intermediate_sha256':{n:r.sha_bytes(b) for n,b in blobs.items()},
                'parent_refs':{k:gate['immutable_refs'][k] for k in ('parent_attempt','parent_host_attempt','parent_close','parent_failure')}}
        r.durable(directory,'lifecycle-intent.json',intent)
        replace_current(target,previous,blobs['runtime-stopped-initial.json'])
        return {'actual_readback':actual,'stopped':stopped,'starting':starting,'intent':intent}


def host_start_resume(gate,previous,canonical=False):
    import subprocess
    with projection_lock(gate):
        gate_check(gate,utc())
        directory,intent,blobs=lifecycle_files(gate,previous)
        target=Path(gate['run_dir'])/'target-runtime-receipt.json'
        if not canonical:
            replace_current(target,blobs['runtime-stopped-initial.json'],blobs['runtime-starting.json'])
        else:require(private_bytes(target)==blobs['runtime-starting.json'],'Starting projection drifted')
        gate_check(gate,utc())
        names=[w.CANONICAL] if canonical else ['dashboard-supabase-20261003-'+n+'-1' for n in p.API_IMAGES]
        subprocess.run(['docker','start',*names],check=True,capture_output=True,timeout=75)


def host_publish_resume(gate,previous,published):
    with projection_lock(gate):
        gate_check(gate,utc())
        directory,intent,blobs=lifecycle_files(gate,previous)
        publication=json.loads(private_bytes(directory/'publication-intent.json'))
        require(publication['previous_sha256']==r.sha_bytes(previous) and publication['published_sha256']==r.sha_bytes(published)
                and publication['prepublish_sha256']==r.sha_bytes(blobs['runtime-starting.json']),'Publish lifecycle differs')
        require(private_bytes(directory/PROJECTION)==published,'Historical healthy bytes changed')
        projection=json.loads(published)
        require(projection['status']=='TARGET_READONLY_RUNTIME_ACTIVE' and projection['health']['status']=='ok'
                and projection['resume_receipt_sha256']==r.digest(directory/RECEIPT)==publication['resume_receipt_sha256'],'Healthy resume receipt absent')
        replace_current(Path(gate['run_dir'])/'target-runtime-receipt.json',blobs['runtime-starting.json'],published)


def host_cleanup_resume(gate,previous):
    """Known own lifecycle only; UNKNOWN durable before stop under shared lock."""
    with projection_lock(gate):
        directory,intent,blobs=lifecycle_files(gate,previous)
        target=Path(gate['run_dir'])/'target-runtime-receipt.json';current=private_bytes(target)
        allowed=[previous,*blobs.values()]
        if (directory/PROJECTION).exists():
            healthy=private_bytes(directory/PROJECTION);projection=json.loads(healthy)
            require(projection['resume_receipt_sha256']==r.digest(directory/RECEIPT)
                    and projection['status']=='TARGET_READONLY_RUNTIME_ACTIVE' and projection['health']['status']=='ok','Foreign healthy receipt')
            allowed.append(healthy)
        require(current in allowed,'Foreign projection; no overwrite/no stop')
        suffix=uuid.uuid4().hex
        with (directory/('cleanup-current-before-'+suffix+'.json')).open('xb') as stream:
            stream.write(current);stream.flush();os.fsync(stream.fileno())
        unknown=current_projection(previous,'TARGET_RUNTIME_UNKNOWN_REPLAN',utc().isoformat(),gate)
        r.durable(directory,'cleanup-unknown-'+suffix+'.json',unknown)
        unknown_bytes=json.dumps(unknown).encode();replace_current(target,current,unknown_bytes)
        try:cleanup=host_cleanup_readback()
        except BaseException as error:cleanup={'containers':{},'observed_at':utc().isoformat(),'error_type':type(error).__name__,'error':str(error)}
        r.durable(directory,'cleanup-readback-'+suffix+'.json',cleanup)
        status=cleanup_status(cleanup)
        if status=='STOPPED':
            stopped=current_projection(previous,'TARGET_READONLY_RUNTIME_STOPPED',cleanup['observed_at'],gate)
            r.durable(directory,'cleanup-stopped-'+suffix+'.json',stopped)
            replace_current(target,unknown_bytes,json.dumps(stopped).encode())
        actual=private_bytes(target)
        return {'status':json.loads(actual)['status'],'cleanup_status':status,'sha256':r.sha_bytes(actual),'observed_at':cleanup['observed_at']}


class Operations(p.PartialOperations):
    def __init__(self, directory, run):
        super().__init__(directory)
        self.remote=run
        self.directory=directory
        c.ERROR_DIR=directory/'transport-errors'

    def batch(self, refs):
        # All immutable Host artifacts verified with ONE remote call. No full
        # reread in mutation guards; mutable facts are separately recollected.
        paths={k:v['path'] for k,v in refs.items()}
        code="import json,base64\nfrom pathlib import Path\nrefs="+repr(paths)+"\nresult={}\nfor k,p in refs.items():\n p=Path(p);assert p.is_file() and not p.is_symlink();result[k]=base64.b64encode(p.read_bytes()).decode()\nprint(json.dumps(result))"
        return {k:base64.b64decode(v,validate=True) for k,v in json.loads(self.remote_python(code,timeout=100)).items()}

    def observe(self, gate, bodies, data):
        queries={'business':bodies['query'].decode(),'auth':AUTH_SQL,'state':STATE_SQL,'roles':EFFECTIVE_PRIVILEGES_SQL,'acl':acl_query(),'cron':CRON_SQL}
        # Read-only independent Source queries and native snapshot run together.
        code='import json\nfrom final_target_readonly_resume_after_return import *\nprint(json.dumps(host_observe('+repr(gate)+','+repr(queries)+','+repr(data['scope_key']['id'])+')))'
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            source={k:pool.submit(self.source_sql,q) for k,q in queries.items()}
            native=pool.submit(self.remote_python,code,timeout=160)
            front={k:pool.submit(self.cli,args) for k,args in {'production_env':['env','ls','production','--format','json'],**{a:['inspect',a,'--format','json'] for a in sorted(w.ALIASES)}}.items()}
            observed={'source':{k:v.result() for k,v in source.items()},'native':json.loads(native.result()),'frontend':{k:json.loads(v.result()) for k,v in front.items()},'observed_at':utc().isoformat()}
        r.durable(self.directory,'observation-'+uuid.uuid4().hex+'.json',observed)
        return observed

    def claim(self, gate):
        code="import os,json\nfrom pathlib import Path\np=Path("+repr(gate['run_dir']+'/'+PACKAGE)+")\np.mkdir(mode=0o700)\nfd=os.open(p/'attempt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)\nwith os.fdopen(fd,'w') as f:json.dump("+repr({'problem_id':PROBLEM,'phase':PHASE,'package_id':PACKAGE,'gate_sha256':self.gate_sha})+",f);f.flush();os.fsync(f.fileno())"
        self.remote_python(code)

    def reconcile_stopped(self,gate,previous):
        code='import json\nfrom final_target_readonly_resume_after_return import host_prepare_resume\nprint(json.dumps(host_prepare_resume('+repr(gate)+','+repr(previous)+')))'
        return json.loads(self.remote_python(code,timeout=60))

    def start(self,gate,canonical=False):
        code='from final_target_readonly_resume_after_return import host_start_resume\nhost_start_resume('+repr(gate)+','+repr(self.previous)+','+repr(canonical)+')'
        self.remote_python(code,timeout=90)

    def save_host(self, name, value):
        self.remote_python('from pathlib import Path\nfrom final_prewrite_rollback_once import durable\ndurable(Path('+repr(self.remote+'/'+PACKAGE)+'),'+repr(name)+','+repr(value)+')')

    def publish(self,gate,previous,projection):
        blob=json.dumps(projection).encode()
        code='from final_target_readonly_resume_after_return import host_publish_resume\nhost_publish_resume('+repr(gate)+','+repr(previous)+','+repr(blob)+')'
        self.remote_python(code,timeout=60)
        return blob

    def cleanup_resume(self,gate,previous):
        code='import json\nfrom final_target_readonly_resume_after_return import host_cleanup_resume\nprint(json.dumps(host_cleanup_resume('+repr(gate)+','+repr(previous)+')))'
        return json.loads(self.remote_python(code,timeout=140))


def review_check(gate, now):
    local = gate['review_ref']
    require(r.sha_bytes(private_bytes(local['path'])) == local['sha256'], 'Review SHA changed')
    review=json.loads(private_bytes(local['path']))
    require(review['problem_id']==PROBLEM and review['scope']==PHASE and review['package_id']==PACKAGE
            and review['decision'] in ('ACCEPT','CONTINUE_BOUNDED') and review['operational_target_go'] is True
            and review['script_hashes']==gate['script_hashes'] and review['immutable_refs']==gate['immutable_refs']
            and review['provenance']['model']=='gpt-6-astra' and review['provenance']['effort']=='high'
            and review['provenance']['sandbox']=='read-only' and review['provenance']['session'], 'Hash-bound independent review absent')
    fresh(review['reviewed_at'],now,600)
    for name, sha in gate['script_hashes'].items():
        require(Path(name).name==name and r.digest(Path(__file__).with_name(name))==sha, 'Reviewed code changed')
    required={Path(__file__).name,'test_final_target_readonly_resume_after_return.py','final_phase_common.py','final_prewrite_rollback_once.py','final_writer_open_once.py','final_target_partial_source_return_once.py','final_quiescence_once.py','final_target_runtime_once.py','n8n_dashboard_pause_once.py','prepare_business_freeze_acl.py'}
    require(required <= set(gate['script_hashes']), 'Helper/dependencies/test unreviewed')


def execute(run, gate_path, operations=None, clock=utc):
    run,gate_path=Path(run),Path(gate_path)
    directory=c.PRIVATE/'current-evidence'/PACKAGE
    directory.mkdir(parents=True,mode=0o700,exist_ok=True)
    require(not directory.is_symlink() and directory.stat().st_mode & 0o077 == 0, 'Unsafe package directory')
    op=operations or Operations(directory,str(w.ROOT/run.name))
    started=False;revoke_dispatched=False;target_started=False
    lifecycle_attempted=False;publication_attempted=False;publication_blob=None;publication_intent=None
    counts={'resume_attempts':0,'revoke_dispatches':0,'api_start_dispatches':0,'canonical_start_dispatches':0}
    try:
        gate=json.loads(private_bytes(gate_path));op.gate_sha=r.digest(gate_path)
        require(run.parent==c.PRIVATE and run.name==Path(gate['run_dir']).name and not run.is_symlink(), 'Local/Host run differs')
        gate_check(gate,clock());review_check(gate,clock())
        require(not (directory/ATTEMPT).exists(), 'This package already attempted; no automatic retry')
        refs={**gate['immutable_refs'], **{'script:'+name:ref for name,ref in gate['host_script_refs'].items()}}
        fetched=op.batch(refs)
        bodies={k:fetched[k] for k in gate['immutable_refs']}
        data=validate_inputs(gate,bodies,clock())
        # Bind remote executable bytes in the same immutable batch.
        require(set(gate['host_script_refs'])==set(gate['script_hashes']), 'Host code refs incomplete')
        for name,ref in gate['host_script_refs'].items():
            require(ref['path']==gate['run_dir']+'/'+name and ref['sha256']==gate['script_hashes'][name], 'Host code binding differs')
        # Executable bytes came from the same single immutable batch.
        for name,sha in gate['script_hashes'].items():
            require(r.sha_bytes(fetched['script:'+name])==sha, 'Host executable SHA changed')
        require({'mac_copy','runtime_projection','acl_original'} <= set(gate['local_refs']), 'Mac provenance refs absent')
        for key in ('mac_copy','runtime_projection','acl_original'):
            ref=gate['local_refs'][key]
            require(ref['sha256']==gate['immutable_refs'][key]['sha256'] and private_bytes(ref['path'])==bodies[key], 'Mac/Host primary binding differs')
        def guard(closed=False,running=False,prior=None):
            gate_check(gate,clock());review_check(gate,clock())
            # Local original primaries are immutable, cheap reads only.
            for ref in gate.get('local_refs',{}).values():
                require(r.digest(ref['path'])==ref['sha256'], 'Local primary changed')
            obs=op.observe(gate,bodies,data)
            sampled=clock()  # Sample AFTER observation, never before slow SSH.
            gate_check(gate,sampled)
            validate_observation(obs,gate,data,sampled,closed=closed,running=running,prior_close=prior)
            return obs
        close=data['parent_close']
        obs=guard(closed=True,prior=close)
        r.durable(directory,ATTEMPT,{'problem_id':PROBLEM,'phase':PHASE,'package_id':PACKAGE,'gate_sha256':op.gate_sha,'attempt':1,
                                    'parent_attempt_ref':gate['immutable_refs']['parent_attempt'],'parent_failure_ref':gate['immutable_refs']['parent_failure']})
        started=True;counts['resume_attempts']=1;op.claim(gate)
        op.previous=bodies['runtime_projection']
        # First correct stale historical ACTIVE only from own exact predecessor
        # and actual five-container STOPPED proof, never from an old timestamp.
        lifecycle_attempted=True
        lifecycle=op.reconcile_stopped(gate,bodies['runtime_projection'])
        r.durable(directory,'stopped-reconciliation-receipt.json',lifecycle)
        obs=guard(closed=True,prior=close)
        gate_check(gate,clock());counts['api_start_dispatches']=1;target_started=True;op.start(gate)
        intermediate=op.observe(gate,bodies,data);sampled=clock();gate_check(gate,sampled)
        validate_observation(intermediate,gate,data,sampled,closed=True,running=False,api_running=True,prior_close=close)
        gate_check(gate,clock());counts['canonical_start_dispatches']=1;op.start(gate,canonical=True)
        obs=guard(closed=True,running=True,prior=close)
        receipt={'status':'TARGET_READONLY_RESUMED','problem_id':PROBLEM,'phase':PHASE,'package_id':PACKAGE,
                 'run_dir':gate['run_dir'],'observed_at':obs['observed_at'],'gate_sha256':op.gate_sha,
                 'helper_sha256':r.digest(__file__),'counters':counts,'parent_counters':data['parent_failure']['counters'],'parent_failure_ref':gate['immutable_refs']['parent_failure'],'source_closed':True,'writers_opened':False,
                 'maintenance_held':True,'n8n_paused':True,'timer_held':True,'original_runtime_status':'FAILED',
                 'original_recovery_ref':gate['immutable_refs']['recovered_runtime'],'health':obs['native']['health']}
        r.durable(directory,RECEIPT,receipt);op.save_host(RECEIPT,receipt)
        projection={**data['runtime_projection'],'status':'TARGET_READONLY_RUNTIME_ACTIVE','runtime_active':True,'cleanup_status':None,'requires_replan':False,'health':obs['native']['health'],'current_observed_at':obs['observed_at'],
                    'observed_at':obs['observed_at'],'resume_receipt_sha256':r.digest(directory/RECEIPT),
                    'resume_receipt_ref':{'path':gate['run_dir']+'/'+PACKAGE+'/'+RECEIPT,'sha256':r.digest(directory/RECEIPT)},
                    'maintenance_held':True}
        r.durable(directory,PROJECTION,projection);op.save_host(PROJECTION,projection)
        # Final gate boundary guards publishing a genuine current projection.
        gate_check(gate,clock())
        publication_blob=json.dumps(projection).encode()
        publication_intent={'problem_id':PROBLEM,'phase':PHASE,'package_id':PACKAGE,'run_dir':gate['run_dir'],
                            'previous_sha256':r.sha_bytes(bodies['runtime_projection']),
                            'published_sha256':r.sha_bytes(publication_blob),'resume_receipt_sha256':r.digest(directory/RECEIPT),
                            'gate_sha256':op.gate_sha,'prepublish_sha256':r.sha_bytes(json.dumps(lifecycle['starting']).encode())}
        r.durable(directory,'publication-intent.json',publication_intent)
        op.save_host('publication-intent.json',publication_intent)
        publication_attempted=True
        blob=op.publish(gate,bodies['runtime_projection'],projection)
        r.durable(directory,'publish-receipt.json',{'status':'HOST_CURRENT_PROJECTION_PUBLISHED','sha256':r.sha_bytes(blob),'observed_at':clock().isoformat()})
        return receipt
    except BaseException as error:
        failure={'status':'STOP_RETURN_TO_ROOT','problem_id':PROBLEM,'package_id':PACKAGE,'started':started,
                 'source_revoke_dispatched':revoke_dispatched,'counters':counts,'error_type':type(error).__name__,
                 'private_error':str(error),'observed_at':clock().isoformat(),'source_rollback_executed':False}
        if lifecycle_attempted:
            try:
                result=op.cleanup_resume(gate,bodies['runtime_projection'])
                failure['current_projection_reconciliation']=result;failure['cleanup_status']=result['cleanup_status']
            except BaseException as cleanup_error:
                failure['projection_reconciliation_error']=str(cleanup_error)
                failure['current_projection_status']='UNKNOWN_REPLAN_UNRECONCILED';failure['cleanup_status']='UNKNOWN'
        r.durable(directory,'failure-'+uuid.uuid4().hex+'.json',failure)
        raise w.PreconditionsError('STOP_RETURN_TO_ROOT; private package: '+str(directory)) from None


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',required=True);parser.add_argument('--gate-receipt',required=True)
    args=parser.parse_args(argv);os.umask(0o077)
    try: execute(args.run_dir,args.gate_receipt)
    except Exception as error: print(json.dumps({'status':'STOP_RETURN_TO_ROOT','error_type':type(error).__name__}));return 1
    print(json.dumps({'status':'TARGET_READONLY_RESUMED','writers_opened':False,'maintenance_held':True}));return 0

if __name__=='__main__':raise SystemExit(main())
