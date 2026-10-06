"""Private, lossless canonical exports with an offline reconstruction check.

No model API. Queue rows are snapshotted atomically; immutable source journals
and original archives are pinned to the same database revision boundary.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from gateway_journal import GatewayJournal
from journal_projection import rebuild
from canonical_archive import rebuild_archive
from memory import connect,ValidationError,overview
from archive_index import connect as open_archive

FILES=('snapshot.json','queue.jsonl','journal.jsonl','documents.jsonl','notes.jsonl')

def checksum(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def private_json(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        os.chmod(path,0o600);json.dump(value,stream,ensure_ascii=False,allow_nan=False)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())


def private_rows(path,rows):
    count=0
    with Path(path).open('x',encoding='utf-8') as stream:
        os.chmod(path,0o600)
        for value in rows:
            stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');count+=1
        stream.flush();os.fsync(stream.fileno())
    return count


def read_rows(path):
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():raise ValidationError('Empty record in backup')
            value=json.loads(line)
            if not isinstance(value,dict):raise ValidationError('Invalid backup record')
            yield value


class FrozenStore:
    def __init__(self,folder):
        self.folder=Path(folder);self.header=json.loads((self.folder/'snapshot.json').read_text())
    def space(self):return {**self.header['space_json'],'revision':self.header['revision'],'archive_revision':self.header['archive_revision']}
    def entries(self,*,after=0,through=None):
        ceiling=self.header['revision'] if through is None else through;cursor=0
        for entry in read_rows(self.folder/'journal.jsonl'):
            if entry['revision']!=cursor+1:raise ValidationError('Missing journal revision in backup')
            cursor=entry['revision']
            if after<cursor<=ceiling:yield entry
        if cursor!=self.header['revision']:raise ValidationError('Incomplete journal backup')
    def source(self,version):raise ValidationError('Backup journal must embed every original source')
    def archive_rows(self,kind,*,through,after=0):
        if through!=self.header['archive_revision']:raise ValidationError('Backup archive boundary changed')
        for row in read_rows(self.folder/(kind+'.jsonl')):
            if after<row['registered_revision']<=through:yield row
            elif row['registered_revision']>through:raise ValidationError('Archive record outside backup boundary')


def verify(folder):
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_text())
    if manifest.get('format') not in ('working-memory-backup-v1','working-memory-backup-v2') or set(manifest.get('files',{}))!=set(FILES):
        raise ValidationError('Unknown or incomplete backup manifest')
    for name,proof in manifest['files'].items():
        path=folder/name
        if path.is_symlink() or path.stat().st_size!=proof['bytes'] or checksum(path)!=proof['sha256']:
            raise ValidationError('Backup file checksum mismatch')
    store=FrozenStore(folder);space=store.space();counts={};last=0;jobs={};calls=[];generations=[];deletions={};deletion_children=[]
    search_documents={};search_snapshots={};search_results=[];questions={};question_calls=[];conversations={};recoveries=[];isolations=[]
    for row in read_rows(folder/'queue.jsonl'):
        if type(row['sequence']) is not int or row['sequence']<=last:raise ValidationError('Backup record order mismatch')
        last=row['sequence']
        if hashlib.sha256(row['record_json'].encode()).hexdigest()!=row['record_hash']:raise ValidationError('Queue record checksum mismatch')
        value=json.loads(row['record_json']);kind=row['kind']
        if kind not in ('config','job','call','job_isolation','job_decision','generation_review','search_document','search_snapshot','search_result','conversation','pipeline_recovery','question','question_call','source_deletion','source_deletion_version','source_deletion_check','source_reimport_authorization') or value.get('space_id')!=space['id']:raise ValidationError('Queue backup scope mismatch')
        counts[kind]=counts.get(kind,0)+1
        if kind=='job':
            if value['id'] in jobs:raise ValidationError('Duplicate queue job')
            jobs[value['id']]=value
        if kind=='call':calls.append(value)
        if kind=='job_isolation':isolations.append(value)
        if kind=='pipeline_recovery':recoveries.append(value)
        if kind=='generation_review':generations.append(value)
        if kind=='source_deletion':
            if value['id'] in deletions:raise ValidationError('Duplicate source deletion ledger')
            deletions[value['id']]=value
        if kind in ('source_deletion_version','source_deletion_check'):deletion_children.append(value)
        if kind=='search_document':
            vector=json.loads(value['embedding']) if isinstance(value['embedding'],str) else value['embedding']
            if value['id'] in search_documents or hashlib.sha256(value['body'].encode()).hexdigest()!=value['content_hash']:
                raise ValidationError('Search document checksum or identity mismatch')
            if value['embedding_model']!='text-embedding-3-small' or len(vector)!=1536 or any(type(x) not in (int,float) or not math.isfinite(x) for x in vector) or not any(vector):
                raise ValidationError('Invalid backed-up vector')
            search_documents[value['id']]=value['content_hash']
        if kind=='search_snapshot':
            ids=value['document_ids']
            if value['id'] in search_snapshots or ids!=sorted(set(ids)) or hashlib.sha256(','.join(ids).encode()).hexdigest()!=value['id']:
                raise ValidationError('Invalid backed-up search snapshot')
            search_snapshots[value['id']]=set(ids)
        if kind=='search_result':search_results.append(value)
        if kind=='conversation':
            if value.get('id') in conversations or not value.get('id') or value.get('owner_id')!=space['owner_id']:
                raise ValidationError('Duplicate conversation or incorrect conversation owner')
            conversations[value['id']]=value
        if kind=='question':
            if value['id'] in questions:raise ValidationError('Duplicate question receipt')
            questions[value['id']]=value
            for field in ('request','response'):
                raw=value.get(field+'_json');h=value.get(field+'_hash')
                effective=value.get('sanitized_'+field+'_hash') or h
                if value.get('sanitized_'+field+'_hash') and not value.get('redaction_id'):raise ValidationError('Sanitized question receipt lacks a deletion ledger')
                if raw is not None and (effective is None or hashlib.sha256(raw.encode()).hexdigest()!=effective):raise ValidationError('Question receipt checksum mismatch')
                if raw is None and h is not None and not value.get('redaction_id'):raise ValidationError('Question receipt lost content without a deletion ledger')
        if kind=='question_call':question_calls.append(value)
    if sum(counts.values())!=store.header['record_count'] or sum(counts.values())!=manifest['counts']['queue']:
        raise ValidationError('Incomplete queue snapshot')
    if manifest['format']=='working-memory-backup-v2':
        deletion_revision=store.header.get('deletion_revision')
        if type(deletion_revision) is not int or deletion_revision<0 or deletion_revision!=space.get('deletion_revision') or manifest.get('deletion_revision')!=deletion_revision:
            raise ValidationError('Backup deletion watermark mismatch')
        if deletions and max(row['ledger_revision'] for row in deletions.values())>deletion_revision:
            raise ValidationError('Deletion ledger exceeds backup watermark')
        if any(row.get('deletion_id') not in deletions for row in deletion_children):
            raise ValidationError('Deletion backup child lost its ledger')
    if counts.get('config',0)>1:raise ValidationError('Multiple processing configurations')
    for ids in search_snapshots.values():
        if ids-set(search_documents):raise ValidationError('Search snapshot lost documents in backup')
    for result in search_results:
        if result['snapshot_id'] not in search_snapshots:raise ValidationError('Search cache lost its snapshot')
        for hit in result['results']:
            if hit['id'] not in search_snapshots[result['snapshot_id']] or hashlib.sha256(hit['text'].encode()).hexdigest()!=search_documents[hit['id']]:
                raise ValidationError('Search cache lost its exact source text')
    call_ids=set()
    for call in calls:
        key=(call['job_id'],call['call_index'])
        if key in call_ids or call['job_id'] not in jobs:raise ValidationError('Missing job or duplicate model call')
        call_ids.add(key)
        for field in ('request','response'):
            raw=call.get(field+'_json');h=call.get(field+'_hash')
            effective=call.get('sanitized_'+field+'_hash') or h
            if call.get('sanitized_'+field+'_hash') and not call.get('redaction_id'):raise ValidationError('Sanitized model receipt lacks a deletion ledger')
            if raw is not None and (effective is None or hashlib.sha256(raw.encode()).hexdigest()!=effective):raise ValidationError('Model receipt checksum mismatch')
            if raw is None and h is not None and not call.get('redaction_id'):raise ValidationError('Model receipt lost content without a deletion ledger')
    isolation_ids=set()
    for audit in isolations:
        job=jobs.get(audit.get('job_id'));job_id=audit.get('job_id')
        # This is a historical event, not a standing permission to skip a job.
        # A late response or an owner decision can invalidate today's positive
        # isolation predicate while the original audit must remain restorable.
        if job is None or job_id in isolation_ids \
          or job.get('source_id')!=audit.get('source_id') or job.get('pipeline')!=audit.get('pipeline') \
          or any(not isinstance(audit.get(field),str) or len(audit[field])!=64 for field in ('body_hash','prepared_hash','call_evidence_hash')):
            raise ValidationError('Technical isolation backup proof mismatch')
        isolation_ids.add(job_id)
    recovery_ids=set()
    for recovery in recoveries:
        identity=recovery.get('failure_id')
        if not identity or identity in recovery_ids or recovery.get('job_id') not in jobs:
            raise ValidationError('Missing job or duplicate pipeline recovery')
        recovery_ids.add(identity)
    conversation_sequences=set()
    for question in questions.values():
        conversation_id=question.get('conversation_id');sequence=question.get('conversation_seq')
        if conversation_id is None:
            if sequence is not None:raise ValidationError('Question sequence has no conversation')
            continue
        if conversation_id not in conversations or type(sequence) is not int or sequence<1:
            raise ValidationError('Question lost its conversation or sequence')
        if question.get('actor_id')!=conversations[conversation_id]['owner_id']:
            raise ValidationError('Question conversation owner mismatch')
        identity=(conversation_id,sequence)
        if identity in conversation_sequences:raise ValidationError('Duplicate conversation sequence')
        conversation_sequences.add(identity)
    question_call_ids=set()
    for call in question_calls:
        key=(call['question_id'],call['call_index'])
        if key in question_call_ids or call['question_id'] not in questions:raise ValidationError('Missing question or duplicate question call')
        question_call_ids.add(key)
        for field in ('request','response'):
            raw=call.get(field+'_json');h=call.get(field+'_hash')
            effective=call.get('sanitized_'+field+'_hash') or h
            if call.get('sanitized_'+field+'_hash') and not call.get('redaction_id'):raise ValidationError('Sanitized question call lacks a deletion ledger')
            if raw is not None and (effective is None or hashlib.sha256(raw.encode()).hexdigest()!=effective):raise ValidationError('Question call checksum mismatch')
            if raw is None and h is not None and not call.get('redaction_id'):raise ValidationError('Question call lost content without a deletion ledger')
    if generations:
        from generation_review import logical_entries,verify_generation
        journal=list(store.entries());review_ids=set()
        for generation in generations:
            if generation['payload'].get('format')=='wm-redacted-generation-v1':
                if not generation.get('redaction_id') or not generation.get('original_payload_hash'):raise ValidationError('Redacted generation lacks an attestation')
                continue
            if generation['id'] in review_ids or type(generation['expected_revision']) is not int or not 0<=generation['expected_revision']<=space['revision']:
                raise ValidationError('Invalid generation backup identity or boundary')
            review_ids.add(generation['id'])
            if generation['review_sha256']!=generation['payload'].get('review_sha256'):
                raise ValidationError('Generation review checksum differs from its envelope')
            if generation.get('job_id') and generation['job_id'] not in jobs:raise ValidationError('Generation recovery job is missing')
            base=logical_entries(journal[:generation['expected_revision']]);verify_generation(base,generation['payload'])
            if generation['state']=='accepted':
                revision=generation['decision_result'].get('revision')
                if type(revision) is not int or not 1<=revision<=len(journal):raise ValidationError('Accepted generation receipt is missing')
                accepted=journal[revision-1]
                if accepted['kind']!='generation' or accepted['command_id']!=generation['decision_command_id'] or accepted['actor_id']!=generation['decision_actor_id'] or accepted['payload']!=generation['payload']:
                    raise ValidationError('Accepted generation differs from immutable journal')
    with tempfile.TemporaryDirectory(prefix='verify-backup-') as tmp:
        archive_path=Path(tmp)/'archive.sqlite';rebuild_archive(store,archive_path)
        archive=open_archive(archive_path,readonly=True)
        try:
            live_doc_count=archive.execute('select count(*) from documents').fetchone()[0]
            deleted_doc_count=archive.execute('select count(*) from deleted_documents').fetchone()[0]
            doc_count=live_doc_count+deleted_doc_count
            note_count=archive.execute('select count(*) from archived_notes').fetchone()[0]+archive.execute('select count(*) from deleted_notes').fetchone()[0]
            for job in jobs.values():
                row=archive.execute('select source_id,body_hash,event_date from documents where id=? union all select source_id,body_hash,event_date from deleted_documents where id=?',(job['document_id'],job['document_id'])).fetchone()
                if not row or row['source_id']!=job['source_id'] or row['event_date']!=job['event_date'] or hashlib.sha256((row['source_id']+':'+row['body_hash']).encode()).hexdigest()!=job['id']:
                    raise ValidationError('Queue job original missing or changed')
                for audit in isolations:
                    if audit['job_id']==job['id'] and audit['body_hash']!=row['body_hash']:
                        raise ValidationError('Technical isolation original changed')
        finally:archive.close()
        projection_path=Path(tmp)/'projection.sqlite';rebuild(store,projection_path)
        db=connect(projection_path)
        try:
            if db.execute('pragma integrity_check').fetchone()[0]!='ok':raise ValidationError('Projection restore integrity failure')
            state=overview(db);observation_count=len(state['knowledge'])
        finally:db.close()
    if doc_count!=manifest['counts']['documents'] or note_count!=manifest['counts']['notes'] or manifest['counts']['journal']!=space['revision']:
        raise ValidationError('Archive or journal backup count mismatch')
    return {'verified':True,'space_id':space['id'],'revision':space['revision'],'archive_revision':space['archive_revision'],
            'documents':doc_count,'notes':note_count,'observations':observation_count,'queue_records':counts,'model_api_calls':0}


def export(store,folder,*,snapshot_id=None):
    folder=Path(folder);folder.mkdir(mode=0o700,parents=True,exist_ok=False)
    snapshot_id=snapshot_id or str(uuid4())
    private_json(folder/'request.json',{'snapshot_id':snapshot_id,'space_id':store.space_id})
    header=store.call('backup_begin',snapshot_id=snapshot_id)
    if header.get('id')!=snapshot_id or header.get('space_id')!=store.space_id:raise ValidationError('Backup snapshot scope mismatch')
    private_json(folder/'snapshot.json',header)
    def queue():
        cursor=0;count=0
        while True:
            page=store.call('backup_page',snapshot_id=snapshot_id,after=cursor)
            if not isinstance(page,list) or len(page)>32:raise ValidationError('Invalid backup page')
            if not page:break
            for row in page:
                if type(row.get('sequence')) is not int or row['sequence']<=cursor:raise ValidationError('Backup cursor failed to advance')
                cursor=row['sequence'];count+=1
                if count>header['record_count']:raise ValidationError('Backup exceeded its pinned record count')
                yield row
        if count!=header['record_count']:raise ValidationError('Backup queue page missing')
    counts={'queue':private_rows(folder/'queue.jsonl',queue()),
            'journal':private_rows(folder/'journal.jsonl',store.entries(through=header['revision']))}
    for kind in ('documents','notes'):
        counts[kind]=private_rows(folder/(kind+'.jsonl'),store.archive_rows(kind,through=header['archive_revision']))
    manifest={'format':'working-memory-backup-v2','snapshot_id':snapshot_id,'deletion_revision':header.get('deletion_revision',header.get('space_json',{}).get('deletion_revision')),'counts':counts,
              'files':{name:{'bytes':(folder/name).stat().st_size,'sha256':checksum(folder/name)} for name in FILES}}
    private_json(folder/'manifest.json',manifest)
    receipt=verify(folder);private_json(folder/'restore-check.json',receipt)
    # Persisted files and the verification receipt precede release. A failed
    # release leaves an export snapshot, never deletes authoritative app data.
    directory=os.open(folder,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)
    store.call('backup_release',snapshot_id=snapshot_id)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['export','verify']);parser.add_argument('folder');args=parser.parse_args()
    if args.action=='verify':result=verify(args.folder)
    else:
        store=GatewayJournal(os.environ['SUPABASE_URL'],os.environ['SUPABASE_PUBLISHABLE_KEY'],os.environ['MEMORY_JOURNAL_TOKEN'],os.environ['MEMORY_SPACE_ID'])
        result=export(store,args.folder)
    print(json.dumps(result,ensure_ascii=False))
