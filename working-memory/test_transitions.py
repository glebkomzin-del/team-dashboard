"""Synthetic state-contract tests, not labels for model extraction quality."""
import sqlite3
import tempfile
from pathlib import Path
import unittest
from memory import connect, register, claim, apply, overview, ValidationError
from test_memory import observation, proposal
from review_api import open_readonly, review

class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'memory.sqlite'
        self.db = connect(self.path)
        self.number = 0
    def tearDown(self):
        self.db.close(); self.tmp.cleanup()
    def append(self, day, quote, **fields):
        self.number += 1
        job = register(self.db, source_id=f'fixture:{self.number}', event_date=day, title='Synthetic sequence', transcript=quote)
        apply(self.db, job, claim(self.db, job), proposal(observation(quotes=[quote], due_text=None, **fields)), model='fixture')
    def test_full_transition_sequence(self):
        quote = 'Gleb: Ich sende den Bericht morgen.'
        job = register(self.db, source_id='first', event_date='2026-07-15', title='Synthetic sequence', transcript=quote)
        apply(self.db, job, claim(self.db, job), proposal(observation(quotes=[quote])), model='fixture')
        initial = overview(self.db)['personal'][0]; wid = initial['id']
        self.append('2026-07-16', 'Gleb: Die Arbeit läuft.', kind='status', owner=None, update='progress', update_target=wid)
        item = overview(self.db)['personal'][0]
        self.assertEqual((item['due_text'], item['due_reference_date'], item['owner']), ('morgen', '2026-07-15', 'Gleb'))
        quote = 'Gleb: Der neue Termin ist Freitag.'
        job = register(self.db, source_id='date', event_date='2026-07-17', title='Synthetic sequence', transcript=quote)
        apply(self.db, job, claim(self.db, job), proposal(observation(kind='status', quotes=[quote], due_text='Freitag', owner=None, update='date_changed', update_target=wid)), model='fixture')
        self.append('2026-07-18', 'Oliver: Ich übernehme den Bericht.', kind='status', owner='Oliver', update='owner_changed', update_target=wid)
        item = overview(self.db)['waiting'][0]
        self.assertEqual((item['id'], item['title'], item['due_text'], item['due_reference_date']), (wid, initial['title'], 'Freitag', '2026-07-17'))
        self.assertFalse(overview(self.db)['personal'])
        self.append('2026-07-19', 'Oliver: Der Bericht ist versendet.', kind='status', owner=None, update='done', update_target=wid)
        self.append('2026-07-20', 'Oliver: Ich erläutere den Versand.', kind='status', owner=None, work_state='open', update='progress', update_target=wid)
        self.assertEqual(len(overview(self.db)['completed']), 1)
        self.append('2026-07-21', 'Oliver: Ich muss ihn erneut überarbeiten.', kind='status', owner=None, update='reopened', update_target=wid)
        item = overview(self.db)['waiting'][0]
        self.assertEqual(item['owner'], 'Oliver'); self.assertFalse(overview(self.db)['completed'])
        self.assertEqual([e['action'] for e in item['history']], ['created','progress','date_changed','owner_changed','done','progress','reopened'])
        self.assertEqual(len({e['source_version'] for e in item['history']}), 7)
        self.assertTrue(all(len(e['content_hash']) == 64 for e in item['history']))
        self.assertEqual(overview(self.db, '2026-07-15')['personal'][0]['due_text'], 'morgen')
        self.assertEqual(len(overview(self.db, '2026-07-19')['completed']), 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM matters').fetchone()[0], 1)
    def test_cross_matter_update_rolls_back(self):
        self.append('2026-07-15', 'Gleb: Ich sende den Bericht.')
        wid = overview(self.db)['personal'][0]['id']
        self.append('2026-07-16', 'Oliver: Ich teste den Export.', matter='Anderes Projekt', owner='Oliver')
        other = self.db.execute('SELECT id FROM matters WHERE title=?', ('Anderes Projekt',)).fetchone()[0]
        before = self.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        with self.assertRaisesRegex(ValidationError, 'different matter'):
            self.append('2026-07-17', 'Gleb: Der Bericht ist erledigt.', matter_id=other, update_target=wid, update='done', kind='status')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], before)
        self.assertEqual(len(overview(self.db)['personal']), 1)
    def test_owner_and_due_changes_require_values(self):
        self.append('2026-07-15', 'Gleb: Ich sende den Bericht.')
        wid = overview(self.db)['personal'][0]['id']
        for action in ('owner_changed', 'date_changed'):
            with self.assertRaises(ValidationError):
                self.append('2026-07-16', 'Der Bericht wird besprochen.', kind='status', owner=None, update=action, update_target=wid)
    def test_name_substring_is_not_personal_identity(self):
        self.append('2026-07-15', 'Glebek: Ich sende den Bericht.', owner='Glebek')
        self.assertFalse(overview(self.db)['personal']); self.assertEqual(len(overview(self.db)['waiting']), 1)
    def test_review_as_of_and_read_only_boundary(self):
        self.append('2026-07-15', 'Gleb: Ich sende den Bericht.')
        self.append('2026-07-20', 'Oliver: Ich teste den Export.', owner='Oliver')
        with open_readonly(self.path) as db:
            state = review(db, '2026-07-15')
            self.assertEqual((len(state['sources']), len(state['jobs']), len(state['changes'])), (1,1,1))
            self.assertEqual(review(db)['as_of'], '2026-07-20')
            self.assertEqual(review(db, '2026-07-14')['sources'], [])
            with self.assertRaises(ValueError): review(db, '2026-02-30')
            with self.assertRaises(sqlite3.OperationalError): db.execute('DELETE FROM observations')
        missing = Path(self.tmp.name) / 'missing.sqlite'
        with self.assertRaises(sqlite3.OperationalError): open_readonly(missing)
        self.assertFalse(missing.exists())

if __name__ == '__main__': unittest.main()
