"""PREP MAC boundary for late readonly rollback; imports have no effects.

The early final_source_rollback_once.py MUST NOT be reused after target restore.
Actual Source/Target business-data proof has no authoritative receipt schema yet.
Fail closed with the precise input requirement below, rather than guessing zero.
No Target rollback/deletion, password reset, frontend/env restoration or Source
mutation is implemented until Root integrates that primary-query contract.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
from final_writer_open_once import (PROBLEM, ROOT, CLOSED, BASE, NGINX_SHA,
    require, stamp, digest, read_json, PreconditionsError)

INPUT_SCHEMA_REQUIREMENT = {
    'status': 'INPUT_SCHEMA_REQUIRED_NOT_EXECUTABLE',
    'owner': 'Root',
    'problem_id': PROBLEM,
    'phase': 'PREWRITE_SOURCE_ROLLBACK',
    'missing_authoritative_inputs': {
        'source_frozen_baseline': 'Exact immutable primary query bytes, query SHA, UTC, run binding; full original Source space/revision/archive identity/business table counts or fingerprints after freeze',
        'target_business_projection': 'Exact native Docker psql readonly query and original response; compare ONLY business fields, excluding explicitly listed Auth/Vault/backup metadata changes',
        'source_current_projection': 'Exact Source Management readonly query response on Mac, compare same frozen business baseline; token only through existing final_phase_common.sql',
        'target_host_boundary': 'Actual all-five-closed env/image, absence of writer marker and any Target business-write receipt, sole frozen Source, n8n inactive versions',
        'frontend_return_contract': 'Actual promotion receipt, existing project cwd, verified installed official rollback/help syntax, two aliases READY old dpl_84v5UqEaCs5TnRsb6QzahSNxeNxL; remove only two new VITE vars if actually added',
        'private_runtime_return': 'SHA-bound original five host files plus exact Source private environment, host selfhost marker migration_run, original ACL82 and enabled-only full CFG restoration SQL'
    },
    'transport': 'Future execution on Mac using actual final_phase_common.sql/shell; no invented server Source-admin credential',
    'forbidden': ['late call of final_source_rollback_once.py', 'Target data revert',
                  'Source restoration after writer marker', 'unknown proof treated as zero',
                  'wholesale frontend OIDC env restoration', 'workflow SQL activation'],
    'live_execution_count': 0
}


def validate_prewrite(gate, proof, *, now, writer_marker_present, target_business_writes):
    """Pure necessary conditions, deliberately not sufficient execution authority."""
    require(writer_marker_present is False, 'Writer marker exists or absence unproven; Source rollback forbidden')
    require(type(target_business_writes) is int and target_business_writes == 0,
            'Target business writes exist or are unproven; Source rollback forbidden')
    require(gate.get('problem_id') == PROBLEM and gate.get('phase') == 'PREWRITE_SOURCE_ROLLBACK'
            and gate.get('decision') == 'CONTINUE_BOUNDED', 'Rollback phase gate absent')
    run = gate['run_dir']
    import re
    require(re.fullmatch(r'/opt/dashboard-supabase-20261003/final-export-\d{8}T\d{6}Z', run), 'Wrong rollback run')
    issued, expires = stamp(gate['issued_at']), stamp(gate['expires_at'])
    require(issued <= now < expires and (expires-issued).total_seconds() <= 600, 'Rollback gate stale')
    require(proof.get('run_dir') == run and proof.get('observed_at'), 'Actual rollback proof absent')
    require(0 <= (now-stamp(proof['observed_at'])).total_seconds() <= 300, 'Rollback proof stale')
    require(proof.get('target_flags') == CLOSED, 'Target not fully closed')
    require(proof.get('source_frozen') is True and proof.get('source_writer_count') == 0,
            'Source freeze not proven')
    baseline = proof.get('source_frozen_business_baseline')
    require(isinstance(baseline, dict) and baseline, 'Frozen Source business baseline unknown')
    require(proof.get('source_current_business') == baseline and proof.get('target_current_business') == baseline,
            'Business data differs; returning to Source would lose data')
    require(proof.get('original_source_image') == BASE and proof.get('original_nginx_sha256') == NGINX_SHA,
            'Original return artifacts differ')
    require(proof.get('primary_receipts'), 'Direct primary receipts absent')
    return {'necessary_prewrite_boundary': True, 'executable': False,
            'remaining': INPUT_SCHEMA_REQUIREMENT}


def execute(run, gate_path, operations=None, now=None):
    """No transport or mutation; do not accept an injectable executor as a bypass."""
    require(not (run/'writer-open-attempt.marker').exists(), 'Writer already opened; Source rollback forbidden')
    gate = read_json(gate_path)
    require(gate.get('run_dir') == str(run), 'Run differs')
    proof_path = run/'prewrite-source-rollback-proof.json'
    require(proof_path.exists(), 'InputSchemaRequirement: actual Source/Target business primary contract missing')
    proof = read_json(proof_path)
    require(gate.get('receipt_hashes', {}).get(str(proof_path)) == digest(proof_path), 'Rollback proof SHA differs')
    validate_prewrite(gate, proof, now=now or dt.datetime.now(dt.timezone.utc),
                     writer_marker_present=False, target_business_writes=proof.get('target_business_writes'))
    raise PreconditionsError('InputSchemaRequirement: necessary proof is insufficient; Root must integrate exact primary-query and return contracts')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True); parser.add_argument('--gate-receipt', required=True)
    args = parser.parse_args()
    try:
        execute(Path(args.run_dir), Path(args.gate_receipt))
    except Exception as error:
        print(json.dumps({'status': INPUT_SCHEMA_REQUIREMENT['status'], 'error_type': type(error).__name__,
                          'source_mutations': 0, 'target_mutations': 0, 'requirement': INPUT_SCHEMA_REQUIREMENT}))
        return 1
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
