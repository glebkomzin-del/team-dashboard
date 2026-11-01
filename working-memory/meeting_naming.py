"""Evidence-bound display names for archived meetings.

The immutable source title remains the identity.  This module only derives a
separate display title and never calls a model.  A title proposed by the
existing extraction call is accepted only with citations into the same source.
"""
from datetime import date
import re
import unicodedata

GENERIC_TITLES = {
    'meeting', 'teams meeting', 'meeting transcription', 'transcription',
    'transkript', 'besprechung', 'kurzabstimmung', 'kurze abstimmung',
    'abstimmung', 'call', 'teams call', 'video call',
}

_TITLE_FILLERS = {
    'abstimmung', 'anruf', 'besprechung', 'call', 'gesprach', 'jour', 'fixe',
    'jf', 'meeting', 'teams', 'termin', 'transcription', 'transkript', 'und',
    'mit', 'andere', 'anderer', 'anderen', 'x',
}
_GROUNDING_FILLERS = _TITLE_FILLERS | {
    'aktuell', 'austausch', 'besprechen', 'besprochen', 'diskussion', 'fur',
    'klaren', 'klarung', 'planen', 'planung', 'prufen', 'prufung', 'sprechen',
    'thema', 'uber', 'zum', 'zur', 'des', 'der', 'die', 'das', 'ein', 'eine',
}
_OWNER_NAMES = {'gleb komzin', 'komzin gleb'}


def _plain(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(c for c in normalized if not unicodedata.combining(c)).lower()))


def _tokens(value):
    return [token for token in _plain(value).split() if len(token) >= 2]


def teams_metadata(transcript):
    """Read only the observed Microsoft Teams transcript header."""
    result = {}
    lines = (transcript or '').splitlines()
    for line in lines[:12]:
        match = re.match(r'^\s*(Meeting Titel|Teilnehmer|Datum|Beginn)\s*:\s*(.*?)\s*$', line, re.I)
        if not match:
            if result and re.match(r'^\s*\[?\d{1,2}:\d{2}', line):
                break
            continue
        key = {'meeting titel': 'source_title', 'teilnehmer': 'participants',
               'datum': 'event_date', 'beginn': 'started_at'}[_plain(match.group(1))]
        if key == 'participants':
            result[key] = [item.strip() for item in match.group(2).split(';') if item.strip()]
        else:
            result[key] = match.group(2).strip()
    return result


def _speaker_names(transcript):
    names = []
    for line in (transcript or '').splitlines()[:300]:
        match = re.match(r'^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s+)([^:]{2,100}):\s*', line)
        if match and match.group(1).strip() not in names:
            names.append(match.group(1).strip())
    return names


def participants(transcript):
    meta = teams_metadata(transcript)
    return meta.get('participants') or _speaker_names(transcript)


def _participant_vocabulary(transcript):
    words = set()
    for name in participants(transcript):
        words.update(_tokens(name))
    return words


def is_ambiguous_source_title(title, transcript=''):
    plain = _plain(title)
    if not plain or plain in GENERIC_TITLES or re.fullmatch(r'(?:teams )?meeting(?: transcription)?(?: \d+)?', plain):
        return True
    if re.search(r'\bund \d+ andere\b', plain):
        return True
    words = [word for word in _tokens(title) if word not in _TITLE_FILLERS and not word.isdigit()]
    people = _participant_vocabulary(transcript)
    if people and words and set(words) <= people:
        return True
    # With no participant header at all, retain a narrow fallback for the
    # observed Teams one-to-one form "Surname, Given".
    if not people and re.fullmatch(r"[\wÀ-ÖØ-öø-ÿ.' -]{2,40},\s*[\wÀ-ÖØ-öø-ÿ.' -]{2,40}", (title or '').strip()) and not set(words)&_TITLE_FILLERS:
        return True
    return False


def _grounded(title, passages, transcript):
    if not isinstance(title, str) or not 5 <= len(title.strip()) <= 120 or '\n' in title or '\r' in title:
        return False
    if is_ambiguous_source_title(title, transcript):
        return False
    evidence = _plain(' '.join(passages))
    significant = [word for word in _tokens(title) if word not in _GROUNDING_FILLERS and not word.isdigit()]
    if not significant:
        return False
    evidence_words = set(evidence.split())
    # Accept inflection, but no invented topic: each content word needs a
    # literal or same-stem witness in the cited original passages.
    return all(word in evidence_words or (
        len(word) >= 6 and any(other.startswith(word[:5]) or word.startswith(other[:5]) for other in evidence_words)
    ) for word in significant)


