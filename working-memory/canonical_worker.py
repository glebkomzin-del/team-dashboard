"""Future-only worker: Supabase owns queue, paid responses and publication.

SQLite is a disposable sandbox at the pinned journal revision. No response is
published against a changed context, and no ambiguous paid call is repeated.
"""
import json
import re
from pathlib import Path
import tempfile
from uuid import uuid4

import processor
from canonical_archive import verify_document
from durable_calls import DurableCalls,OutcomeUnknown,drain_outbox,encode,sha
from call_budget import BudgetExceeded
import future_summary
from journal_projection import prepare_source,rebuild
from journal_store import JournalUnavailable,RevisionConflict
from memory import connect,register,ValidationError,fingerprint
from gateway_journal import TransientGateway
from pipeline_runtime import diagnostic,pause_transient,recover_transport_pause
from review_api import open_readonly

_IMAGE_LINE = re.compile(r'\[\d{2}:\d{2}:\d{2}\] Unknown: (?:image|Bild)')

def verified_image_placeholder(body):
    """Only the observed Tactiq metadata envelope plus one image marker."""
    if not isinstance(body,str):return False
    lines=body.splitlines()
    return (len(lines)==5
            and all(lines[i].startswith(label) for i,label in
                    enumerate(('Meeting Titel: ','Teilnehmer: ','Datum: ','Beginn: ')))
            and all(lines[i].split(': ',1)[1].strip() for i in (0,2,3))
            and _IMAGE_LINE.fullmatch(lines[4]) is not None)

def pipeline_version(model):
    text=''.join((Path(__file__).parent/name).read_text() for name in
                ('canonical_worker.py','pipeline_runtime.py','durable_calls.py','future_summary.py','meeting_naming.py'))
    return processor.pipeline_version(model)+':canonical1:'+sha(text)[:16]

