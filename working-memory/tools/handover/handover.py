#!/usr/bin/env python3
"""Offline, source-bound working-memory handover. Stdlib only."""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
from datetime import date
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parents[1] / 'evaluation/sol-operational-release-20261006/backend'
MEMBERS = ('canonical/journal.jsonl', 'canonical/notes.jsonl', 'canonical/documents.jsonl')
MAX_RELATED = 8
MAX_MEETINGS = 5
MAX_REUSE = 5
MAX_PACKAGE_BYTES = 20_000
MAX_LINE_CHARS = 400
MAX_PACKAGE_LINES = 150
MAX_EVIDENCE = 12
REQUIRED_FIELDS = ('worum', 'naechster', 'fertig_wenn', 'art', 'bearbeitungsweg', 'scope',
                   'wiederverwendung', 'alias_begriffe', 'kontext', 'vorarbeiten_und_vorgespraeche',
                   'offene_fragen', 'abnahme', 'belege', 'reife')
# Ordered deterministic heuristics, not empirical probabilities or authorizations.
RULES = (
    ('power-bi-modell', ('datenmodell', 'modell', 'measure', 'dax'), 'ki', .85),
    ('power-bi-bericht', ('power bi', 'power-bi', 'bericht'), 'ki', .75),
    ('review', ('review', 'prüfen', 'pruefen', 'überprüfen'), 'ki', .80),
    ('entwurf', ('e-mail', 'email', 'mail', 'antwort'), 'ki', .80),
    ('erinnerung', ('erinnern', 'nachfassen', 'nachfragen'), 'selbst', .80),
)
STOPWORDS = frozenset('aber alle als auch auf aus bei das dass dem den der des die ein eine einer eines für hat im in ist mit nach nicht oder sich sind und vom von vor war werden wird zu zum zur'.split())

class HandoverError(ValueError):
    """Messages intentionally contain no meeting contents or identities."""

@dataclass
class Memory:
    tasks: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    db: object = None
    archive: str = 'synthetisch'
    logical_entries: list = field(default_factory=list)
    source_addresses: dict = field(default_factory=dict)
    command_addresses: dict = field(default_factory=dict)
    revision: int = 0
    snapshot_address: str = ''


def assertion(value='unbekannt', maturity='unbekannt', sources=None, **extra):
    if value is None or value == '' or value == []:
        value, maturity = 'unbekannt', 'unbekannt'
    return {'wert': value, 'reife': maturity, 'belege': list(sources or []), **extra}


def extract_terms(text):
    """Only verbatim source tokens/phrases, no inferred synonyms."""
    words = re.findall(r'[\wÄÖÜäöüß]+(?:[-_][\wÄÖÜäöüß]+)*', str(text), re.UNICODE)
    terms, seen = [], set()
    for phrase in re.findall(r'Power[ -]BI|Datenmodell|[A-ZÄÖÜ][A-ZÄÖÜ_]{1,}', str(text)) + words:
        key = phrase.casefold()
        if len(key) >= 3 and key not in STOPWORDS and key not in seen and not key.isdecimal():
            seen.add(key); terms.append(phrase)
    return terms[:24]


def _backend():
    if not BACKEND.is_dir(): raise HandoverError('E_BACKEND')
    # Explicit trusted local path works under -I; no installed external packages.
    if str(BACKEND) not in sys.path: sys.path.insert(0, str(BACKEND))
    import generation_review, memory, planner, corrections
    corrections.RULES = ROOT.parents[1] / 'evaluation/source-corrections.json'
    return generation_review, memory, planner


