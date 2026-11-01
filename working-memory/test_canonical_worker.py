import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import processor
from canonical_worker import CanonicalWorker
from durable_calls import encode,sha
from journal_projection import rebuild
from journal_service import JournalService
from journal_store import JournalUnavailable
from gateway_journal import TransientGateway
from memory import connect
from test_durable_calls import Store

class CanonicalStore(Store):
    space_id='88888888-8888-4888-8888-888888888888'
    def __init__(self,event_date='2026-09-07'):
        super().__init__();self.revision=0;self.entry=None;self.prepared=None;self.applied=False
        body='00:00 Alice: Der Bericht enthält zwei Filialen.';body_hash=sha(body)
        meta=encode({'source_id':'synthetic:future','event_date':event_date,'title':'Synthetic new meeting',
                    'body_sha256':body_hash,'export_sha256':body_hash,'body_offset_characters':0})
        self.document={'space_id':self.space_id,'id':sha('synthetic:future:'+meta),'source_id':'synthetic:future',
            'event_date':event_date,'observed_at':'2026-09-07T12:00:00Z','title':'Synthetic new meeting',
            'body_hash':body_hash,'export_hash':body_hash,'body':body,'export':body,'metadata_json':meta,'registered_revision':1}
        self.job={'id':sha('synthetic:future:'+body_hash),'document_id':self.document['id'],
                  'source_id':'synthetic:future','expected_revision':0,'event_date':event_date}
    def space(self):return {'id':self.space_id,'owner_id':'synthetic-owner','state':'draft','revision':self.revision,'archive_revision':1}
    def entries(self,**kw):return [self.entry] if self.entry and kw.get('through',self.revision)>0 else []
    def archive_rows(self,kind,**kw):return iter([self.document] if kind=='documents' else [])
    def call(self,op,**v):
        if op in ('reserve_call','receive_call'):return super().call(op,**v)
        if op=='claim_job':
            if self.applied:return {'state':'idle'}
            self.job.update(pipeline=v['pipeline'],lease_token=v['lease_token'],state='running')
            return copy.deepcopy(self.job)
        if op=='archive_document':return copy.deepcopy(self.document)
        if op=='job_detail':return {'job':copy.deepcopy(self.job),'calls':[],'decisions':[]}
        if op=='processing_status':return {'config':{'enabled':True,'automatic_from':'2026-09-07'}}
        if op=='prepare_job':self.prepared=copy.deepcopy(v['payload']);return {'saved':True}
        if op=='publish_job':
            d=self.document
            source={'id':self.job['id'],'source_id':d['source_id'],'event_date':d['event_date'],
                    'content_hash':d['body_hash'],'title':d['title'],'transcript':d['body'],'observed_at':d['observed_at']}
            self.entry={'revision':1,'kind':'source','source_version':self.job['id'],'source':source,'payload':self.prepared}
            self.revision=1;self.applied=True;return {'state':'applied','revision':1}
        if op=='pause_job':return {'paused':True}
        raise AssertionError(op)

class CanonicalWorkerTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=processor.PROMPT_VERSION;processor.PROMPT_VERSION='v9'
        self.oldroot=processor.ROOT
        # Processor's diagnostic outputs are temporary and contain only fiction.
        self.sent=0
    def tearDown(self):processor.PROMPT_VERSION=self.old;self.tmp.cleanup()
    def api(self,prompt,model,**kw):
        self.sent+=1
        self.assertIn('meeting_summary',kw['schema']['properties'])
        self.assertIn('meeting_display_title',kw['schema']['properties'])
        self.assertIn('Lesefassung',prompt)
        proposal={'coverage_notes':[],'meeting_summary':[{'text':'Der Bericht enthält zwei Filialen.','evidence_ids':['U0001']}],
            'meeting_display_title':{'text':'Bericht mit zwei Filialen','evidence_ids':['U0001']},
            'observations':[{'matter':'Bericht','matter_id':None,'kind':'fact','title':'Berichtsumfang',
             'claim':'Der Bericht enthält zwei Filialen.','owner':None,'commitment_strength':'not_applicable',
             'due_text':None,'update_target':None,'update':'none','uncertainty':None,'required_review':False,
             'evidence_ids':['U0001'],'action_uncertainty':None,'condition_text':None,'work_state':'not_applicable','state_evidence_ids':[]}]}
        return {'content':[{'type':'text','text':json.dumps(proposal)}],'stop_reason':'end_turn',
                'usage_final':True,'usage':{'input_tokens':100,'output_tokens':100},'elapsed_seconds':.01}
    def test_future_meeting_through_real_rules_and_journal_restore(self):
        store=CanonicalStore();service=JournalService(store,self.tmp.name)
        worker=CanonicalWorker(service,'claude-opus-5',api=self.api)
        result=worker.step();self.assertEqual(result,{'state':'applied','revision':1})
        self.assertEqual(self.sent,1)
        self.assertEqual(store.prepared['archive_note']['origin'],'source_summary')
        self.assertIn('zwei Filialen',store.prepared['archive_note']['note_json'])
        self.assertIn('same_call_source_cited_title',store.prepared['archive_note']['note_json'])
        destination=Path(self.tmp.name)/'restored.sqlite';rebuild(store,destination)
        db=connect(destination)
        try:self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0],1)
        finally:db.close()
        self.assertEqual(worker.step(),{'state':'idle'});self.assertEqual(self.sent,1)
    def test_v11_normal_worker_enables_bounded_extraction_recovery(self):
        processor.PROMPT_VERSION='v11';store=CanonicalStore()
        with patch.object(processor,'process',side_effect=processor.ValidationError('stop after contract check')) as process:
            result=CanonicalWorker(JournalService(store,self.tmp.name),'claude-opus-5',api=self.api).step()
        self.assertEqual(result['reason'],'validation_failed')
        self.assertTrue(process.call_args.kwargs['extraction_recovery'])
        self.assertEqual(self.sent,0)
    def test_even_forged_historical_claim_cannot_reach_provider(self):
        store=CanonicalStore('2026-06-01');worker=CanonicalWorker(JournalService(store,self.tmp.name),'claude-opus-5',api=self.api)
        self.assertEqual(worker.step()['reason'],'validation_failed');self.assertEqual(self.sent,0)
    def test_preclaim_storage_failure_returns_redacted_diagnostic(self):
        store=CanonicalStore();original=store.call
        def call(op,**fields):
            if op=='claim_job':raise JournalUnavailable('private endpoint detail')
            return original(op,**fields)
        store.call=call
        result=CanonicalWorker(JournalService(store,self.tmp.name),'claude-opus-5',api=self.api).step()
        self.assertEqual(result['state'],'unavailable');self.assertEqual(result['diagnostic']['op'],'worker')
        self.assertNotIn('private',str(result));self.assertEqual(self.sent,0)
    def test_integrity_failure_is_not_automatic_transport_recovery(self):
        store=CanonicalStore();original=store.call;paused=[]
        def call(op,**fields):
            if op=='archive_document':raise JournalUnavailable('journal revisions inconsistent')
            if op=='pause_job':paused.append(fields);return {'paused':True}
            return original(op,**fields)
        store.call=call
        result=CanonicalWorker(JournalService(store,self.tmp.name),'claude-opus-5',api=self.api).step()
        self.assertEqual(result['reason'],'validation_failed');self.assertEqual(paused[0]['reason'],'validation_failed')
        self.assertEqual(self.sent,0)
    def test_transient_failure_uses_durable_transport_pause(self):
        store=CanonicalStore();original=store.call;recorded=[]
        def call(op,**fields):
            if op=='archive_document':
                error=TransientGateway(op,'network');error.diagnostic['attempts']=3;raise error
            if op=='pause_transport_job':recorded.append(fields);return {'failure_id':fields['failure_id'],'next_retry_at':'2026-09-20T14:00:00Z'}
            return original(op,**fields)
        store.call=call
        result=CanonicalWorker(JournalService(store,self.tmp.name),'claude-opus-5',api=self.api).step()
        self.assertEqual(result['reason'],'transport_failed');self.assertEqual(recorded[0]['diagnostic']['op'],'archive_document')
        self.assertEqual(self.sent,0)

if __name__=='__main__':unittest.main()
