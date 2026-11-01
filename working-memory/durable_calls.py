"""One reservation and immutable response per canonical model-call slot.

An uncertain reservation is never a reason to send twice. A local outbox also
retains received responses while Supabase is unavailable; it contains private
source material and must be included in the encrypted server backup.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from call_budget import BudgetExceeded, RATES, reserve_micro_usd, usage_micro_usd as usage_cost
from memory import ValidationError

MAX_CALL_INDEX = 1023


class OutcomeUnknown(RuntimeError): pass

def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def sha(text):return hashlib.sha256(text.encode()).hexdigest()

def atomic_private(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(prefix='.receipt-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            f.write(encode(value));f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
        parent=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(parent)
        finally:os.close(parent)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

class DurableCalls:
    def __init__(self,store,job,api,default_schema,outbox,*,start_index=0,prior_calls=None,token_counter=None):
        if not isinstance(start_index,int) or isinstance(start_index,bool) or not 0<=start_index<=MAX_CALL_INDEX+1:
            raise ValidationError('Invalid durable call start index')
        self.store,self.job,self.api,self.schema=store,job,api,default_schema
        self.outbox=Path(outbox);self.index=start_index;self.primary_responses=[]
        self.by_hash = None if prior_calls is None else {c['request_hash']: c for c in prior_calls}
        self.request_scope = {'pipeline':job.get('pipeline'),'revision':job.get('expected_revision')}
        self.token_counter=token_counter

    def __call__(self,prompt,model,max_tokens=24000,schema=None):
        if model not in RATES:raise BudgetExceeded('No verified model price')
        if type(max_tokens) is not int or max_tokens<=0:raise ValidationError('Invalid output allowance')
        effective=self.schema if schema is None else schema
        value={'model':model,'prompt':prompt,'max_tokens':max_tokens,'schema':effective}
        if self.by_hash is not None: value['scope']=self.request_scope
        request=encode(value)
        previous = self.by_hash.get(sha(request)) if self.by_hash is not None else None
        counted=None
        if not previous and self.token_counter and model in ('gpt-5.6-terra','gpt-5.6-luna'):
            counted=self.token_counter(prompt,model,effective)
        reserve=reserve_micro_usd(prompt,model,max_tokens,effective,counted_input_tokens=counted)
        if type(reserve) is not int:raise ValidationError('Prices require integer microdollar accounting')
        if not previous and self.index>MAX_CALL_INDEX:raise ValidationError('Durable call slots exhausted')
        slot = previous['index'] if previous else self.index
        fields={'job_id':self.job['id'],'lease_token':self.job['lease_token'],'call_index':slot}
        record=self.store.call('reserve_call',**fields,request_json=request,reserved_micro_usd=reserve)
        if record.get('state')=='budget_exceeded':raise BudgetExceeded('Remaining budget does not cover request')
        if record.get('request_hash')!=sha(request):raise ValidationError('Reserved request hash mismatch')
        if record.get('response_json') is not None:
            if record.get('response_hash')!=sha(record['response_json']):raise ValidationError('Saved response hash mismatch')
            result=json.loads(record['response_json'])
        elif record.get('send') is True:
            # No network retry is allowed here, even if an exception looks transient.
            result=self.api(prompt,model,max_tokens=max_tokens,schema=effective)
            serialized=encode(result)
            receipt={**fields,'space_id':self.store.space_id,'response_json':serialized,
                     'actual_micro_usd':usage_cost(result,model),'response_hash':sha(serialized)}
            path=self.outbox/f"{self.job['id']}-{slot}.json"
            atomic_private(path,receipt)
            saved=self.store.call('receive_call',**fields,response_json=serialized,actual_micro_usd=receipt['actual_micro_usd'])
            if saved.get('saved') is not True:raise OutcomeUnknown('Response receipt not confirmed')
            path.unlink()
        else:
            raise OutcomeUnknown('Provider outcome is unknown; automatic resend is forbidden')
        if not previous: self.index+=1
        if self.by_hash is not None: self.by_hash[sha(request)]={'index':slot,'request_hash':sha(request)}
        if schema is None:self.primary_responses.append(result)
        return result

def drain_outbox(store,directory):
    """Retry only persistence of a received response, never the model call."""
    count=0
    for path in sorted(Path(directory).glob('*.json')):
        if path.is_symlink():raise ValidationError('Unexpected receipt symlink')
        receipt=json.loads(path.read_text())
        if receipt.get('space_id')!=store.space_id or receipt.get('response_hash')!=sha(receipt['response_json']):
            raise ValidationError('Outbox scope or checksum mismatch')
        result=store.call('receive_call',**{k:receipt[k] for k in ('job_id','lease_token','call_index','response_json','actual_micro_usd')})
        if result.get('saved') is not True:raise OutcomeUnknown('Response persistence remains unconfirmed')
        path.unlink();count+=1
    return count
