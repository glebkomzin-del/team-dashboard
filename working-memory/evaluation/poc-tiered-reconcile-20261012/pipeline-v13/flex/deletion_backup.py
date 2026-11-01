"""Persist the current restore barrier outside rotating backup sets."""
from datetime import datetime, timezone
from pathlib import Path

from deletion_ledger import read, write
from memory import ValidationError


def persist_restore_barrier(store, identity, ledger_path):
    if not ledger_path:
        raise ValidationError('An external restore deletion ledger must be configured')
    target = Path(ledger_path)
    if not target.is_absolute() or '..' in target.parts or target.is_symlink():
        raise ValidationError('Restore barrier requires a private absolute file path')
    if not isinstance(identity, dict) or identity.get('role') != 'owner':
        raise PermissionError('Only the owner can attest the restore barrier')
    for _ in range(3):
        space = store.space()
        if identity.get('id') != space.get('owner_id'):
            raise PermissionError('Restore barrier owner mismatch')
        revision = space.get('deletion_revision')
        if type(revision) is not int or revision < 0:
            raise ValidationError('Deletion-aware schema is required')
        rows = store.call('source_deletion_ledger', actor_id=identity['id'])
        if not isinstance(rows, list):
            raise ValidationError('Invalid deletion ledger response')
        after = store.space()
        if after.get('id') != space['id'] or after.get('owner_id') != identity['id']:
            raise ValidationError('Restore barrier scope changed')
        if after.get('deletion_revision') != revision:
            continue
        payload = write(target, space_id=space['id'], minimum_deletion_revision=revision,
                        deletions=rows, observed_at=datetime.now(timezone.utc).isoformat())
        saved = read(target, space_id=space['id'])
        if saved['minimum_deletion_revision'] < revision:
            raise ValidationError('Restore barrier was not durably retained')
        # A concurrent newer barrier is safe; the database independently checks
        # that this receipt still covers its current deletion revision.
        if saved['minimum_deletion_revision'] == revision and saved['ledger_sha256'] != payload['ledger_sha256']:
            raise ValidationError('Restore barrier changed during attestation')
        return {'restore_ledger_persisted': True,
                'retention_policy': '14-latest-plus-8-observed-weeks',
                'minimum_deletion_revision': revision}
    raise ValidationError('Deletion ledger changed repeatedly; retry attestation')
