"""Read-only deployment preflight for the canonical processing pipeline."""
import json
import os
import re

from canonical_worker import pipeline_version
from gateway_journal import GatewayJournal
from processor import DEFAULT_MODEL


MISMATCH = 2
ERROR = 1
PIPELINE = re.compile(r'[a-zA-Z0-9._:-]{1,240}\Z')


def safe_pipeline(value):
    return value if isinstance(value, str) and PIPELINE.fullmatch(value) else None


def diagnose(store, runtime_pipeline):
    """Use only the two read operations needed for a redacted diagnosis."""
    space = store.space()
    processing = store.call('processing_status')
    if not isinstance(space, dict) or not isinstance(processing, dict):
        raise ValueError('Invalid processing preflight response')
    config = processing.get('config')
    configured = safe_pipeline(config.get('pipeline')) if isinstance(config, dict) else None
    runtime = safe_pipeline(runtime_pipeline)
    if configured is None or runtime is None:
        return {
            'check': 'processing_preflight',
            'ok': False,
            'status': 'configuration_missing',
            'space': _space_summary(space),
            'processing': _processing_summary(processing, config),
        }, ERROR
    matches = configured == runtime
    result = {
        'check': 'processing_preflight',
        'ok': matches,
        'status': 'ready' if matches else 'pipeline_mismatch',
        'space': _space_summary(space),
        'processing': {
            **_processing_summary(processing, config),
            'configured_pipeline': configured,
            'runtime_pipeline': runtime,
            'pipeline_matches': matches,
        },
    }
    if not matches:
        result['action'] = 'Deploy matching runtime and processing configuration before starting the worker.'
    return result, 0 if matches else MISMATCH


def _space_summary(space):
    return {
        'state': space.get('state') if space.get('state') in ('draft', 'active') else 'unknown',
        'revision': space.get('revision') if type(space.get('revision')) is int else None,
        'archive_revision': space.get('archive_revision') if type(space.get('archive_revision')) is int else None,
    }


def _processing_summary(processing, config):
    return {
        'enabled': config.get('enabled') if isinstance(config, dict) and type(config.get('enabled')) is bool else None,
        'automatic_from': config.get('automatic_from') if isinstance(config, dict) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', config.get('automatic_from') or '') else None,
        'pending_count': processing.get('pending_count') if type(processing.get('pending_count')) is int else None,
        'archived_count': processing.get('archived_count') if type(processing.get('archived_count')) is int else None,
    }


def store_from_env(environ):
    return GatewayJournal(environ['SUPABASE_URL'], environ['SUPABASE_PUBLISHABLE_KEY'],
                          environ['MEMORY_JOURNAL_TOKEN'], environ['MEMORY_SPACE_ID'])


def main(environ=None):
    environ = os.environ if environ is None else environ
    try:
        model = environ.get('MEMORY_MODEL', DEFAULT_MODEL)
        result, exit_code = diagnose(store_from_env(environ), pipeline_version(model))
    except Exception as error:
        result = {'check': 'processing_preflight', 'ok': False, 'status': 'error',
                  'error_type': type(error).__name__}
        exit_code = ERROR
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
