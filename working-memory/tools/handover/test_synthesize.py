"""Offline acceptance: synthetic content only, mock transport, no environment secrets."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

SPEC = importlib.util.spec_from_file_location('synthesize', Path(__file__).with_name('synthesize.py'))
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


def fixture():
    value = {name: s.unknown() for name in s.FIELDS}
    value.update({name: [] for name in s.LISTS})
    value['worum'] = {'wert': 'Synthetische Prüfung', 'reife': 'belegt', 'belege': ['B1'], 'begruendung': '', 'zitat': 'Synthetische Prüfung'}
    return value


def package():
    return {'aufgabe': {'id': 'synthetic'}, 'belege': [{'id': 'B1', 'quelle': 'fixture', 'datum': '2026-01-01', 'text': 'Synthetische Prüfung. Vorlage vorhanden.'}]}


def response(value=None, usage=None):
    return {'status': 'completed', 'model': 'gpt-6.1-sol', 'service_tier': 'default', 'usage': usage or {'input_tokens': 10, 'output_tokens': 20}, 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(value or fixture())}]}]}


class EvidenceTests(unittest.TestCase):
    def test_evidence_bounds(self):
        p = {'belege': [{'id': 'B' + str(i), 'quelle': 'fixture' * 100, 'text': 'x' * 1000} for i in range(1, 50)]}
        ev = s.build_evidence(p)
        self.assertLessEqual(len(ev['block']), 12000)
        self.assertTrue(all(len(item['text']) <= 600 for item in ev['belege']))
        self.assertGreater(ev['gekuerzt'], 0)
        self.assertGreater(ev['ausgelassen'], 0)
        self.assertIn('Kürzung:', ev['block'])

    def test_original_package_paths(self):
        p = {'worum': {'wert': 'Synthetic statement', 'reife': 'belegt', 'belege': ['address']}, 'belege': [{'quelle': 'address', 'aussage': 'worum'}]}
        self.assertIn('Synthetic statement', s.build_evidence(p)['block'])

    def test_duplicate_id(self):
        p = package(); p['belege'].append(dict(p['belege'][0]))
        with self.assertRaises(ValueError): s.build_evidence(p)

    def test_prompt_rules(self):
        prompt = s.build_prompt(package())
        for text in ('AUFGABE:', 'BELEGE:', 'B1', 'untrusted', 'annahme', 'unbekannt', 'wiederverwendung', 'prüfbares Kriterium', 'Begründung'):
            self.assertIn(text, prompt)

    def test_prompt_task_bound(self):
        p = package(); p['aufgabe'] = {'claim': 'x' * 100000}
        self.assertLess(len(s.build_prompt(p)), 16000)
        self.assertIn('Aufgabe gekürzt', s.build_prompt(p))


class SchemaTests(unittest.TestCase):
    def test_valid_roundtrip(self):
        self.assertEqual(s.parse_response(json.dumps(fixture())), fixture())

    def test_strict_every_object(self):
        self.assertFalse(s.SCHEMA['additionalProperties'])
        for name in s.FIELDS:
            prop = s.SCHEMA['properties'][name]
            self.assertFalse(prop['additionalProperties'])
            self.assertEqual(set(prop['required']), set(prop['properties']))

    def test_extra_key(self):
        f = fixture(); f['extra'] = 1
        with self.assertRaises(ValueError): s.parse_response(json.dumps(f))

    def test_missing_key(self):
        f = fixture(); del f['worum']['zitat']
        with self.assertRaises(ValueError): s.parse_response(json.dumps(f))

    def test_bad_enum(self):
        f = fixture(); f['art']['wert'] = 'invented'
        with self.assertRaises(ValueError): s.parse_response(json.dumps(f))

    def test_bad_type(self):
        f = fixture(); f['scope']['belege'] = 'B1'
        with self.assertRaises(ValueError): s.parse_response(json.dumps(f))

    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError): s.parse_response('{"worum":1,"worum":2}')

    def test_questions_maximum(self):
        f = fixture(); f['offene_fragen'] = [s.unknown()] * 6
        with self.assertRaises(ValueError): s.parse_response(json.dumps(f))

    def test_quote_nullable(self):
        f = fixture(); f['worum']['zitat'] = None
        self.assertEqual(s.parse_response(json.dumps(f)), f)


class GroundTests(unittest.TestCase):
    def check(self, f): return s.ground_check(f, s.build_evidence(package()))

    def test_positive(self):
        f, count = self.check(fixture()); self.assertEqual(count, 0); self.assertEqual(f, fixture())

    def test_invented_id(self):
        f = fixture(); f['worum']['belege'] = ['B999']
        cleaned, count = self.check(f)
        self.assertGreater(count, 0); self.assertEqual(cleaned['worum'], s.unknown())

    def test_missing_quote(self):
        f = fixture(); f['worum']['zitat'] = 'invented phrase'
        cleaned, count = self.check(f)
        self.assertEqual(count, 1); self.assertEqual(cleaned['worum'], s.unknown())

    def test_belegt_without_id(self):
        f = fixture(); f['worum']['belege'] = []; f['worum']['zitat'] = None
        cleaned, count = self.check(f)
        self.assertEqual(count, 1); self.assertEqual(cleaned['worum'], s.unknown())

    def test_assumption_requires_reason(self):
        f = fixture(); f['worum']['reife'] = 'annahme'
        cleaned, count = self.check(f)
        self.assertEqual(count, 1); self.assertEqual(cleaned['worum'], s.unknown())

    def test_unknown_not_hidden_claim(self):
        f = fixture(); f['scope']['wert'] = 'Invented scope'
        cleaned, count = self.check(f)
        self.assertEqual(count, 1); self.assertEqual(cleaned['scope']['wert'], 'unbekannt')

    def test_reuse_requires_quote(self):
        f = fixture(); f['wiederverwendung'] = [dict(f['worum'], zitat=None)]
        cleaned, count = self.check(f)
        self.assertEqual(count, 1); self.assertEqual(cleaned['wiederverwendung'], [])

    def test_way_requires_reason(self):
        f = fixture(); f['bearbeitungsweg'] = dict(f['worum'], wert='ki')
        cleaned, count = self.check(f)
        self.assertEqual(count, 1); self.assertEqual(cleaned['bearbeitungsweg'], s.unknown())

    def test_no_mutation(self):
        f = fixture(); before = json.dumps(f)
        self.check(f); self.assertEqual(json.dumps(f), before)


class RenderTests(unittest.TestCase):
    def test_sections_and_suffixes(self):
        output = s.render_markdown(package(), fixture())
        for text in ('---', '## Scope', '## Kontext', '## Vorarbeiten/Vorgespräche', '## Wiederverwendung', '## Offene Fragen', '## Abnahme', '## Belege', '[belegt B1]', '[unbekannt]'):
            self.assertIn(text, output)
        self.assertNotIn("{'wert'", output)

    def test_large_render_limits(self):
        p = {'belege': [{'id': 'B' + str(i), 'quelle': '源' * 350, 'text': '文' * 600} for i in range(1, 30)]}
        f = fixture(); f['worum']['zitat'] = None
        for name in s.FIELDS:
            if name not in ('art', 'bearbeitungsweg'):
                f[name] = {'wert': '文' * 600, 'reife': 'annahme', 'belege': ['B1'], 'begruendung': '理' * 240, 'zitat': None}
        f['offene_fragen'] = [dict(f['worum']) for _ in range(5)]
        output = s.render_markdown(p, f)
        self.assertLessEqual(len(output.encode('utf-8')), 20000)
        self.assertLessEqual(len(output.splitlines()), 150)
        self.assertLessEqual(max(map(len, output.splitlines())), 400)
        self.assertIn('Kürzung:', output)

    def test_multiline_injection_escaped(self):
        f = fixture(); f['worum']['wert'] = 'first\n---\nnext'; f['worum']['zitat'] = None
        output = s.render_markdown(package(), f)
        self.assertEqual(output.splitlines().count('---'), 2)


class CostAndTransportTests(unittest.TestCase):
    def test_payload_contract(self):
        calls = []
        s.call_model('prompt', s.SCHEMA, lambda payload: calls.append(payload))
        p = calls[0]
        self.assertEqual(p['model'], 'gpt-6.1-sol'); self.assertEqual(p['service_tier'], 'default')
        self.assertEqual(p['reasoning'], {'effort': 'medium'})
        self.assertTrue(p['text']['format']['strict'])
        self.assertEqual(p['prompt_cache_options'], {'mode': 'explicit'})

    def test_prices_cache_write(self):
        self.assertEqual(s.usage_micro_usd({'input_tokens': 1000000, 'output_tokens': 0}), 2000000)
        self.assertEqual(s.usage_micro_usd({'input_tokens': 1000000, 'output_tokens': 0, 'input_tokens_details': {'cached_tokens': 1000000}}), 100000)
        self.assertEqual(s.usage_micro_usd({'input_tokens': 1000000, 'output_tokens': 0, 'input_tokens_details': {'cache_write_tokens': 1000000}}), 2500000)
        self.assertEqual(s.usage_micro_usd({'input_tokens': 0, 'output_tokens': 1000000}), 10000000)

    def test_invalid_usage(self):
        for usage in ({}, {'input_tokens': True, 'output_tokens': 1}, {'input_tokens': 1, 'output_tokens': 1, 'input_tokens_details': {'cached_tokens': 2}}):
            self.assertIsNone(s.usage_micro_usd(usage))

    def test_dryrun_no_calls(self):
        calls = []; out = io.StringIO()
        summary = s.run_inputs([('synthetic', package())], out, transport=lambda _: calls.append(1))
        self.assertEqual(calls, []); self.assertEqual(summary['actual_micro_usd'], 0)
        self.assertEqual(json.loads(out.getvalue())['status'], 'dry_run')
        self.assertGreater(summary['estimated_micro_usd'], 0)

    def test_utf8_upper_bound(self):
        p = s.model_payload('文' * 100, s.SCHEMA)
        self.assertGreaterEqual(s.estimate(p)['input_token_upper_bound'], len(json.dumps(p, ensure_ascii=False).encode('utf-8')))

    def test_budget_no_calls(self):
        calls = []; out = io.StringIO()
        summary = s.run_inputs([('synthetic', package())], out, execute=True, max_usd=0, transport=lambda _: calls.append(1))
        self.assertEqual(calls, []); self.assertEqual(summary['errors'], 1)
        self.assertEqual(json.loads(out.getvalue())['status'], 'budget_blocked')

    def test_invalid_cap(self):
        for cap in ('NaN', '-1', 'Infinity'):
            with self.assertRaises(ValueError): s.run_inputs([], io.StringIO(), max_usd=cap)

    def test_success_mock_raw(self):
        out = io.StringIO(); raw = response()
        summary = s.run_inputs([('synthetic', package())], out, execute=True, transport=lambda _: raw)
        record = json.loads(out.getvalue())
        self.assertEqual(summary['errors'], 0); self.assertEqual(json.loads(record['raw_response']), raw)
        self.assertEqual(record['status'], 'completed')

    def test_unknown_usage_stops(self):
        calls = []; out = io.StringIO(); raw = response(); raw['usage'] = {}
        def transport(_): calls.append(1); return raw
        summary = s.run_inputs([('a', package()), ('b', package())], out, execute=True, transport=transport)
        self.assertEqual(len(calls), 1); self.assertEqual(summary['errors'], 1)
        self.assertEqual(json.loads(json.loads(out.getvalue())['raw_response']), raw)

    def test_content_error_no_repeat(self):
        calls = []; out = io.StringIO(); raw = response(); raw['output'][0]['content'][0]['text'] = '{}'
        def transport(_): calls.append(1); return raw
        summary = s.run_inputs([('synthetic', package())], out, execute=True, transport=transport)
        self.assertEqual(len(calls), 1); self.assertEqual(summary['errors'], 1)

    def test_ground_violation_preserved(self):
        f = fixture(); f['worum']['belege'] = ['B999']; out = io.StringIO()
        summary = s.run_inputs([('synthetic', package())], out, execute=True, transport=lambda _: response(f))
        row = json.loads(out.getvalue())
        self.assertEqual(summary['errors'], 1); self.assertEqual(row['status'], 'ground_error')
        self.assertEqual(row['synthese']['worum'], s.unknown())

    def test_five_dryrun_under_cap(self):
        summary = s.run_inputs([(str(i), package()) for i in range(5)], io.StringIO())
        self.assertLessEqual(summary['estimated_micro_usd'], 600000)
        self.assertEqual(summary['inputs'], 5)

class RegressionTests(unittest.TestCase):
    def test_assumptions_not_evidence(self):
        p = {'worum': {'wert': 'Invented heuristic', 'reife': 'Annahme', 'belege': ['address']}, 'belege': [{'quelle': 'address', 'aussage': 'worum'}]}
        self.assertNotIn('Invented heuristic', s.build_evidence(p)['block'])

    def test_reuse_wrong_name_valid_quote(self):
        f = fixture(); f['wiederverwendung'] = [dict(f['worum'], wert='Invented report', zitat='Vorlage vorhanden.')]
        clean, count = s.ground_check(f, s.build_evidence(package()))
        self.assertEqual(count, 1); self.assertEqual(clean['wiederverwendung'], [])

    def test_exact_raw_string_preserved(self):
        raw = json.dumps(response(), indent=2) + '\n'
        out = io.StringIO()
        summary = s.run_inputs([('synthetic', package())], out, execute=True, transport=lambda _: raw)
        self.assertEqual(summary['errors'], 0)
        self.assertEqual(json.loads(out.getvalue())['raw_response'], raw)

    def test_huge_suffix_ids_rejected(self):
        f = fixture(); f['worum']['belege'] = ['B' + '9' * 1000]
        with self.assertRaises(ValueError): s.parse_response(json.dumps(f))

    def test_existing_cut_count(self):
        p = package(); p['belege'][0]['gekuerzte_zeichen'] = 123
        self.assertEqual(s.build_evidence(p)['gekuerzt'], 123)

    def test_maximum_unicode_all_sections_retained(self):
        p = {'belege': [{'id': 'B' + str(i), 'quelle': '源' * 350, 'text': '文' * 600} for i in range(1, 20)]}
        f = fixture()
        for name in s.FIELDS:
            f[name] = {'wert': ('review' if name == 'art' else 'ki' if name == 'bearbeitungsweg' else '文' * 600), 'reife': 'annahme', 'belege': ['B1'], 'begruendung': '理' * 240, 'zitat': None}
        for name in s.LISTS: f[name] = [dict(f['worum']) for _ in range(5)]
        rendered = s.render_markdown(p, f)
        self.assertLessEqual(len(rendered.encode()), 20000)
        self.assertLessEqual(len(rendered.splitlines()), 150)
        self.assertLessEqual(max(map(len, rendered.splitlines())), 400)
        for title in ('Scope', 'Kontext', 'Vorarbeiten/Vorgespräche', 'Wiederverwendung', 'Offene Fragen', 'Abnahme', 'Belege'):
            self.assertIn('## ' + title, rendered)

    def test_raw_error_retained(self):
        def transport(_): raise s.TransportError('synthetic raw error')
        out = io.StringIO(); summary = s.run_inputs([('synthetic', package())], out, execute=True, transport=transport)
        self.assertEqual(summary['errors'], 1)
        self.assertEqual(json.loads(out.getvalue())['raw_error'], 'synthetic raw error')

    def test_binding_in_result(self):
        out = io.StringIO(); s.run_inputs([('synthetic', package())], out)
        row = json.loads(out.getvalue())
        self.assertEqual(row['input_aufgabe'], package()['aufgabe'])
        self.assertEqual(row['input_belege'], s.build_evidence(package())['belege'])

class GoalGateRegressionTests(unittest.TestCase):
    def literal_case(self, text, quote):
        p = package(); p['belege'][0]['text'] = text
        evidence = s.build_evidence(p)
        self.assertIn(text, evidence['block'])
        self.assertIn(text, s.build_prompt(p))
        f = fixture(); f['worum']['zitat'] = quote
        clean, count = s.ground_check(f, evidence)
        self.assertEqual(count, 0)
        self.assertEqual(clean['worum']['zitat'], quote)

    def test_literal_newline_quote(self):
        self.literal_case('Synthetische\nPrüfung.', 'Synthetische\nPrüfung')

    def test_literal_multiple_spaces_quote(self):
        self.literal_case('Synthetische   Prüfung.', 'Synthetische   Prüfung')

    def test_literal_tab_quote(self):
        self.literal_case('Synthetische\tPrüfung.', 'Synthetische\tPrüfung')

    def test_nonliteral_whitespace_normalization_rejected(self):
        p = package(); p['belege'][0]['text'] = 'Synthetische\nPrüfung.'
        f = fixture(); f['worum']['zitat'] = 'Synthetische Prüfung'
        clean, count = s.ground_check(f, s.build_evidence(p))
        self.assertEqual(count, 1)
        self.assertEqual(clean['worum'], s.unknown())

    def test_empty_next_step_with_valid_id_rejected(self):
        f = fixture(); f['naechster'] = dict(f['worum'], wert='', zitat=None)
        clean, count = s.ground_check(f, s.build_evidence(package()))
        self.assertEqual(count, 1)
        self.assertEqual(clean['naechster'], s.unknown())

    def test_whitespace_done_criterion_assumption_rejected(self):
        f = fixture(); f['fertig_wenn'] = dict(f['worum'], wert=' \t\n', reife='annahme', begruendung='Synthetische Schlussfolgerung.', zitat=None)
        clean, count = s.ground_check(f, s.build_evidence(package()))
        self.assertEqual(count, 1)
        self.assertEqual(clean['fertig_wenn'], s.unknown())

class FinalReviewRegressionTests(unittest.TestCase):
    def test_url_error_full_detail(self):
        from urllib.error import URLError
        def transport(_): raise URLError('synthetic specific cause')
        out = io.StringIO(); s.run_inputs([('synthetic', package())], out, execute=True, transport=transport)
        row = json.loads(out.getvalue())
        self.assertEqual(row['error_type'], 'URLError')
        self.assertIn('synthetic specific cause', row['error'])

    def test_timeout_full_detail(self):
        def transport(_): raise TimeoutError('synthetic timeout detail')
        out = io.StringIO(); s.run_inputs([('synthetic', package())], out, execute=True, transport=transport)
        row = json.loads(out.getvalue())
        self.assertEqual(row['error_type'], 'TimeoutError')
        self.assertEqual(row['error'], 'synthetic timeout detail')

    def test_late_citation_retained_in_evidence_section(self):
        p = {'belege': [{'id': 'B' + str(i), 'quelle': 'synthetic source', 'datum': '2026-01-01', 'text': 'Synthetische Prüfung.'} for i in range(1, 34)]}
        f = fixture(); f['worum']['belege'] = ['B33']
        rendered = s.render_markdown(p, f)
        self.assertIn('B33 |', rendered.split('## Belege')[1])
        self.assertIn('synthetic source', rendered.split('## Belege')[1])
        self.assertLessEqual(len(rendered.splitlines()), 150)

    def test_many_citations_worst_unicode(self):
        p = {'belege': [{'id': 'B' + str(i), 'quelle': '源' * 20, 'datum': '2026-01-01', 'text': '文' * 100} for i in range(1, 34)]}
        f = fixture()
        ids = ['B' + str(i) for i in range(1, 34)]
        for index, name in enumerate(s.FIELDS):
            refs = [ids[(index * 3 + j) % len(ids)] for j in range(12)]
            f[name] = {'wert': 'review' if name == 'art' else 'ki' if name == 'bearbeitungsweg' else '文' * 600, 'reife': 'annahme', 'belege': refs, 'begruendung': '理' * 240, 'zitat': None}
        f['offene_fragen'] = [dict(f['scope']) for _ in range(5)]
        rendered = s.render_markdown(p, f)
        self.assertLessEqual(len(rendered.encode()), 20000)
        self.assertLessEqual(len(rendered.splitlines()), 150)
        self.assertLessEqual(max(map(len, rendered.splitlines())), 400)
        before, after = rendered.split('## Belege')
        import re
        for suffix in re.findall(r'\[(?:belegt |Annahme: )[^\]]*\]', before):
            for identifier in re.findall(r'B[1-9][0-9]*', suffix): self.assertIn(identifier + ' |', after)

    def test_transport_secret_redaction(self):
        # Mock urllib opener; no network and no environment credential access.
        import urllib.request
        from unittest.mock import patch
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return b'synthetic key123 echoed body'
        class FakeOpener:
            def open(self, *args, **kwargs): return FakeResponse()
        with patch.object(urllib.request, 'build_opener', return_value=FakeOpener()):
            raw = s.http_transport('key123')({})
        self.assertNotIn('key123', raw)
        self.assertIn('[REDACTED]', raw)

class ManyEvidenceRegressionTests(unittest.TestCase):
    def test_evidence_count_cap_explicit(self):
        p = {'belege': [{'id': 'B' + str(i), 'quelle': 's', 'datum': 'd', 'text': 't'} for i in range(1, 301)]}
        evidence = s.build_evidence(p)
        self.assertEqual(len(evidence['belege']), 64)
        self.assertEqual(evidence['ausgelassen'], 236)
        self.assertIn('236 Belege ausgelassen', evidence['block'])

class BracketedReasonRegressionTests(unittest.TestCase):
    def test_bracketed_reason_retains_structural_citation(self):
        f = fixture(); f['scope'] = dict(f['worum'], reife='annahme', begruendung='Prüfung [Test] erforderlich.')
        rendered = s.render_markdown(package(), f)
        self.assertIn('[Annahme: Prüfung [Test] erforderlich.; B1]', rendered)
        self.assertIn('B1 |', rendered.split('## Belege')[1])

    def test_freetext_spoof_does_not_select_unused_evidence(self):
        p = package(); p['belege'].append({'id': 'B9', 'quelle': 'unused', 'datum': '2026-01-01', 'text': 'unused'})
        f = fixture(); f['worum']['wert'] = 'Freitext B9 und [belegt B9]'; f['worum']['zitat'] = None
        rendered = s.render_markdown(p, f)
        self.assertIn('B1 |', rendered.split('## Belege')[1])
        self.assertNotIn('B9 |', rendered.split('## Belege')[1])

if __name__ == '__main__': unittest.main()
