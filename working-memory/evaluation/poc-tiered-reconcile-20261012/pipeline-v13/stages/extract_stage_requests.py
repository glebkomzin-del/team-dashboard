"""Stream archived stage calls. No unpacking, provider access or content logging."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import os

ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('stage_common', ROOT / 'stage_common.py')
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
DEFAULT_ARCHIVE = Path.home() / 'Library/Application Support/Dashboard Job Backup/archives/dashboard-20261012T155114Z.tar.gz'


def object_value(value):
    return common.parse_json(value) if isinstance(value, str) else value


def detect_stage(request):
    """Gate markers first; exclude compact; extract needs extraction/observations.

    Marker matching uses full recorded prompt; schemas provide a structural
    guard when an observations instruction is used without the STUFE 1 marker.
    """
    prompt = request.get('prompt')
    if not isinstance(prompt, str):
        return None
    if 'Bereits geöffnete Original-IDs' in prompt:
        return None
    schema = request.get('schema')
    props = schema.get('properties', {}) if isinstance(schema, dict) else {}
    if 'Bestehende Arbeit:' in prompt and 'Kandidaten:' in prompt:
        return 'gate' if 'verdicts' in props else None
    if 'Kandidaten:' in prompt:
        return None
    schema = request.get('schema')
    observations_schema = isinstance(schema, dict) and 'observations' in schema.get('properties', {})
    if observations_schema and ('Extraktion' in prompt or 'STUFE 1:' in prompt or
            'Beobachtungen' in prompt):
        return 'extract'
    return None


def meeting_date(prompt):
    match = re.search(r'(?:^|\n)Datum: (\d{4}-\d{2}-\d{2})(?=\r?\n|$)', prompt)
    if not match:
        return None
    try:
        return datetime.date.fromisoformat(match.group(1)).isoformat()
    except ValueError:
        return None


def identity(record):
    key = (record.get('job_id'), record.get('call_index'))
    if not isinstance(key[0], str) or not key[0].strip() or type(key[1]) is not int or key[1] < 0:
        raise ValueError('Invalid call identity')
    return key


def extract_lines(lines, writer):
    counts = {'queue_lines': 0, 'call_records': 0, 'extract': 0, 'gate': 0,
              'unknown_dates': 0, 'unknown_references': 0, 'unknown_usage': 0,
              'unknown_reference_cost': 0}
    lengths = {stage: {'n': 0, 'sum': 0, 'max': 0} for stage in ('extract', 'gate')}
    marker_groups = {}
    seen = set()
    for line in lines:
        if not line.strip():
            continue
        counts['queue_lines'] += 1
        envelope = common.parse_json(line)
        if not isinstance(envelope, dict):
            raise ValueError('Invalid queue envelope')
        if envelope.get('kind') != 'call':
            continue
        counts['call_records'] += 1
        call = object_value(envelope.get('record_json'))
        if not isinstance(call, dict):
            raise ValueError('Invalid call object')
        request = object_value(call.get('request_json'))
        if not isinstance(request, dict):
            raise ValueError('Invalid request')
        prompt = request.get('prompt')
        if isinstance(prompt, str):
            flags = ''.join(str(int(marker in prompt)) for marker in (
                'Extraktion', 'STUFE 1:', 'Beobachtungen', 'Kandidaten:',
                'Bestehende Arbeit:', 'Bereits geöffnete Original-IDs'))
            marker_groups[flags] = marker_groups.get(flags, 0) + 1
        stage = detect_stage(request)
        if stage is None:
            continue
        key = identity(call)
        if key in seen:
            raise ValueError('Duplicate selected call')
        seen.add(key)
        response = object_value(call.get('response_json'))
        if response is None:
            response = {}
        if not isinstance(response, dict):
            raise ValueError('Invalid response')
        content = response.get('content', [])
        text = content[0].get('text') if isinstance(content, list) and content and isinstance(content[0], dict) else None
        if not isinstance(text, str):
            text = None
            counts['unknown_references'] += 1
        usage = response.get('usage')
        if not isinstance(usage, dict):
            usage = None
            counts['unknown_usage'] += 1
        cost = call.get('actual_micro_usd')
        if type(cost) is not int or cost < 0:
            cost = common.usage_micro_usd(usage, request.get('model'))
        if cost is None:
            counts['unknown_reference_cost'] += 1
        date = meeting_date(prompt)
        counts['unknown_dates'] += date is None
        row = {'job_id': key[0], 'call_index': key[1], 'stage': stage,
               'meeting_date': date, 'request_json': request,
               'reference_text': text, 'reference_usage': usage,
               'reference_micro_usd': cost,
               'reference_model': response.get('model'),
               'reference_stop_reason': response.get('stop_reason')}
        writer.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n')
        counts[stage] += 1
        stats = lengths[stage]
        stats['n'] += 1
        stats['sum'] += len(prompt)
        stats['max'] = max(stats['max'], len(prompt))
    return {'counts': counts, 'prompt_characters': {
        stage: {'count': stats['n'], 'mean': round(stats['sum'] / stats['n'], 3) if stats['n'] else None,
                'max': stats['max']} for stage, stats in lengths.items()},
        'marker_groups': marker_groups}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument('--queue', choices=['-'])
    parser.add_argument('--output', default=str(ROOT / 'stage_requests.jsonl'))
    parser.add_argument('--stats', default=str(ROOT / 'extraction-stats.json'))
    args = parser.parse_args(argv)
    process = None
    temporary = None
    output = None
    try:
        output = common.output_path(args.output)
        stats_path = common.output_path(args.stats)
        if output.exists() or stats_path.exists():
            raise ValueError('Output already exists')
        temporary = output.with_name('.' + output.name + '.tmp')
        if args.queue:
            lines = sys.stdin
        else:
            process = subprocess.Popen(['tar', '-xzOf', str(args.archive), 'canonical/queue.jsonl'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
            lines = process.stdout
        with temporary.open('x', encoding='utf-8') as writer:
            stats = extract_lines(lines, writer)
            writer.flush()
            os.fsync(writer.fileno())
        if process is not None and process.wait() != 0:
            raise ValueError('Archive stream failed')
        # No output on partial/failed archive stream; refuse overwrite.
        os.link(temporary, output)
        temporary.unlink()
        temporary = None
        with stats_path.open('x', encoding='utf-8') as writer:
            json.dump(stats, writer, indent=2)
            writer.write('\n')
        print(json.dumps(stats, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, UnicodeError):
        print('Extraction failed: invalid input or local I/O.', file=sys.stderr)
        return 1
    finally:
        if process is not None:
            if process.stdout:
                process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
