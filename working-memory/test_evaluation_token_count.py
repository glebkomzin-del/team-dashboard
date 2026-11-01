import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from call_budget import reserve_micro_usd
from openai_provider import count_input_tokens


class CountTests(unittest.TestCase):
    def test_replayed_request_counts_in_comparison_without_new_spend(self):
        from evaluation_budget import EvaluationCalls
        response={'usage_final':True,'usage':{'input_tokens':100,'output_tokens':10}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'budget.sqlite'
            with patch('builtins.print'):
                first=EvaluationCalls(path,None,lambda *a,**k:response,{}, {'source':'fixture','pipeline':'old'})
                first('same','gpt-5.6-terra',max_tokens=10);paid=first.total();first.close()
                api=MagicMock(side_effect=AssertionError('Must reuse response'))
                second=EvaluationCalls(path,None,api,{}, {'source':'fixture','pipeline':'new'})
                before=second.total();second('same','gpt-5.6-terra',max_tokens=10)
                self.assertEqual(second.total()-before,0)
                self.assertEqual(second.used_costs(),{'gpt-5.6-terra':paid})
                second.close();api.assert_not_called()
    def test_count_includes_original_input_and_strict_schema(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {'object': 'response.input_tokens', 'input_tokens': 123}).encode()
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch('urllib.request.urlopen', return_value=response) as send:
            self.assertEqual(count_input_tokens('original', 'gpt-5.6-terra', {'type': 'object'}), 123)
            body = json.loads(send.call_args.args[0].data)
            self.assertEqual(body['input'], [{'role': 'user', 'content': 'original'}])
            self.assertEqual(body['text']['format']['schema'], {'type': 'object'})
            self.assertTrue(body['text']['format']['strict'])

    def test_gpt6_count_preserves_none_effort_and_exact_model(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"object":"response.input_tokens","input_tokens":123}'
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch('urllib.request.urlopen', return_value=response) as send:
            for model in ('gpt-6-sol', 'gpt-6-luna'):
                self.assertEqual(count_input_tokens('original', model, {'type': 'object'}), 123)
                body = json.loads(send.call_args.args[0].data)
                self.assertEqual(body['model'], model)
                self.assertEqual(body['reasoning'], {'effort': 'none'})

    def test_exact_reservation_still_covers_full_output_and_price_premiums(self):
        self.assertEqual(reserve_micro_usd('x', 'gpt-5.6-terra', 100, {}, counted_input_tokens=300000),
                         (300000+4096)*5+1800)
        for value in (0, -1, True, '100'):
            with self.assertRaises(ValueError):
                reserve_micro_usd('x', 'gpt-5.6-terra', 100, {}, counted_input_tokens=value)

    def test_missing_count_stops(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(ValueError): count_input_tokens('x', 'gpt-5.6-terra', {})
