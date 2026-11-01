"""M5-DAILY local validation, synthetic only.
Question: are orchestration, delta/cooldown state, positive cache receipts and
selection gates preserved, including failure and unknown evidence?
Criterion: exact artifacts, cross-date idempotency, independent feasible steps,
real enforced deadlines and all requested output limits.
Scope: synthetic mini archives, disposable files inside daily, pure mocks.
Decision: green supports local acceptance; real archive/review remain with Lead.
"""
import copy
from datetime import date
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_daily as daily
TODAY = date(2026, 10, 13)


def task(identity='synthetic-1', **changes):
    value = dict.fromkeys(daily.SNAPSHOT_FIELDS)
    value.update(id=identity, title='Synthetic task', claim='Synthetic claim',
                 owner='Gleb', status='open', due_text='2026-10-14', due_date=None,
                 first_changed='2026-10-01', last_changed='2026-10-13')
    value.update(changes)
    return value


def row(identity='synthetic-1', importance='wichtig', kind='task'):
    return dict(id=identity, klasse=importance, record_type=kind, status='open')


def wait_forever():
    time.sleep(5)


def raise_private():
    raise ValueError('private-data-must-not-appear')


class FakeSession:
    tasks = [task()]
    rows = [row()]
    failure = None
    calls = []
    def __init__(self, archive, today):
        self.today = today
        self.closed = False
    def initial(self, timeout):
        self.calls.append('archive')
        if self.failure == 'archive':
            return {'status': 'timeout', 'error': 'E_STEP_TIMEOUT', 'seconds': .01}
        return {'status': 'ok', 'value': {'tasks': copy.deepcopy(self.tasks), 'candidate_count': 0, 'revision': 1}, 'seconds': .01}
    def step(self, name, payload, timeout):
        self.calls.append(name)
        if self.failure == name:
            return {'status': 'error', 'error': 'SyntheticError', 'seconds': .01}
        if name == 'reminders':
            result = daily.modules()[0].build_digest(self.tasks, date.fromisoformat(self.today), 'Gleb', payload)
            value = {'text': result.text, 'state': result.state, 'counts': result.counts, 'shown': result.shown, 'omitted': result.omitted}
        elif name == 'relevance':
            value = {'rows': copy.deepcopy(self.rows), 'config': {}}
        else:
            value = {'packages': [{'id': identity, 'text': '# Synthetic package\n', 'lines': 1, 'bytes': 20, 'longest_line': 19} for identity in payload]}
        return {'status': 'ok', 'value': value, 'seconds': .01}
    def close(self):
        self.closed = True


class TempTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.synthetic-', dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.archive = self.folder / 'dashboard-20261013T000000Z.tar.gz'
        self.archive.write_bytes(b'synthetic archive mock')
        self.state = self.folder / 'state.json'
        self.out = self.folder / 'out' / '2026-10-13'
        FakeSession.tasks = [task()]; FakeSession.rows = [row()]
        FakeSession.failure = None; FakeSession.calls = []
    def run_fake(self, **changes):
        options = dict(today=TODAY.isoformat(), out=self.out, archive=self.archive,
                       state_path=self.state, step_timeout=2, session_factory=FakeSession)
        options.update(changes)
        return daily.run_daily(**options)
    def read(self, name):
        return json.loads((self.out / name).read_text())
    def test_orchestration_and_artifacts(self):
        result = self.run_fake()
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(FakeSession.calls, ['archive', 'reminders', 'relevance', 'handover'])
        self.assertEqual(result['packages'], 1)
        for name in ('digest.md', 'relevance.jsonl', 'uebersicht.md', 'delivery.json', 'run.json', 'state.json', 'pakete/paket-01.md'):
            self.assertTrue((self.out / name).is_file())
            self.assertEqual((self.out / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.read('run.json')['status'], 'completed')
        self.assertEqual(self.read('run.json')['digest_entry_count'], 1)
        self.assertGreater(self.read('run.json')['total_seconds'], 0)
        self.assertEqual(self.read('delivery.json')['sent'], False)
        self.assertEqual(self.read('state.json')['reminders']['last_sent']['synthetic-1']['due_soon'], '2026-10-13')
    def test_same_date_and_archive_no_rewrites(self):
        self.run_fake()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.folder.rglob('*') if p.is_file()}
        FakeSession.calls = []
        self.assertTrue(self.run_fake()['cached'])
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.folder.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(FakeSession.calls, [])
    def test_no_new_archive_across_date_and_out(self):
        self.run_fake()
        before = self.state.read_bytes()
        second = self.folder / 'out' / '2026-10-14'
        result = self.run_fake(today='2026-10-14', out=second)
        self.assertTrue(result['cached'])
        self.assertEqual(result['out'], str(self.out))
        self.assertFalse(second.exists())
        self.assertEqual(before, self.state.read_bytes())
    def test_new_archive_delta_spans_out_folders(self):
        self.run_fake()
        self.archive = self.folder / 'dashboard-20261014T000000Z.tar.gz'
        self.archive.write_bytes(b'new synthetic input')
        FakeSession.tasks = [task(title='Changed synthetic title'), task('synthetic-2')]
        FakeSession.rows = [row(), row('synthetic-2')]
        self.out = self.folder / 'out' / '2026-10-14'
        self.run_fake(today='2026-10-14')
        run = self.read('run.json')
        self.assertEqual(run['new_task_ids'], ['synthetic-2'])
        self.assertEqual(run['changed_task_ids'], ['synthetic-1'])
        self.assertEqual(len(run['packages']), 2)
        # Existing cooldown continues despite new out folder/archive/task change.
        state = self.read('state.json')
        self.assertEqual(state['reminders']['last_sent']['synthetic-1']['due_soon'], '2026-10-13')
    def test_new_archive_unchanged_task_not_repackaged(self):
        self.run_fake()
        self.archive = self.folder / 'dashboard-20261014T000000Z.tar.gz'
        self.archive.write_bytes(b'new input')
        self.out = self.folder / 'out' / '2026-10-14'
        self.assertEqual(self.run_fake(today='2026-10-14')['packages'], 0)
    def test_cache_requires_positive_receipt_not_just_files(self):
        self.run_fake()
        value = json.loads(self.state.read_text()); value['last_success'] = None
        self.state.write_text(json.dumps(value))
        FakeSession.calls = []
        self.assertFalse(self.run_fake()['cached'])
        self.assertIn('archive', FakeSession.calls)
    def test_cache_missing_artifact_does_not_skip(self):
        self.run_fake(); (self.out / 'digest.md').unlink()
        self.assertFalse(self.run_fake()['cached'])
        self.assertTrue((self.out / 'digest.md').is_file())
    def test_reminders_failure_isolated(self):
        FakeSession.failure = 'reminders'
        result = self.run_fake()
        self.assertEqual(result['exit_code'], 1)
        self.assertEqual(result['packages'], 1)
        self.assertTrue((self.out / 'relevance.jsonl').exists())
        self.assertTrue((self.out / 'uebersicht.md').exists())
        self.assertFalse((self.out / 'delivery.json').exists())
        self.assertEqual(self.read('run.json')['steps']['delivery']['error'], 'E_DIGEST_UNAVAILABLE')
        self.assertIsNone(json.loads(self.state.read_text())['last_success'])
        self.assertEqual(json.loads(self.state.read_text())['reminders']['last_sent'], {})
    def test_relevance_failure_isolated_and_no_false_package(self):
        FakeSession.failure = 'relevance'
        result = self.run_fake()
        self.assertEqual(result['exit_code'], 1)
        self.assertTrue((self.out / 'digest.md').exists())
        self.assertTrue((self.out / 'delivery.json').exists())
        self.assertEqual(self.read('run.json')['steps']['handover']['status'], 'skipped')
        self.assertEqual(json.loads(self.state.read_text())['reminders']['last_sent'], {})
    def test_handover_failure_isolated(self):
        FakeSession.failure = 'handover'
        self.assertEqual(self.run_fake()['exit_code'], 1)
        self.assertTrue((self.out / 'delivery.json').exists())
    def test_archive_timeout_reports_other_steps_unavailable(self):
        FakeSession.failure = 'archive'
        self.assertEqual(self.run_fake()['exit_code'], 1)
        self.assertEqual(self.read('run.json')['steps']['archive']['status'], 'timeout')
        self.assertEqual(self.read('run.json')['steps']['overview']['status'], 'ok')
        self.assertTrue((self.out / 'uebersicht.md').exists())
    def test_failed_run_retry_not_cached(self):
        FakeSession.failure = 'handover'; self.run_fake()
        FakeSession.failure = None
        result = self.run_fake()
        self.assertEqual(result['exit_code'], 0)
        self.assertFalse(result['cached'])
    def test_missing_archive_abstract_exit2(self):
        sink = io.StringIO()
        with patch('sys.stdout', sink):
            result = daily.main(['--archive', str(self.folder / 'absent'), '--out', str(self.out)])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(sink.getvalue())['error'], 'E_NO_ARCHIVE')
        self.assertNotIn(str(self.folder), sink.getvalue())
    def test_latest_archive_name_order_not_mtime(self):
        later = self.folder / 'dashboard-20261014T000000Z.tar.gz'; later.write_bytes(b'x')
        os.utime(self.archive, ns=(time.time_ns() + 10000000000,) * 2)
        self.assertEqual(daily.latest_archive(self.folder), later)
    def test_no_archive_clear_failure(self):
        self.archive.unlink()
        with self.assertRaises(FileNotFoundError): daily.latest_archive(self.folder)
    def test_output_boundary(self):
        with self.assertRaises(ValueError): daily.output_path(HERE.parent / 'reminders' / 'outside.txt')
    def test_invalid_state_not_reset(self):
        self.state.write_text('{"version": 999}')
        with self.assertRaises(ValueError): self.run_fake()
        self.assertFalse(self.out.exists())
    def test_newer_archive_same_date_removes_stale_packages(self):
        FakeSession.tasks = [task(str(i)) for i in range(5)]
        FakeSession.rows = [row(str(i)) for i in range(5)]
        self.assertEqual(self.run_fake()['packages'], 5)
        self.archive = self.folder / 'dashboard-20261013T010000Z.tar.gz'
        self.archive.write_bytes(b'newer synthetic archive')
        self.assertEqual(self.run_fake()['packages'], 0)
        self.assertEqual(list((self.out / 'pakete').glob('paket-*.md')), [])
    def test_overview_write_failure_is_recorded_and_delivery_continues(self):
        original = daily.atomic_write
        def failing(path, text):
            if Path(path).name == 'uebersicht.md':
                raise OSError('Synthetic write failure')
            return original(path, text)
        with patch.object(daily, 'atomic_write', side_effect=failing):
            self.assertEqual(self.run_fake()['exit_code'], 1)
        self.assertEqual(self.read('run.json')['steps']['overview']['status'], 'error')
        self.assertTrue((self.out / 'delivery.json').exists())
        self.assertEqual(self.read('state.json')['reminders']['last_sent'], {})
    def test_delivery_write_failure_is_recorded(self):
        original = daily.atomic_write
        def failing(path, text):
            if Path(path).name == 'delivery.json':
                raise OSError('Synthetic write failure')
            return original(path, text)
        with patch.object(daily, 'atomic_write', side_effect=failing):
            self.assertEqual(self.run_fake()['exit_code'], 1)
        self.assertEqual(self.read('run.json')['steps']['delivery']['status'], 'error')
        self.assertTrue((self.out / 'uebersicht.md').exists())
        self.assertIsNone(self.read('state.json')['last_success'])
    def test_invalid_timeout(self):
        with self.assertRaises(ValueError): self.run_fake(step_timeout=0)


