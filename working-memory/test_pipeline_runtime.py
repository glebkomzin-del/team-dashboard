import copy,unittest
from unittest.mock import patch

from journal_store import JournalUnavailable
from gateway_journal import TransientGateway
from pipeline_runtime import diagnostic,pause_transient,recover_transport_pause


class Store:
    def __init__(self):
        self.space_value={'id':'space','revision':139}
        self.job={'id':'a'*64,'space_id':'space','state':'review','reason':'transport_failed',
            'pipeline':'pipeline-v1','event_date':'2026-09-20','expected_revision':139,
            'prepared_payload':None,'lease_token':'stale','lease_until':'2026-09-20T00:17:00Z',
            'updated_at':'2026-09-20T00:07:00Z'}
        self.calls=[];self.recovered=[]
        self.failures=[{'failure_id':'11111111-1111-4111-8111-111111111111','recovered_at':None,
                        'next_retry_at':'2026-09-20T00:17:00Z'}]
    def space(self):return copy.deepcopy(self.space_value)
    def call(self,op,**fields):
        if op=='job_detail':return {'job':copy.deepcopy(self.job),'calls':copy.deepcopy(self.calls),
                                    'transport_failures':copy.deepcopy(self.failures)}
        if op=='processing_status':return {'config':{'pipeline':'pipeline-v1','enabled':True,'automatic_from':'2026-09-01'}}
        if op=='recover_transport_job':self.recovered.append(fields);return {'state':'queued','recovered':True,'job_id':fields['job_id']}
        raise AssertionError(op)


class PipelineRuntimeTests(unittest.TestCase):
    claim={'state':'paused','reason':'transport_failed','job_id':'a'*64}
    def test_exact_pre_model_transport_failure_is_requeued(self):
        store=Store();result=recover_transport_pause(store,self.claim,'pipeline-v1')
        self.assertEqual(result['state'],'queued');self.assertTrue(result['recovered'])
        self.assertEqual(store.recovered,[{'job_id':'a'*64,'pipeline':'pipeline-v1',
            'failure_id':'11111111-1111-4111-8111-111111111111','expected_revision':139,
            'expected_updated_at':'2026-09-20T00:07:00Z'}])
    def test_unknown_call_prepared_or_changed_context_stays_in_review(self):
        changes=({'calls':[{'index':0,'received':False}]},{'prepared_payload':{'proposal':{}}},
                 {'expected_revision':138},{'reason':'validation_failed'})
        for change in changes:
            store=Store()
            if 'calls' in change:store.calls=change['calls']
            else:store.job.update(change)
            result=recover_transport_pause(store,self.claim,'pipeline-v1')
            self.assertEqual(result['recovery'],'manual_review_required');self.assertFalse(store.recovered)
        store=Store();store.failures=[]
        self.assertEqual(recover_transport_pause(store,self.claim,'pipeline-v1')['recovery'],'manual_review_required')
    def test_unavailable_recovery_is_redacted_and_not_retried_here(self):
        store=Store()
        def unavailable(op,**fields):
            if op=='recover_transport_job':raise JournalUnavailable('private database detail')
            return Store.call(store,op,**fields)
        store.call=unavailable
        result=recover_transport_pause(store,self.claim,'pipeline-v1')
        self.assertEqual(result['recovery'],'unconfirmed');self.assertNotIn('private',str(result))
        self.assertEqual(result['diagnostic']['op'],'recover_transport_job')
    def test_transient_pause_persists_only_redacted_diagnostic(self):
        store=Store()
        def call(op,**fields):
            if op=='pause_transport_job':
                self.assertEqual(set(fields['diagnostic']),{'at','op','type','http_status','sqlstate','attempts'})
                self.assertEqual(fields['diagnostic']['op'],'archive_document')
                return {'failure_id':fields['failure_id'],'next_retry_at':'2026-09-20T00:20:00Z'}
            return Store.call(store,op,**fields)
        store.call=call
        error=TransientGateway('archive_document','http',http_status=503,sqlstate='57014');error.diagnostic['attempts']=3
        result=pause_transient(store,store.job,'22222222-2222-4222-8222-222222222222',error)
        self.assertEqual(result['reason'],'transport_failed');self.assertEqual(result['diagnostic']['sqlstate'],'57014')
    def test_diagnostic_exposes_only_fixed_metadata(self):
        with patch('pipeline_runtime.datetime') as now:
            now.now.return_value.isoformat.return_value='2026-09-20T12:00:00+00:00'
            value=diagnostic(ValueError('private transcript'),'archive_document')
        self.assertEqual(value,{'at':'2026-09-20T12:00:00Z','op':'archive_document','type':'ValueError',
                                'http_status':None,'sqlstate':None})


if __name__=='__main__':unittest.main()
