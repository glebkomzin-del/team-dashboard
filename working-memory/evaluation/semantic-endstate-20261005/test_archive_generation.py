"""A pinned journal revision chooses one active summary without rewriting archive history."""
import json
import tempfile
import unittest
from pathlib import Path

from archive_index import connect, digest
from canonical_archive import rebuild_archive, summaries
from hybrid_index import documents
from journal_service import JournalService
from test_canonical_archive import fixture
from memory import connect as memory_connect


class ArchiveGenerationTest(unittest.TestCase):
    def test_generation_summary_is_pinned_and_old_note_remains_immutable(self):
        store,document,old=fixture()
        old['origin']='source_summary';old['origin_id']='original-job'
        old['id']=digest(':'.join([old['document_id'],old['origin'],old['origin_id'],old['note_hash']]))
        corrected=dict(old)
        corrected['note_json']=json.dumps({'ai_summary':'Korrigierter Endstand mit einmaligem Upload.'},ensure_ascii=False)
        corrected['note_hash']=digest(corrected['note_json'])
        corrected['id']=digest(':'.join([corrected['document_id'],corrected['origin'],corrected['origin_id'],corrected['note_hash']]))
        source={'id':digest(document['source_id']+':'+document['body_hash']),
                'source_id':document['source_id'],'event_date':document['event_date'],
                'content_hash':document['body_hash'],'title':document['title'],
                'transcript':document['body'],'observed_at':document['observed_at']}
        def entry(note):return {'kind':'source','source':source,'payload':{'archive_note':note}}
        store.space.return_value={'id':store.space.return_value['id'],'owner_id':'owner','revision':2,'archive_revision':2}
        store.entries.side_effect=lambda **kw:[entry(old if kw['through']==1 else corrected)]
        with tempfile.TemporaryDirectory() as folder:
            service=JournalService(store,folder)
            (Path(folder)/'archive').mkdir()
            identity={'role':'owner','id':'owner'}
            with service.archive_projection(identity) as (archive,_):
                self.assertEqual(summaries(archive,document['id'])[0]['ai_summary'],'Korrigierter Endstand mit einmaligem Upload.')
                self.assertEqual(archive.execute('SELECT note_json FROM archived_notes').fetchone()[0],old['note_json'])
                memory=memory_connect(Path(folder)/'memory.sqlite')
                try:
                    rows=documents(memory,{'meeting_date':'2026-10-05','observed_at':'2026-10-05T12:00:00Z'},
                                   archive.execute('PRAGMA database_list').fetchone()[2])
                finally:memory.close()
                indexed=[r['text'] for r in rows if r['kind']=='summary']
                self.assertEqual(indexed,['Korrigierter Endstand mit einmaligem Upload.'])
            older=service._open_projection({**store.space.return_value,'revision':1},archive=True)
            try:self.assertEqual(summaries(older,document['id'])[0]['ai_summary'],json.loads(old['note_json'])['ai_summary'])
            finally:older.close()
            self.assertTrue((Path(folder)/'archive'/f"{store.space.return_value['id']}-2-2.sqlite").exists())
            self.assertTrue((Path(folder)/'archive'/f"{store.space.return_value['id']}-2-1.sqlite").exists())


if __name__=='__main__':unittest.main()
