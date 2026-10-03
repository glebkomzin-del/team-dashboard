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
            root = Path(temp); run = root/'final-export-offline'; run.mkdir(mode=0o700)
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
        owner_tree = ast.parse((OPS/'final_owner_link_once.py').read_text())
        guard = next(node for node in ast.walk(owner_tree) if isinstance(node, ast.Assert) and
                     {'MEMORY_QA_ENABLED', 'MEMORY_READ_ONLY'}.issubset({item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str)}))
        check = compile(ast.fix_missing_locations(ast.Module(body=[guard], type_ignores=[])), '<owner-readonly-guard>', 'exec')
        exec(check, {'cfg': EXPECTED})
        for key, value in EXPECTED.items():
            with self.subTest(owner_flag=key), self.assertRaises(AssertionError):
                exec(check, {'cfg': {**EXPECTED, key: '0' if value == '1' else '1'}})

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
