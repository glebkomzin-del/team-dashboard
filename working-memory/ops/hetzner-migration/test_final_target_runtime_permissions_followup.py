"""Finite synthetic matrix. No real transport, no live receipts, no return execution.

Cycle runner retains all fixture bytes, output and exceptions outside cleanup.
Cases: full recovery/projection; 19 gate/proof denials; 10 failed steps;
5 partial host-write boundaries, completed host and foreign/open denial.
"""
import datetime as dt
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import traceback
import unittest
from contextlib import contextmanager, ExitStack
from unittest.mock import patch
import final_target_runtime_permissions_followup_once as f
import test_final_target_partial_source_return as existing
import final_target_runtime_once as rt
import final_target_partial_source_return_once as p
import final_writer_open_once as w
import final_prewrite_rollback_once as r

PRIVATE=Path(os.environ['PERMISSIONS_PRIVATE_DIR'])
PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True)

class Synthetic(f.Operations):
    def __init__(self,run,old):
        super().__init__(run);self.old=old;self.events=[];self.fail=None;self.images={f.STATIC:old.target_id,rt.BASE:rt.BASE,f.BASE_ALIAS:rt.BASE};self.user='10001:10001'
    def inspect(self,name):
        identity=self.images[name]
        return {'Id':identity,'RootFS':{'Layers':['base'] if identity==rt.BASE else ['base','own']},'Config':{'User':'0' if self.fail=='user' and name==f.GOOD else self.user}}
    def absent_image(self,name):w.require(name not in self.images,'Existing alias')
    def host(self,gate,values):
        self.events.append('hostcheck')
        return self.old.observe_host(gate,values)
    def health(self):
        self.events.append('health')
        if self.fail=='health':raise subprocess.TimeoutExpired('synthetic-health',90,b'private-health-body',b'private-health-error')
        return {'ok':True,'synthetic':True}
    def call(self,args,**kw):
        self.events.append(args.copy())
        if args[:2]==['docker','tag']:
            if self.fail=='bad_alias' and args[-1]==f.BAD:raise RuntimeError('private alias failure')
            self.images[args[-1]]=self.images.get(args[2],args[2])
            if args[-1]==f.STATIC:self.old.target_id=self.images[f.STATIC]
            return b''
        if args[:2]==['docker','build']:
            assert kw['timeout']==120 and (self.run/f.ATTEMPT).exists()
            assert (self.run/'runtime-permissions-build/Dockerfile').read_bytes()==f.DOCKERFILE
            if self.fail=='build':raise subprocess.CalledProcessError(31,args,b'private-build-output',b'private-build-error')
            self.images[f.GOOD]='sha256:'+'c'*64;return b''
        if args[:2]==['docker','run']:
            assert '--user' not in args and '--user=0' not in args and '--network=none' in args
            name=Path(args[-1]).name
            if self.fail=='sha_'+name:return b'wrong'
            return b'offline-server' if name=='server.py' else (self.old.stage/name).read_bytes()
        if args[:2]==['docker','exec']:
            name=Path(args[-1]).name
            if self.fail=='active_sha':return b'wrong'
            return b'offline-server' if name=='server.py' else (self.old.stage/name).read_bytes()
        if args[:2]==['docker','compose']:
            assert args==['docker','compose','up','-d','--no-build','canonical-draft'] and kw['timeout']==120
            assert (self.run/'runtime-permissions-nonroot-pass.json').exists()
            if self.fail=='startup':raise subprocess.CalledProcessError(32,args,b'private-start-output',b'private-start-error')
            self.old.running=True;self.old.image=self.images[f.STATIC]
            self.old.current_env=f.env((self.old.live/'.local/service.env').read_bytes());return b''
        if args[:2]==['docker','inspect']:
            body=json.loads(self.old.process(args,**kw));body[0]['Config']['User']=self.user
            return json.dumps(body).encode()
        if args==['nginx','-t']:
            assert 'health' in self.events
            if self.fail=='nginx':raise RuntimeError('private nginx failure')
            return b''
        if args==['systemctl','reload','nginx']:assert 'health' in self.events;return b''
        raise AssertionError('Real or unsimulated operation '+str(args))

