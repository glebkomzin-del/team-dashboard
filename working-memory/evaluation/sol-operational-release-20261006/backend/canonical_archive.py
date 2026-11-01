"""Pinned Supabase originals; local full-text search is a rebuildable cache.

Archiving and reconstruction never call a model or register extraction jobs.
"""
from datetime import date,datetime
import json,os,sqlite3,tempfile
from pathlib import Path

from archive_index import connect,digest,spans
from meeting_naming import resolve_display_title
from memory import ValidationError

FIELDS=('id','source_id','event_date','observed_at','title','body_hash','export_hash','body','export','metadata_json')

def verify_document(row):
    if not isinstance(row,dict):raise ValidationError('Invalid original envelope')
    redacted=row.get('redaction_id') is not None
    text_fields=tuple(k for k in FIELDS if k not in ('body','export'))
    if not all(isinstance(row.get(k),str) for k in text_fields):raise ValidationError('Invalid original envelope')
    if redacted:
        if row.get('body') is not None or row.get('export') is not None:raise ValidationError('Redacted original retains plaintext')
    elif not isinstance(row.get('body'),str) or not isinstance(row.get('export'),str):raise ValidationError('Invalid original envelope')
    meta=json.loads(row['metadata_json'])
    if not isinstance(meta,dict):raise ValidationError('Invalid original metadata')
    if digest(row['source_id']+':'+row['metadata_json'])!=row['id'] or (not redacted and (digest(row['body'])!=row['body_hash'] or digest(row['export'])!=row['export_hash'])):
        raise ValidationError('Original checksum mismatch')
    for field,target in [('source_id','source_id'),('event_date','event_date'),('title','title'),('body_sha256','body_hash'),('export_sha256','export_hash')]:
        if meta.get(field)!=row[target]:raise ValidationError('Original metadata mismatch')
    offset=meta.get('body_offset_characters')
    if type(offset) is not int or offset<0 or (not redacted and row['export'][offset:]!=row['body']):
        raise ValidationError('Original body derivation mismatch')
    date.fromisoformat(row['event_date'])
    if not datetime.fromisoformat(row['observed_at'].replace('Z','+00:00')).tzinfo:raise ValidationError('Observation time requires timezone')
    result={field:row[field] for field in FIELDS}
    if redacted:result['redaction_id']=row['redaction_id']
    return result

def verify_note(row):
    keys=('id','document_id','origin','origin_id','note_json','note_hash')
    redacted=row.get('redaction_id') is not None
    if not all(isinstance(row.get(k),str) for k in keys if k!='note_json'):raise ValidationError('Invalid note envelope')
    if row['origin'] not in ('legacy_meetings','legacy_meeting_inbox','source_summary'):raise ValidationError('Unknown note origin')
    if redacted:
        body=row.get('note_json');sanitized=row.get('sanitized_note_hash')
        if body is not None:
            if not isinstance(body,str) or not isinstance(json.loads(body),dict) or digest(body)!=sanitized:
                raise ValidationError('Sanitized archive note checksum mismatch')
        elif sanitized is not None:raise ValidationError('Missing sanitized archive note has a checksum')
        return {**{key:row.get(key) for key in keys},'redaction_id':row['redaction_id'],
                'sanitized_note_hash':sanitized}
    if not isinstance(row.get('note_json'),str):raise ValidationError('Invalid note envelope')
    if not isinstance(json.loads(row['note_json']),dict):raise ValidationError('Invalid note body')
    body_hash=digest(row['note_json'])
    if body_hash!=row['note_hash'] or digest(':'.join([row['document_id'],row['origin'],row['origin_id'],body_hash]))!=row['id']:
        raise ValidationError('Note checksum mismatch')
    return {key:row[key] for key in keys}