class SelectionTests(unittest.TestCase):
    def selection(self, tasks, rows=None, changes=None):
        return daily.select_packages(tasks, rows if rows is not None else [row(t['id']) for t in tasks],
                                     set(changes if changes is not None else [t['id'] for t in tasks]), TODAY)
    def test_due_boundary_inclusive(self):
        for due, expected in [('2026-10-27', 1), ('2026-10-28', 0), ('2026-10-12', 1)]:
            with self.subTest(due=due):
                self.assertEqual(len(self.selection([task(due_text=due)])[0]), expected)
    def test_stalled_without_due_is_positive(self):
        selected, evidence = self.selection([task(due_text=None, last_changed='2026-09-01')])
        self.assertEqual(selected, ['synthetic-1']); self.assertEqual(evidence['eligible'], 1)
    def test_unknown_due_and_stall_is_not_positive(self):
        for due in (None, 'morgen oder Freitag', '2026-10-14 / 2026-10-20'):
            selected, evidence = self.selection([task(due_text=due, last_changed=None)])
            self.assertEqual(selected, []); self.assertEqual(evidence['unknown_due_or_stall'], 1)
    def test_unknown_class_is_not_important(self):
        selected, evidence = self.selection([task()], rows=[])
        self.assertEqual(selected, []); self.assertEqual(evidence['unknown_class'], 1)
    def test_standard_class_not_selected(self):
        self.assertEqual(self.selection([task()], [row(importance='standard')])[0], [])
    def test_candidate_does_not_establish_task_class(self):
        selected, evidence = self.selection([task()], [row(kind='candidate')])
        self.assertEqual(selected, []); self.assertEqual(evidence['unknown_class'], 1)
    def test_done_cancelled_not_selected(self):
        for status in ('done', 'cancelled', 'dismissed', 'aborted', 'candidate'):
            self.assertEqual(self.selection([task(status=status)])[0], [])
    def test_waiting_is_open(self):
        self.assertEqual(self.selection([task(status='waiting')])[0], ['synthetic-1'])
    def test_unchanged_never_selected_even_overdue(self):
        selected, evidence = self.selection([task(due_text='2020-01-01')], changes=[])
        self.assertEqual(selected, []); self.assertEqual(evidence['unchanged'], 1)
    def test_max5_stable_deterministic(self):
        tasks = [task(str(i)) for i in range(9, -1, -1)]
        selected, evidence = self.selection(tasks)
        self.assertEqual(selected, ['0', '1', '2', '3', '4'])
        self.assertEqual(evidence['limited'], 5)
    def test_direct_date(self):
        self.assertEqual(self.selection([task(due_text=None, due_date='2026-10-27')])[0], ['synthetic-1'])
    def test_last_changed_unknown_not_stalled(self):
        self.assertFalse(daily.due_and_stall(task(last_changed=None, due_text=None), TODAY)[1])


