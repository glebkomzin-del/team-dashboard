import importlib.util
import io
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('extract_stage_requests', Path(__file__).with_name('extract_stage_requests.py'))
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


class ExtractTests(unittest.TestCase):
    def request(self, prompt='STUFE 1: Beobachtungen\nDatum: 2026-10-12\n'):
        return {'prompt': prompt, 'model': 'gpt-6.1-sol', 'schema': {'type': 'object', 'properties': {'observations': {'type': 'array'}}}}

    def call(self, request=None, response=None, index=0):
        return json.dumps({'kind': 'call', 'record_json': json.dumps({'job_id': 'synthetic',
            'call_index': index, 'request_json': request or self.request(),
            'response_json': response if response is not None else {'content': [{'text': '{"observations":[]}'}],
            'usage': {'input_tokens': 10, 'output_tokens': 5}}, 'actual_micro_usd': 70})})

    def test_extract_stage1(self):
        self.assertEqual(extract.detect_stage(self.request()), 'extract')

    def test_extract_named(self):
        self.assertEqual(extract.detect_stage(self.request('Extraktion')), 'extract')

    def test_extract_old_schema_guard(self):
        self.assertEqual(extract.detect_stage(self.request('Erfasse Beobachtungen')), 'extract')
        self.assertIsNone(extract.detect_stage({'prompt': 'Erfasse Beobachtungen'}))

    def test_gate_precedes_extraction_word(self):
        request = self.request('Extraktion\nKandidaten:\nBestehende Arbeit:')
        request['schema']['properties'] = {'verdicts': {'type': 'array'}}
        self.assertEqual(extract.detect_stage(request), 'gate')

    def test_compact_excluded(self):
        self.assertIsNone(extract.detect_stage(self.request('Extraktion Kandidaten: Bestehende Arbeit: Bereits geöffnete Original-IDs')))

    def test_alignment_excluded(self):
        self.assertIsNone(extract.detect_stage(self.request('Extraktion Beobachtungen Kandidaten:')))

    def test_embedding_excluded(self):
        self.assertIsNone(extract.detect_stage({'prompt': 'Extraktion', 'schema': None, 'model': 'text-embedding-3-small'}))

    def test_other_non_string(self):
        self.assertIsNone(extract.detect_stage({'prompt': None}))
        self.assertIsNone(extract.detect_stage({'prompt': 'Unrelated'}))

    def test_dates(self):
        self.assertEqual(extract.meeting_date('Datum: 2026-10-12\n'), '2026-10-12')
        self.assertIsNone(extract.meeting_date('\nDatum: 2026-02-30\n'))
        self.assertIsNone(extract.meeting_date('none'))

    def test_stream_fields_and_stats(self):
        writer = io.StringIO()
        stats = extract.extract_lines([json.dumps({'kind':'job','record_json':{}}),self.call()], writer)
        row = json.loads(writer.getvalue())
        self.assertEqual(set(row), {'job_id','call_index','stage','meeting_date','request_json','reference_text','reference_usage','reference_micro_usd','reference_model','reference_stop_reason'})
        self.assertEqual(stats['counts']['extract'], 1)
        self.assertEqual(stats['prompt_characters']['extract']['mean'], len(self.request()['prompt']))
        self.assertEqual(row['reference_micro_usd'],70)

    def test_unknown_reference_retained(self):
        writer = io.StringIO()
        stats = extract.extract_lines([self.call(response={})], writer)
        self.assertIsNone(json.loads(writer.getvalue())['reference_text'])
        self.assertEqual(stats['counts']['unknown_references'],1)

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            extract.extract_lines([self.call(),self.call()],io.StringIO())

    def test_invalid_identity_and_duplicate_json(self):
        with self.assertRaises(ValueError):
            extract.extract_lines([self.call(index=True)],io.StringIO())
        with self.assertRaises(ValueError):
            extract.extract_lines(['{"kind":"job","kind":"call"}'],io.StringIO())

    def test_cost_write_and_unknown(self):
        c = extract.common
        self.assertEqual(c.usage_micro_usd({'input_tokens':1000,'output_tokens':100,
            'input_tokens_details':{'cached_tokens':200,'cache_write_tokens':300}},'gpt-6-luna'),140)
        self.assertIsNone(c.usage_micro_usd({'input_tokens':100,'output_tokens':10,
            'input_tokens_details':{'cached_tokens':50,'cache_write_tokens':51}},'gpt-6-luna'))


if __name__ == '__main__':
    unittest.main()
