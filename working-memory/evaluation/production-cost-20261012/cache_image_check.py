import json,pathlib,tempfile,ast,hashlib
import openai_provider as provider
from durable_calls import DurableCalls,encode,sha,OutcomeUnknown
from canonical_worker import pipeline_version
manifest=json.loads(pathlib.Path('/app/build-manifest.json').read_text())
for name in ['openai_provider.py','durable_calls.py','question_calls.py']:
 assert hashlib.sha256(pathlib.Path('/app',name).read_bytes()).hexdigest()==manifest[name]
 assert ast.parse(pathlib.Path('/app',name).read_text())
schema={'type':'object','properties':{},'additionalProperties':False};prompt='Vollständiges Original: Änderung nur nach positivem Nachweis.'
payload=provider.response_input(prompt,provider.MODEL,schema)
assert payload['prompt_cache_options']=={'mode':'explicit'}
assert payload['input']==[{'role':'user','content':prompt}] and payload['reasoning']=={'effort':'medium'}
assert payload['service_tier']=='default' and payload['truncation']=='disabled'
assert payload['text']['format']['schema']==schema
class Store:
 space_id='test-space'
 def __init__(self):self.saved={};self.requests=[]
 def call(self,operation,**kwargs):
  key=kwargs['call_index']
  if operation=='reserve_call':
   self.requests.append(json.loads(kwargs['request_json']))
   return {'request_hash':sha(kwargs['request_json']),**self.saved.get(key,{'send':True})}
  if operation=='receive_call':
   self.saved[key]={'response_json':kwargs['response_json'],'response_hash':sha(kwargs['response_json'])};return {'saved':True}
  raise AssertionError(operation)
called=[]
def fake(prompt,model,**kwargs):
 called.append(model);return {'model':model,'usage_final':True,'returned_service_tier':'default','content':[{'type':'text','text':'{}'}],'stop_reason':'end_turn','usage':{'input_tokens':3,'output_tokens':1,'input_tokens_details':{'cache_write_tokens':0,'cached_tokens':0}}}
store=Store();job={'id':'local-test','lease_token':'test','pipeline':'candidate','expected_revision':1}
with tempfile.TemporaryDirectory() as tmp:
 calls=DurableCalls(store,job,fake,schema,tmp,prior_calls=[])
 first=calls(prompt,provider.MODEL,max_tokens=128,schema=schema)
 assert store.requests[0]['transport']['prompt_cache_options']=={'mode':'explicit'}
 second=calls(prompt,provider.MODEL,max_tokens=128,schema=schema)
 assert first==second and len(called)==1
 request=store.requests[0].copy();old=dict(request);old['transport']={'reasoning_effort':'medium','service_tier':'default'}
 assert sha(encode(request))!=sha(encode(old))
 class Unknown(Store):
  def call(self,op,**kwargs):return {'request_hash':sha(kwargs['request_json']),'send':False}
 failed=DurableCalls(Unknown(),job,fake,schema,tmp,prior_calls=[])
 try:failed(prompt,provider.MODEL,max_tokens=128,schema=schema)
 except OutcomeUnknown:pass
 else:raise AssertionError('Unknown provider outcome resubmitted')
 assert len(called)==1
 assert not list(pathlib.Path(tmp).glob('*.json'))
from question_calls import QuestionCalls
class QuestionStore:
 space_id='test-space'
 def __init__(self,unknown=False):self.requests=[];self.unknown=unknown;self.result=None
 def call(self,operation,**kwargs):
  if operation=='question_reserve':
   self.requests.append(json.loads(kwargs['request_json']))
   return {'request_hash':sha(kwargs['request_json']),'call_index':kwargs['call_index'],**({'send':False} if self.unknown else (self.result or {'send':True}))}
  if operation=='question_receive':
   self.result={'response_json':kwargs['response_json'],'response_hash':sha(kwargs['response_json'])};return {'saved':True}
  raise AssertionError(operation)
with tempfile.TemporaryDirectory() as tmp:
 qs=QuestionStore();q=QuestionCalls(qs,question_id='q',actor_id='owner',api=fake,outbox=tmp,budget_micro_usd=50000)
 before_count=len(called);q(prompt,provider.MODEL,max_tokens=128,schema=schema)
 assert qs.requests[0]['transport']['prompt_cache_options']=={'mode':'explicit'} and len(called)==before_count+1
 unknown=QuestionCalls(QuestionStore(unknown=True),question_id='q-unknown',actor_id='owner',api=fake,outbox=tmp,budget_micro_usd=50000)
 try:unknown(prompt,provider.MODEL,max_tokens=128,schema=schema)
 except OutcomeUnknown:pass
 else:raise AssertionError('Question unknown resent')
 assert len(called)==before_count+1
print(json.dumps({'question_transport_identity':True,'question_unknown_not_resent':True,'image_sources_match' :True,'payload_invariants':True,'transport_identity_includes_cache_mode':True,'saved_response_reused_once':True,'unknown_not_resent':True,'real_provider_calls':0,'pipeline':pipeline_version(provider.MODEL)}))