def _records(archive, member):
    process = subprocess.Popen(['tar', '-xzOf', str(archive), member], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
    try:
        previous_sequence = 0
        previous_revision = 0
        for number, line in enumerate(process.stdout, 1):
            if not line.strip(): continue
            try:
                outer = json.loads(line)
                if 'record_json' in outer:
                    raw = outer['record_json']
                    if not isinstance(raw, str): raise ValueError()
                    if 'record_hash' in outer and hashlib.sha256(raw.encode()).hexdigest() != outer['record_hash']: raise ValueError()
                    if 'sequence' in outer:
                        if type(outer['sequence']) is not int or outer['sequence'] != previous_sequence + 1: raise ValueError()
                        previous_sequence = outer['sequence']
                record = json.loads(outer['record_json']) if isinstance(outer.get('record_json'), str) else outer
                if not isinstance(record, dict): raise ValueError()
                if member == MEMBERS[0]:
                    revision = record.get('revision')
                    if type(revision) is not int or revision != previous_revision + 1: raise ValueError()
                    previous_revision = revision
            except (ValueError, TypeError, KeyError): raise HandoverError('E_JSONL') from None
            yield record, f'{archive.name}/{member}:L{number}'
        if process.wait() != 0: raise HandoverError('E_ARCHIVE_MEMBER')
    finally:
        process.stdout.close()
        if process.poll() is None: process.terminate(); process.wait()


def load_archive(path_or_auto='auto'):
    if str(path_or_auto) == 'auto':
        base = Path.home() / 'Library/Application Support/Dashboard Job Backup/archives'
        candidates = sorted(p for p in base.glob('dashboard-*.tar.gz')
                            if re.fullmatch(r'dashboard-\d{8}T\d{6}Z\.tar\.gz', p.name))
        if not candidates: raise HandoverError('E_NO_ARCHIVE')
        archive = candidates[-1]
    else: archive = Path(path_or_auto).expanduser()
    if not archive.is_file(): raise HandoverError('E_NO_ARCHIVE')
    mem = Memory(archive=archive.name)
    entries = []
    latest_generation = None
    source_after_generation = set()
    human_after_generation = set()
    for entry, address in _records(archive, MEMBERS[0]):
        entries.append(entry)
        mem.revision = entry['revision']
        mem.snapshot_address = address
        if entry['kind'] == 'source':
            mem.source_addresses[entry['source']['id']] = address
            source_after_generation.add(entry['source']['id'])
        if entry['kind'] == 'human':
            mem.command_addresses[entry['command_id']] = address
            human_after_generation.add(entry['command_id'])
        if entry['kind'] in ('generation', 'redaction'):
            latest_generation = address
            source_after_generation.clear(); human_after_generation.clear()
    replay, backend, planner = _backend()
    try:
        mem.logical_entries = replay.logical_entries(entries)
        # A generation may alter previously retained source fields. Its accepted
        # binding, not an obsolete source record, then proves the current value.
        if latest_generation:
            for entry in mem.logical_entries:
                if entry['kind'] == 'source' and entry['source']['id'] not in source_after_generation:
                    mem.source_addresses[entry['source']['id']] = latest_generation
                if entry['kind'] == 'human' and entry['command_id'] not in human_after_generation:
                    mem.command_addresses[entry['command_id']] = latest_generation
        mem.db, _ = replay.materialize(mem.logical_entries)
        state = planner.overlay(mem.db, backend.overview(mem.db), '9999-12-31')
        mem.tasks = [item for group in replay.GROUPS for item in state.get(group, [])]
    except Exception:
        if mem.db: mem.db.close()
        raise HandoverError('E_RECONSTRUCTION') from None
    from canonical_archive import verify_document, verify_note
    try:
        for member, target, verify in ((MEMBERS[1], mem.notes, verify_note), (MEMBERS[2], mem.documents, verify_document)):
            for record, address in _records(archive, member):
                verified = verify(record)
                # Export is validated then discarded; body remains the sole copy.
                verified.pop('export', None)
                target.append({**verified, '_address': address})
    except Exception:
        mem.db.close()
        raise HandoverError('E_CANONICAL_ARCHIVE') from None
    return mem


def select_task(memory, query):
    tasks = list(memory.tasks.values()) if isinstance(memory.tasks, dict) else memory.tasks
    exact = [t for t in tasks if t.get('id') == query]
    if exact: return exact[0]
    needle = str(query).strip().casefold()
    if not needle: raise HandoverError('E_EMPTY_QUERY')
    found = [t for t in tasks if needle in ' '.join(str(t.get(k) or '') for k in ('title', 'claim', 'matter', 'owner')).casefold()]
    if len(found) != 1: raise HandoverError('E_AMBIGUOUS_QUERY' if found else 'E_NO_TASK')
    return found[0]


def _sources(memory, task):
    refs = []
    for event in task.get('history', []):
        version = event.get('source_version')
        if version:
            refs.append(f"{memory.source_addresses.get(version, memory.archive+'/canonical/journal.jsonl')}; source_version={version}; content_hash={event.get('content_hash', 'unbekannt')}; work={task.get('id', 'unbekannt')}; event={event.get('event_date', 'unbekannt')}; action={event.get('action', 'unbekannt')}")
    for event in [*task.get('planning_history', []), *task.get('history', []), *task.get('human_history', []), *task.get('human_decision_history', [])]:
        command = event.get('command_id')
        if command: refs.append(f"{memory.command_addresses.get(command, memory.archive+'/canonical/journal.jsonl')}; command_id={command}")
    return list(dict.fromkeys(refs))


def classify(task, sources=None):
    text = ' '.join(str(task.get(k) or '') for k in ('title', 'claim', 'matter')).casefold()
    matches = []
    for art, keywords, way, confidence in RULES:
        hits = [word for word in keywords if re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text)]
        if hits: matches.append((art, way, confidence, hits))
    # Broad report keywords do not compete with a more specific BI-model rule.
    if any(m[0] == 'power-bi-modell' for m in matches):
        matches = [m for m in matches if m[0] != 'power-bi-bericht']
    if len(matches) != 1: return assertion(konfidenz=0), assertion(konfidenz=0)
    art, way, confidence, hits = matches[0]
    owner = re.sub(r'[^a-z]+', ' ', (task.get('owner') or '').lower()).strip()
    if not owner: return assertion(art, 'Annahme', sources, konfidenz=confidence), assertion(konfidenz=0)
    if owner not in ('gleb', 'gleb komzin', 'komzin gleb'):
        way = 'delegieren'
    reason = {'weg': way, 'begruendung': 'Deterministische Schlüsselwortregel; Besitzerregel bei belegtem fremdem Besitzer.',
              'treffer': hits, 'besitzer': task.get('owner') or 'unbekannt', 'konfidenz': confidence}
    return assertion(art, 'Annahme', sources, konfidenz=confidence), assertion(reason, 'Annahme', sources, konfidenz=confidence)


