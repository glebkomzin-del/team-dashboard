import json
import unittest
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen
from urllib.error import HTTPError
from drive_completion import completion
from drive_intake import FOLDERS
from memory import fingerprint, ValidationError


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.document_id = 'a'*64
        self.source = 'drive:file'
        self.body_hash = 'b'*64
        self.job = {'id': fingerprint(self.source+':'+self.body_hash), 'source_id': self.source,
                    'state': 'applied', 'applied_revision': 12}
        self.document = {'source_id': self.source, 'body_hash': self.body_hash,
                         'metadata_json': json.dumps({'drive_metadata': {'id': 'file', 'version': '7',
                          'md5_checksum': 'c'*32, 'parents': list(FOLDERS)}})}
        self.manifest = [{'document_id': self.document_id, 'source_id': self.source}]
        self.store = Mock()
        self.store.call.side_effect = lambda action, **_: {'drive_manifest': self.manifest,
            'archive_document': self.document, 'job_detail': {'job': self.job}}[action]

    def receipt(self):
        with patch('drive_completion.verify_document', side_effect=lambda value: value):
            return completion(self.store, self.document_id)

    def test_only_durable_publication_produces_a_receipt(self):
        self.assertTrue(self.receipt()['ready_to_move'])
        for state in ('queued', 'running', 'prepared', 'failed', 'review', 'archive_only'):
            self.job['state'] = state
            self.assertFalse(self.receipt()['ready_to_move'])
        self.job.update(state='applied', applied_revision=None)
        self.assertFalse(self.receipt()['ready_to_move'])

    def test_superseded_source_cannot_move(self):
        self.manifest[0]['document_id'] = 'd'*64
        self.assertFalse(self.receipt()['ready_to_move'])
        self.assertEqual(self.store.call.call_count, 1)

    def test_wrong_job_identity_and_missing_manifest_fail_closed(self):
        self.job['id'] = 'foreign'
        with self.assertRaises(ValidationError):
            self.receipt()
        self.manifest = None
        with self.assertRaises(ValidationError):
            self.receipt()

    def test_bad_document_id_never_queries_storage(self):
        with self.assertRaises(ValidationError):
            completion(self.store, '../../other-space')
        self.store.call.assert_not_called()


class CompletionHTTPTests(unittest.TestCase):
    def test_service_only_and_unavailable_is_never_a_success_receipt(self):
        import server
        from journal_store import JournalUnavailable
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = Thread(target=http.serve_forever, daemon=True); thread.start()
        url = f'http://127.0.0.1:{http.server_port}/drive-completion/'+('a'*64)
        def get():
            try:
                with urlopen(url, timeout=3) as r:return r.status, json.load(r)
            except HTTPError as e:
                with e:return e.code, json.load(e)
        try:
            with patch.object(server, 'JOURNAL', Mock()), patch.object(server, 'authenticate', return_value={'role':'owner'}):
                self.assertEqual(get()[0], 403)
            with patch.object(server, 'JOURNAL', Mock()), patch.object(server, 'authenticate', return_value={'role':'service'}):
                with patch('drive_completion.completion', return_value={'ready_to_move':False}):
                    self.assertEqual(get(), (200, {'ready_to_move':False}))
                with patch('drive_completion.completion', side_effect=JournalUnavailable('offline')):
                    self.assertEqual(get()[0], 503)
        finally:
            http.shutdown();http.server_close();thread.join()


if __name__ == '__main__':
    unittest.main()
