"""Plan and persist evidence-bound display titles for historical originals.

The helper never rewrites an archive document.  It produces an immutable
``source_summary`` note whose only new user-facing datum is ``display_title``.
Calls are dry-run by default.  Before committing such notes, the archive UI
must ignore payloads marked ``title_backfill_only`` as summary content while
still passing them to the display-title resolver.
"""
from datetime import datetime
import json

from archive_index import digest
from canonical_archive import verify_note
from durable_calls import encode, sha
from meeting_naming import is_ambiguous_source_title, resolve_display_title, reviewed_no_topic_title, title_from_response
from memory import ValidationError
from processor import units

VERSION = 'display-title-backfill-v1'
DOCUMENT_FIELDS = ('id', 'source_id', 'event_date', 'observed_at', 'title', 'body_hash', 'body')
EXCEPTIONS = {'no_transcribed_content', 'conversation_ended_before_topic'}


def current_documents(store):
    """Read the latest document envelope per source, returning needed fields only."""
    space = store.space()
    revision = space.get('archive_revision')
    if type(revision) is not int or revision < 0:
        raise ValidationError('Invalid archive revision')
    latest = {}
    for row in store.archive_rows('documents', through=revision):
        if not isinstance(row, dict) or not all(isinstance(row.get(field), str) for field in DOCUMENT_FIELDS):
            raise ValidationError('Invalid archive document inventory')
        try:
            observed = datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
        except ValueError as error:
            raise ValidationError('Invalid observation time') from error
        if observed.tzinfo is None:
            raise ValidationError('Observation time requires timezone')
        prior = latest.get(row['source_id'])
        key = (observed, row.get('registered_revision', 0), row['id'])
        if prior is None or key > prior[0]:
            latest[row['source_id']] = (key, {field: row[field] for field in DOCUMENT_FIELDS})
    return revision, [value[1] for value in latest.values()]


def validated_title(document, proposal):
    """Return a stored title object only when exact passages support it."""
    if not isinstance(document, dict) or not all(isinstance(document.get(field), str) for field in DOCUMENT_FIELDS):
        raise ValidationError('Invalid archive document')
    if digest(document['body']) != document['body_hash']:
        raise ValidationError('Original body checksum mismatch')
    if not is_ambiguous_source_title(document['title'], document['body']):
        raise ValidationError('Source already has a clear title')
    result = title_from_response(proposal, units(document['body']), document['body'])
    if result is None:
        raise ValidationError('Display title is not grounded in cited original passages')
    return result


def note_for(document, proposal):
    """Create a deterministic, idempotent archive-note envelope."""
    display_title = validated_title(document, proposal)
    payload = {
        'title': document['title'],
        'display_title': display_title,
        'title_backfill_only': True,
        'link_provenance': {
            'method': VERSION,
            'document_id': document['id'],
            'source_id': document['source_id'],
            'body_hash': document['body_hash'],
        },
    }
    note_json = encode(payload)
    note_hash = sha(note_json)
    origin_id = VERSION + ':' + document['body_hash']
    return {
        'document_id': document['id'],
        'origin': 'source_summary',
        'origin_id': origin_id,
        'note_json': note_json,
        'note_hash': note_hash,
        'id': sha(':'.join([document['id'], 'source_summary', origin_id, note_hash])),
    }


def _exception_note_for(document, outcome):
    payload = {
        'title': document['title'],
        'display_title': outcome['display_title'],
        'title_backfill_only': True,
        'link_provenance': {
            'method': VERSION,
            'document_id': document['id'],
            'source_id': document['source_id'],
            'body_hash': document['body_hash'],
            'review_outcome': outcome['exception'],
        },
    }
    note_json = encode(payload)
    note_hash = sha(note_json)
    origin_id = VERSION + ':' + document['body_hash']
    return {
        'document_id': document['id'], 'origin': 'source_summary', 'origin_id': origin_id,
        'note_json': note_json, 'note_hash': note_hash,
        'id': sha(':'.join([document['id'], 'source_summary', origin_id, note_hash])),
    }


