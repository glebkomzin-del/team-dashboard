"""No network: single-send receipts and immutable target guards."""
import importlib.util
import base64
import json
from pathlib import Path
import tempfile
import shutil
import sys
import io
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
paid = load('paid_calls')


class LedgerStore:
    """Exercise the ordinary sequential reservation/receive contract offline."""
    def __init__(self, start=9, ceiling=None, accounted=0):
        self.rows = {i: {'request_hash': 'old', 'response_json': '{}', 'actual_micro_usd': 0} for i in range(start)}
        self.old = json.dumps(self.rows, sort_keys=True)
        self.ceiling, self.accounted, self.events = ceiling, accounted, []

    def call(self, operation, **fields):
        self.events.append(operation)
        index = fields['call_index']
        if operation == 'reserve_call':
            request = fields['request_json']; digest = paid.sha(request)
            if index in self.rows:
                row = self.rows[index]
                if row['request_hash'] != digest: raise ValueError('Call identity changed')
                return {**row, 'send': False}
            if index != len(self.rows) or any(r['response_json'] is None for r in self.rows.values()):
                raise ValueError('Previous call unresolved or missing')
            if self.ceiling is not None and self.accounted + fields['reserved_micro_usd'] > self.ceiling:
                return {'state': 'budget_exceeded', 'send': False}
            row = {'request_json': request, 'request_hash': digest, 'response_json': None,
                   'reserved_micro_usd': fields['reserved_micro_usd'], 'actual_micro_usd': None}
            self.rows[index] = row
            return {**row, 'send': True}
        if operation != 'receive_call': raise AssertionError('Unexpected operation')
        row = self.rows[index]; body = fields['response_json']; actual = fields['actual_micro_usd']
        if row['response_json'] is not None:
            if row['response_json'] != body or row['actual_micro_usd'] != actual: raise ValueError('Response identity changed')
        else:
            row.update(response_json=body, actual_micro_usd=actual, response_hash=paid.sha(body))
            self.accounted += actual if actual is not None else row['reserved_micro_usd']
        return {'saved': True}


