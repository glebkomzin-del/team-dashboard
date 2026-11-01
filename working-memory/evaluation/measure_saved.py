"""Reproduce costs and narrow regression checks from private captured results.

No API calls. These development checks are not an independent accuracy estimate.
Run from working-memory: python evaluation/measure_saved.py
"""
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory import connect, overview

ROOT = Path(__file__).resolve().parents[1]
RATES = {'claude-opus-5': (5, 25), 'claude-sonnet-5': (2, 10),
         'claude-sonnet-4-6': (3, 15), 'claude-haiku-4-5-20251001': (1, 5),
         'gpt-6-astra': (10, 50), 'gpt-5.6-terra': (2, 12), 'gpt-5.6-luna': (.2, 1.2)}

def cost(model, usage):
    if model not in RATES or not all(k in usage for k in ('input_tokens', 'output_tokens')):
        return None
    ip, op = RATES[model]
    if model.startswith('gpt-'):
        detail = usage.get('input_tokens_details', {})
        cached, written = detail.get('cached_tokens', 0), detail.get('cache_write_tokens', 0)
        value = (usage['input_tokens'] - cached - written) * ip + cached * .1 * ip + written * 1.25 * ip
    else:
        value = usage['input_tokens'] * ip + usage.get('cache_read_input_tokens', 0) * .1 * ip + usage.get('cache_creation_input_tokens', 0) * 1.25 * ip
    return round((value + usage['output_tokens'] * op) / 1_000_000, 6)

def measure():
    ledger, seen = [], set()
    for path in sorted((ROOT / '.local').glob('*.sqlite')):
        db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'").fetchone():
            db.close();continue
        for rid, model, usage, seconds, outcome in db.execute('SELECT id,model,usage_json,elapsed_seconds,outcome FROM runs'):
            if rid in seen or model not in RATES: continue
            seen.add(rid)
            ledger.append({'id': rid, 'artifact': path.name, 'model': model, 'outcome': outcome,
                           'seconds': seconds, 'estimated_usd': cost(model, json.loads(usage))})
        db.close()
    for path in sorted((ROOT / '.local/evaluation').glob('*.json')):
        data = json.loads(path.read_text())
        if data.get('model') not in RATES or data['id'] in seen: continue
        seen.add(data['id'])
        ledger.append({'id': data['id'], 'artifact': path.name, 'model': data['model'],
                       'outcome': data.get('stop_reason', data.get('status')), 'seconds': data.get('elapsed_seconds'),
                       'estimated_usd': cost(data['model'], data.get('usage', {}))})
    finance = connect(ROOT / '.local/finance-corrected-v4.sqlite')
    earlier, later = overview(finance, '2026-07-15'), overview(finance, '2026-07-20')
    long = connect(ROOT / '.local/long-corrected-v4.sqlite'); long_state = overview(long)
    checks = [
        {'case': 'finance-fx-no-personal-task', 'authority': 'user_confirmed', 'pass': len(earlier['personal']) == 0},
        {'case': 'finance-vo-idea-not-work', 'authority': 'user_confirmed',
         'pass': any(r['kind'] == 'idea' and any(c['id'] == 'finance-2026-07-15-vo-option' for c in r['data'].get('human_corrections', [])) and not r['data']['creates_work'] for r in earlier['knowledge'])},
        {'case': 'finance-invitation-open-before-meeting', 'authority': 'assistant_original_review', 'pass': len(earlier['waiting']) == 1 and len(earlier['completed']) == 0},
        {'case': 'finance-two-promises-and-completed-invitation', 'authority': 'assistant_original_review', 'pass': len(later['waiting']) == 2 and len(later['completed']) == 1},
        {'case': 'no-july20-source-in-july15-view', 'authority': 'deterministic', 'pass': all(r['event_date'] <= '2026-07-15' for r in earlier['knowledge'])},
        {'case': 'long-meeting-no-teams-availability-task', 'authority': 'assistant_original_review', 'pass': not long_state['personal']},
        {'case': 'long-meeting-access-done-three-other-promises', 'authority': 'assistant_original_review', 'pass': len(long_state['completed']) == 1 and len(long_state['waiting']) == 3},
    ]
    finance.close(); long.close()
    result = {'date': '2026-09-06', 'scope': 'Saved local development runs; remote n8n test adds USD 0.316295. Not a general precision/recall benchmark.',
              'estimated_local_usd_with_known_usage': round(sum(r['estimated_usd'] or 0 for r in ledger), 6),
              'calls_with_unknown_cost': sum(r['estimated_usd'] is None for r in ledger),
              'api_calls_recorded': len(ledger), 'checks': checks, 'ledger': ledger}
    (ROOT / 'evaluation/results-saved.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'ledger'}, ensure_ascii=False))
    if not all(c['pass'] for c in checks): raise SystemExit(1)

if __name__ == '__main__': measure()
