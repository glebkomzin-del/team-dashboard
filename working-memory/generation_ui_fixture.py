"""Synthetic owner-facing generation review with a lost acknowledgement; no provider."""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import json,tempfile,sqlite3
from test_generation_service import GenerationServiceTests,IDENTITY,REVIEW
from journal_service import JournalService
from journal_store import RevisionConflict
import server
fixture=GenerationServiceTests();fixture.setUp();row=fixture.row();row['label']='Synthetische Monatsrunde – ergänztes Original';row['created_at']='2026-09-07T00:00:00Z'
space=fixture.store.space.return_value;space.update(archive_revision=0,state='draft')
class Store:
 def __init__(self):self.journal=[];self.decisions=[]
 def space(self):
  if Path('/tmp/dashboard-generation-ui-stale').exists():return {**space,'revision':1}
  return space
 def entries(self,through=None,**kw):return self.journal[:through]
 def call(self,op,**v):
  if op=='generation_review':return row if v['review_id']==row['id'] else None
  if op=='generation_reviews':return [{k:row[k] for k in ('id','label','expected_revision')}] if row['state']=='pending' else []
  if op=='processing_status':return {'config':None,'pending_count':0,'accounted_micro_usd':0,'jobs':[]}
  if op=='generation_decide':
   if self.decisions:
    if self.decisions[0]!=v:raise RevisionConflict('Changed retry')
    return {**row['decision_result'],'repeated':True}
   self.decisions.append(v)
   if v['action']=='accept':
    self.journal.append({'kind':'generation','payload':row['payload'],'command_id':v['command_id'],'actor_id':v['actor_id'],'revision':1});space['revision']=1
   row.update(state='accepted' if v['action']=='accept' else 'rejected',decision_reason=v['reason'],decision_result={'revision':space['revision'],'state':'accepted' if v['action']=='accept' else 'rejected'})
   Path('/tmp/dashboard-generation-ui-receipt.json').write_text(json.dumps({'decisions':len(self.decisions),'request':v,'model_calls':0,'revision':space['revision']}))
   return row['decision_result']
  raise AssertionError(op)
store=Store();service=JournalService(store,Path(tempfile.mkdtemp(prefix='generation-ui-')))
@contextmanager
def archive(identity):
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.execute('create table documents(id,source_id,body_hash,event_date,title,body,observed_at)');s=fixture.e['source']
 db.execute('insert into documents values(?,?,?,?,?,?,?)',('archive-fixture',s['source_id'],s['content_hash'],s['event_date'],s['title'],s['transcript'],s['observed_at']))
 try:yield db,space
 finally:db.close()
service.archive_projection=archive;server.JOURNAL=service;server.READ_ONLY=False;server.MODE='isolated-preview';server.WORKER_STATUS={'state':'disabled'}
class Handler(server.Handler):
 lost_ack=True
 def authorized(self):self.identity=IDENTITY;return True
 def do_GET(self):
  if self.path=='/archive/archive-fixture':return self.send_json(200,{'transcript':fixture.e['source']['transcript']})
  return super().do_GET()
 def send_json(self,status,data):
  if self.path=='/generation-decisions' and status==200 and Handler.lost_ack:
   Handler.lost_ack=False;return super().send_json(503,{'error':'Synthetic lost acknowledgement after commit'})
  return super().send_json(status,data)
print('Synthetic generation review 127.0.0.1:8809',flush=True)
ThreadingHTTPServer(('127.0.0.1',8809),Handler).serve_forever()