@contextmanager
def fixture(label):
    destination=PRIVATE/label;destination.mkdir(mode=0o700)
    harness=existing.PartialReturn()
    with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
        try:
            now,local,gp,gate,proof,old,run,originals=harness.setup_case(folder,0,True,False,False)
            # Fresh continuation starts BEFORE original snapshots; immutable originals remain.
            shutil.rmtree(run/'host-runtime-original')
            run.chmod(0o700)
            (run/'source-original-runtime-flags.json').unlink()
            (run/'frontend-final-promotion-evidence.json').unlink()
            for key in ('nginx_original','nginx_maintenance'):(run/key.replace('_','-')).with_suffix('.conf').write_bytes(old.values[key])
            old.api=[True]*4
            gate['run_dir']=str(run);gate['phase']=f.PHASE;gate['operational_target_go']=True
            for name in w.HOST_FILES:
                ref=gate['original_host_sources'][name];ref['path']=str(run/'immutable-original'/name)
                gate['original_host_files'][name]['path']=str(run/'host-runtime-original'/name)
                gate['receipt_hashes'][ref['path']]=ref['sha256'];gate['receipt_hashes'][gate['original_host_files'][name]['path']]=ref['sha256']
            gate['original_host_primary']['path']=str(run/'original-host-primary.json');gate['receipt_hashes'][gate['original_host_primary']['path']]=w.digest(run/'original-host-primary.json')
            for n in p.STAGE_PATCHES:(run/'runtime-build'/n).chmod(0o600)
            (run/'vault-plaintext.json').write_text(json.dumps([{'decrypted_secret':'synthetic-vault','id':'id','name':'name','description':'desc','nonce_hex':'abc','created_at':now.isoformat(),'updated_at':now.isoformat()}]))
            common={'problem_id':w.PROBLEM,'run_dir':str(run),'observed_at':now.isoformat(),'primary_receipts':[]}
            tables=old.tables;config=json.loads(old.values['config'])
            states={'running':0,'unknown_model':0,'unknown_question':0,'cron':0,'outboxes_empty':True,'query_sha256':r.QUERY_SHA,'tables':tables}
            base=json.loads(Path(proof['refs']['baseline']['path']).read_bytes());base.update(run_dir=str(run))
            bp=run/'baseline-response.json';bp.write_text(json.dumps([{'value':tables}]))
            base['primary_response']={'path':str(bp),'sha256':w.digest(bp)};gate['receipt_hashes'][str(bp)]=w.digest(bp)
            original=json.loads((run/'vault-plaintext.json').read_text())[0]
            data={'baseline':base,'config':config,'source':{**common,**states,'roles':[{'role':role,'writable_tables':0,'executable_writers':0} for role in ('anon','authenticated','service_role')],'config':[{**x,'enabled':False} for x in config],'backend_running':False},'target':{**common,**states,'config':config},'vault':{**common,'plaintext_sha256':w.sha_bytes(b'synthetic-vault'),'metadata':{k:v for k,v in original.items() if k!='decrypted_secret'}},'auth':{**common,'source_user_hashes':['offline-auth'],'target_user_hashes':['offline-auth'],'original_user_hashes':['offline-auth']},'workflows':{**common,'versions':f.n8n.VERSIONS,'active':[],'running':0},'frontend':{**common,'promotion_attempts':0,'url_env_added':False,'anon_env_added':False,'aliases':{a:{'id':r.OLD_DEPLOYMENT,'readyState':'READY'} for a in w.ALIASES},'production_env':{'envs':[]},'cli_format':'json'},'writers':{**common,'known_writers':[],'writer_attempts':0},'timer':{**common,'status':'OWN_TIMER_PAUSED','original_active':True,'original_enabled':True,'timer_unit_sha256':p.TIMER_SHA,'code_sha256':w.BACKUP_SHA},'stage_manifest':json.loads(old.values['stage_manifest']),'prior_stages':{k:True for k in ('vault_plaintext_equal','vault_metadata_preserved','original_acl_restored','original_config_enabled_restored')},'failure':{'status':'FAILED','failed_line':131,'cause':'Permission denied','original_runtime_attempts':1,'bad_image':old.target_id,'code_sha256':{n:w.digest(run/'runtime-build'/n) for n in p.STAGE_PATCHES},'dockerfile_sha256':w.sha_bytes(f.OLD_DOCKERFILE)}}
            data['prior_stages'].update(restore_attempts=1,restore_status='PASS',original_runtime_attempts=1,original_runtime_status='FAILED')
            prim=run/'actual-synthetic-primary.json';prim.write_text('{"synthetic_only":true}')
            pref={'path':str(prim),'sha256':w.digest(prim)};gate['receipt_hashes'][str(prim)]=pref['sha256']
            for k in f.OBSERVATIONS|{'prior_stages'}:data[k]['primary_receipts']=[pref]
            data['failure']['primary_response']=pref
            proof={'problem_id':w.PROBLEM,'run_dir':str(run),'observed_at':now.isoformat(),'refs':{}}
            def bind():
                for k in f.REFS:
                    path=run/(k+'.input')
                    path.write_bytes(old.values[k] if k.startswith('nginx_') else json.dumps(data[k]).encode())
                    proof['refs'][k]={'path':str(path),'sha256':w.digest(path)};gate['receipt_hashes'][str(path)]=w.digest(path)
                (run/f.PROOF).write_text(json.dumps(proof));gate['receipt_hashes'][str(run/f.PROOF)]=w.digest(run/f.PROOF)
                gate['script_hashes']={}
                for name in ('final_target_runtime_once.py','final_target_partial_source_return_once.py',Path(f.__file__).name,Path(__file__).name):
                    src=Path(__file__).with_name(name);(run/name).write_bytes(src.read_bytes());gate['script_hashes'][name]=w.digest(src)
                review={'problem_id':w.PROBLEM,'scope':f.PHASE,'reviewed_at':now.isoformat(),'decision':'CONTINUE_BOUNDED','operational_target_go':True,'script_hashes':gate['script_hashes'],'provenance':{'model':'gpt-6-astra','effort':'high','session':'SYNTHETIC','sandbox':'read-only'}}
                rp=run/'synthetic-review.json';rp.write_text(json.dumps(review));gate['followup_review']={'path':str(rp),'sha256':w.digest(rp)};gate['receipt_hashes'][str(rp)]=w.digest(rp)
                gp.write_text(json.dumps(gate))
            bind()
            for obj,name,val in [(rt,'ROOT',old.remote_root),(rt,'LIVE',old.live),(rt,'SERVER_SHA',w.sha_bytes(b'offline-server')),(f,'STAGE',old.stage),(f,'NGINX',old.nginx)]:stack.enter_context(patch.object(obj,name,val))
            stack.enter_context(patch.object(subprocess,'run',side_effect=AssertionError('Real subprocess forbidden')))
            op=Synthetic(run,old)
            yield now,run,gp,gate,proof,data,op,bind
        except Exception:
            (destination/'exception.txt').write_text(traceback.format_exc());raise
        finally:
            harness.doCleanups()
            shutil.copytree(folder,destination/'fixture',dirs_exist_ok=True)
            for x in destination.rglob('*'):x.chmod(0o700 if x.is_dir() else 0o600)

