"""Persistent reservation before each paid request, including repairs and gates.

For text-only requests the conservative estimate uses one input token per UTF-8
byte plus framing/schema allowance and the full configured output allowance.
Unknown provider usage keeps the reservation charged; it is never treated as zero.
This is a local spending control at recorded list prices, not a provider invoice.
"""
import json
import math
import sqlite3
import time
import uuid
from decimal import Decimal, ROUND_CEILING

RATES = {'claude-opus-5': (5, 25), 'claude-sonnet-5': (2, 10), 'gpt-5.6-terra': (2, 12), 'gpt-5.6-luna': (.2, 1.2), 'gpt-6.1-sol': (2, 10), 'text-embedding-3-small': (.02, 0)}


def reserve_micro_usd(prompt, model, max_tokens, schema, *, counted_input_tokens=None):
    if model not in RATES:
        raise BudgetExceeded('No verified price for model')
    if type(max_tokens) is not int or max_tokens <= 0:
        raise ValueError('Invalid output allowance')
    if model=='text-embedding-3-small':
        inputs=json.loads(prompt)
        if not isinstance(inputs,list) or not 1<=len(inputs)<=32 or any(not isinstance(t,str) or not t.strip() or len(t.encode())>8000 for t in inputs):
            raise ValueError('Invalid embedding inputs before reservation')
    size = len(prompt.encode()) + len(json.dumps(schema, ensure_ascii=False).encode()) + 4096
    if counted_input_tokens is not None:
        if model not in ('gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-6.1-sol') or type(counted_input_tokens) is not int or counted_input_tokens <= 0:
            raise ValueError('Invalid provider input token count')
        # Exact provider count includes message/schema framing. Keep additional
        # safety room; full output allowance and pricing premiums still apply.
        size = counted_input_tokens + 4096
    ip, op = map(Decimal, map(str, RATES[model]))
    if model in ('gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-6.1-sol'):
        # Reserve possible cache writes and the full-request long-context premium.
        # One token per UTF-8 byte is deliberately conservative for text inputs.
        if size > 272000:
            ip, op = ip * 2, op * Decimal('1.5')
        ip = Decimal(str(ip)) * Decimal('1.25')
    reserve = size * Decimal(str(ip)) + max_tokens * Decimal(str(op))
    if model == 'gpt-6.1-sol':
        reserve *= Decimal('1.10')  # Regional pricing uncertainty; reservation, not an invoice.
    return int(reserve.to_integral_value(rounding=ROUND_CEILING))


def usage_micro_usd(response, model):
    usage = response.get('usage')
    if model == 'gpt-6.1-sol' and response.get('returned_service_tier') not in ('default', 'flex'):
        return None
    if not response.get('usage_final') or not isinstance(usage, dict):
        return None
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('input_tokens', 'output_tokens')):
        return None
    ip, op = map(Decimal, map(str, (1, 5) if model == 'gpt-6.1-sol' and response.get('returned_service_tier') == 'flex' else RATES[model]))
    if model in ('gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-6.1-sol'):
        detail = usage.get('input_tokens_details', {})
        if not isinstance(detail, dict):
            return None
        if any(type(detail.get(k, 0)) is not int or detail.get(k, 0) < 0 for k in ('cached_tokens', 'cache_write_tokens')):
            return None
        cached, written = detail.get('cached_tokens', 0), detail.get('cache_write_tokens', 0)
        if cached + written > usage['input_tokens']:
            return None
        if usage['input_tokens'] > 272000:
            ip, op = ip * 2, op * Decimal('1.5')
        cache_read_factor = Decimal('.05') if model == 'gpt-6.1-sol' else Decimal('.1')
        cost = ((usage['input_tokens'] - cached - written) * ip
                + cached * ip * cache_read_factor + written * ip * Decimal('1.25'))
    else:
        if any(type(usage.get(k, 0)) is not int or usage.get(k, 0) < 0 for k in ('cache_read_input_tokens', 'cache_creation_input_tokens')):
            return None
        cost = (usage['input_tokens'] * ip + usage.get('cache_read_input_tokens', 0) * ip * Decimal('.1')
                + usage.get('cache_creation_input_tokens', 0) * ip * Decimal('1.25'))
    # output_tokens already includes reasoning; do not charge it a second time.
    return int((cost + usage['output_tokens'] * op).to_integral_value(rounding=ROUND_CEILING))

class BudgetExceeded(RuntimeError):
    pass


class CallBudget:
    def __init__(self, path, ceiling):
        if not math.isfinite(ceiling) or ceiling <= 0:
            raise ValueError('A positive explicit budget is required')
        self.db = sqlite3.connect(path, timeout=15, isolation_level=None)
        self.ceiling = ceiling
        self.db.execute('''CREATE TABLE IF NOT EXISTS call_reservations (
          id TEXT PRIMARY KEY, created_at REAL NOT NULL, model TEXT NOT NULL,
          reserved_usd REAL NOT NULL, actual_usd REAL, state TEXT NOT NULL)''')

    def total(self):
        return self.db.execute('SELECT coalesce(sum(coalesce(actual_usd,reserved_usd)),0) FROM call_reservations').fetchone()[0]

    def wrap(self, api, default_schema):
        def call(prompt, model, max_tokens=24000, schema=None):
            if model not in RATES:
                raise BudgetExceeded('No verified price for model')
            reserve = reserve_micro_usd(prompt, model, max_tokens, schema or default_schema) / 1_000_000
            identifier = uuid.uuid4().hex
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if self.total() + reserve > self.ceiling:
                    raise BudgetExceeded('Remaining budget does not cover the next request and its full output allowance')
                self.db.execute('INSERT INTO call_reservations VALUES (?,?,?,?,NULL,?)',
                                (identifier, time.time(), model, reserve, 'reserved'))
                self.db.execute('COMMIT')
            except Exception:
                self.db.execute('ROLLBACK')
                raise
            # Reservation is durable before networking. A crash cannot erase it.
            result = api(prompt, model, max_tokens=max_tokens, schema=schema)
            micro = usage_micro_usd(result, model)
            actual = None if micro is None else micro / 1_000_000
            self.db.execute('UPDATE call_reservations SET actual_usd=?,state=? WHERE id=?',
                            (actual, 'known' if actual is not None else 'usage_unknown', identifier))
            return result
        return call

    def close(self):
        self.db.close()