def title_from_response(value, originals, transcript):
    """Validate a same-call title proposal and retain its exact evidence."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'text', 'evidence_ids'}:
        return None
    ids = value.get('evidence_ids')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 4 or any(not isinstance(i, str) or i not in originals for i in ids):
        return None
    passages = [originals[i]['text'] for i in dict.fromkeys(ids)]
    text = value.get('text', '').strip() if isinstance(value.get('text'), str) else ''
    if not _grounded(text, passages, transcript):
        return None
    return {'text': text, 'passages': passages, 'method': 'same_call_source_cited_title'}


def _fallback_people(source_title, transcript):
    if source_title and is_ambiguous_source_title(source_title, transcript) and _plain(source_title) not in GENERIC_TITLES and not re.search(r'\bund \d+ andere\b', _plain(source_title)):
        value=source_title.strip()
        prior=None
        while value!=prior:
            prior=value
            value=re.sub(r'^(?:1\s*[:x]\s*1|jf|jour fixe|teams|meeting)\s*[-:/x]*\s*', '', value, flags=re.I).strip()
        pair=[part.strip() for part in re.split(r'\s*(?:/|\bx\b)\s*',value,flags=re.I) if part.strip()]
        pair=[part for part in pair if _plain(part) not in ('gleb','gleb komzin','komzin gleb')]
        if pair:value=' und '.join(pair)
        comma=re.fullmatch(r"([\wÀ-ÖØ-öø-ÿ.' -]{2,40}),\s*([\wÀ-ÖØ-öø-ÿ.' -]{2,40})",value)
        if comma:value=f'{comma.group(2).strip()} {comma.group(1).strip()}'
        if value:
            return value
    names = participants(transcript)
    others = [name for name in names if _plain(name) not in _OWNER_NAMES]
    chosen = others or names
    if not chosen:
        return ''
    return ', '.join(chosen[:2]) + (f' und {len(chosen) - 2} weitere' if len(chosen) > 2 else '')


def _date_label(event_date):
    try:
        return date.fromisoformat(event_date[:10]).strftime('%d.%m.%Y')
    except (TypeError, ValueError, AttributeError):
        return ''


def reviewed_no_topic_title(kind, transcript, event_date, passages=()):
    """Return the single honest label allowed for a reviewed short no-topic record."""
    if kind not in {'no_transcribed_content', 'conversation_ended_before_topic'} or len(transcript or '') > 700:
        return None
    if not isinstance(passages, (list, tuple)) or any(not isinstance(item, str) or item not in transcript for item in passages):
        return None
    day = _date_label(event_date)
    label = 'Aufzeichnung ohne Gesprächsinhalt' if kind == 'no_transcribed_content' else 'Gespräch ohne fachliches Thema'
    return label + (f' · {day}' if day else '')


def resolve_display_title(source_title, transcript, event_date, *, note_payloads=()):
    """Return display title plus transparent provenance, never changing identity."""
    if not is_ambiguous_source_title(source_title, transcript):
        return {'text': source_title, 'method': 'source_title', 'evidence': []}
    for payload in note_payloads:
        candidate = payload.get('display_title') if isinstance(payload, dict) else None
        if isinstance(candidate, dict) and candidate.get('method') == 'same_call_source_cited_title':
            passages = candidate.get('passages')
            text = candidate.get('text')
            if isinstance(passages, list) and all(isinstance(p, str) and p in transcript for p in passages) and _grounded(text, passages, transcript):
                return {'text': text.strip(), 'method': candidate['method'], 'evidence': passages}
        if isinstance(candidate, dict) and candidate.get('method') == 'reviewed_no_topic':
            passages = candidate.get('passages')
            text = reviewed_no_topic_title(candidate.get('exception'), transcript, event_date, passages)
            if text is not None and candidate.get('text') == text:
                return {'text': text, 'method': candidate['method'], 'evidence': list(passages)}
    # Older notes can carry useful topic headings.  Use one only when its
    # content words are literally grounded in this original transcript.
    for payload in note_payloads:
        for topic in payload.get('topics', []) if isinstance(payload, dict) else []:
            text = topic.get('name') if isinstance(topic, dict) else topic
            if isinstance(text, str) and _grounded(text.strip(), [transcript], transcript):
                return {'text': text.strip(), 'method': 'grounded_archived_topic', 'evidence': []}
    # Do not turn speech fragments into titles. Existing sources without a
    # cited title or grounded archived topic get an explicit uncertainty label.
    person = _fallback_people(source_title, transcript)
    day = _date_label(event_date)
    parts = ['Thema offen'] + ([f'Gespräch mit {person}'] if person else []) + ([day] if day else [])
    return {'text': ' · '.join(parts)[:160], 'method': 'transparent_fallback', 'evidence': []}
