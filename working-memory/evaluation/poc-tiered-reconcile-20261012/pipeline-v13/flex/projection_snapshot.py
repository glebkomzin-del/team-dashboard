"""Deterministic, model-free projection checkpoints for source redaction.

A checkpoint is a privacy boundary: rows before it may have their original
source payloads redacted, while the exact accepted projection remains
rebuildable. Only explicitly named source identities lose their transcript;
tasks, knowledge, owner decisions and their retained evidence quotations stay.
"""
from __future__ import annotations

from copy import deepcopy
import json

from journal_projection import digest
from memory import ValidationError, overview


FORMAT = 'wm-projection-snapshot-v1'
TABLES = (
    'source_versions', 'jobs', 'matters', 'observations', 'work_events',
    'human_decisions', 'matter_links', 'planning_events',
    'projection_event_order',
)
INSERT_ORDER = TABLES


def _exists(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(db, table):
    return [row[1] for row in db.execute('PRAGMA table_info(' + table + ')')]


def _rows(db, table):
    if not _exists(db, table):
        return []
    columns = _columns(db, table)
    ordering = 'rowid'
    return [{column: row[column] for column in columns}
            for row in db.execute('SELECT * FROM ' + table + ' ORDER BY ' + ordering)]


def _state_hash(db):
    state = overview(db)
    # JSON strings are storage details. Hash their parsed content so a restore
    # cannot drift merely because object keys were serialized differently.
    normalized = deepcopy(state)
    for row in normalized.get('knowledge', []):
        if isinstance(row.get('data_json'), str):
            row['data_json'] = json.loads(row['data_json'])
    return digest(normalized)


def redact_logical_basis(logical_basis, redaction_packages):
    """Replace deleted source entries with replayable evidence packages."""
    if not isinstance(logical_basis, list) or not isinstance(redaction_packages, list):
        raise ValidationError('Invalid projection snapshot logical basis')
    from original_deletion import verify_redacted_entry
    packages = {}
    for package in redaction_packages:
        status = verify_redacted_entry(package)
        if status['source_id'] in packages:
            raise ValidationError('Duplicate logical-basis redaction package')
        packages[status['source_id']] = deepcopy(package)
    result=[];replaced=set()
    for entry in logical_basis:
        if not isinstance(entry,dict):raise ValidationError('Invalid logical-basis entry')
        if entry.get('kind')=='redacted_source':
            verify_redacted_entry(entry.get('package'));result.append(deepcopy(entry));continue
        if entry.get('kind')=='source' and entry.get('source',{}).get('source_id') in packages:
            source_id=entry['source']['source_id'];package=packages[source_id]
            if entry['source'].get('id')!=package['source']['id'] or entry['source'].get('content_hash')!=package['source']['content_hash']:
                raise ValidationError('Logical-basis redaction package differs from accepted source')
            result.append({'kind':'redacted_source','package':package});replaced.add(source_id)
        else:result.append(deepcopy(entry))
    # Archive-only sources correctly have no logical entry.
    if replaced-set(packages):raise ValidationError('Logical-basis redaction mismatch')
    return result


def build_snapshot(db, *, through_revision, deletions, logical_basis=None, redaction_packages=None):
    if type(through_revision) is not int or through_revision < 0:
        raise ValidationError('Invalid projection snapshot revision')
    if not isinstance(deletions, list) or not deletions:
        raise ValidationError('Projection snapshot needs a source deletion')
    redacted = {}
    for item in deletions:
        if (not isinstance(item, dict) or set(item) != {'deletion_id', 'source_id'}
                or not isinstance(item['deletion_id'], str) or not isinstance(item['source_id'], str)
                or not item['deletion_id'] or not item['source_id']):
            raise ValidationError('Invalid projection snapshot deletion')
        if item['source_id'] in redacted:
            raise ValidationError('Projection snapshot repeats a source deletion')
        redacted[item['source_id']] = item['deletion_id']
    tables = {table: _rows(db, table) for table in TABLES}
    found = set()
    for source in tables['source_versions']:
        deletion_id = redacted.get(source['source_id'])
        if deletion_id:
            source['transcript'] = ''
            source['redaction_id'] = deletion_id
            found.add(source['source_id'])
        else:
            source['redaction_id'] = None
    # Archive-only originals have no projection row. They still participate in
    # the deletion ledger, but do not alter this checkpoint.
    if found - set(redacted):
        raise ValidationError('Projection snapshot redaction mismatch')
    basis=redact_logical_basis(logical_basis or [],redaction_packages or [])
    payload = {
        'format': FORMAT,
        'through_revision': through_revision,
        'deletions': sorted(deletions, key=lambda item: (item['source_id'], item['deletion_id'])),
        'tables': tables,
        'state_sha256': _state_hash(db),
        'logical_basis': basis,
        'logical_basis_sha256': digest(basis),
    }
    payload['rows_sha256'] = digest(tables)
    payload['snapshot_sha256'] = digest(payload)
    verify_snapshot(payload)
    return payload


def verify_snapshot(payload):
    if not isinstance(payload, dict) or payload.get('format') != FORMAT:
        raise ValidationError('Unknown projection snapshot format')
    expected = payload.get('snapshot_sha256')
    if not isinstance(expected, str) or expected != digest({key: value for key, value in payload.items() if key != 'snapshot_sha256'}):
        raise ValidationError('Projection snapshot checksum mismatch')
    if type(payload.get('through_revision')) is not int or payload['through_revision'] < 0:
        raise ValidationError('Invalid projection snapshot revision')
    tables = payload.get('tables')
    if not isinstance(tables, dict) or set(tables) != set(TABLES) or payload.get('rows_sha256') != digest(tables):
        raise ValidationError('Projection snapshot rows checksum mismatch')
    deletions = payload.get('deletions')
    if not isinstance(deletions, list) or not deletions:
        raise ValidationError('Projection snapshot deletion ledger is missing')
    redacted = {item.get('source_id'): item.get('deletion_id') for item in deletions if isinstance(item, dict)}
    if len(redacted) != len(deletions) or None in redacted:
        raise ValidationError('Invalid projection snapshot deletion ledger')
    seen = set()
    for source in tables['source_versions']:
        if not isinstance(source, dict) or not isinstance(source.get('source_id'), str):
            raise ValidationError('Invalid projection snapshot source')
        deletion_id = source.get('redaction_id')
        if deletion_id is not None:
            if redacted.get(source['source_id']) != deletion_id or source.get('transcript') != '':
                raise ValidationError('Redacted projection source contains plaintext')
            seen.add(source['source_id'])
        elif not isinstance(source.get('transcript'), str) or not source['transcript']:
            raise ValidationError('Unredacted projection source lost its transcript')
    if seen - set(redacted):
        raise ValidationError('Projection snapshot has an unknown redaction')
    for table, rows in tables.items():
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValidationError('Invalid projection snapshot table: ' + table)
    basis=payload.get('logical_basis')
    if not isinstance(basis,list) or payload.get('logical_basis_sha256')!=digest(basis):
        raise ValidationError('Projection snapshot logical basis checksum mismatch')
    from original_deletion import verify_redacted_entry
    for entry in basis:
        if not isinstance(entry,dict) or entry.get('kind') not in ('source','redacted_source','human'):
            raise ValidationError('Invalid projection snapshot logical entry')
        if entry['kind']=='redacted_source':verify_redacted_entry(entry.get('package'))
        elif entry['kind']=='source':
            from journal_projection import verify_source
            verify_source(entry.get('source',{}))
        elif not all(key in entry for key in ('command_id','actor_id','payload')):
            raise ValidationError('Invalid projection snapshot human entry')
    if not isinstance(payload.get('state_sha256'), str) or len(payload['state_sha256']) != 64:
        raise ValidationError('Projection snapshot state checksum is missing')
    return payload


def apply_snapshot(db, payload):
    verify_snapshot(payload)
    tables = payload['tables']
    db.execute('BEGIN IMMEDIATE')
    try:
        for table in reversed(INSERT_ORDER):
            if _exists(db, table):
                db.execute('DELETE FROM ' + table)
        for table in INSERT_ORDER:
            rows = tables[table]
            if not rows:
                continue
            actual_columns = set(_columns(db, table))
            columns = [column for column in rows[0] if column in actual_columns]
            if table == 'source_versions':
                columns = [column for column in columns if column != 'redaction_id']
            if any(set(row) - actual_columns - ({'redaction_id'} if table == 'source_versions' else set()) for row in rows):
                raise ValidationError('Projection snapshot has unknown columns: ' + table)
            sql = 'INSERT INTO ' + table + '(' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')'
            for row in rows:
                if set(row) != set(rows[0]):
                    raise ValidationError('Projection snapshot row shapes differ: ' + table)
                db.execute(sql, tuple(row[column] for column in columns))
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise
    if _state_hash(db) != payload['state_sha256']:
        raise ValidationError('Projection snapshot state differs after restore')
    return {'through_revision': payload['through_revision'], 'state_sha256': payload['state_sha256']}
