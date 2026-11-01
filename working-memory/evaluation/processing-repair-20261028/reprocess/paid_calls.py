"""Existing provider calls with the established single-send recovery receipts."""
import hashlib
import json
import os
from pathlib import Path


TOKEN_JOB = '9266439fe8c4bb320db97d2a4bb1c4f16b5badb43f9bebf51c2f2191df6a61f7'
TOKEN_OVERRIDE = {'request_hash': '825d696d562fc164874de3d44bcd70541c3ab17ac165308f4ef567e5a48a9b59',
                  'from_max_tokens': 24000, 'to_max_tokens': 48000}
CONTEXT_ATTEMPT = 'e9a2a394-dab8-5585-b7ee-7570223ac4b8'
CONTEXT_PIPELINE = 'v11:compact1:gate1:gpt-6.1-sol:1b0547b903630200:hotset1:age=30:rank=8:wait1:delta2:canonical1:d6198b7958d46e3e'
CONTEXT_CALLS_HASH = 'c0ae6f2cb016070c62e7c0ad4d22c1333665d0970000210fca046b5d0b058e98'
CONTEXT_CAPTURE = {'prompt_sha256': 'd4c9b6455bc0e221b1e87ab34fe2b713f121631cb236daa3db7c34641f039073',
                   'schema_sha256': 'c5c64bd2012db4c6c937910cce3782f8e30e8457868e7cdf9595257f2fc71f07',
                   'prompt_chars': 958227, 'prompt_utf8_bytes': 968641, 'schema_utf8_bytes': 30139,
                   'max_output_tokens': 59736, 'framing_tokens': 4096, 'conservative_total_tokens': 1062612}


class PaidOutcomeUnknown(RuntimeError):
    pass


class ContextCountUnavailable(RuntimeError):
    pass


