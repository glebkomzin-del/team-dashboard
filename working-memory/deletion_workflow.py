"""Restartable product workflow for owner-authorized original-only deletion."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
from uuid import UUID,uuid5

from deletion_backup import persist_restore_barrier
from durable_calls import OutcomeUnknown,drain_outbox
from memory import ValidationError
from original_deletion import prepare_sanitization_plan,verify_redacted_entry
from original_deletion_service import _deletion_inputs,stage_and_plan,purge
from question_calls import drain_all_question_outbox


COMMAND_NAMESPACE=UUID('d9fa183d-e515-4732-9fe2-92a819bf78df')


class DeletionPending(RuntimeError):pass


def _status(service,identity,deletion_id):
    value=service.store.call('source_deletion_status',deletion_id=deletion_id,actor_id=identity['id'])
    if value is not None and (not isinstance(value,dict) or value.get('deletion_id')!=deletion_id):
        raise ValidationError('Invalid deletion status')
    return value


def public_status(value):
    if value is None:return None
    return {key:value.get(key) for key in ('deletion_id','source_id','state','requested_at','completed_at')}


def status_for_source(service,identity,source_id):
    if not isinstance(source_id,str) or not 1<=len(source_id)<=512:raise ValidationError('Invalid source identity')
    service.authorize(identity,service.store.space())
    rows=service.store.call('source_deletion_ledger',actor_id=identity['id'])
    if not isinstance(rows,list):raise ValidationError('Invalid deletion ledger')
    matches=[row for row in rows if isinstance(row,dict) and row.get('source_id')==source_id]
    if not matches:return None
    matches.sort(key=lambda row:(row.get('ledger_revision',-1),row.get('deletion_id','')))
    latest=matches[-1]
    return None if latest.get('superseded_by_reimport') is True else public_status(latest)


def _resume_plan(service,identity,deletion_id,source_id,packages):
    entries=service.store.call('source_deletion_inputs',source_id=source_id,actor_id=identity['id'])
    _,transcripts=_deletion_inputs(entries)
    after=''
    while True:
        rows=service.store.call('source_deletion_candidates',deletion_id=deletion_id,actor_id=identity['id'],after=after)
        if not isinstance(rows,list) or len(rows)>32:raise ValidationError('Invalid deletion candidate page')
        if not rows:break
        for row in rows:
            candidate=row;removed=0;scan={'changed':False,'removed_characters':0}
            for transcript in transcripts:
                plan=prepare_sanitization_plan(candidate,transcript)
                removed+=plan['scan']['removed_characters'];candidate={**candidate,'data':plan['replacement']};scan=plan['scan']
            scan={**scan,'changed':candidate['data']!=row['data'],'removed_characters':removed}
            service.store.call('source_deletion_plan_put',deletion_id=deletion_id,actor_id=identity['id'],
                scope=row['scope'],record_key=row['record_key'],before_hash=row['before_hash'],
                replacement=plan['replacement'],scan_receipt=scan)
            after=row['scope']+'|'+row['record_key']
        if len(rows)<32:break
    return transcripts


def registered_cache_directories(service,configured=None):
    root=service.cache.resolve().parent
    raw=os.environ.get('MEMORY_PROJECTION_CACHE_DIRS','') if configured is None else configured
    values=[Path(value) for value in raw.split(os.pathsep) if value]
    result=[service.cache.resolve()]
    for value in values:
        unresolved=value if value.is_absolute() else root/value
        if unresolved.is_symlink():raise ValidationError('Projection cache namespace cannot be a symlink')
        candidate=unresolved.resolve()
        if candidate.parent!=root or 'backup' in candidate.name.lower():
            raise ValidationError('Projection cache namespace is outside the registered app cache root')
        if candidate not in result:result.append(candidate)
    return result


def registered_private_outboxes(service,configured_caches=None):
    """Return only known app-runtime receipt directories under the cache root."""
    root=service.cache.resolve().parent
    result=[('model',directory/'response-outbox') for directory in registered_cache_directories(service,configured_caches)]
    for kind,value in getattr(service,'private_outboxes',[]):
        path=Path(value)
        if path.is_symlink():raise ValidationError('Private outbox cannot be a symlink')
        candidate=path.resolve()
        if root not in candidate.parents or 'backup' in candidate.name.lower():
            raise ValidationError('Private outbox is outside the registered app cache root')
        item=(kind,candidate)
        if item not in result:result.append(item)
    return result


def _prepare_private_runtime(service,configured_caches=None):
    """Drain durable receipts, clear RAM results, and remove disposable sandboxes."""
    directories=registered_cache_directories(service,configured_caches)
    try:
        for kind,directory in registered_private_outboxes(service,configured_caches):
            if not directory.exists():continue
            if directory.is_symlink() or not directory.is_dir():raise ValidationError('Invalid private outbox')
            (drain_outbox if kind=='model' else drain_all_question_outbox)(service.store,directory)
            # Hidden atomic-write remnants and unknown files may contain provider
            # bodies. Their outcome is unclear, so deletion stays resumable.
            if next(directory.iterdir(),None) is not None:raise ValidationError('Private outbox is not fully settled')
        service.clear_private_runtime()
        removed=0
        for namespace in directories:
            if not namespace.exists():continue
            for path in namespace.glob('worker-*'):
                if path.is_symlink() or not path.is_dir():raise ValidationError('Invalid worker sandbox')
                shutil.rmtree(path);removed+=1
        return {'outboxes_checked':len(registered_private_outboxes(service,configured_caches)),
                'worker_sandboxes_removed':removed}
    except (OSError,OutcomeUnknown,ValidationError) as error:
        raise DeletionPending('Private response receipts or worker sandboxes are not settled') from error


def _expected_sparse(package):
    verify_redacted_entry(package);manifest=package['evidence_manifest'];chars=['\u2591']*manifest['original_characters']
    for item in manifest['entries']:
        for offset,char in enumerate(item['quote'],item['start']):chars[offset]=char
    return ''.join(chars)


def rebuild_registered_caches(service,identity,*,deletion_id,source_id,packages,configured=None,runtime_receipt=None):
    space=service.store.space();service.authorize(identity,space)
    directories=registered_cache_directories(service,configured);removed=[]
    with service.exclusive_cache_maintenance():
        for namespace in directories:
            for directory in (namespace,namespace/'archive'):
                if not directory.exists():continue
                if directory.is_symlink() or not directory.is_dir():raise ValidationError('Invalid projection cache namespace')
                candidates={*directory.glob(space['id']+'-*.sqlite*'),*directory.glob('.'+space['id']+'-*.sqlite*')}
                for path in candidates:
                    if path.is_symlink() or not path.is_file():raise ValidationError('Invalid projection cache file')
                    path.unlink();removed.append(str(path.relative_to(namespace.parent)))
    # Rebuild only the configured active namespace from the already-redacted
    # journal. Retired namespaces stay empty and cannot serve an old reader.
    service.warm_projection();service.warm_projection(archive=True)
    expected={package['source']['id']:_expected_sparse(package) for package in packages}
    with service.projection(identity) as (db,_):
        for version,transcript in expected.items():
            row=db.execute('select transcript from source_versions where id=?',(version,)).fetchone()
            if not row or row['transcript']!=transcript:raise ValidationError('Rebuilt projection lacks the attested redacted source')
    with service.archive_projection(identity) as (db,_):
        if db.execute('select 1 from documents where source_id=? limit 1',(source_id,)).fetchone():
            raise ValidationError('Rebuilt archive still exposes the deleted original')
    for namespace in directories[1:]:
        for directory in (namespace,namespace/'archive'):
            if directory.exists() and (next(directory.glob(space['id']+'-*.sqlite*'),None)
                                       or next(directory.glob('.'+space['id']+'-*.sqlite*'),None)):
                raise ValidationError('Retired projection cache was recreated during deletion')
    receipt={'rebuilt':True,'canary_scan_clear':True,'method':'registered-namespace-invalidate-and-rebuild-v1',
             'namespaces_checked':len(directories),'files_removed':len(removed)}
    if runtime_receipt is not None:receipt['private_runtime']=runtime_receipt
    service.store.call('source_deletion_check',deletion_id=deletion_id,actor_id=identity['id'],
                       check_scope='local_caches',receipt=receipt)
    return receipt


def _execute_exclusive(service,identity,request):
    if not isinstance(request,dict) or set(request)!={'deletion_id','source_id'}:raise ValidationError('Invalid deletion request')
    deletion_id=str(UUID(request['deletion_id']));source_id=request['source_id']
    if not isinstance(source_id,str) or not 1<=len(source_id)<=512:raise ValidationError('Invalid source identity')
    service.authorize(identity,service.store.space())
    current=_status(service,identity,deletion_id)
    if current and current.get('source_id')!=source_id:raise ValidationError('Deletion source identity changed')
    if current and current.get('state')=='verified':return {**public_status(current),'retained':['tasks','knowledge','adopted_evidence_quotes']}
    runtime_receipt=_prepare_private_runtime(service)
    if current is None:
        staged=stage_and_plan(service,identity,source_id=source_id,deletion_id=deletion_id)
        packages=staged['packages']
    else:
        packages=current.get('packages')
        if not isinstance(packages,list):raise ValidationError('Deletion packages are unavailable')
        for package in packages:verify_redacted_entry(package)
        if current.get('state')=='prepared':_resume_plan(service,identity,deletion_id,source_id,packages)
    current=_status(service,identity,deletion_id)
    if current['state']=='prepared':
        command_id=str(uuid5(COMMAND_NAMESPACE,deletion_id))
        purge(service,identity,deletion_id=deletion_id,command_id=command_id,packages=packages)
        current=_status(service,identity,deletion_id)
    if current['state']=='verified':return {**public_status(current),'retained':['tasks','knowledge','adopted_evidence_quotes']}
    if current['state']!='purging':raise ValidationError('Deletion cannot be resumed from its current state')
    checks=current.get('checks') if isinstance(current.get('checks'),dict) else {}
    if 'local_caches' not in checks:
        try:
            rebuild_registered_caches(service,identity,deletion_id=deletion_id,source_id=source_id,packages=packages,
                                      runtime_receipt=runtime_receipt)
        except (OSError,ValidationError) as error:raise DeletionPending('Cache privacy maintenance is incomplete') from error
    if 'backup_sets' not in checks:
        ledger_path=os.environ.get('MEMORY_RESTORE_DELETION_LEDGER','')
        try:
            receipt=persist_restore_barrier(service.store,identity,ledger_path)
            service.store.call('source_deletion_check',deletion_id=deletion_id,actor_id=identity['id'],
                               check_scope='backup_sets',receipt=receipt)
        except (OSError,ValidationError) as error:raise DeletionPending('Restore privacy barrier is incomplete') from error
    result=service.store.call('source_deletion_finalize',deletion_id=deletion_id,actor_id=identity['id'])
    if not isinstance(result,dict) or result.get('state')!='verified':raise ValidationError('Deletion finalization is unconfirmed')
    return {'deletion_id':deletion_id,'source_id':source_id,'state':'verified',
            'retained':['tasks','knowledge','adopted_evidence_quotes'],
            'backup_retention':'Alte Sicherungen laufen nach der konfigurierten Aufbewahrung aus; Wiederherstellung respektiert den Lösch-Wasserstand.'}


def execute(service,identity,request):
    with service.exclusive_privacy_maintenance():return _execute_exclusive(service,identity,request)


__all__=['DeletionPending','execute','public_status','status_for_source','registered_cache_directories',
         'registered_private_outboxes','rebuild_registered_caches']