def _event_sources(memory, event):
    refs = []
    version = event.get('source_version')
    if version and version in memory.source_addresses:
        refs.append(memory.source_addresses[version] + '; source_version=' + version)
    command = event.get('command_id')
    if command and command in memory.command_addresses:
        refs.append(memory.command_addresses[command] + '; command_id=' + command)
    return refs


def _field_sources(memory, task):
    """Follow field updates, then require equality to the actual read-model value.

    Source history omits titles/work_state. Read the accepted work observation,
    never treat a progress report's title as a replacement task title.
    Human project runs after source overview; manual lifecycle uses replay order.
    """
    candidates = {}
    def put(key, value, refs):
        candidates[key] = (value, refs)
    source_events = [e for e in task.get('history', []) if e.get('source_version')]
    for index, event in enumerate(source_events):
        refs = _event_sources(memory, event)
        data = {}
        if memory.db:
            rows = memory.db.execute("""SELECT e.data_json FROM work_events e
              JOIN observations o ON o.id=e.observation_id
              WHERE e.work_id=? AND o.source_version=? AND e.action=?""",
              (task.get('id'), event['source_version'], event.get('action'))).fetchall()
            matching = [json.loads(r[0]) for r in rows if json.loads(r[0]).get('claim') == event.get('claim')]
            if len(matching) == 1: data = matching[0]
            if not data:
                row = memory.db.execute('SELECT data_json FROM observations WHERE id=? AND source_version=?',
                                        (task.get('id'), event['source_version'])).fetchone()
                if row: data = json.loads(row[0])
        action = event.get('action')
        if index == 0:
            for key in ('title', 'owner', 'matter', 'matter_id', 'subject'):
                if key in data: put(key, data[key], refs)
            put('id', task.get('id'), refs)
            put('status', data.get('work_state') if data.get('work_state') in ('waiting','done') else 'open', refs)
        for key in ('claim', 'quotes'):
            if key in data or key in event: put(key, data.get(key, event.get(key)), refs)
        if 'subject' in data: put('subject', data['subject'], refs)
        if action == 'owner_changed': put('owner', data.get('owner', event.get('owner')), refs)
        prior_status = candidates.get('status', ('unbekannt', []))[0]
        if action == 'done': put('status', 'done', refs)
        elif action == 'reopened': put('status', 'waiting' if data.get('work_state') == 'waiting' else 'open', refs)
        elif action == 'progress' and prior_status != 'done' and data.get('work_state') in ('open','waiting'):
            put('status', data['work_state'], refs)
        elif action == 'condition_met' and prior_status != 'done': put('status', 'open', refs)
        put('last_changed', event.get('event_date'), refs)
    humans = [e for e in task.get('history', []) if e.get('command_id')]
    humans += task.get('human_history', []) + task.get('human_decision_history', [])
    for event in humans:
        if event.get('action') == 'reject': continue
        refs = _event_sources(memory, event)
        for key, value in event.get('patch', {}).items(): put(key, value, refs)
        put('last_changed', event.get('event_date'), refs)
    for event in task.get('planning_history', []):
        refs = _event_sources(memory, event)
        if event.get('action') == 'create_task':
            put('id', task.get('id'), refs); put('status', 'open', refs)
            put('matter', 'Eigene Planung', refs)
        for key, value in event.get('patch', {}).items(): put(key, value, refs)
        put('last_changed', event.get('event_date'), refs)
    if task.get('origin') == 'manual':
        if 'note' in candidates: candidates['claim'] = candidates['note']
        # Manual lifecycle fields can be updated by later accepted sources or
        # human decisions. Select their replay sequence, as planner.overlay does.
        if memory.db:
            from projection_order import sequence
            lifecycle = []
            for event in [*task.get('planning_history', []), *source_events, *humans]:
                refs = _event_sources(memory, event)
                kind = 'source' if event.get('source_version') else ('planning' if event in task.get('planning_history', []) else 'human')
                identity = event.get('source_version') or event.get('command_id')
                if not identity: continue
                seq = sequence(memory.db, kind, identity)
                patch = event.get('patch', {})
                for key in ('owner','status'):
                    if key in patch: lifecycle.append((seq, key, patch[key], refs))
                action = event.get('action')
                if action == 'owner_changed': lifecycle.append((seq,'owner',event.get('owner'),refs))
                if action in ('done','condition_met','create_task'):
                    lifecycle.append((seq,'status','done' if action == 'done' else 'open',refs))
            for _, key, value, refs in sorted(lifecycle, key=lambda x:x[0]): put(key,value,refs)
    # Topic aliases may change via a separate accepted topic command. Without
    # exact field evidence retain unknown rather than attaching every source.
    changed_refs = [r for event in [*task.get('history', []), *task.get('planning_history', [])] if event.get('event_date') == task.get('last_changed') for r in _event_sources(memory, event)]
    if changed_refs: put('last_changed', task.get('last_changed'), changed_refs)
    return {key: refs for key, (value, refs) in candidates.items()
            if value == task.get(key) and refs}


