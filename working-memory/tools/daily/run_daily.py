#!/usr/bin/env python3
"""M5 local daily milestone. Stdlib, offline, private outputs; no delivery."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date, timedelta, datetime
import importlib.util
import io
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import tarfile
import tempfile
import time
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
VERSION = 'daily-v1'
VERSIONS = {'daily': VERSION, 'reminders': 'import-build_digest',
            'relevance': 'import-score/config.json', 'handover': 'import-build_package/render_package'}
CTX = multiprocessing.get_context('fork')
SNAPSHOT_FIELDS = ('id', 'title', 'claim', 'owner', 'status', 'due_text', 'due_date',
                   'due_reference_date', 'condition_text', 'matter', 'matter_id',
                   'first_changed', 'last_changed', 'source_id', 'source_title', 'source_date')


def load_module(name, relative):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HERE.parent / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def modules():
    return (load_module('daily_reminders', 'reminders/reminders.py'),
            load_module('daily_relevance', 'relevance/relevance.py'),
            load_module('daily_handover', 'handover/handover.py'))


def latest_archive(folder=None):
    folder = Path(folder) if folder else Path.home() / 'Library/Application Support/Dashboard Job Backup/archives'
    archives = sorted(p for p in folder.glob('dashboard-*.tar.gz') if p.is_file() and not p.is_symlink())
    if not archives:
        raise FileNotFoundError('E_NO_ARCHIVE')
    return archives[-1]


def output_path(path):
    path = Path(path).expanduser().resolve()
    if path == HERE or not path.is_relative_to(HERE):
        raise ValueError('E_OUTPUT_BOUNDARY')
    return path


def atomic_write(path, text):
    path = output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.daily-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')


def stream_archive(archive):
    """Single sequential gzip scan; no extraction, external tar, or disk projection."""
    seen = set()
    with tarfile.open(archive, 'r|gz') as stream:
        for member in stream:
            if member.name not in ('canonical/journal.jsonl', 'canonical/notes.jsonl', 'canonical/documents.jsonl'):
                continue
            if not member.isfile() or member.name in seen:
                raise ValueError('E_ARCHIVE_MEMBER')
            seen.add(member.name)
            handle = stream.extractfile(member)
            sequence = 0
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                if len(line) > 128 * 1024 * 1024:
                    raise ValueError('E_RECORD_LIMIT')
                outer = json.loads(line)
                if not isinstance(outer, dict):
                    raise ValueError('E_JSONL')
                if 'record_json' in outer:
                    raw = outer['record_json']
                    if not isinstance(raw, str):
                        raise ValueError('E_JSONL')
                    # Canonical envelope integrity is the archive's own contract,
                    # not an outside-directory unchanged proof.
                    if 'record_hash' in outer:
                        import hashlib
                        if hashlib.sha256(raw.encode()).hexdigest() != outer['record_hash']:
                            raise ValueError('E_RECORD_INTEGRITY')
                    if 'sequence' in outer:
                        if type(outer['sequence']) is not int or outer['sequence'] != sequence + 1:
                            raise ValueError('E_SEQUENCE')
                        sequence = outer['sequence']
                    row = json.loads(raw)
                else:
                    row = outer
                if not isinstance(row, dict):
                    raise ValueError('E_JSONL')
                yield member.name, row, f'{archive.name}/{member.name}:L{number}'
            handle.close()
    if len(seen) != 3:
        raise ValueError('E_ARCHIVE_MEMBER')


def project(archive, today):
    """Preserve handover's projection and source-address contract in one stream."""
    reminders, relevance, handover = modules()
    replay, backend, planner = handover._backend()
    from canonical_archive import verify_document, verify_note
    memory = handover.Memory(archive=archive.name)
    journal = []
    latest_generation = None
    source_after, human_after = set(), set()
    for member, row, address in stream_archive(archive):
        if member.endswith('/journal.jsonl'):
            if type(row.get('revision')) is not int or row['revision'] != memory.revision + 1:
                raise ValueError('E_REVISION')
            memory.revision = row['revision']
            memory.snapshot_address = address
            journal.append(row)
            if row['kind'] == 'source':
                memory.source_addresses[row['source']['id']] = address
                source_after.add(row['source']['id'])
            elif row['kind'] == 'human':
                memory.command_addresses[row['command_id']] = address
                human_after.add(row['command_id'])
            elif row['kind'] in ('generation', 'redaction'):
                latest_generation = address
                source_after.clear(); human_after.clear()
            else:
                raise ValueError('E_JOURNAL_KIND')
        else:
            verify = verify_note if member.endswith('/notes.jsonl') else verify_document
            verified = verify(row)
            verified.pop('export', None)
            target = memory.notes if member.endswith('/notes.jsonl') else memory.documents
            target.append({**verified, '_address': address})
    if not journal:
        raise ValueError('E_EMPTY_JOURNAL')
    memory.logical_entries = replay.logical_entries(journal)
    if latest_generation:
        for entry in memory.logical_entries:
            if entry['kind'] == 'source' and entry['source']['id'] not in source_after:
                memory.source_addresses[entry['source']['id']] = latest_generation
            if entry['kind'] == 'human' and entry['command_id'] not in human_after:
                memory.command_addresses[entry['command_id']] = latest_generation
    memory.db, _ = replay.materialize(memory.logical_entries)
    state = planner.overlay(memory.db, backend.overview(memory.db, as_of=today), today)
    memory.tasks = [item for group in replay.GROUPS for item in state.get(group, [])]
    if len({t['id'] for t in memory.tasks}) != len(memory.tasks):
        raise ValueError('E_DUPLICATE_TASK')
    # Adapt canonical read-model fields to the reminders helper's established
    # relative-date/source contract, using that helper's projection in RAM.
    reminder_tasks = {t['id']: t for t in reminders.reconstruct_tasks(journal, notes=memory.notes, today=date.fromisoformat(today))}
    tasks = []
    for task in memory.tasks:
        item = dict(task)
        extra = reminder_tasks.get(task['id'], {})
        for field in ('due_reference_date', 'first_changed', 'source_title', 'source_date', 'source_id'):
            item[field] = extra.get(field)
        item.setdefault('title', '')
        tasks.append(item)
    memory.tasks = tasks
    candidates = []
    identities = {t['id'] for t in tasks}
    for entry in state.get('knowledge', []):
        data = entry.get('data') or {}
        if data.get('kind') != 'commitment' or entry.get('id') in identities or data.get('update_target') in identities:
            continue
        candidates.append({**data, 'id': entry['id'], 'matter_id': entry.get('matter_id'),
                           'last_changed': entry.get('event_date'),
                           'status': 'rejected' if data.get('knowledge_status') == 'rejected' else 'candidate',
                           'history': [{'source_id': entry.get('source_id'), 'event_date': entry.get('event_date'), 'action': 'proposed'}]})
    return memory, candidates