class CanonicalWorker:
    def __init__(self,service,model,*,api=None):
        if processor.PROMPT_VERSION not in ('v9','v10','v11') or not processor.ACTION_GATE:
            raise ValidationError('Canonical worker requires versioned v9/v10/v11 rules')
        self.service,self.store,self.model=service,service.store,model
        self.pipeline=pipeline_version(model);self.api=api or processor.model_request
        self.token_counter=None
        if api is None and processor.PROMPT_VERSION=='v11' and model in ('gpt-5.6-terra','gpt-5.6-luna'):
            from openai_provider import count_input_tokens
            self.token_counter=count_input_tokens
        self.outbox=service.cache/'response-outbox'
        base=json.loads((processor.ROOT/'evaluation/schema-v9.json').read_text())
        self.schema=future_summary.schema(base)
        if processor.PROMPT_VERSION in ('v10','v11'):
            from hybrid_schema import extraction_schema
            self.schema=extraction_schema()

    def step(self):
        with self.service.privacy_reader():return self._step()

    def _step(self):
        try:
            drain_outbox(self.store,self.outbox)
            lease=str(uuid4())
            job=self.store.call('claim_job',pipeline=self.pipeline,lease_token=lease)
            if job.get('state')=='paused':return recover_transport_pause(self.store,job,self.pipeline)
        except JournalUnavailable as error:
            return {'state':'unavailable','reason':'storage_unavailable','diagnostic':diagnostic(error)}
        if job.get('state') not in ('running','prepared'):return job
        if job.get('lease_token')!=lease or job.get('pipeline')!=self.pipeline:
            raise ValidationError('Claim identity mismatch')
        try:
            if job['state']=='prepared':return self.store.call('publish_job',job_id=job['id'],lease_token=lease)
            source=self.store.call('archive_document',document_id=job['document_id'])
            document=verify_document(source)
            if source.get('space_id')!=self.store.space_id or document['source_id']!=job['source_id']:
                raise ValidationError('Job source scope mismatch')
            version={'id':job['id'],'source_id':document['source_id'],'content_hash':document['body_hash'],
                     'event_date':document['event_date'],'observed_at':document['observed_at'],
                     'title':document['title'],'transcript':document['body']}
            if fingerprint(version['source_id']+':'+version['content_hash'])!=job['id']:
                raise ValidationError('Job version mismatch')
            status=self.store.call('processing_status')
            config=status.get('config') or {}
            if not config.get('enabled') or not config.get('automatic_from') or version['event_date']<config['automatic_from']:
                raise ValidationError('Historical or disabled source cannot reach the model')
            if verified_image_placeholder(version['transcript']):
                return self.store.call('archive_image_placeholder_job',job_id=job['id'],lease_token=lease,
                                       body_hash=document['body_hash'])
            identity={'role':'owner','id':self.store.space()['owner_id']}
            self.service.cache.mkdir(parents=True,exist_ok=True,mode=0o700)
            with tempfile.TemporaryDirectory(prefix='worker-',dir=self.service.cache) as tmp:
                pinned=Path(tmp)/'pinned.sqlite'
                rebuild(self.store,pinned,through=job['expected_revision'])
                base=open_readonly(pinned);scratch=connect(Path(tmp)/'scratch.sqlite')
                try:
                    base.backup(scratch)
                    meeting={'id':job['id'],'source_id':version['source_id'],'title':version['title'],
                             'meeting_date':version['event_date'],'observed_at':version['observed_at'],'raw_transcript':version['transcript']}
                    detail=self.store.call('job_detail',job_id=job['id'])
                    prior_calls=detail.get('calls') if isinstance(detail,dict) else None
                    if not isinstance(prior_calls,list) or [call.get('index') for call in prior_calls]!=list(range(len(prior_calls))) or any(not call.get('received') for call in prior_calls):
                        raise OutcomeUnknown('Prior model-call history is incomplete')
                    calls=DurableCalls(self.store,job,self.api,self.schema,self.outbox,start_index=len(prior_calls),
                        prior_calls=prior_calls if processor.PROMPT_VERSION in ('v10','v11') else None,token_counter=self.token_counter)
                    # Archive projection is itself read-only and pinned while
                    # building context; the service lock is not held during API calls.
                    with self.service.archive_projection(identity) as (archive,_):
                        archive_path=archive.execute('PRAGMA database_list').fetchone()[2]
                        local_archive=Path(tmp)/'archive.sqlite'
                        import sqlite3
                        copy=sqlite3.connect(local_archive)
                        try:archive.backup(copy)
                        finally:copy.close()
                    result=processor.process(scratch,meeting,self.model,api=calls,pipeline=self.pipeline,
                        archive_db=str(local_archive),extra_instruction=future_summary.INSTRUCTION,
                        extraction_recovery=processor.PROMPT_VERSION in ('v10','v11'))
                    if result['status']!='applied':raise ValidationError('Sandbox result not applied')
                    row=scratch.execute("SELECT proposal_json FROM runs WHERE job_id=? AND outcome='applied'",(result['job'],)).fetchone()
                    if not row or not calls.primary_responses:raise ValidationError('Missing accepted proposal')
                    summary=(result['summary'] if processor.PROMPT_VERSION in ('v10','v11')
                             else future_summary.from_response(calls.primary_responses[-1],processor.units(version['transcript']),version['title'],version['transcript']))
                    payload=prepare_source(base,version,json.loads(row['proposal_json']),pipeline=self.pipeline,model=self.model,
                        provenance={'mode':'automatic_future_source','document_id':document['id'],
                                    'job_id':job['id'],'context_revision':job['expected_revision']},
                        usage={'durable_call_count':calls.index})
                    note_json=encode(summary);note_hash=sha(note_json)
                    payload['archive_note']={'document_id':document['id'],'origin':'source_summary','origin_id':job['id'],
                        'note_json':note_json,'note_hash':note_hash,
                        'id':sha(':'.join([document['id'],'source_summary',job['id'],note_hash]))}
                    self.store.call('prepare_job',job_id=job['id'],lease_token=lease,payload=payload)
                finally:base.close();scratch.close()
            return self.store.call('publish_job',job_id=job['id'],lease_token=lease)
        except (BudgetExceeded,OutcomeUnknown,RevisionConflict,ValidationError,JournalUnavailable) as error:
            if isinstance(error,TransientGateway):return pause_transient(self.store,job,lease,error)
            reason='budget_exceeded' if isinstance(error,BudgetExceeded) else 'provider_outcome_unknown' if isinstance(error,OutcomeUnknown) else 'context_changed' if isinstance(error,RevisionConflict) else 'validation_failed'
            result={'state':'paused','reason':reason,'job_id':job['id']}
            if isinstance(error,JournalUnavailable):result['diagnostic']=diagnostic(error)
            try:self.store.call('pause_job',job_id=job['id'],lease_token=lease,reason=reason)
            except JournalUnavailable as pause_error:
                result.update(state='unavailable',reason='pause_unconfirmed',diagnostic=diagnostic(pause_error,'pause_job'))
            return result
