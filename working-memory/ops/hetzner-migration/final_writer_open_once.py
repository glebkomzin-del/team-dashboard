"""PREP: one reviewed writer opening on Hetzner. Import is pure; no business test.

Root must supply actual primary receipts using CONTRACT below. This file never
manufactures them. Failed preconditions cannot write even an attempt marker.
After the marker, failures return to Root and NEVER trigger Source rollback.
"""
import base64
import urllib.error
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request
import uuid

PROBLEM = 'HZ-MIGRATION-20261003-FINAL-CUTOVER'
ROOT = Path('/opt/dashboard-supabase-20261003')
LIVE = Path('/opt/dashboard-memory-canonical-draft')
CANONICAL = 'dashboard-memory-canonical-draft-canonical-draft-1'
DB = 'dashboard-supabase-20261003-db-1'
ORIGIN = 'https://178-105-167-26.nip.io/supabase'
BASE = 'sha256:15a6a820f9d887fac5f0bcd3e2dd29c477d4d5f6a7e82db41bb83cd899f43a2f'
BACKUP_SHA = '58048432e2efb34dc6ede449fc86fc3ce9e3ecbb7d17816d8f512de9b5cb0ea9'
NGINX_SHA = '7cfba8642673162a182f67926bc26dbb0def8bdafecd7952e7ee5c524511fe51'
SCOPES_SHA = 'c1fa6235bdee05964f84e3e06521278f7ffcdd463340e8d2bb2644d9492d589a'
CLOSED = {'MEMORY_READ_ONLY': '1', 'MEMORY_INTAKE_ENABLED': '0',
          'MEMORY_AUTOMATIC_ENABLED': '0', 'MEMORY_QA_ENABLED': '0',
          'MEMORY_ORIGINAL_DELETION_ENABLED': '0'}
ORIGINAL = {k: '0' if k == 'MEMORY_READ_ONLY' else '1' for k in CLOSED}
ALIASES = {'team-dashboard-rho.vercel.app', 'team-dashboard-glebkomzin-dels-projects.vercel.app'}
HOST_FILES = ('compose.yaml', 'build-manifest.json', 'access.py', 'gateway_journal.py', 'service.env')
HOST_PRIMARY_SHA = '19cd20b6c8070ed34ffc3e88c8b1df5be3894948fce652cade3e826092885d48'
SOURCE_ORIGIN = 'https://lghwikeotbkmojyyjglz.supabase.co'
VERSIONS = {'nzyaKxs5Om9wuPEc': None, 'dashboardDriveMove': None, 'dashboardDriveWatch': None}
# Version IDs are extracted from the hash-bound existing helper, never guessed.
RECEIPTS = {
    'comparison': 'final-snapshot-comparison.json',
    'runtime': 'target-runtime-receipt.json',
    'flags': 'source-original-runtime-flags.json',
    'config': 'source-original-config-private.json',
    'source': 'source-effective-before-writer-open.json',
    'frontend': 'frontend-final-promotion-evidence.json',
    'owner': 'production-owner-flow-receipt.json',
    'backup': None, 'mirror': None, 'bundle_manifest': None,
}
CONTRACT = {
    'manifest_schema': 'final-writer-prerequisites-v1',
    'gate': ['problem_id', 'phase=TARGET_WRITER_OPEN', 'decision=CONTINUE_BOUNDED',
             'run_dir', 'issued_at', 'expires_at', 'dump_sha256', 'script_hashes',
             'receipt_hashes'],
    'manifest': ['schema', 'problem_id', 'run_dir', 'receipts'],
    'receipt_reference': {'path': 'absolute primary path, copied byte-for-byte if from Mac',
                          'sha256': 'actual file SHA256, also in gate.receipt_hashes'},
    'receipt_names': RECEIPTS,
    'source_new_primary_contract': {
        'problem_id': PROBLEM, 'run_dir': 'exact remote run', 'observed_at': 'UTC within 300s',
        'query_sha256': 'Root actual OID effective-right query, in gate.source_query_sha256',
        'roles': 'exact anon/authenticated/service_role rows: writable_tables=0, executable_writers=0',
        'catalog_function_count': 43, 'source_config': 'full original with enabled=false',
        'source_backend_running': False,
        'process_scope': 'known inspected host backend and three original paused publications; no world absence claim',
        'primary_receipts': 'nonempty direct path/SHA refs ALSO bound by gate'},
    'owner_new_primary_contract': {
        'status': 'PASSED', 'run_dir': 'exact remote run',
        'source_uid': 'exact original UID', 'target_uid': 'same UID',
        'overview': True, 'archive': True, 'saved_summary': True,
        'same_original': True, 'readonly': True,
        'primary_receipts': 'nonempty direct path/SHA refs ALSO bound by gate'},
    'existing_backup_fields': ['state=ok', 'archive', 'sha256', 'bytes',
                               'selfhost.enabled=true', 'selfhost.restore_verified=true',
                               'n8n.active=0', 'n8n.published=0', 'n8n.external_network=false',
                               'n8n.model_calls=0', 'n8n.credential_decryption_verified=true'],
    'existing_mirror_fields': ['state=ok', 'target=owner_mac', 'archive/sha256/bytes equal backup',
                              'files_verified equals bundle-manifest.files count'],
    'not_ready': 'No future runtime files are supplied by PREP; Root must capture actual results.'
}

