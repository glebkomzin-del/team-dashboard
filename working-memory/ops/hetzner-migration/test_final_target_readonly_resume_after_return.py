"""Offline contract tests only; synthetic data, no provider/SSH/DB/Docker calls.

Question: can unknown/drift/stale evidence permit revoke/start/publication?
Criterion: complete positive prerequisites, one SQL dispatch, truthful crash and
ambiguous-response history, immutable failure/recovery provenance.
Scope: pure guards and complete coordinator with injected clock/operations.
Decision: failures block Root execution; PASS is local evidence, no live approval.
"""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import final_target_readonly_resume_after_return as m

NOW=dt.datetime(2026,10,4,16,0,tzinfo=dt.timezone.utc)

def blob(x): return json.dumps(x).encode()
def sha(x): return hashlib.sha256(x).hexdigest()

class Clock:
    def __init__(self): self.now=NOW
    def __call__(self): return self.now


def fixture():
    tables=[{'table_name':name,'rows':0,'sha256':'0'*64} for name in m.r.TABLES]
    acl=[{'kind':'TABLE','object':'public.synthetic_'+str(i),'grantor':'postgres','privilege_type':'UPDATE','is_grantable':False} for i in range(82)]
    config=[{'space_id':'synthetic','enabled':True,'nullable':None}]
    auth=[{'id':'synthetic','email_sha256':'1'*64,'password_sha256':'2'*64}]
    cron=[{'jobid':i,'active':False,'command':'SELECT 1','schedule':'0 0 * * *','nullable':None} for i in (8,9)]
    vault={'id':'synthetic','name':None,'description':None,'nonce_hex':'00','created_at':NOW.isoformat(),'updated_at':NOW.isoformat(),'decrypted_secret':'synthetic-only'}
    originals={k:'3'*64 for k in m.w.HOST_FILES};live={k:'4'*64 for k in m.w.HOST_FILES}
    run='/opt/dashboard-supabase-20261003/final-export-20261004T004000Z'
    bodies={'baseline':blob({'status':'FROZEN_SOURCE_BUSINESS_BASELINE','captured_after_freeze':True,'problem_id':m.PROBLEM,'run_dir':run,'query_sha256':m.r.QUERY_SHA,'tables':tables}),
            'query':b'SYNTHETIC QUERY','acl_original':blob(acl),'revoke_sql':('BEGIN;\n'+''.join('REVOKE UPDATE ON TABLE '+x['object']+' FROM service_role;\n' for x in acl)+'COMMIT;\n').encode(),
            'config':blob(config),'auth_original':blob({'original_user_hashes':auth}), 'cron_original':blob(cron),'cron_fingerprint':blob({'rows':2,'sha256':'5'*64}),
            'vault_original':blob([vault]),'runtime_original_failure':b'original failure bytes',
            'full_backup':blob({'state':'ok','selfhost':{'restore_verified':True},'canonical':{'verified':True},'restore_barrier':{'restore_ledger_persisted':True},'sha256':'6'*64,'archive':'archive'}),
            'mac_copy':blob({'status':{'sha256':'6'*64,'archive':'archive','state':'ok','files_verified':202},'same_archive':True,'all_files_verified':True,'whole_archive_sha256_rechecked':True}),
            'host_original_primary':blob({'original_image':m.w.BASE,'original_origin':m.w.SOURCE_ORIGIN,'original_flags':m.w.ORIGINAL,'original_file_sha256':originals}),
            'scope_key':blob({'id':'synthetic','userId':'synthetic','apiKey':'synthetic-only','scopes':['workflow:read']})}
    recovered={'status':'RecoveredRuntime','problem_id':m.PROBLEM,'run_dir':run,'original_runtime_status':'FAILED','original_runtime_attempts':1,'corrected_image':m.IMAGE,'closed_flags':m.w.CLOSED,'writers_opened':False,'original_error_sha256':sha(bodies['runtime_original_failure'])}
    bodies['recovered_runtime']=blob(recovered)
    prior={'status':'TARGET_READONLY_RUNTIME_ACTIVE','state_kind':'CURRENT_OPERATIONAL_STATE','original_runtime_attempt_status':'FAILED','recovery_status':'RecoveredRuntime','recovery_receipt_sha256':sha(bodies['recovered_runtime']),'target_image':m.IMAGE,'closed_flags':m.w.CLOSED,'base_image':m.w.BASE,'backend_origin':m.w.ORIGIN,'server_py_sha256':m.SERVER_SHA,'original_error_sha256':recovered['original_error_sha256'],'writers_opened':False,'health':{'status':'old'}}
    bodies['runtime_projection']=blob(prior)
    parent_gate='a'*64
    bodies['parent_attempt']=blob({'problem_id':m.PROBLEM,'phase':m.PARENT_PHASE,'package_id':m.PARENT_PACKAGE,'gate_sha256':parent_gate,'attempt':1})
    bodies['parent_host_attempt']=blob({'problem_id':m.PROBLEM,'phase':m.PARENT_PHASE,'package_id':m.PARENT_PACKAGE,'gate_sha256':parent_gate})
    bodies['parent_close']=blob({'problem_id':m.PROBLEM,'phase':m.PARENT_PHASE,'package_id':m.PARENT_PACKAGE,'gate_sha256':parent_gate,'run_dir':run,'status':'SOURCE_CLOSED_READBACK','revoke_dispatches':1,'observed_at':NOW.isoformat()})
    bodies['parent_failure']=blob({'problem_id':m.PROBLEM,'package_id':m.PARENT_PACKAGE,'status':'STOP_RETURN_TO_ROOT','cleanup_status':'STOPPED','source_revoke_dispatched':True,'source_rollback_executed':False,'observed_at':NOW.isoformat(),'counters':{'resume_attempts':1,'revoke_dispatches':1,'api_start_dispatches':1,'canonical_start_dispatches':0}})
    consumers={m.w.CANONICAL:{'image':m.IMAGE,'running':False,'flags':m.w.CLOSED,'origin':m.w.ORIGIN,'matching_env_keys':['MEMORY_JOURNAL_TOKEN']},
        'dashboard-memory-stage-read-20261003':{'image':'other-image','running':True,'flags':m.w.CLOSED,'origin':'http://api-gw:8000','matching_env_keys':['MEMORY_JOURNAL_TOKEN']},
        'dashboard-memory-rc1-shadow-20260919':{'image':'shadow-image','running':False,'flags':{**m.w.CLOSED,'MEMORY_ORIGINAL_DELETION_ENABLED':None},'origin':m.w.SOURCE_ORIGIN,'matching_env_keys':['MEMORY_JOURNAL_TOKEN']}}
    definition={'definition':'CREATE OR REPLACE FUNCTION public.wm_service_scope(p_token_hash text) RETURNS TABLE(space_id uuid,owner_id uuid) LANGUAGE sql STABLE AS $function$ select t.space_id,s.owner_id from memory_private.service_tokens t join public.wm_spaces s on s.id=t.space_id where t.token_hash=p_token_hash and t.enabled $function$','language':'sql','volatility':'s','security_definer':False}
    functions_contract={'status':'REACTIVE_FUNCTIONS_WITH_BOUND_CALLERS','scope':'KNOWN_DOCKER_TOKEN_CONSUMERS_AND_HELD_APP_CALLERS',
        'functions_image':'sha256:'+m.p.API_IMAGES['functions'].split('@sha256:')[1],
        'functions_command':['start','--user-worker-request-idle-timeout','150000','--main-service','/home/deno/functions/main'],'functions_entrypoint':['edge-runtime'],
        'function_files':{str(m.w.ROOT/'functions'/n):'1'*64 for n in ['main/index.ts','working-memory-journal/index.ts','working-memory-journal/handler.ts']},
        'scope_definition':definition,'scope_definition_sha256':sha(definition['definition'].encode()),'scope_rows':[{'space_id':'synthetic','owner_id':'synthetic'}],
        'original_space_id':'synthetic','original_owner_id':'synthetic','original_token_sha256':'a'*64,'known_token_consumers':consumers}
    bodies['functions_contract']=blob(functions_contract)
    refs={k:{'path':run+'/'+k+'.json','sha256':sha(v)} for k,v in bodies.items()}
    refs['acl_original']['path']=str(m.w.ROOT/'source/freeze-business-original-acl.json')
    refs['revoke_sql']['path']=str(m.w.ROOT/'source/freeze-business.sql')
    scripts={name:m.r.digest(Path(m.__file__).with_name(name)) for name in [Path(m.__file__).name,Path(__file__).name,'final_phase_common.py','final_prewrite_rollback_once.py','final_writer_open_once.py','final_target_partial_source_return_once.py','final_quiescence_once.py','final_target_runtime_once.py','n8n_dashboard_pause_once.py','prepare_business_freeze_acl.py']}
    gate={'problem_id':m.PROBLEM,'phase':m.PHASE,'package_id':m.PACKAGE,'decision':'CONTINUE_BOUNDED','operational_target_go':True,
          'run_dir':run,'issued_at':NOW.isoformat(),'expires_at':(NOW+dt.timedelta(seconds=600)).isoformat(),'proof_observed_at':NOW.isoformat(),
          'immutable_refs':refs,'functions_contract':functions_contract,'script_hashes':scripts,'host_script_refs':{n:{'path':run+'/'+n,'sha256':h} for n,h in scripts.items()},
          'original_file_sha256':originals,'live_file_sha256':live,'other_containers':{n:{'image':'other-image','started_at':'unchanged'} for n in m.STABLE_CONTAINERS},'local_refs':{}}
    source={'business':[{'value':tables}],'auth':[{'value':auth}],'state':[{'value':{'running':0,'unknown_model':0,'unknown_question':0,'cron':0,'queued_http':0,'cron_total':2,'config':[{**x,'enabled':False} for x in config]}}],
            'roles':[{'role':role,'writable_tables':0,'executable_writers':0} for role in ('anon','authenticated','service_role')],'acl':acl,'cron':[{'value':cron}]}
    source['roles'][-1].update(writable_tables=23,executable_writers=32)
    native={'target':{'business':tables,'auth':auth,'state':{**source['state'][0]['value'],'config':config},'roles':copy.deepcopy(source['roles']),'acl':acl,'cron':cron,
                     'vault':{'plaintext_sha256':sha(vault['decrypted_secret'].encode()),'metadata':{k:v for k,v in vault.items() if k!='decrypted_secret'}}},
            'observed_at':NOW.isoformat(),'cron_fingerprint':{'rows':2,'sha256':'5'*64},'canonical_image':m.IMAGE,'canonical_running':False,'canonical_user':'10001:10001','canonical_flags':m.w.CLOSED,'canonical_origin':m.w.ORIGIN,
            'live_files_sha256':live,'original_files_sha256':originals,'nginx_sha256':m.MAINTENANCE_SHA,'timer_sha256':m.p.TIMER_SHA,'backup_code_sha256':m.w.BACKUP_SHA,
            'timer':{'is-active':'inactive','is-enabled':'enabled','service':'inactive'},'backup_marker':{'enabled':True,'migration_run':Path(run).name},'other_containers':gate['other_containers'],
            'n8n_running':0,'outboxes':{n:0 for n in m.OUTBOXES},'markers':[],'known_external_target_writers':[],
            'reactive_functions':{k:v for k,v in functions_contract.items() if k in ['function_files','functions_image','functions_command','functions_entrypoint','scope_definition','scope_rows','original_token_sha256','known_token_consumers']},
            'workflows':{k:{'active':False,'versionId':v} for k,v in m.workflow_versions().items()},
            'scope':{'userId':'synthetic','md5':hashlib.md5(b'synthetic-only').hexdigest(),'scopes':['workflow:read','workflow:activate','workflow:deactivate']},
            'apis':{name:{'running':False,'image':'sha256:'+image.split('@sha256:')[1],'configured_image':image,'networks':list(m.p.API_NETWORKS[name]),'ports':{},'project':'dashboard-supabase-20261003','service':name} for name,image in m.p.API_IMAGES.items()},'health':None,'health_status':None}
    native['reactive_functions'].update(functions_mount={'Type':'bind','Source':str(m.w.ROOT/'functions'),'Destination':'/home/deno/functions','RW':False},functions_url='http://api-gw:8000',service_role_credential_present=True)
    source['acl']=[];source['roles'][-1].update(writable_tables=0,executable_writers=0)
    front={'production_env':{'envs':[]},**{a:{'id':m.r.OLD_DEPLOYMENT,'readyState':'READY'} for a in m.w.ALIASES}}
    return gate,bodies,{'source':source,'native':native,'frontend':front,'observed_at':NOW.isoformat()}


