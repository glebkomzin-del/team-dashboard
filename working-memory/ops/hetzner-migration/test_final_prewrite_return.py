"""Disposable offline entrypoint proofs. No provider, SSH, Docker or auth calls."""
import base64
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import patch, Mock
import final_phase_common as c
import final_writer_open_once as w
import final_prewrite_rollback_once as r
import test_final_writer_preconditions as fixtures


class OfflineReturn(r.MacReturnOperations):
    def __init__(self, run, remote_root, values, tables):
        super().__init__(run)
        self.remote_root = remote_root; self.values = values; self.tables = tables
        self.events = []; self.commands = []; self.source_tables = tables; self.target_tables = tables
        self.acl = json.loads(values['acl_frozen']); self.config = [{**v, 'enabled': False} for v in json.loads(values['config'])]
        self.fail = None; self.marker = False
        self.live = remote_root/'live'; self.live.mkdir(); (self.live/'.local').mkdir()
        for name in w.HOST_FILES:
            (self.live/('.local/service.env' if name == 'service.env' else name)).write_text('target-fixture')
        (self.live/'.local/selfhost-backup.json').write_text(json.dumps({'enabled': True, 'migration_run': run.name}))

    def read(self, path):
        if path.startswith(str(w.ROOT)+'/'):
            path = str(self.remote_root)+path[len(str(w.ROOT)):]
        return Path(path).read_bytes()

    def remote_python(self, code, timeout=60):
        compile(code, '<offline-native-return>', 'exec')
        self.commands.append(code)
        if 'op.verify_runtime(' in code:
            return b''  # Accepted native runtime boundary is mocked, never Docker.
        if 'for w,v in VERSIONS.items()' in code:
            return b''  # Supported API state transport; resume itself is mocked below.
        if "assert not any('writer' in p.name" in code:
            r.require(not self.marker, 'Writer already opened')
            return b''
        if "tempfile.mkstemp" in code:
            self.events.append('host')
            mapped = code.replace(str(w.ROOT), str(self.remote_root)).replace(str(w.LIVE), str(self.live))
            with patch.object(subprocess, 'check_output', return_value=b'false\n'):
                exec(mapped, {})  # Execute actual exact-five-file copy code on disposable files.
            return b''
        if 'docker' in code and "'compose','up'" in code:
            self.events.append('source_start')
            if self.fail == 'activation':
                raise subprocess.CalledProcessError(17, ['offline-source-start'], b'full-output-private', b'full-stderr-private')
            mapped = code.replace(str(w.ROOT), str(self.remote_root)).replace(str(w.LIVE), str(self.live))
            def inspect(args):
                if args[1:3] == ['image','inspect']: return json.dumps([{'Id':w.BASE}]).encode()
                env=(self.live/'.local/service.env').read_text().splitlines()
                return json.dumps([{'Image':w.BASE,'State':{'Running':True},'Config':{'Env':env}}]).encode()
            with patch.object(subprocess,'check_output',side_effect=inspect),patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'',b'')) as startup:
                exec(mapped,{})
                assert startup.call_count == 1
                assert startup.call_args.args[0] == ['docker','compose','up','-d','--no-build','canonical-draft']
            return b''
        if 'end=time.monotonic()+90' in code:
            self.events.append('health')
            if self.fail == 'health': raise subprocess.TimeoutExpired('offline-health', 90, b'health-private', b'health-stderr')
            return b''
        if "p.write_bytes(" in code:
            self.events.append('ingress' if "p.read_bytes()==" in code else 'maintenance')
            return b''
        raise AssertionError('Unhandled offline native transport')

    def source_sql(self, query):
        from final_quiescence_once import acl_query, EFFECTIVE_PRIVILEGES_SQL
        if query == self.values['query'].decode(): return [{'value': self.source_tables}]
        if query == EFFECTIVE_PRIVILEGES_SQL:
            return [{'role': x, 'writable_tables': 0, 'executable_writers': 0} for x in ['anon','authenticated','service_role']]
        if query == acl_query(): return self.acl
        if query.startswith('BEGIN;') and 'GRANT ' in query:
            self.events.append('acl'); self.acl = json.loads(self.values['acl_original']); return []
        if query.startswith('BEGIN;') and 'LOCK TABLE public.wm_processing_config' in query:
            self.events.append('config'); self.config = json.loads(self.values['config']); return []
        if query.startswith('SELECT json_build_object'): return [{'value': {'running':0,'unknown_model':0,'unknown_question':0,'config':self.config}}]
        if query == 'SELECT count(*) AS count FROM cron.job': return [{'count':0}]
        if query.startswith('SELECT json_agg(c'): return [{'value': self.config}]
        raise AssertionError('Unhandled offline Source query')

    def target_sql(self, query):
        if query == self.values['query'].decode(): return self.target_tables
        if query.startswith('SELECT json_agg(c'): return json.loads(self.values['config'])
        raise AssertionError('Unhandled offline Target query')

    def mutation_guard(self, gate, values): self.markers_absent(gate['run_dir'])

    def stop_target(self): self.events.append('stop')

    def resume(self, gate, gate_path, values):
        # Mock only supported resume transport; never workflow SQL.
        self.events.append('resume_three')
        self.workflows(gate['run_dir'], False)
        self.workflows(gate['run_dir'], True)

    def cli(self, args):
        self.commands.append(args)
        if args[0] == 'inspect': return json.dumps({'id': r.OLD_DEPLOYMENT, 'readyState':'READY'}).encode()
        self.events.append('frontend_'+args[0]); return b''