class PreconditionsError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise PreconditionsError(message)


def sha_bytes(body):
    return hashlib.sha256(body).hexdigest()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def stamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'Timestamp must include timezone')
    return parsed.astimezone(dt.timezone.utc)


def validate_preconditions(gate, manifest, receipts, *, now, script_hashes, receipt_hashes, frontend_read_bytes=None):
    """Pure validator. receipt_hashes are hashes of actual bytes, not claimed hashes."""
    run = gate.get('run_dir', '')
    require(re.fullmatch(r'/opt/dashboard-supabase-20261003/final-export-\d{8}T\d{6}Z', run), 'Exact new run required')
    require(gate.get('problem_id') == PROBLEM and gate.get('phase') == 'TARGET_WRITER_OPEN'
            and gate.get('decision') == 'CONTINUE_BOUNDED', 'Writer phase permit missing')
    issued, expires = stamp(gate['issued_at']), stamp(gate['expires_at'])
    require(issued <= now < expires and (expires-issued).total_seconds() <= 600, 'Stale gate')
    require(manifest.get('schema') == CONTRACT['manifest_schema']
            and manifest.get('problem_id') == PROBLEM and manifest.get('run_dir') == run, 'Manifest binding differs')
    for name in ['final_writer_open_once.py', 'n8n_dashboard_pause_once.py']:
        require(script_hashes.get(name) == gate.get('script_hashes', {}).get(name)
                and re.fullmatch('[a-f0-9]{64}', script_hashes.get(name, '')), 'Reviewed helper SHA differs')
    refs = manifest['receipts']
    require(set(refs) == set(RECEIPTS), 'Incomplete receipt set')
    require(receipt_hashes.get(run+'/final-writer-prerequisites.json') ==
            gate.get('receipt_hashes', {}).get(run+'/final-writer-prerequisites.json'), 'Prerequisites SHA differs')
    for key, filename in RECEIPTS.items():
        ref = refs[key]
        require(Path(ref['path']).is_absolute(), 'Primary receipt path must be absolute')
        if key=='frontend' and receipts['frontend'].get('schema')=='frontend-access-successor-v1':
            filename='frontend-access-successor-receipt.json'
        if filename:
            require(ref['path'] == run+'/'+filename, 'Receipt belongs to another run')
        require(re.fullmatch('[a-f0-9]{64}', ref['sha256']) and receipt_hashes.get(ref['path']) == ref['sha256']
                and gate.get('receipt_hashes', {}).get(ref['path']) == ref['sha256'], 'Primary receipt SHA differs')
    require(receipts['flags'] == ORIGINAL, 'Actual five Source flags differ')
    comparison, runtime = receipts['comparison'], receipts['runtime']
    require(comparison['mismatches'] in ([], {}) and comparison['comparison_before_auth_vault_acl'] is True
            and comparison['source_sha256'] == gate['dump_sha256'], 'Snapshot comparison incomplete')
    require(runtime['status'] == 'TARGET_READONLY_RUNTIME_ACTIVE' and runtime['closed_flags'] == CLOSED
            and runtime['base_image'] == BASE and runtime['backend_origin'] == ORIGIN
            and runtime['writers_opened'] is False
            and re.fullmatch('sha256:[a-f0-9]{64}', runtime['target_image']), 'Readonly native runtime differs')
    require(receipts['config'] and all(type(c.get('enabled')) is bool for c in receipts['config']), 'Original full config absent')
    source = receipts['source']
    require(source['problem_id'] == PROBLEM and source['run_dir'] == run, 'Source proof binding differs')
    age = (now-stamp(source['observed_at'])).total_seconds()
    require(0 <= age <= 300, 'Stale Source proof')
    require(re.fullmatch('[a-f0-9]{64}', source['query_sha256'])
            and source['query_sha256'] == gate['source_query_sha256'], 'Source query not bound')
    require(source['roles'] == [{'role': r, 'writable_tables': 0, 'executable_writers': 0}
                               for r in ['anon', 'authenticated', 'service_role']]
            and source['catalog_function_count'] == 43, 'Source still writable or incomplete catalog')
    require(source['source_config'] == [{**r, 'enabled': False} for r in receipts['config']]
            and source['source_backend_running'] is False, 'Source not frozen')
    owner = receipts['owner']
    require(owner['status'] == 'PASSED' and owner['run_dir'] == run
            and owner['source_uid'] and owner['source_uid'] == owner['target_uid']
            and all(owner[k] is True for k in ['overview', 'archive', 'saved_summary', 'same_original', 'readonly']), 'Real production Owner flow absent')
    for receipt in [source, owner]:
        require(receipt.get('primary_receipts'), 'Direct primary proof absent')
        for ref in receipt['primary_receipts']:
            require(Path(ref['path']).is_absolute() and re.fullmatch('[a-f0-9]{64}', ref['sha256'])
                    and receipt_hashes.get(ref['path']) == ref['sha256']
                    and gate['receipt_hashes'].get(ref['path']) == ref['sha256'], 'Primary proof not bound')
    frontend = receipts['frontend']
    if frontend.get('schema')=='frontend-access-successor-v1':
        import frontend_access_successor as access
        require(gate.get('frontend_access_schema')==access.SCHEMA and callable(frontend_read_bytes)
                and script_hashes.get('frontend_access_successor.py')==gate['script_hashes'].get('frontend_access_successor.py')
                and re.fullmatch('[a-f0-9]{64}',script_hashes.get('frontend_access_successor.py','')), 'Reviewed access validator/raw reader absent')
        current_ref=gate['frontend_access_current_ref']
        current=access.current_observation(current_ref,frontend_read_bytes,gate['receipt_hashes'],run=run,now=now)
        require(receipt_hashes.get(current_ref['path'])==current_ref['sha256'], 'Actual current access observation not hashed')
        current_receipt=json.loads(access.bound(current_ref,frontend_read_bytes,gate['receipt_hashes']))
        for ref in access.references(current_receipt):
            require(receipt_hashes.get(ref['path'])==ref['sha256'],'Actual current access primary not hashed')
        access.validate(frontend, frontend_read_bytes, gate['receipt_hashes'], run=run,
                        recovery_sha=runtime['recovery_receipt_sha256'], current_provider=current)
        for ref in access.references(frontend):
            require(receipt_hashes.get(ref['path'])==ref['sha256'], 'Actual access primary hash not established')
    else:
        require(frontend['status'] == 'PROMOTED_AND_PUBLIC_ARTIFACT_VERIFIED'
                and frontend['production']['readyState'] == 'READY'
                and frontend['production']['target'] == 'production'
                and ALIASES.issubset(set(frontend['production']['aliases'])), 'Frozen frontend not ready')
        require(all(any(c.get('alias') == a and c.get('exact_index') is True and c.get('exact_headers') is True
                        for c in frontend['checks']) for a in ALIASES), 'Public artifact checks incomplete')
    backup, mirror, bundle = receipts['backup'], receipts['mirror'], receipts['bundle_manifest']
    require(backup['state'] == 'ok' and backup['selfhost']['enabled'] is True
            and backup['selfhost']['restore_verified'] is True, 'Full target restore not verified')
    n8n = backup['n8n']
    require(n8n['active'] == 0 and n8n['published'] == 0 and n8n['external_network'] is False
            and n8n['model_calls'] == 0 and n8n['credential_decryption_verified'] is True, 'Isolated n8n restore missing')
    require(mirror['state'] == 'ok' and mirror['target'] == 'owner_mac'
            and all(mirror[k] == backup[k] for k in ['archive', 'sha256', 'bytes'])
            and bundle['format'] == 'dashboard-full-backup-v1' and bundle['files']
            and mirror['files_verified'] == len(bundle['files']), 'Actual Mac mirror or manifest differs')
    require(re.fullmatch(r'dashboard-\d{8}T\d{6}Z.tar.gz', backup['archive'])
            and re.fullmatch('[a-f0-9]{64}', backup['sha256']) and type(backup['bytes']) is int
            and backup['bytes'] > 0, 'Backup archive identity absent')
    require('selfhost/restore-check.json' in bundle['files'] and 'n8n-restore-check.json' in bundle['files'], 'Embedded restore receipts missing')
    return {'run_dir': run, 'target_image': runtime['target_image'], 'flags': receipts['flags']}