class FakeOps:
    def __init__(self,gate,bodies,observation,clock):
        self.gate,self.bodies,self.obs,self.clock=gate,bodies,copy.deepcopy(observation),clock
        self.calls=[];self.observations=0;self.delay_at=None;self.ambiguous=False;self.crash=False;self.corrupt=False;self.revoke_no_effect=False
        self.publish_lost=False;self.cleanup_kind='stopped';self.host_current=bodies['runtime_projection'];self.host_values={}
    def batch(self,refs):
        self.calls.append('batch')
        values={**self.bodies,**{'script:'+n:Path(m.__file__).with_name(n).read_bytes() for n in self.gate['script_hashes']}}
        if self.corrupt:values['config']+=b' '
        return values
    def observe(self,*args):
        self.observations+=1
        if self.delay_at==self.observations:self.clock.now+=dt.timedelta(seconds=301)
        value=copy.deepcopy(self.obs);value['observed_at']=self.clock.now.isoformat();value['native']['observed_at']=value['observed_at']
        return value
    def claim(self,gate):self.calls.append('claim')
    def revoke(self,sql,gate):
        self.calls.append(('revoke',sql))
        if not self.revoke_no_effect:
            self.obs['source']['acl']=[]
            self.obs['source']['roles'][-1].update(writable_tables=0,executable_writers=0)
        if self.ambiguous:raise TimeoutError('synthetic response unknown')
    def start(self,gate,canonical=False):
        self.calls.append('canonical' if canonical else 'apis')
        if canonical:
            self.obs['native']['reactive_functions']['known_token_consumers'][m.w.CANONICAL]['running']=True;self.obs['native']['canonical_running']=True;self.obs['native']['health']={'status':'ok','mode':'production'};self.obs['native']['health_status']=200
        else:
            for a in self.obs['native']['apis'].values():a['running']=True
    def save_host(self,name,value):
        self.calls.append(('host-save',name));self.host_values[name]=copy.deepcopy(value)
        if self.crash and name=='source-closed-readback.json':raise RuntimeError('synthetic crash after ACL close')
    def reconcile_stopped(self,gate,previous):
        self.calls.append('reconcile-stopped')
        if self.crash:raise RuntimeError('crash after parent closure before new start')
        stopped=m.current_projection(previous,'TARGET_READONLY_RUNTIME_STOPPED',self.clock.now.isoformat(),gate)
        starting=m.current_projection(previous,'TARGET_RUNTIME_UNKNOWN_REPLAN',self.clock.now.isoformat(),gate)
        self.host_current=blob(stopped)
        return {'stopped':stopped,'starting':starting,'intent':{},'actual_readback':self.fail_closed()}
    def cleanup_resume(self,gate,previous):
        self.calls.append('degrade')
        allowed=[previous]
        if self.host_current not in allowed and json.loads(self.host_current).get('status')=='FOREIGN':raise RuntimeError('foreign projection')
        self.host_current=blob(m.current_projection(previous,'TARGET_RUNTIME_UNKNOWN_REPLAN',self.clock.now.isoformat(),gate))
        try:actual=self.fail_closed()
        except Exception:actual=None
        status=m.cleanup_status(actual)
        if status=='STOPPED':self.host_current=blob(m.current_projection(previous,'TARGET_READONLY_RUNTIME_STOPPED',self.clock.now.isoformat(),gate))
        return {'status':json.loads(self.host_current)['status'],'cleanup_status':status,'sha256':sha(self.host_current)}
    def publish(self,gate,previous,projection):
        self.calls.append('publish');self.host_current=blob(projection)
        if self.publish_lost:raise TimeoutError('successful Host replace; response lost')
        return self.host_current
    def fail_closed(self):
        self.calls.append('fail-closed')
        if self.cleanup_kind=='failed':raise TimeoutError('cleanup response lost')
        if self.cleanup_kind=='unknown':return None
        expected={m.w.CANONICAL:m.IMAGE,**{'dashboard-supabase-20261003-'+n+'-1':'sha256:'+v.split('@sha256:')[1] for n,v in m.p.API_IMAGES.items()}}
        return {'containers':{n:{'image':image,'running':False} for n,image in expected.items()},'observed_at':self.clock.now.isoformat()}
    def degrade(self,gate,previous,published,intent,cleanup):
        self.calls.append('degrade')
        assert self.host_values['publication-intent.json']==intent
        pending={'observed_at':self.clock.now.isoformat(),'containers':{}}
        unknown=m.degraded_projection(gate,previous,published,intent,pending,self.host_current)
        self.host_current=blob(unknown)
        try:cleanup=self.fail_closed()
        except Exception:cleanup=None
        if not isinstance(cleanup,dict):cleanup=pending
        degraded=m.degraded_projection(gate,previous,published,intent,cleanup,published)
        self.host_current=blob(degraded)
        return {'status':degraded['status'],'cleanup_status':degraded['cleanup_status'],'sha256':sha(self.host_current)}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.clock=Clock()
        self.gate,self.bodies,self.obs=fixture()
        self.run=self.root/Path(self.gate['run_dir']).name;self.run.mkdir()
        review={'problem_id':m.PROBLEM,'scope':m.PHASE,'package_id':m.PACKAGE,'decision':'ACCEPT','operational_target_go':True,
                'script_hashes':self.gate['script_hashes'],'immutable_refs':self.gate['immutable_refs'],'reviewed_at':NOW.isoformat(),
                'provenance':{'model':'gpt-6-astra','effort':'high','sandbox':'read-only','session':'synthetic-offline'}}
        self.review=self.root/'review.json';self.review.write_bytes(blob(review));self.gate['review_ref']={'path':str(self.review),'sha256':sha(blob(review))}
        self.gate_path=self.root/'gate.json';self.gate_path.write_bytes(blob(self.gate))
        self.patches=[patch.object(m.c,'PRIVATE',self.root),patch.object(m,'ACL_SHA',sha(self.bodies['acl_original'])),patch.object(m.r,'QUERY_SHA',sha(self.bodies['query'])),patch.object(m.w,'HOST_PRIMARY_SHA',sha(self.bodies['host_original_primary']))]
        # Baseline query matches patched query contract.
        baseline=json.loads(self.bodies['baseline']);baseline['query_sha256']=sha(self.bodies['query']);self.bodies['baseline']=blob(baseline)
        self.gate['immutable_refs']['baseline']['sha256']=sha(self.bodies['baseline'])
        for p in self.patches:p.start()
        for key in ('mac_copy','runtime_projection','acl_original'):
            local=self.root/(key+'.json');local.write_bytes(self.bodies[key]);self.gate['local_refs'][key]={'path':str(local),'sha256':sha(self.bodies[key])}
        self.op=FakeOps(self.gate,self.bodies,self.obs,self.clock)
        self.write_gate()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def write_gate(self):
        rev=json.loads(self.review.read_bytes());rev['immutable_refs']=self.gate['immutable_refs'];self.review.write_bytes(blob(rev));self.gate['review_ref']['sha256']=sha(blob(rev));self.gate_path.write_bytes(blob(self.gate))
    def execute(self):return m.execute(self.run,self.gate_path,self.op,self.clock)
    def data(self):return m.validate_inputs(self.gate,self.bodies,self.clock())
    def validate(self,obs=None,closed=True,running=False,prior=None):
        m.validate_observation(obs or self.obs,self.gate,self.data(),self.clock(),closed=closed,running=running,prior_close=prior)
    def test_complete_positive_contract(self):self.validate()
    def test_complete_resume_one_dispatch_preserves_original_history(self):
        prior=copy.deepcopy(self.bodies)
        result=self.execute();self.assertEqual(result['status'],'TARGET_READONLY_RESUMED')
        self.assertEqual(result['counters'],{'resume_attempts':1,'revoke_dispatches':0,'api_start_dispatches':1,'canonical_start_dispatches':1})
        self.assertEqual(self.op.calls.count('batch'),1);self.assertEqual(self.bodies,prior)
        self.assertFalse(any(isinstance(c,tuple) and c[0]=='revoke' for c in self.op.calls))
        projection=json.loads((self.root/'current-evidence'/m.PACKAGE/m.PROJECTION).read_bytes())
        self.assertEqual(projection['recovery_status'],'RecoveredRuntime');self.assertEqual(projection['original_runtime_attempt_status'],'FAILED')
        self.assertEqual(projection['health'],{'status':'ok','mode':'production'});self.assertEqual(projection['current_observed_at'],NOW.isoformat())
    def test_source43_drift_despite_disabled_config_denies(self):
        self.obs['source']['business'][0]['value'][0]['rows']=1
        with self.assertRaises(Exception):self.validate()
    def test_target43_missing_denies(self):
        del self.obs['native']['target']['business']
        with self.assertRaises(Exception):self.validate()
    def test_auth_equality_missing_or_wrong_denies(self):
        for value in (None,[],[{'id':'other'}]):
            obs=copy.deepcopy(self.obs);obs['native']['target']['auth']=value
            with self.subTest(value=value),self.assertRaises(Exception):self.validate(obs)
    def test_counts_bool_float_unknown_nonzero_deny(self):
        for bad in (False,0.0,None,1,'0'):
            for section,key in (('state','running'),('roles','writable_tables')):
                obs=copy.deepcopy(self.obs)
                if section=='state':obs['source']['state'][0]['value'][key]=bad
                else:obs['source']['roles'][0][key]=bad
                with self.subTest(bad=bad,section=section),self.assertRaises(Exception):self.validate(obs)
    def test_unknown_source_rows_deny(self):
        for value in ([],None,[{'wrong':[]}],[{'value':[]},{'value':[]}]):
            obs=copy.deepcopy(self.obs);obs['source']['business']=value
            with self.subTest(value=value),self.assertRaises(Exception):self.validate(obs)
    def test_full_cron_definition_drift_denies(self):
        self.obs['native']['target']['cron'][0]['command']='SELECT altered'
        with self.assertRaises(Exception):self.validate()
    def test_target_public_rights_open_denies(self):
        self.obs['native']['target']['roles'][0]['writable_tables']=1
        with self.assertRaises(Exception):self.validate()
    def test_closed_source_without_provenance_initial_attempt_denies(self):
        self.gate['immutable_refs'].pop('parent_close');self.write_gate()
        with self.assertRaises(Exception):self.execute()
        self.assertFalse(any(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls))
    def test_closed_source_same_attempt_positive_readback_with_provenance(self):
        self.obs['source']['acl']=[];self.obs['source']['roles'][-1].update(writable_tables=0,executable_writers=0)
        prior=json.loads(self.bodies['parent_close'])
        self.validate(closed=True,prior=prior)
        prior['phase']='UNKNOWN'
        with self.assertRaises(Exception):self.validate(closed=True,prior=prior)
    def test_stale_before_sql_denies(self):
        self.op.delay_at=2
        with self.assertRaises(Exception):self.execute()
        self.assertFalse(any(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls))
    def test_stale_after_sql_before_start_denies(self):
        self.op.delay_at=2
        with self.assertRaises(Exception):self.execute()
        self.assertEqual(sum(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls),0)
        self.assertNotIn('apis',self.op.calls)
    def test_stale_between_api_and_canonical_start_denies(self):
        self.op.delay_at=3
        with self.assertRaises(Exception):self.execute()
        self.assertIn('apis',self.op.calls);self.assertNotIn('canonical',self.op.calls);self.assertIn('fail-closed',self.op.calls)
    def test_gate_expiry_and_future_proof_deny(self):
        for now in (NOW+dt.timedelta(seconds=600),NOW-dt.timedelta(seconds=1)):
            with self.subTest(now=now),self.assertRaises(Exception):m.gate_check(self.gate,now)
    def test_static_sha_change_denies(self):
        self.op.corrupt=True
        with self.assertRaises(Exception):self.execute()
        self.assertNotIn('claim',self.op.calls)
    def test_review_content_change_denies(self):
        self.review.write_bytes(b'{}')
        with self.assertRaises(Exception):self.execute()
        self.assertEqual(self.op.calls,[])
    def test_host_script_sha_change_denies(self):
        original=self.op.batch
        def corrupt(refs):
            result=original(refs);result['script:final_phase_common.py']=b'changed';return result
        self.op.batch=corrupt
        with self.assertRaises(Exception):self.execute()
        self.assertNotIn('claim',self.op.calls)
    def test_parent_closed_source_success_never_revoke(self):
        self.assertEqual(self.execute()['status'],'TARGET_READONLY_RESUMED')
        self.assertFalse(any(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls))
        receipt=json.loads((self.root/'current-evidence'/m.PACKAGE/m.RECEIPT).read_bytes())
        self.assertEqual(receipt['counters']['revoke_dispatches'],0);self.assertEqual(receipt['parent_counters']['revoke_dispatches'],1)
    def test_missing_parent_closure_denies_no_revoke_no_start(self):
        body=json.loads(self.bodies['parent_close']);body['status']='UNKNOWN';self.bodies['parent_close']=blob(body);self.gate['immutable_refs']['parent_close']['sha256']=sha(self.bodies['parent_close']);self.write_gate()
        with self.assertRaises(Exception):self.execute()
        self.assertNotIn('apis',self.op.calls);self.assertFalse(any(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls))
    def test_crash_after_parent_close_retains_new_attempt_no_revoke(self):
        self.op.crash=True
        with self.assertRaises(Exception):self.execute()
        marker=self.root/'current-evidence'/m.PACKAGE/m.ATTEMPT;before=marker.read_bytes()
        with self.assertRaises(Exception):self.execute()
        self.assertEqual(marker.read_bytes(),before);self.assertNotIn('apis',self.op.calls)
        self.assertFalse(any(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls))
    def test_unknown_health_does_not_publish_current(self):
        original=self.op.start
        def unhealthy(gate,canonical=False):
            original(gate,canonical)
            if canonical:self.op.obs['native']['health']=None
        self.op.start=unhealthy
        with self.assertRaises(Exception):self.execute()
        self.assertNotIn('publish',self.op.calls);self.assertIn('fail-closed',self.op.calls)
    def test_mutable_protection_drift_denies(self):
        for key,value in [('canonical_flags',{}),('nginx_sha256','foreign'),('n8n_running',False),('markers',['writer-open-attempt.marker']),('other_containers',{}),('scope',{}),('timer',{}),('live_files_sha256',{})]:
            obs=copy.deepcopy(self.obs);obs['native'][key]=value
            with self.subTest(key=key),self.assertRaises(Exception):self.validate(obs)
    def test_transport_batch_is_one_compilable_call(self):
        op=m.Operations(self.root,self.gate['run_dir']);calls=[]
        def capture(code,timeout=60):
            compile(code,'offline-host-batch','exec');calls.append(code)
            return blob({k:m.base64.b64encode(v).decode() for k,v in self.bodies.items()})
        op.remote_python=capture
        self.assertEqual(op.batch(self.gate['immutable_refs']),self.bodies)
        self.assertEqual(len(calls),1)
    def test_transport_start_only_existing_names_and_checks_host_clock(self):
        op=m.Operations(self.root,self.gate['run_dir']);calls=[]
        def capture(code,timeout=60):compile(code,'offline-host-start','exec');calls.append(code);return b''
        op.remote_python=capture
        op.previous=self.bodies['runtime_projection'];op.start(self.gate);op.start(self.gate,canonical=True)
        for code in calls:
            self.assertIn('host_start_resume(',code)
            host=m.inspect.getsource(m.host_start_resume);self.assertIn('gate_check(',host);self.assertIn('utc()',host);self.assertIn("'docker','start'",host)
            self.assertNotIn("'compose'",code);self.assertNotIn("'build'",code);self.assertNotIn("'restore'",code)
        self.assertIn(',True)',calls[1])
    def test_transport_publisher_compiles_and_preserves_before_atomic_replace(self):
        op=m.Operations(self.root,self.gate['run_dir']);calls=[]
        def capture(code,timeout=60):compile(code,'offline-host-publish','exec');calls.append(code);return b''
        op.remote_python=capture
        projection={'status':'synthetic-current','health':{'status':'ok'}}
        self.assertEqual(op.publish(self.gate,self.bodies['runtime_projection'],projection),blob(projection))
        code=calls[0];self.assertIn('host_publish_resume(',code)
        source=m.inspect.getsource(m.host_publish_resume)
        self.assertIn('projection_lock(gate)',source);self.assertIn('lifecycle_files(',source);self.assertIn('gate_check(',source)
    def test_complete_host_observer_code_compiles_without_execution(self):
        compile(m.inspect.getsource(m.host_observe),'offline-host-observer','exec')
    def test_missing_mac_positive_binding_denies(self):
        self.gate['local_refs'].pop('mac_copy');self.write_gate()
        with self.assertRaises(Exception):self.execute()
        self.assertNotIn('claim',self.op.calls)
    def test_full_backup_positive_restore_proof_required(self):
        full=json.loads(self.bodies['full_backup']);full['selfhost']['restore_verified']=None
        self.bodies['full_backup']=blob(full);self.gate['immutable_refs']['full_backup']['sha256']=sha(self.bodies['full_backup'])
        with self.assertRaises(Exception):self.data()
    def test_host_publish_success_response_lost_cleanup_actual_stopped(self):
        self.op.publish_lost=True
        with self.assertRaises(Exception):self.execute()
        current=json.loads(self.op.host_current)
        self.assertEqual(current['status'],'TARGET_READONLY_RUNTIME_STOPPED');self.assertIs(current['runtime_active'],False)
        self.assertIsNone(current['health']);self.assertEqual(current['original_runtime_attempt_status'],'FAILED')
        historical=json.loads((self.root/'current-evidence'/m.PACKAGE/m.PROJECTION).read_bytes())
        self.assertEqual(historical['status'],'TARGET_READONLY_RUNTIME_ACTIVE');self.assertEqual(historical['health']['status'],'ok')
        self.assertEqual(sum(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls),0)
    def test_local_publish_receipt_failure_after_host_publish_reconciles(self):
        original=m.r.durable
        def fail_receipt(directory,name,value):
            if name=='publish-receipt.json':raise OSError('synthetic disk failure after Host publication')
            return original(directory,name,value)
        with patch.object(m.r,'durable',side_effect=fail_receipt),self.assertRaises(Exception):self.execute()
        current=json.loads(self.op.host_current);self.assertEqual(current['status'],'TARGET_READONLY_RUNTIME_STOPPED')
        self.assertIn('degrade',self.op.calls)
        self.assertEqual(sum(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls),0)
    def test_lost_publish_failed_or_unknown_cleanup_never_active(self):
        for kind in ('failed','unknown'):
            with self.subTest(kind=kind):
                # Separate entbehrliche test attempt, never reset real markers.
                if (self.root/'current-evidence'/m.PACKAGE).exists():
                    import shutil;shutil.rmtree(self.root/'current-evidence'/m.PACKAGE)
                self.op=FakeOps(self.gate,self.bodies,self.obs,self.clock);self.op.publish_lost=True;self.op.cleanup_kind=kind
                with self.assertRaises(Exception):self.execute()
                current=json.loads(self.op.host_current);self.assertEqual(current['status'],'TARGET_RUNTIME_UNKNOWN_REPLAN')
                self.assertIsNone(current['runtime_active']);self.assertIsNone(current['health'])
                self.assertEqual(sum(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls),0)
    def test_foreign_projection_after_lost_publish_denied_and_retained(self):
        original=self.op.publish
        foreign=blob({'status':'FOREIGN'})
        def changed(gate,previous,projection):
            original(gate,previous,projection);self.op.host_current=foreign;raise TimeoutError('lost response plus foreign current writer')
        self.op.publish=changed
        with self.assertRaises(Exception):self.execute()
        self.assertEqual(self.op.host_current,foreign)
        failure=json.loads(next((self.root/'current-evidence'/m.PACKAGE).glob('failure-*')).read_bytes())
        self.assertEqual(failure['current_projection_status'],'UNKNOWN_REPLAN_UNRECONCILED')
    def test_cleanup_positive_readback_strict_images_all_five_false(self):
        actual=self.op.fail_closed();self.assertEqual(m.cleanup_status(actual),'STOPPED')
        for bad in (None,False,{}, {'containers':{},'observed_at':NOW.isoformat()}):self.assertEqual(m.cleanup_status(bad),'UNKNOWN')
        actual['containers'][m.w.CANONICAL]['running']=0;self.assertEqual(m.cleanup_status(actual),'UNKNOWN')
    def test_bound_previous_bytes_can_be_degraded_without_claiming_publish(self):
        self.op.publish_lost=True
        with self.assertRaises(Exception):self.execute()
        intent=self.op.host_values['publication-intent.json'];published=blob(self.op.host_values[m.PROJECTION])
        result=m.degraded_projection(self.gate,self.bodies['runtime_projection'],published,intent,self.op.fail_closed(),self.bodies['runtime_projection'])
        self.assertEqual(result['status'],'TARGET_READONLY_RUNTIME_STOPPED')
    def test_reconciliation_host_code_compiles_only(self):
        compile(m.inspect.getsource(m.host_cleanup_readback),'offline-cleanup-readback','exec')
        compile(m.inspect.getsource(m.host_degrade),'offline-host-degrade','exec')
    def test_cumulative_advancing_clock_success_and_limit_denial(self):
        original=self.op.observe
        def advances(*args):self.clock.now+=dt.timedelta(seconds=30);return original(*args)
        self.op.observe=advances
        self.assertEqual(self.execute()['status'],'TARGET_READONLY_RESUMED')
        self.assertGreater(self.clock.now,NOW)
    def test_original_recovered_history_must_remain_failed(self):
        data=json.loads(self.bodies['recovered_runtime']);data['original_runtime_status']='PASS';self.bodies['recovered_runtime']=blob(data);self.gate['immutable_refs']['recovered_runtime']['sha256']=sha(self.bodies['recovered_runtime'])
        with self.assertRaises(Exception):self.data()

