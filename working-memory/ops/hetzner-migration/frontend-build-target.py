"""Build the accepted isolated source with target anon key; never deploy."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

OPS = Path(__file__).resolve().parent
REPO = OPS.parents[2]
TARGET = 'https://178-105-167-26.nip.io/supabase'
preparation = json.loads((OPS / 'frontend-preparation-evidence.json').read_text())
build = Path(preparation['isolated_build']['path'])
hashes = preparation['isolated_build']['source_hashes']
for name, digest in hashes.items():
    assert hashlib.sha256((REPO / name).read_bytes()).hexdigest() == digest, name
    assert hashlib.sha256((build / name).read_bytes()).hexdigest() == digest, name
assert hashlib.sha256((build / 'vercel.json').read_bytes()).hexdigest() == preparation['csp']['result_sha256']
remote = "python3 -c \"from pathlib import Path; d=dict(x.split('=',1) for x in Path('/opt/dashboard-supabase-20261003/.private.env').read_text().splitlines() if '=' in x and not x.startswith('#')); print(d['ANON_KEY'].strip(chr(39)))\""
key = subprocess.check_output(['ssh', '-i', str(Path.home() / '.ssh/id_ed25519'), '-o', 'StrictHostKeyChecking=yes', 'root@178.105.167.26', remote], text=True, timeout=30).strip()
claims = json.loads(__import__('base64').urlsafe_b64decode(key.split('.')[1] + '==='))
assert claims['role'] == 'anon'
env = dict(os.environ, VITE_SUPABASE_URL=TARGET, VITE_SUPABASE_ANON_KEY=key)
result = subprocess.run(['vercel', 'build', '--yes'], cwd=build, env=env, capture_output=True, text=True, timeout=240)
log = (result.stdout + result.stderr).replace(key, '<target-anon-key>')
(OPS / 'frontend-target-build.txt').write_text(log)
if result.returncode:
    raise SystemExit('Target build failed; see safe build log')
output = build / '.vercel/output'
bundle = b''.join(p.read_bytes() for p in (output / 'static').rglob('*.js'))
assert TARGET.encode() in bundle and key.encode() in bundle
artifact = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file()}
(OPS / 'frontend-target-artifact.json').write_text(json.dumps({'problem_id': 'HZ-MIGRATION-20261003-FRONTEND-CUTOVER', 'source_manifest_count': len(hashes), 'build_path': str(build), 'target_url': TARGET, 'target_key_role': claims['role'], 'target_key_sha256': hashlib.sha256(key.encode()).hexdigest(), 'build_exit': result.returncode, 'output_hashes': artifact, 'production_environment_mutated': False, 'deployment_executed': False}, indent=2) + '\n')
print(json.dumps({'build_exit': result.returncode, 'artifact_files': len(artifact), 'target_url_and_anon_key_embedded': True}))
