from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from index import DataIndex, normalize_task

def task(id, **changes):
    return {'id': id, 'title': 'Synthetic alpha', 'claim': 'Synthetic beta', 'owner': 'Person Alpha',
        'matter': 'Synthetic topic', 'matter_id': 'topic-1', 'status': 'open', 'due_text': '2020-02-01',
        'last_changed': '2020-01-15', 'quotes': ['Synthetic quote'], 'history': [{'source_title': 'Synthetic meeting',
        'event_date': '2020-01-01', 'quotes': ['Synthetic quote'], 'action': 'created'}], **changes}

class IndexTests(unittest.TestCase):
    def setUp(self):
        self.index = DataIndex([task('1'), task('2', owner='Person Beta', status='done'),
            task('3', due_text='next week', uncertainty='Synthetic uncertainty'),
            task('4', status='waiting', matter='Other topic', matter_id='topic-2', due_text='2020-01-20')],
            [{'id': 'meeting-1', 'title': 'Synthetic meeting', 'date': '2020-01-01', 'summary': 'Synthetic gamma'}])
    def test_filters_boundaries(self):
        for filters,count in [({'status':'open'},2),({'owner':'alpha','matter':'topic-1'},2),({'owner':'BETA'},1),
            ({'due_before':'2020-02-01'},1),({'updated_since':'2020-01-15'},4),({'updated_since':'2020-01-16'},0),
            ({'text':'alpha beta'},4),({'text':'unknown synthetic token'},0)]:
            self.assertEqual(self.index.tasks_list(**filters)['count'], count)
    def test_maturity(self):
        self.assertEqual(self.index.task_get('1')['task']['reife'], 'belegt')
        self.assertEqual(self.index.task_get('3')['task']['reife'], 'Annahme')
        self.assertEqual(DataIndex([task('u',history=[],quotes=[])],[]).task_get('u')['task']['reife'],'unbekannt')
    def test_search_notes_and_no_match(self):
        result = self.index.memory_ask('gamma')
        self.assertEqual(result['answer'], 'Auswahl, keine Vollständigkeit')
        self.assertEqual(result['results'][0]['kind'], 'meeting')
        self.assertEqual(result['results'][0]['item']['source']['date'], '2020-01-01')
        self.assertEqual(self.index.memory_ask('nonmatching')['count'],0)
    def test_overdue_excludes_done_and_unknown(self):
        result = self.index.memory_ask('Welche Aufgaben sind überfällig?')
        self.assertEqual({r['item']['id'] for r in result['results']},{'1','4'})
        self.assertEqual(result['unknown_due_dates'],1)
    def test_matters_meeting_limits(self):
        self.assertEqual(self.index.matters_list()['count'],2)
        self.assertEqual(self.index.meetings_recent()['count'],1)
        for n in (0,101,True):
            with self.assertRaises(ValueError): self.index.meetings_recent(n)
    def test_invalid_filters_and_id(self):
        for filters in ({'status':'unknown'},{'due_before':'tomorrow'},{'updated_since':'2020-02-31'}):
            with self.assertRaises(ValueError): self.index.tasks_list(**filters)
        with self.assertRaises(ValueError): self.index.task_get('missing')
    def test_planning_history_is_idempotent(self):
        first = {'command_id': 'synthetic-command-1', 'event_date': '2020-01-02',
                 'action': 'create_task', 'patch': {'title': 'Synthetic task'}}
        second = {'command_id': 'synthetic-command-2', 'event_date': '2020-01-03',
                  'action': 'update_task', 'patch': {'status': 'done'}}
        raw = task('manual', origin='manual', history=[], planning_history=[first, second])
        once = normalize_task(raw)
        result = DataIndex([once], []).task_get('manual')['task']
        self.assertEqual(len(result['history']), 2)
        self.assertEqual([e['command_id'] for e in result['history']], ['synthetic-command-1', 'synthetic-command-2'])
        self.assertEqual(normalize_task(result), result)
        self.assertEqual(result['planning_history'], [first, second])

if __name__ == '__main__': unittest.main()
