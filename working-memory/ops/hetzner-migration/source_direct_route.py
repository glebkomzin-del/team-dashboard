"""Bounded Source-only direct route. Importing this module performs no operations.

Root supplies fresh receipts; this module never creates an approval or renews a lease.
"""
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import time
from urllib.parse import urlparse
import final_phase_common as c

HOST = 'db.' + c.PROJECT + '.supabase.co'
PORT = 15433
PROBLEM = 'HZ-MIGRATION-20261003-FINAL-CUTOVER'
EXPORT_SHA = '3ee071249949e62877c7b04556cd4d73eae259d61c4d3c2ead877f38030ae3ea'
READONLY = '-c role=supabase_read_only_user -c default_transaction_read_only=on'


def require(condition, kind='DIRECT_ROUTE_DENIED'):
    if not condition:
        raise RuntimeError(kind)


def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None)
    return result.astimezone(timezone.utc)


def now():
    return datetime.now(timezone.utc)


def checked_gate(path, run_dir, phase, clock=now):
    """Validate all local proof before any marker, credential, tunnel or transport."""
    gate = dict(path) if isinstance(path, dict) else json.loads(Path(path).read_text())
    require(gate['schema'] == 'source-direct-gate-v1')
    require(gate['problem_id'] == PROBLEM and gate['decision'] == 'CONTINUE_BOUNDED')
    require(gate['phase'] == phase and gate['direct_gate'] is True)
    require(Path(gate['run_dir']).resolve() == Path(run_dir).resolve())
    require(gate['project'] == c.PROJECT and gate['host'] == HOST)
    require(gate['hostaddr'] == '127.0.0.1' and gate['port'] == PORT)
    require(gate['sslmode'] == 'verify-full')
    current = clock()
    require(utc(gate['issued_at']) <= current < utc(gate['expires_at']))
    require((utc(gate['expires_at']) - utc(gate['issued_at'])).total_seconds() <= 300)
    expected = {'source_direct_route.py', 'source_direct_preflight_once.py', 'export_source.py',
                'final_phase_common.py', 'final_export_once.py'}
    require(expected <= set(gate['script_hashes']))
    for filename, digest in gate['script_hashes'].items():
        require(Path(filename).name == filename and c.digest(c.HERE / filename) == digest)
    require(c.digest(c.HERE / 'export_source.py') == EXPORT_SHA)
    ca = c.PRIVATE / 'source/prod-ca-2021.crt'
    require(gate['ca_sha256'] == c.digest(ca))
    proof_dir = c.PRIVATE / 'current-evidence/direct-db-route-1'
    for filename in ('actual-hetzner-direct-db-network.json', 'actual-hetzner-direct-db-tls.json'):
        require(gate['proof_hashes'][filename] == c.digest(proof_dir / filename))
    tcp = json.loads((proof_dir / 'actual-hetzner-direct-db-network.json').read_text())
    tls = json.loads((proof_dir / 'actual-hetzner-direct-db-tls.json').read_text())
    require(tcp['host'] == HOST and any(a['family'] == 10 and a['tcp_connected'] is True for a in tcp['addresses']))
    require(tcp['auth_requests'] == 0 and tcp['queries'] == 0)
    require(tls['host'] == HOST and tls['tls_verified'] is True and tls['hostname_verified'] is True)
    require(tls['tls_version'] == 'TLSv1.3' and tls['auth_requests'] == 0 and tls['queries'] == 0)
    require(gate['lease_budget'] == 1 and gate['probe_budget'] == 1)
    if phase == 'SOURCE_DIRECT_FINAL_EXPORT':
        receipt_path = c.PRIVATE / 'current-evidence/source-direct-auth-preflight-1/preflight-passed.json'
        require(gate['preflight_receipt_sha256'] == c.digest(receipt_path))
        receipt = json.loads(receipt_path.read_text())
        require(receipt['status'] == 'PASSED' and receipt['actual_auth_pass'] is True)
        require(receipt['project'] == c.PROJECT and receipt['host'] == HOST)
    return gate


