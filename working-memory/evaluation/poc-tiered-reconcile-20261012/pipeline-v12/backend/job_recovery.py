"""Owner-reviewed recovery consumes saved results only; never calls a model."""
from datetime import datetime,timezone
import json,re
from uuid import UUID
from journal_projection import prepare_source,digest
from memory import ValidationError
from journal_store import RevisionConflict
from canonical_archive import verify_document


def _time(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')) if value else None


def inspect(service,identity,job_id,command_id):
    if not isinstance(job_id,str) or not re.fullmatch('[0-9a-f]{64}',job_id):raise ValidationError('Invalid job ID')
    command_id=str(UUID(command_id))
    space=service.store.space();service.authorize(identity,space)
    detail=service.store.call('job_detail',job_id=job_id)
    if not detail:raise ValidationError('Unknown job')
    job=detail['job']
    if job['space_id']!=space['id'] or job['id']!=job_id:raise ValidationError('Job scope mismatch')
    status=service.store.call('processing_status');config=status.get('config') or {}
    active=job['state'] in ('running','prepared') and bool(job.get('lease_until')) and _time(job['lease_until'])>datetime.now(timezone.utc)
    recoverable=job['state'] not in ('applied','archived','queued') and not active
    unknown=any(not call['received'] for call in detail['calls'])
    policy=(config.get('automatic_from') is not None and job['event_date']>=config['automatic_from'] and job['pipeline']==config.get('pipeline'))
    payload=None;blocked=None
    prepared=job.get('prepared_payload')
    with service.projection(identity) as (db,current):
        if current['revision']!=space['revision']:raise RevisionConflict('Memory changed during recovery preview')
        represented=db.execute('SELECT 1 FROM source_versions WHERE source_id=? OR event_date>? LIMIT 1',(job['source_id'],job['event_date'])).fetchone()
        # Check every archived version: a changed original requires an explicit
        # generation review, even if no older version reached working memory.
        with service.archive_projection(identity) as (archive,_):
            versions=archive.execute('SELECT DISTINCT body_hash FROM documents WHERE source_id=?',(job['source_id'],)).fetchall()
        if represented or len(versions)!=1:policy=False;blocked='source_generation_review'
        if recoverable and policy and not unknown and prepared:
            document=verify_document(service.store.call('archive_document',document_id=job['document_id']))
            source={'id':job['id'],'source_id':document['source_id'],'content_hash':document['body_hash'],
                    'event_date':document['event_date'],'title':document['title'],'transcript':document['body'],'observed_at':document['observed_at']}
            try:
                payload=prepare_source(db,source,prepared['proposal'],pipeline=job['pipeline'],model=prepared['model'],usage=prepared.get('usage'),
                    provenance={**prepared.get('provenance',{}),'context_revision':space['revision'],
                                'previous_context_revision':job.get('expected_revision'),'previous_result_sha256':prepared['result_sha256'],
                                'owner_recovery_command':command_id,'owner_id':identity['id'],'mode':'owner_reviewed_saved_result'})
                if 'archive_note' in prepared:payload['archive_note']=prepared['archive_note']
            except (ValidationError,KeyError,TypeError):blocked='saved_result_requires_content_review'
    same_context=job.get('expected_revision')==space['revision']
    retry=bool(recoverable and policy and not unknown and (same_context or (not detail['calls'] and not prepared))
               and not (job.get('reason')=='validation_failed' and not prepared))
    observations=payload['proposal']['observations'] if payload else []
    # Show the normalized result, including newly protected personal edits,
    # rather than the unguarded saved proposal.
    if payload:
        from human_decisions import guard_updates
        with service.projection(identity) as (db,current):
            if current['revision']!=space['revision']:raise RevisionConflict('Memory changed during recovery preview')
            observations=guard_updates(db,payload['proposal'])['observations']
    public={'job_id':job_id,'title':detail['title'],'event_date':job['event_date'],'state':job['state'],'reason':job.get('reason'),
            'expected_revision':space['revision'],'expected_updated_at':job['updated_at'],'command_id':command_id,
            'calls':detail['calls'],'decisions':detail['decisions'],'unknown_provider_outcome':unknown,
            'can_archive':recoverable,'can_retry':retry,'can_rebase':payload is not None,
            'blocked':blocked,'prepared_observations':observations,'preview_hash':digest(payload) if payload else None}
    return public,payload


def decide(service,identity,request):
    fields={'job_id','command_id','expected_revision','expected_updated_at','action','reason','preview_hash'}
    if not isinstance(request,dict) or set(request)!=fields:raise ValidationError('Invalid recovery decision')
    if request['action'] not in ('retry','archive_only','rebase_prepared') or not isinstance(request['reason'],str) or not 1<=len(request['reason'].strip())<=4000:
        raise ValidationError('Explicit recovery reason required')
    if type(request['expected_revision']) is not int or request['expected_revision']<0:raise ValidationError('Invalid recovery revision')
    command_id=str(UUID(request['command_id']));space=service.store.space();service.authorize(identity,space)
    existing=service.store.call('job_decision',command_id=command_id)
    if existing:
        saved=existing['request']
        if existing['actor_id']!=identity['id'] or any(saved.get(k)!=request[k] for k in ('job_id','expected_revision','action','reason')) or _time(saved['expected_updated_at'])!=_time(request['expected_updated_at']):
            raise RevisionConflict('Recovery identity reused with different content')
        wanted=digest(saved['payload']) if saved.get('payload') else None
        if wanted!=request['preview_hash']:raise RevisionConflict('Recovery result changed')
        return {**existing['result'],'repeated':True}
    public,payload=inspect(service,identity,request['job_id'],command_id)
    if public['expected_revision']!=request['expected_revision'] or _time(public['expected_updated_at'])!=_time(request['expected_updated_at']):
        raise RevisionConflict('Refresh the changed recovery view')
    action=request['action'];flag={'retry':'can_retry','archive_only':'can_archive','rebase_prepared':'can_rebase'}[action]
    if not public[flag]:raise ValidationError('Recovery action is not safe for this job')
    if action=='rebase_prepared':
        if public['preview_hash']!=request['preview_hash']:raise RevisionConflict('Reviewed result changed')
    else:
        payload=None
        if request['preview_hash'] is not None:raise ValidationError('Unexpected result replacement')
    return service.store.call('resolve_job',job_id=request['job_id'],command_id=command_id,actor_id=identity['id'],
                              expected_revision=request['expected_revision'],expected_updated_at=request['expected_updated_at'],
                              action=action,reason=request['reason'],payload=payload)
