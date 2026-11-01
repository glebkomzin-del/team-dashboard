import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
import archive_index,test_archive_index
from legacy_snapshot import build

class LegacySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        fixture=test_archive_index.ArchiveIndexTests();fixture.root=self.root
        db=archive_index.connect(self.root/'archive.sqlite');archive_index.ingest_archive(db,fixture.archive('input',[('drive:a','2026-07-15','Gleicher Titel','Original A'),('drive:b','2026-07-15','Gleicher Titel','Original B')]));db.close()
        self.snapshot={'captured_at':'2026-09-06T12:00:00Z','tables':{'meetings':[{'id':'same-id','title':'Gleicher Titel','raw_transcript':'Beschädigter alter Text','raw_sha256':hashlib.sha256(b'Besch\xc3\xa4digter alter Text').hexdigest()}],'todos':[{'id':'same-id','meeting_id':'same-id','title':'Vorschlag aus Altbestand','status':'open'}],'blockers':[],'open_items':[],'inbox_items':[{'id':'a','source':'a','status':'pending','payload':{'meeting_id':'same-id','title':'Vorschlag A'}},{'id':'b','source':'b','status':'pending','payload':{'meeting_id':'same-id','title':'Vorschlag B'}}]}}
        self.path=self.root/'snapshot.json'
    def tearDown(self):self.tmp.cleanup()
    def save(self):self.path.write_text(json.dumps(self.snapshot))
    def test_same_title_never_merges_corrupt_sources_and_all_ids_survive(self):
        self.save();report=build(self.path,self.root/'archive.sqlite',self.root/'legacy.sqlite')
        self.assertEqual(report['conflicting_meeting_links'],1)
        db=sqlite3.connect(self.root/'legacy.sqlite')
        self.assertEqual(db.execute("SELECT count(*) FROM legacy_records WHERE legacy_id='same-id'").fetchone()[0],2)
        link=json.loads(db.execute("SELECT link_json FROM legacy_records WHERE entity_table='todos'").fetchone()[0]);self.assertEqual(link['status'],'needs_review');self.assertEqual(link['archive_ids'],[])
        self.assertEqual(db.execute('SELECT count(*) FROM legacy_records').fetchone()[0],4)
        self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='work_events'").fetchone()[0],0);db.close()
    def test_changed_export_rejected_and_existing_target_never_overwritten(self):
        self.snapshot['tables']['meetings'][0]['raw_transcript']='Changed during export';self.save()
        with self.assertRaises(ValueError):build(self.path,self.root/'archive.sqlite',self.root/'legacy.sqlite')
        target=self.root/'legacy.sqlite';target.write_bytes(b'Existing production data')
        with self.assertRaises(ValueError):build(self.path,self.root/'archive.sqlite',target)
        self.assertEqual(target.read_bytes(),b'Existing production data')

if __name__=='__main__':unittest.main()
