"""Offline-first delta replay; execution is explicit, bounded, durable and never retried."""
import argparse
from decimal import Decimal, ROUND_CEILING
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('v2_replay_common', ROOT / 'replay_common.py')
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
MODEL = 'gpt-6.1-sol'
CAP = 2500000
MICRO = 1000000


def identity(record):
    job, index = record.get('job_id'), record.get('call_index')
    if not isinstance(job, str) or not job or type(index) is not int or index < 0:
        raise ValueError('Invalid identity')
    expected = f'{job}:{index}:delta-v2'
    if record.get('replay_id') != expected:
        raise ValueError('Invalid identity')
    return expected


def build_request(record):
    identity(record)
    source = record['request_json']
    if not isinstance(source.get('prompt'), str) or not isinstance(source.get('schema'), dict):
        raise ValueError('Explicit prompt/schema required')
    common.validate_schema_structure(source['schema'])
    cap = record.get('max_output_tokens', source.get('max_tokens'))
    reference_cap = record.get('reference_request_json', {}).get('max_tokens')
    if type(reference_cap) is not int or reference_cap < 1:
        raise ValueError('Missing reference output cap')
    if (type(cap) is not int or cap != max(reference_cap, 16000) or cap > 128000
            or source.get('max_tokens') != cap):
        raise ValueError('Invalid output cap')
    return {'model': MODEL, 'input': [{'role': 'user', 'content': source['prompt']}],
            'reasoning': {'effort': 'medium'}, 'truncation': 'disabled',
            'service_tier': 'default', 'text': {'format': {'type': 'json_schema',
            'name': 'compact_delta_v2', 'strict': True, 'schema': source['schema']}},
            'max_output_tokens': cap, 'store': False, 'stream': True,
            'prompt_cache_options': {'mode': 'explicit'}}


def estimate(record, payload=None):
    payload = payload or build_request(record)
    n = len(payload['input'][0]['content'].encode('utf-8')) + len(json.dumps(
        payload['text']['format']['schema'], ensure_ascii=False).encode('utf-8')) + 4096
    usage = record.get('reference_usage', {})
    reference = usage.get('input_tokens', usage.get('in_tok', 0))
    declared = record.get('input_tokens_estimate', 0)
    if any(type(v) is not int or v < 0 for v in (reference, declared)):
        raise ValueError('Invalid input estimate')
    reference_request = record.get('reference_request_json')
    method = 'absolute_utf8_upper_proxy'
    if reference_request is not None:
        if (not isinstance(reference_request, dict) or not isinstance(reference_request.get('prompt'), str)
                or not isinstance(reference_request.get('schema'), dict) or reference <= 0):
            raise ValueError('Invalid observed-input anchor')
        original_prompt_bytes = len(reference_request['prompt'].encode('utf-8'))
        original_schema_bytes = len(json.dumps(reference_request['schema'], ensure_ascii=False).encode('utf-8'))
        new_prompt_bytes = len(payload['input'][0]['content'].encode('utf-8'))
        new_schema_bytes = len(json.dumps(payload['text']['format']['schema'], ensure_ascii=False).encode('utf-8'))
        # Observation-anchored proxy: recorded actual input + nonnegative byte deltas.
        # 4096 protects framing variation; this is not a tokenizer guarantee.
        n = reference + max(0, new_prompt_bytes-original_prompt_bytes) + max(0, new_schema_bytes-original_schema_bytes) + 4096
        method = 'observed_reference_plus_positive_utf8_deltas'
    n = max(n, reference, declared)
    cost = int((Decimal(n) * Decimal('2.5') + payload['max_output_tokens'] * 10).to_integral_value(rounding=ROUND_CEILING))
    return {'estimate_method': method, 'reserved_input_tokens': n, 'reserved_output_tokens': payload['max_output_tokens'],
            'reserved_micro_usd': cost}


def prior_state(events):
    """An unclosed reservation or unknown usage prevents further paid calls."""
    pending, done, actual, unknown = {}, set(), 0, False
    for event in events:
        rid = identity(event)
        phase = event.get('record_type')
        if phase == 'reservation':
            amount = event.get('reserved_micro_usd')
            if rid in pending or rid in done or type(amount) is not int or amount <= 0:
                raise ValueError('Invalid reservation ledger')
            pending[rid] = amount
        elif phase == 'attempt':
            if rid not in pending or rid in done:
                raise ValueError('Unreserved attempt')
            amount = event.get('actual_micro_usd')
            if amount is None:
                unknown = True
                actual += pending[rid]
            elif type(amount) is not int or amount < 0:
                raise ValueError('Invalid usage cost')
            else:
                actual += amount
            pending.pop(rid)
            done.add(rid)
        else:
            raise ValueError('Unknown ledger event')
    return {'done': done | set(pending), 'spent': actual + sum(pending.values()),
            'blocked': unknown or bool(pending)}