def read_json(path):
    require(not Path(path).is_symlink(), 'Symlink input refused')
    return json.loads(Path(path).read_bytes())


def load_and_validate(run, gate_path, now=None):
    require(run.is_absolute() and run.parent == ROOT and not run.is_symlink(), 'Wrong run root')
    require(not any('writer' in p.name and ('marker' in p.name or 'attempt' in p.name) for p in run.iterdir()), 'Writer attempt already started')
    gate = read_json(gate_path)
    require(gate.get('run_dir') == str(run), 'Run binding differs')
    manifest_path = run/'final-writer-prerequisites.json'
    manifest = read_json(manifest_path)
    receipts = {key: read_json(ref['path']) for key, ref in manifest['receipts'].items()}
    hashes = {str(manifest_path): digest(manifest_path)}
    for ref in manifest['receipts'].values():
        hashes[ref['path']] = digest(ref['path'])
    for key in ['source', 'owner']:
        for ref in receipts[key].get('primary_receipts', []):
            require(not Path(ref['path']).is_symlink(), 'Symlink primary refused')
            hashes[ref['path']] = digest(ref['path'])
    if receipts['frontend'].get('schema')=='frontend-access-successor-v1':
        import frontend_access_successor as access
        current_ref=gate['frontend_access_current_ref'];hashes[current_ref['path']]=digest(current_ref['path'])
        current=json.loads(access.bound(current_ref,lambda path:Path(path).read_bytes(),gate['receipt_hashes']))
        for ref in [*access.references(receipts['frontend']),*access.references(current)]:
            require(not Path(ref['path']).is_symlink(), 'Symlink access primary refused')
            hashes[ref['path']]=digest(ref['path'])
    validate_host_binding(gate, run, lambda path: Path(path).read_bytes())
    scripts = {'final_writer_open_once.py': digest(__file__),
               'n8n_dashboard_pause_once.py': digest(run/'n8n_dashboard_pause_once.py')}
    if receipts['frontend'].get('schema')=='frontend-access-successor-v1':
        scripts['frontend_access_successor.py']=digest(Path(__file__).with_name('frontend_access_successor.py'))
    validated = validate_preconditions(gate, manifest, receipts, now=now or dt.datetime.now(dt.timezone.utc),
                                       script_hashes=scripts, receipt_hashes=hashes, frontend_read_bytes=lambda path: Path(path).read_bytes())
    return gate, receipts, validated