class ContextBudgetExceeded(RuntimeError):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def private_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.new')
    with temporary.open('w') as stream:
        stream.write(encode(value)); stream.flush(); os.fsync(stream.fileno())
    temporary.chmod(0o600); temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class PaidCalls:
    def __init__(self, store, directory, job, pipeline, revision, start_index, schema,
                 provider=None, budget=None, ledger_directory=None, lease_token=None, token_override=None,
                 context_continuation=None):
        if provider is None:
            import openai_provider as provider
        if budget is None:
            import call_budget as budget
        self.store, self.provider, self.budget = store, provider, budget
        if not lease_token: raise ValueError("Normal ledger lease is required")
        if token_override is not None and (token_override != TOKEN_OVERRIDE or job != TOKEN_JOB or revision != 355 or start_index != 2):
            raise ValueError('Token recovery scope changed')
        self.token_override, self.override_used = token_override, False
        if context_continuation is not None and not (
                job == TOKEN_JOB and pipeline == CONTEXT_PIPELINE and revision == 355 and start_index == 2
                and token_override == TOKEN_OVERRIDE
                and context_continuation.get('execution_path') == 'owner_full_reprocess_context_continuation'
                and context_continuation.get('attempt_command_id') == CONTEXT_ATTEMPT
                and context_continuation.get('calls_hash') == CONTEXT_CALLS_HASH
                and context_continuation.get('lease_token') == lease_token
                and {k: context_continuation.get('capture', {}).get(k) for k in CONTEXT_CAPTURE} == CONTEXT_CAPTURE):
            raise ValueError('Context continuation scope changed')
        self.context_continuation = context_continuation
        self.context_counts, self.counted_inputs = {}, {}
        self.lease_token = lease_token
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.ledger = Path(ledger_directory) if ledger_directory is not None else self.directory
        self.ledger.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.job, self.pipeline, self.revision = job, pipeline, revision
        self.start_index, self.index, self.schema = start_index, start_index, schema
        self.receipts, self.primary_responses = [], []
        self.last_metadata = {}
        self.existing = {}
        for folder in sorted(self.ledger.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else -1):
            if not folder.is_dir() or not folder.name.isdigit(): continue
            if not (folder / 'reservation.json').exists(): continue
            reservation = json.loads((folder / 'reservation.json').read_text())
            index = reservation['call_index']
            if not start_index <= index <= 1023: raise ValueError('Existing recovery slot scope changed')
            self.index = max(self.index, index + 1)
            self.existing[reservation['request_hash']] = folder
            body_folder = self.directory / folder.name
            if (folder / 'receipt.json').exists() and (body_folder / 'response.json').exists():
                receipt = json.loads((folder / 'receipt.json').read_text())
                response = json.loads((body_folder / 'response.json').read_text())
                if receipt['response_hash'] != sha(encode(response)): raise ValueError('Saved receipt hash changed')
                if receipt['actual_micro_usd'] != self.budget.usage_micro_usd(response, receipt['model']):
                    raise ValueError('Saved receipt cost changed')
                if type(receipt.get('actual_micro_usd')) is int and response.get('stop_reason') == 'end_turn':
                    self.receipts.append(receipt)

    def request_value(self, prompt, model, max_tokens, schema):
        return {'model': model, 'prompt': prompt, 'max_tokens': max_tokens, 'schema': schema,
                'scope': {'mode': 'bounded_recovery_generation', 'job_id': self.job,
                          'pipeline': self.pipeline, 'revision': self.revision}}

    def context_guard(self, original):
        """Use the existing exact counter only for this approved compact attempt."""
        def checked(name, prompt, schema, max_tokens, model, compact):
            rejected = original(name, prompt, schema, max_tokens, model, compact)
            if not self.context_continuation:
                return rejected
            if not (compact and name.startswith('compact-') and name[8:].isdigit() and model == self.provider.MODEL):
                return rejected
            capture = self.context_continuation['capture']
            if name == 'compact-0' and (sha(prompt) != capture['prompt_sha256']
                    or sha(json.dumps(schema, ensure_ascii=False)) != capture['schema_sha256']
                    or max_tokens != capture['max_output_tokens']):
                raise ValueError('Captured compact request changed')
            if not rejected:
                if name == 'compact-0': raise ValueError('Captured compact guard changed')
                return False
            if type(max_tokens) is not int or not 0 < max_tokens <= 64000:
                raise ValueError('Normal compact output limit changed')
            request_hash = sha(encode(self.request_value(prompt, model, max_tokens, schema)))
            identity = {'request_hash': request_hash, 'stage': name, 'model': model,
                        'max_output_tokens': max_tokens, 'framing_tokens': 4096, 'limit': 1050000}
            folder = self.directory.parent / 'context-counts'; folder.mkdir(exist_ok=True, mode=0o700)
            path = folder / (request_hash + '.json')
            if path.exists():
                receipt = json.loads(path.read_text())
                if {k: receipt.get(k) for k in identity if k != 'stage'} != {k:v for k,v in identity.items() if k != 'stage'} or not (
                        str(receipt.get('stage', '')).startswith('compact-') and str(receipt['stage'])[8:].isdigit()):
                    raise ValueError('Saved exact context count changed')
                count = receipt.get('input_tokens')
            else:
                try:
                    count = self.provider.count_input_tokens(prompt, model, schema)
                except Exception as error:
                    self.last_metadata = {'error': 'Exact context count unavailable', 'stage': name,
                                          'generation_sent': False}
                    raise ContextCountUnavailable('Exact context count unavailable; generation not sent') from error
                receipt = {**identity, 'input_tokens': count}
            if type(count) is not int or count <= 0:
                self.last_metadata = {'error': 'Exact context count unavailable', 'stage': name,
                                      'generation_sent': False}
                raise ContextCountUnavailable('Exact context count unavailable; generation not sent')
            if type(max_tokens) is not int or max_tokens <= 0 or count + 4096 + max_tokens > 1050000:
                self.last_metadata = {'error': 'Exact compact context exceeds production budget', 'stage': name,
                                      'input_tokens': count, 'max_output_tokens': max_tokens, 'generation_sent': False}
                raise ContextBudgetExceeded('Exact compact context exceeds production budget')
            if not path.exists(): private_json(path, receipt)
            self.context_counts[request_hash] = receipt
            self.counted_inputs[request_hash] = count
            return False
        return checked

    def _reserve(self, reservation, request):
        if request['model'] != reservation['model'] or reservation['job_id'] != self.job:
            raise ValueError('Saved reservation identity changed')
        if sha(encode(request)) != reservation['request_hash']:
            raise ValueError('Saved request hash changed')
        record = self.store.call('reserve_call', job_id=self.job, lease_token=self.lease_token,
                                 call_index=reservation['call_index'], request_json=encode(request),
                                 reserved_micro_usd=reservation['reserved_micro_usd'])
        if record.get('state') == 'budget_exceeded':
            self.last_metadata = {'error': 'Existing processing budget does not cover request', 'generation_sent': False}
            raise ContextBudgetExceeded('Existing processing budget does not cover request')
        if record.get('reserved_micro_usd') != reservation['reserved_micro_usd']:
            raise ValueError('Normal reservation amount changed')
        if record.get('request_hash') != reservation['request_hash']:
            raise ValueError('Normal reservation hash changed')
        return record

    def _receive(self, reservation, response):
        actual = self.budget.usage_micro_usd(response, reservation['model'])
        receipt = {**reservation, 'response_hash': sha(encode(response)), 'actual_micro_usd': actual,
                   'usage': response.get('usage', {})}
        saved = self.store.call('receive_call', job_id=self.job, lease_token=self.lease_token,
                               call_index=reservation['call_index'], response_json=encode(response),
                               actual_micro_usd=actual)
        if saved.get('saved') is not True:
            raise PaidOutcomeUnknown('Normal response persistence unconfirmed')
        private_json(self.ledger / str(reservation['call_index']) / 'receipt.json', receipt)
        if actual is None or response.get('stop_reason') != 'end_turn':
            raise PaidOutcomeUnknown('Provider response is not a known successful result')
        if not any(r['call_index'] == receipt['call_index'] for r in self.receipts):
            self.receipts.append(receipt)
        return receipt

    def import_known(self):
        """Settle existing known bodies numerically, never invoke the provider."""
        imported = 0
        for folder in sorted(self.existing.values(), key=lambda p: int(p.name)):
            reservation = json.loads((folder / 'reservation.json').read_text())
            body = self.directory / folder.name
            if not (body / 'request.json').exists() or not (body / 'response.json').exists():
                raise PaidOutcomeUnknown('Known-body import cannot resend an incomplete reservation')
            request = json.loads((body / 'request.json').read_text())
            response = json.loads((body / 'response.json').read_text())
            if request['scope'] != {'mode': 'bounded_recovery_generation', 'job_id': self.job,
                                    'pipeline': self.pipeline, 'revision': self.revision}:
                raise ValueError('Saved request scope changed')
            if request['model'] != reservation['model'] or reservation['job_id'] != self.job:
                raise ValueError('Saved reservation scope changed')
            actual = self.budget.usage_micro_usd(response, reservation['model'])
            if type(actual) is not int or response.get('stop_reason') != 'end_turn':
                raise PaidOutcomeUnknown('Only known successful responses may be imported')
            existing_receipt = folder / 'receipt.json'
            if existing_receipt.exists():
                receipt = json.loads(existing_receipt.read_text())
                if receipt['response_hash'] != sha(encode(response)) or receipt['actual_micro_usd'] != actual:
                    raise ValueError('Saved receipt hash or cost changed')
            record = self._reserve(reservation, request)
            if record.get('response_json') is not None:
                if record['response_json'] != encode(response) or record.get('actual_micro_usd') != actual:
                    raise ValueError('Normal ledger response differs from known body')
            self._receive(reservation, response)
            imported += 1
        return {'imported': imported, 'actual_micro_usd': sum(r['actual_micro_usd'] for r in self.receipts)}

    def __call__(self, prompt, model, max_tokens=24000, schema=None):
        if model not in (self.provider.MODEL, 'text-embedding-3-small'):
            raise ValueError('Production model scope changed')
        effective = self.schema if schema is None else schema
        # Preserve the old cache serialization so the 32 known replies are reused.
        value = self.request_value(prompt, model, max_tokens, effective)
        if self.token_override and model == self.provider.MODEL and not self.override_used:
            if sha(encode(value)) != self.token_override['request_hash'] or max_tokens != 24000:
                raise ValueError('Reviewed extraction request changed before token recovery')
            max_tokens = value['max_tokens'] = 48000
            # Existing runtime conservative context guard, with the actual larger output cap.
            if len(prompt) > 220000 or len(prompt.encode()) + len(encode(effective).encode()) + 4096 + max_tokens > 1050000:
                raise ValueError('Token recovery context exceeds production budget')
            self.override_used = True
        request_hash = sha(encode(value)); previous = self.existing.get(request_hash)
        if previous is None and not 0 <= self.index <= 1023:
            raise RuntimeError('Normal durable call boundary exhausted')
        if previous is None and len(self.existing) != len(self.receipts):
            raise PaidOutcomeUnknown('Uncertain existing request forbids further sends')
        metadata_slot = previous or self.ledger / str(self.index)
        slot = self.directory / metadata_slot.name
        slot.mkdir(exist_ok=True, mode=0o700); metadata_slot.mkdir(exist_ok=True, mode=0o700)
        reservation_path, response_path = metadata_slot / 'reservation.json', slot / 'response.json'
        fresh = not reservation_path.exists()
        if not fresh:
            reservation = json.loads(reservation_path.read_text())
            if reservation['request_hash'] != request_hash:
                raise PaidOutcomeUnknown('Existing reservation belongs to different input')
            if not response_path.exists():
                raise PaidOutcomeUnknown('Existing reservation forbids another send')
        else:
            count = self.counted_inputs.get(request_hash)
            if count is None:
                count = (self.provider.count_input_tokens(prompt, model, effective)
                         if model == self.provider.MODEL else 0)
            reserved = self.budget.reserve_micro_usd(prompt, model, max_tokens, effective,
                                                   counted_input_tokens=count or None)
            reservation = {'job_id': self.job, 'call_index': self.index, 'request_hash': request_hash,
                           'model': model, 'provider_input_tokens': count, 'reserved_micro_usd': reserved}
            private_json(slot / 'request.json', value)
            with reservation_path.open('x') as stream:
                stream.write(encode(reservation)); stream.flush(); os.fsync(stream.fileno())
            reservation_path.chmod(0o600)
            descriptor = os.open(metadata_slot, os.O_RDONLY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
            self.existing[request_hash] = metadata_slot
        record = self._reserve(reservation, value)
        if response_path.exists():
            response = json.loads(response_path.read_text())
            if record.get('response_json') is not None and record['response_json'] != encode(response):
                raise ValueError('Normal ledger response differs from private body')
        elif record.get('response_json') is not None:
            response = json.loads(record['response_json'])
            private_json(response_path, response)
        elif fresh and record.get('send') is True:
            response = self.provider.request(prompt, model, max_tokens=max_tokens, schema=effective)
            private_json(response_path, response)
        else:
            raise PaidOutcomeUnknown('Reserved normal slot cannot be sent again')
        self.last_metadata = {key: response.get(key) for key in
                              ('error', 'provider_error_code', 'stream_error_kind', 'terminal_status')}
        receipt = self._receive(reservation, response)
        if previous is None: self.index += 1
        if schema is None: self.primary_responses.append(response)
        print(encode({'event': 'paid_call_received', 'job': self.job[:8], 'call_index': receipt['call_index'],
                      'model': model, 'actual_micro_usd': receipt['actual_micro_usd']}), flush=True)
        return response
