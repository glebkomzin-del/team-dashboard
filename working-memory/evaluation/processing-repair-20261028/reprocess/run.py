"""Read-only preflight by default; explicit execution uses the unchanged pipeline."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def bundle(action, prefix=None):
    raw = (HERE.parent / 'audit/private/reprocess22-targets.json').read_bytes()
    snapshot = json.loads(raw); targets = snapshot['targets']
    assert len(targets) == 22 and len({t['id'] for t in targets}) == 22
    assert all(t['state'] == 'review' and t['reason'] == 'provider_outcome_unknown' for t in targets)
    if prefix: assert len([t for t in targets if t['id'].startswith(prefix)]) == 1
    return {'action': action, 'job_prefix': prefix, 'space_id': snapshot['space']['id'], 'targets': targets,
            'targets_sha256': hashlib.sha256(raw).hexdigest(),
            'code': {name: base64.b64encode((HERE / name).read_bytes()).decode()
                     for name in ('paid_calls.py', 'container_worker.py')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'claim', 'import', 'one', 'all',
                                         'reviewed-preflight', 'reviewed-claim', 'reviewed-one',
                                         'context-preflight', 'context-claim', 'context-one'), nargs='?', default='preflight')
    parser.add_argument('--job'); parser.add_argument('--execute', action='store_true'); args = parser.parse_args()
    if not args.action.endswith('preflight') and not args.execute: parser.error('Executing pipeline calls requires --execute by Lead')
    encoded = base64.b64encode(json.dumps(bundle(args.action, args.job), ensure_ascii=False).encode()).decode()
    source = (HERE / 'remote.py').read_text() + '\nrun(json.loads(base64.b64decode(' + repr(encoded) + ')))\n'
    process = subprocess.Popen(['ssh', '-i', '/Users/glebkomzin/.ssh/id_ed25519', '-o', 'IdentitiesOnly=yes',
                                '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=12',
                                '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=6',
                                'root@178.105.167.26', 'python3 -'], stdin=subprocess.PIPE)
    process.stdin.write(source.encode()); process.stdin.close(); raise SystemExit(process.wait())


if __name__ == '__main__': main()
