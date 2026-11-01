"""Synthetic transport tests: no server, real meeting data, or provider calls."""
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
sys.path.insert(0, str(Path(__file__).resolve().parent))
import live


class TestLive(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'DASHBOARD_API_BASE': 'https://example.invalid',
                                         'DASHBOARD_API_TOKEN': 'synthetic-secret'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.backend = live.LiveBackend()

    def transport(self, payloads):
        requests = []
        def open_request(request, timeout):
            requests.append((request, timeout))
            value = payloads.pop(0)
            if isinstance(value, Exception):
                raise value
            return io.BytesIO(json.dumps(value).encode())
        mock = patch.object(self.backend._opener, 'open', side_effect=open_request)
        mock.start()
        self.addCleanup(mock.stop)
        return requests

    def test_origin_and_prefixed_base(self):
        for base in ('https://example.invalid', 'https://example.invalid/',
                     'https://example.invalid/api/working-memory',
                     'https://example.invalid/api/working-memory/'):
            with patch.dict(os.environ, {'DASHBOARD_API_BASE': base}):
                self.assertEqual(live.LiveBackend()._base,
                                 'https://example.invalid/api/working-memory')

    def test_configuration_rejects_unsafe_urls_and_missing_values(self):
        for base in ('http://example.invalid', 'https://u:p@example.invalid',
                     'https://example.invalid?x=1', 'https://example.invalid#x',
                     'https://example.invalid/other', 'https://example.invalid:bad',
                     'file:///tmp/x', ''):
            with patch.dict(os.environ, {'DASHBOARD_API_BASE': base}):
                with self.assertRaises(live.LiveError) as caught:
                    live.LiveBackend()
                self.assertNotIn('synthetic-secret', str(caught.exception))
        with patch.dict(os.environ, {'DASHBOARD_API_TOKEN': ''}):
            with self.assertRaises(live.LiveError):
                live.LiveBackend()
        with patch.dict(os.environ, {'DASHBOARD_API_TOKEN': 'secret'+chr(13)+chr(10)+'Injected: x'}):
            with self.assertRaises(live.LiveError):
                live.LiveBackend()

    def test_loopback_http_allowed(self):
        for base in ('http://localhost:8080', 'http://127.0.0.1:8080', 'http://[::1]:8080'):
            with patch.dict(os.environ, {'DASHBOARD_API_BASE': base}):
                self.assertTrue(live.LiveBackend()._base.startswith(base))

    @staticmethod
    def snapshot():
        groups = ('personal', 'waiting_dependencies', 'waiting', 'completed', 'cancelled')
        statuses = ('open', 'waiting', 'open', 'done', 'cancelled')
        result = {'sources': [{'id': 's1', 'title': 'Synthetic source', 'event_date': '2026-01-01'}],
                  'knowledge': [], 'revision': 7, 'as_of': '2026-01-02'}
        for i, (group, status) in enumerate(zip(groups, statuses)):
            result[group] = [{'id': str(i), 'title': 'Synthetic task ' + str(i),
                              'claim': 'Synthetic evidence', 'owner': 'Alias A', 'status': status,
                              'matter': 'Synthetic matter', 'due_date': '2026-01-03',
                              'last_changed': '2026-01-02',
                              'history': [{'event_date': '2026-01-01', 'source_version': 's1',
                                           'action': 'created'}]}]
        return result

    def test_groups_filters_headers_and_history(self):
        requests = self.transport([self.snapshot(), self.snapshot(), self.snapshot()])
        all_tasks = self.backend.tasks_list()
        self.assertEqual(all_tasks['count'], 5)
        selected = self.backend.tasks_list(status='waiting', owner='Alias A',
                                           matter='Synthetic matter', due_before='2026-01-04',
                                           updated_since='2026-01-01', text='evidence')
        self.assertEqual(selected['count'], 1)
        task = self.backend.task_get('1')['task']
        self.assertEqual(task['history'][0]['action'], 'created')
        self.assertEqual(task['history'][0]['source']['meeting_title'], 'Synthetic source')
        self.assertEqual(task['source']['meeting_title'], 'Synthetic source')
        self.assertNotIn('knowledge', all_tasks['source'])
        for request, timeout in requests:
            self.assertEqual(request.full_url, 'https://example.invalid/api/working-memory/review')
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-secret')
            self.assertEqual(timeout, 20)

    def test_paginated_archive_and_summaries(self):
        rows = [{'id': str(i), 'title': 'Synthetic source', 'event_date': '2026-01-01'}
                for i in range(101)]
        payloads = [{'sources': rows[:100], 'total': 101}]
        payloads.extend([{'id': str(i), 'summaries': [{'executive_summary': 'Synthetic summary'}]} for i in range(100)])
        payloads += [{'sources': rows[100:], 'total': 101},
                     {'id': '100', 'summaries': [{'ai_summary': 'Synthetic detail'}]}]
        requests = self.transport(payloads)
        result = self.backend._meetings(101)
        self.assertEqual(len(result), 101)
        self.assertIn('offset=100', requests[101][0].full_url)
        self.assertIn('limit=1', requests[101][0].full_url)
        self.assertEqual(result[0]['summary'], 'Synthetic summary')

    def test_readonly_question_uses_local_index(self):
        requests = self.transport([self.snapshot(), {'sources': [{'id': 'a', 'title': 'Synthetic',
            'event_date': '2026-01-01'}], 'total': 1},
            {'id': 'a', 'summaries': [{'ai_summary': 'Synthetic evidence'}]}])
        result = self.backend.memory_ask('evidence')
        self.assertIn('live_questions_unavailable_read_only', result['limitations'])
        self.assertGreater(result['count'], 0)
        self.assertTrue(all(request.method == 'GET' for request, _ in requests))
        self.assertFalse(any('/questions' in request.full_url for request, _ in requests))

    def test_recent_envelope_and_matters(self):
        self.transport([{'sources': [{'id': 'a', 'title': 'Synthetic',
                          'event_date': '2026-01-01'}], 'total': 1}, {'id': 'a', 'summaries': []},
                        self.snapshot()])
        result = self.backend.meetings_recent()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['meetings'][0]['source']['date'], '2026-01-01')
        self.assertTrue(result['source']['read_only'])
        self.assertEqual(self.backend.matters_list()['count'], 1)

    def test_archive_detail_identity_required(self):
        for detail in ({}, {'id': 'other'}, {'id': None}):
            with patch.object(self.backend, '_get', side_effect=[
                    {'sources': [{'id': 'a'}], 'total': 1}, detail]):
                with self.assertRaisesRegex(live.LiveError, 'Invalid Dashboard archive response'):
                    self.backend.meetings_recent()

    def test_archive_provenance_and_summary_maturity(self):
        self.transport([{'sources': [{'id': 'a', 'title': 'Synthetic original',
            'summary_title': 'Synthetic display', 'event_date': '2026-01-01'}], 'total': 1},
            {'id': 'a', 'provenance': {'origin': 'synthetic'}, 'deleted': True,
             'summaries': [{'ai_summary': 'Synthetic inference'}]}])
        meeting = self.backend.meetings_recent()['meetings'][0]
        self.assertEqual(meeting['source']['source_id'], 'a')
        self.assertEqual(meeting['source']['meeting_title'], 'Synthetic display')
        self.assertEqual(meeting['provenance'], {'origin': 'synthetic'})
        self.assertTrue(meeting['deleted'])
        self.assertEqual(meeting['reife'], 'Annahme')

    def test_optional_cancelled_group(self):
        snapshot = self.snapshot()
        del snapshot['cancelled']
        self.transport([snapshot])
        self.assertEqual(self.backend.tasks_list()['count'], 4)

    def test_malformed_snapshot_is_not_empty_success(self):
        for payload in ({}, {'personal': None}, {**self.snapshot(), 'sources': [None]},
                        {**self.snapshot(), 'personal': [{'id': 'x', 'history': [None]}]}):
            with patch.object(self.backend, '_get', return_value=payload):
                with self.assertRaises(live.LiveError):
                    self.backend.tasks_list()

    def test_transport_errors_are_redacted(self):
        for error in (HTTPError('https://synthetic-secret.invalid', 401, 'synthetic-secret',
                                {}, io.BytesIO(b'synthetic-secret')),
                      URLError('synthetic-secret')):
            with patch.object(self.backend._opener, 'open', side_effect=error):
                with self.assertRaises(live.LiveError) as caught:
                    self.backend._get('/review')
                self.assertNotIn('synthetic-secret', str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
        with patch.object(self.backend._opener, 'open', return_value=io.BytesIO(b'synthetic-secret')):
            with self.assertRaises(live.LiveError):
                self.backend._get('/review')

    def test_redirects_are_not_followed(self):
        handler = next(item for item in self.backend._opener.handlers
                       if isinstance(item, live._NoRedirect))
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'https://other.invalid'))
        error = HTTPError('https://example.invalid', 302, 'synthetic-secret',
                          {'Location': 'https://other.invalid'}, io.BytesIO(b''))
        requests = self.transport([error])
        with self.assertRaisesRegex(live.LiveError, '302'):
            self.backend._get('/review')
        self.assertEqual(len(requests), 1)

    def test_zero_recent_and_invalid_pagination(self):
        requests = self.transport([])
        for n in (-1, 0, 101, True, '10'):
            with self.assertRaises(ValueError):
                self.backend.meetings_recent(n)
        self.assertEqual(requests, [])
        with patch.object(self.backend, '_get', return_value={'sources': [], 'total': 1}):
            with self.assertRaises(live.LiveError):
                self.backend._meetings()


if __name__ == '__main__':
    unittest.main()
