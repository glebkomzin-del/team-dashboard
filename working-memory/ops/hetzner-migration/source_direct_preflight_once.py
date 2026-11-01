"""Prepared future Root CLI; exactly one lease and one direct read-only probe.

No freeze, dump, target, timer or production-flow operation. No import-time effects.
"""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import final_phase_common as c
from final_export_once import PrivateExportProcesses
import source_direct_route as route

POOLER_LINK = c.HERE.parents[3] / 'supabase/.temp/pooler-url'


def run(gate_path, run_dir, *, transport=subprocess, http=urllib.request.urlopen,
        token=c.source_token, tunnel_factory=route.OwnedTunnel, clock=route.now):
    root = Path(run_dir)
    route.require(root.resolve() == (c.PRIVATE / 'current-evidence/source-direct-auth-preflight-1').resolve())
    gate = route.checked_gate(gate_path, root, 'SOURCE_DIRECT_AUTH_PREFLIGHT', clock)
    query = route.validation_query()
    ca = c.PRIVATE / 'source/prod-ca-2021.crt'
    pooler = POOLER_LINK.read_text()
    # Verify Source URI before consuming the single-use marker or any external action.
    from urllib.parse import urlparse
    source = urlparse(pooler.strip())
    route.require(source.scheme in ('postgres', 'postgresql') and source.hostname and
                  source.hostname.endswith('.pooler.supabase.com') and
                  source.username == 'postgres.' + c.PROJECT and (source.port or 5432) == 5432 and
                  source.path == '/postgres' and not source.password and not source.query)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    c.save(root / 'preflight-attempt.json', {'attempt': 1, 'leases_max': 1, 'probes_max': 1,
                                          'dump': 0, 'source_freeze': 0, 'target_mutations': 0})
    child_env = {**os.environ, 'PATH': '/opt/homebrew/bin:' + os.environ.get('PATH', '')}
    processes = PrivateExportProcesses(transport)
    version = processes.check_output(['/opt/homebrew/bin/psql', '--version'], env=child_env, timeout=15)
    route.require(b'17.10' in version, 'DIRECT_PSQL_VERSION_DENIED')
    with tunnel_factory(root):
        created = clock()  # Conservative: lease validity starts before the HTTP request.
        request = urllib.request.Request('https://api.supabase.com/v1/projects/' + c.PROJECT + '/cli/login-role',
                     data=b'{"read_only":true}', headers={'Authorization': 'Bearer ' + token(),
                                                         'Content-Type': 'application/json'})
        try:
            with http(request, timeout=30) as response:
                body = response.read()
                c.save(root / 'lease-http-private.json', {'status': response.status,
                       'headers': str(response.headers), 'body_base64': __import__('base64').b64encode(body).decode()})
                route.require(response.status == 201 or response.status == 200, 'DIRECT_LEASE_HTTP_STATUS')
                lease = json.loads(body)
        except urllib.error.HTTPError as error:
            raise c.private_failure('DIRECT_LEASE_HTTP_ERROR', status=error.code, headers=str(error.headers),
                                    body=error.read()) from None
        except Exception as error:
            raise c.private_failure('DIRECT_LEASE_REQUEST_ERROR', error_type=type(error).__name__,
                 primary_error=str(error), stdout=getattr(error, 'stdout', None), stderr=getattr(error, 'stderr', None)) from None
        route.require(isinstance(lease, dict) and all(lease.get(k) for k in ('role', 'password', 'ttl_seconds')))
        route.require(type(lease['ttl_seconds']) is int and 0 < lease['ttl_seconds'] <= 300)
        lease = {**lease, 'created_at': created.isoformat(), 'read_only_requested': True,
                 'valid_until': (created + timedelta(seconds=lease['ttl_seconds'])).isoformat()}
        c.save(root / 'login-role.json', lease)
        bound = {**gate, 'approved_role': lease['role'], 'lease_created_at': lease['created_at'],
                 'lease_ttl_seconds': lease['ttl_seconds']}
        c.save(root / 'direct-route-lease-private.json', bound)
        direct = route.DirectRoute(bound, root / 'login-role.json', ca, pooler, clock)
        actual = direct.lease()  # Guard immediately before the only new authenticated process.
        env = {**child_env, 'PGPASSWORD': actual['password'], 'PGOPTIONS': route.READONLY}
        result = processes.run(['/opt/homebrew/bin/psql', direct.connection(actual), '-XqAt',
                      '-v', 'ON_ERROR_STOP=1', '-c', query], env=env, capture_output=True, text=True, timeout=45)
        c.save(root / 'probe-private.json', {'returncode': result.returncode,
                                           'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            raise c.private_failure('DIRECT_PROBE_RETURN', returncode=result.returncode,
                                    stdout=result.stdout, stderr=result.stderr) from None
        try:
            facts = json.loads(result.stdout)
            c.save(root / 'role-validation-private.json', facts)
            route.check_facts(facts, actual['role'])
        except Exception as error:
            raise c.private_failure('DIRECT_PROBE_FACTS_ERROR', error_type=type(error).__name__,
                                    primary_error=str(error), stdout=result.stdout, stderr=result.stderr) from None
    # A receipt exists only after the actual facts pass and our tunnel has closed.
    receipt = {'schema': 'source-direct-auth-preflight-v1', 'status': 'PASSED',
               'actual_auth_pass': True, 'project': c.PROJECT, 'host': route.HOST,
               'source_account_password_unchanged': True, 'leases': 1, 'probes': 1,
               'dump': 0, 'source_freeze': 0, 'target_mutations': 0,
               'gate_sha256': c.digest(gate_path), 'script_hashes': gate['script_hashes'],
               'facts_sha256': c.digest(root / 'role-validation-private.json'),
               'ca_sha256': gate['ca_sha256'], 'proof_hashes': gate['proof_hashes']}
    c.save(root / 'preflight-passed.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gate-receipt', required=True)
    parser.add_argument('--run-dir', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        receipt = run(args.gate_receipt, args.run_dir)
    except Exception as error:
        # Any unanticipated exception also has a private original, without caller body leakage.
        raise SystemExit(str(c.private_failure('DIRECT_PREFLIGHT_ERROR', error_type=type(error).__name__,
                                               primary_error=str(error)))) from None
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