def compact_tasks(tasks):
    return [{key: task.get(key) for key in SNAPSHOT_FIELDS} for task in tasks]


def execute_step(memory, candidates, today, name, payload):
    reminders, relevance, handover = modules()
    if name == 'reminders':
        result = reminders.build_digest(memory.tasks, date.fromisoformat(today), 'Gleb', payload)
        return {'text': result.text, 'state': result.state, 'counts': result.counts,
                'shown': result.shown, 'omitted': result.omitted}
    if name == 'relevance':
        config = relevance.load_config()
        context = {'config': config, 'as_of': today, 'topics': relevance._topic_context(memory.tasks)}
        rows = []
        for kind, tasks in (('task', memory.tasks), ('candidate', candidates)):
            for task in tasks:
                rows.append({'id': task['id'], 'as_of': today, **relevance.score(task, context),
                             'status': task.get('status'), 'has_due': bool(task.get('due_text') or task.get('due_date')),
                             'record_type': kind})
        return {'rows': rows, 'config': config}
    if name == 'handover':
        selected = set(payload)
        texts = []
        for identity in payload:
            task = next(task for task in memory.tasks if task['id'] == identity)
            text = handover.render_package(handover.build_package(memory, task))
            stats = {'lines': len(text.splitlines()), 'bytes': len(text.encode()),
                     'longest_line': max(map(len, text.splitlines()), default=0)}
            if stats['lines'] > 150 or stats['bytes'] > 20000 or stats['longest_line'] > 400:
                raise ValueError('E_PACKAGE_LIMIT')
            texts.append({'id': identity, 'text': text, **stats})
        return {'packages': texts}
    raise ValueError('E_STEP')