class Permissions(unittest.TestCase):
    def test_success(self):
        with fixture('success') as (now,run,gp,gate,proof,data,op,bind):
            result=f.execute(run,gp,op,now,project_current=True)
            self.assertEqual(result['status'],'RecoveredRuntime');self.assertEqual(result['original_runtime_status'],'FAILED')
            self.assertEqual(result['counters'],{'corrected_image_builds':1,'host_completion_dispatches':1,'backend_starts':1})
            current=json.loads((run/'target-runtime-receipt.json').read_text())
            self.assertEqual(current['original_runtime_attempt_status'],'FAILED');self.assertEqual(current['recovery_receipt_sha256'],w.digest(run/f.RECOVERY))
            self.assertEqual(op.images[f.BAD],data['failure']['bad_image'])
            self.assertEqual((run/'runtime-build/Dockerfile').read_bytes(),f.OLD_DOCKERFILE)
            self.assertEqual((run/'target-runtime-attempt.marker').read_bytes(),b'single COPY-bound readonly activation')
            self.assertTrue(op.old.current_env['PRIVATE_PROVIDER']=='offline-preserved')
            self.assertTrue(op.host(gate,op.old.values)['changed'])
            for rel in [f.ATTEMPT,f.RECOVERY,'target-runtime-receipt.json','runtime-permissions-build/Dockerfile']:
                self.assertEqual((run/rel).stat().st_mode&0o777,0o600)
            with self.assertRaises(w.PreconditionsError):f.execute(run,gp,op,now)
    def test_gate_denials(self):
        faults=['no_go','phase','expired','long_gate','stale_proof','rights','source43','target43','config','cron','vault','auth','n8n','frontend','writer','timer','primary','review','attempt']
        for fault in faults:
            with self.subTest(fault=fault),fixture('deny-'+fault) as (now,run,gp,gate,proof,data,op,bind):
                if fault=='no_go':gate['operational_target_go']=False
                elif fault=='phase':gate['phase']='TARGET_WRITER_OPEN'
                elif fault=='expired':gate['expires_at']=(now-dt.timedelta(seconds=1)).isoformat()
                elif fault=='long_gate':gate['expires_at']=(now+dt.timedelta(seconds=601)).isoformat();gate['issued_at']=now.isoformat()
                elif fault=='stale_proof':proof['observed_at']=(now-dt.timedelta(seconds=301)).isoformat()
                elif fault=='rights':data['source']['roles'][0]['writable_tables']=1
                elif fault in ('source43','target43'):data['source' if fault=='source43' else 'target']['tables']=[{**x,'rows':999} for x in op.old.tables]
                elif fault=='config':data['target']['config']=[]
                elif fault=='cron':data['source']['cron']=1
                elif fault=='vault':data['vault']['plaintext_sha256']='0'*64
                elif fault=='auth':data['auth']['target_user_hashes']=['wrong']
                elif fault=='n8n':data['workflows']['active']=['writer']
                elif fault=='frontend':data['frontend']['production_env']={'envs':[{'key':'VITE_SUPABASE_URL'}]}
                elif fault=='writer':data['writers']['writer_attempts']=1
                elif fault=='timer':data['timer']['status']='active'
                bind()
                if fault=='primary':(run/'actual-synthetic-primary.json').write_text('changed')
                if fault=='review':(run/'synthetic-review.json').write_text('{}')
                if fault=='attempt':(run/f.ATTEMPT).write_text('existing')
                with self.assertRaises(w.PreconditionsError):f.execute(run,gp,op,now)
                self.assertFalse(any(isinstance(x,list) and x[:2]==['docker','build'] for x in op.events))
                self.assertFalse(op.old.running)
    def test_failed_steps(self):
        faults=['bad_alias','build','user','sha_server.py','sha_access.py','sha_gateway_journal.py','startup','active_sha','health','nginx']
        for fault in faults:
            with self.subTest(fault=fault),fixture('fail-'+fault) as (now,run,gp,gate,proof,data,op,bind):
                op.fail=fault
                with self.assertRaises(w.PreconditionsError):f.execute(run,gp,op,now)
                self.assertTrue((run/f.ATTEMPT).exists());self.assertFalse((run/f.RECOVERY).exists())
                self.assertEqual((run/'runtime-build/Dockerfile').read_bytes(),f.OLD_DOCKERFILE)
                outcomes=list(op.errors.glob('outcome-*.json'));self.assertEqual(len(outcomes),1)
                outcome=json.loads(outcomes[0].read_text());self.assertFalse(outcome['partial_return_executed'])
                self.assertLessEqual(outcome['counters']['corrected_image_builds'],1)
                if fault in ('bad_alias','build','user','sha_server.py','sha_access.py','sha_gateway_journal.py'):
                    self.assertFalse((run/'host-runtime-original').exists());self.assertFalse(op.old.running)
                for x in op.errors.iterdir():self.assertEqual(x.stat().st_mode&0o777,0o600)
    def test_partial_return_contract(self):
        # Existing host_check only. No Source return or recovery mutation.
        for changes in range(1,6):
            with fixture('partial-'+str(changes)) as (now,run,gp,gate,proof,data,op,bind):
                original={n:(run/'immutable-original'/n).read_bytes() for n in w.HOST_FILES}
                backup=run/'host-runtime-original';backup.mkdir()
                for n,b in original.items():(backup/n).write_bytes(b)
                cfg=f.env(original['service.env']);cfg.update(w.CLOSED);cfg.update(SUPABASE_URL=w.ORIGIN,SUPABASE_PUBLISHABLE_KEY='offline-native-anon')
                planned={**original,'service.env':''.join(k+'='+v+'\n' for k,v in cfg.items()).encode(),'compose.yaml':original['compose.yaml'].replace(b'image: dashboard-memory:memory-20260921-compact-guard-final',('image: '+f.STATIC).encode())}
                manifest=json.loads(original['build-manifest.json'])
                for n in p.STAGE_PATCHES:planned[n]=(op.old.stage/n).read_bytes();manifest[n]=w.sha_bytes(planned[n])
                planned['build-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
                for n in ['service.env','compose.yaml','access.py','gateway_journal.py','build-manifest.json'][:changes]:(op.old.live/('.local/service.env' if n=='service.env' else n)).write_bytes(planned[n])
                self.assertTrue(op.host(gate,op.old.values)['changed'])
                (op.old.live/'access.py').write_bytes(b'foreign')
                with self.assertRaises(Exception):op.host(gate,op.old.values)
        with fixture('open-flags') as (now,run,gp,gate,proof,data,op,bind):
            f.execute(run,gp,op,now);op.old.current_env['MEMORY_INTAKE_ENABLED']='1'
            with self.assertRaises(Exception):op.host(gate,op.old.values)

if __name__=='__main__':unittest.main()
