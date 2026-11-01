"""Offline by default. Only --execute constructs a credentialed transport."""
import argparse
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_CEILING

_spec = importlib.util.spec_from_file_location('replay_common', Path(__file__).with_name('replay_common.py'))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)


def build_request(record, model, service_tier='standard'):
    source = record['request_json']
    if model not in common.RATES or service_tier != 'standard':
        raise ValueError('Only priced models and standard tier supported')
    if not isinstance(source.get('prompt'), str) or not isinstance(source.get('schema'), dict):
        raise ValueError('Prompt and explicit schema required')
    allowance = source.get('max_tokens', 16000)
    if type(allowance) is not int or not 1 <= allowance <= 128000:
        raise ValueError('Invalid reference max_tokens')
    # openai_provider.py:149-154,194-208. Only explicit replay parameters change.
    return {'model': model, 'input': [{'role': 'user', 'content': source['prompt']}],
        'reasoning': {'effort': 'low'}, 'truncation': 'disabled', 'service_tier': 'default',
        'text': {'format': {'type': 'json_schema', 'name': 'meeting_result',
                          'strict': True, 'schema': source['schema']}},
        'max_output_tokens': max(16000, allowance), 'store': False, 'stream': True}


def estimate(payload):
    characters = len(payload['input'][0]['content']) + len(json.dumps(
        payload['text']['format']['schema'], ensure_ascii=False))
    input_tokens = int((Decimal(characters) / Decimal('3.6')).to_integral_value(rounding=ROUND_CEILING))
    output_tokens = payload['max_output_tokens']
    return {'characters': characters, 'estimated_input_tokens': input_tokens,
        'reserved_output_tokens': output_tokens,
        'estimated_micro_usd': common.usage_micro_usd(
            {'input_tokens': input_tokens, 'output_tokens': output_tokens}, payload['model'])}


def response_body(raw):
    """Parse retained raw SSE; terminal object is the provider's complete response."""
    try:
        body = common.parse_json(raw)
        if isinstance(body, dict):
            return body, None
    except ValueError:
        pass
    terminal = None
    error = None
    data = []
    def event(lines):
        nonlocal terminal, error
        if not lines or ''.join(lines).strip() == '[DONE]':
            return
        value = common.parse_json('\n'.join(lines))
        if not isinstance(value, dict):
            raise ValueError('Invalid SSE event')
        kind = value.get('type')
        if kind in ('response.completed', 'response.incomplete', 'response.failed'):
            if terminal is not None:
                raise ValueError('Duplicate terminal SSE event')
            terminal = value.get('response')
            if not isinstance(terminal, dict) or terminal.get('status') != kind.split('.')[1]:
                raise ValueError('Terminal SSE status mismatch')
        elif kind == 'error':
            error = value
    try:
        for line in raw.splitlines() + ['']:
            if line.startswith('data:'):
                data.append(line[5:].lstrip())
            elif not line:
                event(data)
                data = []
    except (ValueError, TypeError):
        return terminal, {'type': 'invalid_stream', 'message': 'Invalid SSE event stream'}
    if error is not None:
        return terminal, {'type': 'provider_stream_error', 'detail': error}
    if terminal is None:
        return None, {'type': 'incomplete_stream', 'message': 'No terminal response event'}
    return terminal, None


def answer_text(body):
    if not isinstance(body, dict):
        return None
    parts = []
    for item in body.get('output', []) if isinstance(body.get('output'), list) else []:
        if isinstance(item, dict) and item.get('type') == 'message':
            for block in item.get('content', []) if isinstance(item.get('content'), list) else []:
                if isinstance(block, dict) and block.get('type') == 'output_text' and isinstance(block.get('text'), str):
                    parts.append(block['text'])
    return ''.join(parts) if parts else None


def content_error(body, text, payload):
    if not isinstance(body, dict) or body.get('status') != 'completed':
        return 'Provider response not completed'
    if body.get('model') != payload['model']:
        return 'Unexpected provider model'
    if body.get('service_tier') != 'default':
        return 'Standard service tier not confirmed'
    messages = 0
    output = body.get('output')
    if not isinstance(output, list):
        return 'Missing output items'
    for item in output:
        if not isinstance(item, dict):
            return 'Invalid output item'
        if item.get('type') == 'reasoning':
            if item.get('status') not in (None, 'completed'):
                return 'Incomplete reasoning item'
            continue
        if item.get('type') != 'message' or item.get('role') != 'assistant' or item.get('status') != 'completed':
            return 'Invalid assistant message'
        messages += 1
        blocks = item.get('content')
        if not isinstance(blocks, list) or not blocks or any(
            not isinstance(b, dict) or b.get('type') != 'output_text' or not isinstance(b.get('text'), str)
            for b in blocks):
            return 'Refusal or invalid output content'
    if messages != 1 or text is None:
        return 'Missing structured output'
    try:
        value = common.parse_json(text)
    except (ValueError, TypeError):
        return 'Answer is not valid JSON'
    if common.schema_errors(value, payload['text']['format']['schema']):
        return 'Answer does not satisfy recorded schema'
    return None