def validated_exception(document, proposal):
    """Accept a reviewed no-topic outcome only for a genuinely tiny transcript."""
    if not isinstance(proposal, dict) or set(proposal) != {'exception', 'reason', 'evidence_ids'}:
        raise ValidationError('Invalid title backfill exception')
    if proposal['exception'] not in EXCEPTIONS or not isinstance(proposal['reason'], str) or not 5 <= len(proposal['reason'].strip()) <= 240:
        raise ValidationError('Invalid title backfill exception')
    if digest(document['body']) != document['body_hash'] or len(document['body']) > 700:
        raise ValidationError('Title exception requires a short unchanged transcript')
    originals = units(document['body'])
    evidence_ids = proposal['evidence_ids']
    if (not isinstance(evidence_ids, list) or len(evidence_ids) > 4 or
            any(not isinstance(item, str) or item not in originals for item in evidence_ids)):
        raise ValidationError('Invalid title exception evidence')
    if proposal['exception'] == 'conversation_ended_before_topic' and not evidence_ids:
        raise ValidationError('Ended conversation requires exact evidence')
    passages = [originals[item]['text'] for item in dict.fromkeys(evidence_ids)]
    text = reviewed_no_topic_title(proposal['exception'], document['body'], document['event_date'], passages)
    if text is None:
        raise ValidationError('Invalid title backfill exception')
    return {
        'document_id': document['id'],
        'exception': proposal['exception'],
        'reason': proposal['reason'].strip(),
        'evidence': passages,
        'display_title': {'text': text, 'passages': passages, 'method': 'reviewed_no_topic',
                          'exception': proposal['exception']},
    }


def _note_payloads(store, revision):
    result = {}
    for raw in store.archive_rows('notes', through=revision):
        note = verify_note(raw)
        payload = json.loads(note['note_json'])
        record = payload.get('legacy_record', payload)
        value = record.get('payload', record)
        value = {**value, **({'display_title': payload['display_title']} if 'display_title' in payload else {})}
        result.setdefault(note['document_id'], []).append(value)
    return result


def plan(store, proposals):
    """Build a no-write plan keyed by immutable document id."""
    if not isinstance(proposals, dict):
        raise ValidationError('Proposals must be keyed by document id')
    revision, documents = current_documents(store)
    payloads = _note_payloads(store, revision)
    result = {'archive_revision': revision, 'inventory_count': len(documents),
              'ambiguous_count': 0, 'target_count': 0, 'already_resolved': [],
              'notes': [], 'exceptions': [], 'missing': [], 'rejected': []}
    for document in sorted(documents, key=lambda row: (row['event_date'], row['id'])):
        if not is_ambiguous_source_title(document['title'], document['body']):
            continue
        result['ambiguous_count'] += 1
        resolved = resolve_display_title(document['title'], document['body'], document['event_date'],
                                         note_payloads=payloads.get(document['id'], ()))
        if resolved['method'] != 'transparent_fallback':
            result['already_resolved'].append({'document_id': document['id'], 'method': resolved['method']})
            continue
        result['target_count'] += 1
        proposal = proposals.get(document['id'])
        if proposal is None:
            result['missing'].append(document['id'])
            continue
        try:
            if isinstance(proposal, dict) and 'exception' in proposal:
                outcome = validated_exception(document, proposal)
                result['exceptions'].append({key: outcome[key] for key in ('document_id', 'exception', 'reason', 'evidence')})
                result['notes'].append(_exception_note_for(document, outcome))
            else:
                result['notes'].append(note_for(document, proposal))
        except ValidationError as error:
            result['rejected'].append({'document_id': document['id'], 'reason': str(error)})
    return result


def apply(store, backfill_plan, *, commit=False):
    """Persist an already-reviewed plan; partial runs are safely resumable by note id."""
    notes = backfill_plan.get('notes') if isinstance(backfill_plan, dict) else None
    if not isinstance(notes, list) or type(backfill_plan.get('archive_revision')) is not int:
        raise ValidationError('Invalid backfill plan')
    exceptions = backfill_plan.get('exceptions')
    if (backfill_plan.get('missing') or backfill_plan.get('rejected') or
            type(backfill_plan.get('target_count')) is not int or not isinstance(exceptions, list) or
            len(notes) != backfill_plan['target_count']):
        raise ValidationError('Backfill plan is incomplete')
    seen = set()
    for note in notes:
        verified = verify_note(note)
        payload = json.loads(verified['note_json'])
        if (verified['origin'] != 'source_summary' or not payload.get('title_backfill_only') or
                payload.get('link_provenance', {}).get('method') != VERSION or verified['id'] in seen):
            raise ValidationError('Invalid title backfill note')
        seen.add(verified['id'])
    if not commit:
        return {'dry_run': True, 'planned': len(notes), 'written': 0}
    if store.space().get('archive_revision') != backfill_plan['archive_revision']:
        raise ValidationError('Archive changed after title review')
    receipts = [store.archive_note_put(note) for note in notes]
    return {'dry_run': False, 'planned': len(notes), 'written': len(receipts), 'receipts': receipts}
