import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from memory import connect, register, claim, apply, overview, ValidationError
from projection_snapshot import apply_snapshot, build_snapshot, verify_snapshot
from journal_projection import rebuild, digest
from original_deletion import prepare_redacted_entry
from generation_review import materialize,compile_generation,verify_generation,expand_generation
from test_generation_review import entry as generation_entry


class ProjectionSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        self.transcript = 'Nina: Ich liefere den Export bis Freitag.'
        self.source_id = 'drive:snapshot-private'
        job = register(self.db, source_id=self.source_id, event_date='2026-09-19',
                       title='Private source', transcript=self.transcript)
        token = claim(self.db, job)
        self.proposal = {'observations': [{
            'kind': 'commitment', 'title': 'Export liefern', 'claim': 'Nina liefert den Export.',
            'matter': 'Export', 'owner': 'Nina', 'uncertainty': None,
            'action_uncertainty': None, 'condition_text': None, 'matter_id': None,
            'update_target': None, 'update': 'none', 'required_review': False,
            'quotes': ['Ich liefere den Export bis Freitag.'], 'due_text': 'bis Freitag',
            'work_state': 'open', 'commitment_strength': 'explicit',
        }], 'coverage_notes': []}
        self.items = apply(self.db, job, token, self.proposal, model='fixture')
        row=self.db.execute('select * from source_versions where source_id=?',(self.source_id,)).fetchone()
        self.source={
            'id':row['id'],'source_id':row['source_id'],'content_hash':row['content_hash'],
            'event_date':row['event_date'],'title':row['title'],'transcript':row['transcript'],
            'observed_at':'2026-09-19T10:00:00+00:00',
        }
        self.payload={'format':'wm-source-batch-v1','pipeline':'working-memory-v1','model':'fixture',
                      'proposal':self.proposal,'provenance':{},'usage':{},'result_sha256':digest(self.items)}

    def tearDown(self):
        self.db.close()

    def test_snapshot_restores_exact_state_without_deleted_transcript(self):
        before = overview(self.db)
        payload = build_snapshot(self.db, through_revision=7, deletions=[{
            'deletion_id': str(uuid4()), 'source_id': self.source_id,
        }])
        source = payload['tables']['source_versions'][0]
        self.assertEqual(source['transcript'], '')
        self.assertNotIn(self.transcript, str(payload))
        restored = connect(':memory:')
        try:
            result = apply_snapshot(restored, payload)
            self.assertEqual(result['through_revision'], 7)
            self.assertEqual(overview(restored), before)
            self.assertEqual(restored.execute('select transcript from source_versions').fetchone()[0], '')
        finally:
            restored.close()

    def test_tampering_fails_before_restore(self):
        payload = build_snapshot(self.db, through_revision=7, deletions=[{
            'deletion_id': str(uuid4()), 'source_id': self.source_id,
        }])
        changed = copy.deepcopy(payload)
        changed['tables']['observations'][0]['data_json'] = '{}'
        with self.assertRaisesRegex(ValidationError, 'checksum'):
            verify_snapshot(changed)

    def test_unredacted_sources_keep_their_transcript(self):
        second = register(self.db, source_id='drive:retained', event_date='2026-09-20',
                          title='Retained source', transcript='A harmless retained source.')
        # It need not be applied to prove the checkpoint keeps an unrelated
        # original available for later generation review.
        self.assertIsNotNone(second)
        payload = build_snapshot(self.db, through_revision=7, deletions=[{
            'deletion_id': str(uuid4()), 'source_id': self.source_id,
        }])
        retained = next(row for row in payload['tables']['source_versions'] if row['source_id'] == 'drive:retained')
        self.assertEqual(retained['transcript'], 'A harmless retained source.')

    def test_journal_rebuild_starts_at_latest_privacy_checkpoint(self):
        payload = build_snapshot(self.db, through_revision=1, deletions=[{
            'deletion_id': str(uuid4()), 'source_id': self.source_id,
        }])
        store = Mock()
        store.space.return_value = {'id': 'space', 'revision': 2}
        store.entries.return_value = [
            {'revision': 1, 'kind': 'source', 'source_version': '0' * 64,
             'payload': {'redacted': True}},
            {'revision': 2, 'kind': 'redaction', 'payload': payload},
        ]
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'projection.sqlite'
            result = rebuild(store, target)
            restored = connect(target)
            try:
                self.assertEqual(result['revision'], 2)
                self.assertEqual(overview(restored), overview(self.db))
                self.assertEqual(restored.execute('select transcript from source_versions').fetchone()[0], '')
                store.source.assert_not_called()
            finally:
                restored.close()

    def test_checkpoint_contains_compiler_basis_for_later_generations(self):
        deletion_id=str(uuid4())
        package=prepare_redacted_entry({'kind':'source','source':self.source,'payload':self.payload},
            deletion_id=deletion_id,prepared_at='2026-09-19T12:00:00+00:00')
        payload=build_snapshot(self.db,through_revision=1,
            deletions=[{'deletion_id':deletion_id,'source_id':self.source_id}],
            logical_basis=[{'kind':'source','source':self.source,'payload':self.payload}],
            redaction_packages=[package])
        self.assertEqual(payload['logical_basis'][0]['kind'],'redacted_source')
        self.assertNotIn(self.transcript,str(payload['logical_basis']))
        replayed,_=materialize(payload['logical_basis'])
        try:self.assertEqual(overview(replayed),overview(self.db))
        finally:replayed.close()

        later_db=connect(':memory:')
        try:later=generation_entry(later_db,'drive:after-deletion',day='2026-09-20')
        finally:later_db.close()
        generation=compile_generation(payload['logical_basis'],[*payload['logical_basis'],later],
            source_reviews={'drive:after-deletion':'Neues Original nach der Löschung geprüft'},
            identity_links=[],reason='Neue Quelle nach Privacy-Checkpoint übernehmen')
        self.assertTrue(verify_generation(payload['logical_basis'],generation))
        after,_=materialize(expand_generation(payload['logical_basis'],generation))
        try:self.assertEqual(after.execute('select count(*) from observations').fetchone()[0],2)
        finally:after.close()


if __name__ == '__main__':
    unittest.main()
