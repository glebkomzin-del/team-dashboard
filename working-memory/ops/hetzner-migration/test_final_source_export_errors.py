"""Primary error preservation through actual immutable export helper and final CLI."""
import base64, importlib.util, json, os, subprocess, tempfile, types, unittest
from pathlib import Path
from unittest.mock import Mock, patch
import final_export_once as export
import final_phase_common as common

OPS=Path(__file__).resolve().parent
SECRET=b'synthetic-private-original\x00\xff'

class ExportErrors(unittest.TestCase):
    def record(self,error,root):
        self.assertNotIn('synthetic-private',str(error))
        files=list((root/'errors').glob('*.json'));self.assertEqual(len(files),1)
        self.assertEqual(files[0].stat().st_mode&0o777,0o600)
        self.assertEqual(files[0].parent.stat().st_mode&0o777,0o700)
        return json.loads(files[0].read_text())
    def original(self,root):
        spec=importlib.util.spec_from_file_location('fixture_immutable_source',OPS/'export_source.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        mod.ROOT=root;mod.LINK=root/'pooler-url'
        mod.LINK.write_text('postgres://postgres.lghwikeotbkmojyyjglz@fixture.invalid:5432/postgres')
        (root/'login-role.json').write_text(json.dumps({'role':'fixture-readonly','password':'synthetic-private-password','ttl_seconds':600}))
        (root/'prod-ca-2021.crt').write_text('fixture-ca')
        return mod
    def test_actual_imported_helper_timeouts_psql_dump_dumpall_no_retry(self):
        for executable in ['psql','pg_dump','pg_dumpall']:
            with self.subTest(executable=executable),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);mod=self.original(root);calls=[]
                def run(args,**kw):
                    calls.append(args[0])
                    if args[0]==executable:
                        if hasattr(kw.get('stdout'),'write'):kw['stdout'].write(b'PGDMP retained partial archive')
                        raise subprocess.TimeoutExpired(args,kw['timeout'],output=SECRET,stderr=SECRET+b' stderr')
                    if args[0]=='psql':
                        facts={'current_user':'supabase_read_only_user','read_only':'on','public_writable':0,'public_readable':1,'public_tables':1,'auth_readable':1,'auth_tables':1}
                        return subprocess.CompletedProcess(args,0,json.dumps(facts),'')
                    kw['stdout'].write(b'PGDMP original complete file');return subprocess.CompletedProcess(args,0,None,b'normal stderr')
                mod.subprocess=export.PrivateExportProcesses(types.SimpleNamespace(run=run,PIPE=subprocess.PIPE))
                with patch.object(common,'ERROR_DIR',root/'errors'),patch('builtins.print'),patch('subprocess.run',side_effect=AssertionError('Global subprocess unchanged')),patch('urllib.request.urlopen',side_effect=AssertionError('No lease permitted')):
                    with self.assertRaises(RuntimeError) as raised:mod.main()
                record=self.record(raised.exception,root)
                self.assertEqual(base64.b64decode(record['stdout']['base64']),SECRET)
                self.assertEqual(base64.b64decode(record['stderr']['base64']),SECRET+b' stderr')
                self.assertEqual(calls,['psql','pg_dump','pg_dumpall'][:['psql','pg_dump','pg_dumpall'].index(executable)+1])
                if executable!='psql':
                    target=root/('full.dump' if executable=='pg_dump' else 'roles.sql')
                    self.assertEqual(record['stdout_path'],str(target));self.assertEqual(record['stdout_bytes'],target.stat().st_size)
                    self.assertTrue((root/'full.dump').exists())
    def test_normal_failed_return_preserves_original_helper_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);mod=self.original(root)
            transport=types.SimpleNamespace(run=Mock(return_value=subprocess.CompletedProcess([],7,'original stdout','original stderr')),PIPE=subprocess.PIPE)
            mod.subprocess=export.PrivateExportProcesses(transport)
            with patch.object(common,'ERROR_DIR',root/'errors'),patch('builtins.print'):
                with self.assertRaises(SystemExit):mod.main()
            transport.run.assert_called_once()
            self.assertEqual(json.loads(next(root.glob('connection-failure-*')).read_text())['stderr'],'original stderr')
            self.assertEqual(json.loads(next((root/'errors').iterdir()).read_text())['stdout'],'original stdout')
    def test_final_entry_version_toc_archive_vault_primary_errors(self):
        for operation in ['version','toc','archive','vault']:
            for failure in ['return','timeout']:
                with self.subTest(operation=operation,failure=failure),tempfile.TemporaryDirectory() as temp:
                    root=Path(temp);private=root/'private';(private/'source').mkdir(parents=True)
                    (private/'source/prod-ca-2021.crt').write_text('fixture-ca')
                    (root/'freeze-receipt.json').write_text(json.dumps({'status':'FROZEN','run_dir':'fixture-remote'}))
                    calls=[]
                    def run(args,**kw):
                        op='version' if '--version' in args else 'toc' if '--list' in args else 'vault' if '--data-only' in args else 'archive'
                        calls.append(op)
                        if op==operation:
                            if hasattr(kw.get('stderr'),'write'):kw['stderr'].write(SECRET)
                            if failure=='timeout':raise subprocess.TimeoutExpired(args,kw.get('timeout'),output=SECRET,stderr=SECRET+b' stderr')
                            return subprocess.CompletedProcess(args,9,SECRET,None if hasattr(kw.get('stderr'),'write') else SECRET+b' stderr')
                        return subprocess.CompletedProcess(args,0,b'pg_dump (PostgreSQL) 17.10' if op=='version' else b'fixture TOC',b'')
                    def source_main():
                        (root/'full.dump').write_bytes(b'PGDMP original fixture archive')
                        for name in ['dump-result.json','roles-result.json']:(root/name).write_text('{"returncode":0}')
                        (root/'role-validation.json').write_text(json.dumps({'roles':[{'bypassrls':True}],'read_only':'on','public_writable':0}))
                    mod=types.SimpleNamespace(main=source_main)
                    spec=types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda m:None))
                    response=Mock();response.read.return_value=b'{"role":"fixture-readonly","password":"fixture-private","ttl_seconds":600}'
                    response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
                    transport=types.SimpleNamespace(run=run,PIPE=subprocess.PIPE)
                    with patch.object(common,'ERROR_DIR',root/'errors'),patch.object(export,'PRIVATE',private),patch.object(export,'paths',return_value=(root,'fixture-remote')),patch.object(export,'gate_check',return_value={}),patch.object(export,'shell',return_value=b'false'),patch.object(export,'source_token',return_value='fixture-private'),patch.object(export,'metadata',return_value={'vault':[]}),patch.object(export,'processes',export.PrivateExportProcesses(transport)),patch.object(export.importlib.util,'spec_from_file_location',return_value=spec),patch.object(export.importlib.util,'module_from_spec',return_value=mod),patch('urllib.request.urlopen',return_value=response) as lease,patch('subprocess.run',side_effect=AssertionError('No global process')),patch.dict(os.environ,{},clear=False),patch('sys.argv',['export','--name','final-export-20261003T220500Z','--gate-receipt','fixture']),patch('builtins.print'):
                        with self.assertRaises((RuntimeError,AssertionError)) as raised:export.main()
                        self.assertEqual(lease.call_count,0 if operation=='version' else 1)
                    record=self.record(raised.exception,root)
                    if failure=='timeout' or operation!='archive':
                        self.assertEqual(base64.b64decode(record['stdout']['base64']),SECRET)
                        self.assertEqual(base64.b64decode(record['stderr']['base64']),SECRET+b' stderr')
                    else:
                        self.assertEqual(Path(record['stderr_path']).read_bytes(),SECRET)
                        self.assertEqual(record['stderr_bytes'],len(SECRET))
                    self.assertEqual(calls,['version','toc','archive','vault'][:['version','toc','archive','vault'].index(operation)+1])
                    attempt=json.loads((root/'final-export-attempt.json').read_text());self.assertEqual(attempt['lease_budget'],1);self.assertEqual(attempt['dump_budget'],1)
                    if operation!='version':self.assertEqual((root/'full.dump').read_bytes(),b'PGDMP original fixture archive')
                    self.assertFalse((root/'final-export-receipt.json').exists())

if __name__=='__main__':unittest.main(verbosity=2)