def save_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())


def private_failure(run, error):
    # A rejected/missing run must still retain the original transport failure.
    directory = Path(run)/'writer-private-errors'
    try:
        require(Path(run).is_dir() and not Path(run).is_symlink(), 'Invalid diagnostic run')
        directory.mkdir(mode=0o700, exist_ok=True)
        require(not directory.is_symlink() and not directory.stat().st_mode & 0o077, 'Unsafe error directory')
    except Exception:
        directory = Path(tempfile.mkdtemp(prefix='hz-writer-private-'))
        directory.chmod(0o700)
    def encoded(value):
        if value is None: return None
        return base64.b64encode(value.encode() if isinstance(value, str) else value).decode()
    body = error.read() if isinstance(error, urllib.error.HTTPError) else getattr(error, 'body', None)
    path = directory/(uuid.uuid4().hex+'.json')
    save_private(path, {'exception_type': type(error).__name__, 'primary_error': str(error),
        'stdout_b64': encoded(getattr(error, 'stdout', None)),
        'stderr_b64': encoded(getattr(error, 'stderr', None)), 'body_b64': encoded(body),
        'status': getattr(error, 'code', getattr(error, 'returncode', None)),
        'headers': list(error.headers.items()) if getattr(error, 'headers', None) is not None else None,
        'command': getattr(error, 'cmd', None), 'timeout': getattr(error, 'timeout', None)})
    return str(path)