class OpenAITransport:
    """Created solely by --execute; no credential files, no redirects."""
    def __init__(self):
        self.key = os.environ.get('OPENAI_API_KEY')
        if not self.key:
            raise ValueError('OPENAI_API_KEY environment variable missing')

    def redact(self, value):
        # Exceptional redaction takes precedence over raw-body fidelity.
        return value.replace(self.key, '[REDACTED_API_KEY]')

    def __call__(self, payload):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        request = urllib.request.Request('https://api.openai.com/v1/responses',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json',
                     'Accept': 'text/event-stream'})
        chunks = []
        status = None
        deadline = time.monotonic() + 420
        try:
            with opener.open(request, timeout=60) as response:
                status = response.status
                for line in response:
                    chunks.append(line)
                    if time.monotonic() > deadline:
                        raise TimeoutError('Total request deadline exceeded')
            return {'http_status': status, 'raw_response': self.redact(b''.join(chunks).decode('utf-8', 'replace'))}
        except urllib.error.HTTPError as error:
            error_chunks = []
            read_error = None
            try:
                while True:
                    chunk = error.read(65536)
                    if not chunk:
                        break
                    error_chunks.append(chunk)
            except (OSError, http.client.HTTPException) as reading_error:
                if isinstance(reading_error, http.client.IncompleteRead) and isinstance(reading_error.partial, bytes):
                    error_chunks.append(reading_error.partial)
                read_error = self.redact(str(reading_error))
            finally:
                error.close()
            raw = b''.join(error_chunks).decode('utf-8', 'replace')
            return {'http_status': error.code, 'raw_response': self.redact(raw),
                    'http_error': self.redact(str(error)), 'body_read_error': read_error}
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
            if isinstance(error, http.client.IncompleteRead) and isinstance(error.partial, bytes):
                chunks.append(error.partial)
            return {'http_status': status,
                'raw_response': self.redact(b''.join(chunks).decode('utf-8', 'replace')),
                'transport_error': self.redact(str(error)), 'exception_type': type(error).__name__}


