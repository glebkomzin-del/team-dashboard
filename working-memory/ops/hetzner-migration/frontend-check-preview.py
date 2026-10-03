"""Read-only preview routing, CSP and exact deployed static bytes check."""
import hashlib
import json
from pathlib import Path
import subprocess

OPS = Path(__file__).resolve().parent
REPO = OPS.parents[2]
artifact = json.loads((OPS / 'frontend-target-artifact.json').read_text())
url = artifact['preview_url']
output = Path(artifact['build_path']) / '.vercel/output'
checks = []
for route in ['/', '/memory-next?recovery=1']:
    p = subprocess.run(['vercel', 'curl', route, '--deployment', url, '--', '-i'], cwd=REPO, capture_output=True, timeout=45)
    assert p.returncode == 0
    response = p.stdout.decode().replace('\r\n', '\n')
    header, body = response.split('\n\n', 1)
    assert '200' in header.splitlines()[0]
    assert 'content-security-policy:' in header.lower() and 'https://178-105-167-26.nip.io' in header
    original = (output / 'static/index.html').read_text()
    toolbar = '<script async data-explicit-opt-in="true" data-deployment-id="' + artifact['preview_deployment']['id'] + '" src="https://vercel.live/_next-live/feedback/feedback.js"></script>'
    assert body.strip() in (original.strip(), (original + toolbar).strip())
    checks.append({'route': route, 'http': 200, 'csp_target_origin': True, 'exact_app_index': True, 'platform_toolbar_appended': body.strip() != original.strip()})
for path in sorted((output / 'static/assets').glob('*')):
    p = subprocess.run(['vercel', 'curl', '/assets/' + path.name, '--deployment', url], cwd=REPO, capture_output=True, timeout=45)
    assert p.returncode == 0 and p.stdout == path.read_bytes(), path.name
    checks.append({'route': '/assets/' + path.name, 'exact_local_bytes': True, 'sha256': hashlib.sha256(p.stdout).hexdigest()})
p = subprocess.run(['vercel', 'inspect', url, '--format', 'json'], cwd=REPO, capture_output=True, text=True, timeout=45)
assert p.returncode == 0
inspection = json.loads(p.stdout)
assert inspection['id'] == artifact['preview_deployment']['id'] and inspection['readyState'] == 'READY'
evidence = {'problem_id': artifact['problem_id'], 'preview_deployment_id': inspection['id'], 'preview_ready': True, 'checks': checks, 'browser': {'preview': 'Vercel SSO required; protection preserved', 'identical_local_artifact': 'Login form rendered; Passwort vergessen opened recovery request form; no credentials entered or mail requested'}, 'target_integration': 'Open: correct public API route requires Lead GOAL_GATE', 'cycles_used_this_package': 2, 'cycles_max_this_package': 2, 'previous_frontend_prep_cycles': 2, 'first_check_failure': 'Exact HTML comparison distinguished documented Vercel feedback toolbar injection from source alteration; assertion now permits only the exact deployment-bound toolbar suffix.', 'application_provider_cost_calls': 0, 'codex_budget_usage': 'unknown'}
(OPS / 'frontend-preview-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps({'preview_ready': True, 'checks_passed': len(checks), 'production_mutations': 0}))
