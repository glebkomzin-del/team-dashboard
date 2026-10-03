"""Restore the verified source snapshot only into our disposable target."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/opt/dashboard-supabase-20261003')
DB = 'dashboard-supabase-20261003-db-1'
EXPECTED = '4e3574cedb2858f3022f931202581cdea4f43f611e068d8ffecde1c7e1f1bea1'


def run(args, **kwargs):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        (ROOT / 'restore-error-private.txt').write_bytes(result.stderr + result.stdout)
        (ROOT / 'restore-error-private.txt').chmod(0o600)
        raise SystemExit('Target restore command failed; private diagnostic retained: ' + args[0])
    return result.stdout.decode()


def sql(value):
    return run(['docker', 'exec', '-i', DB, 'psql', '-U', 'supabase_admin', '-d', 'postgres',
                '-XqAt', '-v', 'ON_ERROR_STOP=1'], input=value.encode())


def main():
    if Path.cwd() != ROOT:
        raise SystemExit('Unexpected target directory')
    dump = ROOT / 'source-private/full.dump'
    h = hashlib.sha256()
    with dump.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    if h.hexdigest() != EXPECTED:
        raise SystemExit('Source snapshot checksum mismatch')
    marker = ROOT / 'restore-attempt.json'
    if marker.exists():
        raise SystemExit('Existing restore attempt requires explicit bounded review before retry')
    if sql("select (select count(*) from pg_tables where schemaname='public')::text || ':' || (select count(*) from auth.users)::text;").strip() != '0:0':
        raise SystemExit('Target is not the empty isolated instance; refuse to replace it')
    marker.write_text(json.dumps({'source_sha256': EXPECTED, 'attempt': 1, 'status': 'running'}))
    run(['docker', 'compose', '--env-file', '.private.env', 'stop', 'auth', 'rest', 'api-gw', 'functions'])
    existing = set(sql('select rolname from pg_roles;').splitlines())
    roles = []
    for line in (ROOT / 'source-private/roles.sql').read_text().splitlines():
        if 'cli_login_' in line:
            continue  # Temporary CLI sessions are not application identities.
        match = re.fullmatch(r'CREATE ROLE ([a-z_]+);', line)
        if match and match.group(1) in existing:
            continue
        roles.append(line)
    sql('\n'.join(roles))
    # Source Auth migrations and target Auth versions can have different tables.
    # A fresh database avoids dropping around target-only extension dependencies.
    run(['docker', 'exec', DB, 'psql', '-U', 'supabase_admin', '-d', 'template1', '-X', '-v', 'ON_ERROR_STOP=1',
         '-c', 'DROP DATABASE postgres WITH (FORCE);',
         '-c', 'CREATE DATABASE postgres OWNER postgres TEMPLATE template0;'])
    with dump.open('rb') as stream:
        run(['docker', 'exec', '-i', DB, 'pg_restore', '-U', 'supabase_admin', '-d', 'postgres',
             '--exit-on-error', '--verbose'], stdin=stream, timeout=600)
    marker.write_text(json.dumps({'source_sha256': EXPECTED, 'attempt': 1, 'status': 'restored'}))
    print(json.dumps({'target': str(ROOT), 'source_sha256': EXPECTED,
                      'restored': True, 'production_changed': False, 'source_cli_roles_imported': False}))


if __name__ == '__main__':
    main()
