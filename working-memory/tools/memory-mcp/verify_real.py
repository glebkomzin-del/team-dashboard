"""Real snapshot stdio verification, emitting numeric counts/timings only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import select

def main():
    root = Path(__file__).resolve().parent
    candidates = [p for p in (Path.home() / 'Library/Application Support/Dashboard Job Backup/archives').glob('dashboard-*.tar.gz')
                  if p.is_file() and not p.is_symlink()]
    archive = max(candidates, key=lambda p: p.name)
    before = archive.stat()
    env = dict(os.environ, DASHBOARD_MEMORY_CACHE='0', DASHBOARD_MEMORY_MODE='snapshot')
    env.pop('DASHBOARD_API_TOKEN', None)
    p = subprocess.Popen([sys.executable, '-I', '-B', str(root / 'server.py'), '--mode', 'snapshot', '--archive', str(archive)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    try:
        def request(i, method, params):
            start = time.perf_counter()
            p.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}) + '\n'); p.stdin.flush()
            if not select.select([p.stdout], [], [], 1800)[0]:
                raise RuntimeError('Numeric verification timeout')
            value = json.loads(p.stdout.readline())
            if value.get('id') != i or 'error' in value or value.get('result', {}).get('isError'): raise RuntimeError('Numeric verification failed')
            return value['result'], round(time.perf_counter() - start, 6)
        request(1, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'numeric-check', 'version': '1'}})
        p.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); p.stdin.flush()
        first, tlist = request(2, 'tools/call', {'name': 'tasks_list', 'arguments': {'status': 'open'}})
        result = first['structuredContent']; tasks = result['tasks']
        assert result['count'] == len(tasks) and tasks
        chosen = next(t for t in tasks if t['history'] and any(s.get('meeting_title') and s.get('date') for s in t['sources']))
        detail, tget = request(3, 'tools/call', {'name': 'task_get', 'arguments': {'id': chosen['id']}})
        checked = detail['structuredContent']['task']
        assert checked['id'] == chosen['id'] and checked['history'] and checked['sources']
        assert checked['reife'] in ('belegt', 'Annahme', 'unbekannt')
        answer, task = request(4, 'tools/call', {'name': 'memory_ask', 'arguments': {'question': 'Welche Aufgaben sind überfällig?'}})
        assert answer['structuredContent']['answer'] == 'Auswahl, keine Vollständigkeit'
        assert answer['structuredContent']['count'] == len(answer['structuredContent']['results'])
        after = archive.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        numeric = {'open_tasks': len(tasks), 'total_tasks': result['source']['task_total'], 'tasks_list_seconds': tlist, 'task_get_seconds': tget, 'memory_ask_seconds': task, 'overdue_tasks': answer['structuredContent']['count'], 'unknown_due_dates': answer['structuredContent']['unknown_due_dates'], 'archive_bytes': archive.stat().st_size, 'archive_mtime_ns': archive.stat().st_mtime_ns}
        numeric['code_hashes'] = {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest()
                                  for f in sorted(root.rglob('*.py'))}
        (root / 'verification.json').write_text(json.dumps(numeric, indent=2) + '\n')
        print(json.dumps({k: v for k, v in numeric.items() if k != 'code_hashes'}), flush=True)
    finally:
        p.stdin.close()
        try: p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.kill(); p.wait()

if __name__ == '__main__': main()
