"""Freeze one private, source-grounded semantic relation request; no provider call."""
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIVATE = Path('/private/tmp/semantic-relation-probe-20261005')
SOURCE = Path('/private/tmp/semantic-endstate-20261005/real-input.json')
EXPECTED_BODY_SHA = '7a77c62f3845cd5888400de24f3a900a897b18993da26aee7bf1cc878f6dcd8d'

SYNTHETIC = {
    'unrelated_negation': [
        'U001 [09:00] Mara: I will check the stock report every Friday.',
        'U002 [09:01] Lee: The warehouse inventory needs no regular check.',
        'U003 [09:02] Mara: Please send the stock report to my inbox.'
    ],
    'ambiguous_referent': [
        'U001 [09:00] Mara: I will check the PC report every Friday.',
        'U002 [09:01] Lee: I will check the stock report every Friday.',
        'U003 [09:02] Unknown speaker: That need not be checked regularly.'
    ]
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write_private(name, obj):
    path = PRIVATE / name
    content = json.dumps(obj, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text() != content:
        raise RuntimeError(f'frozen artifact differs: {path}')
    if not path.exists():
        with path.open('x') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    os.chmod(path, 0o600)
    return sha(path.read_bytes())

def main():
    old_umask = os.umask(0o077)
    try:
        PRIVATE.mkdir(mode=0o700, exist_ok=True)
        os.chmod(PRIVATE, 0o700)
        doc = json.loads(SOURCE.read_text())['document']
        body = doc['body']
        assert len(body) == 24865 and sha(body.encode()) == EXPECTED_BODY_SHA
        units = body.splitlines()
        assert len(units) == 197
        real = [f'U{i:03d} {line}' for i, line in enumerate(units, 1)]
        cases = [
            {'case_id': 'A', 'actions': [
                {'action_id': 'real_pc_check', 'focus': 'Regular PC France check discussed earlier; determine its relation to the later statement.'},
                {'action_id': 'real_csv_upload', 'focus': 'Upload or ingestion after receiving CSV; determine whether the later discussion changes the condition.'},
                {'action_id': 'real_priority_feedback', 'focus': 'Discussion of priority/timing with another decision maker and feedback; determine its relation to later discussion.'}
            ], 'units': real},
            {'case_id': 'B', 'actions': [
                {'action_id': 'synthetic_stock_check', 'focus': 'Mara: regular stock-report check; assess the later statement.'}
            ], 'units': SYNTHETIC['unrelated_negation']},
            {'case_id': 'C', 'actions': [
                {'action_id': 'synthetic_topic_a', 'focus': 'Mara: regular PC-report check; assess the later statement.'}
            ], 'units': SYNTHETIC['ambiguous_referent']}
        ]
        prompt = (HERE / 'prompt.txt').read_text()
        schema = json.loads((HERE / 'schema.json').read_text())
        request = {
            'model': 'gpt-5.6-terra',
            'max_tokens': 8000,
            'schema': schema,
            'prompt': prompt + '\nINPUT CASES AND ORIGINAL UNITS:\n' + json.dumps({'cases': cases}, ensure_ascii=False),
            'scope': {'mode': 'semantic_relation_probe', 'source_body_sha256': EXPECTED_BODY_SHA,
                      'provider_requests': 1, 'summary_generation': False}
        }
        source_map = {case['case_id']: {line.split(' ', 1)[0]: line.split(' ', 1)[1] for line in case['units']} for case in cases}
        req_sha = write_private('request.json', request)
        map_sha = write_private('source-map.json', source_map)
        expected = {
            'source_body_sha256': EXPECTED_BODY_SHA,
            'request_sha256': req_sha,
            'cases': {
                'A': {'real_pc_check': 'expressly_withdrawn', 'real_csv_upload': 'confirmed', 'real_priority_feedback': 'confirmed'},
                'B': {'synthetic_stock_check': 'independent'},
                'C': {'synthetic_topic_a': 'unclear'}
            },
            'required_evidence': {
                'A/real_pc_check': {'earlier': ['U085', 'U088'], 'later': ['U134']},
                'A/real_csv_upload': {'earlier': ['U134'], 'later': ['U164']},
                'A/real_priority_feedback': {'earlier': ['U178'], 'later': ['U180', 'U181']},
                'B/synthetic_stock_check': {'earlier': ['U001'], 'later': ['U002']},
                'C/synthetic_topic_a': {'earlier': ['U001'], 'later': ['U003']}
            },
            'required_review': ['C/synthetic_topic_a'],
            'interpretation': 'Real: withdraw regular PC check, preserve CSV prerequisite and priority/feedback. Synthetic unrelated: different inventory object does not withdraw stock report check. Ambiguous: no automatic cancellation.'
        }
        expected_sha = write_private('expected-private.json', expected)
        manifest = {
            'status': 'frozen_no_provider_request',
            'supersedes_request_sha256': '8415aae936dec6a6650e0d1329913a4ff553e4c232de079f8c8f84bb698f586a',
            'source_body_sha256': EXPECTED_BODY_SHA,
            'prompt_sha256': sha(prompt.encode()),
            'schema_sha256': sha((HERE / 'schema.json').read_bytes()),
            'request_sha256': req_sha,
            'source_map_sha256': map_sha,
            'expected_private_sha256': expected_sha,
            'model': request['model'], 'max_output_tokens': 8000,
            'reservation_config': 'Use existing provider count_input_tokens and reserve_micro_usd for exactly one gpt-5.6-terra request, max_tokens=8000; persist exclusive reservation before send; unknown outcome forbids resend.',
            'provider_requests_allowed_after_independent_lead_go': 1,
            'previous_failed_rounds_retained': 2,
            'paid_new_74194_status': 'preserved_not_accepted'
        }
        manifest_path = HERE / 'manifest.json'
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
        if manifest_path.exists() and manifest_path.read_text() != manifest_text:
            raise RuntimeError('frozen manifest differs')
        if not manifest_path.exists():
            manifest_path.write_text(manifest_text)
        print(json.dumps(manifest, indent=2))
    finally:
        os.umask(old_umask)

if __name__ == '__main__':
    main()
