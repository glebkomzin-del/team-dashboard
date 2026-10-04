"""Synthetic offline cases. All fixtures and primary causes retained outside temp cleanup.

Run: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s
working-memory/ops/hetzner-migration -p test_final_frontend_control.py -v
No real CLI/HTTP/DB/SSH/browser/provider operations are used.
"""
import base64
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import final_owner_link_once as old_owner

spec=importlib.util.spec_from_file_location('frontend_control_test',Path(__file__).with_name('frontend-final-promote-control-once.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
spec=importlib.util.spec_from_file_location('owner_control_test',Path(__file__).with_name('final_owner_link_recovered_once.py'))
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
NOW=dt.datetime(2026,10,4,8,tzinfo=dt.timezone.utc)
RUN='/opt/dashboard-supabase-20261003/final-export-20261004T004000Z'
UID='01234567-89ab-cdef-0123-456789abcdef'
ACTUAL_ID='dpl_SyntheticNewProduction54'
ACTUAL_URL='synthetic-new.vercel.app'
RESULT_URL='https://vercel.com/'+c.SCOPE+'/'+c.PROJECT+'/'+ACTUAL_ID.removeprefix('dpl_')
PROMOTE_STDERR='Successfully created new deployment of '+c.PROJECT+' at '+RESULT_URL+'\n'
KEY='eyJhbGciOiJIUzI1NiJ9.'+base64.urlsafe_b64encode(b'{"role":"anon"}').decode().rstrip('=')+'.synthetic-only'

class Fixture:
    def __init__(self,root):
        self.root=root;self.gate={'problem_id':c.PROBLEM,'phase':c.PHASE,'action':'PROMOTE','run_dir':RUN,
            'decision':'CONTINUE_BOUNDED','operational_frontend_go':True,'issued_at':NOW.isoformat(),
            'expires_at':(NOW+dt.timedelta(seconds=600)).isoformat(),'script_hashes':{n:c.digest(c.OPS/n) for n in c.SCRIPTS},
            'receipt_hashes':{},'artifact_sha256':c.ARTIFACT_SHA,'preview':c.PREVIEW,
            'project':{'projectId':'prj_pWCB8TaGLQesLsT9me0jgT0FqcC5','orgId':'team_xbeBltwkXhOuVc8JUUR0CqoF'},
            'budget':{'env_add_each':1,'promotions':1,'owner_links':1,'automatic_retries':0}}
        primary=self.put('synthetic-primary',b'SYNTHETIC offline original observation')
        def obs(**kw):return {'problem_id':c.PROBLEM,'run_dir':RUN,'observed_at':NOW.isoformat(),'primary_receipts':[primary],**kw}
        tables=[{'table_name':n,'rows':0,'sha256':c.sha(n.encode())} for n in c.late.TABLES]
        error=self.put('runtime-error',b'SYNTHETIC Permission denied original FAILED')
        self.recovery={'status':'RecoveredRuntime','problem_id':c.PROBLEM,'run_dir':RUN,'original_runtime_status':'FAILED',
            'original_runtime_attempts':1,'original_helper_sha256':'e301b63688dfc56ac9339b0bd4152648c41ee66a54f0df6d318c2dc8aaa90a0c',
            'writers_opened':False,'original_error_sha256':error['sha256'],'corrected_image':'sha256:synthetic-nonroot',
            'closed_flags':old_owner.CLOSED_FLAGS,'health':{'status':'ok'}}
        recovery_ref=self.put('runtime_recovery',self.recovery)
        projection={'status':'TARGET_READONLY_RUNTIME_ACTIVE','state_kind':'CURRENT_OPERATIONAL_STATE','original_runtime_attempt_status':'FAILED',
            'recovery_status':'RecoveredRuntime','recovery_receipt_sha256':recovery_ref['sha256'],'original_error_sha256':error['sha256'],
            'target_image':self.recovery['corrected_image'],'backend_origin':old_owner.TARGET,'writers_opened':False,
            'closed_flags':old_owner.CLOSED_FLAGS,'readonly':True,'intake':False,'automatic':False,'qa':False,'original_deletion':False,
            'health':{'status':'ok'},'vault_plaintext_equal':True,'vault_metadata_preserved':True,'original_acl_restored':True,'original_config_enabled_restored':True}
        archive=self.put('full-archive',b'SYNTHETIC recovered Target FULL archive')
        mac=self.put('mac-archive',b'SYNTHETIC recovered Target FULL archive')
        src=self.put('source_archive',b'SYNTHETIC frozen Source104 archive');self.gate['source104_archive_sha256']=src['sha256']
        files=[{'path':n,'sha256':c.sha(n.encode())} for n in ('selfhost.sql','canonical.json','n8n.sql')]
        self.objects={
            'runtime_recovery':self.recovery,'runtime_projection':projection,
            'runtime_failure':{'status':'FAILED','original_runtime_attempts':1,'primary_response':error},
            'live':obs(running=True,image=self.recovery['corrected_image'],host_flags=old_owner.CLOSED_FLAGS,container_flags=old_owner.CLOSED_FLAGS,
                       health={'status':'ok'},backend_origin=old_owner.TARGET,allowed_users=[UID]),
            'baseline':{'status':'FROZEN_SOURCE_BUSINESS_BASELINE','captured_after_freeze':True,'query_sha256':c.late.QUERY_SHA,'tables':tables},
            'source':obs(tables=tables,query_sha256=c.late.QUERY_SHA,running=0,unknown_model=0,unknown_question=0,cron=0,outboxes_empty=True,
                         backend_running=False,roles=[{'role':r,'writable_tables':0,'executable_writers':0} for r in ('anon','authenticated','service_role')],
                         config=[{'key':'native-config','enabled':False}]),
            'target':obs(tables=tables,query_sha256=c.late.QUERY_SHA,running=0,unknown_model=0,unknown_question=0,cron=0,outboxes_empty=True),
            'vault_auth':obs(vault_plaintext_equal=True,vault_metadata_preserved=True,source_user_hashes=[c.sha(b'owner')],target_user_hashes=[c.sha(b'owner')],original_user_hashes=[c.sha(b'owner')]),
            'workflows':obs(versions=c.n8n.VERSIONS,active=[],running=0),
            'writers':obs(known_writers=[],writer_attempts=0,writer_marker_absent=True),
            'full_backup':obs(status='PASS',kind='FULL',origin='CURRENT_RECOVERED_TARGET',runtime_recovery_sha256=recovery_ref['sha256'],
                              isolated_restores={k:'PASS' for k in ('selfhost','canonical','n8n')},files=files,archive=archive),
            'mac_copy':obs(status='PASS',same_archive=True,all_files_verified=True,files=files,archive=mac),
            'frontend':obs(promotion_attempts=0,url_env_added=False,anon_env_added=False,
                           aliases={a:{'id':c.ROLLBACK,'readyState':'READY'} for a in c.ALIASES},production_env={'envs':[]},source104_archive={'files':104,'sha256':src['sha256']}),
            'return_contract':obs(mode='HEALTH_BOUND_LATE_SOURCE_RETURN_ONLY',helper_sha256=c.digest(c.OPS/'final_prewrite_rollback_once.py'),
                                  partial_return_after_frontend_forbidden=True,fresh_actual_gate_required=True,writer_opened=False)}
        self.refs={k:self.put(k,v) for k,v in self.objects.items()}
        self.refs.update(runtime_error=error,source_archive=src,anon_key=self.put('anon_key',KEY.encode()))
        self.proof=obs(refs=self.refs)
        self.review={'problem_id':c.PROBLEM,'scope':c.PHASE,'decision':'ACCEPT','conditional_technical_go':True,
            'script_hashes':self.gate['script_hashes'],'artifact_sha256':c.ARTIFACT_SHA,'reviewed_at':NOW.isoformat(),
            'provenance':{'model':'gpt-6-astra','effort':'high','sandbox':'read-only','session':'synthetic-review-only'}}
        self.path=root/'synthetic-gate.json';self.write()
    def put(self,name,value):
        path=self.root/(name+'.json');body=value if isinstance(value,bytes) else json.dumps(value).encode()
        path.write_bytes(body);path.chmod(0o600)
        ref={'path':str(path),'sha256':c.sha(body)};self.gate['receipt_hashes'][str(path)]=ref['sha256'];return ref
    def write(self):
        for k,v in self.objects.items():self.refs[k]=self.put(k,v)
        self.proof['refs']=self.refs;self.gate['proof']=self.put('proof',self.proof)
        self.gate['independent_review']=self.put('review',self.review)
        self.path.write_text(json.dumps(self.gate));self.path.chmod(0o600)
    def owner(self, actual_receipt=None):
        self.gate['action']='OWNER'
        receipt={'status':'PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED','promotion_attempts':1,'url_env_added':True,'anon_env_added':True,
                 'artifact_sha256':c.ARTIFACT_SHA,'runtime_recovery_sha256':self.refs['runtime_recovery']['sha256'],
                 'production_deployment_id':ACTUAL_ID,'promoted_url':ACTUAL_URL,'readiness_count':2,
                 'production':{'id':ACTUAL_ID,'url':ACTUAL_URL}}
        self.objects['frontend']['promotion_receipt']=self.put('canonical-promotion',receipt)
        self.objects['frontend']['aliases']={a:{'id':ACTUAL_ID,'readyState':'READY','target':'production','name':c.PROJECT,'contextName':c.SCOPE,'aliases':sorted(c.ALIASES)} for a in c.ALIASES}
        if actual_receipt is not None:
            receipt=json.loads(actual_receipt.read_text())
            ref={'path':str(actual_receipt),'sha256':c.digest(actual_receipt)}
            self.gate['receipt_hashes'][str(actual_receipt)]=ref['sha256']
            self.objects['frontend']['promotion_receipt']=ref
            if 'production' in receipt:
                poll=json.loads((self.root/'control'/('ready-poll-'+str(receipt['readiness_count'])+'.json')).read_text())
                self.objects['frontend']['aliases']=poll['aliases']
        self.write()

class FakeOps(c.Operations):
    def __init__(self,directory,receipt,case='success'):
        super().__init__(directory);self.receipt=receipt;self.case=case;self.calls=[];self.adds=0;self.promoted=False;self.polls=0
    def process(self,args,**kw):
        cli=args[1:];self.calls.append(cli)
        if cli[:2]==['env','add']:
            snapshot=json.loads(self.receipt.read_text());name=cli[2]
            assert snapshot[c.ENV_FLAGS[name]] is None and snapshot['intents'][name]['budget']==1
            assert (self.directory.parent/(name+'-INTENT.json')).exists()
            if self.adds==1:assert snapshot['url_env_added'] is True
            self.adds+=1
            if self.adds==2 and self.case in ('second-fail','foreign-present'):return subprocess.CompletedProcess(args,1,'raw failure stdout','raw failure stderr')
            if self.case=='timeout':raise subprocess.TimeoutExpired(args,240,output=b'partial-success-unknown',stderr=b'timeout-primary')
            return subprocess.CompletedProcess(args,0,'full env success\n','CLI success stderr\n')
        if cli[0]=='promote':
            assert json.loads(self.receipt.read_text())['promotion_attempts']==1
            assert (self.directory.parent/'promotion-INTENT.marker').exists()
            stderr=PROMOTE_STDERR
            if self.case=='missing-create':stderr='No creation result\n'
            if self.case=='ambiguous-create':stderr+=PROMOTE_STDERR
            if self.case=='old-preview':stderr=stderr.replace(ACTUAL_ID.removeprefix('dpl_'),c.PREVIEW.removeprefix('dpl_'))
            self.promoted=True;return subprocess.CompletedProcess(args,0,'original promotion stdout\n',stderr)
        if cli[0]=='inspect':
            if self.case=='bad-json':return subprocess.CompletedProcess(args,0,'ORIGINAL MALFORMED JSON','original inspect success stderr')
            deployment=ACTUAL_ID if self.promoted else c.ROLLBACK
            if self.promoted and self.case=='alias-fail' and cli[1]==sorted(c.ALIASES)[0]:deployment='dpl_foreign'
            if self.promoted and cli[1]==RESULT_URL:self.polls+=1
            pending=self.promoted and self.case in ('pending','expiry') and (self.polls==1 or self.case=='expiry')
            if pending and cli[1] in c.ALIASES:deployment=c.ROLLBACK
            body={'id':deployment,'readyState':'BUILDING' if pending and cli[1]==RESULT_URL else 'READY',
                  'target':'production','name':c.PROJECT,'contextName':c.SCOPE,'aliases':sorted(c.ALIASES),'url':ACTUAL_URL}
            return subprocess.CompletedProcess(args,0,json.dumps(body),'inspect stderr')
        if cli[:2]==['env','ls']:
            envs=[]
            if self.case=='foreign-present' and self.adds==2:envs=[{'key':'VITE_SUPABASE_ANON_KEY','id':'foreign-id','value':KEY,'createdBy':'foreign-actor'}]
            if self.case=='timeout' and self.adds>0:envs=[{'key':'VITE_SUPABASE_URL','value':c.original.artifact['target_url']}]
            return subprocess.CompletedProcess(args,0,json.dumps({'envs':envs}),'env list stderr')
        raise AssertionError('Unexpected synthetic CLI '+str(cli))
    def http(self,url):
        output=c.original.BUILD/'.vercel/output';route=url.split('.vercel.app',1)[1]
        if route in ('/','/memory-next?recovery=1'):
            body=(output/'static/index.html').read_bytes()
            if self.case=='byte-fail':body+=b'\n'
            headers=json.loads((output/'config.json').read_text())['routes'][0]['headers']
            if self.case=='header-fail':headers={**headers,'Content-Security-Policy':'foreign-csp'}
        else:
            body=(output/('static'+route)).read_bytes();headers={}
            if self.case=='asset-fail':body+=b'corrupt'
        c.save(self.directory/('http-'+str(len(list(self.directory.iterdir())))+'.json'),{'body_b64':c.enc(body),'status':200,'headers':headers})
        return body,200,headers

class FrontendControlTests(unittest.TestCase):
    def setUp(self):
        parent=Path(os.getenv('FRONTEND_CONTROL_EVIDENCE_DIR','/private/tmp'))
        self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=parent));self.root.chmod(0o700)
        self.f=Fixture(self.root);self.receipt=self.root/'frontend-final-promotion-evidence.json'
        self.key_patch=patch.dict(c.original.artifact,{'target_key_sha256':c.sha(KEY.encode())});self.key_patch.start();self.addCleanup(self.key_patch.stop)
        self.before={str(p):c.digest(p) for p in (c.OPS/'frontend-target-artifact.json',c.OPS/'frontend-final-promote-once.py',c.OPS/'final_owner_link_once.py')}
    def tearDown(self):
        self.assertEqual(self.before,{p:c.digest(p) for p in self.before})
        c.save(self.root/'case-result.json',{'case':self._testMethodName,'synthetic_only':True,'input_artifact_hashes_unchanged':True})
    def promote(self,case='success'):
        directory=self.root/'control';directory.mkdir(mode=0o700,exist_ok=True)
        ops=FakeOps(directory/'primaries',self.receipt,case)
        with patch.object(c.subprocess,'run',side_effect=ops.process):
            try:result=c.execute(self.f.path,directory,ops,NOW,self.receipt)
            except Exception:
                c.save(self.root/'call-summary.json',{'calls':ops.calls});raise
        c.save(self.root/'call-summary.json',{'calls':ops.calls});return result,ops
    def denial(self,mutation,action='PROMOTE'):
        mutation();self.f.write()
        with patch.object(c.subprocess,'run',side_effect=AssertionError('REAL COMMAND FORBIDDEN')):
            with self.assertRaises(Exception):c.load(self.f.path,action,NOW)
        self.assertFalse(self.receipt.exists())
    def test_success_exact_frozen_artifact_one_promotion(self):
        result,ops=self.promote();self.assertEqual(result['status'],'PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED')
        self.assertTrue(result['url_env_added']);self.assertTrue(result['anon_env_added']);self.assertEqual(result['promotion_attempts'],1)
        self.assertEqual(sum(x[0]=='promote' for x in ops.calls),1);self.assertEqual(ops.adds,2);self.assertEqual(len(result['checks']),12)
        with patch.object(c.subprocess,'run',side_effect=AssertionError('retry forbidden')):
            with self.assertRaises(Exception):c.execute(self.f.path,self.root/'control',ops,NOW,self.receipt)
        self.assertEqual(self.receipt.stat().st_mode&0o777,0o600)
    def test_first_success_second_failure_reconciles_unchanged_absence(self):
        with self.assertRaises(RuntimeError):self.promote('second-fail')
        r=json.loads(self.receipt.read_text());self.assertIs(r['url_env_added'],True);self.assertIs(r['anon_env_added'],False)
        self.assertEqual(r['promotion_attempts'],0);self.assertTrue(r['return_ownership_known']);self.assertTrue((self.root/'control/VITE_SUPABASE_ANON_KEY-INTENT.json').exists())
    def test_foreign_exact_value_after_absence_does_not_prove_ownership(self):
        with self.assertRaises(RuntimeError):self.promote('foreign-present')
        r=json.loads(self.receipt.read_text());self.assertIs(r['url_env_added'],True);self.assertIsNone(r['anon_env_added'])
        self.assertEqual(r['return_authorization'],'DENY_RETURN_UNKNOWN_OWNERSHIP');self.assertEqual(r['unknown_ownership'],['VITE_SUPABASE_ANON_KEY'])
    def test_timeout_denies_even_matching_current_value(self):
        with self.assertRaises(RuntimeError):self.promote('timeout')
        r=json.loads(self.receipt.read_text());self.assertIsNone(r['url_env_added']);self.assertIs(r['anon_env_added'],False);self.assertEqual(r['promotion_attempts'],0)
        records=[json.loads(p.read_text()) for p in (self.root/'control/primaries').glob('cli-*')]
        timeout=[x for x in records if x['timeout']];self.assertEqual(len(timeout),1)
        self.assertEqual(base64.b64decode(timeout[0]['stdout_b64']),b'partial-success-unknown')
    def test_successful_cli_raw_durable_before_bad_json(self):
        with self.assertRaises(RuntimeError):self.promote('bad-json')
        records=[json.loads(p.read_text()) for p in (self.root/'control/primaries').glob('cli-*')]
        self.assertTrue(any(x['exit_code']==0 and base64.b64decode(x['stdout_b64'])==b'ORIGINAL MALFORMED JSON' for x in records))
        r=json.loads(self.receipt.read_text());self.assertIs(r['url_env_added'],False);self.assertIs(r['anon_env_added'],False)
    def test_public_index_newline_is_failure(self):
        with self.assertRaises(RuntimeError):self.promote('byte-fail')
        self.assertEqual(json.loads(self.receipt.read_text())['promotion_attempts'],1)
    def test_public_header_csp_is_failure(self):
        with self.assertRaises(RuntimeError):self.promote('header-fail')
    def test_public_asset_hash_is_failure(self):
        with self.assertRaises(RuntimeError):self.promote('asset-fail')
    def test_alias_mismatch_retains_complete_success_output_and_known_ownership(self):
        with self.assertRaises(RuntimeError):self.promote('alias-fail')
        r=json.loads(self.receipt.read_text());self.assertIs(r['url_env_added'],True);self.assertIs(r['anon_env_added'],True)
        records=[json.loads(p.read_text()) for p in (self.root/'control/primaries').glob('cli-*')]
        self.assertTrue(any(base64.b64decode(x['stdout_b64'])==b'original promotion stdout\n' and x['exit_code']==0 for x in records))
    def test_missing_recovery_ref_denies(self):
        def missing():self.f.objects.pop('runtime_recovery');self.f.refs.pop('runtime_recovery')
        self.denial(missing)
    def test_historical_pass_fiction_denies(self):self.denial(lambda:self.f.objects['runtime_projection'].update(original_runtime_attempt_status='PASS'))
    def test_recovery_sha_mismatch_denies(self):self.denial(lambda:self.f.objects['runtime_projection'].update(recovery_receipt_sha256='0'*64))
    def test_open_native_container_flag_denies(self):self.denial(lambda:self.f.objects['live'].update(container_flags={**old_owner.CLOSED_FLAGS,'MEMORY_QA_ENABLED':'1'}))
    def test_source_role_writer_denies(self):self.denial(lambda:self.f.objects['source']['roles'][0].update(writable_tables=1))
    def test_running_n8n_denies(self):self.denial(lambda:self.f.objects['workflows'].update(running=1))
    def test_writer_marker_denies(self):self.denial(lambda:self.f.objects['writers'].update(writer_marker_absent=False))
    def test_source_era_backup_denies(self):self.denial(lambda:self.f.objects['full_backup'].update(origin='SOURCE_ERA'))
    def test_missing_actual_mac_inventory_denies(self):self.denial(lambda:self.f.objects['mac_copy'].update(files=[]))
    def test_missing_actual_n8n_restore_denies(self):self.denial(lambda:self.f.objects['full_backup']['isolated_restores'].update(n8n='PENDING'))
    def test_stale_actual_source_denies(self):self.denial(lambda:self.f.objects['source'].update(observed_at=(NOW-dt.timedelta(seconds=301)).isoformat()))
    def test_unbound_primary_denies(self):self.denial(lambda:self.f.gate['receipt_hashes'].pop(self.f.objects['source']['primary_receipts'][0]['path']))
    def test_old_astra_change_approach_denies(self):self.denial(lambda:self.f.review.update(decision='CHANGE_APPROACH',conditional_technical_go=False))
    def test_review_code_hash_mismatch_denies(self):
        self.f.review=copy.deepcopy(self.f.review)
        self.denial(lambda:self.f.review['script_hashes'].update({'final_owner_link_recovered_once.py':'0'*64}))
    def test_owner_rejects_old_pass_without_recovery(self):
        self.f.owner();self.denial(lambda:self.f.objects['runtime_projection'].update(recovery_status='PASS'),action='OWNER')
    def test_owner_real_original_flow_once_on_bound_current_projection(self):
        self.f.owner(getattr(self,'actual_promotion',None));gate,values,data,key=c.load(self.f.path,'OWNER',NOW)
        root=self.root/'host';root.mkdir(mode=0o700);run=root/'final-export-20261004T004000Z';run.mkdir(mode=0o700)
        (run/'target-runtime-receipt.json').write_bytes(values['runtime_projection'])
        (run/'target-runtime-permissions-receipt.json').write_bytes(values['runtime_recovery'])
        live=self.root/'live';(live/'.local').mkdir(mode=0o700,parents=True)
        (live/'.local/service.env').write_text('\n'.join(k+'='+v for k,v in old_owner.CLOSED_FLAGS.items())+'\nMEMORY_ALLOWED_USERS='+UID+'\n')
        (root/'.private.env').write_text('SERVICE_ROLE_KEY=synthetic-service-role\n')
        owner={'id':UID,'email':'synthetic@example.invalid','encrypted_password':'synthetic-unchanged-hash'}
        url=old_owner.TARGET+'/auth/v1/verify?type=magiclink&token=synthetic-token&redirect_to='+old_owner.urllib.parse.quote(old_owner.REDIRECT,safe='')
        result={**owner,'verification_type':'magiclink','redirect_to':old_owner.REDIRECT,'action_link':url}
        body=json.dumps(result).encode();calls=[]
        def sql(args,**kw):calls.append(args);return subprocess.CompletedProcess(args,0,json.dumps(owner),'original SQL stderr')
        class Response:
            status=200;headers={}
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self):return body
        def http(req,**kw):
            self.assertEqual(req.full_url,old_owner.TARGET+'/auth/v1/admin/generate_link')
            self.assertEqual(json.loads(req.data),{'type':'magiclink','email':owner['email'],'redirect_to':old_owner.REDIRECT})
            return Response()
        fixture_gate={**gate,'run_dir':str(run)}
        with patch.object(o.control,'OPS',run),patch.object(o.control,'load',return_value=(fixture_gate,values,data,key)),patch.object(old_owner,'ROOT',root),patch.object(old_owner,'LIVE',live),patch.object(o.subprocess,'run',side_effect=sql),patch.object(old_owner.urllib.request,'urlopen',side_effect=http) as http_mock:
            receipt=o.execute(run,self.f.path,NOW);self.assertEqual(receipt['generated_links'],1);self.assertEqual(len(calls),2);self.assertEqual(http_mock.call_count,1)
            self.assertTrue(receipt['production_browser_proof_pending']);self.assertEqual((run/'target-runtime-receipt.json').read_bytes(),values['runtime_projection'])
            with self.assertRaises(Exception):o.execute(run,self.f.path,NOW)
            self.assertEqual(http_mock.call_count,1)
        self.assertEqual(json.loads((run/'owner-link-receipt.json').read_text()),receipt)
        self.assertTrue((run/'owner-recovered-control-private/original-output.json').exists())
        self.assertTrue(any('body_b64' in json.loads(p.read_text()) for p in (run/'owner-recovered-control-private').glob('*.json')))


