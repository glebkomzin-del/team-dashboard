"""Audit all requests of a completed run without permitting any new generation."""
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import run_hybrid_validation as runner
from evaluation_budget import EvaluationCalls
from call_budget import usage_micro_usd


def main():
    db=sqlite3.connect(runner.ROOT/'budget.sqlite')
    before=db.execute('select sum(coalesce(actual,reserved)) from calls').fetchone()[0]
    traces=[]
    class Replay(EvaluationCalls):
        def __init__(self,*args,**kwargs):
            kwargs.update(ceiling=before,token_counter=None)
            super().__init__(*args,**kwargs)
        def __call__(self,prompt,model,max_tokens=24000,schema=None):
            result=super().__call__(prompt,model,max_tokens,schema)
            cost=usage_micro_usd(result,model)
            if cost is None:raise ValueError('Cannot establish complete comparison cost')
            traces.append({'model':model,'input_tokens':result['usage']['input_tokens'],
                           'output_tokens':result['usage']['output_tokens'],'micro_usd':cost,
                           'provider_seconds':result.get('elapsed_seconds'),'response_id':result.get('id')})
            return result
    def no_generation(*args,**kwargs):raise AssertionError('Replay may not generate')
    runner.EvaluationCalls=Replay;runner.request=no_generation
    runner.main('gpt-5.6-terra',True,before)
    after=db.execute('select sum(coalesce(actual,reserved)) from calls').fetchone()[0]
    if before!=after:raise AssertionError('Replay changed spending')
    model=[t for t in traces if t['model']=='gpt-5.6-terra']
    embeddings=[t for t in traces if t['model']=='text-embedding-3-small']
    output={'model_cost_usd':sum(t['micro_usd'] for t in model)/1e6,
            'embedding_request_equivalent_usd':sum(t['micro_usd'] for t in embeddings)/1e6,
            'model_calls':len(model),'embedding_calls_reused':len(embeddings),
            'input_tokens':sum(t['input_tokens'] for t in model),
            'provider_seconds_equivalent':sum(t['provider_seconds'] for t in model),
            'replay_incremental_usd':(after-before)/1e6,'calls':traces}
    path=runner.ROOT.parent/'cost-optimization-20260908'/'final-cost-audit.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in output.items() if k!='calls'}),flush=True)

if __name__=='__main__':main()
