"""Prepare only /opt/dashboard-supabase-20261003; no production switch."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

ROOT = Path('/opt/dashboard-supabase-20261003')
COMMIT = '4ab54b935919ba3f4bb92f436ae4e757108e4f8a'
UPSTREAM = 'https://raw.githubusercontent.com/supabase/supabase/' + COMMIT + '/docker/'


def token(role, secret):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).rstrip(b'=')
    data = encode({'alg': 'HS256', 'typ': 'JWT'}) + b'.' + encode({
        'role': role, 'iss': 'supabase', 'iat': int(time.time()), 'exp': int(time.time()) + 315360000})
    return (data + b'.' + base64.urlsafe_b64encode(hmac.new(secret.encode(), data, hashlib.sha256).digest()).rstrip(b'=')).decode()


def main():
    if Path.cwd() != ROOT:
        raise SystemExit('Run only in the approved isolated target directory')
    os.umask(0o077)
    ROOT.chmod(0o700)
    network = 'dashboard-supabase-20261003_restore'
    probe = subprocess.run(['docker', 'network', 'inspect', network], capture_output=True, text=True)
    if probe.returncode:
        subprocess.run(['docker', 'network', 'create', '--internal', network], check=True, capture_output=True)
    elif not json.loads(probe.stdout)[0]['Internal']:
        raise SystemExit('Existing stage network permits egress; refuse to continue')
    if not (ROOT / 'auth-ownership.sql').is_file():
        raise SystemExit('Copy the approved empty-target auth-ownership.sql before preparation')
    assets = {
        'volumes/db/roles.sql': 'upstream/roles.sql',
        'volumes/db/jwt.sql': 'upstream/jwt.sql',
        'volumes/api/envoy/envoy.yaml': 'upstream/envoy.yaml',
        'volumes/api/envoy/cds.yaml': 'upstream/cds.yaml',
        'volumes/api/envoy/lds.template.yaml': 'upstream/lds.template.yaml',
        'volumes/api/envoy/docker-entrypoint.sh': 'upstream/docker-entrypoint.sh',
        'volumes/functions/main/index.ts': 'functions/main/index.ts',
    }
    manifest = {'upstream_commit': COMMIT, 'files': {}}
    for source, destination in assets.items():
        body = urllib.request.urlopen(UPSTREAM + source, timeout=30).read()
        path = ROOT / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != body:
            raise SystemExit('Existing target upstream file differs; review before replacing')
        path.write_bytes(body)
        path.chmod(0o644)
        manifest['files'][destination] = hashlib.sha256(body).hexdigest()
    (ROOT / 'upstream-manifest.json').write_text(json.dumps(manifest, indent=2))
    env_path = ROOT / '.private.env'
    if not env_path.exists():
        result = subprocess.run(['docker', 'inspect', 'n8n'], capture_output=True, text=True, check=True)
        source = dict(line.split('=', 1) for line in json.loads(result.stdout)[0]['Config']['Env'] if '=' in line)
        if not source.get('GMAIL_APP_PASSWORD') or not source.get('GMAIL_FROM'):
            raise SystemExit('Existing SMTP credential is unavailable; do not silently disable recovery')
        secret = secrets.token_hex(32)
        values = {'POSTGRES_PASSWORD': secrets.token_hex(24), 'JWT_SECRET': secret,
                  'ANON_KEY': token('anon', secret), 'SERVICE_ROLE_KEY': token('service_role', secret),
                  'DASHBOARD_PASSWORD': secrets.token_hex(24),
                  'SMTP_USER': source['GMAIL_FROM'], 'SMTP_PASS': source['GMAIL_APP_PASSWORD']}
        with env_path.open('x') as stream:
            for key, value in values.items():
                if '\n' in value or '\r' in value or "'" in value:
                    raise SystemExit('Unexpected credential format; private configuration needs explicit review')
                stream.write(key + "='" + value + "'\n")
        env_path.chmod(0o600)
    print(json.dumps({'target': str(ROOT), 'upstream_commit': COMMIT,
                      'smtp_credential_present': True, 'secrets_printed': False, 'production_changed': False}))


if __name__ == '__main__':
    main()
