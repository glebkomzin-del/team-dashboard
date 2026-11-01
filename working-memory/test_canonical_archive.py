import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from archive_index import catalogue,connect,digest,original
from canonical_archive import meeting_display_title,rebuild_archive,verify_document,verify_note,summaries
from memory import ValidationError

SPACE='10000000-0000-4000-8000-000000000001'
def fixture():
    body='00:01 Gleb: Die Zusammenfassung bleibt unverändert. ÄÖÜ 👋\n'
    export='Meeting\n'+body
    meta=dict(source_id='drive:fixture',event_date='2026-06-02',title='Archivprüfung',body_sha256=digest(body),export_sha256=digest(export),body_offset_characters=8)
    metadata=json.dumps(meta,ensure_ascii=False,sort_keys=True)
    doc=dict(id=digest(meta['source_id']+':'+metadata),source_id=meta['source_id'],event_date=meta['event_date'],title=meta['title'],observed_at='2026-09-06T20:00:00Z',body=body,export=export,body_hash=digest(body),export_hash=digest(export),metadata_json=metadata,space_id=SPACE,registered_revision=1)
    content=json.dumps({'ai_summary':'Vorhandene Zusammenfassung, ohne Neuberechnung.'},ensure_ascii=False)
    note=dict(document_id=doc['id'],origin='legacy_meetings',origin_id='fixture',note_json=content,note_hash=digest(content),space_id=SPACE,registered_revision=2)
    note['id']=digest(':'.join([note['document_id'],note['origin'],note['origin_id'],note['note_hash']]))
    store=Mock();store.space.return_value={'id':SPACE,'archive_revision':2}
    store.archive_rows.side_effect=lambda kind,**kwargs:iter([doc] if kind=='documents' else [note])
    return store,doc,note

