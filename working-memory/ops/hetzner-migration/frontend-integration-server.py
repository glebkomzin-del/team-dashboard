"""Loopback-only, read-only harness for the exact accepted frontend artifact.

Sessions are stage-issued private files, never command arguments or logs.
Bootstrap only after Lead approval of the public target Auth route.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import urllib.error
import urllib.parse
import urllib.request

OPS = Path(__file__).resolve().parent
REPO = OPS.parents[2]
args = argparse.ArgumentParser()
args.add_argument('--private-dir', type=Path, required=True)
args.add_argument('--port', type=int, default=8943)
args.add_argument('--backend-port', type=int, default=18899)
options = args.parse_args()
artifact = json.loads((OPS / 'frontend-target-artifact.json').read_text())
static = Path(artifact['build_path']) / '.vercel/output/static'
for name, digest in artifact['current_static_hashes'].items():
    assert hashlib.sha256((static.parent / name).read_bytes()).hexdigest() == digest, name
csp = json.loads((static.parent / 'config.json').read_text())['routes'][0]['headers']
evidence_file = options.private_dir / 'integration-requests.jsonl'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never expose sessions, content or Authorization headers.

    def reply(self, status, body, content_type, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        for name, value in (headers or csp).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.reply(405, b'Read-only migration harness', 'text/plain')

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def do_GET(self):
        route = urllib.parse.urlsplit(self.path).path
        if route.startswith('/__migration_session/'):
            name = route.rsplit('/', 1)[-1]
            if name not in ('owner', 'wrong-owner') or not (options.private_dir / 'public-route-approved').exists():
                return self.reply(403, b'Public target route awaits Lead GO', 'text/plain')
            session = json.loads((options.private_dir / (name + '-session.json')).read_text())
            assert session.get('access_token') and session.get('refresh_token')
            nonce = secrets.token_urlsafe(24)
            payload = json.dumps(json.dumps(session)).replace('<', '\\u003c')
            body = ('<!doctype html><meta charset="utf-8"><script nonce="' + nonce + '">localStorage.clear();localStorage.setItem("sb-178-auth-token",' + payload + ');location.replace("/memory-next");</script>').encode()
            return self.reply(200, body, 'text/html', {'Content-Security-Policy': "default-src 'none'; script-src 'nonce-" + nonce + "'; base-uri 'none'; frame-ancestors 'none'"})
        if route.startswith('/api/working-memory/'):
            upstream_path = self.path[len('/api/working-memory'):]
            request = urllib.request.Request('http://127.0.0.1:' + str(options.backend_port) + upstream_path,
                headers={'Authorization': self.headers.get('Authorization', ''), 'Accept': 'application/json'})
            try:
                response = urllib.request.urlopen(request, timeout=110)
            except urllib.error.HTTPError as error:
                response = error
            except (OSError, TimeoutError):
                return self.reply(502, b'{"error":"Private stage clone unavailable"}', 'application/json')
            with response:
                body = response.read()
                record = {'route': route, 'status': response.status, 'body_sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
                try:
                    value = json.loads(body)
                    if isinstance(value, dict):
                        record['json_keys'] = sorted(value)
                        record['array_counts'] = {k: len(v) for k, v in value.items() if isinstance(v, list)}
                except (ValueError, UnicodeError):
                    pass
                with evidence_file.open('a') as evidence:
                    evidence.write(json.dumps(record) + '\n')
                return self.reply(response.status, body, response.headers.get('Content-Type', 'application/json'))
        path = (static / route.lstrip('/')).resolve()
        if not path.is_relative_to(static.resolve()):
            return self.reply(404, b'Not found', 'text/plain')
        if not path.is_file():
            path = static / 'index.html'
        mime = {'.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.html': 'text/html'}.get(path.suffix, 'application/octet-stream')
        self.reply(200, path.read_bytes(), mime)


options.private_dir.mkdir(mode=0o700, exist_ok=True)
print('Read-only integration harness on loopback; target bootstrap gated', flush=True)
ThreadingHTTPServer(('127.0.0.1', options.port), Handler).serve_forever()
