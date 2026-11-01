"""Fail-closed chronological worker policy; no background work on import.

The configured start date is a source-date boundary, never an import-time
substitute. Legacy sources remain manual work even when newly discovered.
"""
from datetime import date
import json
import math
import time

import processor
from call_budget import CallBudget
from memory import ValidationError


def policy(environ):
    start = environ.get('MEMORY_AUTOMATIC_FROM_DATE', '')
    if not start or date.fromisoformat(start).isoformat() != start:
        raise ValidationError('An explicit automatic source-date boundary is required')
    ceiling = float(environ.get('MEMORY_BUDGET_USD', '0'))
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise ValidationError('An explicit finite positive service budget is required')
    if processor.PROMPT_VERSION != 'v9' or not processor.ACTION_GATE:
        raise ValidationError('Automatic processing requires v9 and action validation')
    return start, ceiling


def next_job(db, pipeline, start, now=None):
    """Return a runnable earliest job, or a visible reason for the pause.

    Filtering failed/leased/mismatching jobs *before* sorting would let later
    meetings run with missing context. Inspect the head of the entire queue.
    """
    now = time.time() if now is None else now
    row = db.execute('''SELECT j.id AS job_id,j.status,j.pipeline,j.lease_until,
        j.attempts,s.* FROM jobs j JOIN source_versions s ON s.id=j.source_version
        WHERE j.status!='applied' ORDER BY s.event_date,s.observed_at,s.source_id,j.id
        LIMIT 1''').fetchone()
    if not row:
        return None, {'state': 'idle'}
    base = {'job_id': row['job_id'], 'event_date': row['event_date']}
    if row['event_date'] < start:
        return None, {**base, 'state': 'paused', 'reason': 'legacy_requires_direct_review'}
    if row['pipeline'] != pipeline:
        return None, {**base, 'state': 'paused', 'reason': 'pipeline_changed'}
    if row['status'] == 'failed':
        return None, {**base, 'state': 'paused', 'reason': 'earlier_job_failed'}
    if row['status'] == 'leased':
        if row['lease_until'] is None or row['lease_until'] > now:
            return None, {**base, 'state': 'waiting', 'reason': 'earlier_job_leased'}
        # After a crash a provider call may have completed. Its reservation stays
        # charged; a bounded retry can claim the expired lease.
        if row['attempts'] >= 3:
            return None, {**base, 'state': 'paused', 'reason': 'attempt_limit'}
    elif row['status'] != 'queued':
        return None, {**base, 'state': 'paused', 'reason': 'unknown_job_state'}
    return dict(row), {**base, 'state': 'ready'}


class Worker:
    def __init__(self, db, budget_path, model, environ):
        self.db, self.model = db, model
        self.start, ceiling = policy(environ)
        self.pipeline = processor.pipeline_version(model)
        self.budget = CallBudget(budget_path, ceiling)
        schema = json.loads((processor.ROOT / 'evaluation/schema-v9.json').read_text())
        self.api = self.budget.wrap(processor.model_request, schema)

    def step(self, now=None):
        row, status = next_job(self.db, self.pipeline, self.start, now)
        if row:
            meeting = {'id': row['job_id'], 'source_id': row['source_id'],
                       'meeting_date': row['event_date'], 'title': row['title'],
                       'raw_transcript': row['transcript']}
            try:
                result = processor.process(self.db, meeting, self.model, api=self.api)
                status = {'state': result['status'], 'job_id': row['job_id']}
            except Exception as error:
                # processor records the failure; never expose source text or
                # provider payloads through operational status.
                status = {'state': 'paused', 'job_id': row['job_id'],
                          'reason': type(error).__name__}
        return {**status, 'accounted_usd': self.budget.total(),
                'budget_usd': self.budget.ceiling}

    def close(self):
        self.budget.close()
