"""Streaming canonical backup reader. Projections only use SQLite :memory:."""
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from index import DataIndex, normalize_task

BACKEND = Path(__file__).resolve().parents[2] / 'evaluation/sol-operational-release-20261006/backend'
MEMBERS = ('canonical/journal.jsonl', 'canonical/documents.jsonl', 'canonical/notes.jsonl')
CACHE_VERSION = 2
CACHE_FILE_LIMIT = 9_000_000
CACHE_TOTAL_LIMIT = 20_000_000
GROUPS = ('personal', 'waiting_dependencies', 'waiting', 'completed', 'cancelled')

def projection_modules():
    sys.dont_write_bytecode = True
    if not (BACKEND / 'generation_review.py').is_file(): raise ValueError('Projection backend unavailable')
    support = str(Path(__file__).resolve().parent / 'projection_support')
    if support not in sys.path: sys.path.insert(1, support)
    if str(BACKEND) not in sys.path: sys.path.append(str(BACKEND))
    import memory, generation_review, review_api, projection_snapshot, planner, corrections
    if not corrections.RULES.is_file():
        rules = BACKEND.parents[1] / 'source-corrections.json'
        if not rules.is_file(): raise ValueError('Projection correction rules unavailable')
        corrections.RULES = rules
    return memory, generation_review, review_api, projection_snapshot, planner

def latest_archive():
    folder = Path.home() / 'Library/Application Support/Dashboard Job Backup/archives'
    archives = [p for p in folder.glob('dashboard-*.tar.gz') if p.is_file() and not p.is_symlink()]
    if not archives: raise ValueError('No snapshot archive available')
    return max(archives, key=lambda p: p.name)