def _explicit(task, labels, field_sources):
    for label in labels:
        if task.get(label):
            refs = field_sources.get(label, [])
            return assertion(task[label], 'belegt', [r + '; field=' + label for r in refs]) if refs else assertion()
    texts = [(task.get('note', ''), field_sources.get('note', []), 'note')]
    for quote in task.get('quotes', []):
        texts.append((quote if isinstance(quote, str) else quote.get('quote', ''), field_sources.get('quotes', []), 'quotes'))
    aliases = {'naechster': ('naechster', 'nächster Schritt', 'nächster'), 'fertig_wenn': ('fertig_wenn', 'Fertig, wenn'),
               'scope': ('scope', 'Umfang'), 'abnahme': ('abnahme', 'Abnahme'), 'wiederverwendung': ('wiederverwendung', 'Wiederverwendung')}
    for label in labels:
        for spelling in aliases.get(label, (label,)):
            pattern = r'(?:^|\n)\s*(?:[-*]\s*)?' + re.escape(spelling) + r'\s*:\s*([^\n]+)'
            for text, refs, field_name in texts:
                match = re.search(pattern, str(text), re.I)
                if match and refs:
                    return assertion(match.group(1).strip(), 'belegt', [r + '; field=' + field_name + '; task-bound label=' + spelling for r in refs])
    return assertion()


def _plain_quotes(task):
    result = []
    for event in task.get('history', []):
        for q in event.get('quotes', []):
            quote = q if isinstance(q, str) else q.get('quote', '')
            if quote: result.append((event, quote))
    return result


