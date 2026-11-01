"""Pure offline contract tests. Import must never invoke providers or subprocesses."""
import ast
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.parse
import urllib.request

OPS = Path(__file__).resolve().parent
PROJECT = OPS.parents[2]
CONTRACT = PROJECT/'working-memory/.local/hetzner-migration-20261003/current-evidence/runtime-contract-1'
NAMES = ['final_target_runtime_once.py', 'final_restore_once.py', 'frontend-final-promote-once.py',
         'final_owner_link_once.py', 'n8n_dashboard_pause_once.py']
SECRET = 'SyntheticPrivateSecret-DoNotPublish'
EXPECTED = {'MEMORY_READ_ONLY': '1', 'MEMORY_INTAKE_ENABLED': '0', 'MEMORY_AUTOMATIC_ENABLED': '0',
            'MEMORY_QA_ENABLED': '0', 'MEMORY_ORIGINAL_DELETION_ENABLED': '0'}


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), OPS/name)
    module = importlib.util.module_from_spec(spec)
    with patch('subprocess.run', side_effect=AssertionError('Forbidden subprocess during import')), \
         patch('subprocess.Popen', side_effect=AssertionError('Forbidden Popen during import')), \
         patch('subprocess.check_output', side_effect=AssertionError('Forbidden CLI during import')), \
         patch('urllib.request.urlopen', side_effect=AssertionError('Forbidden HTTP during import')):
        spec.loader.exec_module(module)
    return module


class PrivateProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = {name: load(name) for name in NAMES}

    def captured(self, error, directory):
        outward = str(error)
        self.assertNotIn(SECRET, outward)
        receipt = json.loads(outward)
        self.assertEqual(set(receipt), {'kind', 'private_path', 'operation'})
        path = Path(receipt['private_path'])
        self.assertEqual(path.parent, directory)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(path.stem), 32)
        return json.loads(path.read_text())

    def test_process_failures_and_timeout_exact_private_capture_one_attempt(self):
        for name, module in self.modules.items():
            with self.subTest(helper=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)/'private'
                stdout = (SECRET+' stdout\x00').encode()
                stderr = (SECRET+' stderr\n').encode()
                failed = subprocess.CompletedProcess(['private-argv-'+SECRET], 19, stdout, stderr)
                with patch.object(subprocess, 'run', return_value=failed) as run:
                    with self.assertRaises(RuntimeError) as raised:
                        module.run_process(['private-argv-'+SECRET], operation='offline-process', private_errors=directory)
                    run.assert_called_once()
                record = self.captured(raised.exception, directory)
                self.assertEqual(base64.b64decode(record['stdout_b64']), stdout)
                self.assertEqual(base64.b64decode(record['stderr_b64']), stderr)
                self.assertEqual(record['status'], 19)
                original = next(directory.iterdir()).read_bytes()
                timeout = subprocess.TimeoutExpired(['private-argv-'+SECRET], 2, output=stdout, stderr=stderr)
                with patch.object(subprocess, 'run', side_effect=timeout) as run:
                    with self.assertRaises(RuntimeError) as raised:
                        module.run_process(['private-argv-'+SECRET], operation='offline-timeout', private_errors=directory)
                    run.assert_called_once()
                record = self.captured(raised.exception, directory)
                self.assertEqual(base64.b64decode(record['stdout_b64']), stdout)
                self.assertEqual(base64.b64decode(record['stderr_b64']), stderr)
                self.assertEqual(record['exception_type'], 'TimeoutExpired')
                self.assertIn(SECRET, record['exception_text'])
                self.assertEqual(len(list(directory.iterdir())), 2)
                self.assertIn(original, [file.read_bytes() for file in directory.iterdir()])

    def test_success_returns_exact_output_without_logging_secret_stdin(self):
        for name, module in self.modules.items():
            with self.subTest(helper=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)/'private'
                output = SECRET+' successful response'
                with patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')) as run:
                    self.assertEqual(module.run_process(['mock'], operation='offline-success', private_errors=directory,
                                                        input=SECRET, text=True), output)
                    run.assert_called_once()
                    self.assertEqual(run.call_args.kwargs['input'], SECRET)
                self.assertFalse(directory.exists())

    def test_real_runtime_and_frontend_wrappers_preserve_diagnostics(self):
        runtime = self.modules[NAMES[0]]; frontend = self.modules[NAMES[2]]
        for module, invoke in [(runtime, lambda: runtime.call(['mock'])),
                               (frontend, lambda: frontend.cli(['env', 'add'], SECRET+'\n'))]:
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)/'private'
                with patch.object(module, 'PRIVATE_ERRORS', directory), patch.object(frontend, 'PRIVATE', Path(temp)), \
                     patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, SECRET, SECRET)) as run:
                    with self.assertRaises(RuntimeError) as raised: invoke()
                    run.assert_called_once()
                actual_dir = Path(temp)/'private-errors' if module is frontend else directory
                record = self.captured(raised.exception, actual_dir)
                self.assertEqual(base64.b64decode(record['stderr_b64']).decode(), SECRET)

    def test_http_primary_body_status_headers_and_exception_are_private(self):
        for name, module in self.modules.items():
            with self.subTest(helper=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)/'private'
                headers = {'Set-Cookie': SECRET, 'X-Original': 'original-header'}
                body = (SECRET+' HTTP body').encode()
                error = urllib.error.HTTPError('https://invalid.example/'+SECRET, 503, SECRET, headers, io.BytesIO(body))
                request = urllib.request.Request('https://invalid.example/', data=b'private', method='POST')
                with patch('urllib.request.urlopen', side_effect=error) as fetch:
                    with self.assertRaises(RuntimeError) as raised:
                        module.http_read(request, operation='offline-http', private_errors=directory)
                    fetch.assert_called_once()
                record = self.captured(raised.exception, directory)
                self.assertEqual(base64.b64decode(record['body_b64']), body)
                self.assertEqual(record['status'], 503)
                self.assertEqual(dict(record['headers']), headers)
                self.assertEqual(record['method'], 'POST')
                self.assertEqual(record['exception_type'], 'HTTPError')
                self.assertIn(SECRET, record['exception_text'])

    def test_http_success_and_n8n_original_body_preservation(self):
        for name, module in self.modules.items():
            with self.subTest(helper=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)/'private'
                body = ('{ "original": "'+SECRET+'" }').encode()
                response = Mock(status=200, headers={'X-Original': 'keep'})
                response.read.return_value = body
                response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
                preserve = name == 'n8n_dashboard_pause_once.py'
                with patch('urllib.request.urlopen', return_value=response) as fetch:
                    result = module.http_read('https://invalid.example/', operation='offline-http-success',
                                              private_errors=directory, preserve_success=preserve)
                    fetch.assert_called_once()
                self.assertEqual(result, (body, 200, response.headers))
                if preserve:
                    path = next(directory.iterdir()); self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(base64.b64decode(json.loads(path.read_text())['body_b64']), body)
                else: self.assertFalse(directory.exists())

    def test_n8n_partial_change_receipt_and_original_http_body_survive_failure(self):
        module = self.modules['n8n_dashboard_pause_once.py']
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); run = root/'final-export-offline'; run.mkdir(mode=0o700)
            access = root/'n8n-pause-access-1'; access.mkdir(mode=0o700)
            (access/'existing-api-key-private.json').write_text(json.dumps({'apiKey':SECRET}))
            gate = root/'gate.json'
            gate.write_text(json.dumps({'problem_id':'HZ-MIGRATION-20261003-FINAL-CUTOVER',
                                       'decision':'CONTINUE_BOUNDED','run_dir':str(run)}))
            workflows = list(module.VERSIONS)
            bodies = [json.dumps({'active':True,'activeVersionId':module.VERSIONS[w], 'original':SECRET}).encode() for w in workflows]
            bodies += [b'{ "active": false, "original": "'+SECRET.encode()+b'" }', b'{"active":false}']
            responses=[]
            for body in bodies:
                response=Mock(status=200, headers={'X-Original':SECRET})
                response.read.return_value=body
                response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
                responses.append(response)
            original_error=(SECRET+' partial failure original body').encode()
            responses.append(urllib.error.HTTPError('http://invalid/',503,SECRET,{'X-Original':SECRET},io.BytesIO(original_error)))
            with patch.object(module,'ROOT',root), patch('sys.argv',['offline','--action','pause','--run-dir',str(run),'--gate-receipt',str(gate)]), \
                 patch('urllib.request.urlopen',side_effect=responses) as fetch, patch('builtins.print') as outward:
                with self.assertRaises(SystemExit) as raised:module.main()
                self.assertEqual(raised.exception.code,1)
                self.assertEqual(fetch.call_count,6)
                self.assertNotIn(SECRET,str(outward.call_args))
            receipt=json.loads((run/'n8n-pause-receipt.json').read_text())
            self.assertEqual(receipt['changed'],workflows[:1])
            self.assertEqual(receipt['attempted'],workflows[:2])
            self.assertEqual(receipt['status'],'FAILED')
            self.assertNotIn(SECRET,json.dumps(receipt))
            records=[json.loads(file.read_text()) for file in (run/'private-errors').iterdir()]
            captured=[base64.b64decode(record['body_b64']) for record in records if record['body_b64'] is not None]
            for body in bodies+[original_error]:self.assertIn(body,captured)

    def test_fingerprint_failed_stream_keeps_whole_original_stdout_stderr(self):
        module = self.modules['final_restore_once.py']
        stdout = b'COPY public.example (value) FROM stdin;\n'+SECRET.encode()+b'\n\\.\n'
        stderr = (SECRET+' pg_restore original failure').encode()
        proc = types.SimpleNamespace(stdout=io.BytesIO(stdout), stderr=io.BytesIO(stderr), wait=Mock(return_value=3))
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)/'private'
            with self.assertRaises(RuntimeError) as raised: module.fp(proc, directory)
            record = self.captured(raised.exception, directory)
            self.assertEqual(base64.b64decode(record['stdout_b64']), stdout)
            self.assertEqual(base64.b64decode(record['stderr_b64']), stderr)
            proc.wait.assert_called_once()

    def test_fingerprint_success_remains_order_independent_and_no_private_log(self):
        module = self.modules['final_restore_once.py']
        results = []
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)/'private'
            for rows in [b'first\nsecond\n', b'second\nfirst\n']:
                stdout = b'COPY public.example (value) FROM stdin;\n'+rows+b'\\.\n'
                proc = types.SimpleNamespace(stdout=io.BytesIO(stdout), stderr=io.BytesIO(b''), wait=Mock(return_value=0))
                results.append(module.fp(proc, directory)); proc.wait.assert_called_once()
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[0]['public.example']['rows'], 2)
            self.assertFalse(directory.exists())

    def test_five_flags_reject_each_open_host_and_container_value(self):
        runtime = self.modules['final_target_runtime_once.py']
        self.assertEqual(runtime.CLOSED_FLAGS, EXPECTED)
        runtime.closed_flags(EXPECTED)
        runtime.verify_container_flags({'Config': {'Env': [key+'='+value for key, value in EXPECTED.items()]}})
        for key, value in EXPECTED.items():
            wrong = {**EXPECTED, key: '0' if value == '1' else '1'}
            with self.subTest(flag=key):
                with self.assertRaises(AssertionError): runtime.closed_flags(wrong)
                with self.assertRaises(AssertionError):
                    runtime.verify_container_flags({'Config': {'Env': [key+'='+value for key, value in wrong.items()]}})
        self.assertEqual(self.modules['final_owner_link_once.py'].CLOSED_FLAGS, EXPECTED)

    def test_actual_image_server_ast_blocks_post_paths_and_deletion_startup(self):
        raw = (CONTRACT/'live-server.py').read_bytes()
        receipt = json.loads((CONTRACT/'receipt.json').read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt['server_py_sha256'])
        self.assertEqual(receipt['server_py_sha256'], self.modules[NAMES[0]].SERVER_SHA)
        self.assertEqual(receipt['image'], self.modules[NAMES[0]].BASE)
        tree = ast.parse(raw)
        names = {'READ_ONLY': 'MEMORY_READ_ONLY', 'INTAKE_ENABLED': 'MEMORY_INTAKE_ENABLED',
                 'AUTOMATIC_ENABLED': 'MEMORY_AUTOMATIC_ENABLED', 'QA_ENABLED': 'MEMORY_QA_ENABLED',
                 'ORIGINAL_DELETION_ENABLED': 'MEMORY_ORIGINAL_DELETION_ENABLED'}
        assignments = [node for node in tree.body if isinstance(node, ast.Assign) and
                       any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
        env = {'os': types.SimpleNamespace(environ=EXPECTED)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=assignments, type_ignores=[])), '<actual-image-flags>', 'exec'), env)
        self.assertEqual({key:env[key] for key in names}, {key: value=='MEMORY_READ_ONLY' for key,value in names.items()})
        post = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'do_POST')
        env.update(urlparse=urllib.parse.urlparse, AuthUnavailable=type('AuthUnavailable', (Exception,), {}),
                   CONVERSATIONS=Mock(), QUESTION_SERVICE=Mock(), QUESTION_JOBS=Mock(), JOURNAL=Mock())
        exec(compile(ast.fix_missing_locations(ast.Module(body=[post], type_ignores=[])), '<actual-image-post>', 'exec'), env)
        for route, status in [('/conversations',404), ('/questions',405), ('/source-deletions',404), ('/sources',405)]:
            handler=types.SimpleNamespace(path=route, authorized=lambda:True, send_json=lambda status,body:(status,body))
            self.assertEqual(env['do_POST'](handler)[0], status)
        env['CONVERSATIONS'].create.assert_not_called(); env['QUESTION_JOBS'].submit.assert_not_called()
        startup = next(node for node in ast.walk(tree) if isinstance(node, ast.If) and
                       isinstance(node.test, ast.Name) and node.test.id == 'ORIGINAL_DELETION_ENABLED' and
                       any(isinstance(item, ast.Raise) for item in ast.walk(node)))
        check = compile(ast.fix_missing_locations(ast.Module(body=[startup], type_ignores=[])), '<actual-image-startup>', 'exec')
        exec(check, env)  # Closed deletion skips all startup side effects.
        env['ORIGINAL_DELETION_ENABLED']=True
        with self.assertRaises(SystemExit): exec(check, env)