def validate_host_binding(gate, run, read_bytes):
    refs = gate.get('original_host_files', {})
    require(set(refs) == set(HOST_FILES), 'Exact five original host SHAs required')
    primary = gate.get('original_host_primary', {})
    require(primary.get('sha256') == HOST_PRIMARY_SHA, 'Original host primary differs')
    require(gate.get('receipt_hashes', {}).get(primary.get('path')) == HOST_PRIMARY_SHA,
            'Original host primary not gate bound')
    original = json.loads(read_bytes(primary['path']))
    require(sha_bytes(read_bytes(primary['path'])) == HOST_PRIMARY_SHA, 'Original host primary bytes differ')
    require(original['original_image'] == BASE and original['original_origin'] == SOURCE_ORIGIN
            and original['original_flags'] == ORIGINAL, 'Original host identity differs')
    for name in HOST_FILES:
        ref = refs[name]
        require(ref['path'] == str(run)+'/host-runtime-original/'+name, 'Snapshot path differs')
        require(ref['sha256'] == original['original_file_sha256'][name]
                and gate['receipt_hashes'].get(ref['path']) == ref['sha256']
                and sha_bytes(read_bytes(ref['path'])) == ref['sha256'], 'Original host file SHA differs')
    env = dict(line.split('=', 1) for line in read_bytes(refs['service.env']['path']).decode().splitlines()
               if line and not line.startswith('#'))
    require(env['SUPABASE_URL'].rstrip('/') == SOURCE_ORIGIN
            and all(env[k] == v for k, v in ORIGINAL.items()), 'Original Source environment differs')
    require(b'image: dashboard-memory:memory-20260921-compact-guard-final' in
            read_bytes(refs['compose.yaml']['path']), 'Original compose image differs')
    return original


def env_file(path):
    pairs = [line.split('=', 1) for line in path.read_text().splitlines() if line and not line.startswith('#')]
    require(len(pairs) == len(dict(pairs)), 'Duplicate environment keys')
    return dict(pairs)


