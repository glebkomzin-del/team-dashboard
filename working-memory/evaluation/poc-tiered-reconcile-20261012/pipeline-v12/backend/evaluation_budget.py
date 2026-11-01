"""One shared experiment ledger: cached exact requests, durable reservations, no resend.

Default cap $10 (~EUR8.61 at ECB 2026-09-08 1.1614 USD/EUR).
This leaves room below EUR15 for tax/FX and necessary repair; no auto top-up.
"""
import json
import os
from pathlib import Path
import sqlite3
import time
from call_budget import reserve_micro_usd,usage_micro_usd,BudgetExceeded
from durable_calls import encode,sha,OutcomeUnknown,atomic_private

class EvaluationCalls:
 def __init__(self,path,store,api,schema,scope,ceiling=10000000,token_counter=None):
  if type(ceiling) is not int or not 0<ceiling<=11500000:raise ValueError('Validation cap exceeds authorized allocation')
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  self.db=sqlite3.connect(path,isolation_level=None,timeout=30);self.path.chmod(0o600)
  self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
  self.db.execute('CREATE TABLE IF NOT EXISTS calls(hash TEXT PRIMARY KEY,request TEXT NOT NULL,model TEXT NOT NULL,reserved INTEGER NOT NULL,actual INTEGER,response TEXT,created REAL NOT NULL)')
  self.store,self.api,self.schema,self.scope,self.ceiling=store,api,schema,scope,ceiling
  self.token_counter=token_counter
  self.primary_responses=[]
  self.used_identifiers=set()
  self.outbox=self.path.parent/'evaluation-outbox'
  for path in self.outbox.glob('*.json') if self.outbox.exists() else []:
   value=json.loads(path.read_text())
   if sha(value['response'])!=value['response_hash']:raise ValueError('Evaluation receipt checksum mismatch')
   self.db.execute('UPDATE calls SET actual=?,response=? WHERE hash=? AND response IS NULL',(value['actual'],value['response'],value['hash']))
   path.unlink()
 def total(self):return self.db.execute('SELECT coalesce(sum(coalesce(actual,reserved)),0) FROM calls').fetchone()[0]
 def __call__(self,prompt,model,max_tokens=24000,schema=None):
  effective=self.schema if schema is None else schema
  # Shared deterministic embeddings can be reused across model comparisons.
  scope='embedding-v1' if model=='text-embedding-3-small' else self.scope
  request=encode({'scope':scope,'model':model,'prompt':prompt,'schema':effective,'max_tokens':max_tokens});identifier=sha(request)
  self.db.execute('BEGIN IMMEDIATE')
  try:
   previous=self.db.execute('SELECT response FROM calls WHERE hash=?',(identifier,)).fetchone()
   if previous is None:
    expected=json.loads(request)
    if isinstance(expected['scope'],dict):expected['scope'].pop('pipeline',None)
    # A software revision alone does not justify paying again for an IDENTICAL
    # model request against the same source/revision. Revalidate saved output.
    for old_hash,old_request,old_response in self.db.execute('SELECT hash,request,response FROM calls WHERE model=?',(model,)):
     candidate=json.loads(old_request)
     if isinstance(candidate['scope'],dict):candidate['scope'].pop('pipeline',None)
     if candidate==expected:
      identifier=old_hash;previous=(old_response,);break
   if previous:
    if previous[0] is None:raise OutcomeUnknown('Unknown prior evaluation result; no automatic resend')
    result=json.loads(previous[0]);self.db.execute('COMMIT')
   else:
    counted=None
    if self.token_counter and model in ('gpt-5.6-terra','gpt-5.6-luna'):
     counted=self.token_counter(prompt,model,effective)
    reserve=reserve_micro_usd(prompt,model,max_tokens,effective,counted_input_tokens=counted)
    if self.total()+reserve>self.ceiling:raise BudgetExceeded('Shared experiment allocation exhausted')
    self.db.execute('INSERT INTO calls VALUES (?,?,?,?,NULL,NULL,?)',(identifier,request,model,reserve,time.time()));self.db.execute('COMMIT')
    result=self.api(prompt,model,max_tokens=max_tokens,schema=effective)
    response=encode(result);actual=usage_micro_usd(result,model)
    path=self.outbox/(identifier+'.json');atomic_private(path,{'hash':identifier,'response':response,'response_hash':sha(response),'actual':actual})
    self.db.execute('UPDATE calls SET response=?,actual=? WHERE hash=?',(response,actual,identifier));path.unlink()
  except Exception:
   if self.db.in_transaction:self.db.execute('ROLLBACK')
   raise
  if schema is None:self.primary_responses.append(result)
  self.used_identifiers.add(identifier)
  print(encode({'paid_ledger_usd':self.total()/1000000,'model':model,'reused':bool(previous)}),flush=True)
  return result
 def close(self):self.db.close()
 def used_costs(self):
  """Price the exact requests consumed by this run, including replayed calls."""
  totals={}
  for identifier in self.used_identifiers:
   model,actual,reserved=self.db.execute('SELECT model,actual,reserved FROM calls WHERE hash=?',(identifier,)).fetchone()
   totals[model]=totals.get(model,0)+(actual if actual is not None else reserved)
  return totals
