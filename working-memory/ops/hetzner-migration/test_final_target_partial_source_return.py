"""Offline actual entrypoint and host bytes, synthetic transports only.

No fixture is a live receipt. Calls to network, SSH, Keychain, real Docker and
providers fail closed; native remote code executes on disposable file fixtures.
"""
import base64
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import traceback
import shutil
from contextlib import contextmanager
import unittest
from unittest.mock import patch, Mock
import final_phase_common as c
import final_writer_open_once as w
import final_prewrite_rollback_once as r
import final_target_partial_source_return_once as p
import test_final_prewrite_return as existing
import test_final_writer_preconditions as fixtures
import n8n_dashboard_pause_once as n8n


ACTUAL_EXECUTE=p.execute
PRIVATE_EVIDENCE=Path(os.environ.get('PARTIAL_RETURN_PRIVATE_DIR') or tempfile.mkdtemp(prefix='partial-return-private-',dir='/private/tmp'))
PRIVATE_EVIDENCE.mkdir(mode=0o700,parents=True,exist_ok=True)
PRIVATE_EVIDENCE.chmod(0o700)

@contextmanager
def private_case(label):
    destination=PRIVATE_EVIDENCE/label
    destination.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory() as folder:
        try:
            yield folder
        finally:
            shutil.copytree(folder,destination/'fixture',dirs_exist_ok=True)
            for path in destination.rglob('*'):
                path.chmod(0o700 if path.is_dir() else 0o600)
            r.durable(destination,'primary-files-sha256.json',{str(path.relative_to(destination)):w.digest(path) for path in destination.rglob('*') if path.is_file()})


