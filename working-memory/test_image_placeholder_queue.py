import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

import processor
from canonical_worker import CanonicalWorker, verified_image_placeholder
from durable_calls import sha
from journal_service import JournalService
from test_canonical_worker import CanonicalStore


HEADER = 'Meeting Titel: Beispiel\nTeilnehmer: \nDatum: 2026-09-23\nBeginn: 2026-09-23 10:35:55\n'
IMAGE = HEADER + '[10:35:55] Unknown: image\n'


class PlaceholderStore(CanonicalStore):
    def __init__(self, body=IMAGE):
        super().__init__('2026-09-23')
        self.document['body'] = self.document['export'] = body
        self.document['body_hash'] = self.document['export_hash'] = sha(body)
        import json
        metadata = json.loads(self.document['metadata_json'])
        metadata['body_sha256'] = metadata['export_sha256'] = sha(body)
        self.document['metadata_json'] = json.dumps(metadata, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        self.document['id'] = sha(self.document['source_id'] + ':' + self.document['metadata_json'])
        self.job['id'] = sha(self.document['source_id'] + ':' + sha(body))
        self.job['document_id'] = self.document['id']
        self.archived = []

    def call(self, op, **fields):
        if op == 'archive_image_placeholder_job':
            self.archived.append(fields)
            return {'state': 'archived', 'reason': 'verified_image_placeholder', 'job_id': fields['job_id']}
        return super().call(op, **fields)


class ImagePlaceholderTests(unittest.TestCase):
    def test_exact_known_export_and_counterexamples(self):
        self.assertTrue(verified_image_placeholder(IMAGE))
        self.assertTrue(verified_image_placeholder(IMAGE.replace('image', 'Bild')))
        for body in (
            HEADER + '[10:35:55] Alex: Ja.\n',
            HEADER + '[10:35:55] Unknown: image\n[10:35:56] Alex: Ja.\n',
            HEADER + '[10:35:55] Unknown: Bild\n[10:35:56] Unknown: Moin\n',
            HEADER + '[10:35:55] Unknown: Mo Di Mi Do Fr Sa So\n',
            HEADER + '[10:35:55] Unknown: output.png\n',
            HEADER + '[10:35:55] Unknown: \n',
            '[10:35:55] Unknown: image\n',
            '', None,
        ):
            with self.subTest(body=repr(body)[:50]):
                self.assertFalse(verified_image_placeholder(body))

    def test_worker_closes_only_verified_unpaid_claim_before_provider(self):
        with TemporaryDirectory() as directory:
            store = PlaceholderStore()
            calls = []
            with patch.object(processor, 'PROMPT_VERSION', 'v9'):
                worker = CanonicalWorker(JournalService(store, directory), 'claude-opus-5',
                                         api=lambda *args, **kwargs: calls.append(args))
                result = worker.step()
        self.assertEqual(result['state'], 'archived')
        self.assertEqual(calls, [])
        self.assertEqual(store.prepared, None)
        self.assertEqual(len(store.archived), 1)
        self.assertEqual(store.archived[0]['body_hash'], store.document['body_hash'])
        self.assertEqual(store.archived[0]['job_id'], store.job['id'])


if __name__ == '__main__':
    unittest.main()
