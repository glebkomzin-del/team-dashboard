#!/usr/bin/env python3
"""Read-only binding check for the private overlay stage; never authorizes release."""
import hashlib
import json
import subprocess
from pathlib import Path

STAGE = Path('/root/dashboard-archive-generation-reason-overlay-stage-20261005/package')
LIVE = Path('/opt/dashboard-memory-canonical-draft')
MANIFEST_SHA = '1e1e235a15b1e352e62b52fb794416cb16a3ca930330fed14f933a91d9d4d049'
BASE_IMAGE = 'sha256:2c935de2b6c458810c67dbe7b10e07ec8ee06a97bbca305bc9e8582bf5e3e6cb'
CANDIDATE_IMAGE = 'sha256:8f72278bafb04e24dd04468d941dedaf0ead4d1638cebf4081edf600e185e471'
SOURCE_BUILD_MANIFEST_SHA = 'bbb1bda7b73b7dc9f885129c6fec83cdd6b23435ecf493c20dd86f39e254d85c'
SOURCE_COMPOSE_SHA = 'e22911ec94d218bcbc313f950ce4abb4698c282298a95117d9b4d5e5c0192466'
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
    assert package['migration_sha256'] == '2bfdad83ecaf7a797a77fe6b84b91d5c569471735c51303bb4f8241f2d5f93f0'
    assert package['restore_schema_candidate_sha256'] == '627800affff32a07e255a6f20baffebc6bd9e0dd35a72535b30092b52c8f1346'
    assert digest(STAGE/'schema/20261005202341_generation_review_empty_reason_audit.sql') == package['migration_sha256']
    assert digest(STAGE/'restore_schema.py') == package['restore_schema_candidate_sha256']
    assert package['production_release_gate'] == 'DENY_private_candidate_only'
    for name, expected in package['file_sha256'].items():
        assert digest(STAGE/name) == expected, name
    assert run('docker','image','inspect',package['source_image_tag'],'--format','{{.Id}}') == BASE_IMAGE
    assert run('docker','image','inspect',package['candidate_tag'],'--format','{{.Id}}') == CANDIDATE_IMAGE
    assert run('docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1','--format','{{.Image}} {{.State.Health.Status}}') == BASE_IMAGE+' healthy'
    assert digest(LIVE/'build-manifest.json') == SOURCE_BUILD_MANIFEST_SHA
    assert digest(LIVE/'compose.yaml') == SOURCE_COMPOSE_SHA
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
                      'candidate_pipeline':package['candidate_pipeline_runtime'],
                      'baseline_schema_sources':46,'candidate_schema_sources':47},sort_keys=True))


if __name__ == '__main__':
    main()
