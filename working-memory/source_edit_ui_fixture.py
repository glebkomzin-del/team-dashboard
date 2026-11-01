"""Loopback-only manual editing and generation acceptance; fictional data only."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import json,tempfile
from copy import deepcopy
from test_source_edit import EditStore,OWNER
from journal_service import JournalService
from journal_store import RevisionConflict
import server
class Store(EditStore):
 def __init__(self):super().__init__();self.journal=[];self.decisions=[];self.stages=0
 def entries(self,through=None,**kw):return self.journal[:through]
 def call(self,op,**v):
  if op=='processing_status':return {'config':None,'pending_count':0 if self.applied else 1,'accounted_micro_usd':0,'jobs':[] if self.applied else [{**self.job,'title':'Synthetische Monatsrunde'}]}
  if op=='generation_reviews':return [{k:self.generation[k] for k in ('id','label','expected_revision')}] if self.generation and self.generation['state']=='pending' else []
  if op=='generation_stage':
   if self.staged:
    if self.staged!=v:raise RevisionConflict('Changed stage retry')
   else:
    self.staged=deepcopy(v);self.stages+=1
    self.generation={'id':v['review_id'],'space_id':self.space_id,'label':v['label'],'payload':v['payload'],'expected_revision':v['expected_revision'],
     'review_sha256':v['payload']['review_sha256'],'state':'pending','job_id':v['job_id'],'created_at':'2026-09-07T02:50:00Z'}
   self.receipt_file();return {'review_id':v['review_id'],'state':self.generation['state'],'repeated':self.stages>1}
  if op=='generation_decide':
   if self.decisions:
    if self.decisions[0]!=v:raise RevisionConflict('Changed decision retry')
    return {**self.generation['decision_result'],'repeated':True}
   self.decisions.append(v)
   if v['action']=='accept':
    self.journal.append({'kind':'generation','payload':self.generation['payload'],'command_id':v['command_id'],'actor_id':v['actor_id'],'revision':1});self.revision=1;self.applied=True;self.job['state']='applied'
   self.generation.update(state='accepted' if v['action']=='accept' else 'rejected',decision_reason=v['reason'],decision_result={'revision':self.revision,'state':'accepted' if v['action']=='accept' else 'rejected'})
   self.receipt_file();return self.generation['decision_result']
  return super().call(op,**v)
 def receipt_file(self):Path('/tmp/dashboard-source-edit-ui-receipt.json').write_text(json.dumps({'stages':self.stages,'decisions':len(self.decisions),'revision':self.revision,'model_calls':0}))
store=Store();server.JOURNAL=JournalService(store,Path(tempfile.mkdtemp(prefix='source-edit-ui-')))
server.READ_ONLY=False;server.MODE='isolated-preview';server.WORKER_STATUS={'state':'disabled'}
class Handler(server.Handler):
 lost={'/source-edits','/generation-decisions'}
 def authorized(self):self.identity=OWNER;return True
 def send_json(self,status,data):
  if status==200 and self.path in Handler.lost:
   Handler.lost.remove(self.path);return super().send_json(503,{'error':'Synthetic lost acknowledgement'})
  return super().send_json(status,data)
print('Synthetic manual source review 127.0.0.1:8811',flush=True)
ThreadingHTTPServer(('127.0.0.1',8811),Handler).serve_forever()