def build_package(memory, task):
    sources = _sources(memory, task)
    field_sources = _field_sources(memory, task)
    def fact(value, field_name, refs=None):
        refs = field_sources.get(field_name, []) if refs is None else refs
        return assertion(value, 'belegt', [r + '; field=' + field_name for r in refs]) if refs else assertion()
    package = {'worum': fact(task.get('title') or task.get('claim'), 'title' if task.get('title') else 'claim'),
               'naechster': _explicit(task, ('naechster', 'next_step'), field_sources),
               'fertig_wenn': _explicit(task, ('fertig_wenn', 'done_when'), field_sources),
               'scope': _explicit(task, ('scope',), field_sources),
               'wiederverwendung': _explicit(task, ('wiederverwendung',), field_sources),
               'alias_begriffe': fact(extract_terms(' '.join(str(task.get(k) or '') for k in ('title','claim','matter') if field_sources.get(k))), 'title/claim/matter', list(dict.fromkeys(r + '; input_field=' + k for k in ('title','claim','matter') for r in field_sources.get(k, [])))),
               'abnahme': _explicit(task, ('abnahme', 'acceptance'), field_sources)}
    package['art'], package['bearbeitungsweg'] = classify(task, sources)
    package['aufgabe'] = {k: fact(task.get(k), k) for k in ('id', 'status', 'owner', 'last_changed')}
    package['aufgabe']['archiv'] = assertion(memory.archive, 'belegt', [memory.snapshot_address or memory.archive + '/canonical/journal.jsonl'])
    package['aufgabe']['journal_revision'] = assertion(memory.revision, 'belegt', [memory.snapshot_address]) if memory.snapshot_address else assertion()
    package['verlauf'] = []
    for event in [*task.get('history', []), *task.get('planning_history', []), *task.get('human_history', []), *task.get('human_decision_history', [])]:
        refs = _event_sources(memory, event)
        package['verlauf'].append({k: fact(v, 'event.' + k, refs) for k, v in event.items()})
    if not package['verlauf']: package['verlauf'] = assertion()
    theme = task.get('matter') or task.get('subject')
    package['kontext'] = {'thema': fact(theme, 'matter' if task.get('matter') else 'subject'), 'personen': [fact(task.get('owner'), 'owner')], 'meetings': []}
    terms = {w.casefold() for w in extract_terms(' '.join(str(task.get(k) or '') for k in ('title','claim','matter')))}
    tasks = list(memory.tasks.values()) if isinstance(memory.tasks, dict) else memory.tasks
    related = []
    for other in tasks:
        if other.get('id') == task.get('id'): continue
        overlap = sorted(terms & {w.casefold() for w in extract_terms(' '.join(str(other.get(k) or '') for k in ('title','claim','matter')))})
        same_theme = bool(task.get('matter_id') and task.get('matter_id') == other.get('matter_id'))
        same_owner = bool(task.get('owner') and task.get('owner') == other.get('owner'))
        if same_theme or same_owner or len(overlap) >= 2:
            refs = _sources(memory, other)
            other_fields = _field_sources(memory, other)
            related.append({'id': fact(other.get('id'), 'id', other_fields.get('id', [])), 'titel': fact(other.get('title'), 'title', other_fields.get('title', [])),
                            'status': fact(other.get('status'), 'status', other_fields.get('status', [])),
                            'aehnlichkeit': assertion({'gleiches_thema': same_theme, 'gleicher_besitzer': same_owner,
                                                       'begriffsueberlappung': overlap}, 'Annahme', refs),
                            'vorarbeit': assertion(), '_rank': (-int(same_theme), -len(overlap), -int(same_owner), str(other.get('id','')))})
    related.sort(key=lambda item: item['_rank'])
    related_total = len(related)
    related = related[:MAX_RELATED]
    for item in related: item.pop('_rank')
    package['verwandte_aufgaben'] = related if related else assertion('keine gefunden', 'belegt', sources)
    raw_cutoff = max((e.get('event_date', '') for e in task.get('history', [])), default=task.get('last_changed', ''))
    try: cutoff = date.fromisoformat(raw_cutoff).isoformat()
    except (ValueError, TypeError): cutoff = None
    canonical = {}
    document_ids = {}
    for doc in memory.documents:
        if isinstance(doc.get('body'), str):
            document_ids.setdefault((doc['source_id'], doc['body_hash']), set()).add(doc['id'])
            canonical[(doc['source_id'], doc['body_hash'])] = {**doc, 'ref': doc.get('_address', memory.archive + '/canonical/documents.jsonl') + '; document_id=' + doc['id'] + '; body_hash=' + doc['body_hash'], 'matter_ids': set(), 'matters': set()}
    for entry in memory.logical_entries:
        if entry.get('kind') != 'source': continue
        src = entry['source']; key = (src['source_id'], src['content_hash'])
        item = canonical.setdefault(key, {'id': None, 'source_id': src['source_id'], 'body_hash': src['content_hash'],
                       'body': src['transcript'], 'title': src['title'], 'event_date': src['event_date'],
                       'ref': memory.source_addresses.get(src['id'], memory.archive + '/canonical/journal.jsonl') + '; source_version=' + src['id'] + '; content_hash=' + src['content_hash'], 'matter_ids': set(), 'matters': set()})
        for observation in entry['payload'].get('proposal', {}).get('observations', []):
            if observation.get('matter'): item['matters'].add(observation['matter'])
        if memory.db:
            item['matter_ids'].update(r[0] for r in memory.db.execute('SELECT matter_id FROM observations WHERE source_version=?', (src['id'],)))
    meetings, reuse = [], []
    selected_docs = set()
    existence = re.compile(r'\b(?:vorhanden\w*|bestehend\w*|bereits erstellt|hat[^.\n]{0,100}erstellt|ist[^.\n]{0,100}erstellt)\b', re.I)
    for doc in canonical.values():
        if not cutoff: continue
        try: day = date.fromisoformat(doc['event_date']).isoformat()
        except (ValueError, TypeError): continue
        if day >= cutoff: continue
        body = doc['body']
        title_body = doc['title'] + ' ' + body
        matching = sorted(w for w in terms if re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', title_body, re.I))
        thematic = bool((task.get('matter_id') and task['matter_id'] in doc['matter_ids']) or (theme and theme in doc['matters']))
        if not thematic and len(matching) < 2: continue
        selected_docs.update(document_ids.get((doc['source_id'], doc['body_hash']), set()))
        body_hits = [w for w in matching if re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', body, re.I)]
        if not body_hits: continue
        found = re.search(r'(?<!\w)' + re.escape(body_hits[0]) + r'(?!\w)', body, re.I)
        start = max(0, found.start() - 80); passage = body[start:start + 300]
        refs = [doc['ref']]
        meetings.append({'titel': fact(doc['title'], 'title', refs), 'datum': fact(day, 'event_date', refs),
                         'passage': {**fact(passage, f'body[{start}:{start+len(passage)}]', refs), 'rolle': 'passage'},
                         'thematische_zuordnung': assertion({'begriffe': matching, 'kanonisches_thema': thematic}, 'Annahme', refs),
                         'stand': fact(cutoff, 'last_task_evidence', [r for e in task.get('history', []) if e.get('event_date') == cutoff for r in _event_sources(memory, e)])})
        for match in existence.finditer(body):
            start = max(0, body.rfind('.', 0, match.start()) + 1)
            stop = body.find('.', match.end()); stop = len(body) if stop < 0 else stop + 1
            quote = body[start:stop].strip()
            if any(re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', quote, re.I) for w in terms):
                reuse.append({'bestandsaussage': fact(quote, 'body literal existence statement', refs),
                             'eignung_fuer_aufgabe': assertion(), 'zuordnung': assertion('thematischer Suchfund', 'Annahme', refs)})
    meetings.sort(key=lambda item: (item['datum']['wert'], item['titel']['wert'], item['passage']['belege']), reverse=True)
    meetings_total = len(meetings)
    meetings = meetings[:MAX_MEETINGS]
    retained_refs = {ref.split(';')[0] for item in meetings for ref in item['passage']['belege']}
    selected_docs = {doc['id'] for doc in memory.documents if doc.get('_address') in retained_refs}
    reuse = [item for item in reuse if any(ref.split(';')[0] in retained_refs for ref in item['bestandsaussage']['belege'])]
    def note_leaves(value, path='note'):
        if isinstance(value, dict):
            for key, child in value.items(): yield from note_leaves(child, path + '.' + key)
        elif isinstance(value, list):
            for index, child in enumerate(value): yield from note_leaves(child, path + '[' + str(index) + ']')
        elif isinstance(value, str): yield path, value
    for note in memory.notes:
        if note.get('document_id') not in selected_docs or not note.get('note_json'): continue
        refs = [note.get('_address', memory.archive + '/canonical/notes.jsonl') + '; note_id=' + note['id'] + '; note_hash=' + note['note_hash']]
        value = json.loads(note['note_json'])
        for path, text in note_leaves(value):
            if existence.search(text):
                reuse.append({'bestandsaussage': fact(text, path, refs), 'eignung_fuer_aufgabe': assertion(),
                             'zuordnung': assertion('Notiz am thematisch zugeordneten Dokument', 'Annahme', refs)})
            if '.participants' in path or '.teilnehmer' in path:
                package['kontext']['personen'].append(fact(text, path, refs))
    reuse_total = len(reuse)
    reuse = reuse[:MAX_REUSE]
    package['suchmetadaten'] = {key: {'kandidaten': total, 'angezeigt': min(total, limit), 'ausgelassen': max(0,total-limit)} for key, total, limit in (('verwandte_aufgaben',related_total,MAX_RELATED),('vorgespraeche',meetings_total,MAX_MEETINGS),('wiederverwendung',reuse_total,MAX_REUSE))}
    if reuse:
        explicit = package['wiederverwendung']
        package['wiederverwendung'] = ([explicit] if explicit['reife'] != 'unbekannt' else []) + reuse
    empty_meetings = assertion('keine gefunden', 'belegt', sources) if cutoff else assertion()
    package['kontext']['meetings'] = meetings if meetings else empty_meetings
    package['vorarbeiten_und_vorgespraeche'] = meetings if meetings else empty_meetings
    questions = [f'{name}: unbekannt' for name, value in package.items()
                 if isinstance(value, dict) and value.get('reife') == 'unbekannt']
    if cutoff is None: questions.append('Zeitstand: unbekannt; frühere Meetings nicht bestimmbar')
    package['offene_fragen'] = assertion(questions if questions else 'keine gefunden', 'Annahme', [],
                                        regel='fehlende explizite Pflichtfelder')
    evidence = []; maturity = {}
    def walk(value, path):
        if isinstance(value, dict) and 'reife' in value and 'wert' in value:
            maturity[path] = value['reife']
            for ref in value.get('belege', []): evidence.append({'quelle': ref, 'aussage': path})
        elif isinstance(value, dict):
            for key, item in value.items(): walk(item, path + '.' + key)
        elif isinstance(value, list):
            for index, item in enumerate(value): walk(item, path + '[' + str(index) + ']')
    for key, value in package.items(): walk(value, key)
    package['belege'] = evidence; package['reife'] = maturity
    return package


def _short_text(value, limit):
    """Literal prefix, whitespace normalized; never silently summarize."""
    text = ' '.join(str(value).split())
    length = len(text)
    if length > limit:
        text = text[:limit - 1] + '…'
    # A quoted JSON token cannot be split over physical lines. Escaped quotes
    # and backslashes also need to fit, regardless of character/byte ratio.
    while len(json.dumps(text, ensure_ascii=False)) > 320:
        text = text[:-2] + '…'
    return text, max(0, length - len(text.rstrip('…')))


def _assertion_paths(value, path=''):
    if isinstance(value, dict) and 'wert' in value and 'reife' in value:
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _assertion_paths(item, path + '.' + key if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _assertion_paths(item, path + '[' + str(index) + ']')


def _compact_package(package, text_limit, passage_limit):
    """Bound the presentation, keeping the original reconstructed data intact."""
    def bounded(value, limit):
        if isinstance(value, str): return _short_text(value, limit)[0]
        if isinstance(value, list): return [bounded(v, min(limit, 40)) for v in value[:12]]
        if isinstance(value, dict): return {k: bounded(v, min(limit, 120)) for k, v in value.items()}
        return value

    def leaf(value, limit=None):
        value = value if isinstance(value, dict) and 'wert' in value else assertion()
        limit = text_limit if limit is None else limit
        result = assertion(bounded(value['wert'], limit), value['reife'],
                           list(dict.fromkeys(r.split(';', 1)[0] for r in value.get('belege', []))))
        if isinstance(value['wert'], str):
            _, omitted = _short_text(value['wert'], limit)
            if omitted: result['gekuerzte_zeichen'] = omitted
        if isinstance(value['wert'], list) and len(value['wert']) > 12:
            result['weitere'] = len(value['wert']) - 12
        if 'konfidenz' in value: result['konfidenz'] = value['konfidenz']
        return result

    result = {name: leaf(package[name]) for name in
              ('worum', 'naechster', 'fertig_wenn', 'art', 'bearbeitungsweg',
               'scope', 'alias_begriffe', 'offene_fragen', 'abnahme')}
    result['aufgabe'] = {k: leaf(v, 120) for k, v in package.get('aufgabe', {}).items()}
    context = package.get('kontext', {})
    result['kontext'] = {'thema': leaf(context.get('thema')),
                         'personen': [leaf(v, 100) for v in context.get('personen', [])[:5]]}
    meetings = package['vorarbeiten_und_vorgespraeche']
    result['vorarbeiten_und_vorgespraeche'] = [
        {k: leaf(item.get(k), passage_limit if k == 'passage' else 120)
         for k in ('titel', 'datum', 'passage')} for item in meetings[:MAX_MEETINGS]
    ] if isinstance(meetings, list) else leaf(meetings)
    related = package.get('verwandte_aufgaben', [])
    result['verwandte_aufgaben'] = [leaf(item.get('titel'), 120) for item in related[:MAX_RELATED]] if isinstance(related, list) else leaf(related)
    reuse = package['wiederverwendung']
    result['wiederverwendung'] = [
        {'bestandsaussage': leaf(item.get('bestandsaussage', item)),
         'eignung_fuer_aufgabe': leaf(item.get('eignung_fuer_aufgabe'))}
        for item in reuse[:MAX_REUSE]
    ] if isinstance(reuse, list) else leaf(reuse)
    # Total hits are numbers, not duplicated meeting objects or histories.
    result['trefferzahlen'] = {k: v['kandidaten'] for k, v in package.get('suchmetadaten', {}).items()}
    result['verlauf_ereignisse'] = len(package['verlauf']) if isinstance(package.get('verlauf'), list) else 0

    # Direct task sources precede meetings (already sorted newest first), then
    # other sources. One entry per canonical archive line, no hash repetition.
    direct = set()
    for name in ('worum', 'naechster', 'fertig_wenn', 'scope', 'abnahme', 'aufgabe', 'verlauf'):
        for _, item in _assertion_paths(package.get(name)):
            direct.update(r.split(';', 1)[0] for r in item.get('belege', []))
    addresses, statements = [], {}
    for path, item in _assertion_paths(result):
        for ref in item['belege']:
            if ref not in statements:
                addresses.append(ref); statements[ref] = []
            value = item['wert'] if isinstance(item['wert'], str) else json.dumps(item['wert'], ensure_ascii=False)
            statements[ref].append(path + ': ' + value)
    addresses.sort(key=lambda ref: 0 if ref in direct else 1)
    retained = addresses[:MAX_EVIDENCE]
    labels = {ref: 'B' + str(i) for i, ref in enumerate(retained, 1)}
    result['belege'] = [{'quelle': ref, 'aussage': _short_text('; '.join(statements[ref]), 200)[0]}
                        for ref in retained]
    for i, proof in enumerate(result['belege'], 1):
        if len(json.dumps(f'B{i} {proof["quelle"]} → ', ensure_ascii=False)) > 380:
            raise HandoverError('E_SOURCE_SIZE')
        while len(json.dumps(f'B{i} {proof["quelle"]} → {proof["aussage"]}', ensure_ascii=False)) > 390:
            proof['aussage'] = proof['aussage'][:-2] + '…'
    result['belege_weitere'] = len(addresses) - len(retained)
    for _, item in _assertion_paths(result):
        refs = item['belege']
        item['belege'] = [labels.get(r, r) for r in refs[:1]]
        if len(refs) > 1: item['belege_weitere'] = len(refs) - 1
    result['reife'] = {path: item['reife'] for path, item in _assertion_paths(result)}
    return result


def _flow_lines(prefix, value):
    """Wrap JSON only between tokens, preserving valid YAML flow values."""
    lines, current = [], prefix
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False)
    for token in encoder.iterencode(value):
        if len(current) + len(token) > MAX_LINE_CHARS:
            lines.append(current.rstrip()); current = '  '
        current += token
    lines.append(current.rstrip())
    return lines


def _render_compact(package):
    lines = ['---']
    for name, value in package.items():
        if name == 'belege':
            lines.append('belege:' if value else 'belege: []')
            for i, proof in enumerate(value, 1):
                lines += _flow_lines('  - ', f'B{i} {proof["quelle"]} → {proof["aussage"]}')
        else:
            lines += _flow_lines(name + ': ', value)
    lines += ['---', '', '# Auftragspaket',
              'Belegt bedeutet: im gesicherten Memory vorhanden; fachliche Live-Verifikation: unbekannt.',
              'Annahmen und unbekannte Pflichtfelder vor Ausführung prüfen. Lieferweg: unbekannt.',
              'Vault: _Index.md → _Alias.md (alias_begriffe) → 15 Zeilen Gist → gezielter Volltext.']
    if package['belege_weitere']:
        lines.append('… und ' + str(package['belege_weitere']) + ' weitere')
    return '\n'.join(lines) + '\n'


def presentation_package(package):
    if any(name not in package for name in REQUIRED_FIELDS): raise HandoverError('E_SCHEMA')
    # Fixed deterministic text budgets. No required field or selected entry is
    # removed to meet the size limit; all prefix cuts carry character counts.
    for text_limit, passage_limit in ((240, 300), (140, 200), (80, 120)):
        compact = _compact_package(package, text_limit, passage_limit)
        text = _render_compact(compact)
        if (len(text.encode('utf-8')) <= MAX_PACKAGE_BYTES
                and len(text.splitlines()) <= MAX_PACKAGE_LINES
                and max(map(len, text.splitlines()), default=0) <= MAX_LINE_CHARS):
            return compact
    raise HandoverError('E_SIZE')


def render_package(package):
    return _render_compact(presentation_package(package))


def package_stats(package, text):
    compact = presentation_package(package)
    states = compact['reife'].values()
    meetings = compact.get('vorarbeiten_und_vorgespraeche', [])
    return {'zeilen': len(text.splitlines()), 'belegt': sum(s == 'belegt' for s in states),
            'Annahme': sum(s == 'Annahme' for s in states), 'unbekannt': sum(s == 'unbekannt' for s in states),
            'vorgespraeche': len(meetings) if isinstance(meetings, list) else 0,
            'bytes': len(text.encode('utf-8')),
            'laengste_zeile': max(map(len, text.splitlines()), default=0)}


def write_package(text, destination):
    path = Path(destination).expanduser()
    if not path.is_absolute(): path = Path.cwd() / path
    if not path.resolve().is_relative_to(ROOT) or path == ROOT: raise HandoverError('E_OUTPUT_BOUNDARY')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() or path.is_symlink(): raise HandoverError('E_OUTPUT_EXISTS')
    descriptor, temporary = tempfile.mkstemp(prefix='.handover-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle: handle.write(text)
        # Hard-link creation is atomic and rejects an intervening existing file.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline handover generator')
    parser.add_argument('--archive', default='auto'); parser.add_argument('--task', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    started = time.monotonic(); memory = None
    try:
        memory = load_archive(args.archive)
        package = build_package(memory, select_task(memory, args.task))
        text = render_package(package); write_package(text, args.out)
        stats = package_stats(package, text); stats['sekunden'] = round(time.monotonic() - started, 3)
        # No task IDs, meeting content or filenames in console output.
        print(json.dumps(stats, ensure_ascii=False))
        return 0
    except Exception as error:
        print(str(error) if isinstance(error, HandoverError) else 'E_GENERATION', file=sys.stderr)
        return 2
    finally:
        if memory is not None and memory.db is not None: memory.db.close()

if __name__ == '__main__': raise SystemExit(main())
