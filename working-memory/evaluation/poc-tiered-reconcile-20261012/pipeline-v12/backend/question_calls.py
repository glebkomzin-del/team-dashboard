"""Durable, budgeted provider calls for owner questions.

Question calls are independent from ingestion jobs but keep the same rule: reserve
before networking, persist the complete response, and never resend an unresolved
reservation. The private outbox only retries receipt persistence.
"""
import json
from pathlib import Path

from call_budget import BudgetExceeded, RATES, reserve_micro_usd, usage_micro_usd
from durable_calls import OutcomeUnknown, atomic_private, encode, sha
from memory import ValidationError


class QuestionCalls:
    def __init__(self, store, *, question_id, actor_id, api, outbox, budget_micro_usd, start_index=0):
        if budget_micro_usd is not None and (type(budget_micro_usd) is not int or budget_micro_usd<=0):
            raise ValidationError('Question budget must be positive or unlimited')
        self.store,self.question_id,self.actor_id=store,question_id,actor_id
        self.api,self.outbox,self.budget=api,Path(outbox),budget_micro_usd
        self.index=start_index

    def __call__(self,prompt,model,max_tokens=24000,schema=None):
        if model not in RATES or not isinstance(schema,dict):
            raise BudgetExceeded('Question model or schema is not priced')
        value={'model':model,'prompt':prompt,'max_tokens':max_tokens,'schema':schema}
        if model == 'gpt-6.1-sol':
            value['transport']={'reasoning_effort':'medium','service_tier':'default'}
        request=encode(value);reserve=reserve_micro_usd(prompt,model,max_tokens,schema)
        fields={'question_id':self.question_id,'actor_id':self.actor_id,'call_index':self.index}
        record=self.store.call('question_reserve',**fields,request_json=request,
            reserved_micro_usd=reserve,budget_micro_usd=self.budget)
        if record.get('state')=='budget_exceeded':
            raise BudgetExceeded('Question budget does not cover the next request')
        if record.get('request_hash')!=sha(request):raise ValidationError('Question call hash mismatch')
        if record.get('response_json') is not None:
            if record.get('response_hash')!=sha(record['response_json']):raise ValidationError('Question response hash mismatch')
            result=json.loads(record['response_json'])
        elif record.get('send') is True:
            result=self.api(prompt,model,max_tokens=max_tokens,schema=schema)
            serialized=encode(result);actual=usage_micro_usd(result,model)
            receipt={**fields,'space_id':self.store.space_id,'response_json':serialized,
                     'actual_micro_usd':actual,'response_hash':sha(serialized)}
            path=self.outbox/f"question-{self.question_id}-{self.index}.json"
            atomic_private(path,receipt)
            saved=self.store.call('question_receive',**fields,response_json=serialized,actual_micro_usd=actual)
            if saved.get('saved') is not True:raise OutcomeUnknown('Question response receipt not confirmed')
            path.unlink()
        else:raise OutcomeUnknown('Question provider outcome is unknown; automatic resend is forbidden')
        # A retry may start after all historical slots and replay an older,
        # content-addressed request. Only a newly allocated slot advances it.
        self.index=max(self.index,int(record['call_index'])+1)
        return result


def drain_question_outbox(store,directory,question_id,actor_id):
    count=0
    for path in sorted(Path(directory).glob(f"question-{question_id}-*.json")):
        receipt=json.loads(path.read_text())
        if receipt.get('space_id')!=store.space_id or receipt.get('question_id')!=question_id \
          or receipt.get('actor_id')!=actor_id or receipt.get('response_hash')!=sha(receipt['response_json']):
            raise ValidationError('Question outbox scope or checksum mismatch')
        result=store.call('question_receive',**{k:receipt[k] for k in
            ('question_id','actor_id','call_index','response_json','actual_micro_usd')})
        if result.get('saved') is not True:raise OutcomeUnknown('Question response persistence remains unconfirmed')
        path.unlink();count+=1
    return count


def drain_all_question_outbox(store,directory):
    """Persist every complete local receipt before a privacy checkpoint."""
    count=0
    for path in sorted(Path(directory).glob('question-*.json')):
        if path.is_symlink():raise ValidationError('Unexpected question receipt symlink')
        receipt=json.loads(path.read_text())
        required=('question_id','actor_id','call_index','response_json','actual_micro_usd')
        if receipt.get('space_id')!=store.space_id or any(key not in receipt for key in required) \
          or receipt.get('response_hash')!=sha(receipt['response_json']):
            raise ValidationError('Question outbox scope or checksum mismatch')
        result=store.call('question_receive',**{key:receipt[key] for key in required})
        if result.get('saved') is not True:raise OutcomeUnknown('Question response persistence remains unconfirmed')
        path.unlink();count+=1
    return count