def _summary_rows(db,document_id):
    # Drive metadata changes (for example moving to Processed) create a new
    # document envelope, not a new transcript. Reuse notes only from the same
    # source, meeting date and exact body; never borrow across changed content
    # or expose a later version's notes when opening a historical envelope.
    query = '''SELECT n.* FROM archived_notes n
      JOIN documents noted ON noted.id=n.document_id
      JOIN documents current ON current.id=?
      WHERE noted.source_id=current.source_id
        AND noted.event_date=current.event_date
        AND noted.body_hash=current.body_hash
        AND noted.body=current.body
        AND (noted.id=current.id OR noted.observed_at<=current.observed_at)
      ORDER BY (n.document_id=?) DESC,n.registered_revision DESC,n.id'''
    try:
        rows=list(db.execute(query,(document_id,document_id)))
        # The journal's accepted source generation is authoritative for its
        # current summary. Immutable archive notes remain in archived_notes.
        try:
            active=list(db.execute('''SELECT n.* FROM active_source_notes n
              JOIN documents noted ON noted.id=n.document_id
              JOIN documents current ON current.id=?
              WHERE noted.source_id=current.source_id
                AND noted.event_date=current.event_date
                AND noted.body_hash=current.body_hash
                AND noted.body=current.body
                AND (noted.id=current.id OR noted.observed_at<=current.observed_at)
              ORDER BY (n.document_id=?) DESC,n.id''',(document_id,document_id)))
        except sqlite3.OperationalError as error:
            if 'no such table: active_source_notes' not in str(error):raise
            active=[]
        if active:
            return active+[row for row in rows if row['origin']!='source_summary']
        if rows:return rows
        # A deleted original is absent from the active documents table. Its
        # independently sanitized derived note remains useful and may still be
        # shown from the tombstoned archive record.
        deleted='''SELECT n.* FROM deleted_notes n
          JOIN deleted_documents noted ON noted.id=n.document_id
          JOIN deleted_documents current ON current.id=?
          WHERE n.note_json IS NOT NULL
            AND noted.source_id=current.source_id
            AND noted.event_date=current.event_date
            AND noted.body_hash=current.body_hash
            AND (noted.id=current.id OR noted.observed_at<=current.observed_at)
          ORDER BY (n.document_id=?) DESC,n.registered_revision DESC,n.id'''
        return list(db.execute(deleted,(document_id,document_id)))
    except sqlite3.OperationalError as error:
        # Pre-canonical read-only archive caches contain originals only.
        if 'no such table: archived_notes' in str(error) or 'no such table: deleted_notes' in str(error):return []
        raise


def _summary_payload(row):
    payload=json.loads(row['note_json']);record=payload.get('legacy_record',payload)
    return payload,record,record.get('payload',record)


def meeting_display_title(db,document_id,rows=None):
    document=db.execute('SELECT title,event_date,body FROM documents WHERE id=?',(document_id,)).fetchone()
    if not document:
        try:document=db.execute("SELECT title,event_date,'' AS body FROM deleted_documents WHERE id=?",(document_id,)).fetchone()
        except sqlite3.OperationalError:pass
    if not document:return None
    rows=_summary_rows(db,document_id) if rows is None else rows
    payloads=[]
    for row in rows:
        payload,record,value=_summary_payload(row)
        # display_title belongs to source_summary itself. Legacy envelopes keep
        # their user-visible title/topics inside the nested value.
        payloads.append({**value,**({'display_title':payload['display_title']} if 'display_title' in payload else {})})
    return resolve_display_title(document['title'],document['body'],document['event_date'],note_payloads=payloads)


def summaries(db,document_id):
    result=[];rows=_summary_rows(db,document_id)
    display=meeting_display_title(db,document_id,rows)
    source=db.execute('SELECT title FROM documents WHERE id=?',(document_id,)).fetchone()
    if not source:
        try:source=db.execute('SELECT title FROM deleted_documents WHERE id=?',(document_id,)).fetchone()
        except sqlite3.OperationalError:pass
    for row in rows:
        payload,record,value=_summary_payload(row)
        # A historical title backfill is an evidence note, not a user-facing
        # meeting summary. It remains available to meeting_display_title above.
        if payload.get('title_backfill_only') is True:continue
        result.append({'id':row['id'],'origin':row['origin'],'origin_id':row['origin_id'],
            'legacy_status':record.get('status'),'title':display['text'] if display else value.get('title'),
            'source_title':source['title'] if source else value.get('title'),
            'display_title_method':display['method'] if display else None,
            'ai_summary':value.get('ai_summary',''),'executive_summary':value.get('executive_summary',''),
            'topics':value.get('topics',[]),'key_decisions':value.get('key_decisions',[]),
            'participants':value.get('participants',[]),'provenance':payload.get('link_provenance',{})})
    # An existing accepted meeting may have been edited after inbox promotion.
    # Keep both snapshots but present the accepted meeting's text first.
    return sorted(result,key=lambda row:row['origin']!='legacy_meetings')

