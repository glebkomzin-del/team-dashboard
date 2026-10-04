"""Offline behavioral checks only. Every lease/fact/transport below is synthetic."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import final_phase_common as c
from final_export_once import PrivateExportProcesses
import source_direct_route as r
import source_direct_preflight_once as pre

OPS = Path(__file__).resolve().parent
STAMP = datetime(2026, 10, 4, tzinfo=timezone.utc)
URI = 'postgresql://postgres.' + c.PROJECT + '@aws-0-eu-central-1.pooler.supabase.com:5432/postgres'
SECRET = 'synthetic-password-only-env'


def facts(role='cli_login_postgres_fixture'):
    return {'current_user': 'supabase_read_only_user', 'session_user': role, 'ssl': True,
            'read_only': 'on', 'roles': [{'name': 'supabase_read_only_user', 'bypassrls': True, 'superuser': False}],
            'public_tables': 43, 'public_readable': 43, 'auth_tables': 20, 'auth_readable': 20, 'public_writable': 0}


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / 'private'
        (self.private / 'source').mkdir(parents=True)
        self.ca = self.private / 'source/prod-ca-2021.crt'
        self.ca.write_text('synthetic-ca')
        self.proofs = self.private / 'current-evidence/direct-db-route-1'
        self.proofs.mkdir(parents=True)
        self.proof_names = ('actual-hetzner-direct-db-network.json', 'actual-hetzner-direct-db-tls.json')
        (self.proofs / self.proof_names[0]).write_text(json.dumps({'host': r.HOST, 'addresses': [{'family': 10, 'tcp_connected': True}], 'auth_requests': 0, 'queries': 0}))
        (self.proofs / self.proof_names[1]).write_text(json.dumps({'host': r.HOST, 'tls_verified': True, 'hostname_verified': True, 'tls_version': 'TLSv1.3', 'auth_requests': 0, 'queries': 0}))
        self.run_dir = self.private / 'current-evidence/source-direct-auth-preflight-1'
        self.pooler = self.root / 'pooler-url'
        self.pooler.write_text(URI)
        self.clock = Mock(return_value=STAMP)
        self.gate = {'schema': 'source-direct-gate-v1', 'problem_id': r.PROBLEM,
             'decision': 'CONTINUE_BOUNDED', 'phase': 'SOURCE_DIRECT_AUTH_PREFLIGHT', 'direct_gate': True,
             'run_dir': str(self.run_dir), 'project': c.PROJECT, 'host': r.HOST,
             'hostaddr': '127.0.0.1', 'port': r.PORT, 'sslmode': 'verify-full',
             'ca_sha256': c.digest(self.ca), 'issued_at': STAMP.isoformat(),
             'expires_at': (STAMP + timedelta(seconds=300)).isoformat(), 'lease_budget': 1, 'probe_budget': 1,
             'script_hashes': {f: c.digest(OPS / f) for f in ('source_direct_route.py', 'source_direct_preflight_once.py', 'export_source.py', 'final_phase_common.py', 'final_export_once.py')},
             'proof_hashes': {f: c.digest(self.proofs / f) for f in self.proof_names}}
        self.gate_path = self.root / 'gate.json'
        self.write_gate()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(c, 'PRIVATE', self.private))
        self.stack.enter_context(patch.object(c, 'ERROR_DIR', self.root / 'errors'))
        self.stack.enter_context(patch.object(pre, 'POOLER_LINK', self.pooler))
        # Any accidentally unmocked actual transport fails, even on failure branches.
        self.stack.enter_context(patch('subprocess.run', side_effect=AssertionError('real subprocess forbidden')))
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('real child forbidden')))
        self.stack.enter_context(patch('socket.create_connection', side_effect=AssertionError('real network forbidden')))
        self.stack.enter_context(patch('socket.socket', side_effect=AssertionError('real socket forbidden')))
        self.stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('real HTTP forbidden')))

    def write_gate(self):
        self.gate_path.write_text(json.dumps(self.gate))

    def lease(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        value = {'role': 'cli_login_postgres_fixture', 'password': SECRET, 'ttl_seconds': 300,
                 'created_at': STAMP.isoformat(), 'read_only_requested': True}
        (self.run_dir / 'login-role.json').write_text(json.dumps(value))
        self.gate.update(approved_role=value['role'], lease_created_at=value['created_at'], lease_ttl_seconds=300)
        return value

    def direct(self):
        return r.DirectRoute(self.gate, self.run_dir / 'login-role.json', self.ca, URI, self.clock)

    def original(self):
        spec = importlib.util.spec_from_file_location('synthetic_source_export', OPS / 'export_source.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.ROOT = self.run_dir
        module.LINK = self.pooler
        (self.run_dir / 'prod-ca-2021.crt').write_bytes(self.ca.read_bytes())
        return module


class RouteTests(Fixtures):
    def test_original_entry_three_connections_preserves_args_env_archive(self):
        self.lease()
        module = self.original()
        direct = r.DirectRoute(self.gate, self.run_dir / 'login-role.json', self.run_dir / 'prod-ca-2021.crt', URI, self.clock)
        calls = []
        def run(args, **kw):
            calls.append((args, kw))
            if args[0] == 'psql':
                return subprocess.CompletedProcess(args, 0, json.dumps(facts()), '')
            kw['stdout'].write(b'PGDMP synthetic archive' if args[0] == 'pg_dump' else b'synthetic roles without passwords')
            return subprocess.CompletedProcess(args, 0, None, b'full original stderr')
        module.subprocess = r.SourceProcessAdapter(PrivateExportProcesses(types.SimpleNamespace(run=run, PIPE=subprocess.PIPE)), direct)
        with patch('builtins.print'):
            module.main()
        self.assertEqual([a[0] for a, k in calls], ['psql', 'pg_dump', 'pg_dumpall'])
        for args, kw in calls:
            connection = args[2] if args[0] == 'pg_dumpall' else args[1]
            self.assertIn('host=' + r.HOST + ' hostaddr=127.0.0.1 port=15433', connection)
            self.assertIn('user=cli_login_postgres_fixture sslmode=verify-full', connection)
            self.assertIn("sslrootcert='" + str(self.run_dir / 'prod-ca-2021.crt') + "'", connection)
            self.assertNotIn(SECRET, str(args))
            self.assertEqual(kw['env']['PGPASSWORD'], SECRET)
            self.assertEqual(kw['env']['PGOPTIONS'], r.READONLY)
        self.assertIn('--no-role-passwords', calls[2][0])
        self.assertIn('--role=supabase_read_only_user', calls[1][0])
        self.assertEqual((self.run_dir / 'full.dump').read_bytes(), b'PGDMP synthetic archive')
        self.assertEqual(c.digest(OPS / 'export_source.py'), r.EXPORT_SHA)

    def test_each_new_connection_checks_expiry_no_renewal(self):
        for expires_after in ('psql', 'pg_dump'):
            with self.subTest(expires_after=expires_after):
                for f in self.run_dir.glob('*') if self.run_dir.exists() else []: f.unlink()
                self.clock.return_value = STAMP
                self.lease()
                module = self.original()
                direct = r.DirectRoute(self.gate, self.run_dir / 'login-role.json', self.run_dir / 'prod-ca-2021.crt', URI, self.clock)
                calls = []
                def run(args, **kw):
                    calls.append(args[0])
                    if args[0] == expires_after: self.clock.return_value = STAMP + timedelta(seconds=300)
                    if args[0] == 'psql': return subprocess.CompletedProcess(args, 0, json.dumps(facts()), '')
                    kw['stdout'].write(b'PGDMP synthetic')
                    return subprocess.CompletedProcess(args, 0, None, b'')
                module.subprocess = r.SourceProcessAdapter(PrivateExportProcesses(types.SimpleNamespace(run=run, PIPE=subprocess.PIPE)), direct)
                with patch('builtins.print'), self.assertRaisesRegex(RuntimeError, 'LEASE_EXPIRED'): module.main()
                self.assertEqual(calls, ['psql'] if expires_after == 'psql' else ['psql', 'pg_dump'])

    def test_reject_nonexact_source_arguments_and_readonly_changes(self):
        lease = self.lease()
        direct = self.direct()
        env = {'PGPASSWORD': SECRET, 'PGOPTIONS': r.READONLY}
        cert = "'" + str(self.ca) + "'"
        original = 'host=aws-0-eu-central-1.pooler.supabase.com port=5432 dbname=postgres user=' + lease['role'] + '.' + c.PROJECT + ' sslmode=verify-full sslrootcert=' + cert + ' connect_timeout=15'
        for bad in (original.replace('host=', 'hostaddr=', 1), original.replace(c.PROJECT, 'wrongproject'), original.replace('5432', '6543'), original.replace('verify-full', 'require'), original + ' password=synthetic'):
            with self.assertRaises(RuntimeError): direct.rewrite(['psql', bad], env)
        with self.assertRaises(RuntimeError): direct.rewrite(['psql', original], {**env, 'PGOPTIONS': ''})
        with self.assertRaises(RuntimeError): direct.rewrite(['pg_dumpall', '--dbname=' + original], env)
        with self.assertRaises(RuntimeError): r.DirectRoute(self.gate, direct.lease_path, self.ca, URI.replace(c.PROJECT, 'wrong'), self.clock)

    def test_primary_timeout_full_capture_no_retry(self):
        self.lease()
        module = self.original()
        direct = r.DirectRoute(self.gate, self.run_dir / 'login-role.json', self.run_dir / 'prod-ca-2021.crt', URI, self.clock)
        fake = types.SimpleNamespace(run=Mock(side_effect=subprocess.TimeoutExpired('synthetic', 45, output=b'private full stdout', stderr=b'private full stderr')), PIPE=subprocess.PIPE)
        module.subprocess = r.SourceProcessAdapter(PrivateExportProcesses(fake), direct)
        with self.assertRaises(RuntimeError) as caught: module.main()
        self.assertNotIn('private full stdout', str(caught.exception))
        error = json.loads(next((self.root / 'errors').iterdir()).read_text())
        import base64
        self.assertEqual(base64.b64decode(error['stdout']['base64']), b'private full stdout')
        self.assertEqual(base64.b64decode(error['stderr']['base64']), b'private full stderr')
        fake.run.assert_called_once()


class PreflightTests(Fixtures):
    def prepared(self, mode='success'):
        calls = []
        def run(args, **kw):
            calls.append(args)
            if '--version' in args: return subprocess.CompletedProcess(args, 0, b'psql (PostgreSQL) 17.10', b'')
            self.assertEqual(args[0], '/opt/homebrew/bin/psql')
            self.assertIn('BEGIN READ ONLY; SET LOCAL ROLE supabase_read_only_user;', args[-1])
            self.assertTrue(args[-1].endswith('; ROLLBACK;'))
            self.assertEqual(kw['env']['PGOPTIONS'], r.READONLY)
            self.assertEqual(kw['env']['PGPASSWORD'], SECRET)
            self.assertNotIn(SECRET, str(args))
            if mode == 'probe_timeout': raise subprocess.TimeoutExpired(args, 45, output=b'original output', stderr=b'original error')
            value = facts()
            if mode == 'wrong_facts': value['session_user'] = 'postgres'
            return subprocess.CompletedProcess(args, 9 if mode == 'probe_nonzero' else 0, json.dumps(value), 'original probe stderr')
        response = Mock(status=201, headers={'synthetic': 'raw header'})
        response.read.return_value = json.dumps({'role': 'cli_login_postgres_fixture', 'password': SECRET, 'ttl_seconds': 300}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        http = Mock(return_value=response)
        if mode == 'http_timeout': http.side_effect = TimeoutError('synthetic full HTTP primary')
        if mode == 'http_error':
            http.side_effect = __import__('urllib.error', fromlist=['HTTPError']).HTTPError('synthetic', 503, 'unavailable', {'raw': 'header'}, __import__('io').BytesIO(b'full HTTP error body'))
            self.addCleanup(http.side_effect.close)
        tunnel = Mock()
        tunnel.return_value.__enter__ = Mock(return_value=tunnel)
        tunnel.return_value.__exit__ = Mock(return_value=False)
        transport = types.SimpleNamespace(run=Mock(side_effect=run), PIPE=subprocess.PIPE)
        token = Mock(return_value='synthetic-token')
        return calls, transport, http, tunnel, token

    def invoke(self, prepared):
        calls, transport, http, tunnel, token = prepared
        return pre.run(self.gate_path, self.run_dir, transport=transport, http=http,
                       token=token, tunnel_factory=tunnel, clock=self.clock)

    def test_main_success_actual_fact_guard_synthetic_only_single_budget(self):
        prepared = self.prepared()
        calls, transport, http, tunnel, token = prepared
        actual_run = pre.run
        def invoke_main(g, d):
            return actual_run(g, d, transport=transport, http=http, token=token, tunnel_factory=tunnel, clock=self.clock)
        with patch.object(pre, 'run', side_effect=invoke_main), patch('sys.argv', ['preflight', '--gate-receipt', str(self.gate_path), '--run-dir', str(self.run_dir)]), patch('builtins.print') as out:
            pre.main()
        self.assertEqual(json.loads(out.call_args.args[0])['status'], 'PASSED')
        self.assertEqual(len(calls), 2)  # Version observation and exactly one query process.
        http.assert_called_once()
        token.assert_called_once()
        self.assertEqual(http.call_args.args[0].data, b'{"read_only":true}')
        tunnel.return_value.__exit__.assert_called_once()
        self.assertEqual((self.run_dir / 'login-role.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.run_dir.stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.run_dir / 'full.dump').exists())
        with self.assertRaises(FileExistsError): self.invoke(prepared)
        http.assert_called_once()

    def test_before_marker_bad_gate_project_host_port_tls_expiry_code_proof(self):
        changes = [('phase', 'OLD_SOURCE_GOAL'), ('project', 'wrong'), ('host', 'wrong'), ('port', 5432),
                   ('direct_gate', False), ('sslmode', 'require'), ('expires_at', STAMP.isoformat()), ('decision', 'GO')]
        for key, bad in changes:
            with self.subTest(key=key):
                original = self.gate[key]
                self.gate[key] = bad
                self.write_gate()
                prepared = self.prepared()
                with self.assertRaises(RuntimeError): self.invoke(prepared)
                self.assertFalse(self.run_dir.exists())
                for fake in prepared[1:]:
                    if hasattr(fake, 'assert_not_called'): fake.assert_not_called()
                self.gate[key] = original
        for section in ('script_hashes', 'proof_hashes'):
            original = dict(self.gate[section])
            self.gate[section][next(iter(original))] = '0' * 64
            self.write_gate()
            with self.assertRaises(RuntimeError): self.invoke(self.prepared())
            self.assertFalse(self.run_dir.exists())
            self.gate[section] = original
        proof = self.proofs / self.proof_names[1]
        body = json.loads(proof.read_text());body['tls_verified'] = False;proof.write_text(json.dumps(body))
        self.gate['proof_hashes'][proof.name] = c.digest(proof)
        self.write_gate()
        with self.assertRaises(RuntimeError): self.invoke(self.prepared())
        self.assertFalse(self.run_dir.exists())

    def test_failure_budget_full_primary_and_cleanup_no_pass(self):
        for mode in ('wrong_facts', 'probe_nonzero', 'probe_timeout', 'http_timeout', 'http_error'):
            with self.subTest(mode=mode):
                if self.run_dir.exists():
                    for f in self.run_dir.iterdir(): f.unlink()
                if (self.root / 'errors').exists():
                    for f in (self.root / 'errors').iterdir(): f.unlink()
                prepared = self.prepared(mode)
                with self.assertRaises(RuntimeError): self.invoke(prepared)
                prepared[2].assert_called_once()
                prepared[3].return_value.__exit__.assert_called_once()
                self.assertFalse((self.run_dir / 'preflight-passed.json').exists())
                self.assertTrue(list((self.root / 'errors').iterdir()))
                if mode == 'http_error':
                    import base64
                    record = json.loads(next((self.root / 'errors').iterdir()).read_text())
                    self.assertEqual(base64.b64decode(record['body']['base64']), b'full HTTP error body')
                before = prepared[2].call_count
                with self.assertRaises(FileExistsError): self.invoke(prepared)
                self.assertEqual(prepared[2].call_count, before)

    def test_each_fact_boundary(self):
        for key, value in [('ssl', False), ('current_user', 'postgres'), ('session_user', 'postgres'),
                           ('read_only', 'off'), ('public_writable', 1), ('public_readable', 42), ('auth_readable', 19)]:
            value_facts = facts();value_facts[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError): r.check_facts(value_facts, 'cli_login_postgres_fixture')
        value = facts();value['roles'][0]['bypassrls'] = False
        with self.assertRaises(RuntimeError): r.check_facts(value, 'cli_login_postgres_fixture')


class TunnelTests(Fixtures):
    def tunnel(self, occupied=False, popen_failure=False):
        self.run_dir.mkdir(parents=True)
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired('own-child', 3), 0]
        transport = types.SimpleNamespace(Popen=Mock(return_value=child))
        if popen_failure: transport.Popen.side_effect = OSError('synthetic original Popen error')
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)
        if occupied: sock.bind.side_effect = OSError('occupied loopback')
        sockets = types.SimpleNamespace(AF_INET=2, SOCK_STREAM=1, socket=Mock(return_value=sock), create_connection=Mock(return_value=sock))
        return r.OwnedTunnel(self.run_dir, transport=transport, sockets=sockets), child, transport, sockets

    def test_strict_loopback_own_child_cleanup_stream_modes_duplicate(self):
        tunnel, child, transport, sockets = self.tunnel()
        with tunnel:
            with self.assertRaisesRegex(RuntimeError, 'DUPLICATE'): tunnel.__enter__()
        args = transport.Popen.call_args.args[0]
        self.assertIn('127.0.0.1:15433:' + r.HOST + ':5432', args)
        for option in ('StrictHostKeyChecking=yes', 'BatchMode=yes', 'ExitOnForwardFailure=yes', 'ControlPath=none', 'ServerAliveInterval=15', 'ServerAliveCountMax=2'): self.assertIn(option, args)
        self.assertEqual(args[-1], c.SSH[-1])
        self.assertEqual(transport.Popen.call_count, 1)
        child.terminate.assert_called_once();child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)
        for name in ('tunnel.stdout', 'tunnel.stderr'): self.assertEqual((self.run_dir / name).stat().st_mode & 0o777, 0o600)

    def test_port_occupied_denies_before_popen(self):
        tunnel, child, transport, sockets = self.tunnel(occupied=True)
        with self.assertRaises(RuntimeError): tunnel.__enter__()
        transport.Popen.assert_not_called()
        child.terminate.assert_not_called()
        self.assertIn('occupied loopback', next((self.root / 'errors').iterdir()).read_text())

    def test_popen_error_private_primary_and_no_duplicate_child(self):
        tunnel, child, transport, sockets = self.tunnel(popen_failure=True)
        with self.assertRaises(RuntimeError) as caught: tunnel.__enter__()
        self.assertNotIn('synthetic original', str(caught.exception))
        self.assertIn('synthetic original Popen error', next((self.root / 'errors').iterdir()).read_text())
        self.assertTrue(all(stream.closed for stream in tunnel.streams))
        transport.Popen.assert_called_once()


    def test_readiness_timeout_and_early_child_exit_capture_owned_cleanup(self):
        for mode in ('timeout', 'exited'):
            with self.subTest(mode=mode):
                if self.run_dir.exists():
                    for f in self.run_dir.iterdir(): f.unlink()
                    self.run_dir.rmdir()
                tunnel, child, transport, sockets = self.tunnel()
                if mode == 'timeout':
                    tunnel.monotonic = Mock(side_effect=[0, 13])
                else:
                    child.poll.return_value = 255
                with self.assertRaises(RuntimeError): tunnel.__enter__()
                transport.Popen.assert_called_once()
                self.assertTrue(all(stream.closed for stream in tunnel.streams))
                if mode == 'timeout': child.terminate.assert_called_once()
                else: child.terminate.assert_not_called()


class FinalEntryTests(Fixtures):
    def test_actual_final_direct_branch_tunnel_before_one_lease_cleanup_timeout(self):
        import final_export_once as export
        events = []
        local = self.run_dir
        local.mkdir(parents=True)
        (local / 'freeze-receipt.json').write_text(json.dumps({'status': 'FROZEN', 'run_dir': 'synthetic-remote'}))
        self.gate['phase'] = 'SOURCE_DIRECT_FINAL_EXPORT'
        self.gate['preflight_receipt_sha256'] = 'synthetic-root-proof'
        module = self.original()
        spec = types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda m: None))
        tunnel = Mock()
        tunnel.return_value.__enter__ = Mock(side_effect=lambda: events.append('tunnel'))
        tunnel.return_value.__exit__ = Mock(side_effect=lambda *args: events.append('closed'))
        response = Mock(status=201, headers={'raw': 'header'})
        response.read.return_value = json.dumps({'role': 'cli_login_postgres_fixture', 'password': SECRET, 'ttl_seconds': 300}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        def http(*args, **kw):
            events.append('lease')
            return response
        def run(args, **kw):
            if '--version' in args: return subprocess.CompletedProcess(args, 0, b'pg_dump (PostgreSQL) 17.10', b'')
            events.append('psql')
            self.assertIn('hostaddr=127.0.0.1 port=15433', args[1])
            self.assertEqual(kw['env']['PGOPTIONS'], r.READONLY)
            raise subprocess.TimeoutExpired(args, 45, output=b'full final primary', stderr=b'full final stderr')
        transport = types.SimpleNamespace(run=Mock(side_effect=run), PIPE=subprocess.PIPE)
        # Fresh final phase validation is Root's separate concern; only inject that gate here.
        with patch.object(export, 'PRIVATE', self.private), patch.object(export, 'paths', return_value=(local, 'synthetic-remote')), patch.object(export, 'gate_check', return_value={}), patch.object(export, 'shell', return_value=b'false'), patch.object(export, 'metadata', return_value={'vault': []}), patch.object(export, 'source_token', return_value='synthetic-token'), patch.object(export, 'processes', PrivateExportProcesses(transport)), patch.object(export.importlib.util, 'spec_from_file_location', return_value=spec), patch.object(export.importlib.util, 'module_from_spec', return_value=module), patch.object(r, 'checked_gate', side_effect=lambda path, *args: dict(path) if isinstance(path, dict) else self.gate), patch.object(r, 'OwnedTunnel', tunnel), patch('urllib.request.urlopen', side_effect=http) as lease_api, patch('sys.argv', ['export', '--name', 'final-export-20261004T000000Z', '--gate-receipt', 'synthetic', '--direct-route-gate', 'synthetic']), patch.dict(os.environ):
            with self.assertRaises(RuntimeError): export.main()
        self.assertEqual(events, ['tunnel', 'lease', 'psql', 'closed'])
        lease_api.assert_called_once()
        self.assertEqual(transport.run.call_count, 2)
        self.assertFalse((local / 'full.dump').exists())
        self.assertFalse((local / 'final-export-receipt.json').exists())
        self.assertTrue((local / 'direct-lease-http-private.json').exists())

    def test_final_receipt_requires_actual_preflight_binding(self):
        self.gate['phase'] = 'SOURCE_DIRECT_FINAL_EXPORT'
        self.gate['preflight_receipt_sha256'] = '0' * 64
        self.run_dir.mkdir(parents=True)
        receipt = self.run_dir / 'preflight-passed.json'
        receipt.write_text(json.dumps({'status': 'PASSED', 'actual_auth_pass': True, 'host': r.HOST, 'project': c.PROJECT}))
        with self.assertRaises(RuntimeError): r.checked_gate(self.gate, self.run_dir, self.gate['phase'], self.clock)
        self.gate['preflight_receipt_sha256'] = c.digest(receipt)
        r.checked_gate(self.gate, self.run_dir, self.gate['phase'], self.clock)
        receipt.write_text(json.dumps({'status': 'PASSED', 'actual_auth_pass': False}))
        self.gate['preflight_receipt_sha256'] = c.digest(receipt)
        with self.assertRaises(RuntimeError): r.checked_gate(self.gate, self.run_dir, self.gate['phase'], self.clock)


if __name__ == '__main__':
    unittest.main(verbosity=2)