def stream_rows(archive, members=MEMBERS):
    process = subprocess.Popen(['tar', '-xzOf', str(archive), *members], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    sequences = {}
    try:
        for line in process.stdout:
            if len(line) > 128 * 1024 * 1024: raise ValueError('Snapshot record too large')
            row = json.loads(line)
            if not isinstance(row, dict): raise ValueError('Invalid snapshot record')
            if 'record_json' in row:
                if 'record_hash' in row and hashlib.sha256(row['record_json'].encode()).hexdigest() != row['record_hash']: raise ValueError('Snapshot checksum mismatch')
                sequence, kind = row.get('sequence'), row.get('kind')
                if sequence is not None:
                    if type(sequence) is not int or sequence <= sequences.get(kind, 0): raise ValueError('Invalid snapshot sequence')
                    sequences[kind] = sequence
                row = json.loads(row['record_json']) if isinstance(row['record_json'], str) else row['record_json']
            if not isinstance(row, dict): raise ValueError('Invalid snapshot body')
            yield row
        if process.wait() != 0: raise ValueError('Cannot stream canonical snapshot members')
    finally:
        process.stdout.close()
        if process.poll() is None: process.kill()
        process.wait()

def _logical_source(entry):
    fields = ('id', 'source_id', 'content_hash', 'event_date', 'title', 'transcript', 'observed_at')
    if entry.get('source_version', entry['source']['id']) != entry['source']['id']:
        raise ValueError('Journal source reference mismatch')
    return {'kind': 'source', 'source': {k: entry['source'][k] for k in fields}, 'payload': entry['payload']}

def _latest_checkpoint(archive):
    # Earlier journal entries may have been tombstoned by a deletion. Find the
    # authoritative replay boundary without retaining the original journal.
    revision, checkpoint = 0, None
    for row in stream_rows(archive, MEMBERS[:1]):
        if row.get('kind') not in ('source', 'human', 'generation', 'redaction') or type(row.get('revision')) is not int or row['revision'] != revision + 1:
            raise ValueError('Incomplete canonical journal')
        revision = row['revision']
        if row['kind'] == 'redaction':
            if row['payload'].get('through_revision') != revision - 1:
                raise ValueError('Invalid redaction boundary')
            checkpoint = row
    return checkpoint

def _note(row):
    raw = row.get('note_json')
    if raw is None: return None
    expected = row.get('sanitized_note_hash') if row.get('redaction_id') else row.get('note_hash')
    if (expected is not None or row.get('redaction_id')) and (not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != expected):
        raise ValueError('Archive note checksum mismatch')
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if payload.get('title_backfill_only') is True: return None
    record = payload.get('legacy_record', payload)
    value = record.get('payload', record)
    summary = '\n\n'.join(s for s in (value.get('executive_summary'), value.get('ai_summary')) if isinstance(s, str) and s)
    return {'summary': summary or None, 'title': payload.get('display_title') or value.get('title'),
            'note_id': row.get('id'), 'origin': row.get('origin'), 'document_id': row.get('document_id'),
            'registered_revision': row.get('registered_revision', 0)}

def _document_order(document):
    raw = document.get('observed_at')
    observed = datetime.fromisoformat(raw.replace('Z', '+00:00')) if raw else datetime.min.replace(tzinfo=timezone.utc)
    if observed.tzinfo is None: raise ValueError('Observation time requires timezone')
    return observed, document.get('registered_revision') or 0

def build_index(archive):
    memory, generation, review, snapshots, planner = projection_modules()
    checkpoint = _latest_checkpoint(archive)
    db = memory.connect(':memory:')
    logical, documents, notes = [], {}, {}
    revision = 0
    counts = {k: 0 for k in ('source', 'human', 'generation', 'redaction', 'documents', 'notes')}
    try:
        if checkpoint:
            planner.setup(db)
            snapshots.apply_snapshot(db, checkpoint['payload'])
            logical = deepcopy(checkpoint['payload']['logical_basis'])
        for row in stream_rows(archive):
            if row.get('kind') in ('source', 'human', 'generation', 'redaction'):
                if row.get('revision') != revision + 1: raise ValueError('Incomplete canonical journal')
                revision = row['revision']
                kind = row['kind']; counts[kind] += 1
                if checkpoint and revision <= checkpoint['revision']: continue
                if kind == 'generation':
                    following, _, raw = generation.verify_generation(logical, row['payload'], _projection=True, _base_projection=db, _raw_entries=True)
                    db.close(); db, logical = following, raw
                elif kind == 'redaction':
                    if row['payload'].get('through_revision') != revision - 1: raise ValueError('Invalid redaction boundary')
                    db.close(); db = memory.connect(':memory:'); planner.setup(db)
                    snapshots.apply_snapshot(db, row['payload']); logical = deepcopy(row['payload']['logical_basis'])
                else:
                    entry = _logical_source(row) if kind == 'source' else {k: row[k] for k in ('kind', 'command_id', 'actor_id', 'payload')}
                    normalized = generation._materialize_into(db, [entry], prior=logical)
                    logical.extend(normalized)
            elif 'note_json' in row:
                counts['notes'] += 1
                note = _note(row)
                if note: notes.setdefault(row['document_id'], []).append(note)
            elif 'source_id' in row and 'event_date' in row and 'body_hash' in row:
                counts['documents'] += 1
                documents[row['id']] = {k: row.get(k) for k in ('id', 'source_id', 'title', 'event_date', 'observed_at', 'body_hash', 'registered_revision', 'redaction_id')}
            else: raise ValueError('Unknown canonical snapshot record')
        for entry in logical:
            if entry['kind'] == 'source' and entry['payload'].get('archive_note'):
                row = entry['payload']['archive_note']; note = _note(row)
                if note:
                    note['active'] = True; notes.setdefault(row['document_id'], []).append(note)
        view = review.review(db)
        tasks = [normalize_task(t, view['sources']) for group in GROUPS for t in view.get(group, [])]
        by_identity, current = {}, {}
        for d in documents.values():
            identity = (d['source_id'], d['event_date'], d['body_hash'])
            by_identity.setdefault(identity, []).extend(notes.get(d['id'], []))
            key = (d['source_id'], d['event_date']); prior = current.get(key)
            if prior is None or _document_order(d) > _document_order(prior): current[key] = d
        meetings = []
        for d in current.values():
            available = by_identity.get((d['source_id'], d['event_date'], d['body_hash']), [])
            available.sort(key=lambda n: (bool(n.get('active')), n.get('registered_revision', 0), n.get('note_id') or ''), reverse=True)
            preferred = next((n for n in available if n.get('active')), None) or next((n for n in available if n['summary']), {})
            meetings.append({'id': d['id'], 'source_id': d['source_id'], 'title': preferred.get('title') or d['title'],
                             'date': d['event_date'], 'summary': preferred.get('summary'), 'note_id': preferred.get('note_id'),
                             'reife': 'Annahme' if preferred.get('summary') else 'unbekannt'})
        return DataIndex(tasks, meetings, {'mode': 'snapshot', 'archive': archive.name, 'revision': revision,
                         'as_of': view['as_of'], 'counts': counts, 'task_total': len(tasks), 'read_only': True})
    finally: db.close()

def cache_identity(archive):
    digest = hashlib.sha256(); info = archive.stat()
    digest.update(f'{CACHE_VERSION}:{archive.resolve()}:{info.st_size}:{info.st_mtime_ns}'.encode())
    for folder, pattern in ((BACKEND, '*.py'), (BACKEND.parents[1], 'source-corrections.json'), (BACKEND / 'evaluation', 'source-corrections.json'), (Path(__file__).parent, '*.py'), (Path(__file__).parent / 'projection_support', '*.py')):
        for path in sorted(folder.glob(pattern)): digest.update(path.name.encode()); digest.update(path.read_bytes())
    return digest.hexdigest()

def cache_folder():
    folder = Path.home() / '.cache/dashboard-memory-mcp'
    if folder.is_symlink() or folder.parent.is_symlink(): raise ValueError('Unsafe cache directory')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700); os.chmod(folder, 0o700)
    return folder