class ReturnProtocol(unittest.TestCase):
    fixture = fixtures.FinalWriterSafety.fixture
    def return_fixture(self, folder, promoted=False):
        root = Path(folder); remote_root = root/'host'; remote_root.mkdir()
        # Build the original-byte SHA binder with synthetic original files only.
        now, host_run, _, host_gate = self.fixture(remote_root)
        local_root = root/'mac'; local_root.mkdir(); run = local_root/host_run.name; run.mkdir()
        remote = str(w.ROOT/host_run.name)
        gate = {**host_gate, 'phase':'PREWRITE_SOURCE_ROLLBACK', 'run_dir':remote}
        old = str(host_run)
        def replace_path(path): return path.replace(old, remote)
        gate['receipt_hashes'] = {replace_path(p):h for p,h in gate['receipt_hashes'].items()}
        gate['original_host_primary'] = {**gate['original_host_primary'], 'path': replace_path(gate['original_host_primary']['path'])}
        gate['original_host_files'] = {n:{**v, 'path':replace_path(v['path'])} for n,v in gate['original_host_files'].items()}
        for name in ['final_writer_open_once.py','final_prewrite_rollback_once.py','n8n_dashboard_pause_once.py']:
            src=Path(r.__file__).with_name(name); (host_run/name).write_bytes(src.read_bytes()); gate['script_hashes'][name]=w.digest(src)
        private = Path(r.__file__).parents[2]/'.local/hetzner-migration-20261003'
        business = private/'current-evidence/rollback-business-contract-1'
        query = (business/'business-fingerprint.sql').read_bytes()
        tables = [{'table_name':n, 'rows':0, 'sha256':'a'*64} for n in sorted(r.TABLES)]
        original_acl = (private/'source/freeze-business-original-acl.json').read_bytes()
        acl_path = local_root/'source/freeze-business-original-acl.json'; acl_path.parent.mkdir(); acl_path.write_bytes(original_acl)
        values = {'query':query, 'host_primary':(host_run/'original-host-primary.json').read_bytes(),
            'acl_original':original_acl, 'acl_frozen':b'[]', 'acl_restore':Path(r.__file__).with_name('freeze-business-restore-acl.sql').read_bytes(),
            'config':json.dumps([{'space_id':'offline-uuid','enabled':True,'budget':17}]).encode(),
            'scopes_restore':(private/'current-evidence/n8n-scope-plan-1/restore-scopes.sql').read_bytes(),
            'scope_key':json.dumps({'id':'offline-key','scopes':['workflow:read','workflow:activate']}).encode(),
            'frontend':json.dumps({'problem_id':'HZ-MIGRATION-20261003-FINAL-FRONTEND','promotion_attempts':int(promoted),
                'url_env_added':promoted,'anon_env_added':promoted}).encode(), 'frontend_original_env':b'OIDC_UNRELATED=offline-preserved\n',
            'project_link':json.dumps({'projectId':'prj_pWCB8TaGLQesLsT9me0jgT0FqcC5','orgId':'team_xbeBltwkXhOuVc8JUUR0CqoF'}).encode(),
            'nginx_original':b'offline-original-nginx', 'nginx_maintenance':b'offline-maintenance',
            'runtime':(host_run/'target-runtime-receipt.json').read_bytes()}
        front = root/'front'; (front/'.vercel').mkdir(parents=True)
        refs = {}
        for key, body in values.items():
            path = acl_path if key == 'acl_original' else front/'.vercel/project.json' if key == 'project_link' else run/(key+'.primary')
            path.write_bytes(body); refs[key] = {'path':str(path), 'sha256':w.digest(path)}
        refs['host_primary'] = gate['original_host_primary']
        source_raw = run/'frozen-source-primary.json'; source_raw.write_text(json.dumps([{'value':tables}]))
        baseline = {'status':'FROZEN_SOURCE_BUSINESS_BASELINE','problem_id':w.PROBLEM,'run_dir':remote,
            'query_path':refs['query']['path'],'query_sha256':r.QUERY_SHA,'observed_at':now.isoformat(),
            'captured_after_freeze':True,'table_names':sorted(r.TABLES),'tables':tables,
            'primary_response':{'path':str(source_raw),'sha256':w.digest(source_raw)}}
        path=run/'baseline.primary';path.write_text(json.dumps(baseline));refs['baseline']={'path':str(path),'sha256':w.digest(path)}
        proof={'problem_id':w.PROBLEM,'run_dir':remote,'observed_at':now.isoformat(),'refs':refs}
        proof_path=run/'prewrite-source-rollback-proof.json';proof_path.write_text(json.dumps(proof))
        gate['receipt_hashes'].update({v['path']:v['sha256'] for v in refs.values()})
        gate['receipt_hashes'][str(source_raw)]=w.digest(source_raw);gate['receipt_hashes'][str(proof_path)]=w.digest(proof_path)
        gate_path=run/'return-gate.json';gate_path.write_text(json.dumps(gate));(host_run/'prewrite-return-gate.json').write_bytes(gate_path.read_bytes())
        stack = [patch.object(c,'PRIVATE',local_root), patch.object(c,'ERROR_DIR',root/'private-errors'),
                 patch.object(r,'FRONT_BUILD',front), patch.object(r,'NGINX_SHA',w.sha_bytes(values['nginx_original']))]
        for p in stack: p.start();self.addCleanup(p.stop)
        ops=OfflineReturn(run,remote_root,values,tables)
        return now,run,gate_path,gate,proof,ops

    def rewrite(self, run, gate_path, gate, proof):
        proof_path=run/'prewrite-source-rollback-proof.json';proof_path.write_text(json.dumps(proof))
        gate['receipt_hashes'][str(proof_path)]=w.digest(proof_path);gate_path.write_text(json.dumps(gate))
        # Explicit matching host gate copy is primary input; no automatic overwrite in production.

    def test_entrypoint_denies_incomplete_or_different_business_before_mutation(self):
        for fault in ['baseline','missing','extra','source_diff','target_diff','writer','hostmissing','hostwrong','stale']:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                now,run,gp,gate,proof,ops=self.return_fixture(folder)
                if fault=='baseline': Path(proof['refs']['baseline']['path']).unlink()
                elif fault=='missing':ops.source_tables=ops.tables[:-1]
                elif fault=='extra':ops.target_tables=ops.tables+[{'table_name':'unexpected','rows':0,'sha256':'a'*64}]
                elif fault=='source_diff':ops.source_tables=[{**v,'sha256':'b'*64} for v in ops.tables]
                elif fault=='target_diff':ops.target_tables=[{**v,'rows':1} for v in ops.tables]
                elif fault=='writer':ops.marker=True
                elif fault=='hostmissing':gate['original_host_files'].pop('service.env');gp.write_text(json.dumps(gate))
                elif fault=='hostwrong':(ops.remote_root/run.name/'host-runtime-original/service.env').write_text('tampered')
                else:gate['expires_at']=(now-dt.timedelta(seconds=1)).isoformat();gp.write_text(json.dumps(gate))
                with self.assertRaises(w.PreconditionsError):r.execute(run,gp,ops,now)
                self.assertEqual(ops.events,[])
                self.assertFalse((run/'prewrite-source-return-attempt.marker').exists())

    def test_full_return_both_frontend_branches_and_exact_original_files(self):
        for promoted in [False,True]:
            with self.subTest(promoted=promoted), tempfile.TemporaryDirectory() as folder:
                now,run,gp,gate,proof,ops=self.return_fixture(folder,promoted)
                key=json.loads(ops.values['scope_key']);scope_calls=[]
                def n8n(query):
                    scope_calls.append(query)
                    return json.dumps(key['scopes']) if query.startswith('SELECT scopes') else ''
                with patch.object(c,'n8n_sql',side_effect=n8n):r.execute(run,gp,ops,now)
                self.assertEqual(ops.events[:8],['maintenance','stop','host','acl','config','source_start','health','ingress'])
                self.assertIn('resume_three',ops.events)
                for name in w.HOST_FILES:
                    original=ops.read(gate['original_host_files'][name]['path'])
                    self.assertEqual((ops.live/('.local/service.env' if name=='service.env' else name)).read_bytes(),original)
                self.assertFalse((ops.live/'.local/selfhost-backup.json').exists())
                self.assertEqual(ops.acl,json.loads(ops.values['acl_original']));self.assertEqual(ops.config,json.loads(ops.values['config']))
                self.assertEqual(scope_calls[0],ops.values['scopes_restore'].decode())
                cli=[x for x in ops.commands if isinstance(x,list)]
                self.assertEqual([x[1] for x in cli if x[0]=='inspect'],sorted(w.ALIASES))
                self.assertEqual([x for x in cli if x[0]=='rollback'],[['rollback',r.OLD_DEPLOYMENT,'--yes','--timeout','3m']] if promoted else [])
                removed=[x[2] for x in cli if x[:2]==['env','rm']]
                self.assertEqual(removed,['VITE_SUPABASE_URL','VITE_SUPABASE_ANON_KEY'] if promoted else [])
                self.assertTrue(all('OIDC' not in str(x) for x in cli))

    def test_failed_activation_and_health_stop_with_private_primary(self):
        for fault in ['activation','health']:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                now,run,gp,gate,proof,ops=self.return_fixture(folder);ops.fail=fault
                with self.assertRaises(w.PreconditionsError):r.execute(run,gp,ops,now)
                self.assertNotIn('ingress',ops.events);self.assertNotIn('resume_three',ops.events)
                self.assertEqual(ops.events[-2:],['maintenance','stop'])
                errors=list(c.ERROR_DIR.glob('*.json'));self.assertTrue(errors)
                raw=json.loads(errors[0].read_text())
                self.assertEqual(base64.b64decode(raw['stdout']['base64']), b'full-output-private' if fault=='activation' else b'health-private')
                self.assertEqual(base64.b64decode(raw['stderr']['base64']), b'full-stderr-private' if fault=='activation' else b'health-stderr')
                self.assertEqual(errors[0].stat().st_mode&0o777,0o600)
                self.assertEqual(c.ERROR_DIR.stat().st_mode&0o777,0o700)

    def test_source_management_retains_raw_body_before_decode_error(self):
        with tempfile.TemporaryDirectory() as folder:
            run=Path(folder);ops=r.MacReturnOperations(run)
            response=Mock();response.read.return_value=b'complete-private-malformed-body'
            response.status=200;response.headers={'Sensitive':'original-private-header'}
            context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock(return_value=False)
            with patch.object(c,'ERROR_DIR',run/'private-errors'),patch.object(c,'source_token',return_value='offline-token'),patch.object(c.urllib.request,'urlopen',return_value=context),self.assertRaises(RuntimeError):
                ops.source_sql('SELECT offline_only')
            original=json.loads(next(run.glob('source-query-*.json')).read_text())
            self.assertEqual(base64.b64decode(original['body_b64']),b'complete-private-malformed-body')
            self.assertEqual(original['headers'],[['Sensitive','original-private-header']])
            self.assertEqual(next(run.glob('source-query-*.json')).stat().st_mode&0o777,0o600)

    def test_writer_pre_and_postmarker_full_error_and_private_fallback(self):
        for marked in [False,True]:
            with self.subTest(marked=marked), tempfile.TemporaryDirectory() as folder:
                root=Path(folder);now,run,gp,gate=self.fixture(root)
                actual=w.re.fullmatch; native_root=str(w.ROOT)
                def mapped(pattern,value,*a,**kw):return actual(pattern.replace(native_root,str(root)),value,*a,**kw)
                ops=Mock()
                err=urllib.error.HTTPError('https://offline.invalid',503,'offline',{'Sensitive':'private-header'},io.BytesIO(b'complete-private-http-body'))
                if marked:ops.open_writer.side_effect=err
                else:ops.preflight.side_effect=err
                with patch.object(w,'ROOT',root),patch.object(w.re,'fullmatch',side_effect=mapped),self.assertRaises(w.PreconditionsError):w.execute(run,gp,ops,now)
                errors=list((run/'writer-private-errors').glob('*.json'));self.assertTrue(errors)
                primary=json.loads(errors[-1].read_text())
                ops.preflight.assert_called_once()
                self.assertEqual(base64.b64decode(primary['body_b64']),b'complete-private-http-body')
                self.assertEqual(primary['status'],503);self.assertEqual(primary['headers'],[['Sensitive','private-header']])
                self.assertEqual(errors[-1].stat().st_mode&0o777,0o600)
                self.assertEqual((run/'writer-open-attempt.marker').exists(),marked)
                if marked:ops.hold_maintenance.assert_called_once()
                else:ops.open_writer.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(w.tempfile,'mkdtemp',return_value=folder):
                path=Path(w.private_failure(Path(folder)/'missing',subprocess.TimeoutExpired('offline',3,b'full-timeout',b'full-error')))
            value=json.loads(path.read_text());self.assertEqual(base64.b64decode(value['stdout_b64']),b'full-timeout')
            self.assertEqual(value['timeout'],3);self.assertEqual(path.stat().st_mode&0o777,0o600)


if __name__=='__main__':unittest.main()