def replay(records, max_micro_usd=CAP, transport=None, writer=None, previous=()):
    if type(max_micro_usd) is not int or not 0 < max_micro_usd <= CAP:
        raise ValueError('Budget must be <= 2.50 USD')
    if transport is not None and writer is None:
        raise ValueError('Durable writer required')
    records = list(records)
    ids = [identity(r) for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate identity')
    state = prior_state(previous)
    plans = [(r, build_request(r)) for r in records if identity(r) not in state['done']]
    reserve_total = sum(estimate(r, p)['reserved_micro_usd'] for r, p in plans)
    summary = {'calls': 0, 'candidates': len(plans), 'attempts': 0, 'skipped': len(records) - len(plans),
               'reserved_micro_usd': reserve_total, 'ceiling_micro_usd': max_micro_usd, 'previous_micro_usd': state['spent'],
               'actual_micro_usd': 0, 'failed': 0, 'blocked': int(state['blocked']),
               'execute': int(transport is not None), 'stopped': 'end'}
    if state['blocked']:
        summary['stopped'] = 'uncertain_budget'
        return summary
    if state['spent'] + reserve_total > max_micro_usd:
        summary.update(blocked=1, stopped='estimated_budget')
        return summary
    for record, payload in plans:
        summary['calls'] += 1
        if transport is None:
            continue
        predicted = estimate(record, payload)['reserved_micro_usd']
        current = state['spent'] + summary['actual_micro_usd']
        if current + predicted > max_micro_usd:
            summary.update(blocked=1, stopped='actual_budget')
            break
        base = {k: record[k] for k in ('job_id', 'call_index', 'replay_id')}
        writer(dict(base, record_type='reservation', reserved_micro_usd=predicted))
        # The reservation is durable before transport. Interrupted calls stay blocked.
        try:
            raw_result = transport(payload)
        except Exception:
            raw_result = {'raw_response': '', 'transport_error': 'transport exception'}
        raw = raw_result.get('raw_response', '')
        body, stream_error = common.response_body(raw)
        text = common.answer_text(body)
        usage = body.get('usage', {}) if isinstance(body, dict) else {}
        valid_model = isinstance(body, dict) and body.get('model') == MODEL and body.get('service_tier') == 'default'
        cost = common.usage_micro_usd(usage, MODEL) if valid_model else None
        content_error = common.content_error(body, text, payload)
        status = 'ok'
        http = raw_result.get('http_status')
        if raw_result.get('transport_error') or stream_error or content_error or type(http) is not int or not 200 <= http < 300:
            status = 'error'
            summary['failed'] += 1
        result = dict(base, record_type='attempt', status=status, raw_response=raw,
                      response=body, text=text, usage=usage, actual_micro_usd=cost,
                      reserved_micro_usd=predicted, transport=raw_result,
                      content_error=content_error, stream_error=stream_error)
        writer(result)
        summary['attempts'] += 1
        if cost is None:
            summary.update(blocked=1, stopped='uncertain_budget')
            break
        summary['actual_micro_usd'] += cost
    return summary


class StreamingTransport(common.OpenAITransport):
    """Raw stream is synced incrementally, even if the process is interrupted."""
    def __init__(self, path):
        super().__init__()
        self.path = path
    def __call__(self, payload):
        import urllib.request
        import urllib.error
        import http.client
        import time
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        request = urllib.request.Request('https://api.openai.com/v1/responses',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json',
                     'Accept': 'text/event-stream'})
        chunks, status = [], None
        with self.path.open('x', encoding='utf-8') as rawfile:
            def retain(chunk):
                value = self.redact(chunk.decode('utf-8', 'replace'))
                chunks.append(value)
                rawfile.write(value)
                rawfile.flush()
                os.fsync(rawfile.fileno())
            try:
                deadline = time.monotonic() + 420
                with opener.open(request, timeout=60) as response:
                    status = response.status
                    for line in response:
                        retain(line)
                        if time.monotonic() > deadline:
                            raise TimeoutError()
                return {'http_status': status, 'raw_response': ''.join(chunks)}
            except urllib.error.HTTPError as error:
                status = error.code
                try:
                    while True:
                        chunk = error.read(65536)
                        if not chunk: break
                        retain(chunk)
                finally:
                    error.close()
                return {'http_status': status, 'raw_response': ''.join(chunks), 'http_error': 'HTTP failure'}
            except (OSError, TimeoutError, http.client.HTTPException) as error:
                if isinstance(error, http.client.IncompleteRead) and isinstance(error.partial, bytes):
                    retain(error.partial)
                return {'http_status': status, 'raw_response': ''.join(chunks), 'transport_error': type(error).__name__}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', default=str(ROOT / 'selected_requests.jsonl'))
    parser.add_argument('--max-usd', default='2.50')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    try:
        budget = Decimal(args.max_usd) * MICRO
        if not budget.is_finite() or budget != budget.to_integral_value() or not 0 < budget <= CAP:
            raise ValueError('Budget')
        records = list(common.read_jsonl(args.requests))
        ledger = ROOT / 'replay_ledger.jsonl'
        events = list(common.read_jsonl(ledger)) if ledger.exists() else []
        if not args.execute:
            summary = replay(records, int(budget), previous=events)
        else:
            lock = ROOT / 'replay.lock'
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                events = list(common.read_jsonl(ledger)) if ledger.exists() else []
                with ledger.open('a', encoding='utf-8') as handle:
                    def writer(value):
                        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
                        handle.flush()
                        os.fsync(handle.fileno())
                    attempts = sum(e.get('record_type') == 'reservation' for e in events)
                    def transport(payload):
                        nonlocal attempts
                        attempts += 1
                        return StreamingTransport(ROOT / f'raw-attempt-{attempts:03d}.sse')(payload)
                    summary = replay(records, int(budget), transport, writer, events)
            finally:
                os.close(descriptor)
                lock.unlink()
        print(json.dumps(summary, sort_keys=True))
        return 2 if summary['blocked'] else 1 if summary['failed'] else 0
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
        print('Replay stopped: invalid configuration or local I/O.', file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
