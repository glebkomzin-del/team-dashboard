import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from memory import connect,context,overview,fingerprint,ValidationError
from journal_projection import prepare_source,apply_saved,rebuild
from test_memory import TEXT,observation,proposal


class MatterLinkTests(unittest.TestCase):
    def setUp(self):
        self.db=connect(':memory:');self.entries=[]
        for day in ('15','16'):
            source=self.source(day)
            payload=prepare_source(self.db,source,proposal(observation()),pipeline='fixture',model='fixture',provenance={})
            apply_saved(self.db,source,payload)
            self.entries.append({'kind':'source','source_version':source['id'],'source':source,'payload':payload})
        self.ids=[r[0] for r in self.db.execute('SELECT id FROM matters ORDER BY rowid')]
        self.link={'from_id':self.ids[1],'to_id':self.ids[0],'reason':'The speaker explicitly identifies the same report.', 'quotes':[TEXT.splitlines()[0]]}
    def tearDown(self):self.db.close()
    def source(self,day):
        source_id='drive:'+day;h=fingerprint(TEXT)
        return dict(id=fingerprint(source_id+':'+h),source_id=source_id,content_hash=h,event_date='2026-07-'+day,title='Fixture',transcript=TEXT,observed_at='2026-09-06T00:00:00Z')
    def prepared(self,links):
        return prepare_source(self.db,self.source('17'),proposal(),pipeline='fixture',model='codex_direct_review',provenance={},matter_links=links)
    def test_explicit_link_preserves_old_views_and_work_ids_and_rebuild(self):
        before=[dict(r) for r in self.db.execute('SELECT * FROM observations')]
        work={w['id'] for w in overview(self.db)['personal']}
        self.assertEqual(len({r['matter_id'] for r in context(self.db,'2026-07-16')}),2)
        payload=self.prepared([self.link]);apply_saved(self.db,self.source('17'),payload)
        self.assertEqual(before,[dict(r) for r in self.db.execute('SELECT * FROM observations')])
        self.assertEqual(len({r['matter_id'] for r in context(self.db,'2026-07-16')}),2)
        self.assertEqual({r['matter_id'] for r in context(self.db,'2026-07-17')},{self.ids[0]})
        self.assertEqual({w['id'] for w in overview(self.db)['personal']},work)
        self.assertEqual({w['matter_id'] for w in overview(self.db)['personal']},{self.ids[0]})
        self.entries.append({'kind':'source','source_version':self.source('17')['id'],'source':self.source('17'),'payload':payload})
        store=Mock();store.space.return_value={'id':'space','revision':3};store.entries.return_value=self.entries
        with tempfile.TemporaryDirectory() as tmp,patch('processor.anthropic') as api:
            path=Path(tmp)/'rebuilt.sqlite';rebuild(store,path);api.assert_not_called()
            db=connect(path)
            self.assertEqual(context(db,'2026-07-17'),context(self.db,'2026-07-17'));db.close()
    def test_unknown_cycles_missing_proof_and_silent_v1_additions_rejected(self):
        bad=[{**self.link,'from_id':'unknown'},{**self.link,'quotes':['invented']},{**self.link,'reason':''}]
        for link in bad:
            with self.assertRaises(ValidationError):self.prepared([link])
        with self.assertRaises(ValidationError):self.prepared([self.link,{**self.link,'from_id':self.ids[0],'to_id':self.ids[1]}])
        payload=self.prepared([self.link]);payload['format']='wm-source-batch-v1'
        with self.assertRaises(ValidationError):apply_saved(self.db,self.source('17'),payload)
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_versions').fetchone()[0],2)
    def test_linked_target_accepts_canonical_matter_without_merging_work(self):
        payload=self.prepared([self.link]);apply_saved(self.db,self.source('17'),payload)
        wid=self.db.execute('SELECT id FROM observations WHERE matter_id=?',(self.ids[1],)).fetchone()[0]
        update=observation(kind='status',commitment_strength='not_applicable',update='progress',update_target=wid,matter_id=self.ids[0])
        next_source=self.source('18')
        payload=prepare_source(self.db,next_source,proposal(update),pipeline='fixture',model='fixture',provenance={})
        apply_saved(self.db,next_source,payload)
        self.assertEqual(len(overview(self.db)['personal']),2)
        self.assertEqual(len(next(w for w in overview(self.db)['personal'] if w['id']==wid)['history']),2)


if __name__=='__main__':unittest.main()
