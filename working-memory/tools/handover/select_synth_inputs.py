"""Select five source-bound inputs from the local archive; numeric stdout only."""
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import handover
import synthesize


def evidence_from_package(package, task):
    evidence = []
    # Direct facts and actual history first; classification/search assumptions excluded.
    fields = ['worum', 'naechster', 'fertig_wenn', 'scope', 'abnahme', 'aufgabe',
              'verlauf', 'vorarbeiten_und_vorgespraeche', 'wiederverwendung',
              'verwandte_aufgaben', 'kontext']
    seen = set()
    for field in fields:
        for path, fact in handover._assertion_paths(package.get(field), field):
            if fact.get('reife') != 'belegt' or not fact.get('belege'):
                continue
            value = fact.get('wert')
            if not isinstance(value, str) or value in ('', 'unbekannt', 'keine gefunden'):
                continue
            # Structural identifiers/hashes and automatic snapshot metadata are not work instructions.
            if re.search(r'(?:^|\.)(?:id|source_id|archiv|status|journal_revision|source_version|content_hash|command_id|action|event_date|last_changed|stand|datum)$', path):
                continue
            source = fact['belege'][0].split(';', 1)[0]
            signature = (source, value)
            if signature in seen: continue
            seen.add(signature)
            day = 'unbekannt'
            if field == 'vorarbeiten_und_vorgespraeche':
                match = re.search(r'\[(\d+)\]', path)
                if match:
                    day = package[field][int(match[1])]['datum']['wert']
            else:
                match = re.search(r'(?:event|event_date)=([0-9-]+)', fact['belege'][0])
                if match: day = match[1]
                history = re.search(r'^verlauf\[(\d+)\]', path)
                if history:
                    day = package['verlauf'][int(history[1])].get('event_date', {}).get('wert', 'unbekannt')
            original = len(value)
            text = value if original <= 600 else value[:599] + '…'
            evidence.append({'id': 'B' + str(len(evidence) + 1), 'quelle': source,
                             'datum': day, 'text': text, 'feld': path,
                             'gekuerzte_zeichen': max(0, original - len(text.rstrip('…')))})
    participants = 0
    bounded = []
    for item in evidence:
        if item['feld'].startswith('kontext.personen'):
            participants += 1
            if participants > 5: continue
        bounded.append(item)
    return bounded


def main():
    relevance_path = HERE.parent / 'relevance/relevance.jsonl'
    records = [json.loads(line) for line in relevance_path.read_text().splitlines() if line.strip()]
    relevance = {r['id']: r for r in records if r.get('klasse') == 'wichtig'}
    memory = handover.load_archive('auto')
    try:
        candidates = [t for t in memory.tasks if t.get('status') == 'open' and t.get('id') in relevance]
        candidates.sort(key=lambda t: (not bool(relevance[t['id']]['features'].get('owner_self')),
                                       not bool(t.get('due_date')), str(t.get('last_changed') or '')), reverse=False)
        selected = []; themes = set()
        for task in candidates:
            theme = str(task.get('matter_id') or task.get('matter') or task.get('subject') or '').casefold()
            if not theme or theme in themes: continue
            package = handover.build_package(memory, task)
            count = package['suchmetadaten']['verwandte_aufgaben']['kandidaten']
            if not task.get('due_date') and count < 3: continue
            selected.append((task, package, count)); themes.add(theme)
            if len(selected) == 5: break
        if len(selected) != 5: raise handover.HandoverError('E_SELECTION')
        target = HERE / 'synth'; target.mkdir(mode=0o700, exist_ok=True)
        numbers = []
        for number, (task, package, count) in enumerate(selected, 1):
            evidence = evidence_from_package(package, task)
            for item in evidence: item['quelle'] += '; feld=' + item['feld']
            normalized = synthesize.build_evidence({'belege': evidence})
            direct = {k: task.get(k) for k in ('id', 'title', 'claim', 'owner', 'matter', 'due_date', 'status')}
            result = {'aufgabe': direct, 'belege': normalized['belege'],
                      'beleg_block': normalized['block'], 'gekuerzt': normalized['gekuerzt'],
                      'ausgelassen': normalized['ausgelassen'],
                      'relevanz': 'wichtig', 'auswahl': {'status': 'open', 'klasse': 'wichtig',
                        'frist': bool(task.get('due_date')), 'verwandte': count,
                        'besitzer_gleb': bool(relevance[task['id']]['features'].get('owner_self')),
                        'archiv': memory.archive, 'relevanzquelle': '../relevance/relevance.jsonl'}}
            destination = target / f'synth-input-{number:02d}.json'
            if destination.exists(): raise handover.HandoverError('E_EXISTS')
            handover.write_package(json.dumps(result, ensure_ascii=False, indent=2) + '\n', destination)
            numbers.append({'input':number, 'belege':len(evidence), 'verwandte':count,
                            'frist':int(bool(task.get('due_date'))), 'gleb':int(result['auswahl']['besitzer_gleb']),
                            'bytes':destination.stat().st_size})
        for row in numbers: print(json.dumps(row))
    finally:
        memory.db.close()

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(str(error) if isinstance(error, handover.HandoverError) else 'E_SELECT', file=sys.stderr)
        raise SystemExit(2)
