from http.server import ThreadingHTTPServer
import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from journal_service import JournalService
from test_canonical_archive import fixture
import server

class CanonicalArchiveHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store,self.document,self.note=fixture()
        self.owner={'id':'00000000-0000-4000-8000-000000000001','role':'owner'}
        self.store.space.return_value.update(owner_id=self.owner['id'],revision=0,state='draft')
        self.store.call.return_value={'config':None,'pending_count':0,'jobs':[],'accounted_micro_usd':0}
        self.service=JournalService(self.store,Path(self.tmp.name)/'cache')
        self.settings=patch.multiple(server,JOURNAL=self.service,DB='/missing-legacy-database',ARCHIVE_DB='/missing-legacy-archive',READ_ONLY=True)
        self.settings.start();self.auth=patch.object(server,'authenticate',return_value=self.owner);self.auth.start()
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join(timeout=2)
        self.auth.stop();self.settings.stop();self.tmp.cleanup()
    def request(self,path):
        try:
            with urlopen(Request(f'http://127.0.0.1:{self.http.server_port}'+path),timeout=3) as result:return result.status,json.load(result)
        except HTTPError as error:
            with error:return error.code,json.load(error)
    def test_canonical_archive_and_summary_work_without_any_legacy_database(self):
        self.assertEqual(self.request('/health')[0],200)
        status,catalogue=self.request('/archive?as_of=2026-09-06&known_at=2026-09-06T21:00:00Z&q=Zusammenfassung')
        self.assertEqual(status,200);self.assertEqual(catalogue['total'],1);self.assertEqual(catalogue['storage'],'supabase')
        status,source=self.request('/archive/'+self.document['id'])
        self.assertEqual(status,200);self.assertEqual(source['transcript'],self.document['body'])
        self.assertEqual(source['summaries'][0]['ai_summary'],'Vorhandene Zusammenfassung, ohne Neuberechnung.')
        self.assertEqual(self.request('/operations')[1]['archive_revision'],2)
    def test_moved_original_exposes_existing_summary_in_catalogue_and_dialog(self):
        from archive_index import digest
        moved=dict(self.document)
        meta=json.loads(moved['metadata_json']);meta['drive_metadata']={'parents':['processed'],'version':'2'}
        moved.update(metadata_json=json.dumps(meta,ensure_ascii=False,sort_keys=True),observed_at='2026-09-06T21:00:00Z',registered_revision=3)
        moved['id']=digest(moved['source_id']+':'+moved['metadata_json'])
        self.store.space.return_value['archive_revision']=3
        self.store.archive_rows.side_effect=lambda kind,**kwargs:iter([self.document,moved] if kind=='documents' else [self.note])
        status,result=self.request('/archive?as_of=2026-09-06&known_at=2026-09-06T22:00:00Z')
        self.assertEqual(status,200);self.assertEqual(result['total'],1)
        self.assertEqual(result['sources'][0]['id'],moved['id'])
        self.assertTrue(result['sources'][0]['summary_available'])
        status,original=self.request('/archive/'+moved['id'])
        self.assertEqual(status,200)
        self.assertEqual(original['summaries'][0]['id'],self.note['id'])
        self.assertEqual(original['transcript'],self.document['body'])

    def test_ambiguous_teams_title_is_replaced_in_list_and_dialog_without_mutating_source(self):
        from archive_index import digest
        body='''Meeting Titel: Gieselberg, Jan Philipp\nTeilnehmer: Gleb Komzin; Jan Philipp Gieselberg\nDatum: 02.06.2026\n[10:00:00] Jan Philipp Gieselberg: Hallo.\n'''
        metadata={'source_id':self.document['source_id'],'event_date':'2026-06-02',
                  'title':'Gieselberg, Jan Philipp','body_sha256':digest(body),
                  'export_sha256':digest(body),'body_offset_characters':0}
        encoded=json.dumps(metadata,ensure_ascii=False,sort_keys=True)
        self.document.update(id=digest(self.document['source_id']+':'+encoded),title=metadata['title'],
            body=body,export=body,body_hash=digest(body),export_hash=digest(body),metadata_json=encoded)
        self.store.space.return_value['archive_revision']=1
        self.store.archive_rows.side_effect=lambda kind,**kwargs:iter([self.document] if kind=='documents' else [])
        status,catalogue=self.request('/archive')
        self.assertEqual(status,200)
        self.assertEqual(catalogue['sources'][0]['title'],'Gieselberg, Jan Philipp')
        self.assertEqual(catalogue['sources'][0]['summary_title'],
                         'Thema offen · Gespräch mit Jan Philipp Gieselberg · 02.06.2026')
        status,original=self.request('/archive/'+self.document['id'])
        self.assertEqual(status,200)
        self.assertEqual(original['title'],'Gieselberg, Jan Philipp')
        self.assertEqual(original['summary_title'],catalogue['sources'][0]['summary_title'])

    def test_owner_boundary_and_snapshot_cache_cannot_expose_another_account(self):
        self.assertEqual(self.request('/archive')[0],200)
        with patch.object(server,'authenticate',return_value={'id':'other','role':'owner'}):
            self.assertEqual(self.request('/archive')[0],403)
            self.assertEqual(self.request('/archive/'+self.document['id'])[0],403)
        with patch.object(server,'authenticate',return_value=None):self.assertEqual(self.request('/archive')[0],401)

    def test_unknown_canonical_route_does_not_create_legacy_database(self):
        self.assertEqual(self.request('/jobs/legacy-id')[0],404)

    def test_drive_manifest_and_intake_have_a_service_only_boundary(self):
        from test_drive_intake import DriveIntakeTests
        original=DriveIntakeTests().original()
        def post():
            request=Request(f'http://127.0.0.1:{self.http.server_port}/drive-sources',data=json.dumps({'original':original}).encode(),headers={'Content-Type':'application/json'})
            try:
                with urlopen(request,timeout=3) as result:return result.status,json.load(result)
            except HTTPError as error:
                with error:return error.code,json.load(error)
        with patch.multiple(server,READ_ONLY=False,INTAKE_ENABLED=True):
            self.assertEqual(self.request('/drive-manifest')[0],403)
            self.assertEqual(post()[0],403)
            with patch.object(server,'authenticate',return_value={'role':'service'}):
                self.store.call.return_value=[]
                self.assertEqual(self.request('/drive-manifest'),(200,{'documents':[]}))
                with patch.object(server,'persist_original',return_value={'state':'archive_only'}) as intake:
                    self.assertEqual(post()[0],200);intake.assert_called_once()
                with patch.object(server,'INTAKE_ENABLED',False):self.assertEqual(post()[0],405)

    def test_canonical_intake_requires_service_and_only_archives_old_original(self):
        def post(document):
            request=Request(f'http://127.0.0.1:{self.http.server_port}/sources',data=json.dumps({'document':document}).encode(),headers={'Content-Type':'application/json'})
            try:
                with urlopen(request,timeout=3) as result:return result.status,json.load(result)
            except HTTPError as error:
                with error:return error.code,json.load(error)
        with patch.multiple(server,READ_ONLY=False,INTAKE_ENABLED=True),patch.object(server,'connect',side_effect=AssertionError('Legacy DB must not be used')):
            self.assertEqual(post(self.document)[0],403)
            with patch.object(server,'authenticate',return_value={'role':'service'}):
                self.store.archive_put.return_value={'id':self.document['id'],'repeated':True}
                self.store.call.return_value={'state':'archive_only','reason':'historical_source_requires_direct_review'}
                status,result=post(self.document)
                self.assertEqual(status,200);self.assertEqual(result['state'],'archive_only')
                self.store.call.assert_called_with('enqueue',document_id=self.document['id'],pipeline=server.canonical_pipeline(server.MODEL))
                for invalid in (None,[],{'body':'missing proof'}):self.assertEqual(post(invalid)[0],400)
                with patch.object(server,'INTAKE_ENABLED',False):self.assertEqual(post(self.document)[0],405)