def cache_read(path, identity=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r', encoding='utf-8') as stream:
        if stat.S_IMODE(os.fstat(stream.fileno()).st_mode) != 0o600: raise ValueError('Cache permissions must be private')
        if os.fstat(stream.fileno()).st_size > CACHE_FILE_LIMIT: raise ValueError('Cache exceeds size limit')
        value = json.load(stream)
    if value.get('version') != CACHE_VERSION: raise ValueError('Unknown cache version')
    if identity is not None and value.get('identity') != identity: raise ValueError('Stale snapshot cache')
    return DataIndex(value['tasks'], value['meetings'], value['metadata'])

def cache_write(path, index, identity=None):
    payload = json.dumps({'version': CACHE_VERSION, 'identity': identity, 'tasks': list(index.tasks.values()), 'meetings': index.meetings, 'metadata': index.metadata}, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > CACHE_FILE_LIMIT: raise ValueError('Cache exceeds size limit')
    lock_fd = os.open(path.parent / '.cache.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    temporary = None
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        os.fchmod(lock_fd, 0o600)
        # Only adapter-owned old caches are pruned; unrelated files count
        # against the directory budget and can cause an in-memory fallback.
        for candidate in path.parent.iterdir():
            if candidate != path and not candidate.is_symlink() and candidate.is_file() and len(candidate.stem) == 64 and all(c in '0123456789abcdef' for c in candidate.stem) and candidate.suffix == '.json':
                candidate.unlink()
        total = sum(p.lstat().st_size for p in path.parent.iterdir())
        if total + len(payload) >= CACHE_TOTAL_LIMIT: raise ValueError('Cache directory exceeds size limit')
        fd, temporary = tempfile.mkstemp(prefix='.index-', dir=path.parent)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600); stream.write(payload)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary): os.unlink(temporary)
        os.close(lock_fd)

class SnapshotBackend:
    def __init__(self, archive=None):
        self.archive = Path(archive).expanduser().resolve() if archive else latest_archive()
        if not self.archive.is_file(): raise ValueError('Snapshot archive unavailable')
        self.index = None
    def _load(self):
        if self.index is None:
            path = None
            identity = None
            if os.environ.get('DASHBOARD_MEMORY_CACHE', '0') == '1':
                try:
                    path = cache_folder() / 'index.json'; identity = cache_identity(self.archive)
                    self.index = cache_read(path, identity)
                except (OSError, ValueError, KeyError, TypeError): pass
            if self.index is None:
                self.index = build_index(self.archive)
                if path:
                    try: cache_write(path, self.index, identity)
                    except (OSError, ValueError): pass
        return self.index
    def tasks_list(self, **filters): return self._load().tasks_list(**filters)
    def task_get(self, id): return self._load().task_get(id)
    def matters_list(self): return self._load().matters_list()
    def meetings_recent(self, n=10): return self._load().meetings_recent(n)
    def memory_ask(self, question): return self._load().memory_ask(question)