class LimitsAndProcessesTests(unittest.TestCase):
    def test_real_step_deadline(self):
        start = time.monotonic()
        result = daily.bounded_call(wait_forever, (), .08)
        self.assertEqual(result['status'], 'timeout')
        self.assertLess(time.monotonic() - start, 1)
    def test_error_does_not_leak_message(self):
        result = daily.bounded_call(raise_private, (), 1)
        self.assertEqual(result['status'], 'error')
        self.assertNotIn('private-data', json.dumps(result))
    def test_delivery_limits(self):
        output = daily.delivery('ü' * 10000, '2026-10-13')
        self.assertEqual(len(output['email_body']), 3000)
        self.assertLessEqual(len(output['push']), 140)
        self.assertFalse(output['sent'])
    def test_delivery_preserves_short_digest(self):
        self.assertEqual(daily.delivery('short\n', '2026-10-13')['email_body'], 'short\n')
    def test_overview_limit_top10_and_delta_count(self):
        tasks = [task(str(i), title='long\n' * 100) for i in range(100)]
        rows = [row(t['id']) for t in tasks]
        text = daily.overview(tasks, rows, [t['id'] for t in tasks], [], [{}] * 5, TODAY, 0)
        self.assertLessEqual(len(text.splitlines()), 60)
        self.assertEqual(text.count('Stillstand:'), 10)
        self.assertEqual(text.count('](pakete/paket-'), 5)
        self.assertIn('80', text)
    def test_overview_unknown_relevance(self):
        text = daily.overview([task()], None, [], [], [], TODAY, 1)
        self.assertIn('Klassen: unbekannt', text)
        self.assertIn('nicht bestimmbar', text)


