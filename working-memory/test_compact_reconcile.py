import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from compact_reconcile import Catalog, _packed_candidates, preview, response_schema, run
from hybrid_index import encode
from hybrid_pipeline import (COMPACT_CHARS, CONFIDENCE, CONTEXT_FRAMING_TOKENS, GPT6_MAX_INPUT_TOKENS,
                             TERRA_CONTEXT_TOKENS, context_exceeds_budget)
from memory import ValidationError
from processor import units
from retrieval_context import pack_catalog, unpack_catalog, pack_batches
from test_memory import observation


class PackingTests(unittest.TestCase):
    def test_terra_compact_budget_counts_utf8_schema_framing_and_output(self):
        schema = {'enum': ['ä'*10000]}
        fixed = (len(json.dumps(schema, ensure_ascii=False).encode())
                 + CONTEXT_FRAMING_TOKENS + 128000)
        prompt = 'x'*(TERRA_CONTEXT_TOKENS-fixed)
        self.assertFalse(context_exceeds_budget('compact-0', prompt, schema, 128000,
                                                'gpt-5.6-terra', True))
        self.assertTrue(context_exceeds_budget('compact-0', prompt+'🙂', schema, 128000,
                                               'gpt-5.6-terra', True))
        for model in ('gpt-6-sol', 'gpt-6-luna'):
            self.assertFalse(context_exceeds_budget('compact-0', prompt, schema, 128000, model, True))
            self.assertTrue(context_exceeds_budget('compact-0', prompt+'🙂', schema, 128000, model, True))

    def test_gpt6_compact_accepts_420k_and_checks_input_separately(self):
        for model in ('gpt-6-sol', 'gpt-6-luna'):
            self.assertFalse(context_exceeds_budget('compact-0', 'x'*420000, {}, 17800, model, True))
            prompt='x'*(GPT6_MAX_INPUT_TOKENS-len(json.dumps({}).encode())-CONTEXT_FRAMING_TOKENS)
            self.assertFalse(context_exceeds_budget('compact-0', prompt, {}, 128000, model, True))
            self.assertTrue(context_exceeds_budget('compact-0', prompt+'x', {}, 1, model, True))

    def test_gpt6_noncompact_checks_encoded_input_and_schema(self):
        prompt='🙂'*220000
        schema={'enum':['x'*40000]}
        for model in ('gpt-6-sol', 'gpt-6-luna'):
            self.assertFalse(context_exceeds_budget('extract', '🙂'*100000, schema, 18000, model, False))
            self.assertTrue(context_exceeds_budget('extract', prompt, schema, 18000, model, False))
            self.assertTrue(context_exceeds_budget('align-0', prompt, schema, 18000, model, True))
        self.assertFalse(context_exceeds_budget('extract', prompt, schema, 18000, 'gpt-5.6-terra', False))

    def test_other_models_keep_existing_compact_character_guard(self):
        self.assertFalse(context_exceeds_budget('compact-0', 'x'*COMPACT_CHARS, {}, 1,
                                                'other-model', True))
        self.assertTrue(context_exceeds_budget('compact-0', 'x'*(COMPACT_CHARS+1), {}, 1,
                                               'other-model', True))

    def test_round_trip_keeps_null_missing_numbers_false_unicode_and_source_versions(self):
        value = {'work': [{'id': 'a', 'claim': 'Nicht erledigt. Ä🙂', 'due': None, 'n': 3, 'ok': False},
                          {'id': 'b', 'claim': 'Nicht erledigt. Ä🙂', 'n': 4}],
                 'search_hits': [{'id': 'c', 'source_version': '1', 'text': 'gleich'},
                                 {'id': 'd', 'source_version': '2', 'text': 'gleich'}],
                 'rule': 'Beleg erforderlich'}
        self.assertEqual(unpack_catalog(pack_catalog(value)), value)

    def test_invalid_text_reference_fails_closed(self):
        value = pack_catalog({'work': [{'title': 'a'}]})
        value['tables']['work']['rows'][0][0] = 999
        with self.assertRaises(ValidationError):
            unpack_catalog(value)

    def test_pack_preserves_indices_and_refuses_oversized_singleton(self):
        items = [(2, 'x'), (0, 'y'), (1, 'z')]
        batches = pack_batches(items, lambda b: 'a'*(len(b)*3), 6)
        self.assertEqual(sorted(i for b in batches for i, _ in b), [0, 1, 2])
        with self.assertRaises(ValidationError):
            pack_batches(items, lambda b: 'long', 2)

    def test_compact_candidates_pack_full_work_losslessly(self):
        work = [{'id': 'W'+str(i), 'work_index': str(i), 'title': 'Monatsbericht',
                 'claim': 'Vollständige wiederholte Aufgabenbeschreibung',
                 'condition_text': None, 'required_review': False} for i in range(400)]
        archive = pack_catalog({'search_hits': []})
        packed = _packed_candidates(work, archive)
        self.assertEqual(unpack_catalog(packed), {'work': work, 'archive_navigation': archive})
        self.assertLess(len(encode(packed)), len(encode({'work': work, 'archive_navigation': archive}))-3650)


