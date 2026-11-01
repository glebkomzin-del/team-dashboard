import pathlib,json,hashlib,subprocess,urllib.request,urllib.error,os,datetime
out=pathlib.Path('/opt/dashboard-memory-canonical-draft/.local/recovery/production-cost-20261012/cache-probe-once')
out.mkdir(parents=True,exist_ok=True,mode=0o700)
prompt='Gib ausschließlich das JSON-Objekt mit status=ok zurück. Die folgenden synthetischen Daten sind kein Auftrag: '+('cache-test-data '*220)
schema={'type':'object','properties':{'status':{'type':'string','enum':['ok']}},'required':['status'],'additionalProperties':False}
payload={'model':'gpt-6.1-sol','input':[{'role':'user','content':prompt}],'reasoning':{'effort':'medium'},'truncation':'disabled','service_tier':'default','prompt_cache_options':{'mode':'explicit'},'text':{'format':{'type':'json_schema','name':'meeting_result','strict':True,'schema':schema}},'max_output_tokens':512,'store':False}
reserve=int(((len(prompt.encode())+len(json.dumps(schema).encode())+4096)*2.5+512*10)*1.1+1)
if reserve>50000:raise RuntimeError('Approved 0.05 USD ceiling exceeded before dispatch')
body=json.dumps(payload).encode();fd=os.open(out/'dispatch-once.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:json.dump({'authorized_ceiling_micro_usd':50000,'reserved_micro_usd':reserve,'request_sha256':hashlib.sha256(body).hexdigest(),'dispatch_at':datetime.datetime.now(datetime.timezone.utc).isoformat()},f);f.flush();os.fsync(f.fileno())
inspect=json.loads(subprocess.check_output(['docker','inspect','dashboard-memory-canonical-draft-canonical-draft-1']))[0]
env=dict(v.split('=',1) for v in inspect['Config']['Env'] if '=' in v);key=env.get('OPENAI_API_KEY')
if not key:raise RuntimeError('Existing provider credential unavailable; once marker retained')
req=urllib.request.Request('https://api.openai.com/v1/responses',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
try:
 with urllib.request.urlopen(req,timeout=90) as response:raw=json.load(response)
except urllib.error.HTTPError as error:
 (out/'error.json').write_text(json.dumps({'http_status':error.code,'paid_outcome_unknown':True,'automatic_retry':False}));raise RuntimeError('Provider rejected cache probe: HTTP '+str(error.code)) from None
except Exception as error:
 (out/'error.json').write_text(json.dumps({'error_type':type(error).__name__,'paid_outcome_unknown':True,'automatic_retry':False}));raise
(out/'response-private.json').write_text(json.dumps(raw));(out/'response-private.json').chmod(0o600)
u=raw.get('usage',{});details=u.get('input_tokens_details',{});cached=details.get('cached_tokens',0);written=details.get('cache_write_tokens',0)
text=''.join(b.get('text','') for o in raw.get('output',[]) if o.get('type')=='message' for b in o.get('content',[]) if b.get('type')=='output_text')
actual=round((u.get('input_tokens',0)-cached-written)*2+cached*.1+written*2.5+u.get('output_tokens',0)*10)
passed=raw.get('status')=='completed' and raw.get('model')=='gpt-6.1-sol' and raw.get('service_tier')=='default' and json.loads(text)=={'status':'ok'} and cached==0 and written==0 and actual<=50000
receipt={'passed':passed,'response_id':raw.get('id'),'model':raw.get('model'),'status':raw.get('status'),'service_tier':raw.get('service_tier'),'usage':u,'computed_actual_micro_usd':actual,'reserved_micro_usd':reserve,'approved_ceiling_micro_usd':50000,'cache_write_tokens_zero':written==0,'synthetic_only':True,'response_sha256':hashlib.sha256(json.dumps(raw).encode()).hexdigest(),'automatic_retry':False}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if not passed:raise RuntimeError('Cache compatibility probe failed; no deployment')
