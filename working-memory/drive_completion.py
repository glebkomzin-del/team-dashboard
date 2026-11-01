"""Read-only completion receipts. Never move a file or trigger a model here."""
import json
import re
from canonical_archive import verify_document
from drive_intake import FOLDERS
from memory import ValidationError, fingerprint

PROCESSED_FOLDER = '1gB3Yy_rh-OdR89LVUUckekjbqUzfPbQT'


def completion(store, document_id):
    if not isinstance(document_id, str) or not re.fullmatch(r'[a-f0-9]{64}', document_id):
        raise ValidationError('Invalid document identity')
    manifest = store.call('drive_manifest')
    if not isinstance(manifest, list):
        raise ValidationError('Incomplete source manifest')
    rows = [r for r in manifest if r.get('document_id') == document_id]
    if len(rows) != 1:
        return {'ready_to_move': False, 'reason': 'unknown_or_superseded_source'}
    original = verify_document(store.call('archive_document', document_id=document_id))
    if original['source_id'] != rows[0]['source_id']:
        raise ValidationError('Completion source mismatch')
    meta = json.loads(original['metadata_json']).get('drive_metadata', {})
    file_id = meta.get('id')
    if not file_id or original['source_id'] != 'drive:'+file_id or not FOLDERS.intersection(meta.get('parents', [])):
        return {'ready_to_move': False, 'reason': 'outside_managed_inbox'}
    job_id = fingerprint(original['source_id']+':'+original['body_hash'])
    detail = store.call('job_detail', job_id=job_id)
    job = detail.get('job', {}) if isinstance(detail, dict) else {}
    if job.get('state') != 'applied' or type(job.get('applied_revision')) is not int or job['applied_revision'] <= 0:
        return {'ready_to_move': False, 'reason': 'not_published'}
    if job.get('id') != job_id or job.get('source_id') != original['source_id']:
        raise ValidationError('Completion job mismatch')
    checksum = meta.get('md5_checksum')
    if not isinstance(checksum, str) or not re.fullmatch(r'[a-fA-F0-9]{32}', checksum):
        return {'ready_to_move': False, 'reason': 'missing_file_checksum'}
    return {'ready_to_move': True, 'document_id': document_id, 'job_id': job_id,
            'applied_revision': job['applied_revision'], 'file_id': file_id,
            'version': meta['version'], 'md5_checksum': checksum.lower(),
            'source_folders': sorted(FOLDERS.intersection(meta['parents'])),
            'destination_folder': PROCESSED_FOLDER}
