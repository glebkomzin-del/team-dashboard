import io
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import snapshot
from index import DataIndex, iso_date

def fixture_source(private_suffix=False):
    memory, _, _, _, _ = snapshot.projection_modules()
    from journal_projection import prepare_source
    quote = 'Person Alpha liefert das synthetische Paket am 2020-01-02.'
    transcript = quote + (' Synthetic private original.' if private_suffix else '')
    h = memory.fingerprint(transcript)
    source = {'source_id': 'synthetic-source', 'content_hash': h,
        'id': memory.fingerprint('synthetic-source:' + h), 'event_date': '2020-01-01',
        'title': 'Synthetic meeting', 'transcript': transcript, 'observed_at': '2020-01-01T12:00:00Z'}
    observation = {'kind': 'commitment', 'title': 'Synthetic package', 'claim': 'Deliver synthetic package',
        'matter': 'Synthetic topic', 'owner': 'Person Alpha', 'quotes': [quote], 'due_text': '2020-01-02',
        'uncertainty': None, 'action_uncertainty': None, 'required_review': False, 'update': 'none',
        'update_target': None, 'commitment_strength': 'explicit', 'work_state': 'open'}
    db = memory.connect(':memory:')
    try:
        payload = prepare_source(db, source, {'observations': [observation], 'coverage_notes': []},
                                 pipeline='synthetic-v1', model='synthetic', provenance={})
    finally: db.close()
    return {'revision': 1, 'kind': 'source', 'source_version': source['id'], 'source': source,
            'payload': payload, 'command_id': 'synthetic-command'}

