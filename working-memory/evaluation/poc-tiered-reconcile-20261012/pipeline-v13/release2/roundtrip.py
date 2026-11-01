"""Reproduce archived and live-normalized delta round trips, offline.

The archive records four expansion work_results values as {}, while the live
contract requires null. archive=True preserves that export projection exactly;
separate live checks replace only that value with null. One error-only record is
accounted for, never treated as a successful call. Output contains counts only.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from local_support import configure
configure()
from delta_codec import equal, to_delta, from_delta

DEFAULT_SOURCE = Path('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/compact_calls.jsonl')


def run(source):
    counts = dict(lines=0, calls=0, passed=0, finals=0, archived_expansions=0,
                  live_expansions_passed=0, error_records=0, failed=0)
    with Path(source).open(encoding='utf-8') as stream:
        for line in stream:
            counts['lines'] += 1
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError('Invalid record')
                if 'obs_out' not in record:
                    if set(record) != {'call_index', 'error', 'job_id'}:
                        raise ValueError('Unknown non-call record')
                    counts['error_records'] += 1
                    continue
                counts['calls'] += 1
                full = {'observations': record['obs_out'],
                        'work_results': record['work_results'],
                        'open_ids': record['open_ids']}
                obs, work = record['obs_in'], record['work']
                if full['open_ids']:
                    counts['archived_expansions'] += 1
                else:
                    counts['finals'] += 1
                delta = to_delta(full, obs, work, archive=True)
                if not equal(full, from_delta(delta, obs, work, archive=True)):
                    raise ValueError('Archived round-trip mismatch')
                counts['passed'] += 1
                if full['open_ids']:
                    live = dict(full, work_results=None)
                    if not equal(live, from_delta(to_delta(live, obs, work), obs, work)):
                        raise ValueError('Live round-trip mismatch')
                    counts['live_expansions_passed'] += 1
            except Exception:
                counts['failed'] += 1
    return counts


def main():
    try:
        if len(sys.argv) > 2:
            raise ValueError('One optional input path expected')
        counts = run(Path(sys.argv[1]) if len(sys.argv) == 2 else DEFAULT_SOURCE)
    except Exception:
        print(json.dumps({'failed': 1}, sort_keys=True))
        return 1
    print(json.dumps(counts, sort_keys=True))
    expected = dict(lines=41, calls=40, passed=40, finals=36,
                    archived_expansions=4, live_expansions_passed=4,
                    error_records=1, failed=0)
    return 0 if counts == expected else 1


if __name__ == '__main__':
    raise SystemExit(main())
