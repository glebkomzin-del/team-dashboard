"""Local read models and BM25 retrieval; no filesystem/network/model access."""
from collections import Counter
from datetime import date, datetime
import math
import re
from zoneinfo import ZoneInfo

STATUSES = {'open', 'waiting', 'done', 'cancelled', 'dismissed'}

def iso_date(value):
    if not isinstance(value, str) or len(value) != 10: return None
    try:
        normalized = date.fromisoformat(value).isoformat()
        return normalized if normalized == value else None
    except ValueError: return None

def maturity(item):
    if item.get('uncertainty') or item.get('action_uncertainty') or item.get('required_review'): return 'Annahme'
    if item.get('quotes') or item.get('human_decision') or item.get('origin') == 'manual': return 'belegt'
    return 'unbekannt'

def normalize_task(row, sources=None):
    item = dict(row)
    source_map = sources if isinstance(sources, dict) else {s['id']: s for s in sources or []}
    history, evidence = [], []
    events = list(row.get('history', []))
    for event in row.get('planning_history', []):
        plain = {k: v for k, v in event.items() if k != 'source'}
        if not any((event.get('command_id') and event.get('command_id') == e.get('command_id'))
                   or plain == {k: v for k, v in e.items() if k != 'source'} for e in events):
            events.append(event)
    for original in events:
        event = dict(original)
        src = source_map.get(event.get('source_version'), {})
        previous = event.get('source', {})
        source = {'meeting_title': event.get('source_title') or src.get('title') or previous.get('meeting_title'),
            'date': event.get('event_date') or src.get('event_date') or previous.get('date'),
            'source_id': event.get('source_id') or src.get('source_id') or src.get('id') or previous.get('source_id'),
            'source_version': event.get('source_version'), 'quotes': event.get('quotes', []),
            'reife': 'belegt' if event.get('quotes') or event.get('human') else 'unbekannt'}
        if event.get('human') or event.get('command_id'): source['authority'] = 'explicit_user_decision'
        event['source'] = source
        history.append(event)
        if source not in evidence: evidence.append(source)
    if not evidence: evidence = row.get('sources', [])
    if not evidence:
        src = source_map.get(row.get('source_version'), {})
        evidence = [{'meeting_title': src.get('title') or row.get('source_title'),
            'date': src.get('event_date') or row.get('event_date'),
            'source_id': src.get('source_id') or src.get('id'), 'source_version': row.get('source_version'),
            'quotes': row.get('quotes', []), 'reife': maturity(row)}]
    item.update(history=history, sources=evidence, source=evidence[-1], reife=maturity(row))
    for key in ('owner', 'matter_id', 'matter', 'due_text', 'last_changed'): item.setdefault(key, None)
    for key in ('claim', 'title'): item.setdefault(key, '')
    item.setdefault('status', 'open')
    item['due_date'] = iso_date(row.get('due_date')) or iso_date(row.get('due_text'))
    item['due_reife'] = 'belegt' if item['due_date'] else 'unbekannt'
    return item

def normalize_meeting(row):
    item = dict(row)
    item['title'] = row.get('meeting_title') or row.get('title')
    item['date'] = row.get('date') or row.get('event_date')
    item.setdefault('summary', None)
    item['source'] = {'meeting_title': item['title'], 'date': item['date'], 'source_id': row.get('source_id') or row.get('id')}
    item['reife'] = row.get('reife') or ('Annahme' if item['summary'] else 'unbekannt')
    return item

def tokens(text): return re.findall(r'[^\W_]+', str(text).casefold(), re.UNICODE)

