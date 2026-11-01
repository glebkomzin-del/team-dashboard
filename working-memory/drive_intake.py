"""Lossless n8n Drive-envelope adapter. No model access and no Drive writes."""
from datetime import date,datetime,timezone
import json,re
from archive_drive import body_offset
from archive_index import digest
from canonical_archive import verify_document
from memory import ValidationError
from journal_store import RevisionConflict

FOLDERS=frozenset(('1BFIu-ukqXgQu5143cmUaJvsaqLfmxLw2',))

def document_from_original(original, *, observed_at=None):
    if not isinstance(original,dict) or original.get('intake_status')!='read_verified_not_imported':
        raise ValidationError('Verified Drive original required')
    meta=original.get('drive_metadata');text=original.get('transcript')
    if not isinstance(meta,dict) or not isinstance(text,str) or not text.strip() or '\ufffd' in text:
        raise ValidationError('Complete decoded original required')
    try:text.encode('utf-8')
    except UnicodeError:raise ValidationError('Invalid source encoding')
    if len(text.encode('utf-8'))>2_500_000:raise ValidationError('Original exceeds intake size; never truncate')
    identifier=meta.get('id');name=meta.get('name');parents=meta.get('parents')
    if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',identifier):raise ValidationError('Invalid Drive ID')
    if meta.get('mime_type')!='application/vnd.openxmlformats-officedocument.wordprocessingml.document':raise ValidationError('Unsupported original format')
    if not isinstance(parents,list) or not all(isinstance(p,str) for p in parents) or not FOLDERS.intersection(parents):raise ValidationError('Source outside configured folders')
    if not isinstance(name,str) or len(name)>1000:raise ValidationError('Invalid source name')
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2})\s*(.+)',name)
    if not match:raise ValidationError('Missing meeting date in source name')
    day,title=match.groups();date.fromisoformat(day);title=re.sub(r'\.docx$','',title,flags=re.I)
    if not title.strip() or (original.get('source_id'),original.get('event_date'),original.get('title'))!=('drive:'+identifier,day,title):
        raise ValidationError('Source identity or date mismatch')
    if not isinstance(meta.get('version'),str) or not re.fullmatch(r'\d+',meta['version']):raise ValidationError('Missing Drive version')
    modified=meta.get('modified_time')
    if not isinstance(modified,str) or not datetime.fromisoformat(modified.replace('Z','+00:00')).tzinfo:raise ValidationError('Invalid modification time')
    offset,transform=body_offset(text);body=text[offset:]
    if not body.strip():raise ValidationError('Empty transcript body')
    metadata={'source_id':original['source_id'],'event_date':day,'title':title,
              'drive_metadata':{key:meta.get(key) for key in ('id','name','mime_type','version','modified_time','parents','md5_checksum')},
              'export_sha256':digest(text),'export_characters':len(text),
              'body_sha256':digest(body),'body_characters':len(body),
              'body_offset_characters':offset,'body_transform':transform}
    # Exactly the serialization used by the existing original archive. The
    # same version must keep its existing identity and first observation time.
    serialized=json.dumps(metadata,ensure_ascii=False,sort_keys=True)
    row={'id':digest(original['source_id']+':'+serialized),'source_id':original['source_id'],
         'event_date':day,'title':title,'observed_at':observed_at or datetime.now(timezone.utc).isoformat(),
         'body_hash':metadata['body_sha256'],'export_hash':metadata['export_sha256'],
         'body':body,'export':text,'metadata_json':serialized}
    if len(json.dumps(row,ensure_ascii=False).encode('utf-8'))>3_000_000:
        raise ValidationError('Lossless archive envelope exceeds gateway size; never truncate')
    return verify_document(row)

def persist_original(store,original,*,pipeline):
    document=document_from_original(original)
    previous=store.call('archive_lookup',document_id=document['id'])
    def reuse(row):
        row=verify_document(row)
        if any(row[k]!=v for k,v in document.items() if k!='observed_at'):
            raise RevisionConflict('Existing original identity differs')
        return row
    if previous:document=reuse(previous)
    try:receipt=store.archive_put(document)
    except RevisionConflict:
        # Concurrent identical readers may race only on the first observation
        # timestamp. Re-read authoritative data, never overwrite it.
        previous=store.call('archive_lookup',document_id=document['id'])
        if not previous:raise
        document=reuse(previous);receipt=store.archive_put(document)
    job=store.call('enqueue',document_id=document['id'],pipeline=pipeline)
    return {'archive':receipt,'job_id':job.get('id'),'state':job['state'],'reason':job.get('reason')}