class CatalogTests(unittest.TestCase):
    def catalog(self):
        hits = {'p': {'id': 'p', 'kind': 'passage', 'target_id': 'source-v1',
                      'text': 'X'*350+' NEGATION: nicht erledigt. '+'Y'*400,
                      'metadata': {'matter_id': 'real-matter'}, 'event_date': '2025-01-01'}}
        return Catalog([{'id': 'real-task', 'title': 'Zugang freischalten',
                         'claim': 'Zugang nach beiden Freigaben freischalten',
                         'condition_text': 'Beide Freigaben', 'original_commitment_evidence': ['Beleg']}],
                       hits, {'Zugang': hits})

    def test_preview_explicitly_shortened_and_full_open_exact(self):
        c = self.catalog()
        first = c.render(set())
        self.assertTrue(first['search_hits'][0]['preview_only'])
        self.assertEqual(c.render({'H0'})['search_hits'][0]['text'], c.hits[0]['text'])
        self.assertFalse(c.render({'H0'})['search_hits'][0]['preview_only'])
        self.assertEqual(first['work'][0]['condition_text'], 'Beide Freigaben')
        self.assertEqual(first['work'][0]['work_index'], '0')

    def test_old_semantic_candidate_without_common_keywords_is_never_dropped(self):
        c = self.catalog()
        self.assertEqual(len(c.render(set())['work']), 1)
        self.assertEqual(len(c.render(set())['search_hits']), 1)
        self.assertEqual(c.render(set())['search_hits'][0]['event_date'], '2025-01-01')

    def test_alias_restoration_and_unknown_ids(self):
        c = self.catalog()
        value = {'observations': [{'update_target': 'W0', 'matter_id': 'M0'}]}
        self.assertEqual(c.decode(value)['observations'][0],
                         {'update_target': 'real-task', 'matter_id': 'real-matter'})
        value['observations'][0]['update_target'] = 'foreign'
        with self.assertRaises(ValidationError):
            c.decode(value)

    def test_preview_cannot_authorize_topic_without_opening(self):
        c = self.catalog()
        response = {'observations': [{'matter_id': 'M0'}]}
        self.assertEqual(c.required_open(response, set()), {'H0'})
        self.assertEqual(c.required_open(response, {'H0'}), set())

    def test_empty_search_contract_allows_no_archive_request(self):
        schema = response_schema(Catalog([], {}, {}), [0])
        self.assertEqual(schema['properties']['open_ids']['maxItems'], 0)

    def test_semantic_preview_has_no_keyword_requirement_and_keeps_original_untouched(self):
        text = 'Berechtigung wurde erteilt. '*50
        value, shortened = preview(text, 'Zugang freischalten')
        self.assertTrue(shortened)
        self.assertIn(value, text)