class Offline(p.PartialOperations,existing.OfflineReturn):
    def __init__(self,run,root,values,tables):
        r.MacReturnOperations.__init__(self,run)
        self.remote_root=root;self.values=values;self.tables=tables
        self.events=[];self.commands=[];self.source_tables=tables;self.target_tables=tables
        self.acl=json.loads(values['acl_frozen']);self.config=[{**v,'enabled':False} for v in json.loads(values['config'])]
        self.live=root/'live'
        self.source_env={};self.current_env={};self.image=w.BASE;self.running=False
        self.target_id='sha256:'+'b'*64;self.api=[False]*4;self.runtime_attempt=False
        self.timer_active=False;self.front_promoted=False;self.front_env=False
        self.writer=False;self.fail=None;self.workflow_active=False
        self.stage=root/'stage';self.stage.mkdir()
        self.nginx=root/'nginx';self.nginx.write_bytes(values['nginx_maintenance'])
        self.unit=root/'timer';self.unit.write_bytes(b'offline-unit')
        self.scope_state=['workflow:read','workflow:activate','workflow:deactivate']

    def read_stage(self,ref):
        with patch.object(c,'shell',return_value=(self.stage/'build-manifest.json').read_bytes()) as transport:
            raw=p.PartialOperations.read_stage(self,ref)
        assert transport.call_count==1
        return raw

    def read(self,path):
        return super().read(path)

    def remote_python(self,code,timeout=60):
        try:return self._remote_python(code,timeout)
        except Exception as error:
            r.durable(self.local,'remote-traceback-'+__import__('uuid').uuid4().hex+'.json',{'traceback':traceback.format_exc(),'events':self.events.copy()})
            w.private_failure(self.local,error)
            raise

    def _remote_python(self,code,timeout=60):
        compile(code,'<partial-native-offline>','exec');self.commands.append(code)
        mapped=code.replace(str(w.ROOT),str(self.remote_root)).replace(str(w.LIVE),str(self.live))
        mapped=mapped.replace('/opt/dashboard-memory-stage-read-20261003/build/',str(self.stage)+'/')
        mapped=mapped.replace('/etc/nginx/sites-available/alexa',str(self.nginx))
        mapped=mapped.replace('/etc/systemd/system/dashboard-job-backup.timer',str(self.unit))
        if "assert not any('writer' in p.name" in code:
            p.require(not self.writer,'Writer already opened');return b''
        if 'for w,v in VERSIONS.items()' in code:
            key=self.local/'workflow-key.json'
            if not key.exists():key.write_text(json.dumps({'apiKey':'offline-secret'}));key.chmod(0o600)
            mapped=mapped.replace(str(self.remote_root/'n8n-pause-access-1/existing-api-key-private.json'),str(key))
            def response(request,**kw):
                identity=request.full_url.rsplit('/',1)[1]
                assert identity in n8n.VERSIONS
                self.events.append('publication_'+identity+'_'+str(self.workflow_active))
                return json.dumps({'active':self.workflow_active,'versionId':n8n.VERSIONS[identity],'activeVersionId':n8n.VERSIONS[identity]}).encode(),200,{}
            with patch.object(n8n,'http_read',side_effect=response):exec(mapped,{})
            return b''
        if 'end=time.monotonic()+90' in code:
            self.events.append('health')
            if self.fail=='health':raise subprocess.TimeoutExpired('offline-health',90,b'full-health-output',b'full-health-error')
            return b''
        stream=io.StringIO()
        def fake_run(args,**kw):
            out=self.process(args,**kw)
            return subprocess.CompletedProcess(args,0,out,b'')
        with patch.object(w,'ROOT',self.remote_root),patch.object(w,'LIVE',self.live),patch.object(w,'BACKUP_SHA',w.sha_bytes(b'offline-backup')),patch.object(subprocess,'run',side_effect=fake_run),patch.object(subprocess,'check_output',side_effect=self.process),patch('sys.stdout',stream):
            try:
                exec(mapped,{})
            except Exception as error:
                r.durable(self.local,'host-traceback-'+__import__('uuid').uuid4().hex+'.json',{'traceback':traceback.format_exc(),'events':self.events.copy()})
                raise
        return stream.getvalue().encode()

    def process(self,args,**kw):
        if args[:2]==['docker','inspect']:
            if args[2]=='-f':return b'true\n' if self.running else b'false\n'
            if args[2]==w.CANONICAL:
                return json.dumps([{'Image':self.image,'State':{'Running':self.running},'Config':{'Env':[k+'='+v for k,v in self.current_env.items()]},'Mounts':[{'Type':'bind','Source':str(self.live/'.local/cache'),'Destination':'/app/.local'}]}]).encode()
            index=int(args[2].replace('api',''))
            service=['auth','rest','api-gw','functions'][index]
            return json.dumps([{'Image':'foreign' if self.fail=='foreign_api_id' else 'sha256:offline-'+service,'NetworkSettings':{'Networks':({'foreign':{}} if self.fail=='foreign_api_network' else {name:{} for name in p.API_NETWORKS[service]}),'Ports':{'1/tcp':['open']} if self.fail=='api_port' else ({'8000/tcp':[{'HostIp':'127.0.0.1','HostPort':'8800'}]} if service=='api-gw' else {})},'State':{'Running':self.api[index]},'Config':{'Image':'foreign' if self.fail=='foreign_api_image' else p.API_IMAGES[service],'Labels':{'com.docker.compose.project':'foreign' if self.fail=='foreign_api_project' else 'dashboard-supabase-20261003','com.docker.compose.service':'foreign' if self.fail=='foreign_api_service' else service}}}]).encode()
        if args[:3]==['docker','image','inspect']:
            if args[3] in p.API_IMAGES.values():return json.dumps([{'Id':'sha256:offline-'+next(k for k,v in p.API_IMAGES.items() if v==args[3])}]).encode()
            return json.dumps([{'Id':w.BASE if args[3] in (w.BASE,'dashboard-memory:memory-20260921-compact-guard-final') else self.target_id,'RootFS':{'Layers':['base'] if args[3]==w.BASE else ['base','own']}}]).encode()
        if args[:2]==['docker','run']:
            name=Path(args[-1]).name
            return b'offline-server' if name=='server.py' else (self.stage/name).read_bytes()
        if args[:2]==['docker','compose']:
            if 'ps' in args:return b'api0\napi1\napi2\napi3\n'
            if 'stop' in args:
                self.events.append('stop_apis');self.api=[False]*4
                if self.fail=='api_stop':self.api[2]=True
                if self.fail=='source_after_stop':self.source_tables=[{**x,'rows':1} for x in self.tables]
                if self.fail=='writer_after_stop':self.writer=True
                return b''
            if 'up' in args:
                self.events.append('source_start')
                if self.fail=='activation':raise subprocess.CalledProcessError(17,args,b'full-start-output',b'full-start-error')
                self.running=True;self.image=w.BASE
                self.current_env=dict(v.split('=',1) for v in (self.live/'.local/service.env').read_text().splitlines())
                return b''
        if args[:2]==['docker','exec']:return b'0\n'
        if args[:2]==['systemctl','show']:
            return b'active\n' if args[2].endswith('.timer') and self.timer_active else b'inactive\n'
        if args[:2]==['systemctl','is-enabled']:return b'enabled\n'
        if args[:2]==['systemctl','start']:
            self.events.append('timer')
            assert (self.local/'target-partial-source-return-core-pass.json').exists()
            assert not (self.local/'target-partial-source-return-receipt.json').exists()
            if self.fail=='timer':raise subprocess.CalledProcessError(8,args,b'full-timer-output',b'full-timer-error')
            self.timer_active=True;return b''
        if args[:2]==['systemctl','reload']:self.events.append('ingress' if self.nginx.read_bytes()==self.values['nginx_original'] else 'maintenance');return b''
        if args==['nginx','-t']:return b''
        raise AssertionError('Unsimulated process '+str(args))

    def source_sql(self,query):
        if query.startswith('BEGIN;') and 'GRANT ' in query:
            assert not self.running and not any(self.api)
            self.events.append('target_inactive_proved')
        if query==self.values['query'].decode():self.events.append('source43')
        return super().source_sql(query)

    def target_sql(self,query):
        if query.startswith('SELECT json_build_object'):return {'running':0,'unknown_model':0,'unknown_question':0}
        if query=='SELECT count(*) FROM cron.job':return 0
        if query==self.values['query'].decode():self.events.append('target43')
        return super().target_sql(query)

    def stop_target(self):self.events.append('stop_canonical');self.running=False
    observe_host=p.PartialOperations.observe_host
    frontend_guard=p.PartialOperations.frontend_guard
    source_frozen=p.PartialOperations.source_frozen
    source_projection=p.PartialOperations.source_projection
    scopes_guard=p.PartialOperations.scopes_guard
    preflight_partial=p.PartialOperations.preflight_partial
    stop_partial=p.PartialOperations.stop_partial
    restore_partial_host=p.PartialOperations.restore_partial_host
    timer=p.PartialOperations.timer
    workflows=r.MacReturnOperations.workflows
    def resume(self,gate,gp,values):
        assert 'health' in self.events and 'ingress' in self.events
        def resume_transport(command,**kw):
            assert 'n8n_dashboard_pause_once.py --action resume --run-dir ' in command
            assert '--gate-receipt ' in command and kw=={'timeout':100}
            self.events.append('resume_three');self.workflow_active=True
            return b'{"status":"PASSED"}'
        with patch.object(c,'shell',side_effect=resume_transport):
            r.MacReturnOperations.resume(self,gate,gp,values)
    def cli(self,args):
        self.commands.append(args)
        if args[0]=='inspect':return json.dumps({'id':'foreign' if self.front_promoted else r.OLD_DEPLOYMENT,'readyState':'READY'}).encode()
        assert args==['env','ls','production','--format','json']
        return json.dumps({'envs':[{'key':'VITE_SUPABASE_URL'}] if self.front_env else []}).encode()