def validation_query():
    require(c.digest(c.HERE / 'export_source.py') == EXPORT_SHA)
    tree = ast.parse((c.HERE / 'export_source.py').read_text())
    values = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == 'query' for t in node.targets)]
    require(len(values) == 1 and isinstance(values[0], ast.Constant))
    return 'BEGIN READ ONLY; SET LOCAL ROLE supabase_read_only_user; ' + ast.literal_eval(values[0]) + '; ROLLBACK;'


def check_facts(facts, role):
    require(facts['ssl'] is True and facts['current_user'] == 'supabase_read_only_user', 'DIRECT_FACTS_DENIED')
    require(facts['session_user'] == role and facts['read_only'] == 'on', 'DIRECT_FACTS_DENIED')
    require(facts['roles'] and len(facts['roles']) == 1)
    reader = facts['roles'][0]
    require(reader['name'] == 'supabase_read_only_user' and reader['bypassrls'] is True)
    require(reader['superuser'] is False)
    for schema in ('public', 'auth'):
        total, readable = facts[schema + '_tables'], facts[schema + '_readable']
        require(type(total) is int and type(readable) is int and total > 0 and total == readable)
    require(type(facts['public_writable']) is int and facts['public_writable'] == 0)


class DirectRoute:
    """Exact adapter for the immutable exporter, bound to a fresh actual lease."""
    def __init__(self, gate, lease_path, ca, pooler_uri, clock=now):
        require(gate['phase'] in ('SOURCE_DIRECT_AUTH_PREFLIGHT', 'SOURCE_DIRECT_FINAL_EXPORT'))
        self.gate = checked_gate(gate, gate['run_dir'], gate['phase'], clock)
        self.lease_path, self.ca, self.clock = Path(lease_path), Path(ca), clock
        self.source = urlparse(pooler_uri.strip())
        require(self.source.scheme in ('postgres', 'postgresql'))
        require(self.source.hostname and self.source.hostname.endswith('.pooler.supabase.com'))
        require(self.source.username == 'postgres.' + c.PROJECT and (self.source.port or 5432) == 5432)
        require(self.source.path == '/postgres' and not self.source.password and not self.source.query)

    def lease(self):
        value = json.loads(self.lease_path.read_text())
        require(value['read_only_requested'] is True)
        require(type(value['ttl_seconds']) is int and 0 < value['ttl_seconds'] <= 300)
        require(re.fullmatch(r'cli_login_postgres[a-zA-Z0-9_]*', value['role']) is not None)
        require(bool(value['password']))
        created = utc(value['created_at'])
        require(created <= self.clock() and (self.clock() - created).total_seconds() < value['ttl_seconds'], 'DIRECT_LEASE_EXPIRED')
        require(self.gate['project'] == c.PROJECT and self.gate['host'] == HOST)
        require(self.gate['hostaddr'] == '127.0.0.1' and self.gate['port'] == PORT)
        require(self.gate['direct_gate'] is True and self.gate['sslmode'] == 'verify-full')
        require(self.gate['approved_role'] == value['role'])
        require(self.gate['lease_created_at'] == value['created_at'] and self.gate['lease_ttl_seconds'] == value['ttl_seconds'])
        require(self.gate['ca_sha256'] == c.digest(self.ca))
        return value

    def connection(self, lease):
        cert = "'" + str(self.ca).replace("'", "\\'") + "'"
        return ('host=' + HOST + ' hostaddr=127.0.0.1 port=15433 dbname=postgres user=' +
                lease['role'] + ' sslmode=verify-full sslrootcert=' + cert + ' connect_timeout=15')

    def rewrite(self, args, env):
        args = list(args)
        executable = Path(args[0]).name
        require(executable in ('psql', 'pg_dump', 'pg_dumpall'))
        index = 2 if executable == 'pg_dumpall' else 1
        require(len(args) > index and (executable != 'pg_dumpall' or args[1] == '--dbname'))
        lease = self.lease()
        cert = "'" + str(self.ca).replace("'", "\\'") + "'"
        original = ('host=' + self.source.hostname + ' port=5432 dbname=postgres user=' +
                    lease['role'] + '.' + c.PROJECT + ' sslmode=verify-full sslrootcert=' + cert + ' connect_timeout=15')
        require(args[index] == original)
        require(env['PGPASSWORD'] == lease['password'] and env['PGOPTIONS'] == READONLY)
        require(not any('password=' in arg.lower() for arg in args))
        if executable != 'psql':
            require('--role=supabase_read_only_user' in args)
        args[index] = self.connection(lease)
        return args