class DeploymentIdentityFollowupTests(FrontendControlTests):
    """Only these three selected families run in the single follow-up invocation."""
    def test_new_id_pending_then_ready(self):
        with patch.object(c.time,'sleep'):
            result,ops=self.promote('pending')
        self.assertNotEqual(ACTUAL_ID,c.PREVIEW)
        self.assertEqual(result['production_deployment_id'],ACTUAL_ID)
        self.assertEqual(result['promoted_url'],ACTUAL_URL)
        self.assertEqual(result['readiness_count'],2)
        self.assertEqual(result['status'],'PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED')
        self.assertEqual(len(result['checks']),12)
        self.assertEqual(sum(x[0]=='promote' for x in ops.calls),1)
        self.assertEqual(ops.adds,2)
        first=json.loads((self.root/'control/ready-poll-1.json').read_text())
        self.assertEqual(first['production']['readyState'],'BUILDING')
        self.assertEqual({x['id'] for x in first['aliases'].values()},{c.ROLLBACK})
        primary=result['promote_primary'];self.assertEqual(c.digest(primary['path']),primary['sha256'])
        record=json.loads(Path(primary['path']).read_text())
        self.assertEqual(base64.b64decode(record['stdout_b64']),b'original promotion stdout\n')
        self.assertEqual(base64.b64decode(record['stderr_b64']).decode(),PROMOTE_STDERR)
        self.assertEqual(self.receipt.stat().st_mode&0o777,0o600)

        unsafe=self.root/'unsafe-control';unsafe.mkdir(mode=0o755);unsafe.chmod(0o755)
        with self.assertRaisesRegex(Exception,'Unsafe private directory'):c.private_dir(unsafe)

    def test_alias_mismatch_or_expiry_stops_without_second_mutation(self):
        original_root=self.root
        causes={'alias-fail':'Foreign alias identity','expiry':'READY observation expired',
                'old-preview':'New creation identity absent','byte-fail':'Index bytes differ',
                'missing-create':'Unambiguous CLI54 creation result absent',
                'ambiguous-create':'Unambiguous CLI54 creation result absent','timeout':None,'foreign-present':None}
        for case in causes:
            self.root=original_root/case;self.root.mkdir(mode=0o700)
            self.f=Fixture(self.root);self.receipt=self.root/'frontend-final-promotion-evidence.json'
            ticks=[0.0]
            def sleep(seconds):ticks[0]+=180 if case=='expiry' else seconds
            with patch.object(c.time,'monotonic',side_effect=lambda:ticks[0]),patch.object(c.time,'sleep',side_effect=sleep):
                with self.assertRaises(RuntimeError):self.promote(case)
            result=json.loads(self.receipt.read_text());calls=json.loads((self.root/'call-summary.json').read_text())['calls']
            self.assertEqual(result['status'],'STOPPED_NO_RETRY')
            promoted=case not in ('timeout','foreign-present')
            self.assertEqual(sum(x[0]=='promote' for x in calls),int(promoted))
            self.assertEqual(sum(x[:2]==['env','add'] for x in calls),1 if case=='timeout' else 2)
            if not promoted:
                self.assertFalse(result['return_ownership_known'])
                self.assertEqual(result['return_authorization'],'DENY_RETURN_UNKNOWN_OWNERSHIP')
            else:
                self.assertIs(result['url_env_added'],True);self.assertIs(result['anon_env_added'],True)
                self.assertTrue(result['return_ownership_known'])
            self.f.owner(self.receipt)
            with self.assertRaises(Exception):c.load(self.f.path,'OWNER',NOW)
            error=json.loads((self.root/'control/primary-control-error.json').read_text())
            if causes[case] is not None:self.assertEqual(error['cause'],causes[case])
        self.root=original_root

    def test_owner_actual_receipt_id_accepts_and_mismatch_denies(self):
        with patch.object(c.time,'sleep'):result,ops=self.promote('pending')
        self.actual_promotion=self.receipt
        self.test_owner_real_original_flow_once_on_bound_current_projection()
        self.assertNotEqual(ACTUAL_ID,c.PREVIEW)
        gate,values,data,key=c.load(self.f.path,'OWNER',NOW)
        self.assertEqual(data['frontend']['promotion_receipt']['sha256'],c.digest(self.receipt))
        self.assertEqual(json.loads(c.bound(data['frontend']['promotion_receipt'],gate))['promote_primary'],result['promote_primary'])
        self.assertEqual({x['id'] for x in data['frontend']['aliases'].values()},{ACTUAL_ID})
        for mismatch in ('dpl_foreign',c.PREVIEW):
            self.f.objects['frontend']['aliases'][sorted(c.ALIASES)[0]]['id']=mismatch;self.f.write()
            with patch.object(c.subprocess,'run',side_effect=AssertionError('mutation forbidden')):
                with self.assertRaisesRegex(Exception,'Production identity/project differs'):c.load(self.f.path,'OWNER',NOW)
        self.f.owner(self.receipt)
        self.f.objects['runtime_projection']['recovery_status']='PASS';self.f.write()
        with self.assertRaises(Exception):c.load(self.f.path,'OWNER',NOW)
        self.f.objects['runtime_projection']['recovery_status']='RecoveredRuntime'
        self.f.objects['frontend'].pop('promotion_receipt');self.f.write()
        with self.assertRaises(Exception):c.load(self.f.path,'OWNER',NOW)
        c.save(self.root/'owner-id-family.json',{'accepted_id':ACTUAL_ID,'rejected_ids':['dpl_foreign',c.PREVIEW],
               'actual_original_owner_receipt':str(self.root/'host/final-export-20261004T004000Z/owner-link-receipt.json')})

