"""GET-only Dashboard adapter. Questions are answered locally, never via POST."""
import ipaddress
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from index import DataIndex, normalize_task


class LiveError(RuntimeError):
    """Safe errors contain neither credentials nor remote response bodies."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _base_url(value):
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        parsed.port
        loopback = host == 'localhost'
        if host:
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                pass
        if (not host or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or chr(92) in value
                or any(c.isspace() or ord(c) < 32 for c in value)
                or parsed.scheme not in ('http', 'https')
                or (parsed.scheme == 'http' and not loopback)
                or parsed.path.rstrip('/') not in ('', '/api/working-memory')):
            raise ValueError
        return urlunsplit((parsed.scheme, parsed.netloc, '/api/working-memory', '', ''))
    except (ValueError, TypeError):
        raise LiveError('Invalid DASHBOARD_API_BASE configuration') from None


class LiveBackend:
    def __init__(self):
        base = os.environ.get('DASHBOARD_API_BASE')
        token = os.environ.get('DASHBOARD_API_TOKEN')
        if not base or not token:
            raise LiveError('DASHBOARD_API_BASE and DASHBOARD_API_TOKEN are required')
        self._base = _base_url(base)
        if any(c.isspace() for c in token):
            raise LiveError('Invalid DASHBOARD_API_TOKEN configuration')
        self._token = token
        self._opener = build_opener(_NoRedirect())

    def _get(self, path, params=None):
        url = self._base + path
        if params:
            url += '?' + urlencode(params)
        request = Request(url, headers={'Authorization': 'Bearer ' + self._token,
                                      'Accept': 'application/json'}, method='GET')
        try:
            with self._opener.open(request, timeout=20) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise LiveError('Invalid Dashboard response')
            return result
        except HTTPError as error:
            code = error.code
            error.close()
            raise LiveError('Dashboard HTTP error ' + str(code)) from None
        except (URLError, OSError, ValueError, TypeError, UnicodeError):
            raise LiveError('Dashboard read failed') from None

    def _tasks(self):
        snapshot = self._get('/review')
        if any(key not in snapshot for key in
               ('personal', 'waiting_dependencies', 'waiting', 'completed', 'sources')):
            raise LiveError('Invalid Dashboard review response')
        tasks, seen = [], set()
        sources = snapshot.get('sources', [])
        if not isinstance(sources, list) or any(not isinstance(s, dict) or 'id' not in s for s in sources):
            raise LiveError('Invalid Dashboard review response')
        for group in ('personal', 'waiting_dependencies', 'waiting', 'completed', 'cancelled'):
            rows = snapshot.get(group, [])
            if not isinstance(rows, list):
                raise LiveError('Invalid Dashboard review response')
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                    raise LiveError('Invalid Dashboard review response')
                if any(not isinstance(row.get(key, []), list) or
                       any(not isinstance(event, dict) for event in row.get(key, []))
                       for key in ('history', 'planning_history')):
                    raise LiveError('Invalid Dashboard review response')
                task = normalize_task(row, sources)
                if task['id'] not in seen:
                    tasks.append(task)
                    seen.add(task['id'])
        metadata = {key: snapshot[key] for key in
                    ('as_of', 'revision', 'archive_revision', 'mode') if key in snapshot}
        metadata.update(backend='live', read_only=True)
        return tasks, metadata

    def _index(self):
        tasks, metadata = self._tasks()
        return DataIndex(tasks, [], metadata)

    def tasks_list(self, status=None, owner=None, matter=None, due_before=None,
                   updated_since=None, text=None):
        return self._index().tasks_list(status=status, owner=owner, matter=matter,
                                       due_before=due_before, updated_since=updated_since, text=text)

    def task_get(self, id):
        return self._index().task_get(id)

    def matters_list(self):
        return self._index().matters_list()

    def _meetings(self, n=None):
        meetings, offset = [], 0
        while n is None or len(meetings) < n:
            limit = 100 if n is None else min(100, n - len(meetings))
            page = self._get('/archive', {'order': 'newest', 'limit': limit, 'offset': offset})
            rows, total = page.get('sources'), page.get('total')
            if (not isinstance(rows, list) or type(total) is not int or total < 0
                    or (not rows and offset < total)):
                raise LiveError('Invalid Dashboard archive response')
            for row in rows:
                if not isinstance(row, dict):
                    raise LiveError('Invalid Dashboard archive response')
                identifier = row.get('id')
                if not isinstance(identifier, str) or not identifier:
                    raise LiveError('Invalid Dashboard archive response')
                detail = self._get('/archive/' + quote(identifier, safe=''))
                if detail.get('id') != identifier:
                    raise LiveError('Invalid Dashboard archive response')
                summaries = detail.get('summaries', [])
                if not isinstance(summaries, list) or any(not isinstance(note, dict) for note in summaries):
                    raise LiveError('Invalid Dashboard archive response')
                summary = chr(10).join(str(note.get(field) or '') for note in summaries
                                    for field in ('executive_summary', 'ai_summary')).strip()
                meetings.append({**row, 'title': row.get('summary_title') or row.get('title', ''),
                                 'date': row.get('event_date'), 'summary': summary,
                                 'summaries': summaries, 'source': 'archive:' + identifier,
                                 'sources': [row], 'provenance': detail.get('provenance', {}),
                                 'deleted': detail.get('deleted', False)})
            offset += len(rows)
            if offset >= total:
                break
            if offset > 100000:
                raise LiveError('Dashboard archive exceeds supported pagination')
        return meetings

    def meetings_recent(self, n=10):
        if type(n) is not int or not 1 <= n <= 100:
            raise ValueError('n must be an integer from 1 to 100')
        return DataIndex([], self._meetings(n), {'backend': 'live', 'read_only': True}).meetings_recent(n)

    def memory_ask(self, question):
        tasks, metadata = self._tasks()
        metadata['limitations'] = ['live_questions_unavailable_read_only']
        result = dict(DataIndex(tasks, self._meetings(), metadata).memory_ask(question))
        result['limitations'] = list(dict.fromkeys(
            [*result.get('limitations', []), 'live_questions_unavailable_read_only']))
        return result