class RealMiniArchiveTests(unittest.TestCase):
    setUp = TempTests.setUp
    read = TempTests.read
    # Integration uses real import contracts/backend and synthetic canonical data.
    def mini_archive(self, revision=1, wrapped=False):
        handover = daily.modules()[2]
        handover._backend()
        from memory import connect
        from human_decisions import record
        db = connect(':memory:')
        command = dict(action='create_task', target_id='20000000-0000-4000-8000-000000000001',
                       reason='Synthetic plan', event_date='2026-10-12',
                       patch=dict(title='Synthetic Bericht erstellen', owner='Gleb',
                                  due_date='2026-10-14', note='Ich werde den synthetischen Bericht 7 erstellen und die Datei für eine synthetische Freigabe mit Tabelle und Dokument vorbereiten.'))
        cid = '20000000-0000-4000-8000-000000000002'
        aid = '20000000-0000-4000-8000-000000000003'
        record(db, command_id=cid, actor_id=aid, command=command)
        db.close()
        entry = dict(kind='human', revision=revision, command_id=cid, actor_id=aid, payload=command)
        if wrapped:
            entry = {'kind': 'journal', 'sequence': 1, 'record_json': json.dumps(entry)}
        with tarfile.open(self.archive, 'w:gz') as archive:
            for name, records in [('journal', [entry]), ('documents', []), ('notes', getattr(self, 'notes', []))]:
                data = ''.join(json.dumps(item) + '\n' for item in records).encode()
                member = tarfile.TarInfo('canonical/' + name + '.jsonl'); member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
    def test_genuine_synthetic_orchestration(self):
        self.mini_archive()
        result = daily.run_daily(TODAY.isoformat(), self.out, self.archive, 20, state_path=self.state)
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(result['tasks'], 1)
        self.assertEqual(result['packages'], 1)
        package = (self.out / 'pakete' / 'paket-01.md').read_text()
        self.assertLessEqual(len(package.splitlines()), 150)
        self.assertLessEqual(len(package.encode()), 20000)
        self.assertLessEqual(max(map(len, package.splitlines())), 400)
        self.assertEqual(self.read('run.json')['steps']['archive']['status'], 'ok')
        run = self.read('run.json')
        self.assertGreaterEqual(run['total_seconds'], sum(step['seconds'] for step in run['steps'].values()))
        self.assertEqual(run['digest_entry_count'], 1)
        self.assertIn('Synthetic Bericht', (self.out / 'digest.md').read_text())
    def test_verified_notes_pass_to_reminders_projection(self):
        daily.modules()[2]._backend()
        from memory import fingerprint
        raw = json.dumps({'legacy_record': {'id': 'synthetic-source',
                         'title': 'Synthetic source fallback', 'meeting_date': '2026-10-12'}})
        note = dict(document_id='synthetic-document', origin='legacy_meetings',
                    origin_id='synthetic-note', note_json=raw, note_hash=fingerprint(raw), registered_revision=1)
        note['id'] = fingerprint(':'.join([note['document_id'], note['origin'], note['origin_id'], note['note_hash']]))
        self.notes = [note]
        self.mini_archive()
        reminders = daily.modules()[0]
        with patch.object(reminders, 'reconstruct_tasks', wraps=reminders.reconstruct_tasks) as spy:
            memory, _ = daily.project(self.archive, TODAY.isoformat())
        try:
            verified = spy.call_args.kwargs['notes']
            self.assertEqual(len(verified), 1)
            self.assertEqual(verified[0]['note_json'], raw)
            self.assertIn('_address', verified[0])
        finally:
            memory.db.close()
    def test_genuine_wrapped_archive(self):
        self.mini_archive(wrapped=True)
        result = daily.run_daily(TODAY.isoformat(), self.out, self.archive, 20, state_path=self.state)
        self.assertEqual(result['exit_code'], 0)
    def test_invalid_revision_isolated(self):
        self.mini_archive(revision=2)
        result = daily.run_daily(TODAY.isoformat(), self.out, self.archive, 20, state_path=self.state)
        self.assertEqual(result['exit_code'], 1)
        self.assertEqual(self.read('run.json')['steps']['archive']['status'], 'error')
        self.assertIsNone(json.loads(self.state.read_text())['last_success'])
    def test_step_timeout_preserves_projection_for_next_step(self):
        self.mini_archive()
        original = daily.execute_step
        def blocked(memory, candidates, today, name, payload):
            if name == 'reminders':
                time.sleep(5)
            return original(memory, candidates, today, name, payload)
        with patch.object(daily, 'execute_step', side_effect=blocked):
            session = daily.Session(self.archive, TODAY.isoformat())
            try:
                self.assertEqual(session.initial(20)['status'], 'ok')
                timed = session.step('reminders', {'version': 1, 'last_sent': {}}, .08)
                self.assertEqual(timed['status'], 'timeout')
                self.assertLess(timed['seconds'], 1)
                self.assertEqual(session.step('relevance', None, 20)['status'], 'ok')
            finally:
                session.close()
    def test_archive_process_real_timeout(self):
        # fork carries this mock; parent terminates the actual blocked reader.
        with patch.object(daily, 'project', side_effect=lambda *args: time.sleep(5)):
            session = daily.Session(self.archive, TODAY.isoformat())
            start = time.monotonic()
            try:
                result = session.initial(.08)
                self.assertEqual(result['status'], 'timeout')
                self.assertLess(time.monotonic() - start, 1)
                self.assertFalse(session.process.is_alive())
            finally:
                session.close()


if __name__ == '__main__':
    unittest.main()
