"""Private review boundary exercised over real loopback HTTP, with synthetic data."""
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from memory import connect, register, claim, apply
from test_memory import observation, proposal
import test_archive_index
from archive_index import connect as archive_connect, ingest_archive
import server

class ReviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'review.sqlite'
        db = connect(self.path)
        text = 'Gleb: Ich sende den Bericht morgen.'
        job = register(db, source_id='fixture:source', event_date='2026-07-15', title='Fixture', transcript=text)
        apply(db, job, claim(db, job), proposal(observation(quotes=[text])), model='fixture')
        db.close()
        self.before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.token = 'synthetic-test-token-not-a-real-secret'
        self.archive_path = Path(self.tmp.name) / 'archive.sqlite'
        fixture = test_archive_index.ArchiveIndexTests(); fixture.root = Path(self.tmp.name)
        archive = archive_connect(self.archive_path)
        ingest_archive(archive, fixture.archive('snapshot', [('drive:fixture', '2026-07-15', 'Fixture', text)]))
        archive.close()
        self.settings = patch.multiple(server, DB=str(self.path), TOKEN=self.token, READ_ONLY=True, ARCHIVE_DB=str(self.archive_path))
        self.settings.start()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(timeout=2)
        self.settings.stop()
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), self.before)
        self.tmp.cleanup()
    def request(self, path, *, method='GET', auth=True):
        request = Request(f'http://127.0.0.1:{self.http.server_port}{path}', method=method,
                          headers={'Authorization': 'Bearer '+self.token} if auth else {})
        try:
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                return response.status, json.load(response)
        except HTTPError as error:
            with error: return error.code, json.load(error)
    def test_readiness_checks_the_actual_databases(self):
        self.assertEqual(self.request('/health', auth=False)[0], 200)
        with patch.object(server, 'ARCHIVE_DB', str(Path(self.tmp.name)/'missing.sqlite')):
            self.assertEqual(self.request('/health', auth=False)[0], 503)

    def test_private_review_and_original_hash(self):
        self.assertEqual(self.request('/review', auth=False)[0], 401)
        status, state = self.request('/review?as_of=2026-07-15')
        self.assertEqual(status, 200); self.assertEqual(len(state['personal']), 1)
        status, source = self.request('/sources/'+state['sources'][0]['id'])
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(source['transcript'].encode()).hexdigest(), source['content_hash'])
        self.assertEqual(self.request('/sources/'+source['id'], auth=False)[0], 401)
    def test_archive_requires_auth_and_returns_exact_full_original(self):
        self.assertEqual(self.request('/archive', auth=False)[0], 401)
        status, result = self.request('/archive?q=Bericht&as_of=2026-07-15')
        self.assertEqual(status, 200); self.assertEqual(result['total'], 1)
        source = result['sources'][0]
        status, original = self.request('/archive/' + source['id'])
        self.assertEqual(status, 200)
        self.assertEqual(original['transcript'][source['match']['start']:source['match']['end']], source['match']['text'])
        self.assertEqual(self.request('/archive/' + source['id'], auth=False)[0], 401)
        self.assertEqual(self.request('/archive?limit=101')[0], 400)
        self.assertEqual(self.request('/archive?as_of=2026-07-14')[1]['total'], 0)

    def test_owner_can_read_but_cannot_submit_sources(self):
        with patch.object(server, 'authenticate', return_value={'role': 'owner', 'id': 'fixture-user'}):
            self.assertEqual(self.request('/archive')[0], 200)
            with patch.object(server, 'READ_ONLY', False):
                self.assertEqual(self.request('/sources', method='POST')[0], 403)

    def test_invalid_date_unknown_source_and_mutation_cannot_change_db(self):
        self.assertEqual(self.request('/review?as_of=2026-02-30')[0], 400)
        self.assertEqual(self.request('/sources/unknown')[0], 404)
        self.assertEqual(self.request('/sources', method='POST')[0], 405)
        self.assertEqual(self.request('/review?as_of=2026-07-14')[1]['personal'], [])

if __name__ == '__main__': unittest.main()