def rebuild_archive(store,destination,*,through=None,journal_through=None,_logical_base=None):
    space=store.space();ceiling=space['archive_revision'] if through is None else through
    if type(ceiling) is not int or not 0<=ceiling<=space['archive_revision']:raise ValidationError('Invalid archive snapshot')
    if journal_through is not None and (type(journal_through) is not int or not 0<=journal_through<=space['revision']):
        raise ValidationError('Invalid journal snapshot for archive summary')
    target=Path(destination);target.parent.mkdir(mode=0o700,exist_ok=True,parents=True)
    fd,name=tempfile.mkstemp(prefix='.'+space['id']+'-archive-',suffix='.sqlite',dir=target.parent);os.close(fd)
    db=None;revisions=set();counts={'documents':0,'notes':0}
    try:
        db=connect(name)
        db.execute('CREATE TABLE archived_notes (id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id),origin TEXT NOT NULL,origin_id TEXT NOT NULL,note_json TEXT NOT NULL,note_hash TEXT NOT NULL,registered_revision INTEGER NOT NULL)')
        db.execute('CREATE TABLE deleted_documents (id TEXT PRIMARY KEY,source_id TEXT NOT NULL,event_date TEXT NOT NULL,observed_at TEXT NOT NULL,title TEXT NOT NULL,body_hash TEXT NOT NULL,export_hash TEXT NOT NULL,metadata_json TEXT NOT NULL,redaction_id TEXT NOT NULL,registered_revision INTEGER NOT NULL)')
        db.execute('CREATE TABLE deleted_notes (id TEXT PRIMARY KEY,document_id TEXT NOT NULL,origin TEXT NOT NULL,origin_id TEXT NOT NULL,note_json TEXT,sanitized_note_hash TEXT,note_hash TEXT NOT NULL,redaction_id TEXT NOT NULL,registered_revision INTEGER NOT NULL)')
        for kind in ('documents','notes'):
            for raw in store.archive_rows(kind,through=ceiling):
                revision=raw.get('registered_revision')
                if raw.get('space_id')!=space['id'] or type(revision) is not int or not 1<=revision<=ceiling or revision in revisions:
                    raise ValidationError('Invalid archive revision')
                revisions.add(revision)
                if kind=='documents':
                    row=verify_document(raw)
                    if row.get('redaction_id'):
                        db.execute('INSERT INTO deleted_documents VALUES (?,?,?,?,?,?,?,?,?,?)',tuple(row[k] for k in ('id','source_id','event_date','observed_at','title','body_hash','export_hash','metadata_json','redaction_id'))+(revision,))
                    else:
                        db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',tuple(row[k] for k in FIELDS))
                        for ordinal,(start,end,text) in enumerate(spans(row['body'])):
                            cursor=db.execute('INSERT INTO passages(document_id,ordinal,start,end,text,title) VALUES (?,?,?,?,?,?)',(row['id'],ordinal,start,end,text,row['title']))
                            db.execute('INSERT INTO passage_search(rowid,text,title) VALUES (?,?,?)',(cursor.lastrowid,text,row['title']))
                else:
                    row=verify_note(raw)
                    if row.get('redaction_id'):
                        db.execute('INSERT INTO deleted_notes VALUES (?,?,?,?,?,?,?,?,?)',tuple(row.get(k) for k in ('id','document_id','origin','origin_id','note_json','sanitized_note_hash','note_hash','redaction_id'))+(revision,))
                    else:
                        db.execute('INSERT INTO archived_notes VALUES (?,?,?,?,?,?,?)',tuple(row[k] for k in ('id','document_id','origin','origin_id','note_json','note_hash'))+(revision,))
                counts[kind]+=1
        if len(revisions)!=ceiling:raise ValidationError('Archive snapshot has missing revisions')
        db.execute('CREATE TABLE active_source_notes (id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id),origin TEXT NOT NULL,origin_id TEXT NOT NULL,note_json TEXT NOT NULL,note_hash TEXT NOT NULL)')
        if journal_through is not None:
            from generation_review import logical_entries
            logical=(_logical_base({**space,'revision':journal_through}) if _logical_base is not None
                     else logical_entries(store.entries(through=journal_through)))
            for entry in logical:
                if entry['kind']!='source':continue
                note=entry['payload'].get('archive_note')
                if note is None:continue
                checked=verify_note(note)
                source=entry['source']
                document=db.execute('SELECT source_id,event_date,body_hash FROM documents WHERE id=?',(checked['document_id'],)).fetchone()
                if document is None:continue  # Redacted or no longer present in this archive snapshot.
                if (checked['origin']!='source_summary' or document['source_id']!=source['source_id']
                        or document['event_date']!=source['event_date'] or document['body_hash']!=source['content_hash']):
                    raise ValidationError('Journal summary does not match its immutable original')
                db.execute('INSERT INTO active_source_notes VALUES (?,?,?,?,?,?)',tuple(checked[k] for k in ('id','document_id','origin','origin_id','note_json','note_hash')))
        db.execute('CREATE TABLE archive_cursor (space_id TEXT PRIMARY KEY,revision INTEGER NOT NULL)')
        db.execute('INSERT INTO archive_cursor VALUES (?,?)',(space['id'],ceiling));db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValidationError('Archive cache integrity failure')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.execute('PRAGMA journal_mode=DELETE');db.close();db=None
        os.chmod(name,0o600);os.replace(name,target)
        return {'space_id':space['id'],'archive_revision':ceiling,**counts,'model_api_calls':0}
    finally:
        if db:db.close()
        for suffix in ('','-wal','-shm'):
            try:Path(name+suffix).unlink()
            except FileNotFoundError:pass
