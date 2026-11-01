"""Versioned full-text archive. Search results always point back to exact source spans."""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def connect(path, *, readonly=False):
    path = Path(path).resolve()
    if readonly:
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
        db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, event_date TEXT NOT NULL,
            observed_at TEXT NOT NULL, title TEXT NOT NULL, body_hash TEXT NOT NULL,
            export_hash TEXT NOT NULL, body TEXT NOT NULL, export TEXT NOT NULL,
            metadata_json TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS document_time ON documents(event_date,observed_at);
          CREATE TABLE IF NOT EXISTS passages (
            id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
            ordinal INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
            text TEXT NOT NULL, title TEXT NOT NULL, UNIQUE(document_id,ordinal));
          CREATE VIRTUAL TABLE IF NOT EXISTS passage_search USING fts5(
            text,title,content='passages',content_rowid='id',tokenize='unicode61 remove_diacritics 2');
        ''')
        path.chmod(0o600)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def spans(text, size=1800, overlap=200):
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind('\n', start + size // 2, end)
            if boundary >= 0:
                end = boundary + 1
        yield start, end, text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


def ingest_archive(db, folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text())
    if len(manifest['sources']) != manifest['inventory_files']:
        raise ValueError('Incomplete archive manifest')
    observed = datetime.fromisoformat(manifest['stopped_at'].replace('Z', '+00:00')).astimezone(timezone.utc).isoformat()
    added = 0
    with db:
        for source in manifest['sources']:
            for field in ['export_sha256', 'body_sha256']:
                if not re.fullmatch('[a-f0-9]{64}', source[field]):
                    raise ValueError('Invalid content address')
            body = (folder / (source['body_sha256'] + '.txt')).read_bytes().decode('utf-8')
            export = (folder / (source['export_sha256'] + '.txt')).read_bytes().decode('utf-8')
            if digest(body) != source['body_sha256'] or digest(export) != source['export_sha256']:
                raise ValueError('Corrupt archive content')
            if export[source['body_offset_characters']:] != body:
                raise ValueError('Invalid body derivation')
            date.fromisoformat(source['event_date'])
            metadata = json.dumps(source, ensure_ascii=False, sort_keys=True)
            identifier = digest(source['source_id'] + ':' + metadata)
            existing = db.execute('SELECT id FROM documents WHERE id=?', (identifier,)).fetchone()
            if existing:
                continue
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (identifier, source['source_id'], source['event_date'], observed, source['title'],
                        source['body_sha256'], source['export_sha256'], body, export, metadata))
            for ordinal, (start, end, text) in enumerate(spans(body)):
                cursor = db.execute('INSERT INTO passages(document_id,ordinal,start,end,text,title) VALUES (?,?,?,?,?,?)',
                                    (identifier, ordinal, start, end, text, source['title']))
                db.execute('INSERT INTO passage_search(rowid,text,title) VALUES (?,?,?)',
                           (cursor.lastrowid, text, source['title']))
            added += 1
    return added


def bounds(as_of=None, known_at=None):
    as_of = as_of or date.today().isoformat()
    date.fromisoformat(as_of)
    known_at = datetime.fromisoformat(known_at.replace('Z', '+00:00')) if known_at else datetime.now(timezone.utc)
    if known_at.tzinfo is None:
        raise ValueError('Knowledge cutoff requires timezone')
    return as_of, known_at.astimezone(timezone.utc).isoformat()


LATEST = '''d.event_date<=? AND d.observed_at<=? AND NOT EXISTS (
  SELECT 1 FROM documents newer WHERE newer.source_id=d.source_id AND newer.observed_at<=?
  AND (newer.observed_at>d.observed_at OR (newer.observed_at=d.observed_at AND newer.rowid>d.rowid)))'''


def catalogue(db, *, as_of=None, known_at=None, query='', order='relevance', limit=50, offset=0):
    as_of, known_at = bounds(as_of, known_at)
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000 or len(query) > 500 or order not in ('relevance','newest','oldest','title'):
        raise ValueError('Invalid search bounds')
    params = [as_of, known_at, known_at]
    fields = 'd.id,d.source_id,d.title,d.event_date,d.observed_at,d.body_hash AS content_hash,length(d.body) AS characters'
    if query.strip():
        # Literal lexical search. Never interpolate FTS syntax or SQL from a request.
        terms = list(dict.fromkeys(re.findall(r'\w+', query, re.UNICODE)))[:16]
        if not terms:
            return {'sources': [], 'total': 0, 'as_of': as_of, 'known_at': known_at, 'order': order}
        expression = ' AND '.join('"' + term.replace('"', '""') + '"*' for term in terms)
        where = 'passage_search MATCH ? AND ' + LATEST
        params = [expression, *params]
        total = db.execute('SELECT count(DISTINCT d.id) FROM passage_search JOIN passages p ON p.id=passage_search.rowid JOIN documents d ON d.id=p.document_id WHERE ' + where, params).fetchone()[0]
        # Aggregate after ranking in a CTE; one best matching verbatim passage per source.
        ordering = {'relevance': 'score,event_date DESC,id', 'newest': 'event_date DESC,title,id',
                    'oldest': 'event_date ASC,title,id', 'title': 'title COLLATE NOCASE,event_date DESC,id'}[order]
        sql = '''WITH hits AS (SELECT ''' + fields + ''',p.start,p.end,p.text,bm25(passage_search,1.0,3.0) AS score
          FROM passage_search JOIN passages p ON p.id=passage_search.rowid JOIN documents d ON d.id=p.document_id WHERE ''' + where + '''),
          ranked AS (SELECT *,row_number() OVER (PARTITION BY id ORDER BY score,start) AS position FROM hits)
          SELECT * FROM ranked WHERE position=1 ORDER BY ''' + ordering + ''' LIMIT ? OFFSET ?'''
        rows = [dict(r) for r in db.execute(sql, [*params, limit, offset])]
        for row in rows:
            row.pop('position', None)
            row['match'] = {'start': row.pop('start'), 'end': row.pop('end'), 'text': row.pop('text')}
    else:
        total = db.execute('SELECT count(*) FROM documents d WHERE ' + LATEST, params).fetchone()[0]
        ordering = {'relevance': 'event_date DESC,title,id', 'newest': 'event_date DESC,title,id',
                    'oldest': 'event_date ASC,title,id', 'title': 'title COLLATE NOCASE,event_date DESC,id'}[order]
        rows = [dict(r) for r in db.execute('SELECT ' + fields + ' FROM documents d WHERE ' + LATEST + ' ORDER BY ' + ordering + ' LIMIT ? OFFSET ?', [*params, limit, offset])]
    return {'sources': rows, 'total': total, 'limit': limit, 'offset': offset,
            'as_of': as_of, 'known_at': known_at, 'order': order, 'search_mode': 'literal_full_text'}


def original(db, identifier):
    if not re.fullmatch('[a-f0-9]{64}', identifier):
        return None
    row = db.execute('SELECT id,source_id,title,event_date,observed_at,body_hash AS content_hash,export_hash,body AS transcript,export AS full_export,metadata_json FROM documents WHERE id=?', (identifier,)).fetchone()
    if not row:
        try:row=db.execute('SELECT id,source_id,title,event_date,observed_at,body_hash AS content_hash,export_hash,metadata_json,redaction_id FROM deleted_documents WHERE id=?',(identifier,)).fetchone()
        except sqlite3.OperationalError:return None
        if not row:return None
        result=dict(row);result['provenance']=json.loads(result.pop('metadata_json'))
        result['deleted']=True
        return result
    result = dict(row)
    result['provenance'] = json.loads(result.pop('metadata_json'))
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('archive')
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    db = connect(args.db)
    print(json.dumps({'indexed_new_sources': ingest_archive(db, args.archive),
                      'sources': db.execute('SELECT count(*) FROM documents').fetchone()[0],
                      'passages': db.execute('SELECT count(*) FROM passages').fetchone()[0]}))
    db.close()