def atomic_env(path, flags):
    # Replace ONLY the five existing flag lines, preserving all other bytes.
    body = path.read_bytes(); lines = body.splitlines(keepends=True)
    for key, value in flags.items():
        matches = [i for i, line in enumerate(lines) if line.startswith((key+'=').encode())]
        require(len(matches) == 1, 'Flag line missing or duplicated')
        i = matches[0]; ending = b'\r\n' if lines[i].endswith(b'\r\n') else b'\n' if lines[i].endswith(b'\n') else b''
        lines[i] = (key+'='+value).encode()+ending
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.writer-flags-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(b''.join(lines)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if Path(temp).exists(): Path(temp).unlink()


class HostOperations:
    """No effects in construction. Called only after complete receipt validation."""
    def call(self, args, **kw):
        result = subprocess.run(args, capture_output=True, timeout=kw.pop('timeout', 60), **kw)
        raw = subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
        private_failure(getattr(self, 'run', ROOT), raw)
        if result.returncode:
            raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
        return result.stdout

    def sql(self, query):
        return json.loads(self.call(['docker', 'exec', '-i', DB, 'psql', '-U', 'supabase_admin', '-d', 'postgres',
                                     '-XqAt', '-v', 'ON_ERROR_STOP=1'], input=query.encode()))

    def n8n_check(self, run, active):
        import ast
        tree = ast.parse((run/'n8n_dashboard_pause_once.py').read_text())
        versions = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'VERSIONS' for t in node.targets))
        require(set(versions) == set(VERSIONS), 'Workflow inventory differs')
        key = read_json(ROOT/'n8n-pause-access-1/existing-api-key-private.json')['apiKey']
        for workflow, version in versions.items():
            request = urllib.request.Request('http://127.0.0.1:5678/api/v1/workflows/'+workflow,
                                              headers={'X-N8N-API-KEY': key})
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read()
                save_private(run/('writer-n8n-'+uuid.uuid4().hex+'.json'), {'body_b64': base64.b64encode(body).decode(), 'status': response.status, 'headers': list(response.headers.items())})
                value = json.loads(body)
            require(value['active'] is active and (value.get('activeVersionId') if active else value.get('versionId')) == version, 'n8n publication differs')

    def verify_runtime(self, run, receipts, flags, nginx_sha=NGINX_SHA):
        image = json.loads(self.call(['docker', 'inspect', CANONICAL]))[0]
        env = dict(item.split('=', 1) for item in image['Config']['Env'] if '=' in item)
        current = env_file(LIVE/'.local/service.env')
        original = env_file(run/'host-runtime-original/service.env')
        require(image['State']['Running'] and image['Image'] == receipts['runtime']['target_image'], 'Actual target image differs')
        require(all(current.get(k) == v and env.get(k) == v for k, v in flags.items()), 'Actual five flags differ')
        require(current['SUPABASE_URL'] == ORIGIN and env['SUPABASE_URL'] == ORIGIN, 'Target origin differs')
        mutable = set(CLOSED) | {'SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY'}
        require(set(original) == set(current) and all(current[k] == v and env.get(k) == v
                for k, v in original.items() if k not in mutable), 'Original provider environment differs')
        private = env_file(ROOT/'.private.env')
        require(current['SUPABASE_PUBLISHABLE_KEY'] == env.get('SUPABASE_PUBLISHABLE_KEY') == private['ANON_KEY'].strip("'"), 'Target publish key differs')
        require(digest('/etc/nginx/sites-available/alexa') == nginx_sha, 'Original Nginx not restored')
        manifest = read_json(LIVE/'build-manifest.json'); old = read_json(run/'host-runtime-original/build-manifest.json')
        require(manifest['scheduled_backup.py'] == BACKUP_SHA and digest(LIVE/'scheduled_backup.py') == BACKUP_SHA, 'Backup adapter differs')
        changes = {'access.py', 'gateway_journal.py'}
        require(set(manifest) == set(old) and {k for k in manifest if manifest[k] != old[k]} == changes, 'Runtime changes exceed two origin patches')
        for name in changes:
            require(digest(LIVE/name) == manifest[name] == digest(run/'runtime-build'/name), 'Origin patch differs')
        require(self.sql('SELECT json_agg(c ORDER BY space_id) FROM public.wm_processing_config c') == receipts['config'], 'Full original config differs')
        public = self.sql("SELECT json_agg(x ORDER BY role) FROM (SELECT r.rolname AS role, (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') AND has_table_privilege(r.rolname,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')) AS writable_tables FROM pg_roles r WHERE r.rolname IN ('anon','authenticated')) x")
        require(public == [{'role': r, 'writable_tables': 0} for r in ['anon', 'authenticated']], 'Target public DML remains writable')
        ids = self.call(['docker', 'ps', '-q']).decode().split()
        if ids:
            for other in json.loads(self.call(['docker', 'inspect', *ids])):
                other_env = dict(v.split('=', 1) for v in other['Config'].get('Env', []) if '=' in v)
                require(other_env.get('SUPABASE_URL', '').rstrip('/') != 'https://lghwikeotbkmojyyjglz.supabase.co', 'Hosted Source process still running')

    def preflight(self, run, receipts):
        self.run = run
        require(digest(run/'restore-scopes.sql') == SCOPES_SHA, 'Exact guarded scope restore absent')
        self.verify_runtime(run, receipts, CLOSED)
        self.n8n_check(run, False)

    def hold_maintenance(self, run):
        nginx = Path('/etc/nginx/sites-available/alexa')
        original, candidate = (run/'nginx-original.conf').read_bytes(), (run/'nginx-maintenance.conf').read_bytes()
        require(sha_bytes(original) == NGINX_SHA and nginx.read_bytes() in (original, candidate), 'Foreign Nginx')
        nginx.write_bytes(candidate)
        self.call(['nginx', '-t']); self.call(['systemctl', 'reload', 'nginx'])
        self.call(['docker', 'stop', '--time', '120', CANONICAL], timeout=135)

    def open_writer(self, run, gate_path, receipts):
        atomic_env(LIVE/'.local/service.env', receipts['flags'])
        self.call(['docker', 'compose', 'up', '-d', '--no-build', 'canonical-draft'], cwd=LIVE, timeout=120)
        deadline = time.monotonic()+90
        while True:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8798/health', timeout=5) as response:
                    body = response.read()
                    save_private(run/('writer-health-'+uuid.uuid4().hex+'.json'), {'body_b64': base64.b64encode(body).decode(), 'status': response.status, 'headers': list(response.headers.items())})
                    health = json.loads(body); require(response.status == 200 and health.get('status') == 'ok', 'Health not ok')
                break
            except Exception as error:
                private_failure(run, error)
                if time.monotonic() >= deadline: raise
                time.sleep(min(2, max(0, deadline-time.monotonic())))
        self.call(['python3', str(run/'n8n_dashboard_pause_once.py'), '--action', 'resume',
                   '--run-dir', str(run), '--gate-receipt', str(gate_path)], timeout=100)
        require(read_json(run/'n8n-resume-receipt.json')['status'] == 'PASSED', 'Supported resume incomplete')
        scope = run/'restore-scopes.sql'; require(digest(scope) == SCOPES_SHA, 'Scope SQL changed')
        self.call(['docker', 'exec', '-i', 'n8n_postgres', 'psql', '-U', 'n8n', '-d', 'n8n',
                   '-XqAt', '-v', 'ON_ERROR_STOP=1'], input=scope.read_bytes())
        key = read_json(ROOT/'n8n-pause-access-1/existing-api-key-private.json')
        escaped = str(key['id']).replace("'", "''")
        scopes = json.loads(self.call(['docker', 'exec', '-i', 'n8n_postgres', 'psql', '-U', 'n8n', '-d', 'n8n',
                                      '-XqAt', '-v', 'ON_ERROR_STOP=1'],
                                     input=("SELECT scopes FROM user_api_keys WHERE id='"+escaped+"';").encode()))
        require(scopes == key['scopes'], 'Original API key scopes not restored')
        self.verify_runtime(run, receipts, ORIGINAL)
        self.n8n_check(run, True)
        return health


