"""Access exception matrix: raw positive proof, violated/unknown deny.

Question: can READY or Login HTTP200 alone unlock the protected-alias exception?
Required: all six anonymous exact artifact responses, bounded unchanged policy,
same production, immutable stopped parent and bound raw primaries. Tests are local;
failure blocks use. Accepted legacy paths are checked only for this consumer delta.
"""
import base64
import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import frontend_access_successor as a
import prepare_final_frontend_control_proof as p
from test_prepare_final_frontend_control_proof import PreparationTests
from test_final_frontend_control import NOW, RUN, ACTUAL_ID, ACTUAL_URL


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.prep=PreparationTests();self.prep.setUp();self.addCleanup(self.prep.doCleanups)
        self.prep.owner();self.f=self.prep.f;self.root=self.prep.root
        production={'id':ACTUAL_ID,'url':ACTUAL_URL,'target':'production','readyState':'READY','aliases':sorted(a.ALIASES)}
        parent={'status':'STOPPED_NO_RETRY','promotion_attempts':1,'url_env_added':True,'anon_env_added':True,
                'return_ownership_known':True,'unknown_ownership':[],
                'ownership':{k:'OWN_ADD_CONFIRMED_EXIT_0' for k in a.ENV},'production':production,
                'production_deployment_id':ACTUAL_ID,'runtime_recovery_sha256':self.prep.inputs['originals']['runtime_recovery']['sha256'],
                'artifact_sha256':a.ARTIFACT_SHA,'promoted_url':ACTUAL_URL,'readiness_count':2}
        parent_ref=self.f.put('access-parent',parent)
        self.parent_patch=patch.object(a,'PARENT_SHA',parent_ref['sha256']);self.parent_patch.start();self.addCleanup(self.parent_patch.stop)
        self.provider={'project':{'id':a.PROJECT,'ssoProtection':{'deploymentType':'all_except_custom_domains'}},
                       'deployment':{'id':ACTUAL_ID,'projectId':a.PROJECT,'target':'production','readyState':'READY',
                                     'url':ACTUAL_URL,'alias':sorted(a.ALIASES),'automaticAliases':[a.SECONDARY]}}
        for key,alias in [('alias-primary',a.PRIMARY),('alias-secondary',a.SECONDARY)]:
            self.provider[key]={'alias':alias,'projectId':a.PROJECT,'deploymentId':ACTUAL_ID,'redirect':None,'redirectStatusCode':None}
        artifact=json.loads((a.OPS/'frontend-target-artifact.json').read_bytes());output=Path(artifact['build_path'])/'.vercel/output'
        config_ref={'path':str(output/'config.json'),'sha256':artifact['output_hashes']['config.json']}
        config=json.loads((output/'config.json').read_bytes());self.expected_headers=list(config['routes'][0]['headers'].items())
        before,after={},{}
        for name,value in self.provider.items():
            raw={'args':['api','/synthetic','--method','GET'],'exit_code':0,
                 'stdout_b64':base64.b64encode(json.dumps(value).encode()).decode(),'observed_at':NOW.isoformat()}
            before[name]=self.f.put('before-'+name,raw);after[name]=self.f.put('after-'+name,raw)
        public={}
        for name in artifact['current_static_hashes']:
            if name=='static/index.html':routes=['/','/memory-next?recovery=1']
            elif name.startswith('static/assets/'):routes=['/'+name.removeprefix('static/')]
            else:continue
            for route in routes:
                url='https://'+a.PRIMARY+route
                public[route]=self.f.put('public-'+str(len(public)),{'requested_url':url,'final_url':url,'redirects':[],
                     'credentials_sent':False,'request_headers':{},'status':200,'headers':self.expected_headers,
                     'body_b64':base64.b64encode((output/name).read_bytes()).decode(),'observed_at':NOW.isoformat()})
        secondary=self.f.put('secondary',{'requested_url':'https://'+a.SECONDARY+'/', 'final_url':'https://vercel.com/login',
            'redirects':[{'requested_url':'https://'+a.SECONDARY+'/','status':302,'location':'https://vercel.com/login'}],
            'credentials_sent':False,'request_headers':{},'status':200,'headers':[['X-Matched-Path','/login']],
            'body_b64':base64.b64encode(b'<title>Login - Vercel</title>').decode(),'observed_at':NOW.isoformat()})
        self.receipt={k:v for k,v in parent.items() if k!='status'}
        self.receipt.update(schema=a.SCHEMA,status='READONLY_VERIFIED',phase=a.PHASE,problem_id=a.PROBLEM,run_dir=RUN,
             operational_go=False,parent_receipt=parent_ref,
             artifact_ref={'path':str(a.OPS/'frontend-target-artifact.json'),'sha256':a.ARTIFACT_SHA},config_ref=config_ref,
             window_started_at=(NOW-dt.timedelta(seconds=5)).isoformat(),observed_at=NOW.isoformat(),
             provider_before=before,provider_after=after,provider_before_projection=a.provider_projection(self.provider),
             provider_after_projection=a.provider_projection(self.provider),public_primaries=public,secondary_primary=secondary,
             historical_protection_configuration='UNKNOWN',secondary_classification='EXISTING_SSO_PROTECTED_AUTOMATIC_ALIAS',
             primary_alias=a.PRIMARY,secondary_alias=a.SECONDARY,static_acceptance='HISTORICAL_DEPLOYMENT_BOUND_BYTES',
             later_current_operational_facts_required=True)

    def mutate_raw(self,ref,change):
        value=p.jsonref(ref);change(value);return self.f.put('mutated-'+str(len(list(self.root.iterdir()))),value)

    def valid(self):return a.validate(self.receipt,run=RUN,recovery_sha=self.prep.inputs['originals']['runtime_recovery']['sha256'])

    def test_fulfilled_raw_proof_and_owner_exact_load_and_host_remap(self):
        self.assertEqual(self.valid(),ACTUAL_ID)
        self.prep.inputs['promotion_successor_ref']=self.f.put('access-successor',self.receipt)
        self.prep.inputs['promotion_receipt']=self.prep.inputs['promotion_successor_ref']
        self.prep.front['access_provider']=self.provider
        self.prep.inputs['frontend_access_current_ref']=self.f.put('owner-current-access',{'problem_id':a.PROBLEM,'run_dir':RUN,
            'observed_at':NOW.isoformat(),'provider_primaries':self.receipt['provider_after'],'payload':self.provider})
        candidate=self.prep.prepare();gate=p.jsonref(candidate)
        self.assertEqual(gate['script_hashes']['frontend_access_successor.py'],p.digest(a.OPS/'frontend_access_successor.py'))
        p.c.load(p.finalize(candidate['path'],self.prep.review(candidate)['path'],self.root/'reviewed',NOW)['path'],'OWNER',NOW)
        mapping=self.root/'host-map.json';mapping.write_text('{}')
        host=p.owner_bundle(candidate['path'],RUN+'/access-host',mapping,self.root/'host-staged')
        manifest=json.loads((self.root/'host-staged/host-bundle-manifest.json').read_bytes())
        virtual={e['host_ref']['path']:Path(e['staged_ref']['path']).read_bytes() for e in manifest['files'] if 'staged_ref' in e}
        old=p.c.raw
        with patch.object(p.c,'raw',side_effect=lambda path:virtual.get(str(path)) if str(path) in virtual else old(path)):
            p.c.load(p.finalize(host['path'],self.prep.review(candidate)['path'],self.root/'host-reviewed',NOW)['path'],'OWNER',NOW)

    def test_violated_root_login_200_counterexample_denied(self):
        self.receipt['public_primaries']['/']=self.mutate_raw(self.receipt['public_primaries']['/'],lambda x:x.update(body_b64=base64.b64encode(b'<title>Login - Vercel</title>').decode()))
        with self.assertRaises(ValueError):self.valid()

    def test_unknown_secondary_primary_denied(self):
        del self.receipt['secondary_primary']
        with self.assertRaises((ValueError,KeyError)):self.valid()

    def test_current_policy_changed_denied(self):
        current=copy.deepcopy(self.provider);current['project']['ssoProtection']={'deploymentType':'all'}
        with self.assertRaises(ValueError):a.validate(self.receipt,current_provider=current)

    def test_gate_unbound_primary_denied(self):
        hashes={r['path']:r['sha256'] for r in a.references(self.receipt)};hashes.pop(self.receipt['public_primaries']['/']['path'])
        with self.assertRaises(ValueError):a.validate(self.receipt,hashes=hashes)

    def test_wrong_parent_hash_denied(self):
        self.receipt['parent_receipt']=self.f.put('different-parent',{'status':'STOPPED_NO_RETRY'})
        with self.assertRaises(ValueError):self.valid()

    def test_missing_asset_denied_despite_ready_both_aliases(self):
        self.receipt['public_primaries'].pop(next(k for k in self.receipt['public_primaries'] if k.startswith('/assets/')))
        with self.assertRaises(ValueError):self.valid()

    def test_static_age_not_renewed_current_observation_must_be_fresh(self):
        ref=self.f.put('fresh-current',{'problem_id':a.PROBLEM,'run_dir':RUN,'observed_at':NOW.isoformat(),
                     'provider_primaries':self.receipt['provider_after'],'payload':self.provider})
        hashes={r['path']:r['sha256'] for r in a.references(self.receipt)};hashes[ref['path']]=ref['sha256']
        self.assertEqual(a.current_observation(ref,a.local_read,hashes,run=RUN,now=NOW),self.provider)
        with self.assertRaises(ValueError):a.current_observation(ref,a.local_read,hashes,run=RUN,now=NOW+dt.timedelta(seconds=301))

    def writer_case(self, missing_current=False):
        import final_writer_open_once as writer
        from test_final_writer_preconditions import FinalWriterSafety
        case=FinalWriterSafety();self.addCleanup(case.doCleanups)
        folder=self.root/'writer-synthetic';folder.mkdir()
        now,run,gate_path,gate=case.fixture(folder);now=NOW
        gate['issued_at']=NOW.isoformat();gate['expires_at']=(NOW+dt.timedelta(seconds=300)).isoformat()
        manifest_path=run/'final-writer-prerequisites.json';manifest=json.loads(manifest_path.read_bytes())
        receipts={k:json.loads(Path(ref['path']).read_bytes()) for k,ref in manifest['receipts'].items()}
        for name in ('source','owner'):
            receipts[name]['observed_at']=NOW.isoformat()
        receipts['runtime']['recovery_receipt_sha256']=self.receipt['runtime_recovery_sha256']
        receipt=copy.deepcopy(self.receipt);receipt['run_dir']=str(run);receipts['frontend']=receipt
        ref=p.write(run,'frontend-access-successor-receipt.json',receipt);manifest['receipts']['frontend']=ref
        hashes=gate['receipt_hashes'];hashes[ref['path']]=ref['sha256']
        for ref in a.references(receipt):hashes[ref['path']]=ref['sha256']
        current=p.write(run,'current-access.json',{'problem_id':a.PROBLEM,'run_dir':str(run),'observed_at':NOW.isoformat(),
                       'provider_primaries':receipt['provider_after'],'payload':self.provider})
        hashes[current['path']]=current['sha256'];gate['frontend_access_current_ref']=current
        gate['frontend_access_schema']=a.SCHEMA
        gate['script_hashes']['frontend_access_successor.py']=p.digest(a.OPS/'frontend_access_successor.py')
        manifest_path.write_text(json.dumps(manifest));hashes[str(manifest_path)]=writer.digest(manifest_path)
        if missing_current:del hashes[current['path']]
        original=writer.re.fullmatch
        def mapped(pattern,string,*args,**kwargs):
            if pattern.startswith('/opt/dashboard-supabase-20261003/'):
                pattern=pattern.replace('/opt/dashboard-supabase-20261003',str(folder))
            return original(pattern,string,*args,**kwargs)
        with patch.object(writer.re,'fullmatch',side_effect=mapped):
            return writer.validate_preconditions(gate,manifest,receipts,now=now,script_hashes=gate['script_hashes'],
                     receipt_hashes=hashes,frontend_read_bytes=a.local_read)

    def test_writer_accepts_bound_successor_with_separate_fresh_current_proof(self):
        self.assertTrue(self.writer_case()['run_dir'])

    def test_writer_unknown_current_proof_denies(self):
        with self.assertRaises((ValueError,RuntimeError)):self.writer_case(missing_current=True)

    def test_owner_collection_emits_actual_current_raw_contract_and_assembles(self):
        import final_phase_common as common
        import final_target_partial_source_return_once as partial
        test=self;prep=self.prep
        prep.inputs['promotion_successor_ref']=self.f.put('collector-successor',self.receipt)
        archive=prep.inputs['archives']['mac'];prep.inputs['archives']['full']=archive
        prep.inputs['archive_hash_observation']=self.f.put('accepted-hash',{'archive':archive['path'],'sha256':archive['sha256'],
                   'bytes':len(p.read(archive)),'observed_at':NOW.isoformat()})
        prep.native['archive_current'].update(hash_kind='HISTORICAL_ACCEPTED_FULL_HASH',hash_observed_at=NOW.isoformat())
        prep.inputs['collection']={'frontend_control_directory':RUN+'/control','host_archive':'/var/backups/synthetic','frontend_marker_paths':{}}
        prep.save_inputs();calls=[]
        class Operations:
            def __init__(self,directory):pass
            def source_sql(self,query):
                if 'writable_tables' in query:key='roles'
                elif "SELECT 'activity_log'" in query:key='business'
                elif 'pg_namespace' in query:key='acl'
                elif 'password_sha256' in query:key='auth'
                elif 'cron_total' in query:key='state'
                elif 'to_jsonb(j)' in query:key='cron'
                else:raise AssertionError('Unexpected query')
                return prep.source[key]
            def cli(self,args):
                calls.append(args)
                if args[0]=='api':
                    if '/projects/' in args[1]:key='project'
                    elif '/deployments/' in args[1]:key='deployment'
                    else:key='alias-primary' if args[1].endswith(a.PRIMARY) else 'alias-secondary'
                    return json.dumps(test.provider[key]).encode()
                return json.dumps(prep.front['production_env'] if args[0]=='env' else prep.front[args[1]]).encode()
        def shell(command,timeout):
            host={RUN+'/'+name:base64.b64encode(p.read(prep.inputs['originals'][key])).decode()
                  for name,key in [('target-runtime-receipt.json','runtime_projection'),('target-runtime-permissions-receipt.json','runtime_recovery')]}
            return json.dumps({'payload':prep.native,'observed_at':NOW.isoformat(),'host_primaries':host}).encode()
        class Clock(dt.datetime):
            @classmethod
            def now(cls,tz=None):return NOW
        with patch.object(partial,'PartialOperations',Operations),patch.object(common,'shell',side_effect=shell),patch.object(p.dt,'datetime',Clock):
            ref=p.collect(prep.input_path,self.root/'owner-collected',assemble=True)
        inputs=p.jsonref(ref);current=p.jsonref(inputs['frontend_access_current_ref'])
        self.assertEqual(len(current['provider_primaries']),4)
        for name,primary in current['provider_primaries'].items():
            raw=p.jsonref(primary)
            self.assertEqual(base64.b64decode(raw['stdout_b64']),json.dumps(self.provider[name]).encode())
        self.assertEqual(len([args for args in calls if args[0]=='api']),4)
        hashes={r['path']:r['sha256'] for r in a.references(current)};hashes[inputs['frontend_access_current_ref']['path']]=inputs['frontend_access_current_ref']['sha256']
        self.assertEqual(a.current_observation(inputs['frontend_access_current_ref'],a.local_read,hashes,run=RUN,now=NOW),self.provider)
        gate=json.loads((self.root/'owner-collected/candidate/candidate-gate.json').read_bytes())
        self.assertFalse(gate['operational_frontend_go'])

if __name__=='__main__':unittest.main()