class DataIndex:
    def __init__(self, tasks, meetings, metadata=None):
        self.tasks = {t['id']: normalize_task(t) for t in tasks}
        self.meetings = [normalize_meeting(m) for m in meetings]
        self.metadata = {'meeting_title': None, 'date': None, **(metadata or {})}
        self._search = None

    def envelope(self, **values): return {'source': self.metadata, 'reife': 'belegt', **values}

    def tasks_list(self, status=None, owner=None, matter=None, due_before=None, updated_since=None, text=None):
        if status is not None and status not in STATUSES: raise ValueError('Invalid status')
        if due_before is not None and not iso_date(due_before): raise ValueError('Invalid date filter')
        if updated_since is not None and not iso_date(updated_since): raise ValueError('Invalid date filter')
        result = []
        for t in self.tasks.values():
            if status is not None and t['status'] != status: continue
            if owner is not None and owner.casefold() not in (t.get('owner') or '').casefold(): continue
            if matter is not None and matter != t.get('matter_id') and matter.casefold() not in (t.get('matter') or '').casefold(): continue
            if due_before and (not t['due_date'] or t['due_date'] >= due_before): continue
            if updated_since and (not t.get('last_changed') or t['last_changed'] < updated_since): continue
            hay = ' '.join(str(t.get(k) or '') for k in ('title', 'claim', 'owner', 'matter', 'due_text')).casefold()
            if text is not None and not all(w in hay for w in tokens(text)): continue
            result.append(t)
        result.sort(key=lambda t: (t.get('due_date') or '9999-12-31', t['id']))
        reife = 'unbekannt' if not result else 'Annahme' if any(t['reife'] != 'belegt' for t in result) else 'belegt'
        return self.envelope(tasks=result, count=len(result), reife=reife)

    def task_get(self, id):
        if id not in self.tasks: raise ValueError('Unknown task ID')
        return self.envelope(task=self.tasks[id], reife=self.tasks[id]['reife'])

    def matters_list(self):
        grouped = {}
        for t in self.tasks.values():
            key = t.get('matter_id') or t.get('matter') or 'unknown'
            row = grouped.setdefault(key, {'id': key, 'title': t.get('matter'), 'task_count': 0, 'sources': []})
            row['task_count'] += 1
            for source in t['sources']:
                if source not in row['sources']: row['sources'].append(source)
            row['source'] = row['sources'][-1]
            row['reife'] = 'belegt' if row['title'] else 'unbekannt'
        return self.envelope(matters=list(grouped.values()), count=len(grouped))

    def meetings_recent(self, n=10):
        if type(n) is not int or not 1 <= n <= 100: raise ValueError('Invalid meeting limit')
        rows = sorted(self.meetings, key=lambda m: (m.get('date') or '', m.get('id') or ''), reverse=True)[:n]
        return self.envelope(meetings=rows, count=len(rows), reife='Annahme' if rows else 'unbekannt')

    def memory_ask(self, question):
        if not isinstance(question, str) or not question.strip() or len(question) > 8000: raise ValueError('Invalid question')
        if any(w in question.casefold() for w in ('überfällig', 'ueberfaellig', 'overdue')):
            today = datetime.now(ZoneInfo('Europe/Berlin')).date().isoformat()
            rows = [t for t in self.tasks.values() if t['status'] in ('open', 'waiting') and t['due_date'] and t['due_date'] < today]
            rows.sort(key=lambda t: (t['due_date'], t['id']))
            return self.envelope(answer='Auswahl, keine Vollständigkeit', as_of=today,
                results=[{'kind': 'task', 'item': t} for t in rows], count=len(rows), reife='Annahme',
                unknown_due_dates=sum(t['status'] in ('open', 'waiting') and not t['due_date'] for t in self.tasks.values()), retrieval='absolute_due_dates')
        if self._search is None:
            documents, df = [], Counter()
            for kind, item in [('task', t) for t in self.tasks.values()] + [('meeting', m) for m in self.meetings]:
                terms = Counter(tokens(' '.join(str(item.get(k) or '') for k in ('title', 'claim', 'matter', 'owner', 'summary'))))
                documents.append((kind, item, terms, sum(terms.values())))
                df.update(terms.keys())
            self._search = documents, df, sum(d[3] for d in documents) / max(1, len(documents)) or 1
        documents, df, avg = self._search
        ranked = []
        for kind, item, terms, length in documents:
            score = 0
            for term in set(tokens(question)):
                tf = terms.get(term, 0)
                if tf: score += math.log(1 + (len(documents) - df[term] + .5) / (df[term] + .5)) * tf * 2.2 / (tf + 1.2 * (.25 + .75 * length / avg))
            if score > 0: ranked.append({'kind': kind, 'score': round(score, 6), 'item': item})
        ranked.sort(key=lambda r: (-r['score'], r['kind'], str(r['item'].get('id', ''))))
        return self.envelope(answer='Auswahl, keine Vollständigkeit', results=ranked[:10], count=min(10, len(ranked)), matches=len(ranked), retrieval='BM25', reife='Annahme' if ranked else 'unbekannt')
