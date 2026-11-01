"""Pure preparation and verification primitives for original-only deletion.

This module deliberately performs no database writes.  It converts one accepted
source journal entry into a self-contained, attested evidence manifest while the
original transcript is still available.  A later migration can persist the
manifest, purge every plaintext copy, and teach replay to consume the redacted
format without pretending that retained quotations are a complete transcript.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from difflib import SequenceMatcher
import hashlib
import json
from uuid import UUID

from memory import ValidationError
from journal_projection import digest, verify_source


FORMAT = 'wm-redacted-source-v1'

# A purge is only complete once every durable or rebuildable plaintext location
# was checked.  Keeping this contract in code prevents a UI from equating a
# source-table update with deletion of the original.
REQUIRED_SCOPES = (
    'archive_documents',
    'archive_notes',
    'source_versions',
    'journal_payloads',
    'generation_payloads',
    'prepared_jobs',
    'model_receipts',
    'question_receipts',
    'search_documents',
    'search_results',
    'local_caches',
    'backup_sets',
)
SANITIZED_RECORD_SCOPES = frozenset({
    'archive_note', 'prepared_job', 'model_call', 'question',
    'question_call', 'generation_review', 'journal_generation',
    'job_decision',
})


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _iso_time(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError('Redaction time requires a timezone')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValidationError('Redaction time requires a timezone')
    return value


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('Deletion identity must be a UUID') from None


def _quote_spans(observation: dict, transcript: str) -> list[dict]:
    quotes = observation.get('quotes')
    if not isinstance(quotes, list) or not quotes:
        raise ValidationError('Every retained observation needs evidence')
    if any(not isinstance(quote, str) or not quote.strip() for quote in quotes):
        raise ValidationError('Invalid retained evidence quote')
    selected = observation.get('source_spans')
    if selected is None:
        result = []
        for quote in quotes:
            start = transcript.find(quote)
            if start < 0:
                raise ValidationError('Retained quote is absent from the original')
            result.append({'start': start, 'end': start + len(quote), 'quote': quote})
        return result
    if not isinstance(selected, list) or not selected:
        raise ValidationError('Invalid retained evidence spans')
    result = []
    for span in selected:
        if (not isinstance(span, dict) or type(span.get('start')) is not int
                or type(span.get('end')) is not int or not isinstance(span.get('quote'), str)):
            raise ValidationError('Invalid retained evidence span')
        start, end, quote = span['start'], span['end'], span['quote']
        if not 0 <= start < end <= len(transcript) or transcript[start:end] != quote:
            raise ValidationError('Retained evidence span differs from the original')
        result.append({'start': start, 'end': end, 'quote': quote})
    if {span['quote'] for span in result} != set(quotes):
        raise ValidationError('Retained evidence spans do not cover every quote')
    return result


def _evidence_manifest(transcript: str, payload: dict) -> dict:
    proposal = payload.get('proposal')
    if not isinstance(proposal, dict) or not isinstance(proposal.get('observations'), list):
        raise ValidationError('Accepted source payload has no observation list')
    entries = []
    for observation_index, observation in enumerate(proposal['observations']):
        if not isinstance(observation, dict):
            raise ValidationError('Invalid retained observation')
        for quote_index, span in enumerate(_quote_spans(observation, transcript)):
            entries.append({
                'observation_index': observation_index,
                'quote_index': quote_index,
                'start': span['start'],
                'end': span['end'],
                'quote': span['quote'],
                'quote_sha256': _sha(span['quote']),
            })
    # Matter-link evidence is also a user-visible derivation and must remain
    # attributable after the original is gone.
    for link_index, link in enumerate(payload.get('matter_links', [])):
        if not isinstance(link, dict) or not isinstance(link.get('quotes'), list):
            raise ValidationError('Invalid retained matter-link evidence')
        for quote_index, quote in enumerate(link['quotes']):
            if not isinstance(quote, str) or not quote.strip():
                raise ValidationError('Invalid retained matter-link quote')
            start = transcript.find(quote)
            if start < 0:
                raise ValidationError('Matter-link quote is absent from the original')
            entries.append({
                'matter_link_index': link_index,
                'quote_index': quote_index,
                'start': start,
                'end': start + len(quote),
                'quote': quote,
                'quote_sha256': _sha(quote),
            })
    entries.sort(key=lambda item: (
        item['start'], item['end'], item.get('observation_index', -1),
        item.get('matter_link_index', -1), item['quote_index']))
    covered = []
    for item in entries:
        start, end = item['start'], item['end']
        if covered and start <= covered[-1][1]:
            covered[-1][1] = max(covered[-1][1], end)
        else:
            covered.append([start, end])
    retained_characters = sum(end - start for start, end in covered)
    return {
        'entries': entries,
        'original_characters': len(transcript),
        'retained_evidence_characters': retained_characters,
        'retained_evidence_fraction': retained_characters / len(transcript),
    }


def _retained_payload(payload: dict) -> dict:
    """Keep replay inputs and deliberate derivations, excluding auxiliary copies.

    coverage_notes, provenance and archive_note are not needed to reconstruct
    accepted tasks or knowledge and may contain broad source paraphrases or old
    envelopes. Their original hashes remain in the attestation.
    """
    proposal = payload['proposal']
    retained = {
        'format': payload.get('format'),
        'pipeline': payload.get('pipeline'),
        'model': payload.get('model'),
        'proposal': {
            'observations': deepcopy(proposal['observations']),
            'coverage_notes': [],
        },
        'usage': deepcopy(payload.get('usage', {})),
        'result_sha256': payload.get('result_sha256'),
    }
    for field in ('human_guard', 'matter_links'):
        if field in payload:
            retained[field] = deepcopy(payload[field])
    return retained


def prepare_redacted_entry(entry: dict, *, deletion_id: str, prepared_at: str) -> dict:
    """Build a redacted replacement without mutating the accepted entry."""
    if not isinstance(entry, dict) or entry.get('kind') != 'source':
        raise ValidationError('Only an accepted source entry can be redacted')
    source, payload = entry.get('source'), entry.get('payload')
    if not isinstance(source, dict) or not isinstance(payload, dict):
        raise ValidationError('Incomplete accepted source entry')
    verify_source(source)
    if not isinstance(payload.get('result_sha256'), str) or len(payload['result_sha256']) != 64:
        raise ValidationError('Accepted source result checksum is required')
    manifest = _evidence_manifest(source['transcript'], payload)
    manifest['sha256'] = digest({key: value for key, value in manifest.items() if key != 'sha256'})
    retained_payload = _retained_payload(payload)
    package = {
        'format': FORMAT,
        'deletion_id': _uuid(deletion_id),
        'prepared_at': _iso_time(prepared_at),
        'source': {
            key: source[key] for key in
            ('id', 'source_id', 'content_hash', 'event_date', 'title', 'observed_at')
        },
        'evidence_manifest': manifest,
        'retained_payload': retained_payload,
        'attestation': {
            'accepted_payload_sha256': digest(payload),
            'accepted_result_sha256': payload['result_sha256'],
            'original_content_sha256': source['content_hash'],
            'omitted_payload_fields_sha256': {
                key: digest(payload[key]) for key in sorted(set(payload) - set(retained_payload))
            },
        },
    }
    package['package_sha256'] = digest(package)
    verify_redacted_entry(package)
    return package


def verify_redacted_entry(package: dict) -> dict:
    """Verify a redacted package using no original plaintext."""
    if not isinstance(package, dict) or package.get('format') != FORMAT:
        raise ValidationError('Unknown redacted source format')
    expected = package.get('package_sha256')
    if not isinstance(expected, str) or expected != digest({key: value for key, value in package.items() if key != 'package_sha256'}):
        raise ValidationError('Redacted source package checksum mismatch')
    _uuid(package.get('deletion_id'))
    _iso_time(package.get('prepared_at'))
    source = package.get('source')
    if not isinstance(source, dict) or set(source) != {'id', 'source_id', 'content_hash', 'event_date', 'title', 'observed_at'}:
        raise ValidationError('Invalid redacted source identity')
    if _sha(source['source_id'] + ':' + source['content_hash']) != source['id']:
        raise ValidationError('Redacted source identity checksum mismatch')
    manifest = package.get('evidence_manifest')
    if not isinstance(manifest, dict) or manifest.get('sha256') != digest({key: value for key, value in manifest.items() if key != 'sha256'}):
        raise ValidationError('Evidence manifest checksum mismatch')
    total = manifest.get('original_characters')
    retained = manifest.get('retained_evidence_characters')
    if type(total) is not int or total <= 0 or type(retained) is not int or not 0 <= retained <= total:
        raise ValidationError('Invalid evidence coverage')
    entries = manifest.get('entries')
    if not isinstance(entries, list):
        raise ValidationError('Invalid evidence manifest')
    intervals = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get('quote'), str):
            raise ValidationError('Invalid evidence entry')
        if _sha(item['quote']) != item.get('quote_sha256'):
            raise ValidationError('Evidence quote checksum mismatch')
        start, end = item.get('start'), item.get('end')
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= total or end - start != len(item['quote']):
            raise ValidationError('Invalid evidence position')
        intervals.append((start, end))
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    if sum(end - start for start, end in merged) != retained:
        raise ValidationError('Evidence coverage checksum mismatch')
    retained_payload = package.get('retained_payload')
    attestation = package.get('attestation')
    if not isinstance(retained_payload, dict) or not isinstance(attestation, dict):
        raise ValidationError('Incomplete redaction attestation')
    if retained_payload.get('result_sha256') != attestation.get('accepted_result_sha256'):
        raise ValidationError('Accepted result is not bound to retained replay data')
    if source['content_hash'] != attestation.get('original_content_sha256'):
        raise ValidationError('Original content hash is not bound to the source')
    return {
        'verified': True,
        'source_id': source['source_id'],
        'source_version': source['id'],
        'retained_evidence_characters': retained,
        'original_characters': total,
        'full_text_retained_as_evidence': retained == total,
    }


def plaintext_canaries(transcript: str, *, window: int = 64, step: int = 32) -> tuple[str, ...]:
    """Return transient plaintext canaries for post-purge scans.

    Callers must not persist these strings in the ledger.  Persist only their
    hashes if an audit trail is needed.
    """
    if not isinstance(transcript, str) or not transcript:
        raise ValidationError('Original transcript is required')
    if type(window) is not int or type(step) is not int or window < 16 or step < 1:
        raise ValidationError('Invalid plaintext canary bounds')
    if len(transcript) <= window:
        return (transcript,)
    starts = list(range(0, len(transcript) - window + 1, step))
    if starts[-1] != len(transcript) - window:
        starts.append(len(transcript) - window)
    return tuple(dict.fromkeys(transcript[start:start + window] for start in starts))


def find_plaintext_leaks(value, canaries: tuple[str, ...], *, allowed_quotes=()) -> list[str]:
    """Return JSON paths containing non-evidence original plaintext.

    Exact retained quotes are removed before scanning.  Results contain paths
    only, so purge logs never reproduce user content.
    """
    if not isinstance(canaries, tuple) or not canaries or any(not isinstance(item, str) or not item for item in canaries):
        raise ValidationError('Invalid plaintext canaries')
    allowed = sorted(set(allowed_quotes), key=len, reverse=True)
    leaks = []

    def visit(item, path):
        if isinstance(item, dict):
            for key, child in item.items():
                visit(child, path + (str(key),))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, path + (str(index),))
        elif isinstance(item, str):
            candidate = item
            for quote in allowed:
                candidate = candidate.replace(quote, '')
            if any(canary in candidate for canary in canaries):
                leaks.append('$.' + '.'.join(path))

    visit(value, ())
    return sorted(set(leaks))


def _redact_matches(value: str, transcript: str, *, minimum: int) -> tuple[str, int]:
    """Remove copied source spans while retaining unrelated derived prose."""
    if not value or not transcript:
        return value, 0
    threshold = min(minimum, len(transcript))
    if threshold <= 0:
        return value, 0
    matches = []

    def collect(a_start, a_end, b_start, b_end):
        match = SequenceMatcher(None, transcript[a_start:a_end], value[b_start:b_end],
                                autojunk=False).find_longest_match()
        if match.size < threshold:
            return
        a = a_start + match.a
        b = b_start + match.b
        matches.append((b, b + match.size))
        collect(a_start, a, b_start, b)
        collect(a + match.size, a_end, b + match.size, b_end)

    collect(0, len(transcript), 0, len(value))
    if not matches:
        return value, 0
    merged = []
    for start, end in sorted(matches):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    pieces = []
    cursor = 0
    for start, end in merged:
        pieces.append(value[cursor:start])
        pieces.append('[Originalpassage entfernt]')
        cursor = end
    pieces.append(value[cursor:])
    return ''.join(pieces), sum(end - start for start, end in merged)


def sanitize_json_receipt(raw: str | None, transcript: str, *, minimum_match=48):
    """Surgically remove copied original spans from a JSON receipt.

    User questions, independent answers, hashes and accounting can therefore be
    retained. The returned body is canonical JSON plus a count of removed
    characters; callers keep the original receipt hash separately.
    """
    if raw is None:
        return None, {'changed': False, 'removed_characters': 0}
    if not isinstance(raw, str):
        raise ValidationError('Receipt body must be JSON text')
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise ValidationError('Receipt body is not JSON') from None
    removed = 0

    def visit(item):
        nonlocal removed
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, str):
            result, count = _redact_matches(item, transcript, minimum=minimum_match)
            removed += count
            return result
        return item

    transformed = visit(value)
    sanitized = (raw if removed == 0 else
                 json.dumps(transformed, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    canaries = plaintext_canaries(transcript, window=max(16, min(minimum_match, len(transcript))),
                                  step=max(1, min(minimum_match, len(transcript)) // 2))
    leaks = find_plaintext_leaks(json.loads(sanitized), canaries)
    if leaks:
        raise ValidationError('Sanitized receipt still contains original plaintext at ' + ','.join(leaks))
    return sanitized, {'changed': removed > 0, 'removed_characters': removed,
                       'sanitized_sha256': _sha(sanitized)}


def prepare_sanitization_plan(candidate: dict, transcript: str, *, minimum_match=48) -> dict:
    """Sanitize one complete database candidate returned by the gateway.

    Candidate keys and the server-computed before hash are opaque identities.
    The purge rechecks both under table locks, preventing a plan from being
    applied to a row that changed while the source was inspected.
    """
    if (not isinstance(candidate, dict) or set(candidate) != {'scope', 'record_key', 'before_hash', 'data'}
            or candidate.get('scope') not in SANITIZED_RECORD_SCOPES
            or not isinstance(candidate.get('record_key'), str) or not candidate['record_key']
            or not isinstance(candidate.get('before_hash'), str)
            or len(candidate['before_hash']) != 64 or not isinstance(candidate.get('data'), dict)):
        raise ValidationError('Invalid source deletion candidate')
    raw=json.dumps(candidate['data'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
    sanitized,receipt=sanitize_json_receipt(raw,transcript,minimum_match=minimum_match)
    replacement=json.loads(sanitized)
    return {
        'scope':candidate['scope'],'record_key':candidate['record_key'],
        'before_hash':candidate['before_hash'],'replacement':replacement,
        'replacement_hash':digest(replacement),'scan':receipt,
    }


def deletion_label(package: dict, verified_scopes) -> str:
    """Return a truthful UI state; never claim deletion from a partial purge."""
    status = verify_redacted_entry(package)
    scopes = set(verified_scopes)
    if scopes != set(REQUIRED_SCOPES):
        return 'Löschung läuft'
    if status['full_text_retained_as_evidence']:
        return 'Aus der aktiven App gelöscht; vollständiger Wortlaut bleibt als übernommener Beleg erhalten'
    return 'Original gelöscht; Belegzitate bleiben erhalten'
