"""Disposable Unix-socket PostgreSQL 17 reproduction; no external database access."""
import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BIN = pathlib.Path('/opt/homebrew/opt/postgresql@17/bin')
MIGRATION = ROOT / 'supabase/migrations/20261005202341_generation_review_empty_reason_audit.sql'
OLD = ROOT / 'supabase/migrations/20260909155014_optional_generation_review_reason.sql'

def call(args, **kwargs):
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=75, **kwargs)

def main():
    old = OLD.read_text()
    start = old.index('create or replace function public.wm_generation_decide')
    end = old.index('end; $$;', start) + len('end; $$;')
    old_function = old[start:end]
    with socket.socket() as port_probe:
        port_probe.bind(('127.0.0.1', 0))
        port = port_probe.getsockname()[1]
    outer = pathlib.Path('/private/tmp/gen-reason-400-20261005')
    outer.mkdir(mode=0o700, exist_ok=True)
    os.chmod(outer, 0o700)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='pg-', dir=outer))
    cluster, sock = tmp / 'cluster', tmp / 'socket'
    sock.mkdir(mode=0o700)
    started = False
    try:
        init = call([str(BIN / 'initdb'), '-D', str(cluster), '-A', 'trust', '--no-instructions'])
        if init.returncode:
            raise RuntimeError('initdb failed: ' + init.stderr[-600:])
        start_pg = call([str(BIN / 'pg_ctl'), '-D', str(cluster), '-l', str(tmp / 'postgres.log'),
                         '-o', f"-k {sock} -p {port} -c listen_addresses=''", 'start'])
        if start_pg.returncode:
            raise RuntimeError('pg_ctl start failed: ' + start_pg.stderr[-600:])
        started = True
        script = '\n'.join([
            (HERE / 'setup.sql').read_text(), old_function,
            "revoke all on function public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text) from public,anon,authenticated;",
            "grant execute on function public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text) to service_role;",
            "select 'BASELINE_MD5:'||md5(pg_get_functiondef('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure));",
            (HERE / 'baseline-repro.sql').read_text(),
            "select 'BASELINE_REPRO_OK';",
            MIGRATION.read_text(),
            "select 'MIGRATION_APPLIED_LOCAL';",
            "select 'POST_MD5:'||md5(pg_get_functiondef('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure));",
            (HERE / 'acceptance.sql').read_text(),
            "select 'ACCEPTANCE_OK';",
            (HERE / 'rollback.sql').read_text(),
            "select 'ROLLBACK_MD5:'||md5(pg_get_functiondef('public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure));"
        ])
        test = call([str(BIN / 'psql'), '-h', str(sock), '-p', str(port), '-U', os.environ['USER'],
                     '-d', 'postgres', '-XAtq', '-v', 'ON_ERROR_STOP=1'], input=script)
        (outer / 'last-test.stdout').write_text(test.stdout)
        (outer / 'last-test.stderr').write_text(test.stderr)
        os.chmod(outer / 'last-test.stdout', 0o600)
        os.chmod(outer / 'last-test.stderr', 0o600)
        if test.returncode:
            raise RuntimeError('psql failed: ' + test.stderr[-900:])
        markers = test.stdout.splitlines()
        needed = {'BASELINE_MD5:0622bb6e1c04dcd75e5e0774ed502337',
                  'BASELINE_REPRO_OK', 'MIGRATION_APPLIED_LOCAL', 'ACCEPTANCE_OK',
                  'POST_MD5:52e542324b17616d1f912cb0f3ef14f7',
                  'ROLLBACK_MD5:0622bb6e1c04dcd75e5e0774ed502337'}
        if not needed.issubset(set(markers)):
            raise RuntimeError('missing verification marker: ' + repr(markers[-10:]))
        evidence = {'status': 'isolated_postgres17_pass', 'markers': markers,
                    'migration_sha256': hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
                    'setup_sha256': hashlib.sha256((HERE / 'setup.sql').read_bytes()).hexdigest(),
                    'scope': 'synthetic disposable local database; no production or provider call',
                    'cleanup': 'pending'}
        print('GEN_REASON_400_LOCAL_PASS', evidence['migration_sha256'])
    finally:
        if started:
            stop_pg = call([str(BIN / 'pg_ctl'), '-D', str(cluster), '-m', 'immediate', 'stop'])
            if stop_pg.returncode:
                raise RuntimeError('isolated postgres did not stop: ' + stop_pg.stderr[-500:])
        shutil.rmtree(tmp)
        if 'evidence' in locals():
            evidence['cleanup'] = 'stopped_and_removed'
            (HERE / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

if __name__ == '__main__':
    main()