def _call_child(connection, function, args):
    # Never expose imported helper output, tracebacks, identities, or payloads.
    with open(os.devnull, 'w') as sink:
        from contextlib import redirect_stdout, redirect_stderr
        with redirect_stdout(sink), redirect_stderr(sink):
            try:
                connection.send({'status': 'ok', 'value': function(*args)})
            except BaseException as error:
                connection.send({'status': 'error', 'error': type(error).__name__})
    connection.close()


def bounded_call(function, args, timeout):
    started = time.monotonic()
    parent, child = CTX.Pipe(duplex=False)
    process = CTX.Process(target=_call_child, args=(child, function, args))
    process.start(); child.close()
    try:
        if not parent.poll(timeout):
            result = {'status': 'timeout', 'error': 'E_STEP_TIMEOUT'}
        else:
            try:
                result = parent.recv()
            except EOFError:
                result = {'status': 'error', 'error': 'E_STEP_PROCESS'}
    finally:
        if process.is_alive():
            process.terminate()
        process.join(1)
        if process.is_alive():
            process.kill(); process.join()
        parent.close()
    result['seconds'] = round(time.monotonic() - started, 6)
    return result


def _session_worker(connection, archive, today):
    def stop_worker(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_worker)
    try:
        memory, candidates = project(Path(archive), today)
        connection.send({'status': 'ok', 'value': {'tasks': compact_tasks(memory.tasks),
                         'candidate_count': len(candidates), 'revision': memory.revision}})
        while True:
            name, payload, timeout = connection.recv()
            if name == 'stop':
                break
            connection.send(bounded_call(execute_step, (memory, candidates, today, name, payload), timeout))
    except BaseException as error:
        try:
            connection.send({'status': 'error', 'error': type(error).__name__})
        except (BrokenPipeError, EOFError):
            pass
    finally:
        if 'memory' in locals() and memory.db:
            memory.db.close()
        connection.close()


class Session:
    """One RAM projection; deadline terminates archive reader; bounded children are cleaned up."""
    def __init__(self, archive, today):
        self.connection, child = CTX.Pipe()
        self.process = CTX.Process(target=_session_worker, args=(child, str(archive), today))
        self.started = time.monotonic()
        self.process.start(); child.close()
        self.alive = True

    def _receive(self, timeout):
        if self.connection.poll(timeout):
            try:
                return self.connection.recv()
            except EOFError:
                return {'status': 'error', 'error': 'E_STEP_PROCESS'}
        self.close()
        return {'status': 'timeout', 'error': 'E_STEP_TIMEOUT'}

    def initial(self, timeout):
        result = self._receive(timeout)
        result['seconds'] = round(time.monotonic() - self.started, 6)
        return result

    def step(self, name, payload, timeout):
        if not self.alive or not self.process.is_alive():
            return {'status': 'skipped', 'error': 'E_PROJECTION_UNAVAILABLE', 'seconds': 0}
        self.connection.send((name, payload, timeout))
        # Inner step process owns the exact deadline; the outer margin only
        # catches a broken protocol/cleanup, never extends its execution budget.
        return self._receive(timeout + 3)

    def close(self):
        if not self.alive:
            return
        self.alive = False
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join()
        self.connection.close()


def due_and_stall(task, today):
    reminders = modules()[0]
    direct = reminders.as_date(task.get('due_date'))
    due = direct or reminders.parse_due(task.get('due_text'), task.get('due_reference_date')).value
    stalled = 'stalled' in reminders.rule_matches(task, today, 'Gleb')
    return due, stalled