class OwnerHostMarkerContractTests(unittest.TestCase):
    """Fixed Host marker only; missing positive evidence never starts Auth."""
    setUp=FrontendControlTests.setUp
    tearDown=FrontendControlTests.tearDown
    test_host_ops_equals_run_once=FrontendControlTests.test_owner_real_original_flow_once_on_bound_current_projection

    def host(self):
        self.f.owner();gate,values,data,key=c.load(self.f.path,'OWNER',NOW)
        root=self.root/'host';root.mkdir(mode=0o700)
        run=root/'final-export-20261004T004000Z';run.mkdir(mode=0o700)
        for name,field in [('target-runtime-receipt.json','runtime_projection'),('target-runtime-permissions-receipt.json','runtime_recovery')]:
            (run/name).write_bytes(values[field])
        live=self.root/'live';(live/'.local').mkdir(mode=0o700,parents=True)
        (live/'.local/service.env').write_text('\n'.join(k+'='+v for k,v in old_owner.CLOSED_FLAGS.items())+'\nMEMORY_ALLOWED_USERS='+UID+'\n')
        return root,run,live,({**gate,'run_dir':str(run)},values,data,key)

    def test_invalid_missing_foreign_stale_unbound_gate_no_auth(self):
        root,run,live,bound=self.host()
        for case in ('missing','invalid','foreign','stale','unbound'):
            with self.subTest(case=case):
                gate=copy.deepcopy(self.f.gate)
                if case=='invalid':gate['action']='PROMOTE'
                if case=='foreign':gate['run_dir']='/opt/foreign/final-export'
                if case=='stale':gate['expires_at']=(NOW-dt.timedelta(seconds=1)).isoformat()
                if case=='unbound':gate['receipt_hashes'].pop(self.f.refs['runtime_projection']['path'])
                path=self.root/(case+'-gate.json');path.write_text(json.dumps(gate));path.chmod(0o600)
                if case=='missing':path.unlink()
                with patch.object(old_owner,'ROOT',root),patch.object(o.control,'load',side_effect=lambda p,a,n:c.load(p,a,n)),patch.object(old_owner,'main') as auth:
                    with self.assertRaises(Exception):o.execute(run,path,NOW)
                    auth.assert_not_called()
                self.assertFalse((run/'owner-recovered-control-attempt.marker').exists())

    def test_unsafe_paths_and_markers_no_auth(self):
        root,run,live,bound=self.host()
        cases=[]
        missing=root/'missing';foreign=self.root/'foreign';foreign.mkdir(mode=0o700)
        link=root/'run-link';link.symlink_to(run,target_is_directory=True)
        parent_link=self.root/'parent-link';parent_link.symlink_to(root,target_is_directory=True)
        cases.extend([missing,foreign,link,parent_link/run.name])
        for path in cases:
            with self.subTest(path=str(path)),patch.object(old_owner,'ROOT',root),patch.object(o.control,'load',return_value=bound),patch.object(old_owner,'main') as auth:
                with self.assertRaises(Exception):o.execute(path,self.f.path,NOW)
                auth.assert_not_called()
        run.chmod(0o755)
        with patch.object(old_owner,'ROOT',root),patch.object(old_owner,'main') as auth:
            with self.assertRaises(Exception):o.execute(run,self.f.path,NOW)
            auth.assert_not_called()
        run.chmod(0o700)
        marker=run/'owner-recovered-control-attempt.marker';marker.symlink_to(root/'absent')
        with patch.object(old_owner,'ROOT',root),patch.object(old_owner,'LIVE',live),patch.object(o.control,'load',return_value=bound),patch.object(old_owner,'main') as auth:
            with self.assertRaises(Exception):o.execute(run,self.f.path,NOW)
            auth.assert_not_called()
        self.assertTrue(marker.is_symlink());self.assertFalse((root/'absent').exists())

    def test_marker_write_error_preserved_before_auth(self):
        root,run,live,bound=self.host();real_open=os.open
        def fail_marker(path,*args,**kw):
            if path=='owner-recovered-control-attempt.marker':raise PermissionError('synthetic marker write denied')
            return real_open(path,*args,**kw)
        with patch.object(old_owner,'ROOT',root),patch.object(old_owner,'LIVE',live),patch.object(o.control,'OPS',run),patch.object(o.control,'load',return_value=bound),patch.object(o.os,'open',side_effect=fail_marker),patch.object(old_owner,'main') as auth:
            with self.assertRaisesRegex(PermissionError,'synthetic marker write denied'):o.execute(run,self.f.path,NOW)
            auth.assert_not_called()
        records=list((run/'owner-recovered-control-private').glob('marker-error-*.json'))
        self.assertEqual(len(records),1);record=json.loads(records[0].read_text())
        self.assertEqual(record,{'type':'PermissionError','cause':'synthetic marker write denied','auth_started':False})
        self.assertFalse((run/'owner-recovered-control-attempt.marker').exists())

    def test_repo_guard_unchanged(self):
        with patch.object(c,'OPS',self.root):
            with self.assertRaisesRegex(Exception,'Noncanonical repo write'):c.save(self.root/'owner-recovered-control-attempt.marker',{})
        self.assertFalse((self.root/'owner-recovered-control-attempt.marker').exists())

    def test_marker_fsync_failure_preserves_marker_and_blocks_second_auth(self):
        root,run,live,bound=self.host();real_sync=os.fsync;calls=[]
        def fail_first(fd):
            calls.append(fd)
            if len(calls)==1:raise OSError('synthetic marker fsync failure')
            return real_sync(fd)
        with patch.object(old_owner,'ROOT',root),patch.object(old_owner,'LIVE',live),patch.object(o.control,'OPS',run),patch.object(o.control,'load',return_value=bound),patch.object(o.os,'fsync',side_effect=fail_first),patch.object(old_owner,'main') as auth:
            with self.assertRaisesRegex(OSError,'synthetic marker fsync failure'):o.execute(run,self.f.path,NOW)
            marker=run/'owner-recovered-control-attempt.marker';before=marker.read_bytes()
            with self.assertRaisesRegex(Exception,'already attempted'):o.execute(run,self.f.path,NOW)
            self.assertEqual(marker.read_bytes(),before);auth.assert_not_called()
        records=list((run/'owner-recovered-control-private').glob('marker-error-*.json'))
        self.assertEqual(len(records),1);self.assertEqual(json.loads(records[0].read_text())['auth_started'],False)

    def test_exclusive_marker_private_fsync_and_existing_denied(self):
        root,run,live,bound=self.host()
        with patch.object(old_owner,'ROOT',root),patch.object(o.os,'fsync',wraps=os.fsync) as synced:
            o._save_owner_attempt(run,{'synthetic_only':True})
            self.assertEqual(synced.call_count,2)
            with self.assertRaises(FileExistsError):o._save_owner_attempt(run,{'replacement':True})
        marker=run/'owner-recovered-control-attempt.marker'
        self.assertEqual(marker.stat().st_mode&0o777,0o600)
        self.assertEqual(json.loads(marker.read_text()),{'synthetic_only':True})

if __name__=='__main__':unittest.main(verbosity=2)