class PartialReturn(unittest.TestCase):
    def test_current_vercel_format_contract_in_productive_frontend_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            ops = p.PartialOperations(Path(folder))
            replies = [json.dumps({'id':r.OLD_DEPLOYMENT,'readyState':'READY'}) for _ in p.ALIASES]
            replies.append(json.dumps({'envs':[]}))
            ops.cli = Mock(side_effect=replies)
            ops.remote_python = Mock(return_value=b'')
            values = {'frontend':json.dumps({'problem_id':'HZ-MIGRATION-20261003-FINAL-FRONTEND',
                       'promotion_attempts':0,'url_env_added':False,'anon_env_added':False}).encode()}
            ops.frontend_guard({'run_dir':'/opt/dashboard-supabase-20261003/final-export-20261004T004000Z'},values)
            self.assertEqual(ops.cli.call_args_list[-1].args[0],
                             ['env','ls','production','--format','json'])
            self.assertEqual(ops.cli.call_count,3)
            ops.remote_python.assert_called_once()

    fixture=fixtures.FinalWriterSafety.fixture
    return_fixture=existing.ReturnProtocol.return_fixture

    def setup_case(self,folder,changes=0,runtime=False,marker=False,running=False):
        now,run,gp,gate,oldproof,oldops=self.return_fixture(folder)
        run.chmod(0o700)
        ops=Offline(run,oldops.remote_root,oldops.values,oldops.tables)
        host=ops.remote_root/run.name
        source=host/'immutable-original';source.mkdir()
        originals={n:oldops.read(gate['original_host_files'][n]['path']) for n in w.HOST_FILES}
        originals['build-manifest.json']=json.dumps({'access.py':w.sha_bytes(originals['access.py']),'gateway_journal.py':w.sha_bytes(originals['gateway_journal.py'])}).encode()
        originals['service.env']+=b'MEMORY_CACHE_DIR=/app/.local/projections-rc1-20260919\nMEMORY_QA_OUTBOX=/app/.local/question-outbox\nPRIVATE_PROVIDER=offline-preserved\n'
        stage={'origin_only_changes':{}}
        build=host/'runtime-build';build.mkdir()
        for n in ['access.py','gateway_journal.py']:
            data=b'own-target-'+n.encode();(ops.stage/n).write_bytes(data);(build/n).write_bytes(data)
            stage['origin_only_changes'][n]={'before_sha256':w.sha_bytes(originals[n]),'after_sha256':w.sha_bytes(data)}
        (ops.stage/'build-manifest.json').write_text(json.dumps(stage))
        (build/'Dockerfile').write_bytes(b'FROM dashboard-canonical-baseline:hz20261003\nCOPY access.py gateway_journal.py /app/\n')
        (host/'target-runtime-receipt.json').unlink()
        ops.values.pop('runtime')
        (ops.remote_root/'.private.env').write_text("ANON_KEY='offline-native-anon'\n")
        gate['original_host_sources']={}
        for n,b in originals.items():
            (source/n).write_bytes(b);(host/'host-runtime-original'/n).write_bytes(b)
            gate['original_host_files'][n]['sha256']=w.sha_bytes(b)
            gate['receipt_hashes'][gate['original_host_files'][n]['path']]=w.sha_bytes(b)
            ref={'path':str(w.ROOT/run.name/'immutable-original'/n),'sha256':w.sha_bytes(b)}
            gate['original_host_sources'][n]=ref;gate['receipt_hashes'][ref['path']]=ref['sha256']
        primary={'original_image':w.BASE,'original_origin':w.SOURCE_ORIGIN,'original_flags':w.ORIGINAL,'original_file_sha256':{n:w.sha_bytes(b) for n,b in originals.items()}}
        pp=host/'original-host-primary.json';pp.write_text(json.dumps(primary))
        gate['original_host_primary']['sha256']=w.digest(pp);gate['receipt_hashes'][gate['original_host_primary']['path']]=w.digest(pp)
        binding=patch.object(w,'HOST_PRIMARY_SHA',w.digest(pp));binding.start();self.addCleanup(binding.stop)
        proof={**oldproof,'refs':{k:v for k,v in oldproof['refs'].items() if k!='runtime'}}
        proof['refs']['host_primary']=gate['original_host_primary']
        # Scope key is synthetic and never a real secret file.
        ops.values['scope_key']=json.dumps({'id':'offline-key','userId':'offline-owner','apiKey':'offline-secret','scopes':['workflow:read']}).encode()
        Path(proof['refs']['scope_key']['path']).write_bytes(ops.values['scope_key'])
        proof['refs']['scope_key']['sha256']=w.sha_bytes(ops.values['scope_key'])
        pause={'problem_id':w.PROBLEM,'run_dir':gate['run_dir'],'status':'OWN_TIMER_PAUSED','original_active':True,'original_enabled':True,'timer_unit_sha256':w.sha_bytes(b'offline-unit'),'code_sha256':w.BACKUP_SHA}
        ops.values['timer_pause']=json.dumps(pause).encode();ops.values['stage_manifest']=json.dumps(stage).encode()
        for key in ['timer_pause','stage_manifest']:
            path=run/(key+'.primary');path.write_bytes(ops.values[key]);proof['refs'][key]={'path':str(path),'sha256':w.digest(path)}
        gate['stage_manifest_ref']={'path':'/opt/dashboard-memory-stage-read-20261003/build-manifest.json','sha256':w.sha_bytes(ops.values['stage_manifest'])}
        gate['receipt_hashes'][gate['stage_manifest_ref']['path']]=gate['stage_manifest_ref']['sha256']
        gate['phase']='TARGET_PARTIAL_SOURCE_RETURN'
        gate['dump_sha256']='a'*64
        comparison={'source_sha256':'a'*64,'mismatches':{},'comparison_before_auth_vault_acl':True}
        cp=host/'final-snapshot-comparison.json';cp.write_text(json.dumps(comparison))
        gate['allcopy_receipt']={'path':str(w.ROOT/run.name/cp.name),'sha256':w.digest(cp)};gate['receipt_hashes'][gate['allcopy_receipt']['path']]=w.digest(cp)
        ext={'problem_id':w.PROBLEM,'run_dir':gate['run_dir'],'observed_at':now.isoformat(),'known_external_target_writers':[],'scope':'Root inspected external Target writers'}
        ep=run/'external.primary';ep.write_text(json.dumps(ext))
        gate['external_target_writers']={'observed_at':now.isoformat(),'known_writers':[],'primary_response':{'path':str(ep),'sha256':w.digest(ep)}}
        gate['receipt_hashes'][str(ep)]=w.digest(ep)
        for name in p.SCRIPTS:
            src=Path(p.__file__).with_name(name);(host/name).write_bytes(src.read_bytes());gate['script_hashes'][name]=w.digest(src)
        for key,ref in proof['refs'].items():gate['receipt_hashes'][ref['path']]=ref['sha256']
        self.bind(run,gp,gate,proof,host)
        cfg=dict(v.split('=',1) for v in originals['service.env'].decode().splitlines())
        ops.source_env=cfg.copy();ops.current_env=cfg.copy()
        planned=originals.copy();tcfg={**cfg,**w.CLOSED,'SUPABASE_URL':w.ORIGIN,'SUPABASE_PUBLISHABLE_KEY':'offline-native-anon'}
        planned['service.env']=''.join(k+'='+v+'\n' for k,v in tcfg.items()).encode()
        planned['compose.yaml']=originals['compose.yaml'].replace(b'image: dashboard-memory:memory-20260921-compact-guard-final',b'image: dashboard-memory:hetzner-final-20261003')
        manifest=json.loads(originals['build-manifest.json'])
        for n in ['access.py','gateway_journal.py']:planned[n]=(ops.stage/n).read_bytes();manifest[n]=w.sha_bytes(planned[n])
        planned['build-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
        order=['service.env','compose.yaml','access.py','gateway_journal.py','build-manifest.json']
        for n in w.HOST_FILES:(ops.live/('.local/service.env' if n=='service.env' else n)).write_bytes(planned[n] if n in order[:changes] else originals[n])
        (ops.live/'scheduled_backup.py').write_bytes(b'offline-backup')
        for rel in ['projections-rc1-20260919/response-outbox','question-outbox']:(ops.live/'.local/cache'/rel).mkdir(parents=True)
        mp=ops.live/'.local/selfhost-backup.json'
        if marker:mp.write_text(json.dumps({'enabled':True,'migration_run':run.name}))
        else:mp.unlink()
        (host/'final-restore-attempt.json').write_text(json.dumps({'phase':'final','attempt':1,'source_sha256':'a'*64,'status':'COPY_COMPARE_PASSED_SERVICES_STOPPED' if runtime else 'running'}))
        if runtime:(host/'target-runtime-attempt.marker').write_text('single COPY-bound readonly activation')
        ops.runtime_attempt=runtime
        if running:ops.image=ops.target_id;ops.current_env=tcfg.copy();ops.running=True
        stack=[patch.object(p,'STAGE_PATCHES',stage['origin_only_changes']),patch.object(p,'FRONT_BUILD',r.FRONT_BUILD),patch.object(p,'NGINX_SHA',w.sha_bytes(ops.values['nginx_original'])),patch.object(p,'TIMER_SHA',w.sha_bytes(b'offline-unit')),patch.object(p,'SERVER_SHA',w.sha_bytes(b'offline-server')),
               patch.object(c,'shell',side_effect=AssertionError('Real SSH forbidden')),patch.object(c,'source_token',side_effect=AssertionError('Real Keychain forbidden')),patch.object(c.urllib.request,'urlopen',side_effect=AssertionError('Real HTTP forbidden'))]
        def n8n(query):
            if query.startswith('SELECT json_build_object'):
                import hashlib
                return json.dumps({'scopes':ops.scope_state,'userId':'offline-owner','md5':hashlib.md5(b'offline-secret').hexdigest()})
            if query.startswith('SELECT scopes'):return json.dumps(ops.scope_state)
            ops.events.append('scopes');ops.scope_state=['workflow:read'];return ''
        stack.append(patch.object(c,'n8n_sql',side_effect=n8n))
        for x in stack:x.start();self.addCleanup(x.stop)
        # This cleanup runs before TemporaryDirectory exit via private_case's finally.
        original_execute=ACTUAL_EXECUTE
        def traced(*args,**kw):
            try:return original_execute(*args,**kw)
            except Exception:
                r.durable(run,'entry-traceback-'+__import__('uuid').uuid4().hex+'.json',{'traceback':traceback.format_exc()})
                raise
            finally:
                r.durable(run,'case-events-'+__import__('uuid').uuid4().hex+'.json',{'events':ops.events,'commands':ops.commands})
        tracer=patch.object(p,'execute',side_effect=traced);tracer.start();self.addCleanup(tracer.stop)
        return now,run,gp,gate,proof,ops,host,originals

    def bind(self,run,gp,gate,proof,host):
        pp=run/'target-partial-source-return-proof.json';pp.write_text(json.dumps(proof));gate['receipt_hashes'][str(pp)]=w.digest(pp)
        gp.write_text(json.dumps(gate));(host/'prewrite-return-gate.json').write_bytes(gp.read_bytes())

    def test_own_partial_return_boundaries(self):
        cases=[('failed_restore',0,False,False,False),('partial_api_stop',0,False,False,False),('config_api_partial',0,True,False,False),('imagebuild',0,True,False,False)]
        cases += [('host_file_'+str(i),i,True,False,False) for i in range(1,6)]
        cases += [('marker',5,True,True,False),('startup_health',5,True,True,True),('ingress_before_receipt',5,True,True,True)]
        for name,changes,runtime,marker,running in cases:
            with self.subTest(name=name),private_case(name) as folder:
                now,run,gp,gate,proof,ops,host,originals=self.setup_case(folder,changes,runtime,marker,running)
                if name in ('config_api_partial','partial_api_stop'):ops.api=[True,False,True,False]
                if name=='imagebuild':ops.api=[True]*4
                if name=='failed_restore':
                    for n in ['access.py','gateway_journal.py']:(host/'host-runtime-original'/n).unlink()
                if name=='ingress_before_receipt':ops.nginx.write_bytes(ops.values['nginx_original'])
                self.assertEqual(p.execute(run,gp,ops,now),'SOURCE_ORIGINAL_STATE_RETURNED')
                for n,b in originals.items():self.assertEqual((ops.live/('.local/service.env' if n=='service.env' else n)).read_bytes(),b)
                self.assertEqual(ops.events.count('source_start'),1)
                self.assertLess(ops.events.index('stop_apis'),ops.events.index('acl'))
                acl=ops.events.index('acl');self.assertEqual(ops.events[acl-2:acl],['source43','target_inactive_proved'])
                self.assertLess(ops.events.index('health'),ops.events.index('ingress'))
                self.assertLess(ops.events.index('ingress'),ops.events.index('resume_three'))
                self.assertLess(ops.events.index('scopes'),ops.events.index('timer'))
                self.assertEqual(ops.events.count('stop_canonical'),1 if running else 0)
                self.assertFalse((ops.live/'.local/selfhost-backup.json').exists())
                self.assertTrue((run/'target-partial-source-return-receipt.json').exists())
                self.assertFalse((run/'target-runtime-receipt.json').exists())
                self.assertEqual(ops.acl,json.loads(ops.values['acl_original']))
                self.assertEqual(ops.config,json.loads(ops.values['config']))
                self.assertEqual({k:ops.current_env[k] for k in w.ORIGINAL},w.ORIGINAL)
                self.assertEqual(ops.image,w.BASE);self.assertTrue(ops.running)
                self.assertEqual(ops.scope_state,['workflow:read']);self.assertTrue(ops.workflow_active)
                self.assertTrue(ops.timer_active);self.assertFalse(any(ops.api))
                if not runtime:self.assertNotIn('target43',ops.events)
                for identity in n8n.VERSIONS:self.assertIn('publication_'+identity+'_True',ops.events)

    def test_unknown_states_deny_before_mutation(self):
        faults=['missing_snapshot','wrong_snapshot','foreign_file','foreign_image','foreign_env','open_flag','source43','target43','writer','frontend','frontend_env','external_writer','bad_gate','stale','missing_source','wrong_stage','foreign_marker','source_running','outbox','bad_script','foreign_api_image','foreign_api_id','foreign_api_network','foreign_api_project','foreign_api_service','api_port']
        for fault in faults:
            with self.subTest(fault=fault),private_case(fault) as folder:
                now,run,gp,gate,proof,ops,host,originals=self.setup_case(folder,5,True,True,True)
                if fault.startswith('foreign_api_') or fault=='api_port':ops.fail=fault
                elif fault=='missing_snapshot':(host/'host-runtime-original/service.env').unlink()
                elif fault=='wrong_snapshot':(host/'host-runtime-original/access.py').write_bytes(b'bad')
                elif fault=='foreign_file':(ops.live/'access.py').write_bytes(b'foreign')
                elif fault=='foreign_image':ops.image='foreign'
                elif fault=='foreign_env':ops.current_env['PRIVATE_PROVIDER']='foreign'
                elif fault=='open_flag':ops.current_env['MEMORY_INTAKE_ENABLED']='1'
                elif fault=='source43':ops.source_tables=[{**x,'rows':1} for x in ops.tables]
                elif fault=='target43':ops.target_tables=[{**x,'rows':1} for x in ops.tables]
                elif fault=='writer':ops.writer=True
                elif fault=='frontend':ops.front_promoted=True
                elif fault=='frontend_env':ops.front_env=True
                elif fault=='external_writer':gate['external_target_writers']['known_writers']=['external']
                elif fault=='bad_gate':gate['phase']='PREWRITE_SOURCE_ROLLBACK'
                elif fault=='stale':gate['expires_at']=(now-dt.timedelta(seconds=1)).isoformat()
                elif fault=='missing_source':(host/'immutable-original/access.py').unlink()
                elif fault=='wrong_stage':(ops.stage/'access.py').write_bytes(b'wrong')
                elif fault=='foreign_marker':(ops.live/'.local/selfhost-backup.json').write_text('{"enabled":true,"migration_run":"foreign"}')
                elif fault=='source_running':ops.image=w.BASE;ops.current_env=ops.source_env;ops.running=True
                elif fault=='outbox':(ops.live/'.local/cache/question-outbox/foreign.json').write_text('{}')
                elif fault=='bad_script':(host/'final_target_runtime_once.py').write_text('tamper')
                self.bind(run,gp,gate,proof,host)
                with self.assertRaises(w.PreconditionsError) as rejected:p.execute(run,gp,ops,now)
                self.assert_denial(fault,rejected.exception,run,ops)
                self.assertFalse((run/'target-partial-source-return-attempt.marker').exists())
                self.assertFalse(any(e in ops.events for e in ['maintenance','acl','stop_apis','source_start','timer']))

    def test_activation_health_stop_and_timer_failure_primary(self):
        for fault in ['api_stop','activation','health','timer','source_after_stop','writer_after_stop']:
            with self.subTest(fault=fault),private_case(fault) as folder:
                now,run,gp,gate,proof,ops,host,originals=self.setup_case(folder,5,True,True,True)
                ops.fail=fault;ops.api=[True]*4
                with self.assertRaises(w.PreconditionsError) as rejected:p.execute(run,gp,ops,now)
                self.assert_denial(fault,rejected.exception,run,ops)
                self.assertEqual(ops.nginx.read_bytes(),ops.values['nginx_maintenance'])
                self.assertFalse((run/'target-partial-source-return-receipt.json').exists())
                if fault in ['activation','health']:self.assertNotIn('resume_three',ops.events);self.assertNotIn('ingress',ops.events)
                if fault in ['api_stop','source_after_stop','writer_after_stop']:self.assertNotIn('acl',ops.events)
                if fault in ['activation','health','timer']:
                    expected={'activation':('full-start-output','full-start-error'),'health':('full-health-output','full-health-error'),'timer':('full-timer-output','full-timer-error')}[fault]
                    records=[json.loads(path.read_text()) for path in run.rglob('*.json') if 'private-errors' in str(path)]
                    self.assertTrue(any(base64.b64decode(x.get('stdout_b64') or '').decode()==expected[0] and base64.b64decode(x.get('stderr_b64') or '').decode()==expected[1] for x in records))
                if fault!='timer':self.assertNotIn('timer',ops.events)
                else:
                    self.assertIn('timer',ops.events);self.assertIn('resume_three',ops.events);self.assertIn('scopes',ops.events)
                    self.assertTrue((run/'target-partial-source-return-core-pass.json').exists())
                if fault in ['api_stop','source_after_stop','writer_after_stop']:self.assertNotIn('source_start',ops.events);self.assertNotIn('resume_three',ops.events)

    def assert_denial(self,fault,error,run,ops):
        # Match the exact outer private record, then nested host primary if wrapped.
        path=Path(str(error).split('private primary error: ')[1].split('; no automatic retry')[0])
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        primary=json.loads(path.read_text())
        causes=primary['primary_error']+'\n'+'\n'.join(x.read_text() for x in run.rglob('*traceback*.json'))
        records=[json.loads(x.read_text()) for x in run.rglob('*.json') if 'private-errors' in str(x)]+[primary]
        causes+='\n'+'\n'.join(json.dumps(x) for x in records)
        for record in records:
            for key in ['stdout_b64','stderr_b64']:
                if record.get(key):causes+='\n'+base64.b64decode(record[key]).decode(errors='replace')
            for key in ['stdout','stderr']:
                if isinstance(record.get(key),dict):causes+='\n'+base64.b64decode(record[key]['base64']).decode(errors='replace')
        expected={'missing_snapshot':'Missing snapshot','wrong_snapshot':'Wrong snapshot','foreign_file':'Foreign host file','foreign_image':'Foreign canonical image','foreign_env':'Foreign canonical environment','open_flag':'Foreign canonical environment','source43':'Source43 differs','target43':'Target43 differs','writer':'Writer already opened','frontend':'Frontend alias changed','frontend_env':'Frontend env added','external_writer':'External writer known or observation stale','bad_gate':'Partial return gate absent','stale':'Gate stale','missing_source':'access.py','wrong_stage':'Wrong stage patch','foreign_marker':'Foreign marker','source_running':'Canonical running','outbox':'Outbox not empty','bad_script':'Host helper SHA differs','foreign_api_project':'Foreign API project','foreign_api_service':'Foreign API service','foreign_api_image':'Foreign API image','foreign_api_id':'Foreign API image ID','foreign_api_network':'Foreign API network','api_port':'API published port','api_stop':'API still running','activation':'full-start-error','health':'full-health-error','timer':'full-timer-error','source_after_stop':'Source43 differs','writer_after_stop':'Writer already opened'}
        self.assertIn(expected[fault],causes)
        reached={'api_stop':'stop_apis','activation':'source_start','health':'health','timer':'timer','source_after_stop':'stop_apis','writer_after_stop':'stop_apis'}
        if fault in reached:self.assertIn(reached[fault],ops.events)
        elif fault in ('source43','target43','missing_snapshot','wrong_snapshot','foreign_file','foreign_image','foreign_env','open_flag','wrong_stage','foreign_marker','source_running','outbox','foreign_api_image','foreign_api_id','foreign_api_network','foreign_api_project','foreign_api_service','api_port'):
            self.assertIn('source43',ops.events)

    def test_stage_exact_remote_transport_and_private_failure(self):
        with private_case('stage_transport') as folder:
            root=Path(folder);ops=p.PartialOperations(root)
            data=b'bounded-stage'
            ref={'path':p.STAGE_MANIFEST,'sha256':w.sha_bytes(data)}
            with patch.object(c,'shell',return_value=data) as transport:
                self.assertEqual(ops.read_stage(ref),data)
                self.assertEqual(transport.call_args.args[0], 'test ! -L '+p.STAGE_MANIFEST+' && cat '+p.STAGE_MANIFEST)
                self.assertEqual(transport.call_args.kwargs,{'timeout':60})
                with self.assertRaisesRegex(w.PreconditionsError,'Stage read outside exact contract'):
                    ops.read_stage({**ref,'path':p.STAGE_MANIFEST+'/other'})
                self.assertEqual(transport.call_count,1)
            with patch.object(c.subprocess,'run',return_value=subprocess.CompletedProcess([],0,data,b'')) as process:
                self.assertEqual(ops.read_stage(ref),data)
                self.assertEqual(process.call_args.args[0],c.SSH+['test ! -L '+p.STAGE_MANIFEST+' && cat '+p.STAGE_MANIFEST])
            with patch.object(c,'ERROR_DIR',root/'private-errors'),patch.object(c.subprocess,'run',return_value=subprocess.CompletedProcess([],9,b'full-ssh-output',b'full-ssh-error')) as process:
                with self.assertRaisesRegex(RuntimeError,'SSH_ERROR') as rejected:ops.read_stage(ref)
                self.assertEqual(process.call_args.args[0],c.SSH+['test ! -L '+p.STAGE_MANIFEST+' && cat '+p.STAGE_MANIFEST])
                record=json.loads(next((root/'private-errors').glob('*.json')).read_text())
                self.assertEqual(base64.b64decode(record['stdout']['base64']),b'full-ssh-output')
                self.assertEqual(base64.b64decode(record['stderr']['base64']),b'full-ssh-error')
            with patch.object(c,'shell',return_value=b'tampered'),self.assertRaisesRegex(w.PreconditionsError,'Stage primary SHA differs'):ops.read_stage(ref)
            with patch.object(c,'shell',return_value=b'wrapped-result') as transport:
                self.assertEqual(ops.remote_python('print("wrapped-result")'),b'wrapped-result')
                self.assertIn('w.private_failure',transport.call_args.args[0])
                self.assertIn('Native return stopped; private primary:',transport.call_args.args[0])
            with patch.object(c,'ERROR_DIR',root/'wrapper-errors'),patch.object(c.subprocess,'run',return_value=subprocess.CompletedProcess([],10,b'nested-host-private-path',b'full-wrapper-error')):
                with self.assertRaisesRegex(RuntimeError,'SSH_ERROR'):ops.remote_python('raise RuntimeError("nested")')
                record=json.loads(next((root/'wrapper-errors').glob('*.json')).read_text())
                self.assertEqual(base64.b64decode(record['stderr']['base64']),b'full-wrapper-error')


    def test_legacy_scope_shadow_primary_confirmed(self):
        with private_case('scope_shadow') as folder:
            ops=r.MacReturnOperations(Path(folder));ops.scopes=[]
            try:ops.scopes({})
            except TypeError as error:
                record={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
                r.durable(Path(folder),'legacy-shadow-primary.json',record)
                self.assertIn('not callable',record['message'])
            else:self.fail('Legacy shadow must reproduce actual caller failure')


    def test_cli_invokes_actual_execute_with_simulated_transports(self):
        with private_case('cli') as folder:
            now,run,gp,gate,proof,ops,host,originals=self.setup_case(folder)
            actual=p.execute
            def injected(run,gp):return actual(run,gp,ops,now)
            with patch.object(p,'execute',side_effect=injected),patch('sys.stdout',io.StringIO()) as stdout:
                self.assertEqual(p.main(['--run-dir',str(run),'--gate-receipt',str(gp)]),0)
            self.assertEqual(json.loads(stdout.getvalue())['status'],'SOURCE_ORIGINAL_STATE_RETURNED')

if __name__=='__main__':unittest.main()