def changed_tasks(tasks, previous):
    prior = {t['id']: t for t in previous}
    new = [t['id'] for t in tasks if t['id'] not in prior]
    changed = [t['id'] for t in tasks if t['id'] in prior and t != prior[t['id']]]
    return new, changed


def select_packages(tasks, rows, changed, today):
    classes = {r['id']: r['klasse'] for r in rows if r['record_type'] == 'task'}
    selected, evidence = [], Counter()
    for task in tasks:
        if task['id'] not in changed:
            evidence['unchanged'] += 1; continue
        if task.get('status') not in ('open', 'waiting'):
            evidence['not_open'] += 1; continue
        if classes.get(task['id']) != 'wichtig':
            evidence['unknown_class' if task['id'] not in classes else 'not_important'] += 1; continue
        due, stalled = due_and_stall(task, today)
        if (due is not None and due <= today + timedelta(days=14)) or stalled:
            selected.append((due or date.max, task['id']))
            evidence['eligible'] += 1
        else:
            evidence['unknown_due_or_stall' if due is None else 'outside_window'] += 1
    selected.sort()
    evidence['limited'] = max(0, len(selected) - 5)
    return [identity for _, identity in selected[:5]], dict(evidence)


def overview(tasks, rows, new, changed, packages, today, failed):
    counts = Counter(r['klasse'] for r in rows or [] if r['record_type'] == 'task')
    lines = [f'# Tagesübersicht · {today}', '',
             'Klassen: ' + ', '.join(f'{name}={counts[name]}' for name in ('wichtig', 'standard', 'kleinigkeit')) if rows is not None else 'Klassen: unbekannt',
             f'Aufgaben: {len(tasks)} · neu: {len(new)} · geändert: {len(changed)}',
             f'Fehlgeschlagene Schritte: {failed}', '']
    important = {r['id'] for r in rows or [] if r.get('record_type') == 'task' and r.get('klasse') == 'wichtig'}
    overdue = 0; top = []
    for task in tasks:
        if task.get('status') not in ('open', 'waiting'):
            continue
        due, stalled = due_and_stall(task, today)
        overdue += int(due is not None and due < today)
        if task['id'] in important and (due is not None or stalled):
            top.append((due or date.max, task['id'], task, stalled))
    lines.extend([f'Überfällig: {overdue}', '', '## Top 10 wichtig · Frist / Stillstand'])
    for due, _, task, stalled in sorted(top)[:10]:
        title = modules()[0]._short(task.get('title') or 'unbekannt', 160)
        lines.append(f'- {title} · {due if due != date.max else "Frist unbekannt"} · Stillstand: {"ja" if stalled else "nein"}')
    if not top:
        lines.append('Keine ausgewählten Aufgaben.' if rows is not None else 'Relevanz nicht bestimmbar.')
    lines.extend(['', '## Neue / geänderte Aufgaben'])
    changes = set(new + changed)
    for task in [t for t in tasks if t['id'] in changes][:20]:
        lines.append(f'- {"neu" if task["id"] in new else "geändert"}: {modules()[0]._short(task.get("title"), 160)}')
    if len(changes) > 20:
        lines.append(f'Weitere neue/geänderte Aufgaben: {len(changes) - 20}; vollständige IDs in run.json.')
    lines.extend(['', '## Pakete'])
    for number, package in enumerate(packages, 1):
        lines.append(f'- [Paket {number:02d}](pakete/paket-{number:02d}.md)')
    if not packages:
        lines.append('Keine Pakete erzeugt.')
    text = '\n'.join(lines) + '\n'
    if len(text.splitlines()) > 60:
        raise ValueError('E_OVERVIEW_LIMIT')
    return text


def delivery(digest, today):
    return {'subject': f'Arbeits-Memory · {today}',
            'email_body': digest if len(digest) <= 3000 else digest[:2999] + '…',
            'push': f'Arbeits-Memory · {today}: Der lokale Tagesdigest ist vorbereitet.'[:140],
            'mode': 'draft-only', 'sent': False}


