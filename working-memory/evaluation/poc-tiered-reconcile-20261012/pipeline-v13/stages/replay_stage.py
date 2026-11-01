"""Bounded extract/gate replay. Offline unless --execute; never retries.

Selection and full conservative budget preflight happen before credentials/transport.
Injected writers must make flush() durable; CLI uses flush plus fsync per attempt.
"""
import argparse
import http.client
import importlib.util
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from decimal import Decimal

_spec = importlib.util.spec_from_file_location('stage_common', Path(__file__).with_name('stage_common.py'))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
ROOT = Path(__file__).resolve().parent
STAGES = ('extract', 'gate')


def identity(record):
    job, call, stage = record.get('job_id'), record.get('call_index'), record.get('stage')
    if not isinstance(job, str) or not job or type(call) is not int or call < 0 or stage not in STAGES:
        raise ValueError('Missing or invalid stage identity')
    return job, call, stage


def reasoning_effort(record):
    values = []
    for source in (record.get('request_json', {}).get('transport', {}),
                   record.get('reference_usage', {}), record.get('reference_response', {})):
        if not isinstance(source, dict):
            continue
        if source.get('reasoning_effort') is not None:
            values.append(source['reasoning_effort'])
        reasoning = source.get('reasoning', {})
        if isinstance(reasoning, dict) and reasoning.get('effort') is not None:
            values.append(reasoning['effort'])
    if any(v not in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh') for v in values):
        raise ValueError('Invalid reference reasoning effort')
    if len(set(values)) > 1:
        raise ValueError('Conflicting reference reasoning effort')
    return values[0] if values else 'medium'


def build_request(record, model='gpt-6-luna'):
    if model != 'gpt-6-luna':
        raise ValueError('Only gpt-6-luna supported')
    source = record.get('request_json')
    if not isinstance(source, dict) or not isinstance(source.get('prompt'), str) or not isinstance(source.get('schema'), dict):
        raise ValueError('Prompt and explicit schema required')
    if '$: unsupported or invalid schema' in common.schema_errors(None, source['schema']):
        raise ValueError('Unsupported or invalid schema')
    json.dumps(source['schema'], allow_nan=False)
    allowance = source.get('max_tokens', 16000)
    if type(allowance) is not int or not 1 <= allowance <= 128000:
        raise ValueError('Invalid reference max_tokens')
    return {'model': model, 'input': [{'role': 'user', 'content': source['prompt']}],
        'reasoning': {'effort': reasoning_effort(record)}, 'truncation': 'disabled',
        'service_tier': 'default', 'text': {'format': {'type': 'json_schema',
        'name': 'meeting_result', 'strict': True, 'schema': source['schema']}},
        'max_output_tokens': max(16000, allowance), 'stream': True, 'store': False,
        'prompt_cache_options': {'mode': 'explicit'}}


def estimate(payload):
    prompt_bytes = len(payload['input'][0]['content'].encode('utf-8'))
    schema_bytes = len(json.dumps(payload['text']['format']['schema'], ensure_ascii=False).encode('utf-8'))
    reserve = prompt_bytes + schema_bytes + 4096
    return {'prompt_utf8_bytes': prompt_bytes, 'schema_utf8_bytes': schema_bytes,
        'framing_input_tokens': 4096, 'estimated_input_tokens': reserve,
        'reserved_output_tokens': payload['max_output_tokens'],
        'estimated_micro_usd': common.usage_micro_usd({'input_tokens': reserve,
        'input_tokens_details': {'cache_write_tokens': reserve},
        'output_tokens': payload['max_output_tokens']}, payload['model']),
        'assumptions': 'Upper reserve: one UTF-8 byte per input token plus 4096 framing tokens; all input charged as cache-write; full output allowance. Not a provider tokenizer guarantee.'}


def eligibility_reason(record):
    """Positive archived Sol baseline proof is required for a paid comparison."""
    source = record.get('request_json')
    if not isinstance(source, dict) or source.get('model') != 'gpt-6.1-sol':
        return 'foreign_reference_model'
    if record.get('reference_model') != 'gpt-6.1-sol' or record.get('reference_stop_reason') != 'end_turn':
        return 'unconfirmed_complete_reference'
    try:
        build_request(record)
        value = common.parse_json(record.get('reference_text'))
        if common.schema_errors(value, source['schema']):
            return 'invalid_reference_schema'
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return 'invalid_reference_json_or_request'
    return None


def eligibility_counts(records):
    counts = {name: {'total': 0, 'eligible': 0, 'excluded': 0} for name in STAGES}
    reasons = {}
    for record in records:
        key = identity(record)
        reason = eligibility_reason(record)
        counts[key[2]]['total'] += 1
        counts[key[2]]['eligible' if reason is None else 'excluded'] += 1
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    return {'stages': counts, 'exclusion_reasons': reasons}


def select_records(records, stage='both', select='stratified:6', limit=None):
    """Exact deterministic selection; limit is a safety cap, never truncation."""
    if stage not in (*STAGES, 'both'):
        raise ValueError('Invalid stage')
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError('Positive limit required')
    records = list(records)
    indexed, ids = {}, set()
    for record in records:
        key = identity(record)
        if key in indexed:
            raise ValueError('Duplicate stage identity')
        indexed[key] = record
        for field in ('stage_id', 'replay_id'):
            if field in record:
                value = record[field]
                if not isinstance(value, str) or not value or (field, value) in ids:
                    raise ValueError('Duplicate or invalid explicit identity')
                ids.add((field, value))
    stages = STAGES if stage == 'both' else (stage,)
    selected = []
    if isinstance(select, (str, Path)) and str(select).startswith(('smallest:', 'stratified:')):
        method, amount = str(select).split(':', 1)
        if not amount.isdecimal() or int(amount) < 1 or (method == 'stratified' and int(amount) != 6):
            raise ValueError('Invalid selection count')
        amount = int(amount)
        for name in stages:
            group = sorted((r for r in records if r['stage'] == name and eligibility_reason(r) is None),
                key=lambda r: (len(r['request_json']['prompt']), identity(r)))
            if len(group) < amount:
                raise ValueError('Insufficient stage identity coverage')
            if method == 'smallest':
                selected.extend(group[:amount])
            else:
                middle = (len(group) - 2) // 2
                positions = (0, 1, middle, middle + 1, len(group) - 2, len(group) - 1)
                if len(set(positions)) != 6:
                    raise ValueError('Insufficient stratified coverage')
                selected.extend(group[i] for i in positions)
    elif select == 'all':
        selected = [r for r in records if r['stage'] in stages]
        if any(not any(r['stage'] == name for r in selected) for name in stages):
            raise ValueError('Selected stage coverage missing')
    else:
        requested = list(common.read_jsonl(select)) if isinstance(select, (str, Path)) else list(select)
        seen = set()
        for item in requested:
            key = identity(item)
            if key in seen or key not in indexed or key[2] not in stages:
                raise ValueError('Missing, duplicate or wrong-stage selection identity')
            for field in ('stage_id', 'replay_id'):
                if field in item and item[field] != indexed[key].get(field):
                    raise ValueError('Selection explicit identity mismatch')
            seen.add(key)
            selected.append(indexed[key])
        if any(not any(r['stage'] == name for r in selected) for name in stages):
            raise ValueError('Selected stage coverage missing')
    if limit is not None and len(selected) > limit:
        raise ValueError('Selected calls exceed limit; choose a smaller explicit selection')
    if any(eligibility_reason(record) is not None for record in selected):
        raise ValueError('Selected identity lacks a complete schema-valid Sol reference')
    return selected


def plan(records, model='gpt-6-luna', stage='both', select='stratified:6',
         max_micro_usd=800000, limit=None):
    if type(max_micro_usd) is not int or max_micro_usd <= 0:
        raise ValueError('Positive budget required')
    selected = select_records(records, stage, select, limit)
    planned = [(record, build_request(record, model)) for record in selected]
    total = sum(estimate(payload)['estimated_micro_usd'] for _, payload in planned)
    if total > max_micro_usd:
        raise ValueError('Entire selected estimate exceeds budget')
    return planned


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


class DurableWriter:
    def __init__(self, handle):
        self.handle = handle

    def write(self, text):
        self.handle.write(text)

    def flush(self):
        self.handle.flush()
        os.fsync(self.handle.fileno())


def replay(records, model='gpt-6-luna', stage='both', select='stratified:6',
           max_micro_usd=800000, limit=None, transport=None, writer=None):
    """Offline when transport is None. All selection/budget gates precede calls.

    A supplied writer must durably persist each flush; use DurableWriter for files.
    """
    records = list(records)
    planned = plan(records, model, stage, select, max_micro_usd, limit)
    if transport is not None and writer is None:
        raise ValueError('Execution requires durable writer')
    summary = {'mode': 'DRY-RUN' if transport is None else 'EXECUTE',
        'selected_calls': len(planned), 'calls': 0, 'attempts': 0,
        'estimated_micro_usd': sum(estimate(p)['estimated_micro_usd'] for _, p in planned),
        'actual_micro_usd': 0, 'budget_charged_micro_usd': 0,
        'unknown_cost_attempts': 0, 'error_attempts': 0, 'failed_calls': 0,
        'max_micro_usd': max_micro_usd, 'stopped': 'end',
        'eligibility': eligibility_counts(records),
        'selection': [{'job_id': r['job_id'], 'call_index': r['call_index'],
            'stage': r['stage'], **estimate(p)} for r, p in planned]}
    if transport is None:
        summary['calls'] = len(planned)
        return summary
    for record, payload in planned:
        predicted = estimate(payload)
        reserved = predicted['estimated_micro_usd']
        if summary['budget_charged_micro_usd'] + reserved > max_micro_usd:
            summary['stopped'] = 'estimated_budget'
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
        answer = answer_text(body)
        http_status = raw_result.get('http_status')
        status, error = 'ok', None
        if raw_result.get('transport_error') is not None:
            status, error = 'transport_error', {'type': raw_result.get('exception_type', 'transport'),
                'message': raw_result['transport_error']}
        elif (raw_result.get('http_error') is not None or
              type(http_status) is not int or not 200 <= http_status < 300):
            status, error = 'http_error', {'type': 'http',
                'message': raw_result.get('http_error', 'HTTP status not successful'),
                'detail': body, 'body_read_error': raw_result.get('body_read_error')}
        elif stream_error:
            status, error = 'content_error', stream_error
        else:
            message = content_error(body, answer, payload)
            if message:
                status, error = 'content_error', {'type': 'content', 'message': message,
                    'provider_error': body.get('error') if isinstance(body, dict) else None}
        actual = common.usage_micro_usd(usage, model)
        if isinstance(body, dict) and (body.get('model') != model or body.get('service_tier') != 'default'):
            actual = None
        charged = reserved if actual is None else actual
        # Unknown accounting is an error even if output and schema were valid.
        if actual is None and error is None:
            status, error = 'unknown_cost', {'type': 'usage', 'message': 'Actual usage cost is unknown'}
        result = {'record_type': 'attempt', 'job_id': record['job_id'],
            'call_index': record['call_index'], 'stage': record['stage'],
            'meeting_date': record.get('meeting_date'), 'attempt': 1,
            'model': model, 'service_tier': 'default',
            'reasoning_effort': payload['reasoning']['effort'],
            'max_output_tokens': payload['max_output_tokens'], 'status': status,
            'http_status': http_status, 'raw_response': raw, 'response': body,
            'text': answer, 'usage': usage, 'actual_micro_usd': actual,
            'estimated_micro_usd': reserved, 'budget_charged_micro_usd': charged,
            'error': error, 'elapsed_seconds': round(time.monotonic() - started, 3)}
        serialized = json.dumps(result, ensure_ascii=False, allow_nan=False)
        if isinstance(transport, OpenAITransport):
            serialized = transport.redact(serialized)
        writer.write(serialized + '\n')
        writer.flush()
        summary['calls'] += 1
        summary['attempts'] += 1
        summary['budget_charged_micro_usd'] += charged
        if actual is None:
            summary['unknown_cost_attempts'] += 1
        else:
            summary['actual_micro_usd'] += actual
        if status != 'ok':
            summary['error_attempts'] += 1
            summary['failed_calls'] += 1
        if actual is None:
            summary['stopped'] = 'uncertain_budget'
            return summary
        if summary['budget_charged_micro_usd'] >= max_micro_usd:
            summary['stopped'] = 'actual_budget'
            return summary
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=(*STAGES, 'both'), default='both')
    parser.add_argument('--model', choices=['gpt-6-luna'], default='gpt-6-luna')
    parser.add_argument('--max-usd', default='0.80')
    parser.add_argument('--limit', type=int, help='Safety cap; selection is never silently truncated')
    parser.add_argument('--select', default='stratified:6',
        help='stratified:6 or smallest:N per stage, all, or identity JSONL path')
    parser.add_argument('--requests', default=str(ROOT / 'stage_requests.jsonl'))
    parser.add_argument('--results', default=str(ROOT / 'stage-results.jsonl'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    try:
        budget = Decimal(args.max_usd) * 1000000
        if not budget.is_finite() or budget <= 0 or budget != budget.to_integral_value():
            raise ValueError('Budget must be positive whole micro-USD')
        records = list(common.read_jsonl(args.requests))
        # Validate everything before touching credentials or constructing transport.
        plan(records, args.model, args.stage, args.select, int(budget), args.limit)
        if args.execute:
            path = common.output_path(args.results)
            transport = OpenAITransport()
            with path.open('x', encoding='utf-8') as handle:
                summary = replay(records, args.model, args.stage, args.select,
                    int(budget), args.limit, transport, DurableWriter(handle))
        else:
            summary = replay(records, args.model, args.stage, args.select, int(budget), args.limit)
        print(json.dumps(summary, sort_keys=True, allow_nan=False))
        return 2 if summary['stopped'].endswith('budget') else 1 if summary['failed_calls'] else 0
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
        print('Replay stopped: invalid selection, budget, input, credential configuration or local I/O.',
            file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

