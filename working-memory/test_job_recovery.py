import copy,json,tempfile,unittest
from unittest.mock import patch
from contextlib import contextmanager
from pathlib import Path
from memory import connect,ValidationError,fingerprint,overview
from journal_projection import prepare_source,apply_saved
from journal_service import JournalService
from journal_store import RevisionConflict
from test_canonical_worker import CanonicalStore
from test_memory import proposal,observation,TEXT
from job_recovery import inspect,decide

OWNER={'id':'55555555-5555-4555-8555-555555555555','role':'owner'}
COMMAND='11111111-1111-4111-8111-111111111111'
class RecoveryStore(CanonicalStore):
    def __init__(self):
        super().__init__();self.receipt=None;self.resolved=[]
        self.job.update(space_id=self.space_id,pipeline='fixture',state='review',reason='transport_failed',updated_at='2026-09-07T12:00:00Z',lease_until=None,prepared_payload=None)
        self.calls=[]
    def space(self):return {**super().space(),'owner_id':OWNER['id']}
    def call(self,op,**v):
        if op=='job_detail':return {'job':copy.deepcopy(self.job),'title':self.document['title'],'calls':self.calls,'decisions':[]}
        if op=='job_decision':return self.receipt
        if op=='processing_status':return {'config':{'pipeline':'fixture','enabled':True,'automatic_from':'2026-09-07'}}
        if op=='resolve_job':
            self.resolved.append(v);return {'state':'queued','revision':self.revision}
        return super().call(op,**v)

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=RecoveryStore();self.service=JournalService(self.store,self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def request(self,action='retry'):
        return dict(job_id=self.store.job['id'],command_id=COMMAND,expected_revision=0,expected_updated_at=self.store.job['updated_at'],action=action,reason='Original and saved result checked',preview_hash=None)
    def saved(self):
        d=self.store.document;s=dict(id=self.store.job['id'],source_id=d['source_id'],content_hash=d['body_hash'],event_date=d['event_date'],title=d['title'],transcript=d['body'],observed_at=d['observed_at'])
        db=connect(':memory:')
        o=observation(kind='fact',commitment_strength='not_applicable',owner=None,due_text=None,quotes=[d['body']],claim='Two stores',title='Stores')
        self.store.job['prepared_payload']=prepare_source(db,s,proposal(o),pipeline='fixture',model='fixture',provenance={})
        db.close()
    def test_owner_only_and_unknown_paid_outcome_never_retries(self):
        for identity in ({**OWNER,'role':'service'},{**OWNER,'id':'other'}):
            with self.assertRaises(PermissionError):inspect(self.service,identity,self.store.job['id'],COMMAND)
        self.store.calls=[{'received':False,'index':0}]
        detail,_=inspect(self.service,OWNER,self.store.job['id'],COMMAND)
        self.assertFalse(detail['can_retry']);self.assertTrue(detail['can_archive'])
        with self.assertRaises(ValidationError):decide(self.service,OWNER,self.request())
        self.assertFalse(self.store.resolved)
    def test_clean_transport_retry_preserves_command_and_stale_view_rejected(self):
        r=self.request();r['expected_revision']=1
        with self.assertRaises(RevisionConflict):decide(self.service,OWNER,r)
        decide(self.service,OWNER,self.request())
        self.assertEqual(self.store.resolved[0]['command_id'],COMMAND)
        self.assertIsNone(self.store.resolved[0]['payload'])
    def test_rebase_uses_saved_output_without_model_and_requires_exact_preview(self):
        self.saved();self.store.job['expected_revision']=-1;self.store.job['reason']='context_changed'
        with patch('processor.anthropic') as api:
            detail,payload=inspect(self.service,OWNER,self.store.job['id'],COMMAND)
            self.assertTrue(detail['can_rebase']);self.assertFalse(detail['can_retry'])
            r={**self.request('rebase_prepared'),'preview_hash':detail['preview_hash']}
            decide(self.service,OWNER,r);api.assert_not_called()
        saved=self.store.resolved[0]['payload']
        self.assertEqual(saved,payload);self.assertEqual(saved['provenance']['owner_id'],OWNER['id'])
        r['preview_hash']='0'*64
        with self.assertRaises(RevisionConflict):decide(self.service,OWNER,r)
    def test_retry_after_lost_ack_uses_receipt_even_if_job_changed(self):
        r=self.request();self.store.receipt={'actor_id':OWNER['id'],'request':{**r,'payload':None},'result':{'state':'queued','revision':0}}
        self.store.job['state']='applied';self.store.revision=1
        self.assertTrue(decide(self.service,OWNER,r)['repeated']);self.assertFalse(self.store.resolved)
        with self.assertRaises(RevisionConflict):decide(self.service,OWNER,{**r,'reason':'different'})
    def test_rebase_allows_update_unrelated_to_intervening_personal_correction(self):
        from human_decisions import record
        db=connect(':memory:');h=fingerprint(TEXT)
        source=dict(id=fingerprint('synthetic:prior:'+h),source_id='synthetic:prior',content_hash=h,event_date='2026-09-06',title='Earlier promise',transcript=TEXT,observed_at='2026-09-06T00:00:00Z')
        payload=prepare_source(db,source,proposal(observation()),pipeline='fixture',model='fixture',provenance={});apply_saved(db,source,payload)
        wid=overview(db)['personal'][0]['id']
        record(db,command_id='22222222-2222-4222-8222-222222222222',actor_id=OWNER['id'],command={'action':'correct','target_id':wid,'reason':'Personal correction','patch':{'title':'My actual agreement'},'event_date':'2026-09-07'})
        self.saved();saved=self.store.job['prepared_payload']
        saved['proposal']=proposal(observation(kind='status',commitment_strength='not_applicable',update='progress',update_target=wid,quotes=[self.store.document['body']],claim='Report now contains two stores',owner=None,due_text=None))
        self.store.job['expected_revision']=0;self.store.revision=1
        @contextmanager
        def projection(identity):yield db,self.store.space()
        with patch.object(self.service,'projection',projection),patch('processor.anthropic') as api:
            detail,_=inspect(self.service,OWNER,self.store.job['id'],COMMAND)
            self.assertTrue(detail['can_rebase']);self.assertFalse(detail['prepared_observations'][0]['required_review'])
            self.assertEqual(overview(db)['personal'][0]['title'],'My actual agreement');api.assert_not_called()
        db.close()
    def test_historical_and_changed_originals_cannot_be_reprocessed(self):
        self.store.job['event_date']='2026-06-01'
        detail,_=inspect(self.service,OWNER,self.store.job['id'],COMMAND)
        self.assertFalse(detail['can_retry']);self.assertFalse(detail['can_rebase'])
        self.store.job['event_date']='2026-09-07'
        with self.service.archive_projection(OWNER) as (db,_):path=Path(db.execute('pragma database_list').fetchone()[2])
        import sqlite3
        # A second distinct version cannot be skipped by using an older document.
        db=sqlite3.connect(path);columns=[r[1] for r in db.execute('pragma table_info(documents)')];row=list(db.execute('select * from documents').fetchone())
        row[columns.index('id')]='different';row[columns.index('body_hash')]='different'
        db.execute('insert into documents values ('+','.join('?' for _ in row)+')',row);db.commit();db.close()
        detail,_=inspect(self.service,OWNER,self.store.job['id'],COMMAND)
        self.assertFalse(detail['can_retry']);self.assertEqual(detail['blocked'],'source_generation_review')

if __name__=='__main__':unittest.main()