class SourceProcessAdapter:
    def __init__(self, transport, route):
        self.transport, self.route = transport, route

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def run(self, args, **kwargs):
        if Path(args[0]).name in ('psql', 'pg_dump', 'pg_dumpall'):
            args = self.route.rewrite(args, kwargs['env'])
        result = self.transport.run(args, **kwargs)
        if Path(args[0]).name == 'psql' and result.returncode == 0:
            try:
                check_facts(json.loads(result.stdout), self.route.gate['approved_role'])
            except Exception as error:
                raise c.private_failure('DIRECT_EXPORT_FACTS_ERROR', error_type=type(error).__name__,
                      primary_error=str(error), stdout=result.stdout, stderr=result.stderr) from None
        return result


class OwnedTunnel:
    """Only this child is terminated; original private streams survive all exits."""
    def __init__(self, run_dir, transport=subprocess, sockets=socket, monotonic=time.monotonic, sleeper=time.sleep):
        self.root, self.transport, self.sockets = Path(run_dir), transport, sockets
        self.monotonic, self.sleeper = monotonic, sleeper
        self.child = None
        self.streams = []
        self.started = False

    def __enter__(self):
        require(not self.started, 'DIRECT_TUNNEL_DUPLICATE')
        self.started = True
        try:
            self.root.chmod(0o700)
            # Binding observes port ownership without connecting to any Source service.
            with self.sockets.socket(self.sockets.AF_INET, self.sockets.SOCK_STREAM) as probe:
                probe.bind(('127.0.0.1', PORT))
            for name in ('tunnel.stdout', 'tunnel.stderr'):
                fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                self.streams.append(os.fdopen(fd, 'wb'))
            args = c.SSH[:-1] + ['-o', 'ControlMaster=no', '-o', 'ControlPath=none',
                   '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
                   '-o', 'ServerAliveCountMax=2', '-N', '-L',
                   '127.0.0.1:15433:' + HOST + ':5432', c.SSH[-1]]
            self.child = self.transport.Popen(args, stdout=self.streams[0], stderr=self.streams[1])
            deadline = self.monotonic() + 12
            while self.monotonic() < deadline:
                require(self.child.poll() is None, 'DIRECT_TUNNEL_EXITED')
                try:
                    with self.sockets.create_connection(('127.0.0.1', PORT), timeout=0.25):
                        require(self.child.poll() is None, 'DIRECT_TUNNEL_EXITED')
                        return self
                except OSError:
                    self.sleeper(0.05)
            raise TimeoutError('loopback readiness deadline')
        except Exception as error:
            failure = c.private_failure('DIRECT_TUNNEL_ERROR', error_type=type(error).__name__,
                  primary_error=str(error), stdout_path=str(self.root / 'tunnel.stdout'),
                  stderr_path=str(self.root / 'tunnel.stderr'), stdout=getattr(error, 'stdout', None),
                  stderr=getattr(error, 'stderr', None))
            try:
                self.stop()
            except Exception:
                pass  # Cleanup failure has its own private primary; retain the first failure.
            raise failure from None

    def stop(self):
        try:
            if self.child is not None and self.child.poll() is None:
                self.child.terminate()
                try:
                    self.child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait(timeout=3)
        except Exception as error:
            raise c.private_failure('DIRECT_TUNNEL_CLEANUP_ERROR', error_type=type(error).__name__,
                                  primary_error=str(error), stdout=getattr(error, 'stdout', None),
                                  stderr=getattr(error, 'stderr', None)) from None
        finally:
            for stream in self.streams:
                stream.close()

    def __exit__(self, *exc):
        self.stop()
