import json
from pathlib import Path
import sys
import tempfile
from memory import connect,register,claim,apply,overview
from hybrid_pipeline import process,version
from hybrid_schema import extraction_schema
from evaluation_budget import EvaluationCalls
from openai_provider import request
from future_summary import INSTRUCTION
from quality_cases import CASES
from run_hybrid_validation import ROOT,setup

def seed(db,case):
 for index,(title,text) in enumerate(case.get('seed',[])):
  day=case.get('seed_date','2026-09-01');source='synthetic:hybrid:'+case['id']+':'+str(index)
  job=register(db,source_id=source,event_date=day,title=title,transcript=text,pipeline='quality-reference-v1')
  item={'matter':'Monatsauswertung' if not case.get('condition') else 'Datenmigration','matter_id':None,'kind':'commitment','title':title,'claim':text,'owner':'Gleb','commitment_strength':'explicit','due_text':None,'condition_text':case.get('condition'),'update_target':None,'update':'none','quotes':[text],'state_quotes':[],'uncertainty':None,'action_uncertainty':None,'required_review':False,'work_state':'waiting' if case.get('condition') else 'open'}
  apply(db,job,claim(db,job),{'observations':[item],'coverage_notes':[]},model='reference')
  from datetime import datetime,timezone
  db.execute('UPDATE source_versions SET observed_at=?',(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp(),))

def main(model):
 store=setup();results=[]
 for case in CASES:
  if len(sys.argv)>2 and case['id']!=sys.argv[2]:continue
  folder=ROOT/'cases'/model/case['id'];folder.mkdir(parents=True,exist_ok=True)
  temp=tempfile.TemporaryDirectory();db=connect(Path(temp.name)/'memory.sqlite');seed(db,case)
  source='synthetic:hybrid:'+case['id']+':current'
  meeting={'id':source,'source_id':source,'title':case['id'],'meeting_date':'2026-09-08','observed_at':'2026-09-08T12:00:00Z','raw_transcript':case['text']}
  calls=EvaluationCalls(ROOT/'budget.sqlite',store,request,extraction_schema(),{'case':case['id'],'pipeline':version(model)})
  try:
   result=process(db,meeting,model,api=calls,extra_instruction=INSTRUCTION)
   state=overview(db,'2026-09-08');work=sum((state[k] for k in ('personal','waiting','waiting_dependencies','completed')),[])
   old=len(case.get('seed',[]));created=len(work)-old;done=len(state['completed'])
   checks={'new_tasks':created==case['tasks'],'done':done==case['done']}
   if case['id']=='same_topic_different_action':checks['correct_target']=len(state['completed'])==1 and state['completed'][0]['title']=='Monatsbericht senden'
   checks['owners']=all(w.get('owner')=='Gleb' for w in work)
   if 'due' in case:checks['deadline']=all(w.get('due_text')==case['due'] for w in work)
   if case.get('condition_retained'):checks['condition_retained']=any(w.get('condition_text') for w in work)
   value={'id':case['id'],'difficulty':case['difficulty'],'checks':checks,'passed':all(checks.values()),'result':result,'state':state}
  except Exception as error:value={'id':case['id'],'passed':False,'error':type(error).__name__+': '+str(error)}
  finally:db.close();calls.close();temp.cleanup()
  (folder/'result.json').write_text(json.dumps(value,ensure_ascii=False,indent=2));results.append({k:v for k,v in value.items() if k not in ('state','result')})
  print(json.dumps(results[-1],ensure_ascii=False),flush=True)
 (ROOT/('cases-'+model+('-'+sys.argv[2] if len(sys.argv)>2 else '')+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':main(sys.argv[1])