class ReactiveRoleTests(unittest.TestCase):
    setUp=ContractTests.setUp
    tearDown=ContractTests.tearDown
    write_gate=ContractTests.write_gate
    execute=ContractTests.execute
    data=ContractTests.data
    validate=ContractTests.validate
    # Only new scoped conditions; inherited baseline cases run once in base.
    def test_f1_known_infrastructure_closed_callers_accepted(self):self.validate()
    def test_f1_open_canonical_despite_known_functions_image_denied(self):
        self.obs['native']['reactive_functions']['known_token_consumers'][m.w.CANONICAL]['flags']={**m.w.CLOSED,'MEMORY_READ_ONLY':'0'}
        with self.assertRaises(Exception):self.validate()
    def test_f1_open_stage_denied(self):
        self.obs['native']['reactive_functions']['known_token_consumers']['dashboard-memory-stage-read-20261003']['flags']={**m.w.CLOSED,'MEMORY_AUTOMATIC_ENABLED':'1'}
        with self.assertRaises(Exception):self.validate()
    def test_f1_stopped_historical_source_accepted_no_flag_mutation(self):
        self.validate();self.assertIsNone(self.obs['native']['reactive_functions']['known_token_consumers']['dashboard-memory-rc1-shadow-20260919']['flags']['MEMORY_ORIGINAL_DELETION_ENABLED'])
    def test_f1_started_historical_source_denied(self):
        self.obs['native']['reactive_functions']['known_token_consumers']['dashboard-memory-rc1-shadow-20260919']['running']=True
        with self.assertRaises(Exception):self.validate()
    def test_f1_foreign_handler_or_router_denied(self):
        for suffix in ('main/index.ts','working-memory-journal/handler.ts'):
            obs=copy.deepcopy(self.obs);obs['native']['reactive_functions']['function_files'][str(m.w.ROOT/'functions'/suffix)]='f'*64
            with self.subTest(suffix=suffix),self.assertRaises(Exception):self.validate(obs)
    def test_f1_scope_missing_wrong_owner_or_drift_denied(self):
        for field,value in [('scope_rows',[]),('scope_rows',[{'space_id':'synthetic','owner_id':'foreign'}]),('scope_definition',None),('original_token_sha256',None)]:
            obs=copy.deepcopy(self.obs);obs['native']['reactive_functions'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(Exception):self.validate(obs)
    def test_f1_unknown_or_missing_consumer_denied(self):
        for unknown in (True,False):
            obs=copy.deepcopy(self.obs);rows=obs['native']['reactive_functions']['known_token_consumers']
            if unknown:rows['foreign']={'running':False,'flags':m.w.CLOSED,'image':'known'}
            else:rows.pop(m.w.CANONICAL)
            with self.subTest(unknown=unknown),self.assertRaises(Exception):self.validate(obs)
    def test_f1_source_open_rights_even_configfalse_denied_without_revoke(self):
        self.op.obs['source']['roles'][-1].update(writable_tables=23,executable_writers=32)
        with self.assertRaises(Exception):self.execute()
        self.assertNotIn('apis',self.op.calls);self.assertFalse(any(isinstance(x,tuple) and x[0]=='revoke' for x in self.op.calls))
    def test_f1_operations_has_no_source_revoke_method(self):self.assertNotIn('revoke',m.Operations.__dict__)
    def test_f1_failure_before_publication_intent_reconciles_current_stopped(self):
        original=self.op.observe
        def failed(*args):
            if 'apis' in self.op.calls:raise TimeoutError('intermediate observer failed before publication intent')
            return original(*args)
        self.op.observe=failed
        with self.assertRaises(Exception):self.execute()
        self.assertEqual(json.loads(self.op.host_current)['status'],'TARGET_READONLY_RUNTIME_STOPPED')
        self.assertNotIn('canonical',self.op.calls);self.assertNotIn('publish',self.op.calls)
        self.assertFalse((self.root/'current-evidence'/m.PACKAGE/'publication-intent.json').exists())
    def test_f1_active_only_after_health_and_original_recovery_direct(self):
        self.execute();current=json.loads(self.op.host_current)
        self.assertEqual(current['status'],'TARGET_READONLY_RUNTIME_ACTIVE');self.assertEqual(current['health']['status'],'ok')
        self.assertEqual(current['recovery_receipt_sha256'],self.gate['immutable_refs']['recovered_runtime']['sha256'])
        self.assertEqual(current['resume_receipt_ref']['path'],self.gate['run_dir']+'/'+m.PACKAGE+'/'+m.RECEIPT)
    def test_f1_malformed_consumer_running_zero_denied(self):
        self.obs['native']['reactive_functions']['known_token_consumers'][m.w.CANONICAL]['running']=0
        with self.assertRaises(Exception):self.validate()

class HostFilesystemTests(unittest.TestCase):
    """Actual local filesystem/lock, injected Docker only; no external calls."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.directory=self.root/m.PACKAGE;self.directory.mkdir()
        self.previous=blob({'status':'OLD'})
        self.published=blob({'status':'TARGET_READONLY_RUNTIME_ACTIVE','state_kind':'CURRENT_OPERATIONAL_STATE',
                            'resume_receipt_sha256':'receipt','original_runtime_attempt_status':'FAILED',
                            'recovery_status':'RecoveredRuntime','health':{'status':'ok'}})
        self.target=self.root/'target-runtime-receipt.json';self.target.write_bytes(self.previous)
        self.gate={'run_dir':str(self.root),'immutable_refs':{'runtime_projection':{'sha256':sha(self.previous)}}}
        self.intent={'problem_id':m.PROBLEM,'phase':m.PHASE,'package_id':m.PACKAGE,'run_dir':str(self.root),
                     'previous_sha256':sha(self.previous),'published_sha256':sha(self.published),'resume_receipt_sha256':'receipt'}
        (self.directory/'publication-intent.json').write_bytes(blob(self.intent))
        (self.directory/m.PROJECTION).write_bytes(self.published)
        expected={m.w.CANONICAL:m.IMAGE,**{'dashboard-supabase-20261003-'+n+'-1':'sha256:'+v.split('@sha256:')[1] for n,v in m.p.API_IMAGES.items()}}
        self.stopped={'containers':{n:{'image':image,'running':False} for n,image in expected.items()},'observed_at':NOW.isoformat()}
        self.clock=patch.object(m,'utc',return_value=NOW);self.clock.start()
        self.guard=patch.object(m,'gate_check');self.guard.start()
    def tearDown(self):self.clock.stop();self.guard.stop();self.temp.cleanup()
    def current(self):return json.loads(self.target.read_bytes())
    def cleanup(self):return m.host_degrade(self.gate,self.previous,self.published,self.intent)
    def test_publisher_response_lost_then_cleanup_actual_file_stopped(self):
        m.host_publish(self.gate,self.previous,self.published)
        # Actual Host write completed; caller receives no success response.
        with patch.object(m,'host_cleanup_readback',return_value=self.stopped):self.cleanup()
        self.assertEqual(self.current()['status'],'TARGET_READONLY_RUNTIME_STOPPED')
        self.assertEqual((self.directory/m.PROJECTION).read_bytes(),self.published)
    def test_local_receipt_failure_then_actual_host_cleanup(self):
        m.host_publish(self.gate,self.previous,self.published)
        try:raise OSError('Mac receipt disk failure')
        except OSError:
            with patch.object(m,'host_cleanup_readback',return_value=self.stopped):self.cleanup()
        self.assertIs(self.current()['runtime_active'],False)
    def test_unknown_durable_and_read_back_before_stop(self):
        def stop():
            self.assertEqual(self.current()['status'],'TARGET_RUNTIME_UNKNOWN_REPLAN')
            return self.stopped
        with patch.object(m,'host_cleanup_readback',side_effect=stop):self.cleanup()
        self.assertEqual(self.current()['status'],'TARGET_READONLY_RUNTIME_STOPPED')
    def test_unknown_write_failure_denies_stop(self):
        with patch.object(m,'replace_current',side_effect=OSError('durability failed')),patch.object(m,'host_cleanup_readback') as stop:
            with self.assertRaises(OSError):self.cleanup()
            stop.assert_not_called()
        self.assertEqual(self.target.read_bytes(),self.previous)
    def test_successful_stop_final_replace_failure_leaves_unknown(self):
        original=m.os.replace;calls=[]
        def replace(*args):
            calls.append(args)
            if len(calls)==2:raise OSError('STOPPED write failed')
            return original(*args)
        with patch.object(m.os,'replace',side_effect=replace),patch.object(m,'host_cleanup_readback',return_value=self.stopped):
            with self.assertRaises(OSError):self.cleanup()
        self.assertEqual(self.current()['status'],'TARGET_RUNTIME_UNKNOWN_REPLAN')
        self.assertIsNone(self.current()['runtime_active'])
    def test_stop_transport_failure_or_unknown_readback_leaves_unknown(self):
        for result in (TimeoutError('stop response lost'),{'containers':{},'observed_at':NOW.isoformat()}):
            self.target.write_bytes(self.previous)
            with patch.object(m,'host_cleanup_readback',side_effect=result if isinstance(result,Exception) else None,return_value=result):self.cleanup()
            self.assertEqual(self.current()['status'],'TARGET_RUNTIME_UNKNOWN_REPLAN')
    def test_completed_cleanup_response_lost_actual_file_remains_stopped(self):
        with patch.object(m,'host_cleanup_readback',return_value=self.stopped):
            try:
                self.cleanup()
                raise TimeoutError('completed Host response lost')
            except TimeoutError:pass
        self.assertEqual(self.current()['status'],'TARGET_READONLY_RUNTIME_STOPPED')

    def test_foreign_bytes_deny_no_stop_no_overwrite(self):
        self.target.write_bytes(b'{"status":"FOREIGN"}')
        with patch.object(m,'host_cleanup_readback') as stop:
            with self.assertRaises(Exception):self.cleanup()
            stop.assert_not_called()
        self.assertEqual(self.target.read_bytes(),b'{"status":"FOREIGN"}')
    def test_delayed_publisher_cannot_publish_after_cleanup(self):
        import threading
        started=threading.Event();finished=threading.Event();errors=[]
        def publisher():
            started.set()
            try:m.host_publish(self.gate,self.previous,self.published)
            except Exception as error:errors.append(error)
            finally:finished.set()
        with m.projection_lock(self.gate):
            worker=threading.Thread(target=publisher);worker.start();self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(.05))
            # Simulate durable cleanup publication while the delayed publisher waits.
            unknown=m.degraded_projection(self.gate,self.previous,self.published,self.intent,{'containers':{},'observed_at':NOW.isoformat()},self.previous)
            m.replace_current(self.target,self.previous,blob(unknown))
        worker.join(2);self.assertFalse(worker.is_alive());self.assertEqual(len(errors),1)
        self.assertEqual(self.current()['status'],'TARGET_RUNTIME_UNKNOWN_REPLAN')
    def test_cleanup_waits_for_inflight_publisher_until_end(self):
        import threading
        entered=threading.Event();release=threading.Event();completed=threading.Event();errors=[]
        original=m.replace_current
        def slow(*args):
            result=original(*args)
            if args[2]==self.published:entered.set();release.wait(2)
            return result
        def publish():
            try:m.host_publish(self.gate,self.previous,self.published)
            except Exception as e:errors.append(e)
        def cleanup():
            try:self.cleanup()
            except Exception as e:errors.append(e)
            finally:completed.set()
        with patch.object(m,'replace_current',side_effect=slow),patch.object(m,'host_cleanup_readback',return_value=self.stopped):
            publisher=threading.Thread(target=publish);publisher.start();self.assertTrue(entered.wait(1))
            cleaner=threading.Thread(target=cleanup);cleaner.start();self.assertFalse(completed.wait(.05));release.set()
            publisher.join(2);cleaner.join(2)
        self.assertEqual(errors,[]);self.assertEqual(self.current()['status'],'TARGET_READONLY_RUNTIME_STOPPED')

class ParentLifecycleFilesystemTests(unittest.TestCase):
    tearDown=HostFilesystemTests.tearDown
    current=HostFilesystemTests.current
    def setUp(self):
        HostFilesystemTests.setUp(self)
        (self.directory/'publication-intent.json').unlink()
        (self.directory/m.PROJECTION).unlink()
        self.gate['immutable_refs']['recovered_runtime']={'sha256':'recovery'}
        prior={'status':'TARGET_READONLY_RUNTIME_ACTIVE','state_kind':'CURRENT_OPERATIONAL_STATE','original_runtime_attempt_status':'FAILED','recovery_receipt_sha256':'recovery','health':{'status':'old'}}
        self.previous=blob(prior);self.target.write_bytes(self.previous);self.gate['immutable_refs']['runtime_projection']['sha256']=sha(self.previous)
        parent=self.root/m.PARENT_PACKAGE;parent.mkdir();marker=parent/'attempt.json';marker.write_bytes(b'parent exact marker')
        self.gate['immutable_refs'].update({k:{'path':str(marker),'sha256':sha(marker.read_bytes())} for k in ('parent_attempt','parent_host_attempt','parent_close','parent_failure')})
    def prepare(self):
        with patch.object(m,'actual_pinned_state',return_value=self.stopped):return m.host_prepare_resume(self.gate,self.previous)
    def test_f1_prepare_actual_stopped_truthful_current_not_historical_active(self):
        self.prepare();current=self.current();self.assertEqual(current['status'],'TARGET_READONLY_RUNTIME_STOPPED')
        self.assertIsNone(current['health']);self.assertEqual(current['current_observed_at'],NOW.isoformat())
        self.assertEqual((self.directory/'previous-runtime-projection.json').read_bytes(),self.previous)
    def test_f1_missing_positive_stopped_readback_denies_reconciliation(self):
        with patch.object(m,'actual_pinned_state',return_value={'containers':{},'observed_at':NOW.isoformat()}),self.assertRaises(Exception):m.host_prepare_resume(self.gate,self.previous)
        self.assertEqual(self.target.read_bytes(),self.previous)
    def test_f1_prepublication_failure_after_api_start_cleanup_actual_file_stopped(self):
        self.prepare()
        with patch('subprocess.run') as start:m.host_start_resume(self.gate,self.previous);start.assert_called_once()
        self.assertEqual(self.current()['status'],'TARGET_RUNTIME_UNKNOWN_REPLAN')
        self.assertFalse((self.directory/'publication-intent.json').exists())
        with patch.object(m,'host_cleanup_readback',return_value=self.stopped):m.host_cleanup_resume(self.gate,self.previous)
        self.assertEqual(self.current()['status'],'TARGET_READONLY_RUNTIME_STOPPED')
    def test_f1_prepublication_stop_response_unknown_keeps_actual_unknown(self):
        self.prepare()
        with patch('subprocess.run'):m.host_start_resume(self.gate,self.previous)
        with patch.object(m,'host_cleanup_readback',side_effect=TimeoutError('lost stop response')):m.host_cleanup_resume(self.gate,self.previous)
        self.assertEqual(self.current()['status'],'TARGET_RUNTIME_UNKNOWN_REPLAN')
    def test_f1_prepublication_unknown_write_failure_dispatches_no_stop(self):
        self.prepare()
        with patch.object(m,'replace_current',side_effect=OSError('disk failure')),patch.object(m,'host_cleanup_readback') as stop:
            with self.assertRaises(OSError):m.host_cleanup_resume(self.gate,self.previous)
            stop.assert_not_called()
    def test_f1_foreign_current_denies_start_and_cleanup(self):
        self.prepare();self.target.write_bytes(b'{"status":"FOREIGN"}')
        with patch('subprocess.run') as start,patch.object(m,'host_cleanup_readback') as stop:
            with self.assertRaises(Exception):m.host_start_resume(self.gate,self.previous)
            with self.assertRaises(Exception):m.host_cleanup_resume(self.gate,self.previous)
            start.assert_not_called();stop.assert_not_called()
        self.assertEqual(self.target.read_bytes(),b'{"status":"FOREIGN"}')
    def test_f1_stop_done_final_write_failure_keeps_unknown(self):
        self.prepare();original=m.os.replace;calls=[]
        def replace(*args):
            calls.append(args)
            if len(calls)==2:raise OSError('final STOPPED replace failed')
            return original(*args)
        with patch.object(m.os,'replace',side_effect=replace),patch.object(m,'host_cleanup_readback',return_value=self.stopped),self.assertRaises(OSError):m.host_cleanup_resume(self.gate,self.previous)
        self.assertEqual(self.current()['status'],'TARGET_RUNTIME_UNKNOWN_REPLAN')

if __name__=='__main__':unittest.main()