class CombinedContractTests(unittest.TestCase):
    def execute(self, replies):
        text = 'Gleb: Der Monatsbericht enthält zwölf Tabellen.'
        item = observation(kind='fact', commitment_strength='not_applicable',
                           due_text=None, evidence_ids=['U0001'], state_evidence_ids=[],
                           subject='Monatsbericht', search_keywords=['Tabellen'],
                           assignment_score=2, change_score=2, confidence_reason='Expliziter Beleg')
        original = units(text)
        calls = []
        def stage(name, prompt, schema, check, limit):
            calls.append(prompt)
            reply = replies[len(calls)-1]
            return check(copy.deepcopy(reply(item)))
        hit = {'id': 'h', 'kind': 'passage', 'text': 'Lange alte Aussage. '*80,
               'metadata': {'matter_id': 'matter'}}
        result = run(raw={'observations': [item]}, work=[], hits={'h': hit},
                     query_hits={'Monatsbericht': {'h': hit}}, originals=original,
                     meeting={'raw_transcript': text}, known=set(), stage=stage,
                     rules='Regeln', base='\nVollständiges Original:\n'+encode(original),
                     confidence_rules=CONFIDENCE)
        return result, calls

    @staticmethod
    def final(item):
        return {'open_ids': [], 'observations': [{**item, 'source_index': 0}],
                'coverage_notes': [], 'work_results': {}}

    def test_fact_kept_without_invented_work_and_complete_current_source(self):
        (result, stats), calls = self.execute([self.final])
        self.assertEqual(len(result['observations']), 1)
        self.assertEqual(result['observations'][0]['kind'], 'fact')
        self.assertEqual(stats['rounds'], 1)
        self.assertIn('Gleb: Der Monatsbericht enthält zwölf Tabellen.', calls[0])

    def test_requested_archive_opened_then_reconciled(self):
        (result, stats), calls = self.execute([
            lambda _: {'open_ids': ['H0'], 'observations': [], 'coverage_notes': [], 'work_results': None},
            self.final])
        self.assertEqual(stats['opened_hits'], 1)
        self.assertIn('Lange alte Aussage. '*80, calls[1])

    def test_duplicate_or_missing_observation_is_rejected(self):
        def bad(item):
            value = self.final(item); value['observations'] *= 2; return value
        with self.assertRaisesRegex(ValidationError, 'coverage'):
            self.execute([bad])

    def test_unknown_archive_id_and_partial_publication_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.execute([lambda _: {'open_ids': ['foreign'], 'observations': [],
                                     'work_results': None, 'coverage_notes': []}])
        def partial(item):
            value = self.final(item); value['open_ids'] = ['H0']; return value
        with self.assertRaises(ValidationError):
            self.execute([partial])


