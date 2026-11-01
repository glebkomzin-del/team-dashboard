#!/usr/bin/env python3
"""Root-operated one-attempt perf-only release; never runs without explicit phase CLI."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

INTAKE = Path('/root/dashboard-intake-transition-prep-20261005.py')
CAPTURE = Path('/root/dashboard-archive-generation-reason-overlay-stage-20261005/capture-inventory.sql')
RENDER = Path('/root/dashboard-archive-generation-reason-overlay-stage-20261005/render-cutover.py')
DEPLOY = Path('/root/dashboard-work-projection-stage-20261005/deploy-private.py')
MANIFEST = Path('/root/dashboard-work-projection-stage-20261005/package/package-manifest.json')
IMAGE = 'sha256:5d5986089ce0824b53d530fd35ffe329eada90eb075c5b217f21e3966456bb52'
BASE = 'sha256:8f72278bafb04e24dd04468d941dedaf0ead4d1638cebf4081edf600e185e471'
PIPELINE = 'v11:compact1:gate1:gpt-5.6-terra:25995eec984cca1d:canonical1:7c67663689250e1c'
SPACE = '96a2dc44-9b9e-4644-b236-c5c1956cd39d'
PINNED = {INTAKE:'703e216b264e27d66cb0b144930e9883da5c4e1e3b80038813c6dc40c2a17a99',
          CAPTURE:'fd283ce063b49ff7df3ef97eca80d1efad6d06c02b9b62aa62980e30688a12b8',
          RENDER:'b70caff953150eba3ca96bee76c0ea827322688197c45b3c27d4cf7a00ae34ab',
          DEPLOY:'573bad948c5c7adf5d96df34e7a78823609c61a73a20902c5c1f339012796290',
          MANIFEST:'b3454788a6a738ce4c7cd019bb18c7c02fbe85713c2b438a8ac9957c85e23237'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned():
    for path,expected in PINNED.items():
        if sha(path)!=expected:raise ValueError('Pinned release input changed: '+path.name)
    m=json.loads(MANIFEST.read_text())
    if (m.get('candidate_image_id')!=IMAGE or m.get('source_image_id')!=BASE
            or m.get('candidate_pipeline_runtime')!=PIPELINE
            or m.get('production_release_gate')!='DENY_pending_combined_image_independent_review_and_cold_live_acceptance'):
        raise ValueError('Perf-only image or release policy changed')


def command(args,expected,*,input=None,timeout=180):
    r=subprocess.run(args,input=input,text=True,capture_output=True,timeout=timeout,check=True)
    if expected is None:return r.stdout.strip()
    value=json.loads(r.stdout)
    if value.get('result')!=expected:raise ValueError('Positive phase result missing: '+expected)
    return value


def intake(action,run):
    return command([sys.executable,str(INTAKE),action,'--run-dir',str(run)],
                   {'preflight-ui':'PREFLIGHT_UI_CAPTURE_READY','capture-ui-pause':'UI_PAUSE_OBSERVED_NEEDS_DRAIN',
                    'drain':'POSITIVE_DRAIN','validate':'DRAIN_VALID_NOW',
                    'capture-ui-resume':'ORIGINAL_VERSION_RESUMED_RECONCILE_ARCHIVE_JOBS'}[action])


def exact_run(raw):
    if not raw.is_absolute() or raw.is_symlink():raise ValueError('absolute unsymlinked private run directory required')
    run=raw.resolve()
    if run.parent!=Path('/root') or not run.name.startswith('dashboard-intake-transition-perf-'):
        raise ValueError('wrong run directory')
    if run.exists() and run.stat().st_mode & 0o077:raise ValueError('run directory is not private')
    return run


def receipt(run):
    path=run/'drain-receipt.json'
    value=json.loads(path.read_text())
    if (value.get('schema')!=1 or value.get('decision')!='POSITIVE_DRAIN' or value.get('run_dir')!=str(run)):
        raise ValueError('drain receipt unavailable')
    return path,sha(path)


def inventory(run):
    intake('validate',run)
    output=command(['docker','exec','-i','dashboard-supabase-20261003-db-1','psql','-U','postgres',
                    '-d','postgres','-AtX','-v','ON_ERROR_STOP=1','-f','-'],None,input=CAPTURE.read_text())
    data=json.loads(output)
    captured=datetime.fromisoformat(data['captured_at'].replace('Z','+00:00'))
    if (captured.tzinfo is None or not 0<=(datetime.now(timezone.utc)-captured).total_seconds()<=300
            or data.get('schema_version')!=1 or data.get('space_id')!=SPACE or data.get('revision')!=226
            or data.get('pipeline')!=PIPELINE or data.get('enabled') is not False
            or data.get('queue_all_unstarted') is not True or data.get('running_count')!=0
            or data.get('call_count')!=1505 or data.get('unknown_receipt_count')!=0
            or len(data.get('queued',[]))!=59):
        raise ValueError('fresh 226/59/1505/unknown-zero inventory not proved')
    path=run/'perf-inventory.json'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as file:file.write(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n')
    return path,sha(path)


def release(run,inventory_sha,drain_sha,expected_sha):
    path=run/'perf-release-accepted.json'
    if sha(path)!=expected_sha:raise ValueError('Root release receipt SHA mismatch')
    value=json.loads(path.read_text())
    expected={'schema':1,'result':'RELEASE_ACCEPTED','package_manifest_sha256':PINNED[MANIFEST],
              'candidate_image_id':IMAGE,'source_image_id':BASE,'candidate_pipeline':PIPELINE,
              'inventory_sha256':inventory_sha,'drain_receipt_sha256':drain_sha,'space_revision':226,
              'generation_function_md5':'52e542324b17616d1f912cb0f3ef14f7','lead_clear':True}
    if value!=expected:raise ValueError('Root release receipt does not bind this exact perf-only state')
    return sha(path)


def deploy(run,release_sha_expected):
    inv=run/'perf-inventory.json'
    if not inv.is_file():raise ValueError('fresh inventory must be captured first')
    drain,drain_sha=receipt(run);inv_sha=sha(inv)
    release_sha=release(run,inv_sha,drain_sha,release_sha_expected)
    backup=run/'perf-five-file-before'
    args=['--inventory',str(inv),'--inventory-sha',inv_sha,
          '--drain-receipt',str(drain),'--drain-sha',drain_sha,'--backup-dir',str(backup)]
    command([sys.executable,str(DEPLOY),'preflight',*args],'PRIVATE_PREFLIGHT_ONLY')
    # One launch only. A failed/ambiguous deploy is reconciled manually, never repeated.
    marker=run/'perf-deploy-once.json'
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as file:
        file.write(json.dumps({'candidate_image_id':IMAGE,'inventory_sha256':inv_sha,
                               'drain_receipt_sha256':drain_sha,'release_receipt_sha256':release_sha},sort_keys=True)+'\n')
    return command([sys.executable,str(DEPLOY),'deploy',*args],
                   'WORK_PROJECTION_IMAGE_INSTALLED_NO_COLD_ACCEPTANCE',timeout=300)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=('prepare','capture-drain','inventory','deploy-once','resume-observed'))
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--release-sha256',help='Root-reviewed private receipt SHA-256, required for deploy-once')
    args=parser.parse_args()
    if (args.phase=='deploy-once') != bool(args.release_sha256):
        parser.error('--release-sha256 is required exactly for deploy-once')
    if args.release_sha256 and (len(args.release_sha256)!=64 or any(c not in '0123456789abcdef' for c in args.release_sha256)):
        parser.error('--release-sha256 must be lowercase SHA-256')
    os.umask(0o077)
    run=exact_run(args.run_dir);pinned()
    if args.phase=='prepare':
        result=intake('preflight-ui',run)
    elif args.phase=='capture-drain':
        # The observed 52-55 minute move burst is outside this bounded drain window.
        if 51<=datetime.now(timezone.utc).minute<=55:raise ValueError('move burst window: start a fresh run later')
        intake('capture-ui-pause',run)
        result=intake('drain',run)  # Pinned helper makes two observations 5 seconds apart.
    elif args.phase=='inventory':
        path,value=inventory(run)
        result={'result':'INVENTORY_POSITIVE_PRIVATE','inventory_sha256':value,
                'drain_sha256':receipt(run)[1],'path':str(path)}
    elif args.phase=='deploy-once':result=deploy(run,args.release_sha256)
    else:result=intake('capture-ui-resume',run)
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'result':'DENY','reason_type':type(error).__name__,
                          'detail':'Inspect private run evidence; no automatic retry'}))
        raise SystemExit(1)
