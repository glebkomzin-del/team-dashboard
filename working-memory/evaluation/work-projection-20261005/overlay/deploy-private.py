#!/usr/bin/env python3
"""Bounded, Root-reviewed install of the two-file work projection overlay."""
import argparse
import hashlib
import importlib.machinery
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/root/dashboard-work-projection-stage-20261005')
STAGE = ROOT / 'package'
SOURCE = Path('/root/dashboard-archive-generation-reason-overlay-stage-20261005/package')
LIVE = Path('/opt/dashboard-memory-canonical-draft')
CONTAINER = 'dashboard-memory-canonical-draft-canonical-draft-1'
SPACE = '96a2dc44-9b9e-4644-b236-c5c1956cd39d'
IMAGE = 'sha256:5d5986089ce0824b53d530fd35ffe329eada90eb075c5b217f21e3966456bb52'
BASE = 'sha256:8f72278bafb04e24dd04468d941dedaf0ead4d1638cebf4081edf600e185e471'
PIPELINE = 'v11:compact1:gate1:gpt-5.6-terra:25995eec984cca1d:canonical1:7c67663689250e1c'
MANIFEST_SHA = 'b3454788a6a738ce4c7cd019bb18c7c02fbe85713c2b438a8ac9957c85e23237'
FILES = ('journal_projection.py', 'generation_review.py', 'Dockerfile', 'build-manifest.json', 'compose.yaml')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, *, input=None, timeout=60):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=True, timeout=timeout).stdout.strip()


def query(sql):
    return run(['docker','exec','-i','dashboard-supabase-20261003-db-1','psql','-U','postgres',
                '-d','postgres','-AtX','-v','ON_ERROR_STOP=1','-f','-'], input=sql)


def exact_source():
    if digest(STAGE/'package-manifest.json') != MANIFEST_SHA:
        raise ValueError('candidate package manifest drift')
    m=json.loads((STAGE/'package-manifest.json').read_text())
    if (m['candidate_image_id']!=IMAGE or m['source_image_id']!=BASE or m['candidate_pipeline_runtime']!=PIPELINE
            or m['production_release_gate']!='DENY_pending_combined_image_independent_review_and_cold_live_acceptance'
            or digest(SOURCE/'package-manifest.json')!=m['source_package_manifest_sha256']):
        raise ValueError('candidate/base identity drift')
    if run(['docker','image','inspect',m['candidate_tag'],'--format','{{.Id}}'])!=IMAGE:
        raise ValueError('candidate image tag drift')
    if run(['docker','image','inspect',m['source_image_tag'],'--format','{{.Id}}'])!=BASE:
        raise ValueError('base image tag drift')
    for name,expected in m['file_sha256'].items():
        if digest(STAGE/name)!=expected:raise ValueError('candidate source drift: '+name)
    newer=json.loads((STAGE/'build-manifest.json').read_text())
    older=json.loads((SOURCE/'build-manifest.json').read_text())
    if (len(newer)!=138 or len(older)!=138 or sum(k.startswith('schema/') for k in newer)!=47
            or sum(newer[k]==older[k] for k in older)!=135):
        raise ValueError('runtime manifest scope changed')
    for name,value in newer.items():
        if name in FILES and name!='compose.yaml':
            if digest(STAGE/name)!=value:raise ValueError('candidate manifest file drift')
        elif older[name]!=value:
            raise ValueError('unexpected runtime source delta: '+name)
    return m,older


def exact_live(older):
    current=run(['docker','inspect',CONTAINER,'--format','{{.Image}} {{.State.Health.Status}}'])
    if current!=BASE+' healthy':raise ValueError('base worker not healthy/exact')
    for name,value in older.items():
        if digest(LIVE/name)!=value:raise ValueError('live baseline file drift: '+name)
    source_manifest=json.loads((SOURCE/'package-manifest.json').read_text())
    if digest(LIVE/'compose.yaml')!=source_manifest['file_sha256']['compose.yaml']:
        raise ValueError('live Compose drift')
    if digest(LIVE/'schema/20261005202341_generation_review_empty_reason_audit.sql')!='2bfdad83ecaf7a797a77fe6b84b91d5c569471735c51303bb4f8241f2d5f93f0':
        raise ValueError('live GEN-REASON schema source missing or changed')


def verify_function():
    sql="""select md5(pg_get_functiondef(f)),
       has_function_privilege('service_role',f,'EXECUTE'),
       has_function_privilege('anon',f,'EXECUTE'),
       has_function_privilege('authenticated',f,'EXECUTE')
       from (select 'public.wm_generation_decide(uuid,uuid,uuid,uuid,bigint,text,text,text)'::regprocedure f) x;"""
    if query(sql)!='52e542324b17616d1f912cb0f3ef14f7|t|f|f':
        raise ValueError('GEN-REASON function or ACL changed')


