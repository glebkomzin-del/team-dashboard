import json
import tempfile
import unittest
from pathlib import Path

from archive_index import digest
from canonical_backup import export
from canonical_restore import prepared_rows, TABLES
from deletion_ledger import write as write_ledger
from memory import ValidationError
from test_canonical_restore import CompleteStore, OWNER, STAMP


class ConversationBackupTests(unittest.TestCase):
    def fixture(self, *, include_conversation=True, owner=OWNER, duplicate_sequence=False):
        store = CompleteStore()
        conversation = {'space_id': store.space_id, 'id': '60000000-0000-4000-8000-000000000001',
                        'owner_id': owner, 'title': 'Neues Gespräch', 'created_at': STAMP, 'updated_at': STAMP}
        request = json.dumps({'question': 'Was davon betrifft nächste Woche?'})
        response = json.dumps({'answer': 'Gesicherter Testbeleg'})
        question = {'space_id': store.space_id, 'id': '70000000-0000-4000-8000-000000000001',
                    'actor_id': OWNER, 'revision': 0, 'archive_revision': 2,
                    'conversation_id': conversation['id'], 'conversation_seq': 1,
                    'request_json': request, 'request_hash': digest(request),
                    'response_json': response, 'response_hash': digest(response)}
        values = [('question', question)]
        if include_conversation:
            values.append(('conversation', conversation))
        if duplicate_sequence:
            values.append(('question', {**question, 'id': '70000000-0000-4000-8000-000000000002'}))
        for kind, value in values:
            raw = json.dumps(value, ensure_ascii=False)
            store.records.append({'sequence': len(store.records) + 1, 'kind': kind,
                                  'record_json': raw, 'record_hash': digest(raw)})
        return store, conversation, question

    def test_messages_and_conversation_are_restored_in_dependency_order(self):
        store, conversation, question = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'snapshot'
            result = export(store, folder)
            ledger = Path(tmp) / 'ledger.json'
            write_ledger(ledger, space_id=store.space_id, minimum_deletion_revision=0,
                         deletions=[], observed_at=STAMP)
            rows, _ = prepared_rows(folder, ledger)
        self.assertEqual(result['queue_records']['conversation'], 1)
        self.assertEqual(rows['wm_conversations'], [conversation])
        self.assertEqual(rows['wm_questions'], [question])
        self.assertLess(TABLES.index('wm_conversations'), TABLES.index('wm_questions'))

    def test_missing_conversation_wrong_owner_and_duplicate_sequence_are_rejected(self):
        for kwargs in ({'include_conversation': False},
                       {'owner': '80000000-0000-4000-8000-000000000001'},
                       {'duplicate_sequence': True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                store, _, _ = self.fixture(**kwargs)
                with self.assertRaises(ValidationError):
                    export(store, Path(tmp) / 'snapshot')

    def test_pipeline_recovery_audit_survives_restore_and_requires_job(self):
        for missing_job in (False, True):
            with self.subTest(missing_job=missing_job), tempfile.TemporaryDirectory() as tmp:
                store, _, _ = self.fixture()
                job = next(json.loads(r['record_json']) for r in store.records if r['kind'] == 'job')
                recovery = {'space_id': store.space_id, 'job_id': 'missing' if missing_job else job['id'],
                            'failure_id': '90000000-0000-4000-8000-000000000001',
                            'recovery_ordinal': 2, 'operation': 'archive_document', 'error_type': 'network',
                            'occurred_at': STAMP, 'recorded_at': STAMP, 'next_retry_at': STAMP}
                raw = json.dumps(recovery)
                store.records.append({'sequence': len(store.records) + 1, 'kind': 'pipeline_recovery',
                                      'record_json': raw, 'record_hash': digest(raw)})
                folder = Path(tmp) / 'snapshot'
                if missing_job:
                    with self.assertRaises(ValidationError): export(store, folder)
                    continue
                export(store, folder)
                ledger = Path(tmp) / 'ledger.json'
                write_ledger(ledger, space_id=store.space_id, minimum_deletion_revision=0,
                             deletions=[], observed_at=STAMP)
                rows, _ = prepared_rows(folder, ledger)
                self.assertEqual(rows['wm_pipeline_recoveries'], [recovery])
                self.assertLess(TABLES.index('wm_jobs'), TABLES.index('wm_pipeline_recoveries'))


if __name__ == '__main__':
    unittest.main()