def mini_archive(path, journal, documents=None, notes=None, wrapped=False):
    with tarfile.open(path, 'w:gz') as archive:
        for kind, rows in (('journal', journal), ('documents', documents or []), ('notes', notes or [])):
            if wrapped: rows = [{'kind': kind, 'sequence': i + 1, 'record_json': json.dumps(r)} for i, r in enumerate(rows)]
            data = ''.join(json.dumps(r) + '\n' for r in rows).encode()
            member = tarfile.TarInfo('canonical/' + kind + '.jsonl'); member.size = len(data)
            archive.addfile(member, io.BytesIO(data))

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.synthetic-', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / 'mini.tar.gz'
    def test_mini_archive_source_notes_and_manual_history(self):
        entry = fixture_source(); source = entry['source']
        document = {'id': 'synthetic-doc', 'source_id': source['source_id'], 'title': source['title'],
            'event_date': source['event_date'], 'body_hash': source['content_hash'], 'observed_at': source['observed_at'],
            'registered_revision': 1, 'body': source['transcript']}
        note = {'id': 'synthetic-note', 'document_id': 'synthetic-doc', 'origin': 'source_summary',
            'registered_revision': 1, 'note_json': json.dumps({'executive_summary': 'Synthetic summary'})}
        human = {'revision': 2, 'kind': 'human', 'command_id': '00000000-0000-4000-8000-000000000001',
            'actor_id': '00000000-0000-4000-8000-000000000002', 'payload': {'action': 'create_task',
            'target_id': '00000000-0000-4000-8000-000000000003', 'event_date': '2020-01-03', 'reason': 'Synthetic plan',
            'patch': {'title': 'Synthetic manual task', 'owner': 'Person Beta', 'due_date': '2020-01-04'}}}
        mini_archive(self.archive, [entry, human], [document], [note])
        backend = snapshot.SnapshotBackend(self.archive); result = backend.tasks_list(status='open')
        self.assertEqual(result['count'], 2)
        task = next(t for t in result['tasks'] if t['owner'] == 'Person Alpha')
        detail = backend.task_get(task['id'])['task']
        self.assertEqual(detail['source']['meeting_title'], 'Synthetic meeting')
        self.assertEqual(detail['source']['date'], '2020-01-01')
        self.assertEqual(detail['history'][0]['action'], 'created')
        self.assertEqual(detail['reife'], 'belegt')
        manual = next(t for t in result['tasks'] if t.get('origin') == 'manual')
        self.assertEqual(len(backend.task_get(manual['id'])['task']['history']), 1)
        self.assertEqual(backend.meetings_recent(1)['meetings'][0]['summary'], 'Synthetic summary')
        self.assertEqual(backend.memory_ask('Welche Aufgaben sind überfällig?')['count'], 2)
        self.assertEqual(len(list(Path(self.temp.name).iterdir())), 1)
    def test_wrapped_records(self):
        mini_archive(self.archive, [fixture_source()], wrapped=True)
        self.assertEqual(snapshot.build_index(self.archive).tasks_list()['count'], 1)
    def test_missing_revision(self):
        entry = fixture_source(); entry['revision'] = 2
        mini_archive(self.archive, [entry])
        with self.assertRaisesRegex(ValueError, 'Incomplete'): snapshot.build_index(self.archive)
    def test_missing_member(self):
        with tarfile.open(self.archive, 'w:gz') as archive:
            archive.addfile(tarfile.TarInfo('canonical/journal.jsonl'), io.BytesIO())
        with self.assertRaises(ValueError): list(snapshot.stream_rows(self.archive))
    def test_corrupt_stream(self):
        self.archive.write_bytes(b'invalid synthetic gzip')
        with self.assertRaises(ValueError): list(snapshot.stream_rows(self.archive))
    def test_cache_private_roundtrip(self):
        mini_archive(self.archive, [fixture_source()]); index = snapshot.build_index(self.archive)
        cache = Path(self.temp.name) / 'cache.json'; snapshot.cache_write(cache, index)
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
        self.assertEqual(snapshot.cache_read(cache).tasks_list(), index.tasks_list())
        cache.chmod(0o644)
        with self.assertRaises(ValueError): snapshot.cache_read(cache)
    def test_cache_symlink_refused(self):
        target = Path(self.temp.name) / 'target'; target.write_text('{}')
        link = Path(self.temp.name) / 'link'; link.symlink_to(target)
        with self.assertRaises(OSError): snapshot.cache_read(link)
    def test_latest_encoded_backup_time(self):
        folder = Path(self.temp.name) / 'Library/Application Support/Dashboard Job Backup/archives'
        folder.mkdir(parents=True)
        for stamp in ('20200102T000000Z', '20200101T000000Z'): (folder / ('dashboard-' + stamp + '.tar.gz')).write_bytes(b'')
        with patch.object(snapshot.Path, 'home', return_value=Path(self.temp.name)):
            self.assertEqual(snapshot.latest_archive().name, 'dashboard-20200102T000000Z.tar.gz')

    def test_deleted_original_replays_from_verified_checkpoint(self):
        entry = fixture_source(private_suffix=True)
        memory, generation, _, snapshots, _ = snapshot.projection_modules()
        from original_deletion import prepare_redacted_entry
        logical = snapshot._logical_source(entry)
        db, prepared = generation.materialize([logical])
        deletion_id = '00000000-0000-4000-8000-000000000004'
        try:
            package = prepare_redacted_entry(logical, deletion_id=deletion_id, prepared_at='2020-01-02T00:00:00Z')
            payload = snapshots.build_snapshot(db, through_revision=1,
                deletions=[{'deletion_id': deletion_id, 'source_id': entry['source']['source_id']}],
                logical_basis=prepared, redaction_packages=[package])
        finally: db.close()
        tombstone = {'revision': 1, 'kind': 'source', 'source_version': entry['source']['id'], 'payload': {'redacted': True}}
        redaction = {'revision': 2, 'kind': 'redaction', 'payload': payload}
        mini_archive(self.archive, [tombstone, redaction])
        index = snapshot.build_index(self.archive)
        self.assertEqual(index.tasks_list()['count'], 1)
        self.assertEqual(index.tasks_list(due_before='2020-01-03')['count'], 1)
        self.assertEqual(index.metadata['revision'], 2)
        self.assertNotIn('Synthetic private original.', json.dumps(index.tasks_list()))
        changed = deepcopy(redaction); changed['payload']['tables']['source_versions'][0]['transcript'] = 'bad'
        mini_archive(self.archive, [tombstone, changed])
        with self.assertRaisesRegex(ValueError, 'checksum'): snapshot.build_index(self.archive)

    def test_generation_preserves_task_and_replaces_active_note(self):
        entry = fixture_source()
        _, generation, _, _, _ = snapshot.projection_modules()
        logical = snapshot._logical_source(entry)
        changed = deepcopy(logical)
        changed['payload']['archive_note'] = {'id': 'active-note', 'document_id': 'synthetic-doc',
            'origin': 'source_summary', 'note_json': json.dumps({'executive_summary': 'Synthetic current summary'})}
        payload = generation.compile_generation([logical], [changed],
            source_reviews={'synthetic-source': 'Synthetic source review'}, identity_links=[], reason='Synthetic generation')
        document = {'id': 'synthetic-doc', 'source_id': entry['source']['source_id'],
            'event_date': '2020-01-01', 'title': 'Synthetic meeting', 'body_hash': entry['source']['content_hash'],
            'observed_at': '2020-01-01T12:00:00Z', 'registered_revision': 1}
        historical = {'id': 'older-note', 'document_id': 'synthetic-doc', 'origin': 'source_summary',
            'registered_revision': 1, 'note_json': json.dumps({'executive_summary': 'Synthetic stale summary'})}
        mini_archive(self.archive, [entry, {'revision': 2, 'kind': 'generation', 'payload': payload}], [document], [historical])
        index = snapshot.build_index(self.archive)
        self.assertEqual(index.tasks_list()['count'], 1)
        self.assertEqual(index.meetings_recent()['meetings'][0]['note_id'], 'active-note')
        self.assertEqual(index.memory_ask('current')['results'][0]['kind'], 'meeting')

    def test_sanitized_note_requires_positive_checksum(self):
        raw = json.dumps({'executive_summary': 'Synthetic retained summary'})
        note = {'id': 'sanitized', 'document_id': 'synthetic-doc', 'redaction_id': 'synthetic-deletion', 'note_json': raw}
        for expected in (None, '0' * 64):
            with self.assertRaisesRegex(ValueError, 'checksum'): snapshot._note({**note, 'sanitized_note_hash': expected})
        self.assertEqual(snapshot._note({**note, 'sanitized_note_hash': hashlib.sha256(raw.encode()).hexdigest()})['summary'], 'Synthetic retained summary')
        self.assertIsNone(snapshot._note({**note, 'note_json': None}))

    def test_cache_budget_identity_and_single_file(self):
        index = DataIndex([], [], {'mode': 'synthetic'})
        cache = Path(self.temp.name) / 'index.json'
        legacy = Path(self.temp.name) / (('a' * 64) + '.json'); legacy.write_text('{}')
        snapshot.cache_write(cache, index, 'first')
        self.assertFalse(legacy.exists())
        with self.assertRaisesRegex(ValueError, 'Stale'): snapshot.cache_read(cache, 'second')
        snapshot.cache_write(cache, index, 'second')
        self.assertEqual(snapshot.cache_read(cache, 'second').tasks_list()['count'], 0)
        self.assertEqual(len(list(Path(self.temp.name).glob('*.json'))), 1)
        self.assertLess(sum(p.stat().st_size for p in Path(self.temp.name).iterdir()), snapshot.CACHE_TOTAL_LIMIT)
        before = cache.read_bytes()
        with patch.object(snapshot, 'CACHE_FILE_LIMIT', 1):
            with self.assertRaisesRegex(ValueError, 'size limit'): snapshot.cache_write(cache, index)
        with patch.object(snapshot, 'CACHE_TOTAL_LIMIT', cache.stat().st_size + 1):
            with self.assertRaisesRegex(ValueError, 'directory'): snapshot.cache_write(cache, index)
        self.assertEqual(cache.read_bytes(), before)
        self.assertFalse(list(Path(self.temp.name).glob('.index-*')))

    def test_cache_denial_falls_back_to_memory(self):
        mini_archive(self.archive, [fixture_source()])
        with patch.dict(snapshot.os.environ, {'DASHBOARD_MEMORY_CACHE': '1'}), patch.object(snapshot, 'cache_folder', side_effect=PermissionError):
            backend = snapshot.SnapshotBackend(self.archive)
            self.assertEqual(backend.tasks_list()['count'], 1)
            self.assertIsNotNone(backend.index)

    def test_date_strictness_and_bm25_limit(self):
        for raw in ('2020-W01-1', '2020-02-31', 'next week', None): self.assertIsNone(iso_date(raw))
        self.assertEqual(iso_date('2020-01-02'), '2020-01-02')
        index = DataIndex([{'id': str(i), 'title': 'Synthetic needle', 'due_text': '2020-W01-1'} for i in range(12)], [])
        result = index.memory_ask('needle')
        self.assertEqual((result['count'], result['matches']), (10, 12))
        self.assertEqual(result['answer'], 'Auswahl, keine Vollständigkeit')
        self.assertTrue(all('source' in r['item'] and 'reife' in r['item'] for r in result['results']))
        self.assertEqual(index.tasks_list(due_before='2020-02-01')['count'], 0)

    def test_source_reference_and_wrapped_hash_must_match(self):
        entry = fixture_source(); entry['source_version'] = '0' * 64
        mini_archive(self.archive, [entry])
        with self.assertRaisesRegex(ValueError, 'reference'): snapshot.build_index(self.archive)
        entry = fixture_source(); raw = json.dumps(entry)
        mini_archive(self.archive, [{'kind': 'journal', 'sequence': 1, 'record_json': raw, 'record_hash': '0' * 64}])
        with self.assertRaisesRegex(ValueError, 'checksum'): snapshot.build_index(self.archive)

    def test_document_recency_uses_instants_and_same_content_notes(self):
        documents = [
            {'id': 'newer', 'source_id': 'synthetic-doc-source', 'event_date': '2020-01-01',
             'body_hash': 'current-content', 'observed_at': '2020-01-01T10:00:00Z', 'title': 'Synthetic current'},
            {'id': 'older', 'source_id': 'synthetic-doc-source', 'event_date': '2020-01-01',
             'body_hash': 'stale-content', 'observed_at': '2020-01-01T11:00:00+02:00', 'title': 'Synthetic stale'}]
        notes = [{'id': 'old-note', 'document_id': 'older', 'note_json': json.dumps({'executive_summary': 'Synthetic stale summary'})}]
        mini_archive(self.archive, [], documents, notes)
        index = snapshot.build_index(self.archive)
        meeting = index.meetings_recent()['meetings'][0]
        self.assertEqual(meeting['id'], 'newer')
        self.assertIsNone(meeting['summary'])
        self.assertEqual(index.memory_ask('summary')['count'], 0)

if __name__ == '__main__': unittest.main()
