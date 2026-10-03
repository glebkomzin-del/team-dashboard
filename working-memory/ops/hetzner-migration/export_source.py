"""One explicitly approved read-only login-role attempt; private output only.

Run only after the Lead's migration_export_gate. Never upgrades permissions,
resets an existing password, unbans networking or deletes shared login roles.
"""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from urllib.parse import urlparse

PROJECT = 'lghwikeotbkmojyyjglz'
ROOT = Path(__file__).resolve().parents[2] / '.local/hetzner-migration-20261003/source'
LINK = Path(__file__).resolve().parents[4] / 'supabase/.temp/pooler-url'


def private_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
    path.chmod(0o600)


def main():
    os.umask(0o077)
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (ROOT / 'full.dump').exists():
        raise SystemExit('Approved export completed; no further credential lease or source export is authorized')
    receipt = ROOT / 'login-role.json'
    if receipt.exists():
        value = json.loads(receipt.read_text())
    else:
        token = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', 'Supabase CLI',
                                '-a', 'supabase', '-w'], capture_output=True, text=True, check=True).stdout.strip()
        if token.startswith('go-keyring-base64:'):
            token = base64.b64decode(token.split(':', 1)[1]).decode()
        request = urllib.request.Request('https://api.supabase.com/v1/projects/' + PROJECT + '/cli/login-role',
                                         data=b'{"read_only":true}', headers={
                                             'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.load(response)
        except Exception:
            raise SystemExit('Read-only login-role creation failed; no automatic retry or write-role fallback') from None
        if not isinstance(value, dict) or not all(value.get(k) for k in ('role', 'password', 'ttl_seconds')):
            raise SystemExit('Unexpected private login-role response; review before continuing')
        private_json(receipt, {**value, 'created_at': datetime.now(timezone.utc).isoformat(), 'read_only_requested': True})
    source = urlparse(LINK.read_text().strip())
    if not source.hostname or PROJECT not in (source.username or ''):
        raise SystemExit('Linked pooler does not match the approved source')
    user = value['role'] + '.' + PROJECT
    connection = ('host=' + source.hostname + ' port=' + str(source.port or 5432) +
                  ' dbname=postgres user=' + user + ' sslmode=verify-full sslrootcert=' +
                  "'" + str(ROOT / 'prod-ca-2021.crt').replace("'", "\\'") + "' connect_timeout=15")
    env = {**os.environ, 'PGPASSWORD': value['password'],
           'PGOPTIONS': '-c role=supabase_read_only_user -c default_transaction_read_only=on'}
    query = """select json_build_object(
      'current_user',current_user,'session_user',session_user,
      'version',current_setting('server_version'),'read_only',current_setting('transaction_read_only'),
      'ssl',(select ssl from pg_stat_ssl where pid=pg_backend_pid()),
      'roles',(select json_agg(json_build_object('name',rolname,'login',rolcanlogin,'bypassrls',rolbypassrls,
        'superuser',rolsuper,'valid_until',rolvaliduntil,'config',rolconfig)) from pg_roles where rolname=current_user),
      'memberships',(select json_agg(r.rolname) from pg_auth_members m join pg_roles r on r.oid=m.roleid
        join pg_roles u on u.oid=m.member where u.rolname=current_user),
      'public_readable',(select count(*) from pg_tables where schemaname='public' and has_table_privilege(current_user,schemaname||'.'||tablename,'SELECT')),
      'public_tables',(select count(*) from pg_tables where schemaname='public'),
      'public_writable',(select count(*) from pg_tables where schemaname='public' and has_table_privilege(current_user,schemaname||'.'||tablename,'INSERT,UPDATE,DELETE,TRUNCATE')),
      'auth_readable',(select count(*) from pg_tables where schemaname='auth' and has_table_privilege(current_user,schemaname||'.'||tablename,'SELECT')),
      'auth_tables',(select count(*) from pg_tables where schemaname='auth'))"""
    check = subprocess.run(['psql', connection, '-XqAt', '-v', 'ON_ERROR_STOP=1', '-c', 'BEGIN READ ONLY; SET LOCAL ROLE supabase_read_only_user; ' + query + '; ROLLBACK;'], env=env,
                           capture_output=True, text=True, timeout=45)
    if check.returncode:
        private_json(ROOT / ('connection-failure-' + datetime.now(timezone.utc).strftime('%H%M%S') + '.json'), {'returncode': check.returncode, 'stderr': check.stderr})
        raise SystemExit('TLS-verified source connection unavailable; private diagnostic retained')
    facts = json.loads(check.stdout)
    facts['frontend_tls_mode'] = 'verify-full'
    facts['frontend_ca_sha256'] = __import__('hashlib').sha256((ROOT / 'prod-ca-2021.crt').read_bytes()).hexdigest()
    private_json(ROOT / 'role-validation.json', facts)
    if facts['current_user'] != 'supabase_read_only_user' or facts['read_only'] != 'on' or facts['public_writable'] or facts['public_readable'] != facts['public_tables'] or facts['auth_readable'] != facts['auth_tables']:
        raise SystemExit('Read-only role does not meet the export privilege boundary; stop without escalation')
    print(json.dumps({'stage': 'source_role_checked', 'read_only_requested': True,
                      'ssl_verified': True, 'ttl_seconds': value['ttl_seconds'],
                      'public_readable': facts['public_readable'], 'auth_readable': facts['auth_readable']}))
    with (ROOT / 'full.dump').open('xb') as stream:
        result = subprocess.run(['pg_dump', connection, '--format=custom', '--role=supabase_read_only_user', '--verbose'], env=env,
                                stdout=stream, stderr=subprocess.PIPE, timeout=600)
    private_json(ROOT / 'dump-result.json', {'returncode': result.returncode,
                 'stderr': result.stderr.decode(errors='replace'), 'pg_dump_version': '17.10', 'row_security': 'off (pg_dump default)', 'effective_role': 'supabase_read_only_user', 'requested_default_transaction_read_only': True})
    if result.returncode:
        raise SystemExit('Full read-only dump failed; no row-security or permission fallback')
    with (ROOT / 'roles.sql').open('xb') as stream:
        result = subprocess.run(['pg_dumpall', '--dbname', connection, '--roles-only', '--no-role-passwords', '--role=supabase_read_only_user'],
                                env=env, stdout=stream, stderr=subprocess.PIPE, timeout=120)
    private_json(ROOT / 'roles-result.json', {'returncode': result.returncode, 'stderr': result.stderr.decode(errors='replace')})
    print(json.dumps({'stage': 'source_export_finished', 'dump_bytes': (ROOT / 'full.dump').stat().st_size,
                      'roles_dump_ok': result.returncode == 0, 'private_path': str(ROOT)}))


if __name__ == '__main__':
    main()
