"""Run the same original-meeting test against Anthropic; private evidence stays ignored."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent

def run(model, meeting_id):
    meeting = json.loads((ROOT / '.local/evidence' / f'meeting-{meeting_id}.json').read_text())
    keys = json.loads((ROOT / '.local/model-keys.json').read_text())
    prompt = (ROOT / 'evaluation/prompt-v1.txt').read_text() + '\n\nMeeting: ' + meeting['title'] + '\nDatum: ' + meeting['meeting_date'][:10] + '\nBestehende Vorgänge: [] (isolierter Extraktionstest ohne Archivkontext)\nOriginaltranskript:\n' + meeting['raw_transcript']
    payload = {'model': model, 'max_tokens': 12000, 'messages': [{'role': 'user', 'content': prompt}],
               'output_config': {'format': {'type': 'json_schema', 'schema': json.loads((ROOT / 'evaluation/schema-v1.json').read_text())}}}
    if model in ('claude-sonnet-5', 'claude-opus-5'):
        payload['thinking'] = {'type': 'disabled'}
    request = urllib.request.Request('https://api.anthropic.com/v1/messages', data=json.dumps(payload).encode(),
        headers={'x-api-key': keys['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
        result['elapsed_seconds'] = round(time.time() - started, 3)
    except urllib.error.HTTPError as e:
        result = {'error': 'Anthropic HTTP error', 'status': e.code, 'elapsed_seconds': round(time.time()-started, 3)}
    except Exception as e:
        result = {'error': type(e).__name__, 'elapsed_seconds': round(time.time()-started, 3)}
    target = ROOT / '.local/evaluation' / f'{meeting_id}-{model}.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'model': model, 'elapsed_seconds': result['elapsed_seconds'], 'usage': result.get('usage'), 'error':result.get('error'), 'stop_reason':result.get('stop_reason')}, ensure_ascii=False), flush=True)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--meeting', default='7c5f29e8-0141-4cb0-b2a3-711472b58898')
    parser.add_argument('--models', nargs='+', default=['claude-haiku-4-5-20251001', 'claude-sonnet-5', 'claude-opus-5', 'claude-sonnet-4-6'])
    args = parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda model: run(model, args.meeting), args.models))