def verify_receipts(a):
    renderer=importlib.machinery.SourceFileLoader('renderer47',str(ROOT.parent/'dashboard-archive-generation-reason-overlay-stage-20261005/render-cutover.py')).load_module()
    if not a.inventory.is_absolute() or digest(a.inventory)!=a.inventory_sha:
        raise ValueError('fresh exact inventory receipt required')
    renderer.require_drain(a.drain_receipt,a.drain_sha)  # Validator has 600-second live drain bound.
    p=json.loads(a.inventory.read_text())
    captured=datetime.fromisoformat(p['captured_at'].replace('Z','+00:00'))
    if captured.tzinfo is None or not 0<=(datetime.now(timezone.utc)-captured).total_seconds()<=300:
        raise ValueError('inventory older than 300 seconds or future-dated')
    if (p.get('schema_version')!=1 or p.get('space_id')!=SPACE or p.get('revision')!=226
            or p.get('pipeline')!=PIPELINE or p.get('enabled') is not False
            or p.get('queue_all_unstarted') is not True or p.get('running_count')!=0
            or p.get('unknown_receipt_count')!=0 or p.get('call_count')!=1505
            or len(p.get('queued',[]))!=59):
        raise ValueError('revision/59 unpaid queue/1505 calls/unknown-zero not proved')
    current=json.loads(query((ROOT.parent/'dashboard-archive-generation-reason-overlay-stage-20261005/capture-inventory.sql').read_text()))
    p.pop('captured_at');current.pop('captured_at')
    if p!=current:raise ValueError('live inventory changed')
    verify_function()
    return current


def backup_before(directory):
    if not directory.is_absolute() or directory.exists():
        raise ValueError('fresh absolute backup directory required')
    directory.mkdir(mode=0o700)
    before={}
    for name in FILES:
        dst=directory/name
        shutil.copy2(LIVE/name,dst)
        before[name]=digest(dst)
    (directory/'before-hashes.json').write_text(json.dumps(before,sort_keys=True,indent=2)+'\n')
    (directory/'before-hashes.json').chmod(0o600)
    return before


def install(a,m):
    before=backup_before(a.backup_dir)
    verify_receipts(a)
    for name in FILES:
        target=LIVE/name
        temp=target.with_name(target.name+'.work-projection.tmp')
        if temp.exists():raise ValueError('stale temp file requires reconciliation')
        shutil.copy2(STAGE/name,temp)
        os.replace(temp,target)
        if digest(target)!=m['file_sha256'][name]:raise ValueError('installed file changed: '+name)
    verify_receipts(a)  # Positive Main drain immediately before changing the container.
    run(['docker','compose','-f',str(LIVE/'compose.yaml'),'up','-d','--no-build','--pull','never','canonical-draft'],timeout=60)
    deadline=time.monotonic()+180  # Previous 8f startup/health took approximately 61 seconds.
    while time.monotonic()<deadline:
        state=run(['docker','inspect',CONTAINER,'--format','{{.Image}} {{.State.Health.Status}}'])
        if state==IMAGE+' healthy':break
        time.sleep(5)
    else:raise ValueError('candidate not healthy at exact image within 180 seconds')
    actual=run(['docker','exec',CONTAINER,'python3','-c',
                'from canonical_worker import pipeline_version;print(pipeline_version("gpt-5.6-terra"))'])
    if actual!=PIPELINE:raise ValueError('pipeline changed')
    for name in FILES:
        if digest(LIVE/name)!=m['file_sha256'][name]:raise ValueError('post-install file changed: '+name)
    verify_receipts(a)
    result={'result':'WORK_PROJECTION_IMAGE_INSTALLED_NO_COLD_ACCEPTANCE','image':IMAGE,
            'pipeline':PIPELINE,'inventory_sha256':a.inventory_sha,'drain_sha256':a.drain_sha,
            'before_hashes':before,'after_hashes':m['file_sha256']}
    path=a.backup_dir/'installed.json';path.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');path.chmod(0o600)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=('preflight','deploy'))
    p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--inventory-sha',required=True)
    p.add_argument('--drain-receipt',type=Path,required=True)
    p.add_argument('--drain-sha',required=True)
    p.add_argument('--backup-dir',type=Path,required=True)
    a=p.parse_args()
    if not a.backup_dir.is_absolute() or a.backup_dir.exists():raise ValueError('fresh absolute backup directory required')
    m,older=exact_source();exact_live(older);verify_receipts(a)
    if a.mode=='preflight':
        print(json.dumps({'result':'PRIVATE_PREFLIGHT_ONLY','image':IMAGE,'inventory_sha256':a.inventory_sha},sort_keys=True))
    else:print(json.dumps(install(a,m),sort_keys=True))

if __name__=='__main__':main()