class PipelineIntegrationTests(unittest.TestCase):
    def test_uncertain_compact_update_does_not_require_internal_source_index(self):
        from hybrid_pipeline import process, resolve_v10
        from memory import apply, claim, connect, overview, register
        from test_memory import TEXT, proposal
        current = 'Gleb: Der Monatsbericht ist in Arbeit.'
        with tempfile.TemporaryDirectory() as temp:
            db = connect(Path(temp)/'db.sqlite')
            old = register(db, source_id='synthetic:old-report', event_date='2026-09-07',
                           title='Alter Bericht', transcript=TEXT)
            apply(db, old, claim(db, old), proposal(observation()), model='fixture')
            work_id = overview(db)['personal'][0]['id']
            extracted = observation(kind='fact', commitment_strength='not_applicable', owner=None,
                due_text=None, evidence_ids=['U0001'], state_evidence_ids=[],
                assignment_score=2, change_score=2, confidence_reason='Explizit erwähnt',
                subject='Monatsbericht', search_keywords=['Monatsbericht'])
            raw = {'observations':[extracted], 'coverage_notes':[], 'search_queries':[],
                   'meeting_summary':[{'text':'Der Monatsbericht ist in Arbeit.', 'evidence_ids':['U0001']}]}
            update = observation(kind='status', commitment_strength='not_applicable', owner=None,
                due_text=None, update_target=work_id, update='progress', evidence_ids=['U0001'],
                state_evidence_ids=[], assignment_score=1, change_score=2,
                confidence_reason='Historischer Bezug bleibt mehrdeutig', subject='Monatsbericht',
                search_keywords=['Monatsbericht'])
            compact = resolve_v10({'observations':[{**update, 'source_index':0}], 'coverage_notes':[]},
                                  units(current))
            compact['observations'][0].pop('source_index')
            class Index:
                def __init__(self, *args):pass
                def prepare(self, *args):return {'snapshot_id':'fixture'}
                def search(self, *args):
                    return [{'id':'work-hit','kind':'work','target_id':work_id,'metadata':{}}]
                def persist(self, *args):pass
            class API:
                store = object()
                def __call__(self, prompt, model, max_tokens=0, schema=None):
                    value = raw if schema is None else {'verdicts':[{
                        'index':0, 'verdict':'supported', 'evidence_ids':['U0001'],
                        'due_role':'none', 'duplicate_of':None, 'action_uncertainty':None,
                        'reason':'Der Fortschritt wird ausdrücklich genannt'}]}
                    return {'content':[{'type':'text','text':json.dumps(value)}],
                            'stop_reason':'end_turn', 'usage':{}}
            meeting = {'id':'compact-uncertain', 'source_id':'synthetic:compact-uncertain',
                       'title':'Berichtsstatus', 'meeting_date':'2026-09-08',
                       'raw_transcript':current}
            with patch('hybrid_pipeline.SearchIndex', Index), \
                 patch('compact_reconcile.run', return_value=(compact, {'rounds':1})):
                result = process(db, meeting, 'gpt-5.6-terra', api=API(), compact=True)
            self.assertEqual(result['status'], 'applied')
            db.close()

    def test_new_promise_uses_one_reconciliation_and_keeps_independent_gate(self):
        from hybrid_pipeline import process
        from memory import connect, overview
        text = 'Gleb: Ich sende Maria morgen den Monatsbericht.'
        item = observation(title='Monatsbericht senden', claim=text, owner='Gleb',
                           due_text='morgen', evidence_ids=['U0001'], state_evidence_ids=[],
                           subject='Monatsbericht', search_keywords=['Monatsbericht','senden'],
                           assignment_score=2, change_score=2, confidence_reason='Explizite Zusage')
        raw = {'observations':[item], 'coverage_notes':[], 'search_queries':[],
               'meeting_summary':[{'text':'Gleb sagt den Versand des Monatsberichts zu.', 'evidence_ids':['U0001']}]}
        class Index:
            def __init__(self, *args):pass
            def prepare(self, *args):return {'snapshot_id':'fixture'}
            def search(self, *args):return []
            def persist(self, *args):pass
        class API:
            store = object()
            def __init__(self):self.names=[]
            def __call__(self, prompt, model, max_tokens=0, schema=None):
                self.assert_source(prompt)
                if schema is None:
                    self.names.append('extract'); value=raw
                elif 'work_results' in schema['properties']:
                    self.names.append('compact')
                    value={'observations':[{**item,'source_index':0}], 'coverage_notes':[], 'open_ids':[], 'work_results':{}}
                else:
                    self.names.append('gate')
                    value={'verdicts':[{'index':0,'verdict':'supported','evidence_ids':['U0001'],
                                      'due_role':'work_deadline','duplicate_of':None,'action_uncertainty':None,
                                      'reason':'Expliziter Versand morgen'}]}
                return {'content':[{'type':'text','text':json.dumps(value)}], 'stop_reason':'end_turn', 'usage':{}}
            def assert_source(self, prompt):
                if text not in prompt:raise AssertionError('Complete current source missing')
        api=API()
        with tempfile.TemporaryDirectory() as temp:
            db=connect(Path(temp)/'db.sqlite')
            meeting={'id':'compact-fixture','source_id':'synthetic:compact-fixture','title':'Versand',
                     'meeting_date':'2026-09-08','raw_transcript':text}
            with patch('hybrid_pipeline.SearchIndex',Index):
                result=process(db,meeting,'gpt-5.6-terra',api=api,compact=True)
            self.assertEqual(api.names,['extract','compact','gate'])
            self.assertEqual(result['new_work'],1)
            task=overview(db)['personal'][0]
            self.assertEqual(task['search_keywords'],['Monatsbericht','senden'])
            self.assertEqual(task['due_text'],'morgen')
            db.close()


if __name__ == '__main__':
    unittest.main()
