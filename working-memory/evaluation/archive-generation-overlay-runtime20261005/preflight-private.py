#!/usr/bin/env python3
"""Read-only binding check for the private overlay stage; never authorizes release."""
import hashlib
import json
import subprocess
from pathlib import Path

STAGE = Path('/root/dashboard-archive-overlay-stage-20261005/package')
LIVE = Path('/opt/dashboard-memory-canonical-draft')
MANIFEST_SHA = '086d32d4a65e43234cf4170cb885a1240d9b24b6386de1d66670a317f2e5d022'
BASE_IMAGE = 'sha256:2c935de2b6c458810c67dbe7b10e07ec8ee06a97bbca305bc9e8582bf5e3e6cb'
CANDIDATE_IMAGE = 'sha256:423501711e73203b9ea85f554f9e68f647796e53c89157eb5237fd704e7cb2a2'
OLD_PIPELINE = 'v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    assert digest(STAGE/'package-manifest.json') == MANIFEST_SHA
    package = json.loads((STAGE/'package-manifest.json').read_text())
    assert package['source_image_id'] == BASE_IMAGE
    assert package['candidate_image_id'] == CANDIDATE_IMAGE
    assert package['candidate_pipeline_runtime'] == package['candidate_pipeline_source']
    assert package['production_release_gate'].startswith('DENY_')
    for name, expected in package['file_sha256'].items():
        assert digest(STAGE/name) == expected, name
    assert run('docker','image','inspect',package['source_image_tag'],'--format','{{.Id}}') == BASE_IMAGE
    assert run('docker','image','inspect',package['candidate_tag'],'--format','{{.Id}}') == CANDIDATE_IMAGE
    assert run('docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1','--format','{{.Image}} {{.State.Health.Status}}') == BASE_IMAGE+' healthy'
    assert digest(LIVE/'build-manifest.json') == package['source_build_manifest_sha256']
    assert digest(LIVE/'compose.yaml') == package['source_compose_sha256']
    source = json.loads((LIVE/'build-manifest.json').read_text())
    assert len(source) == 137 and sum(name.startswith('schema/') for name in source) == 46
    for name, expected in source.items():
        assert digest(LIVE/name) == expected, name
    assert digest(LIVE/'restore_schema.py') == package['restore_schema_unchanged_sha256']
    assert digest(LIVE/'scheduled_backup.py') == package['scheduled_backup_unchanged_sha256']
    db = run('docker','exec','dashboard-supabase-20261003-db-1','psql','-U','postgres','-d','postgres','-AtX','-v','ON_ERROR_STOP=1','-c',
             "select pipeline,enabled from public.wm_processing_config where space_id='96a2dc44-9b9e-4644-b236-c5c1956cd39d'::uuid")
    assert db == OLD_PIPELINE+'|f', db
    print(json.dumps({'result':'PRIVATE_STAGE_BOUND_RELEASE_DENIED','baseline_image':BASE_IMAGE,
                      'candidate_image':CANDIDATE_IMAGE,'current_pipeline':OLD_PIPELINE,
                      'candidate_pipeline':package['candidate_pipeline_runtime'],'schema_sources':46},sort_keys=True))


if __name__ == '__main__':
    main()
