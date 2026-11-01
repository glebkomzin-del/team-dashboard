#!/usr/bin/env python3
"""Bounded 47-source runtime install; Root runs deploy only after separate review."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path('/root/dashboard-archive-generation-reason-overlay-stage-20261005')
STAGE = HERE / 'package'
LIVE = Path('/opt/dashboard-memory-canonical-draft')
CONTAINER = 'dashboard-memory-canonical-draft-canonical-draft-1'
IMAGE = 'sha256:8f72278bafb04e24dd04468d941dedaf0ead4d1638cebf4081edf600e185e471'
PIPELINE = 'v11:compact1:gate1:gpt-5.6-terra:25995eec984cca1d:canonical1:7c67663689250e1c'
OLD = 'v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c'
SPACE = '96a2dc44-9b9e-4644-b236-c5c1956cd39d'
FILES = ('canonical_archive.py', 'journal_service.py', 'hybrid_index.py', 'restore_schema.py',
         'Dockerfile', 'build-manifest.json', 'compose.yaml',
         'schema/20261005202341_generation_review_empty_reason_audit.sql')
MANIFEST_SHA = '1e1e235a15b1e352e62b52fb794416cb16a3ca930330fed14f933a91d9d4d049'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(args, *, input=None):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=True, timeout=60).stdout.strip()


def sql(query):
    return run(['docker', 'exec', '-i', 'dashboard-supabase-20261003-db-1', 'psql', '-U', 'postgres', '-d',
                'postgres', '-AtX', '-v', 'ON_ERROR_STOP=1', '-f', '-'], input=query)


def verify_db_function():
    q = """select md5(pg_get_functiondef(f)),
      has_function_privilege('service_role',f,'EXECUTE'),
      has_function_privilege('anon',f,'EXECUTE'),
      has_function_privilege('authenticated',f,'EXECUTE')
      from (select 'public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure f) x;"""
    assert sql(q) == '52e542324b17616d1f912cb0f3ef14f7|t|f|f', 'GEN-REASON function or ACL drift'


def verify_receipts(a):
    from importlib.machinery import SourceFileLoader
    renderer = SourceFileLoader('renderer47', str(HERE / 'render-cutover.py')).load_module()
    if not a.inventory.is_absolute() or digest(a.inventory.read_bytes()) != a.inventory_sha:
        raise ValueError('exact inventory receipt missing or changed')
    renderer.require_drain(a.drain_receipt, a.drain_sha)
    p = json.loads(a.inventory.read_text())
    captured = datetime.fromisoformat(p['captured_at'].replace('Z', '+00:00'))
    if captured.tzinfo is None or not 0 <= (datetime.now(timezone.utc)-captured).total_seconds() <= 300:
        raise ValueError('inventory is stale')
    if (p.get('schema_version') != 1 or p.get('space_id') != SPACE or p.get('revision') != 226
            or p.get('pipeline') != OLD or p.get('enabled') is not False
            or p.get('queue_all_unstarted') is not True or p.get('running_count') != 0
            or p.get('unknown_receipt_count') != 0 or p.get('job_count', 0) < 59
            or len(p.get('queued', [])) != 59):
        raise ValueError('inventory lacks the positive 59-job/unknown-zero condition')
    current = json.loads(sql((HERE / 'capture-inventory.sql').read_text()))
    p.pop('captured_at')
    current.pop('captured_at')
    if p != current:
        raise ValueError('live inventory changed since receipt')
    verify_db_function()
    return current


def verify_stage():
    if digest((STAGE / 'package-manifest.json').read_bytes()) != MANIFEST_SHA:
        raise ValueError('package manifest drift')
    m = json.loads((STAGE / 'package-manifest.json').read_text())
    if (m.get('candidate_image_id') != IMAGE or m.get('candidate_pipeline_runtime') != PIPELINE
            or m.get('migration_sha256') != '2bfdad83ecaf7a797a77fe6b84b91d5c569471735c51303bb4f8241f2d5f93f0'
            or m.get('production_release_gate') != 'DENY_private_candidate_only'):
        raise ValueError('candidate bind drift')
    if run(['docker', 'image', 'inspect', m['candidate_tag'], '--format', '{{.Id}}']) != IMAGE:
        raise ValueError('candidate image drift')
    b = json.loads((STAGE / 'build-manifest.json').read_text())
    if len(b) != 138 or sum(x.startswith('schema/') for x in b) != 47:
        raise ValueError('47-source manifest missing')
    for name, value in b.items():
        source = STAGE / name
        if not source.exists():
            source = LIVE / name
        if digest(source.read_bytes()) != value:
            raise ValueError('source drift: ' + name)
    for name in FILES:
        if digest((STAGE / name).read_bytes()) != m['file_sha256'][name]:
            raise ValueError('overlay drift: ' + name)
    return m


def verify_baseline():
    from importlib.machinery import SourceFileLoader
    SourceFileLoader('preflight47', str(HERE / 'preflight-private.py')).load_module().main()
    if (LIVE / FILES[-1]).exists():
        raise ValueError('live 47-source already exists; reconcile before retry')


def snapshot_before(path):
    if path.exists() or not path.is_absolute():
        raise ValueError('fresh absolute backup directory required')
    path.mkdir(mode=0o700)
    receipt = {}
    for name in FILES:
        src = LIVE / name
        if src.exists():
            dst = path / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            receipt[name] = digest(dst.read_bytes())
        else:
            receipt[name] = None
    out = path / 'before-hashes.json'
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    out.chmod(0o600)
    return receipt


def install(a, m):
    before = snapshot_before(a.backup_dir)
    # Recheck the time-sensitive positive evidence immediately before runtime change.
    verify_receipts(a)
    for name in FILES:
        dst = LIVE / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + '.archive47.tmp')
        if tmp.exists():
            raise ValueError('stale private temp file; reconcile before retry')
        shutil.copy2(STAGE / name, tmp)
        os.replace(tmp, dst)
        if digest(dst.read_bytes()) != m['file_sha256'][name]:
            raise ValueError('installed source changed: ' + name)
    verify_receipts(a)
    run(['docker', 'compose', '-f', str(LIVE/'compose.yaml'), 'up', '-d', '--no-build', '--pull', 'never', 'canonical-draft'])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = run(['docker', 'inspect', CONTAINER, '--format', '{{.Image}} {{.State.Health.Status}}'])
        if state == IMAGE + ' healthy':
            break
        time.sleep(3)
    else:
        raise ValueError('candidate worker did not become healthy within 60 seconds')
    actual = run(['docker', 'exec', CONTAINER, 'python3', '-c',
                  'from canonical_worker import pipeline_version;print(pipeline_version("gpt-5.6-terra"))'])
    if actual != PIPELINE:
        raise ValueError('candidate pipeline mismatch')
    for name in FILES:
        if digest((LIVE/name).read_bytes()) != m['file_sha256'][name]:
            raise ValueError('post-install file drift: ' + name)
    live = verify_receipts(a)
    result = {'result': 'RUNTIME47_INSTALLED_CUTOVER_NOT_RUN', 'image': IMAGE, 'pipeline': actual,
              'inventory_sha256': a.inventory_sha, 'drain_sha256': a.drain_sha,
              'before_hashes': before, 'after_hashes': m['file_sha256'],
              'revision': live['revision'], 'unknown_receipt_count': live['unknown_receipt_count']}
    output = a.backup_dir / 'installed.json'
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    output.chmod(0o600)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=('preflight', 'deploy'))
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--inventory-sha', required=True)
    p.add_argument('--drain-receipt', type=Path, required=True)
    p.add_argument('--drain-sha', required=True)
    p.add_argument('--backup-dir', type=Path, required=True)
    a = p.parse_args()
    if not a.backup_dir.is_absolute() or a.backup_dir.exists():
        raise ValueError('fresh absolute backup directory required')
    verify_stage()
    verify_baseline()
    verify_receipts(a)
    if a.mode == 'preflight':
        print(json.dumps({'result':'DEPLOY47_PREFLIGHT_ONLY','candidate_image':IMAGE,
                          'inventory_sha256':a.inventory_sha,'backup_dir':str(a.backup_dir)}, sort_keys=True))
    else:
        print(json.dumps(install(a, json.loads((STAGE/'package-manifest.json').read_text())), sort_keys=True))


if __name__ == '__main__':
    main()