class ArchiveTests(unittest.TestCase):
    def test_restored_search_keeps_exact_original_export_and_existing_summary(self):
        store,doc,note=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'archive.sqlite';result=rebuild_archive(store,target)
            self.assertEqual((result['documents'],result['notes'],result['model_api_calls']),(1,1,0))
            db=connect(target,readonly=True)
            try:
                data=original(db,doc['id']);self.assertEqual(data['transcript'],doc['body']);self.assertEqual(data['full_export'],doc['export'])
                self.assertEqual(db.execute('select note_json from archived_notes').fetchone()[0],note['note_json'])
                hits=catalogue(db,query='Zusammenfassung',as_of='2026-09-06',known_at='2026-09-06T21:00:00Z')
                self.assertEqual(hits['total'],1);self.assertIn(hits['sources'][0]['match']['text'],doc['body'])
            finally:db.close()
    def test_metadata_only_version_keeps_summary_without_copying_notes(self):
        store,doc,note=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'archive.sqlite';rebuild_archive(store,target)
            db=connect(target)
            columns=tuple(doc[k] for k in ('id','source_id','event_date','observed_at','title','body_hash','export_hash','body','export','metadata_json'))
            def add(identifier, **changes):
                fields=['id','source_id','event_date','observed_at','title','body_hash','export_hash','body','export','metadata_json']
                values=dict(zip(fields,columns));values.update(id=identifier,observed_at='2026-09-07T20:00:00Z',**changes)
                db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',tuple(values[k] for k in fields))
            add('metadata-only')
            self.assertEqual(summaries(db,'metadata-only')[0]['ai_summary'],json.loads(note['note_json'])['ai_summary'])
            self.assertEqual(db.execute('SELECT count(*) FROM archived_notes').fetchone()[0],1)
            add('changed-content',body='Changed transcript',body_hash=digest('Changed transcript'))
            add('other-source',source_id='drive:another')
            add('different-date',event_date='2026-06-03')
            for identifier in ('changed-content','other-source','different-date','missing'):
                self.assertEqual(summaries(db,identifier),[])
            # A summary attached to the later envelope must not leak backwards.
            db.execute("UPDATE archived_notes SET document_id='metadata-only'")
            self.assertEqual(summaries(db,doc['id']),[])
            self.assertEqual(len(summaries(db,'metadata-only')),1)
            db.close()

    def test_display_title_is_separate_from_immutable_source_title(self):
        store,doc,note=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'archive.sqlite';rebuild_archive(store,target)
            db=connect(target)
            body='''Meeting Titel: Gieselberg, Jan Philipp\nTeilnehmer: Gleb Komzin; Jan Philipp Gieselberg\nDatum: 02.06.2026\n[10:00:00] Jan Philipp Gieselberg: Wir prüfen das Power BI Modell und RLS.\n'''
            db.execute('UPDATE documents SET title=?,body=?,body_hash=? WHERE id=?',
                       ('Gieselberg, Jan Philipp',body,digest(body),doc['id']))
            stored={'title':'Gieselberg, Jan Philipp','display_title':{
                'text':'Power-BI-Modell und RLS prüfen','passages':['Wir prüfen das Power BI Modell und RLS.'],
                'method':'same_call_source_cited_title'},'ai_summary':'Belegte Notiz.'}
            db.execute('UPDATE archived_notes SET note_json=?',(json.dumps(stored,ensure_ascii=False),))
            display=meeting_display_title(db,doc['id'])
            self.assertEqual(display['text'],'Power-BI-Modell und RLS prüfen')
            summary=summaries(db,doc['id'])[0]
            self.assertEqual(summary['title'],display['text'])
            self.assertEqual(summary['source_title'],'Gieselberg, Jan Philipp')
            self.assertEqual(db.execute('SELECT title FROM documents WHERE id=?',(doc['id'],)).fetchone()[0],
                             'Gieselberg, Jan Philipp')
            db.close()

    def test_title_only_backfill_names_original_without_creating_empty_summary(self):
        from meeting_title_backfill import note_for
        store,doc,_=fixture()
        body='''Meeting Titel: Gieselberg, Jan Philipp\nTeilnehmer: Gleb Komzin; Jan Philipp Gieselberg\nDatum: 02.06.2026\n[10:00:00] Jan Philipp Gieselberg: Wir prüfen das Power BI Modell und RLS.\n'''
        metadata={'source_id':doc['source_id'],'event_date':doc['event_date'],'title':'Gieselberg, Jan Philipp',
                  'body_sha256':digest(body),'export_sha256':digest(body),'body_offset_characters':0}
        encoded=json.dumps(metadata,ensure_ascii=False,sort_keys=True)
        doc.update(id=digest(doc['source_id']+':'+encoded),title=metadata['title'],body=body,body_hash=digest(body),
                   export=body,export_hash=digest(body),metadata_json=encoded)
        note=note_for(doc,{'text':'Power-BI-Modell und RLS prüfen','evidence_ids':['U0004']})
        note.update(space_id=SPACE,registered_revision=2)
        store.space.return_value['archive_revision']=2
        store.archive_rows.side_effect=lambda kind,**kwargs:iter([doc] if kind=='documents' else [note])
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'archive.sqlite';rebuild_archive(store,target)
            db=connect(target)
            try:
                self.assertEqual(summaries(db,doc['id']),[])
                self.assertEqual(meeting_display_title(db,doc['id'])['text'],'Power-BI-Modell und RLS prüfen')
            finally:db.close()

    def test_missing_or_wrong_space_revision_cannot_replace_previous_cache(self):
        for mode in ('missing','wrong_space','duplicate_revision'):
            store,doc,note=fixture()
            if mode=='missing':store.archive_rows.side_effect=lambda kind,**kwargs:iter([doc] if kind=='documents' else [])
            elif mode=='wrong_space':note['space_id']='another-space'
            else:note['registered_revision']=1
            with tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/'archive.sqlite';target.write_bytes(b'existing verified snapshot')
                with self.assertRaises(ValidationError):rebuild_archive(store,target)
                self.assertEqual(target.read_bytes(),b'existing verified snapshot')
                self.assertEqual([p.name for p in Path(tmp).iterdir()],['archive.sqlite'])
    def test_tampered_original_metadata_and_summary_are_rejected(self):
        _,doc,note=fixture()
        active_document=verify_document(doc);active_note=verify_note(note)
        self.assertEqual(set(active_document),set(('id','source_id','event_date','observed_at','title','body_hash','export_hash','body','export','metadata_json')))
        self.assertEqual(set(active_note),set(('id','document_id','origin','origin_id','note_json','note_hash')))
        for field in ('body','export','title','metadata_json'):
            with self.assertRaises((ValidationError,ValueError)):verify_document({**doc,field:'changed'})
        with self.assertRaises(ValidationError):verify_document({**doc,'observed_at':'2026-09-06T20:00:00'})
        with self.assertRaises(ValidationError):verify_note({**note,'note_json':'{}'})

    def test_redacted_original_keeps_sanitized_derived_summary(self):
        store,doc,note=fixture();deletion='30000000-0000-4000-8000-000000000001'
        doc.update(body=None,export=None,redaction_id=deletion)
        summary=json.dumps({'ai_summary':'Abgeleitete Zusammenfassung bleibt erhalten.'},ensure_ascii=False)
        note.update(note_json=summary,sanitized_note_hash=digest(summary),redaction_id=deletion)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'archive.sqlite';rebuild_archive(store,target)
            db=connect(target,readonly=True)
            try:
                self.assertEqual(db.execute('select note_json from deleted_notes').fetchone()[0],summary)
                self.assertTrue(original(db,doc['id'])['deleted'])
                self.assertEqual(db.execute('select count(*) from passages').fetchone()[0],0)
                self.assertEqual(summaries(db,doc['id'])[0]['ai_summary'],'Abgeleitete Zusammenfassung bleibt erhalten.')
            finally:db.close()
        with self.assertRaises(ValidationError):verify_note({**note,'note_json':None,'sanitized_note_hash':digest(summary),'redaction_id':deletion})

if __name__=='__main__':unittest.main()