class FastReviewTests(CanonicalArchiveHTTPTests):
    def setUp(self):
        super().setUp()
        self.store.entries.return_value=[]

    def test_review_does_not_open_archive_even_when_archive_is_unavailable(self):
        with patch.object(self.service,'archive_projection',side_effect=AssertionError('Review must not open archive')):
            status,result=self.request('/review')
        self.assertEqual(status,200)
        self.assertEqual(result['revision'],0)
        self.assertTrue(result['archive_available'])
        self.assertNotIn('archive_total',result)
        self.store.archive_rows.assert_not_called()

    def test_review_remains_available_while_archive_build_is_locked(self):
        with self.service.archive_lock:
            self.assertEqual(self.request('/review')[0],200)

    def test_warm_projection_is_reused_without_replaying_journal(self):
        self.service.warm_projection()
        self.store.entries.reset_mock()
        self.assertEqual(self.request('/review')[0],200)
        self.assertEqual(self.request('/review')[0],200)
        self.store.entries.assert_not_called()

    def test_ready_revision_remains_readable_while_another_revision_builds(self):
        self.service.warm_projection()
        with self.service.projection_lock:
            self.assertEqual(self.request('/review')[0],200)
        self.store.entries.assert_called_once()

    def test_warm_cache_still_requires_owner_authorization(self):
        self.service.warm_projection()
        with patch.object(server,'authenticate',return_value={'id':'other','role':'owner'}):
            self.assertEqual(self.request('/review')[0],403)

if __name__=='__main__':unittest.main()