class ReviewedProtocolRegression(unittest.TestCase):
    def test_existing_owner_main_original_link_and_password_unchanged_one_request(self):
        module=load('final_owner_link_once.py')
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary).resolve();root=base/'target';root.mkdir();live=base/'live';(live/'.local').mkdir(parents=True)
            run=root/'final-export-20261003T220500Z';run.mkdir(mode=0o700)
            (run/'target-runtime-receipt.json').write_text(json.dumps({'status':'TARGET_READONLY_RUNTIME_ACTIVE'}))
            uid='00000000-0000-0000-0000-000000000001'
            (live/'.local/service.env').write_text(''.join(k+'='+v+'\n' for k,v in EXPECTED.items())+'MEMORY_ALLOWED_USERS='+uid+'\n')
            (root/'.private.env').write_text("SERVICE_ROLE_KEY='fixture-private-api-key'\n")
            owner={'id':uid,'email':'owner@fixture.invalid','encrypted_password':'fixture-unchanged-verifier'}
            link=module.TARGET+'/auth/v1/verify?'+urllib.parse.urlencode({'type':'magiclink','redirect_to':module.REDIRECT,'token':'fixture-original-token'})
            body=json.dumps({'id':uid,'verification_type':'magiclink','redirect_to':module.REDIRECT,'action_link':link}).encode()
            with patch.object(module,'ROOT',root),patch.object(module,'LIVE',live),patch.object(module,'run_process',side_effect=[json.dumps(owner),json.dumps(owner)]) as sql,patch.object(module,'http_read',return_value=(body,200,{})) as fetch,patch('sys.argv',['owner','--run-dir',str(run),'--production-owner-go','HZ-MIGRATION-20261003-FINAL-FRONTEND']),patch('builtins.print'):
                module.main()
                self.assertEqual(sql.call_count,2);fetch.assert_called_once()
                request=fetch.call_args.args[0];self.assertEqual(request.get_method(),'POST')
                self.assertEqual(json.loads(request.data),{'type':'magiclink','email':owner['email'],'redirect_to':module.REDIRECT})
            self.assertEqual((run/'owner-original-action-link-private.txt').read_text(),link)
            self.assertEqual((run/'owner-original-action-link-private.txt').stat().st_mode&0o777,0o600)
            self.assertTrue(json.loads((run/'owner-link-receipt.json').read_text())['owner_password_hash_unchanged'])
            self.assertTrue((run/'owner-magiclink-attempt.marker').exists())
            # Real main must reject every open flag before SQL, token issuance or marker changes.
            for key,value in EXPECTED.items():
                cfg={**EXPECTED,key:'0' if value=='1' else '1'}
                (live/'.local/service.env').write_text(''.join(k+'='+v+'\n' for k,v in cfg.items())+'MEMORY_ALLOWED_USERS='+uid+'\n')
                with self.subTest(owner_open_flag=key),patch.object(module,'ROOT',root),patch.object(module,'LIVE',live),patch.object(module,'run_process',side_effect=AssertionError('Forbidden SQL')) as sql,patch.object(module,'http_read',side_effect=AssertionError('Forbidden token issuance')) as fetch,patch('sys.argv',['owner','--run-dir',str(run),'--production-owner-go','HZ-MIGRATION-20261003-FINAL-FRONTEND']):
                    with self.assertRaises(AssertionError):module.main()
                    sql.assert_not_called();fetch.assert_not_called()


    def test_delayed_health_only_get_observations_preserve_original_failures(self):
        module=load('final_target_runtime_once.py')
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'private';response=Mock(status=200,headers={});response.read.return_value=b'{"status":"ok"}'
            response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            with patch.object(module,'PRIVATE_ERRORS',directory),patch('urllib.request.urlopen',side_effect=[urllib.error.URLError(SECRET),response]) as get,patch('subprocess.run',side_effect=AssertionError('No repeated start')),patch('time.monotonic',side_effect=[0,1]),patch('time.sleep') as sleep:
                self.assertEqual(module.observe_runtime_health(seconds=90),{'status':'ok'})
                self.assertEqual(get.call_count,2);sleep.assert_called_once_with(2)
                self.assertTrue(all(call.args[0]=='http://127.0.0.1:8798/health' for call in get.call_args_list))
            records=[json.loads(x.read_text()) for x in directory.iterdir()]
            self.assertEqual(len(records),1);self.assertEqual(records[0]['method'],'GET');self.assertIn(SECRET,records[0]['exception_text'])

    def test_health_deadline_preserves_error_and_does_not_open_ingress(self):
        module=load('final_target_runtime_once.py')
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'private'
            with patch.object(module,'PRIVATE_ERRORS',directory),patch('urllib.request.urlopen',side_effect=urllib.error.URLError(SECRET)) as get,patch.object(module,'atomic',side_effect=AssertionError('No ingress opening')) as ingress,patch('subprocess.run',side_effect=AssertionError('No start')),patch('time.monotonic',side_effect=[0,91]),patch('time.sleep') as sleep:
                with self.assertRaises(RuntimeError) as raised:module.observe_runtime_health(seconds=90)
                get.assert_called_once();sleep.assert_not_called();ingress.assert_not_called();self.assertNotIn(SECRET,str(raised.exception))
            self.assertEqual(len(list(directory.iterdir())),1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
