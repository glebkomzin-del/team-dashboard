"""Offline schema/denial/Host-remap tests; no external operations.

Question: can missing/stale/raw contradictory prerequisites become a GO?
Required: deny all such inputs; positive synthetic records load exact control schema;
Host refs resolve after staging, immutable originals unchanged. Failure blocks use.
Scope: local assembler only, not operational migration or Owner acceptance.
"""
import copy
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import prepare_final_frontend_control_proof as p
from test_final_frontend_control import Fixture, NOW, RUN, UID, KEY, ACTUAL_ID


class PreparationTests(unittest.TestCase):
    def setUp(self):
        base=Path(os.environ.get('FRONTEND_ACTUAL_PREP_EVIDENCE_DIR','/private/tmp'))
        self.root=Path(tempfile.mkdtemp(prefix='actual-proof-synthetic-',dir=base));self.root.chmod(0o700)
        self.f=Fixture(self.root)
        self.inputs={'run_dir':RUN,'action':'PROMOTE','originals':{},'observations':{},'archives':{}}
        self.error_patch=patch.object(p,'ERROR_SHA',self.f.refs['runtime_error']['sha256']);self.error_patch.start();self.addCleanup(self.error_patch.stop)
        self.key_patch=patch.dict(p.c.original.artifact,{'target_key_sha256':p.c.sha(KEY.encode())});self.key_patch.start();self.addCleanup(self.key_patch.stop)
        self.auth=[{'id':UID,'email_sha256':p.c.sha(b'mail'),'password_sha256':p.c.sha(b'password')}]
        self.config=[{'space_id':UID,'enabled':True}]
        self.cron=[{'jobid':1,'active':False},{'jobid':2,'active':False}]
        vault={'id':UID,'name':'synthetic','description':'test','nonce_hex':'00','created_at':NOW.isoformat(),
               'updated_at':NOW.isoformat(),'decrypted_secret':'synthetic-only'}
        full_body=b'SYNTHETIC recovered Target FULL archive';full=self.f.put('full',full_body);mac=self.f.put('mac',full_body)
        self.inputs['archives']={'full':full,'mac':mac}
        manifest={'format':'dashboard-full-backup-v1','files':{f'file-{i}':{'sha256':p.c.sha(str(i).encode()),'bytes':1} for i in range(198)}}
        status={'state':'ok','archive':'dashboard-synthetic.tar.gz','bytes':len(full_body),'sha256':full['sha256'],
                'selfhost':{'restore_verified':True},'canonical':{'verified':True},
                'n8n':{'credential_decryption_verified':True,'google_refresh_token_preserved':True,'external_network':False,'active':0,'published':0}}
        mac_status={'status':{**status,'files_verified':202}}
        originals={k:self.f.objects[k] for k in ('runtime_recovery','runtime_projection','runtime_failure','baseline')}
        originals.update(auth_original={'original_user_hashes':self.auth},config_original=self.config,cron_original=self.cron,
            vault_original=[vault],full_status=status,mac_status=mac_status,bundle_manifest=manifest,
            runtime_images={'memory':{'image_id':self.f.recovery['corrected_image']}},
            selfhost_restore={'auth_users_verified':True,'vault_decryption_verified':True,'roles_verified':True,'external_network':False,'services_started':['postgres']},
            canonical_restore={'verified':True,'model_api_calls':0},n8n_restore=status['n8n'])
        for key,member in (('runtime_images','runtime-images.json'),('selfhost_restore','selfhost/restore-check.json'),
                           ('canonical_restore','canonical/restore-check.json'),('n8n_restore','n8n-restore-check.json')):
            manifest['files'][member]={'sha256':p.c.sha(json.dumps(originals[key]).encode()),'bytes':len(json.dumps(originals[key]).encode())}
        self.inputs['originals']={k:self.f.put('input-'+k,v) for k,v in originals.items()}
        self.inputs['originals'].update({k:self.f.refs[k] for k in ('runtime_error','source_archive','anon_key')})
        state={'running':0,'unknown_model':0,'unknown_question':0,'cron':0,'cron_total':2,'queued_http':0,
               'config':[{**x,'enabled':False} for x in self.config]}
        self.source={'business':[{'value':self.f.objects['baseline']['tables']}],'auth':[{'value':self.auth}],
            'state':[{'value':state}],'roles':[{'role':r,'writable_tables':0,'executable_writers':0} for r in ('anon','authenticated','service_role')],
            'acl':[],'cron':[{'value':self.cron}]}
        env={**p.c.owner.CLOSED_FLAGS,'SUPABASE_URL':p.c.owner.TARGET,'MEMORY_ALLOWED_USERS':UID}
        canonical={'Id':'synthetic-canonical','Image':self.f.recovery['corrected_image'],'State':{'Running':True},
                   'Config':{'Env':[f'{k}={v}' for k,v in env.items()]}}
        self.native={'target':{'business':self.f.objects['baseline']['tables'],'auth':self.auth,'state':copy.deepcopy(state),'acl':[],
            'cron':self.cron,'vault':{'plaintext_sha256':p.c.sha(vault['decrypted_secret'].encode()),'metadata':{k:v for k,v in vault.items() if k!='decrypted_secret'}}},
            'canonical_inspect':canonical,'host_config':env,'health':{'status':'ok'},'container_inventory':[canonical],
            'marker_checks':{k:False for k in p.MARKERS},'workflows':{k:{'id':k,'versionId':v,'active':False} for k,v in p.c.n8n.VERSIONS.items()},
            'n8n_running':0,'outboxes':{'projections-rc1-20260919/response-outbox':0,'question-outbox':0},
            'archive_current':{'archive':status['archive'],'bytes':len(full_body),'sha256':full['sha256'],'mac_sha256':mac['sha256'],
                'manifest_sha256':self.inputs['originals']['bundle_manifest']['sha256']}}
        self.front={'production_env':{'envs':[]},**{a:{'id':p.c.ROLLBACK,'readyState':'READY'} for a in p.c.ALIASES}}
        self.observed=NOW
        self.input_path=self.root/'input.json';self.save_inputs()
        self.protected={name:p.digest(p.OPS/name) for name in p.c.SCRIPTS}

    def save_inputs(self):
        for key,payload in [('source',self.source),('native',self.native),('frontend',self.front)]:
            primary=self.f.put('raw-'+key,payload)
            envelope={'problem_id':p.c.PROBLEM,'run_dir':RUN,'observed_at':self.observed.isoformat(),'payload':payload,'primary_receipts':[primary]}
            self.inputs['observations'][key]=self.f.put('envelope-'+key,envelope)
        self.input_path.write_text(json.dumps(self.inputs));self.input_path.chmod(0o600)

    def tearDown(self):
        self.assertEqual(self.protected,{name:p.digest(p.OPS/name) for name in self.protected})
        p.write(self.root,'case-result.json',{'case':self._testMethodName,'synthetic_only':True,'protected_files_unchanged':True})

    def prepare(self):
        self.save_inputs()
        with patch.object(subprocess,'run',side_effect=AssertionError('EXTERNAL OPERATIONS FORBIDDEN')):
            return p.prepare(self.input_path,self.root/'prepared',NOW)

    def denied(self):
        with self.assertRaises((ValueError,KeyError,RuntimeError)):self.prepare()
        self.assertFalse((self.root/'prepared/candidate-gate.json').exists())

    def review(self,candidate):
        gate=p.jsonref(candidate)
        review={**self.f.review,'script_hashes':gate['script_hashes']}
        return self.f.put('actual-schema-synthetic-review',review)

    def owner(self):
        self.inputs['action']='OWNER'
        self.f.owner()
        promotion=p.jsonref(self.f.objects['frontend']['promotion_receipt'])
        promotion.update(return_ownership_known=True,unknown_ownership=[],ownership={k:'OWN_ADD_CONFIRMED_EXIT_0' for k in p.c.ENV_FLAGS})
        self.f.objects['frontend']['promotion_receipt']=self.f.put('actual-owned-promotion',promotion)
        self.inputs['promotion_receipt']=self.f.objects['frontend']['promotion_receipt']
        self.front.update(self.f.objects['frontend']['aliases'])
        self.front['production_env']={'envs':[{'key':key} for key in p.c.ENV_FLAGS]}
        self.native['marker_checks']['frontend-final-promotion-evidence.json']=True

    def test_positive_candidate_denied_until_review_then_exact_schema_load(self):
        candidate=self.prepare();gate=p.jsonref(candidate)
        self.assertFalse(gate['operational_frontend_go']);self.assertEqual(set(p.jsonref(gate['proof'])['refs']),p.c.REFS)
        with self.assertRaises(Exception):p.c.load(candidate['path'],'PROMOTE',NOW)
        review=self.review(candidate)
        with patch.object(subprocess,'run',side_effect=AssertionError('EXTERNAL OPERATIONS FORBIDDEN')):
            final=p.finalize(candidate['path'],review['path'],self.root/'reviewed',NOW)
        p.c.load(final['path'],'PROMOTE',NOW)
        self.assertEqual(Path(final['path']).stat().st_mode & 0o777,0o600)

    def test_effective_role_violation_despite_empty_acl_denied(self):
        self.source['roles'][2]['executable_writers']=1;self.denied()

    def test_acl_present_despite_zero_roles_denied(self):
        self.source['acl']=[{'privilege_type':'EXECUTE'}];self.denied()

    def test_unknown_role_count_denied(self):
        self.source['roles'][0]['writable_tables']=None;self.denied()

    def test_boolean_is_not_a_zero_role_count(self):
        self.source['roles'][0]['writable_tables']=False;self.denied()

    def test_stale_observation_is_not_retimestampped(self):
        self.observed=NOW-dt.timedelta(seconds=301);self.denied()

    def test_missing_underlying_primary_denied(self):
        self.save_inputs();e=p.jsonref(self.inputs['observations']['native']);e['primary_receipts']=[]
        self.inputs['observations']['native']=self.f.put('bad-envelope',e);self.input_path.write_text(json.dumps(self.inputs))
        with self.assertRaises(ValueError):p.prepare(self.input_path,self.root/'prepared',NOW)

    def test_wrapper_payload_without_matching_raw_receipt_denied(self):
        self.save_inputs();e=p.jsonref(self.inputs['observations']['native']);e['payload']['health']={'status':'invented'}
        self.inputs['observations']['native']=self.f.put('unproven-envelope',e);self.input_path.write_text(json.dumps(self.inputs))
        with self.assertRaises(ValueError):p.prepare(self.input_path,self.root/'prepared',NOW)

    def test_active_cron_denied_but_two_inactive_allowed(self):
        self.native['target']['state']['cron']=1;self.denied()

    def test_target_flag_open_denied(self):
        self.native['canonical_inspect']['Config']['Env'].append('MEMORY_QA_ENABLED=1');self.denied()

    def test_unknown_marker_coverage_denied(self):
        self.native['marker_checks'].pop('writer-open-attempt.marker');self.denied()

    def test_original_error_not_normalized_denied(self):
        self.inputs['originals']['runtime_error']=self.f.put('wrong-normalized-error',b'normalized');self.denied()

    def test_original_transitive_host_reference_requires_exact_local_bytes(self):
        projection=p.jsonref(self.inputs['originals']['runtime_projection'])
        ref=self.f.put('real-prior-stage',{'status':'synthetic-prior-stage'})
        projection['prior_stages_ref']={'path':RUN+'/prior-native.json','sha256':ref['sha256']}
        self.inputs['originals']['runtime_projection']=self.f.put('with-native-prior',projection)
        self.inputs['local_receipts']={RUN+'/prior-native.json':ref}
        candidate=self.prepare();gate=p.jsonref(candidate);proof=p.jsonref(gate['proof'])
        source=p.jsonref(proof['refs']['source'])
        self.assertTrue(any(r['sha256']==ref['sha256'] for r in source['primary_receipts']))

    def test_original_transitive_reference_missing_denied(self):
        projection=p.jsonref(self.inputs['originals']['runtime_projection'])
        projection['prior_stages_ref']={'path':RUN+'/missing-native.json','sha256':'0'*64}
        self.inputs['originals']['runtime_projection']=self.f.put('missing-native-prior',projection);self.denied()

    def test_fresh_envelope_with_old_live_payload_cannot_pass(self):
        self.native['canonical_inspect']['State']['Running']=False;self.denied()

    def test_missing_full_manifest_file_denied(self):
        manifest=p.jsonref(self.inputs['originals']['bundle_manifest']);manifest['files'].pop('file-1')
        self.inputs['originals']['bundle_manifest']=self.f.put('incomplete-manifest',manifest)
        self.native['archive_current']['manifest_sha256']=self.inputs['originals']['bundle_manifest']['sha256'];self.denied()

    def test_review_stale_or_code_different_denies(self):
        candidate=self.prepare();review=p.jsonref(self.review(candidate));review['script_hashes']={}
        ref=self.f.put('unbound-review',review)
        with self.assertRaises(Exception):p.finalize(candidate['path'],ref['path'],self.root/'reviewed',NOW)
        self.assertFalse((self.root/'reviewed/dry-load-result.json').exists())
        self.assertFalse((self.root/'reviewed/reviewed-gate.json').exists())

    def test_owner_requires_actual_new_ready_aliases(self):
        self.owner();self.front[sorted(p.c.ALIASES)[0]]['id']=p.c.PREVIEW;self.denied()

    def test_owner_unknown_env_ownership_denies_even_matching_aliases(self):
        self.owner();r=p.jsonref(self.inputs['promotion_receipt']);r['return_ownership_known']=False
        self.inputs['promotion_receipt']=self.f.put('unknown-owned-promotion',r);self.denied()

    def test_owner_current_env_removed_after_owned_promotion_denies(self):
        self.owner();self.front['production_env']['envs']=[];self.denied()

    def test_backup_manifest_cannot_relabel_other_runtime_receipt(self):
        self.inputs['originals']['runtime_images']=self.f.put('substituted-runtime-images',{'memory':{'image_id':self.f.recovery['corrected_image']},'extra':'new'})
        self.denied()

    def test_accepted_historic_archive_hash_not_rehashed_or_retimestamped(self):
        archive=self.inputs['archives']['mac'];body=Path(archive['path']).read_bytes()
        historical=NOW-dt.timedelta(days=1)
        self.inputs['archive_hash_observation']=self.f.put('accepted-hash',{'archive':archive['path'],'sha256':archive['sha256'],'bytes':len(body),'observed_at':historical.isoformat()})
        self.native['archive_current'].update(hash_kind='HISTORICAL_ACCEPTED_FULL_HASH',hash_observed_at=historical.isoformat())
        self.inputs['archives']['full']=archive
        original_digest=p.digest
        def digest(path):
            if str(path)==archive['path']:raise AssertionError('Accepted large archive must not be rehashed')
            return original_digest(path)
        with patch.object(p,'digest',side_effect=digest):candidate=self.prepare()
        self.assertFalse(p.jsonref(candidate)['operational_frontend_go'])

    def test_historical_hash_retimestamped_as_current_denied(self):
        archive=self.inputs['archives']['mac'];body=Path(archive['path']).read_bytes()
        self.inputs['archive_hash_observation']=self.f.put('accepted-hash',{'archive':archive['path'],'sha256':archive['sha256'],'bytes':len(body),'observed_at':(NOW-dt.timedelta(days=1)).isoformat()})
        self.native['archive_current'].update(hash_kind='HISTORICAL_ACCEPTED_FULL_HASH',hash_observed_at=NOW.isoformat())
        self.denied()

    def test_one_collection_command_uses_three_separately_observed_envelopes(self):
        import final_phase_common as common
        import final_target_partial_source_return_once as partial
        archive=self.inputs['archives']['mac'];body=Path(archive['path']).read_bytes()
        self.inputs['archive_hash_observation']=self.f.put('accepted-hash',{'archive':archive['path'],'sha256':archive['sha256'],'bytes':len(body),'observed_at':NOW.isoformat()})
        self.inputs['collection']={'frontend_control_directory':RUN+'/control','host_archive':'/var/backups/synthetic',
                'frontend_marker_paths':{}}
        self.inputs['local_receipts']={RUN+'/'+name:self.inputs['originals'][key]
              for name,key in [('target-runtime-receipt.json','runtime_projection'),('target-runtime-permissions-receipt.json','runtime_recovery')]}
        self.save_inputs();calls=[];test=self
        class FakeOperations:
            def __init__(self,directory):self.directory=directory
            def source_sql(self,query):
                if 'writable_tables' in query:key='roles'
                elif "SELECT 'activity_log'" in query:key='business'
                elif 'pg_namespace' in query:key='acl'
                elif 'password_sha256' in query:key='auth'
                elif 'cron_total' in query:key='state'
                elif 'to_jsonb(j)' in query:key='cron'
                else:raise AssertionError('Unexpected read-only Source query')
                calls.append(('source',key));return test.source[key]
            def cli(self,args):
                key='production_env' if args[0]=='env' else args[1]
                calls.append(('cli',key));return json.dumps(test.front[key])
        def shell(command,timeout):
            calls.append(('ssh','one-native-batch'))
            self.assertIn('8798/health',command);self.assertNotIn('generateLink',command)
            originals={RUN+'/'+name:base64.b64encode(p.read(self.inputs['originals'][key])).decode()
                for name,key in [('target-runtime-receipt.json','runtime_projection'),('target-runtime-permissions-receipt.json','runtime_recovery')]}
            return json.dumps({'payload':self.native,'observed_at':NOW.isoformat(),'host_primaries':originals,'process_records':[]}).encode()
        with patch.object(partial,'PartialOperations',FakeOperations),patch.object(common,'shell',side_effect=shell),\
             patch.object(subprocess,'run',side_effect=AssertionError('REAL OPERATIONS FORBIDDEN')):
            ref=p.collect(self.input_path,self.root/'collection')
        inputs=p.jsonref(ref)
        self.assertEqual(len([x for x in calls if x[0]=='ssh']),1)
        self.assertEqual(len([x for x in calls if x[0]=='source']),6)
        self.assertEqual(len([x for x in calls if x[0]=='cli']),3)
        self.assertEqual(set(inputs['observations']),p.OBSERVATIONS)
        self.assertEqual(len(list((self.root/'collection').glob('native-original-*.raw'))),2)
        for name,ref in inputs['observations'].items():
            e=p.jsonref(ref);self.assertTrue(e['observed_at']);self.assertIn('payload',e);self.assertGreaterEqual(len(e['primary_receipts']),2)
        self.assertFalse((self.root/'collection/candidate-gate.json').exists())

    def test_owner_staged_refs_rebase_and_original_bytes_unchanged(self):
        self.owner();candidate=self.prepare()
        p.c.load(p.finalize(candidate['path'],self.review(candidate)['path'],self.root/'reviewed',NOW)['path'],'OWNER',NOW)
        mapping=self.root/'host-map.json';mapping.write_text('{}')
        result=p.owner_bundle(candidate['path'],RUN+'/owner-proof-synthetic',mapping,self.root/'staged')
        host=p.jsonref(result);self.assertFalse(host['operational_frontend_go'])
        manifest=json.loads((self.root/'staged/host-bundle-manifest.json').read_text())
        entries={e['host_ref']['path']:e for e in manifest['files'] if 'staged_ref' in e}
        proof=json.loads(Path(entries[host['proof']['path']]['staged_ref']['path']).read_bytes())
        for name,ref in proof['refs'].items():
            self.assertIn(ref['path'],host['receipt_hashes']);self.assertEqual(ref['sha256'],host['receipt_hashes'][ref['path']])
        for name in ('runtime_recovery','runtime_projection','runtime_error','baseline','source_archive','anon_key'):
            raw=Path(entries[proof['refs'][name]['path']]['staged_ref']['path']).read_bytes()
            self.assertEqual(raw,p.read(self.inputs['originals'][name]))
        for name in ('source','target','frontend','live','vault_auth','writers','return_contract'):
            data=json.loads(Path(entries[proof['refs'][name]['path']]['staged_ref']['path']).read_bytes())
            self.assertTrue(all(ref['path'].startswith(RUN+'/owner-proof-synthetic/') for ref in data['primary_receipts']))
        # Simulate Host file resolution, then exercise the complete real load, offline.
        virtual={path:Path(e['staged_ref']['path']).read_bytes() for path,e in entries.items()}
        original_raw=p.c.raw
        def raw(path):return virtual[str(path)] if str(path) in virtual else original_raw(path)
        with patch.object(p.c,'raw',side_effect=raw),patch.object(subprocess,'run',side_effect=AssertionError('EXTERNAL OPERATIONS FORBIDDEN')):
            verified=p.finalize(result['path'],self.review(candidate)['path'],self.root/'host-virtual-reviewed',NOW)
            p.c.load(verified['path'],'OWNER',NOW)

if __name__=='__main__': unittest.main()
