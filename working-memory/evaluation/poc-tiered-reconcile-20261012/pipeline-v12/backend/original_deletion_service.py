"""Owner-authorized orchestration for original-only deletion.

No model calls are made.  Staging and scanning are restartable; the database
purge is one hash-bound transaction.  External backup retention and final owner
UI are deliberately separate operational steps.
"""
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
from uuid import UUID
from generation_review import logical_entries
from original_deletion import prepare_redacted_entry,prepare_sanitization_plan,plaintext_canaries
from projection_snapshot import build_snapshot
from memory import ValidationError


def _owner(service,identity):
    space=service.store.space();service.authorize(identity,space);return space


def _deletion_inputs(entries):
    if not isinstance(entries,list) or not entries:raise ValidationError('Source has no live original')
    accepted=[];transcripts=[];seen=set()
    for entry in entries:
        if not isinstance(entry,dict):raise ValidationError('Invalid source deletion input')
        source=entry.get('source')
        transcript=source.get('transcript') if isinstance(source,dict) else None
        if entry.get('kind')=='source':accepted.append(entry)
        elif entry.get('kind')!='archive_only':raise ValidationError('Invalid source deletion input')
        if not isinstance(transcript,str) or not transcript:raise ValidationError('Invalid source deletion transcript')
        if transcript not in seen:transcripts.append(transcript);seen.add(transcript)
    return accepted,transcripts


def stage_and_plan(service,identity,*,source_id,deletion_id,prepared_at=None):
    space=_owner(service,identity);deletion_id=str(UUID(deletion_id))
    if not isinstance(source_id,str) or not 1<=len(source_id)<=512:raise ValidationError('Invalid source identity')
    entries=service.store.call('source_deletion_inputs',source_id=source_id,actor_id=identity['id'])
    accepted,transcripts=_deletion_inputs(entries)
    prepared_at=prepared_at or datetime.now(timezone.utc).isoformat()
    packages=[prepare_redacted_entry(entry,deletion_id=deletion_id,prepared_at=prepared_at) for entry in accepted]
    stage=service.store.call('source_deletion_stage',deletion_id=deletion_id,actor_id=identity['id'],source_id=source_id,packages=packages)
    after='';planned=0;removed=0
    while True:
        rows=service.store.call('source_deletion_candidates',deletion_id=deletion_id,actor_id=identity['id'],after=after)
        if not isinstance(rows,list) or len(rows)>32:raise ValidationError('Invalid deletion candidate page')
        if not rows:break
        for row in rows:
            candidate=row;row_removed=0;scan={'changed':False,'removed_characters':0}
            for transcript in transcripts:
                plan=prepare_sanitization_plan(candidate,transcript)
                row_removed+=plan['scan']['removed_characters']
                candidate={**candidate,'data':plan['replacement']}
                scan=plan['scan']
            scan={**scan,'changed':candidate['data']!=row['data'],'removed_characters':row_removed}
            service.store.call('source_deletion_plan_put',deletion_id=deletion_id,actor_id=identity['id'],
                scope=row['scope'],record_key=row['record_key'],before_hash=row['before_hash'],
                replacement=plan['replacement'],scan_receipt=scan)
            planned+=1;removed+=row_removed
            after=row['scope']+'|'+row['record_key']
        if len(rows)<32:break
    return {'stage':stage,'packages':packages,'planned_records':planned,'removed_characters':removed,'space':space}


def purge(service,identity,*,deletion_id,command_id,packages):
    space=_owner(service,identity);deletion_id=str(UUID(deletion_id));command_id=str(UUID(command_id))
    entries=list(service.store.entries(through=space['revision']))
    basis=logical_entries(entries)
    ledger=service.store.call('source_deletion_ledger',actor_id=identity['id'])
    if not isinstance(ledger,list):raise ValidationError('Invalid deletion ledger')
    latest={}
    for row in ledger:
        if not isinstance(row,dict) or row.get('state') not in ('prepared','purging','verified'):continue
        if not isinstance(row.get('source_id'),str) or not isinstance(row.get('deletion_id'),str) \
          or type(row.get('ledger_revision')) is not int:
            raise ValidationError('Invalid deletion ledger entry')
        prior=latest.get(row['source_id'])
        if prior is None or (row['ledger_revision'],row['deletion_id'])>(prior['ledger_revision'],prior['deletion_id']):
            latest[row['source_id']]=row
    deletions=[{'deletion_id':row['deletion_id'],'source_id':row['source_id']}
               for row in sorted(latest.values(),key=lambda item:(item['source_id'],item['deletion_id']))]
    with service.projection(identity) as (db,current):
        if current['revision']!=space['revision']:raise ValidationError('Deletion projection changed')
        snapshot=build_snapshot(db,through_revision=space['revision'],deletions=deletions,
                                logical_basis=basis,redaction_packages=packages)
    return service.store.call('source_deletion_purge',deletion_id=deletion_id,actor_id=identity['id'],
                              command_id=command_id,projection_snapshot=snapshot)


def rebuild_and_attest_local_caches(service,identity,*,deletion_id,transcripts,packages):
    space=_owner(service,identity)
    for directory in (service.cache,service.cache/'archive'):
        for path in directory.glob(space['id']+'-*.sqlite'):
            if path.is_file() and not path.is_symlink():path.unlink()
    service.warm_projection();service.warm_projection(archive=True)
    canaries=[c for transcript in transcripts for c in plaintext_canaries(transcript,window=48,step=24)]
    allowed=sorted({entry['quote'] for package in packages
                    for entry in package['evidence_manifest']['entries']},key=len,reverse=True)
    leaks=[]
    for directory in (service.cache,service.cache/'archive'):
        for path in directory.glob(space['id']+'-*.sqlite'):
            db=sqlite3.connect(path)
            try:body='\n'.join(db.iterdump())
            finally:db.close()
            for quote in allowed:body=body.replace(quote,'')
            if any(canary in body for canary in canaries):leaks.append(path.name)
    if leaks:raise ValidationError('Local cache still contains original plaintext')
    receipt={'rebuilt':True,'canary_scan_clear':True,'files_checked':sum(1 for d in (service.cache,service.cache/'archive') for _ in d.glob(space['id']+'-*.sqlite'))}
    service.store.call('source_deletion_check',deletion_id=str(UUID(deletion_id)),actor_id=identity['id'],check_scope='local_caches',receipt=receipt)
    return receipt
