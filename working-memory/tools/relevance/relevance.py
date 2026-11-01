"""Offline, non-destructive relevance projection of saved Working Memory tasks."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import math
from pathlib import Path
import re
import random
import statistics
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent / 'evaluation' / 'sol-operational-release-20261006' / 'backend'
ARCHIVES = Path.home() / 'Library/Application Support/Dashboard Job Backup/archives'
GROUPS = ('personal', 'waiting_dependencies', 'waiting', 'completed', 'cancelled')
STRONG_VERBS = re.compile(r'\b(?:senden|schicken|prüfen|abstimmen|erstellen|liefern|einreichen|freigeben|umsetzen|vorbereiten)\b', re.I)
WEAK_VERBS = re.compile(r'\b(?:schauen|ansehen|mal\s+sehen|klären\s+ob|überlegen)\b', re.I)
ISO_DATE = re.compile(r'(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)')
GERMAN_DATE = re.compile(r'(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)')


def load_config(path=None) -> dict:
    target = Path(path) if path is not None else HERE / 'config.json'
    config = json.loads(target.read_text(encoding='utf-8'))
    weights = config['weights']; thresholds = config['thresholds']
    if not isinstance(weights, dict) or not weights or not all(isinstance(k, str) and type(v) in (int, float) and math.isfinite(v) for k, v in weights.items()):
        raise ValueError('Invalid weights')
    if not (type(thresholds['standard']) in (int, float) and type(thresholds['wichtig']) in (int, float)
            and math.isfinite(thresholds['standard']) and math.isfinite(thresholds['wichtig'])
            and thresholds['standard'] < thresholds['wichtig']):
        raise ValueError('Invalid thresholds')
    return config


def classify(points, config):
    if points >= config['thresholds']['wichtig']:
        return 'wichtig'
    if points >= config['thresholds']['standard']:
        return 'standard'
    return 'kleinigkeit'


def _date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _due(task):
    direct = _date(task.get('due_date'))
    if direct:
        return direct
    expression = task.get('due_text') or ''
    match = ISO_DATE.search(expression)
    if match:
        return _date(match.group(1))
    match = GERMAN_DATE.search(expression)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass
    return None


def _owner_self(value):
    return bool(re.sub(r'[^a-z]+', ' ', (value or '').lower()).strip() in ('gleb', 'gleb komzin', 'komzin gleb'))


def _commitment(task):
    explicit = str(task.get('commitment_strength') or '').lower()
    if explicit in ('explicit', 'explicit_commitment', 'accepted_request', 'reported', 'reported_action', 'conditional', 'conditional_action', 'none', 'not_applicable'):
        return {'explicit': 'explicit_commitment', 'reported': 'reported_action', 'conditional': 'conditional_action'}.get(explicit, explicit)
    return None


def extract_features(task, context) -> dict[str, float]:
    """Only task evidence and explicitly supplied context determine features."""
    params = context.get('config', {}).get('feature_parameters', {})
    as_of = _date(context.get('as_of'))
    due = _due(task)
    history = task.get('history') or []
    sources = {entry.get('source_id') for entry in history if entry.get('source_id')}
    event_count = sum(1 for entry in history if entry.get('action') not in ('proposed',))
    topic = context.get('topics', {}).get(task.get('matter_id'), {})
    claim = str(task.get('claim') or '')
    strength = _commitment(task)
    last_changed = _date(task.get('last_changed'))
    days_old = (as_of - last_changed).days if as_of and last_changed else None
    delta = (due - as_of).days if due and as_of else None
    people = set()
    def add_person(value):
        if isinstance(value, str):
            name = value.casefold().strip()
            if name and not re.fullmatch(r'(?:speaker|sprecher|unknown(?: speaker)?|unbekannt)\s*\d*', name):
                people.add(name)
    add_person(task.get('owner'))
    for event in history:
        add_person(event.get('owner'))
    for field in ('participants', 'persons'):
        values = task.get(field)
        if isinstance(values, list):
            for value in values:
                add_person(value.get('name') if isinstance(value, dict) else value)
    specificity = sum((bool(re.search(r'\d', claim)), bool(ISO_DATE.search(claim) or GERMAN_DATE.search(claim)),
                       bool(re.search(r'\b(?:datei|dokument|bericht|angebot|liste|protokoll|vertrag|entwurf|präsentation|tabelle|modell|messung|freigabe)\b', claim, re.I))))
    features = {
        'owner_self': float(_owner_self(task.get('owner'))),
        'explicit_commitment': float(strength == 'explicit_commitment'),
        'accepted_request': float(strength == 'accepted_request'),
        'reported_action': float(strength == 'reported_action'),
        'conditional_action': float(strength == 'conditional_action'),
        'clear_promise': float(strength == 'explicit_commitment' or bool(task.get('clear_promise')) or bool(re.search(r'\b(?:ich|wir)\s+(?:werde|werden|mache|machen|schicke|schicken|sende|senden)\b', claim, re.I))),
        'due_present': float(bool(task.get('due_text') or task.get('due_date'))),
        'due_soon': float(delta is not None and 0 <= delta <= params.get('soon_days', 14)),
        'due_overdue': float(delta is not None and delta < 0),
        'event_count': float(min(event_count, params.get('event_cap', 3))),
        'meeting_count': float(min(len(sources), params.get('meeting_cap', 3))),
        'topic_active': float(min(topic.get('active_count', 0), params.get('topic_active_cap', 3))),
        'topic_recent': float(bool(topic.get('last_date') and as_of and _date(topic['last_date'])
                                  and 0 <= (as_of - _date(topic['last_date'])).days <= params.get('recent_days', 30))),
        'person_evidence': float(min(len(people), params.get('person_cap', 3))),
        'specificity': float(min(specificity, params.get('specificity_cap', 3))),
        'claim_length': float(min(len(claim.split()), params.get('claim_word_cap', 24)) / params.get('claim_word_cap', 24)),
        'artifact_detail': float(bool(re.search(r'\b(?:datei|dokument|bericht|angebot|liste|protokoll|vertrag|entwurf|präsentation|tabelle|modell|messung|freigabe)\b', claim, re.I))),
        'strong_verb': float(bool(STRONG_VERBS.search(claim))),
        'weak_verb': float(bool(WEAK_VERBS.search(claim))),
        'age_staleness': float(days_old is not None and days_old > params.get('stale_days', 90)),
    }
    return features


def score(task, context):
    config = context['config']
    features = extract_features(task, context)
    contributions = {key: float(weight) * features.get(key, 0.0) for key, weight in config['weights'].items()}
    points = round(sum(contributions.values()), 4)
    reasons = [{'merkmal': key, 'wert': features[key], 'beitrag': round(value, 4)}
               for key, value in contributions.items() if value and features.get(key)]
    return {'punkte': points, 'klasse': classify(points, config), 'gruende': reasons, 'features': features}


def _archive_path(value):
    if value != 'auto':
        target = Path(value).expanduser()
        if not target.is_file():
            raise ValueError('Archive unavailable')
        return target
    candidates = list(ARCHIVES.glob('dashboard-*.tar.gz'))
    if not candidates:
        raise ValueError('No archive available')
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _output_path(name):
    target = HERE / name
    if Path(name).name != name or target.resolve().parent != HERE or target.is_symlink():
        raise ValueError('Output must be a regular file in the script directory')
    return target


def _member_rows(archive, member):
    command = ['tar', '-xzOf', str(archive), 'canonical/' + member]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
    try:
        for line in process.stdout:
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError('Invalid archive row')
                yield row
        if process.wait() != 0:
            raise ValueError('Required archive member unavailable')
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
        process.stdout.close()


def _journal_entry(row):
    if 'record_json' in row:
        entry = json.loads(row['record_json'])
        if not isinstance(entry, dict):
            raise ValueError('Invalid journal entry')
        entry.setdefault('kind', row.get('kind'))
        return entry
    return row


def _project(archive, as_of):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(BACKEND))
    from generation_review import logical_entries, materialize
    from memory import overview
    import corrections
    rules = HERE.parent.parent / 'evaluation' / 'source-corrections.json'
    if not rules.is_file():
        raise ValueError('Reviewed correction rules unavailable')
    corrections.RULES = rules
    journal = [_journal_entry(row) for row in _member_rows(archive, 'journal.jsonl')]
    kinds = Counter(entry.get('kind') for entry in journal)
    logical = logical_entries(journal)
    db, _ = materialize(logical)
    try:
        state = overview(db, as_of=as_of)
    finally:
        db.close()
    notes = Counter()
    for row in _member_rows(archive, 'notes.jsonl'):
        payload = json.loads(row['note_json']) if isinstance(row.get('note_json'), str) else row
        legacy = payload.get('legacy_record', payload) if isinstance(payload, dict) else {}
        notes['legacy' if isinstance(legacy, dict) else 'unknown'] += 1
    return state, kinds, notes


def _topic_context(tasks):
    topics = defaultdict(lambda: {'active_count': 0, 'last_date': None})
    for task in tasks:
        key = task.get('matter_id')
        if not key:
            continue
        topic = topics[key]
        if task.get('status') in ('open', 'waiting'):
            topic['active_count'] += 1
        changed = task.get('last_changed')
        if _date(changed) and (topic['last_date'] is None or changed > topic['last_date']):
            topic['last_date'] = changed
    return topics


def run(archive, out, report, as_of=None, sample=None):
    started = time.monotonic()
    source = _archive_path(archive)
    out_path, report_path = _output_path(out), _output_path(report)
    if out_path == report_path:
        raise ValueError('Output files must differ')
    sample_path = _output_path(sample) if sample is not None else None
    if sample_path in (out_path, report_path):
        raise ValueError('Output files must differ')
    config = load_config()
    as_of = as_of or date.today().isoformat()
    if not _date(as_of) or _date(as_of).isoformat() != as_of:
        raise ValueError('Invalid as-of date')
    state, kinds, notes = _project(source, as_of)
    tasks = [item for group in GROUPS for item in state.get(group, [])]
    unique = {item['id']: item for item in tasks}
    if len(unique) != len(tasks):
        raise ValueError('Duplicate task identity in projection')
    candidates = []
    for entry in state.get('knowledge', []):
        data = entry.get('data') or {}
        if data.get('kind') != 'commitment' or entry.get('id') in unique or data.get('update_target') in unique:
            continue
        candidates.append({**data, 'id': entry['id'], 'matter_id': entry.get('matter_id'),
                           'last_changed': entry.get('event_date'),
                           'status': 'rejected' if data.get('knowledge_status') == 'rejected' else 'candidate',
                           'history': [{'source_id': entry.get('source_id'), 'event_date': entry.get('event_date'), 'action': 'proposed'}]})
    if len({item['id'] for item in candidates}) != len(candidates):
        raise ValueError('Duplicate candidate identity in projection')
    context = {'config': config, 'as_of': as_of, 'topics': _topic_context(tasks)}
    rows = []
    for task in [*tasks, *candidates]:
        result = score(task, context)
        rows.append({'id': task['id'], 'title': task.get('title'), 'as_of': as_of, **result,
                     'status': task.get('status'), 'has_due': bool(task.get('due_text') or task.get('due_date')),
                     'record_type': 'candidate' if task in candidates else 'task'})
    # Both files are local outputs; no source mutation or archive extraction.
    with out_path.open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps({key: value for key, value in row.items() if key != 'title'},
                                    ensure_ascii=False, allow_nan=False) + '\n')
    task_rows = [row for row in rows if row['record_type'] == 'task']
    candidate_rows = [row for row in rows if row['record_type'] == 'candidate']
    class_counts = Counter(row['klasse'] for row in task_rows)
    candidate_counts = Counter(row['klasse'] for row in candidate_rows)
    status_counts = Counter((row['klasse'], row['status']) for row in task_rows)
    all_points = [row['punkte'] for row in task_rows]
    lines = ['# Relevanz-Audit', '', f'Archiv: {source.name}', f'Stand: {as_of}', f'Aufgaben: {len(task_rows)}',
             f'Kandidaten: {len(candidate_rows)}', f'Journal-Einträge: {len(state.get("human_decisions", []))} persönliche Entscheidungen; '
             f'{sum(kinds.values())} Transport-Einträge', f'Notizen: {sum(notes.values())}',
             f'Mittelwert Aufgaben: {statistics.mean(all_points) if all_points else 0:.2f}',
             f'Median Aufgaben: {statistics.median(all_points) if all_points else 0:.2f}',
             f'Laufzeit Sekunden: {time.monotonic() - started:.2f}', '',
             '| Klasse | Gesamt | Anteil | offen | wartend | erledigt | weitere Status | Mittelwert | Median | ohne Frist |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cls in ('wichtig', 'standard', 'kleinigkeit'):
        subset = [row for row in task_rows if row['klasse'] == cls]
        points = [row['punkte'] for row in subset]
        other = sum(1 for row in subset if row['status'] not in ('open', 'waiting', 'done'))
        missing = sum(not row['has_due'] for row in subset)
        share = missing / len(subset) if subset else 0
        lines.append(f'| {cls} | {class_counts[cls]} | {len(subset) / len(task_rows) if task_rows else 0:.2%} | {status_counts[cls, "open"]} | '
                     f'{status_counts[cls, "waiting"]} | {status_counts[cls, "done"]} | {other} | '
                     f'{statistics.mean(points) if points else 0:.2f} | {statistics.median(points) if points else 0:.2f} | {share:.1%} |')
    lines.extend(('', 'Kandidaten-Klassen: ' + ', '.join(f'{key}={candidate_counts[key]}' for key in ('wichtig', 'standard', 'kleinigkeit')),
                  'Journal-Arten: ' + ', '.join(f'{key}={value}' for key, value in sorted(kinds.items())), ''))
    reason_counts = Counter(reason['merkmal'] for row in task_rows for reason in row['gruende'])
    lines.extend(('| Grund | Aufgaben | Anteil |', '| --- | ---: | ---: |'))
    for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))[:8]:
        lines.append(f'| {reason} | {count} | {count / len(task_rows) if task_rows else 0:.2%} |')
    lines.append('')
    report_path.write_text('\n'.join(lines), encoding='utf-8')
    if sample_path is not None:
        rng = random.Random(42)
        sample_lines = ['# Stichprobe zur späteren Sichtprüfung', '',
                        'Bis zur Kalibrierung gilt jede Markierung als Vorschlag. '
                        'Diese Zufallsstichprobe besitzt keinen Qualitätsmaßstab und belegt keine Güte.',
                        '', f'Stichtag: {as_of}. Seed: 42. Auswahl ohne Zurücklegen aus projizierten Aufgaben; '
                        'je Klasse 10, bei weniger Aufgaben alle. Kandidaten sind ausgeschlossen.', '']
        def cell(value):
            return str(value if value is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\r', ' ').replace('\n', ' ')
        for cls in ('wichtig', 'standard', 'kleinigkeit'):
            subset = sorted((row for row in task_rows if row['klasse'] == cls), key=lambda row: row['id'])
            selected = rng.sample(subset, min(10, len(subset)))
            sample_lines.extend((f'## {cls}: {len(selected)} von {len(subset)}', '',
                                 '| ID | Titel | Status | Punkte | Gründe (Merkmal: Wert × Gewicht = Beitrag) |',
                                 '| --- | --- | --- | ---: | --- |'))
            for row in selected:
                reasons = '; '.join(f'{reason["merkmal"]}: {reason["wert"]:g} × {config["weights"][reason["merkmal"]]:g} = {reason["beitrag"]:g}' for reason in row['gruende']) or 'Keine Punktebeiträge'
                sample_lines.append(f'| {cell(row["id"])} | {cell(row["title"])} | {cell(row["status"])} | {row["punkte"]:.4f} | {cell(reasons)} |')
            sample_lines.append('')
        sample_path.write_text('\n'.join(sample_lines), encoding='utf-8')
    return {'tasks': len(task_rows), 'candidates': len(candidate_rows), 'classes': dict(class_counts)}


def main():
    parser = argparse.ArgumentParser(description='Offline relevance projection')
    parser.add_argument('--archive', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--as-of', default=None)
    parser.add_argument('--sample', default='stichprobe.md')
    args = parser.parse_args()
    try:
        result = run(args.archive, args.out, args.report, args.as_of, args.sample)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        # Exception text can contain private meeting data from upstream validation.
        print('Relevance projection failed; see local input and reconstruction contracts.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