def replay(records, model='gpt-6-luna', service_tier='standard', max_micro_usd=1500000,
           limit=None, transport=None, writer=None):
    """Injected transport is offline-testable. None means dry-run, always."""
    if type(max_micro_usd) is not int or max_micro_usd <= 0:
        raise ValueError('Positive budget required')
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError('Nonnegative limit required')
    if transport is not None and writer is None:
        raise ValueError('Execution requires a durable result writer')
    summary = {'mode': 'DRY-RUN' if transport is None else 'EXECUTE', 'calls': 0,
        'attempts': 0, 'estimated_micro_usd': 0, 'actual_micro_usd': 0,
        'unknown_cost_attempts': 0, 'budget_charged_micro_usd': 0,
        'error_attempts': 0, 'failed_calls': 0, 'stopped': 'end'}
    seen = set()
    for record in records:
        if limit is not None and summary['calls'] >= limit:
            summary['stopped'] = 'limit'
            break
        key = (record.get('job_id'), record.get('call_index'))
        if not isinstance(key[0], str) or not key[0] or type(key[1]) is not int or key[1] < 0 or key in seen:
            raise ValueError('Missing, invalid or duplicate call identity')
        seen.add(key)
        payload = build_request(record, model, service_tier)
        predicted = estimate(payload)
        cost = predicted['estimated_micro_usd']
        current = summary['estimated_micro_usd'] if transport is None else summary['budget_charged_micro_usd']
        if current + cost > max_micro_usd:
            summary['stopped'] = 'estimated_budget'
            break
        summary['calls'] += 1
        summary['estimated_micro_usd'] += cost
        if transport is None:
            print(json.dumps({'call_number': summary['calls'], **predicted}, sort_keys=True))
            continue
        for attempt in range(1, 4):  # initial call + at most two transport retries
            if summary['budget_charged_micro_usd'] + cost > max_micro_usd:
                summary['stopped'] = 'retry_budget'
                return summary
            started = time.monotonic()
            try:
                raw_result = transport(payload)
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
                raw_result = {'http_status': None, 'raw_response': '',
                    'transport_error': str(error), 'exception_type': type(error).__name__}
            raw = raw_result.get('raw_response', '')
            body, stream_error = response_body(raw)
            usage = body.get('usage', {}) if isinstance(body, dict) else {}
            text = answer_text(body)
            http_status = raw_result.get('http_status')
            error = None
            status = 'ok'
            if raw_result.get('transport_error') is not None:
                status = 'transport_error'
                error = {'type': raw_result.get('exception_type', 'transport'),
                         'message': raw_result['transport_error']}
            elif raw_result.get('http_error') is not None or type(http_status) is int and not 200 <= http_status < 300:
                status = 'http_error'
                error = {'type': 'http', 'message': raw_result.get('http_error', 'HTTP failure'),
                         'detail': body, 'body_read_error': raw_result.get('body_read_error')}
            elif stream_error:
                status, error = 'content_error', stream_error
            else:
                message = content_error(body, text, payload)
                if message:
                    status, error = 'content_error', {'type': 'content', 'message': message,
                        'provider_error': body.get('error') if isinstance(body, dict) else None}
            actual = common.usage_micro_usd(usage, model)
            if isinstance(body, dict) and (body.get('model') != model or body.get('service_tier') != 'default'):
                actual = None
            if actual is None:
                summary['unknown_cost_attempts'] += 1
            else:
                summary['actual_micro_usd'] += actual
            charged = actual if actual is not None else cost
            summary['budget_charged_micro_usd'] += charged
            summary['attempts'] += 1
            if status != 'ok':
                summary['error_attempts'] += 1
                if status != 'transport_error' or attempt == 3:
                    summary['failed_calls'] += 1
            result = {'record_type': 'attempt', 'job_id': key[0], 'call_index': key[1],
                'meeting_date': record.get('meeting_date'), 'attempt': attempt,
                'model': model, 'service_tier': service_tier, 'reasoning_effort': 'low',
                'max_output_tokens': payload['max_output_tokens'], 'status': status,
                'http_status': http_status, 'raw_response': raw, 'response': body,
                'text': text, 'usage': usage, 'actual_micro_usd': actual,
                'budget_charged_micro_usd': charged, 'error': error,
                'elapsed_seconds': round(time.monotonic() - started, 3)}
            serialized = json.dumps(result, ensure_ascii=False, allow_nan=False)
            if isinstance(transport, OpenAITransport):
                serialized = transport.redact(serialized)
            writer.write(serialized + '\n')
            writer.flush()
            if summary['budget_charged_micro_usd'] >= max_micro_usd:
                summary['stopped'] = 'actual_budget' if summary['actual_micro_usd'] >= max_micro_usd else 'uncertain_budget'
                return summary
            if status != 'transport_error':
                break
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', required=True)
    parser.add_argument('--model', default='gpt-6-luna', choices=sorted(common.RATES))
    parser.add_argument('--service-tier', default='standard', choices=['standard'])
    parser.add_argument('--max-usd', default='1.50')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--results', default='results.jsonl')
    args = parser.parse_args(argv)
    try:
        budget = Decimal(args.max_usd) * 1000000
        if not budget.is_finite() or budget <= 0 or budget != budget.to_integral_value():
            raise ValueError('Budget must be positive whole micro-USD')
        records = common.read_jsonl(args.requests)
        if args.execute:
            path = common.output_path(args.results)
            transport = OpenAITransport()
            # Exclusive create avoids silently discarding costs from earlier runs.
            with path.open('x', encoding='utf-8') as handle:
                class DurableWriter:
                    def write(self, text): handle.write(text)
                    def flush(self):
                        handle.flush()
                        os.fsync(handle.fileno())
                summary = replay(records, args.model, args.service_tier, int(budget), args.limit,
                                 transport=transport, writer=DurableWriter())
        else:
            summary = replay(records, args.model, args.service_tier, int(budget), args.limit)
        print(json.dumps(summary, sort_keys=True))
        return 2 if summary['stopped'].endswith('budget') else 1 if summary['failed_calls'] else 0
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
        # Never echo provider/input prose or credential-bearing exception strings.
        print('Replay stopped: invalid input, credential configuration or local I/O.', file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
