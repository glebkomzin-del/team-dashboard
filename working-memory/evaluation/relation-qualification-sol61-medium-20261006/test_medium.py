"""Four offline groups: final, incomplete, failed, lost; includes saved-high regression."""
import importlib.util,json,os
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
OLD=Path('/private/tmp/semantic-relation-sol61-default-qualification-20261005')

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
provider=load('medium_provider',ROOT/'provider/openai_provider.py')
runner=load('medium_runner',ROOT/'runner/qualify_once.py')
cost=load('medium_cost',ROOT/'runner/cost_sol61.py')

def raw(status='completed',tier='default'):
 return {'id':'offline','model':'gpt-6.1-sol','status':status,'service_tier':tier,
         'usage':{'input_tokens':9784,'input_tokens_details':{'cache_write_tokens':9781,'cached_tokens':0},
                  'output_tokens':800,'output_tokens_details':{'reasoning_tokens':300}},
         'output':[{'id':'rs_test','type':'reasoning','status':'completed','summary':[]},
                   {'type':'message','role':'assistant','status':'completed',
                    'content':[{'type':'output_text','text':'{"relations":[]}'}]}]}

class MediumOffline(unittest.TestCase):
 def test_completed_final_and_exact_payload(self):
  old=json.loads((OLD/'request/request.json').read_text());new=json.loads((ROOT/'request/request.json').read_text())
  self.assertEqual(new,{**old,'reasoning_effort':'medium'})
  payload=provider.response_input(new['prompt'],new['model'],new['schema'])
  self.assertEqual(payload['reasoning'],{'effort':'medium'})
  self.assertEqual(payload['service_tier'],'default')
  self.assertEqual(new['max_tokens'],8000)
  good=provider.normalize(raw(),'gpt-6.1-sol')
  classification=runner.classify_result(good,cost.usage_micro_usd,'gpt-6.1-sol')
  self.assertEqual((classification['terminal_status'],classification['completeness'],classification['cost_knowledge']),
                   ('completed','complete_final_answer','final_usage_standard_estimate'))
  self.assertEqual(classification['semantic_assessment'],'PENDING_OFFLINE_REVIEW')
  other=provider.normalize(raw(tier='fast'),'gpt-6.1-sol')
  denied=runner.classify_result(other,cost.usage_micro_usd,'gpt-6.1-sol')
  self.assertEqual(denied['cost_knowledge'],'unknown')
  self.assertEqual(denied['completeness'],'no_final_answer')
  self.assertEqual(denied['semantic_assessment'],'NOT_POSSIBLE_NO_FINAL_ANSWER')

 def test_incomplete_known_usage_and_saved_high_regression(self):
  value=raw(status='incomplete');value['incomplete_details']={'reason':'max_output_tokens','other_private':'DO_NOT_COPY'}
  value['output']=[];value['usage']['output_tokens']=8000;value['usage']['output_tokens_details']['reasoning_tokens']=8000
  result=provider.normalize(value,'gpt-6.1-sol')
  self.assertEqual(result['incomplete_reason'],'max_output_tokens')
  self.assertNotIn('DO_NOT_COPY',json.dumps(result))
  classification=runner.classify_result(result,cost.usage_micro_usd,'gpt-6.1-sol')
  self.assertEqual(classification['transport_outcome'],'provider_terminal_received')
  self.assertEqual(classification['state'],'known_incomplete')
  self.assertIsNotNone(classification['actual_micro_usd'])
  self.assertEqual(classification['semantic_assessment'],'NOT_POSSIBLE_NO_FINAL_ANSWER')
  old_path=OLD/'actual-result/response.json'
  self.assertEqual(runner.digest(old_path),'a6ea1e73de70cac429c79e45978f78fdb0047b3402cc99080ae1acddb65de897')
  old=json.loads(old_path.read_text())
  self.assertEqual(cost.usage_micro_usd(old,'gpt-6.1-sol'),104459)
  historical=runner.classify_result(old,cost.usage_micro_usd,'gpt-6.1-sol',historical_actual=104459)
  self.assertEqual(historical['actual_micro_usd'],104459)
  self.assertEqual(historical['cost_knowledge'],'historical_receipt_known')
  self.assertIsNone(historical['terminal_status'])
  self.assertIsNone(historical['incomplete_reason'])
  self.assertIsNone(historical['returned_service_tier'])
  self.assertEqual(historical['semantic_assessment'],'NOT_POSSIBLE_NO_FINAL_ANSWER')

 def test_failed_provider_and_bad_metadata_no_secret_copy(self):
  value=raw(status='failed');value['error']={'code':'server_error','message':'SECRET SOURCE'};value['output']=[]
  result=provider.normalize(value,'gpt-6.1-sol')
  self.assertEqual(result['provider_error_code'],'server_error')
  self.assertNotIn('SECRET SOURCE',json.dumps(result))
  classification=runner.classify_result(result,cost.usage_micro_usd,'gpt-6.1-sol')
  self.assertEqual(classification['state'],'known_failed')
  self.assertEqual(classification['semantic_assessment'],'NOT_POSSIBLE_NO_FINAL_ANSWER')
  value['error']['code']='bad code with spaces and SECRET'
  result2=provider.normalize(value,'gpt-6.1-sol')
  self.assertIsNone(result2['provider_error_code'])
  self.assertNotIn('SECRET',json.dumps(result2))
  value.pop('usage');result3=provider.normalize(value,'gpt-6.1-sol')
  self.assertFalse(result3['usage_final'])
  self.assertIsNone(runner.classify_result(result3,cost.usage_micro_usd,'gpt-6.1-sol')['actual_micro_usd'])

 def test_lost_transport_new_authority_absent_and_full_history(self):
  stream=provider.collect_stream([],float('inf'),'gpt-6.1-sol')
  state=runner.classify_result(stream,cost.usage_micro_usd,'gpt-6.1-sol')
  self.assertEqual(state['transport_outcome'],'unknown_after_transport')
  self.assertIsNone(state['actual_micro_usd'])
  self.assertEqual(state['semantic_assessment'],'NOT_POSSIBLE_NO_FINAL_ANSWER')
  request,bindings,live=runner.preflight(ROOT/'request',ROOT/'runtime',ROOT/'provider/openai_provider.py',
      ROOT/'runner/cost_sol61.py',Path('/private/tmp/dashboard-productive-dispatch-20261005/model61-access-readonly.json'))
  self.assertIsNone(live)
  self.assertEqual(len(bindings['prior_attempts']),7)
  self.assertEqual(sum(v['actual_micro_usd'] for v in bindings['prior_attempts'].values() if v['actual_micro_usd'] is not None),398890)
  self.assertEqual(cost.reserve_micro_usd(request['prompt'],request['model'],request['max_tokens'],request['schema']),191475)
  with self.assertRaises(ValueError):runner.validate_user_authority(None)
  prior_approval={'status':'USER_APPROVED','approval_source':'direct_user','provenance':'OLD-HIGH-ONLY',
    'request_sha256':'b8e14586cc637dcb4ee6bd8d0a6323be8602f01bf99886633ffd23215eccac93',
    'model':'gpt-6.1-sol','reasoning_effort':'high','approved_cap_micro_usd':250000,
    'max_attempts':1,'scope':'single_paid_model_comparison'}
  with self.assertRaises(ValueError):runner.validate_user_authority(prior_approval)
  medium={**prior_approval,'request_sha256':runner.REQUEST_SHA,'reasoning_effort':'medium'}
  with self.assertRaises(ValueError):runner.validate_user_authority({**medium,'approved_cap_micro_usd':250001})
  with self.assertRaises(ValueError):runner.validate_user_authority({**medium,'approved_cap_micro_usd':191474})
  self.assertTrue(runner.validate_user_authority(medium)) # synthetic only; never saved as authority

if __name__=='__main__':unittest.main()