def execute(run, gate_path, operations=None, now=None):
    marked = False
    operations = operations or HostOperations()
    try:
        gate, receipts, validated = load_and_validate(run, gate_path, now)
        operations.preflight(run, receipts)
        load_and_validate(run, gate_path, now)
        save_private(run/'writer-open-attempt.marker', {'problem_id': PROBLEM, 'run_dir': str(run),
                     'phase': 'TARGET_WRITER_OPEN', 'gate_sha256': digest(gate_path), 'rollback_forbidden': True})
        marked = True
        health = operations.open_writer(run, gate_path, receipts)
        save_private(run/'writer-open-receipt.json', {'status': 'TARGET_WRITER_OPENED', 'problem_id': PROBLEM,
                     'run_dir': str(run), 'image': validated['target_image'], 'health': health,
                     'business_write_test': False, 'source_rollback_allowed': False})
    except Exception as error:
        private = private_failure(run, error)
        if marked:
            try: operations.hold_maintenance(run)
            except Exception as maintenance_error: private_failure(run, maintenance_error)
            save_private(run/'writer-open-partial-receipt.json', {'status': 'PARTIAL_STOP_RETURN_TO_ROOT',
                         'writer_marker_present': True, 'source_rollback_allowed': False, 'private_primary': private})
        raise PreconditionsError('Writer stopped; private primary: '+private) from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True); parser.add_argument('--gate-receipt', required=True)
    args = parser.parse_args(); run = Path(args.run_dir)
    try:
        execute(run, Path(args.gate_receipt))
    except Exception as error:
        # No raw exception/credential/SQL escapes onto stdout or stderr.
        print(json.dumps({'status': 'STOP_RETURN_TO_ROOT', 'error_type': type(error).__name__}))
        return 1
    print(json.dumps({'status': 'TARGET_WRITER_OPENED', 'receipt': str(run/'writer-open-receipt.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