def load_state(path):
    if not path.exists():
        return {'version': 1, 'last_success': None, 'tasks': [],
                'reminders': {'version': 1, 'last_sent': {}}}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('tasks'), list):
        raise ValueError('E_STATE')
    modules()[0].validate_state(value['reminders'])
    return value


def _record_step(run, name, result):
    run['steps'][name] = {k: v for k, v in result.items() if k != 'value'}
    return result.get('value') if result['status'] == 'ok' else None


def run_daily(today, out, archive=None, step_timeout=600, session_factory=Session, state_path=None):
    started = time.monotonic()
    today = date.fromisoformat(today).isoformat()
    if not isinstance(step_timeout, (int, float)) or not 0 < step_timeout <= 86400:
        raise ValueError('E_TIMEOUT')
    out = output_path(out)
    state_path = output_path(state_path or HERE / 'state.json')
    archive = Path(archive).expanduser().resolve() if archive else latest_archive()
    if not archive.is_file():
        raise FileNotFoundError('E_NO_ARCHIVE')
    info = archive.stat()
    identity = {'name': archive.name, 'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}
    state = load_state(state_path)
    last = state.get('last_success')
    if last and last.get('archive') == identity:
        prior_out = output_path(last['out'])
        required = last.get('artifacts', [])
        # Skip requires a positive completed receipt plus every stored artifact.
        if required and all(output_path(prior_out / item).is_file() for item in required):
            return {'exit_code': 0, 'cached': True, 'reason': 'E_NO_NEW_ARCHIVE',
                    'out': str(prior_out), 'tasks': len(state['tasks'])}
    run = {'version': VERSION, 'date': today, 'archive': archive.name, 'versions': VERSIONS,
           'steps': {}, 'status': 'running', 'cached': False, 'step_timeout_seconds': step_timeout}
    artifacts = []
    def save(name, text):
        atomic_write(out / name, text); artifacts.append(name)
    session = session_factory(archive, today)
    tasks = []; rows = None; packages = []; digest_result = None
    new = []; changed = []
    try:
        projection = _record_step(run, 'archive', session.initial(step_timeout))
        if projection is not None:
            tasks = projection['tasks']
            run['candidate_count'] = projection['candidate_count']
            run['revision'] = projection['revision']
            new, changed = changed_tasks(tasks, state['tasks'])
            digest_result = _record_step(run, 'reminders', session.step('reminders', state['reminders'], step_timeout))
            if digest_result is not None:
                try:
                    save('digest.md', digest_result['text'])
                    run['reminder_counts'] = digest_result['counts']
                    run['digest_entry_count'] = digest_result['shown']
                except Exception as error:
                    run['steps']['reminders'] = {'status': 'error', 'error': type(error).__name__, 'seconds': run['steps']['reminders']['seconds']}
                    digest_result = None
            relevance_result = _record_step(run, 'relevance', session.step('relevance', None, step_timeout))
            if relevance_result is not None:
                rows = relevance_result['rows']
                try:
                    save('relevance.jsonl', ''.join(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n' for r in rows))
                except Exception as error:
                    run['steps']['relevance']['status'] = 'error'
                    run['steps']['relevance']['error'] = type(error).__name__
                    rows = None
            if rows is not None:
                identities, evidence = select_packages(tasks, rows, set(new + changed), date.fromisoformat(today))
                run['package_selection'] = evidence
                generated = _record_step(run, 'handover', session.step('handover', identities, step_timeout))
                if generated is not None:
                    try:
                        for number, package in enumerate(generated['packages'], 1):
                            save(f'pakete/paket-{number:02d}.md', package['text'])
                            packages.append({k: v for k, v in package.items() if k != 'text'})
                    except Exception as error:
                        run['steps']['handover']['status'] = 'error'
                        run['steps']['handover']['error'] = type(error).__name__
            else:
                run['steps']['handover'] = {'status': 'skipped', 'error': 'E_RELEVANCE_UNAVAILABLE', 'seconds': 0}
        else:
            for name in ('reminders', 'relevance', 'handover'):
                run['steps'][name] = {'status': 'skipped', 'error': 'E_PROJECTION_UNAVAILABLE', 'seconds': 0}
    finally:
        session.close()
    run.update(task_count=len(tasks), new_task_ids=new, changed_task_ids=changed, packages=packages,
               class_counts=dict(Counter(r['klasse'] for r in rows or [] if r['record_type'] == 'task')))
    # Independent local formatting steps also have actual execution deadlines.
    failed = sum(s['status'] != 'ok' for s in run['steps'].values())
    result = bounded_call(overview, (tasks, rows, new, changed, packages, date.fromisoformat(today), failed), step_timeout)
    text = _record_step(run, 'overview', result)
    if text is not None:
        try:
            save('uebersicht.md', text)
        except Exception as error:
            run['steps']['overview']['status'] = 'error'
            run['steps']['overview']['error'] = type(error).__name__
    if digest_result is not None:
        result = bounded_call(delivery, (digest_result['text'], today), step_timeout)
        value = _record_step(run, 'delivery', result)
        if value is not None:
            try:
                save('delivery.json', json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            except Exception as error:
                run['steps']['delivery']['status'] = 'error'
                run['steps']['delivery']['error'] = type(error).__name__
    else:
        run['steps']['delivery'] = {'status': 'skipped', 'error': 'E_DIGEST_UNAVAILABLE', 'seconds': 0}
    # Reconcile only runner-owned filenames. A retry/new archive must never
    # present an older package/digest as a result of a failed current step.
    managed = ['digest.md', 'relevance.jsonl', 'uebersicht.md', 'delivery.json'] + [f'pakete/paket-{number:02d}.md' for number in range(1, 6)]
    for name in managed:
        if name not in artifacts:
            output_path(out / name).unlink(missing_ok=True)
    success = all(s['status'] == 'ok' for s in run['steps'].values())
    run['status'] = 'completed' if success else 'partial'
    run['output_artifacts'] = [*artifacts, 'run.json', 'state.json']
    run['total_seconds'] = round(time.monotonic() - started, 6)
    write_json(out / 'run.json', run)
    if success:
        updated = {'version': 1, 'last_run': {'date': today, 'archive': archive.name, 'status': 'completed'},
                   'last_success': {'date': today, 'archive': identity, 'out': str(out), 'artifacts': run['output_artifacts']},
                   'tasks': tasks, 'reminders': digest_result['state']}
        # Output receipt precedes shared state. A crash before shared replacement
        # permits a retry, never a false successful cache/cooldown advancement.
        write_json(out / 'state.json', updated)
        write_json(state_path, updated)
    else:
        failed_state = {**state, 'last_run': {'date': today, 'archive': archive.name, 'status': 'partial'}}
        write_json(out / 'state.json', failed_state)
        write_json(state_path, failed_state)
    # Total covers all computation and artifact/state commits up to the final
    # metrics receipt; an external process timer can include its final write.
    run['total_seconds'] = round(time.monotonic() - started, 6)
    write_json(out / 'run.json', run)
    return {'exit_code': 0 if success else 1, 'cached': False, 'out': str(out),
            'tasks': len(tasks), 'packages': len(packages), 'failed_steps': sum(s['status'] != 'ok' for s in run['steps'].values())}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline daily digest preparation; numeric stdout only')
    parser.add_argument('--date', default=datetime.now(ZoneInfo('Europe/Berlin')).date().isoformat())
    parser.add_argument('--out', type=Path)
    parser.add_argument('--archive', type=Path, help='optional explicit local archive (synthetic validation)')
    parser.add_argument('--step-timeout', type=float, default=600)
    args = parser.parse_args(argv)
    try:
        result = run_daily(args.date, args.out or HERE / 'out' / args.date, args.archive, args.step_timeout)
        # No output paths or task/archive payloads are printed.
        print(json.dumps({k: v for k, v in result.items() if k != 'out'}, sort_keys=True))
        return result['exit_code']
    except FileNotFoundError:
        print(json.dumps({'exit_code': 2, 'error': 'E_NO_ARCHIVE', 'archives': 0}))
        return 2
    except Exception as error:
        print(json.dumps({'exit_code': 1, 'error': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