class RecoveryTests(unittest.TestCase):
    def context_api(self, folder, count=300000):
        prompt, schema, maximum = 'unchanged compact input', {'type': 'object'}, 59736
        capture = {**paid.CONTEXT_CAPTURE, 'prompt_sha256': paid.sha(prompt),
                   'schema_sha256': paid.sha(json.dumps(schema, ensure_ascii=False))}
        approval = {'execution_path': 'owner_full_reprocess_context_continuation',
                    'attempt_command_id': paid.CONTEXT_ATTEMPT, 'calls_hash': paid.CONTEXT_CALLS_HASH,
                    'lease_token': 'lease', 'capture': capture}
        api, sends = self.setup_api(Path(folder) / 'calls', {'cost': 50, 'stop_reason': 'end_turn'}, start=125)
        with patch.dict(paid.CONTEXT_CAPTURE, capture, clear=True):
            api = paid.PaidCalls(api.store, api.directory, paid.TOKEN_JOB, paid.CONTEXT_PIPELINE, 355, 2,
                                 {}, api.provider, api.budget, lease_token='lease', token_override=paid.TOKEN_OVERRIDE,
                                 context_continuation=approval)
        # Isolate the compact stage after the separately tested 123-response replay.
        api.index, api.override_used = 125, True
        counts, reserves = [], []
        def counter(*args):
            counts.append(args)
            if isinstance(count, Exception): raise count
            return count
        api.provider.count_input_tokens = counter
        api.budget.reserve_micro_usd = lambda *args, **kwargs: reserves.append(kwargs['counted_input_tokens']) or 200
        return api, sends, counts, reserves, prompt, schema, maximum

    def test_exact_compact_count_is_shared_with_reservation_and_reused_without_send(self):
        with tempfile.TemporaryDirectory() as folder:
            api, sends, counts, reserves, prompt, schema, maximum = self.context_api(folder)
            old = paid.encode(api.store.rows)
            guard = api.context_guard(lambda *args: True)
            self.assertFalse(guard('compact-0', prompt, schema, maximum, api.provider.MODEL, True))
            api(prompt, api.provider.MODEL, max_tokens=maximum, schema=schema)
            self.assertEqual((len(counts), reserves, len(sends)), (1, [300000], 1))
            request = json.loads(api.store.rows[125]['request_json'])
            self.assertEqual((request['prompt'], request['schema'], request['max_tokens']), (prompt, schema, maximum))
            self.assertEqual(paid.encode({k:v for k,v in api.store.rows.items() if k<125}), old)
            with patch.dict(paid.CONTEXT_CAPTURE, api.context_continuation['capture'], clear=True):
                resumed = paid.PaidCalls(api.store, api.directory, api.job, api.pipeline, 355, 2, {}, api.provider,
                                         api.budget, lease_token='lease', token_override=paid.TOKEN_OVERRIDE,
                                         context_continuation=api.context_continuation)
            resumed.override_used = True
            self.assertFalse(resumed.context_guard(lambda *args: True)('compact-0', prompt, schema, maximum, api.provider.MODEL, True))
            resumed(prompt, api.provider.MODEL, max_tokens=maximum, schema=schema)
            self.assertEqual((len(counts), reserves, len(sends)), (1, [300000], 1))
            self.assertEqual(resumed.context_counts, api.context_counts)
            self.assertFalse(resumed.context_guard(lambda *args: True)('compact-1', prompt, schema, maximum, api.provider.MODEL, True))
            resumed(prompt, api.provider.MODEL, max_tokens=maximum, schema=schema)
            self.assertEqual((len(counts), reserves, len(sends)), (1, [300000], 1))

    def test_count_unavailable_or_over_budget_never_reserves_or_sends(self):
        for count in (None, 0, True, RuntimeError('counter transport failed'), 1050000-4096-59736+1):
            with self.subTest(count=type(count).__name__), tempfile.TemporaryDirectory() as folder:
                api,sends,counts,reserves,prompt,schema,maximum = self.context_api(folder,count)
                failure = paid.ContextBudgetExceeded if type(count) is int and count>1 else paid.ContextCountUnavailable
                with self.assertRaises(failure):
                    api.context_guard(lambda *args: True)('compact-0',prompt,schema,maximum,api.provider.MODEL,True)
                self.assertEqual((sends,reserves,api.store.events),([],[],[]))
                self.assertIs(api.last_metadata['generation_sent'],False)
        with tempfile.TemporaryDirectory() as folder:
            api,_,counts,_,prompt,schema,maximum=self.context_api(folder,1050000-4096-59736)
            self.assertFalse(api.context_guard(lambda *args:True)('compact-0',prompt,schema,maximum,api.provider.MODEL,True))
            self.assertEqual(len(counts),1)

    def test_context_scope_and_first_capture_changes_stop_before_count(self):
        with tempfile.TemporaryDirectory() as folder:
            api,sends,counts,reserves,prompt,schema,maximum=self.context_api(folder)
            for changed in ((prompt+'!',schema,maximum),(prompt,{},maximum),(prompt,schema,maximum+1)):
                with self.assertRaisesRegex(ValueError,'Captured compact request changed'):
                    api.context_guard(lambda *args:True)('compact-0',*changed,api.provider.MODEL,True)
            self.assertEqual((counts,reserves,sends),([],[],[]))
            self.assertTrue(api.context_guard(lambda *args:True)('gate',prompt,schema,maximum,api.provider.MODEL,True))
            self.assertFalse(api.context_guard(lambda *args:False)('compact-1',prompt,schema,maximum,api.provider.MODEL,True))
            self.assertEqual(counts,[])
            for job,pipeline,revision,start in (('other',api.pipeline,355,2),(api.job,'other',355,2),
                                                (api.job,api.pipeline,356,2),(api.job,api.pipeline,355,125)):
                with self.assertRaisesRegex(ValueError,'scope'):
                    paid.PaidCalls(api.store,api.directory,job,pipeline,revision,start,{},api.provider,api.budget,
                                   lease_token='lease',token_override=paid.TOKEN_OVERRIDE,
                                   context_continuation=api.context_continuation)

    def context_claim_fixture(self):
        remote=load('remote');target={'id':paid.TOKEN_JOB,'source_id':'source','document_id':'doc','body_hash':paid.sha('body')}
        value={'config':{'pipeline':paid.CONTEXT_PIPELINE},'job':{'id':target['id'],'space_id':'space','lease_token':'lease'},
               'document':{'id':'doc','source_id':'source','body_hash':target['body_hash'],'body':'body'}}
        capture={**remote.CONTEXT_CAPTURE,'phase':'captured','name':'compact-0','job':paid.TOKEN_JOB,'revision':355,
                 'limit':1050000,'guard_rejected':True,'search_snapshot_id':'snapshot'}
        return remote,target,value,capture

    def test_context_continuation_is_readonly_or_same_attempt_without_new_range(self):
        remote,target,value,capture=self.context_claim_fixture();queries=[]
        def query(sql,**kwargs):queries.append((sql,kwargs));return '{}'
        with patch.object(remote,'snapshot',return_value=value),patch.object(remote,'context_capture',return_value=capture),patch.object(remote,'sql',side_effect=query):
            remote.context_claim('space',target,'targets')
            remote.context_claim('space',target,'targets',execute=True)
        readonly=queries[0][0];write=queries[1][0]
        self.assertTrue(readonly.startswith('BEGIN ISOLATION LEVEL SERIALIZABLE READ ONLY;'))
        for mutation in ('INSERT INTO','UPDATE wm_jobs','FOR UPDATE'):self.assertNotIn(mutation,readonly)
        self.assertFalse(queries[0][1]['persist_errors'])
        for guard in ('j.attempts<>3','n<>123','BETWEEN 2 AND 124','167049::bigint','n<>125',
                      remote.lit(remote.CONTEXT_FAILURE['calls_hash']),remote.lit(remote.CONTEXT_FAILURE['updated_at']),
                      "j.reason IN ('provider_outcome_unknown','transport_failed')",'new semantic failure stays blocked'):
            self.assertIn(guard,write)
        resume=write.split('IF FOUND THEN ',1)[1].split(' ELSE ',1)[0]
        self.assertNotIn('validation_failed',resume)
        for forbidden in ('attempts=','attempts =','UPDATE wm_model_calls',"'start_index': 125"):
            self.assertNotIn(forbidden,write)
        self.assertTrue(any('owner_full_reprocess_context_continuation' in base64.b64decode(v).decode() for v in re.findall(r"decode\('([A-Za-z0-9+/=]+)'",write)))
        self.assertEqual(remote.CONTEXT_CAPTURE,paid.CONTEXT_CAPTURE)

    def test_context_preflight_failures_never_persist_diagnostics(self):
        remote,target,value,capture=self.context_claim_fixture()
        failed=SimpleNamespace(returncode=1,stdout=b'',stderr=b'private error')
        with tempfile.TemporaryDirectory() as folder,patch.object(remote,'ROOT',Path(folder)),patch.object(remote.subprocess,'run',return_value=failed):
            with self.assertRaisesRegex(RuntimeError,'no diagnostic persisted'):remote.context_claim('space',target,'targets')
            with patch.object(remote,'snapshot',return_value=value),self.assertRaisesRegex(RuntimeError,'no diagnostic persisted'):
                remote.context_claim('space',target,'targets')
            with patch.object(remote,'snapshot',return_value=value),patch.object(remote,'context_capture',return_value=capture),self.assertRaisesRegex(RuntimeError,'no diagnostic persisted'):
                remote.context_claim('space',target,'targets')
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_context_transport_budget_and_semantic_failures_keep_distinct_pause_reasons(self):
        sys.path[:0]=[str(ROOT.parent/'replay/overlay'),str(ROOT.parent/'replay/private/runtime')]
        worker=load('container_worker')
        self.assertEqual(worker.failure_reason(worker.ContextCountUnavailable()),'transport_failed')
        self.assertEqual(worker.failure_reason(worker.ContextBudgetExceeded()),'budget_exceeded')
        self.assertEqual(worker.failure_reason(worker.PaidOutcomeUnknown()),'provider_outcome_unknown')
        self.assertEqual(worker.failure_reason(ValueError('new semantic failure')),'validation_failed')

    def reviewed_fixture(self):
        remote = load('remote')
        target = {'id': remote.REVIEWED_FAILURE['job_id'], 'space_id': 'space',
                  'source_id': 'source', 'document_id': 'document', 'body_hash': paid.sha('body')}
        value = {'config': {'pipeline': 'pipeline'}, 'job': {'id': target['id'], 'space_id': 'space'},
                 'document': {'id': 'document', 'source_id': 'source', 'body_hash': target['body_hash'], 'body': 'body'}}
        return remote, target, value

    def test_reviewed_preflight_is_read_only_and_binds_exact_reviewed_failure(self):
        remote, target, value = self.reviewed_fixture(); queries = []
        def capture(query, *, persist_errors):
            self.assertFalse(persist_errors); queries.append(query); return '{}'
        with patch.object(remote, 'snapshot', return_value=value), patch.object(remote, 'sql', side_effect=capture):
            remote.reviewed_claim('space', target, 'targets')
        query = queries[0]
        self.assertTrue(query.startswith('BEGIN ISOLATION LEVEL SERIALIZABLE READ ONLY;'))
        for write in ('INSERT INTO', 'UPDATE wm_jobs', 'FOR UPDATE', 'DELETE', 'UPDATE wm_model_calls'):
            self.assertNotIn(write, query)
        for guard in ('j.attempts<>2', 'j.prepared_payload IS NOT NULL', 'n<>67', 'response_json IS NULL',
                      's.revision<>354', 'Another job is active', remote.lit(remote.REVIEWED_FAILURE['response_hash']),
                      remote.lit(remote.REVIEWED_FAILURE['updated_at'])):
            self.assertIn(guard, query)
        with patch.object(remote, 'snapshot') as snapshot, self.assertRaises(AssertionError):
            remote.reviewed_claim('space', {**target, 'id': 'a' * 64}, 'targets')
        snapshot.assert_not_called()
        with patch.object(remote, 'snapshot', return_value={**value, 'document': {**value['document'], 'body': 'changed'}}), \
                patch.object(remote, 'sql') as sql, self.assertRaises(AssertionError):
            remote.reviewed_claim('space', target, 'targets')
        sql.assert_not_called()

    def test_failed_readonly_preflight_never_creates_diagnostics(self):
        remote, target, value = self.reviewed_fixture()
        bundle = {'action': 'reviewed-preflight', 'space_id': 'space', 'job_prefix': 'f09befd7',
                  'targets_sha256': 'targets', 'targets': [target] + [{'id': str(i)} for i in range(21)]}
        failed = SimpleNamespace(returncode=1, stdout=b'', stderr=b'private failure')
        with tempfile.TemporaryDirectory() as folder, patch.object(remote, 'ROOT', Path(folder)), \
                patch.object(remote.subprocess, 'run', return_value=failed):
            with self.assertRaisesRegex(RuntimeError, 'no diagnostic persisted'):
                remote.run(bundle)  # Failed container/runtime inspection.
            with self.assertRaisesRegex(RuntimeError, 'no diagnostic persisted'):
                remote.reviewed_claim('space', target, 'targets')  # Failed initial SQL snapshot.
            with patch.object(remote, 'snapshot', return_value=value), \
                    self.assertRaisesRegex(RuntimeError, 'no diagnostic persisted'):
                remote.reviewed_claim('space', target, 'targets')  # Failed final read-only guard SQL.
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_reviewed_claim_has_one_stable_command_and_never_restarts_failed_new_attempt(self):
        remote, target, value = self.reviewed_fixture(); queries = []
        def capture(query, *, persist_errors):
            self.assertTrue(persist_errors)
            queries.append(query)
            encoded = re.findall(r"convert_from\(decode\('([A-Za-z0-9+/=]+)'", query)[-1]
            return base64.b64decode(encoded).decode()
        with patch.object(remote, 'snapshot', return_value=value), patch.object(remote, 'sql', side_effect=capture):
            first = remote.reviewed_claim('space', target, 'targets', execute=True)
            value['job'].update(state='running', attempts=3, updated_at='later')
            resumed = remote.reviewed_claim('space', target, 'targets', execute=True)
        self.assertEqual(first, resumed); self.assertEqual(first['start_index'], 67)
        self.assertEqual(first['cache_scope'], first['command_id'])
        self.assertNotEqual(first['previous_command_id'], first['command_id'])
        for query in queries:
            resume = query.split('IF FOUND THEN ', 1)[1].split('ELSE ', 1)[0]
            self.assertIn('old.request IS DISTINCT FROM', resume)
            self.assertIn('old.result IS DISTINCT FROM', resume)
            self.assertIn('j.attempts<>3', resume)
            self.assertIn("j.reason='provider_outcome_unknown'", resume)
            self.assertNotIn('validation_failed', resume)
            self.assertNotIn('INSERT INTO', resume)
            self.assertIn('FOR UPDATE', query)
            self.assertIn('previous_job', query)
            self.assertIn('attempts=3', query)
            self.assertNotIn('UPDATE wm_model_calls', query)
            self.assertNotIn('DELETE', query)

    def test_fresh_reviewed_attempt_starts_at_67_preserves_old_history_and_resumes_without_send(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); old = root / '66/response.json'; old.parent.mkdir(); old.write_bytes(b'old reviewed response')
            fresh = root / 'attempts/new-command'
            api, sends = self.setup_api(fresh, {'cost': 50, 'stop_reason': 'end_turn'}, start=67)
            old_rows = api.store.old
            api('unchanged normal prompt', api.provider.MODEL)
            self.assertEqual(api.receipts[0]['call_index'], 67)
            resumed = paid.PaidCalls(api.store, fresh, api.job, api.pipeline, api.revision, 67, {},
                                     api.provider, api.budget, lease_token='lease')
            resumed('unchanged normal prompt', api.provider.MODEL)
            self.assertEqual(len(sends), 1)
            self.assertEqual(old.read_bytes(), b'old reviewed response')
            self.assertEqual(json.dumps({k:v for k,v in api.store.rows.items() if k<67}, sort_keys=True), old_rows)

    def test_reviewed_attempt_paths_do_not_replace_old_failure_or_receipts(self):
        sys.path[:0] = [str(ROOT.parent / 'replay/overlay'), str(ROOT.parent / 'replay/private/runtime')]
        worker = load('container_worker'); command = '2f6e579c-4e43-51fc-9b76-cb733053fead'
        base, attempt, ledger = worker.attempt_paths('/cache/projections', 'job', {'command_id': command, 'cache_scope': command})
        self.assertEqual(str(base), '/cache/projections/worker-reprocess22/job')
        self.assertEqual(attempt, base / 'attempts' / command)
        self.assertEqual(str(ledger), '/cache/reprocess22-reservations/job/attempts/' + command)
        self.assertEqual(worker.attempt_paths('/cache/projections', 'job', {})[:2], (base, base))
        with self.assertRaises((AssertionError, ValueError)):
            worker.attempt_paths('/cache', 'job', {'command_id': command, 'cache_scope': '../escape'})

    def test_multiple_attempt_costs_have_unique_contiguous_ranges(self):
        spec = importlib.util.spec_from_file_location('audit_final', ROOT.parent / 'audit/reprocess22-final.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        namespace = {}; exec(module.REMOTE, namespace); ranges = namespace['call_ranges']
        attempts = [{'command_id': 'original', 'start_index': 1}, {'command_id': 'reviewed', 'start_index': 67}]
        calls = [{'call_index': i, 'actual_micro_usd': 1} for i in range(1, 70)]
        result = ranges(attempts, calls)
        self.assertEqual([(r['start_index'], r['end_index'], r['calls']) for r in result], [(1, 66, 66), (67, 69, 3)])
        self.assertEqual(sum(r['actual_micro_usd'] for r in result), 69)
        for bad_attempts, bad_calls in ((attempts, calls + [calls[-1]]), (attempts, calls[:-4]),
                                        (attempts + [attempts[-1]], calls), (attempts, calls[1:])):
            with self.assertRaises(ValueError): ranges(bad_attempts, bad_calls)
        self.assertNotIn('JOIN wm_job_decisions d', module.REMOTE)
        self.assertIn('AND EXISTS(SELECT 1 FROM wm_job_decisions d', module.REMOTE)
        self.assertIn("ledger.rglob('receipt.json')", module.REMOTE)

    def test_token_case_is_separately_bound_to_known_completion_and_new_slot_2(self):
        remote = load('remote'); case = remote.TOKEN_FAILURE
        target = {'id': case['job_id'], 'space_id': 'space', 'source_id': 'source',
                  'document_id': 'document', 'body_hash': paid.sha('body')}
        value = {'config': {'pipeline': 'pipeline'}, 'job': {'id': target['id'], 'space_id': 'space'},
                 'document': {'id': 'document', 'source_id': 'source', 'body_hash': target['body_hash'], 'body': 'body'}}
        queries = []
        def capture(query, **kwargs):
            queries.append(query)
            return base64.b64decode(re.findall(r"convert_from\(decode\('([A-Za-z0-9+/=]+)'", query)[-1]).decode()
        with patch.object(remote, 'snapshot', return_value=value), patch.object(remote, 'sql', side_effect=capture):
            first = remote.reviewed_claim('space', target, 'targets', execute=True)
            resumed = remote.reviewed_claim('space', target, 'targets', execute=True)
        self.assertEqual(first, resumed); self.assertEqual(first['start_index'], 2)
        self.assertEqual(first['revision'], 355); self.assertEqual(first['token_override'], paid.TOKEN_OVERRIDE)
        self.assertNotEqual(first['command_id'], first['previous_command_id'])
        for query in queries:
            for guard in ('s.revision<>355', 'n<>2', 'call_index=1', 'actual_micro_usd=149115',
                          "incomplete_reason'='max_output_tokens'", "usage_final'='true'", 'j.attempts<>3', 'call_index>=2', 'token attempt already ended'):
                self.assertIn(guard, query)
            self.assertNotIn('UPDATE wm_model_calls', query)
        remote, target, value = self.reviewed_fixture()
        with patch.object(remote, 'snapshot', return_value=value), patch.object(remote, 'sql', side_effect=capture):
            source15 = remote.reviewed_claim('space', target, 'targets', execute=True)
        self.assertEqual(source15['start_index'], 67); self.assertNotIn('token_override', source15)
        self.assertNotEqual(first['cache_scope'], source15['cache_scope'])

    def token_api(self, folder, prompt='normal extract'):
        api, sends = self.setup_api(folder, {'cost': 50, 'stop_reason': 'end_turn'}, start=2)
        api.job, api.revision = paid.TOKEN_JOB, 355
        value = {'model': api.provider.MODEL, 'prompt': prompt, 'max_tokens': 24000, 'schema': {},
                 'scope': {'mode': 'bounded_recovery_generation', 'job_id': api.job,
                           'pipeline': api.pipeline, 'revision': api.revision}}
        override = {**paid.TOKEN_OVERRIDE, 'request_hash': paid.sha(paid.encode(value))}
        return api, sends, override

    def test_exact_token_override_reserves_sends_and_reuses_48000_without_changing_old_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            api, sends, override = self.token_api(folder); observed = []
            old = paid.encode(api.store.rows)
            api.token_override = override
            api.budget.reserve_micro_usd = lambda prompt, model, maximum, schema, **kwargs: observed.append(('reserve', maximum)) or maximum
            api.provider.request = lambda prompt, model, **kwargs: observed.append(('send', kwargs['max_tokens'])) or {'cost':50,'stop_reason':'end_turn'}
            api('normal extract', api.provider.MODEL)
            self.assertEqual(observed, [('reserve',48000),('send',48000)])
            request = json.loads(api.store.rows[2]['request_json'])
            self.assertEqual(request['max_tokens'],48000)
            self.assertEqual(api.store.rows[2]['request_hash'],paid.sha(paid.encode(request)))
            self.assertEqual(api.store.rows[2]['reserved_micro_usd'],48000)
            self.assertEqual(paid.encode({k:v for k,v in api.store.rows.items() if k<2}),old)
            with patch.object(paid, 'TOKEN_OVERRIDE', override):
                resumed = paid.PaidCalls(api.store, folder, api.job, api.pipeline, 355, 2, {}, api.provider, api.budget,
                                         lease_token='lease', token_override=override)
                resumed('normal extract',api.provider.MODEL)
            self.assertEqual(observed, [('reserve',48000),('send',48000)])
            api('gate',api.provider.MODEL,max_tokens=12000)
            self.assertEqual(observed[-2:],[('reserve',12000),('send',12000)])

    def test_token_override_hash_context_and_cross_source_fail_before_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            api,sends,override=self.token_api(folder);api.token_override=override
            with self.assertRaisesRegex(ValueError,'request changed'):api('different prompt',api.provider.MODEL)
            self.assertEqual(sends,[]);self.assertEqual(api.store.events,[])
            for job,revision,start,change in ((api.job,354,2,{}),('other',355,2,{}),(api.job,355,67,{}),
                                               (api.job,355,2,{'to_max_tokens':96000})):
                with patch.object(paid,'TOKEN_OVERRIDE',override),self.assertRaisesRegex(ValueError,'scope'):
                    paid.PaidCalls(api.store,folder,job,api.pipeline,revision,start,{},api.provider,api.budget,
                                   lease_token='lease',token_override={**override,**change})
        with tempfile.TemporaryDirectory() as folder:
            prompt='x'*220001;api,sends,override=self.token_api(folder,prompt);api.token_override=override
            with self.assertRaisesRegex(ValueError,'context'):api(prompt,api.provider.MODEL)
            self.assertEqual(sends,[]);self.assertEqual(api.store.events,[])

    def test_token_override_unknown_reply_never_resends_and_larger_budget_is_enforced(self):
        with tempfile.TemporaryDirectory() as folder:
            api,sends,override=self.token_api(folder);api.token_override=override
            api.provider.request=lambda *args,**kwargs:sends.append(1) or {'cost':None,'terminal_status':'incomplete'}
            with self.assertRaises(paid.PaidOutcomeUnknown):api('normal extract',api.provider.MODEL)
            with patch.object(paid,'TOKEN_OVERRIDE',override):
                resumed=paid.PaidCalls(api.store,folder,api.job,api.pipeline,355,2,{},api.provider,api.budget,
                                       lease_token='lease',token_override=override)
                with self.assertRaises(paid.PaidOutcomeUnknown):resumed('normal extract',api.provider.MODEL)
            self.assertEqual(sends,[1])
        with tempfile.TemporaryDirectory() as folder:
            api,sends,override=self.token_api(folder);api.token_override=override
            api.store.ceiling=30000
            api.budget.reserve_micro_usd=lambda prompt,model,maximum,schema,**kwargs:maximum
            with self.assertRaisesRegex(RuntimeError,'budget'):api('normal extract',api.provider.MODEL)
            self.assertEqual(sends,[])

    def test_known_token_failure_cost_is_counted_once_across_attempt_ranges(self):
        spec=importlib.util.spec_from_file_location('audit_final',ROOT.parent/'audit/reprocess22-final.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        namespace={};exec(module.REMOTE,namespace)
        result=namespace['call_ranges']([{'command_id':'old','start_index':1},{'command_id':'new','start_index':2}],
                                       [{'call_index':1,'actual_micro_usd':149115},{'call_index':2,'actual_micro_usd':200000}])
        self.assertEqual([(r['start_index'],r['end_index']) for r in result],[(1,1),(2,2)])
        self.assertEqual(sum(r['actual_micro_usd'] for r in result),349115)

    def test_tmpfs_code_writer_transfers_stdin_and_rejects_other_names(self):
        remote = load('remote')
        with tempfile.TemporaryDirectory() as folder:
            real_path = Path(folder)
            def mapped(value):
                self.assertEqual(value, '/tmp/owner-reprocess22')
                return real_path
            with patch('pathlib.Path', side_effect=mapped), patch.object(sys, 'argv', ['writer', 'paid_calls.py']), patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'public-code'))):
                exec(remote.CODE_WRITER, {})
            self.assertEqual((real_path / 'paid_calls.py').read_bytes(), b'public-code')
            with patch.object(sys, 'argv', ['writer', '../other.py']), self.assertRaises(AssertionError):
                exec(remote.CODE_WRITER, {})

    def setup_api(self, directory, response, start=9):
        calls = []
        def send(*args, **kwargs): calls.append(1); return response
        provider = SimpleNamespace(MODEL='gpt-6.1-sol', count_input_tokens=lambda *args: 10, request=send)
        budget = SimpleNamespace(reserve_micro_usd=lambda *args, **kwargs: 200,
                                 usage_micro_usd=lambda response, model: response.get('cost'))
        store = LedgerStore(start=start)
        return paid.PaidCalls(store, directory, 'a' * 64, 'pipeline', 340, start, {}, provider, budget, lease_token='lease'), calls

    def test_success_is_durable_and_reused_without_send(self):
        with tempfile.TemporaryDirectory() as folder:
            api, calls = self.setup_api(folder, {'cost': 50, 'stop_reason': 'end_turn', 'usage': {}})
            api('prompt', 'gpt-6.1-sol'); self.assertEqual(len(calls), 1)
            resumed, more = self.setup_api(folder, {})
            resumed('prompt', 'gpt-6.1-sol'); self.assertEqual(more, [])
            self.assertEqual(len(resumed.receipts), 1)

    def test_uncertain_response_cannot_send_twice_or_skip_to_new_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            api, calls = self.setup_api(folder, {'cost': None, 'error': 'ValueError'})
            with self.assertRaises(paid.PaidOutcomeUnknown): api('prompt', 'gpt-6.1-sol')
            resumed, more = self.setup_api(folder, {})
            with self.assertRaises(paid.PaidOutcomeUnknown): resumed('changed prompt', 'gpt-6.1-sol')
            self.assertEqual(len(calls), 1); self.assertEqual(more, [])

    def test_crash_after_response_before_receipt_recovers_cost_without_send(self):
        with tempfile.TemporaryDirectory() as folder:
            api, calls = self.setup_api(folder, {'cost': 50, 'stop_reason': 'end_turn', 'usage': {}})
            api('prompt', 'gpt-6.1-sol')
            (Path(folder) / '9/receipt.json').unlink()
            resumed, more = self.setup_api(folder, {})
            self.assertEqual(resumed.receipts, [])
            resumed('prompt', 'gpt-6.1-sol')
            self.assertEqual(more, [])
            self.assertEqual(len(resumed.receipts), 1)
            self.assertEqual(resumed.receipts[0]['actual_micro_usd'], 50)

    def test_normal_1024th_index_stops_before_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            api, calls = self.setup_api(folder, {})
            api.index = 1024
            with self.assertRaisesRegex(RuntimeError, 'boundary'): api('prompt', 'gpt-6.1-sol')
            self.assertEqual(calls, [])

    def test_normal_slot_1023_allowed_then_1024_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            api, calls = self.setup_api(folder, {'cost': 50, 'stop_reason': 'end_turn'}, start=1023)
            api('last', 'gpt-6.1-sol')
            self.assertEqual(len(calls), 1)
            with self.assertRaisesRegex(RuntimeError, 'boundary'): api('over', 'gpt-6.1-sol')
            self.assertEqual(len(calls), 1)

    def test_existing_accounted_budget_is_enforced_before_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            api, calls = self.setup_api(folder, {})
            api.store = LedgerStore(ceiling=250, accounted=100)
            with self.assertRaisesRegex(paid.ContextBudgetExceeded, 'budget') as caught: api('prompt', 'gpt-6.1-sol')
            self.assertIsInstance(caught.exception, RuntimeError)
            self.assertIs(api.last_metadata['generation_sent'], False)
            self.assertEqual(calls, [])

    def test_purged_response_body_never_removes_single_send_reservation(self):
        with tempfile.TemporaryDirectory() as folder:
            body, ledger = Path(folder) / 'body', Path(folder) / 'ledger'
            api, calls = self.setup_api(body, {'cost': 50, 'stop_reason': 'end_turn', 'usage': {}})
            api.ledger = ledger; ledger.mkdir()
            api('private prompt', 'gpt-6.1-sol')
            self.assertNotIn('private prompt', (ledger / '9/reservation.json').read_text())
            shutil.rmtree(body)
            resumed = paid.PaidCalls(api.store, body, api.job, api.pipeline, api.revision, 9, {},
                                     api.provider, api.budget, ledger_directory=ledger, lease_token='lease')
            with self.assertRaises(paid.PaidOutcomeUnknown): resumed('private prompt', 'gpt-6.1-sol')
            with self.assertRaises(paid.PaidOutcomeUnknown): resumed('different prompt', 'gpt-6.1-sol')
            self.assertEqual(len(calls), 1)

    def test_32_known_receipts_import_in_order_without_provider_then_33rd_is_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            api, sends = self.setup_api(folder, {'cost': 50, 'stop_reason': 'end_turn', 'usage': {}}, start=1)
            for i in range(32): api('prompt' + str(i), 'gpt-6.1-sol')
            imported, calls = self.setup_api(folder, {'cost': 50, 'stop_reason': 'end_turn', 'usage': {}}, start=1)
            old = json.dumps(imported.store.rows, sort_keys=True)
            result = imported.import_known()
            self.assertEqual(result, {'imported': 32, 'actual_micro_usd': 1600})
            self.assertEqual(calls, [])
            self.assertEqual(json.dumps({i: imported.store.rows[i] for i in range(1)}, sort_keys=True), old)
            self.assertEqual(len(imported.store.rows), 33)
            self.assertEqual(imported.store.events, ['reserve_call', 'receive_call'] * 32)
            resumed = paid.PaidCalls(imported.store, folder, imported.job, imported.pipeline, imported.revision,
                                     1, {}, imported.provider, imported.budget, lease_token='lease')
            self.assertEqual(resumed.start_index, 1)
            self.assertEqual(resumed.index, 33)
            resumed.import_known()
            self.assertEqual(calls, [])
            resumed('prompt32', 'gpt-6.1-sol')
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(resumed.receipts), 33)
            self.assertEqual(resumed.index, 34)

    def test_reserved_server_slot_without_response_never_sends(self):
        with tempfile.TemporaryDirectory() as folder:
            api, calls = self.setup_api(folder, {'cost': 50, 'stop_reason': 'end_turn'})
            value = {'model': api.provider.MODEL, 'prompt': 'prompt', 'max_tokens': 24000, 'schema': {},
                     'scope': {'mode': 'bounded_recovery_generation', 'job_id': api.job,
                               'pipeline': api.pipeline, 'revision': api.revision}}
            api.store.rows[9] = {'request_json': paid.encode(value), 'request_hash': paid.sha(paid.encode(value)),
                                 'response_json': None, 'actual_micro_usd': None, 'reserved_micro_usd': 200}
            with self.assertRaises(paid.PaidOutcomeUnknown): api('prompt', api.provider.MODEL)
            self.assertEqual(calls, [])

    def test_import_rejects_changed_response_cost_before_sql_and_never_sends(self):
        with tempfile.TemporaryDirectory() as folder:
            api, _ = self.setup_api(folder, {'cost': 50, 'stop_reason': 'end_turn', 'usage': {}})
            api('prompt', api.provider.MODEL)
            body = Path(folder) / '9/response.json'; value = json.loads(body.read_text()); value['cost'] = 51
            body.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'hash'): self.setup_api(folder, {})

    def test_claim_freezes_start_index_and_records_original_job_without_resetting_calls(self):
        remote = load('remote'); queries = []
        target = {'id': 'a' * 64, 'space_id': 's', 'source_id': 'source', 'document_id': 'doc',
                  'body_hash': paid.sha('body'), 'updated_at': '2026-10-14T00:00:00+00:00'}
        run = {'start_index': 1, 'revision': 341, 'lease_token': 'lease'}
        with patch.object(remote, 'snapshot', return_value={'config': {'pipeline': 'current'}, 'job': {'id': target['id'], 'space_id': 's', 'source_id': 'source', 'document_id': 'doc'}, 'document': {'id': 'doc', 'source_id': 'source', 'body_hash': target['body_hash'], 'body': 'body'}}), \
                patch.object(remote, 'sql', side_effect=lambda q: queries.append(q) or json.dumps(run)):
            result = remote.claim_run('s', target, 'snapshot')
        self.assertEqual(result['start_index'], 1)
        query = queries[0]
        self.assertIn('FOR UPDATE', query); self.assertIn('previous_job', query)
        self.assertIn('INSERT INTO wm_job_decisions', query)
        self.assertIn('start_index', query); self.assertIn('response_json IS NULL', query)
        self.assertNotIn('DELETE', query); self.assertNotIn('UPDATE wm_model_calls', query)

    def test_pause_and_adoption_share_the_same_guarded_transaction(self):
        remote = load('remote'); queries = []
        target = {'id': 'a' * 64, 'body_hash': 'body'}
        artifact = {'job_id': target['id'], 'body_hash': 'body', 'expected_revision': 341,
                    'expected_updated_at': 'time', 'pipeline': 'pipeline', 'lease_token': 'lease',
                    'owner_reprocess_command': 'owner', 'generation': {'new_sources': [{'id': target['id']}], 'review_sha256': 'hash'},
                    'review_id': 'review', 'command_id': 'command', 'reason': 'reason', 'note': {}}
        with patch.object(remote, 'sql', side_effect=lambda q: queries.append(q) or ''), \
                patch.object(remote, 'snapshot', return_value={'space': {'revision': 342}, 'job': {'state': 'applied'}}):
            self.assertEqual(remote.adopt('s', target, artifact), 342)
        self.assertEqual(len(queries), 1); query = queries[0]
        self.assertTrue(query.startswith('BEGIN ISOLATION LEVEL SERIALIZABLE'))
        self.assertLess(query.index('PERFORM wm_pause_job'), query.index('PERFORM wm_generation_stage'))
        self.assertLess(query.index('wm_generation_stage'), query.index('wm_generation_decide'))
        self.assertTrue(query.endswith('COMMIT;'))

    def test_unknown_model_and_target_drift_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            api, calls = self.setup_api(folder, {})
            with self.assertRaises(ValueError): api('prompt', 'other-model')
            self.assertEqual(calls, [])
        remote = load('remote')
        with self.assertRaises(AssertionError): remote.guard({'job': None, 'document': None, 'config': {}}, {}, False)

    def test_actual_generation_borrowed_projection_contract(self):
        sys.path[:0] = [str(ROOT.parent / 'replay/overlay'), str(ROOT.parent / 'replay/private/runtime')]
        worker = load('container_worker')
        from memory import fingerprint
        from journal_projection import prepare_source
        current, _ = worker.materialize([])
        body = 'Gleb: Der Bericht liegt vor.'
        source_id = 'synthetic:contract'
        source = {'source_id': source_id, 'content_hash': fingerprint(body),
                  'id': fingerprint(source_id + ':' + fingerprint(body)), 'transcript': body,
                  'event_date': '2026-10-01', 'observed_at': '2026-10-01T09:00:00+00:00', 'title': 'Fixture'}
        payload = prepare_source(current, source, {'observations': [], 'coverage_notes': []},
                                 pipeline='fixture', model='fixture', provenance={'mode': 'fixture'})
        entry = {'kind': 'source', 'source': source, 'payload': payload}
        try:
            generation, prepared = worker.checked_generation([], [entry], {source_id: 'Fixture'}, current, 'Fixture')
            self.assertEqual(len(generation['new_sources']), 1)
            self.assertEqual(generation['personal_decisions_preserved'], 0)
            self.assertEqual(len(prepared), 1)
            self.assertEqual(current.execute('SELECT 1').fetchone()[0], 1)
        finally:
            current.close()


if __name__ == '__main__': unittest.main()
