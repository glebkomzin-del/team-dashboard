"""Bounded recovery and redacted diagnostics for the canonical worker."""
from datetime import datetime,timezone
from uuid import uuid4

from gateway_journal import TransientGateway
from journal_store import JournalUnavailable


def diagnostic(error,op='worker'):
    value=getattr(error,'diagnostic',None)
    if isinstance(value,dict):return dict(value)
    return {'at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            'op':op,'type':type(error).__name__,'http_status':None,'sqlstate':None}


def pause_transient(store,job,lease,error):
    value=diagnostic(error)
    failure_id=str(uuid4())
    try:
        saved=store.call('pause_transport_job',job_id=job['id'],lease_token=lease,
            failure_id=failure_id,diagnostic=value)
        return {'state':'paused','reason':'transport_failed','job_id':job['id'],
                'failure_id':saved.get('failure_id',failure_id),'diagnostic':value,
                'next_retry_at':saved.get('next_retry_at')}
    except JournalUnavailable as pause_error:
        return {'state':'unavailable','reason':'pause_unconfirmed','job_id':job['id'],
                'failure_id':failure_id,'diagnostic':diagnostic(pause_error,'pause_transport_job')}


def recover_transport_pause(store,claim,pipeline):
    """Requeue only a proven pre-model, pre-prepare transport failure."""
    if claim.get('state')!='paused' or claim.get('reason')!='transport_failed' or not claim.get('job_id'):
        return claim
    detail=store.call('job_detail',job_id=claim['job_id'])
    status=store.call('processing_status');space=store.space()
    job=detail.get('job') if isinstance(detail,dict) else None
    calls=detail.get('calls') if isinstance(detail,dict) else None
    failures=detail.get('transport_failures') if isinstance(detail,dict) else None
    config=status.get('config') if isinstance(status,dict) else None
    open_failure=(failures[-1] if isinstance(failures,list) and failures else None)
    safe=(isinstance(job,dict) and isinstance(calls,list) and not calls and isinstance(config,dict)
          and isinstance(open_failure,dict) and open_failure.get('recovered_at') is None
          and job.get('id')==claim['job_id'] and job.get('space_id')==space.get('id')
          and job.get('state')=='review' and job.get('reason')=='transport_failed'
          and job.get('pipeline')==pipeline==config.get('pipeline') and config.get('enabled') is True
          and config.get('automatic_from') is not None and job.get('event_date','')>=config['automatic_from']
          and job.get('expected_revision')==space.get('revision') and job.get('prepared_payload') is None)
    if not safe:return {**claim,'recovery':'manual_review_required'}
    try:
        return store.call('recover_transport_job',job_id=job['id'],pipeline=pipeline,
            failure_id=open_failure['failure_id'],expected_revision=space['revision'],expected_updated_at=job['updated_at'])
    except ValueError:
        # Allows a staged rollout where the worker lands before the gateway hook.
        return {**claim,'recovery':'gateway_hook_required'}
    except JournalUnavailable as error:
        return {**claim,'recovery':'unconfirmed','diagnostic':diagnostic(error,'recover_transport_job')}
