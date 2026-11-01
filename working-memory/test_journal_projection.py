import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from memory import connect,overview,fingerprint,ValidationError
from journal_projection import prepare_source,apply_saved,rebuild
from human_decisions import record
from test_memory import TEXT,proposal,observation

class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=connect(':memory:')
        h=fingerprint(TEXT)
        self.source={'id':fingerprint('drive:fixture:'+h),'source_id':'drive:fixture','content_hash':h,
            'transcript':TEXT,'title':'Fixture','event_date':'2026-07-15','observed_at':'2026-09-06T00:00:00Z'}
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def payload(self):return prepare_source(self.db,self.source,proposal(observation()),pipeline='manual-v1',model='codex_direct_review',provenance={'review_sha256':'fixture'})
    def test_prepare_does_not_mutate_live_projection_and_rebuild_has_no_api(self):
        payload=self.payload()
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],0)
        store=Mock();store.space.return_value={'id':'space','revision':2}
        store.source.return_value=self.source
        apply_saved(self.db,self.source,payload);wid=overview(self.db)['personal'][0]['id']
        store.entries.return_value=[{'kind':'source','source_version':self.source['id'],'payload':payload},
            {'kind':'human','command_id':'20000000-0000-4000-8000-000000000001','actor_id':'00000000-0000-4000-8000-000000000001',
             'payload':{'action':'set_status','target_id':wid,'reason':'User confirmation','patch':{'status':'done'},'event_date':'2026-09-06'}}]
        target=Path(self.tmp.name)/'cache.sqlite'
        with patch('processor.anthropic') as api:
            rebuild(store,target);api.assert_not_called()
        restored=connect(target)
        self.assertEqual(len(overview(restored)['completed']),1)
        self.assertEqual(restored.execute('SELECT revision FROM projection_cursor').fetchone()[0],2)
        restored.close()
    def test_changed_saved_result_fails_without_replacing_existing_cache(self):
        payload=self.payload();payload['result_sha256']='0'*64
        store=Mock();store.space.return_value={'id':'space','revision':1};store.source.return_value=self.source
        store.entries.return_value=[{'kind':'source','source_version':self.source['id'],'payload':payload}]
        target=Path(self.tmp.name)/'cache.sqlite';target.write_bytes(b'previous cache')
        with self.assertRaises(ValidationError):rebuild(store,target)
        self.assertEqual(target.read_bytes(),b'previous cache')
    def test_changed_original_rejected(self):
        source={**self.source,'transcript':'changed'}
        with self.assertRaises(ValidationError):prepare_source(self.db,source,proposal(observation()),pipeline='manual',model='manual',provenance={})
    def test_legacy_guard_replays_a_previously_accepted_result_hash(self):
        first=self.payload();apply_saved(self.db,self.source,first);wid=overview(self.db)['personal'][0]['id']
        record(self.db,command_id='22222222-2222-4222-8222-222222222222',actor_id='00000000-0000-4000-8000-000000000001',
            command={'action':'correct','target_id':wid,'reason':'Personal correction',
                     'patch':{'title':'My actual agreement'},'event_date':'2026-07-16'})
        source={**self.source,'id':fingerprint('drive:legacy-followup:'+self.source['content_hash']),
                'source_id':'drive:legacy-followup','title':'drive:legacy-followup',
                'event_date':'2026-07-17','observed_at':'2026-07-17T12:00:00+00:00'}
        update=observation(kind='status',commitment_strength='not_applicable',update='progress',update_target=wid,
                           claim='Report now contains two stores',owner=None,due_text=None)
        # Frozen from the accepted pre-field-guard behavior. Do not derive a
        # fresh baseline here; that could hide a semantic replay drift.
        expected='c2cd5e92373b41d0ae3b1a7eca8d45c1dd7b5d04a92422f26f99caf2128d5276'
        payload={'format':'wm-source-batch-v1','pipeline':'fixture','model':'fixture','proposal':proposal(update),
                 'provenance':{},'usage':{},'result_sha256':expected}
        self.assertEqual(apply_saved(self.db,source,payload),expected)
        row=self.db.execute('SELECT data_json FROM observations WHERE source_version=?',(source['id'],)).fetchone()
        self.assertTrue(__import__('json').loads(row[0])['required_review'])

if __name__=='__main__':unittest.main()
