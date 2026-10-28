"""Offline historical projection replay. Never connects to any network."""
import hashlib,json,os,sqlite3,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'private'
sys.path.insert(0,str(PRIVATE/'runtime'))
sys.dont_write_bytecode=True
for key in list(os.environ):
 if key.startswith(('OPENAI_','ANTHROPIC_','DASHBOARD_','MEMORY_','SUPABASE_')):os.environ.pop(key)
def audit(event,args):
 if event.startswith('socket.') or event in ('subprocess.Popen','os.system'):
  raise RuntimeError('Offline replay forbids network and subprocesses')
sys.addaudithook(audit)
from journal_projection import rebuild
from memory import connect
value=json.loads((PRIVATE/'inputs.json').read_text())
class Store:
 def __init__(self,job):self.job=job;self.space_id=job['space_id']
 def space(self):return next(s for s in value['spaces'] if s['id']==self.space_id)
 def entries(self,*,through=None):return [e for e in value['entries'] if e['space_id']==self.space_id and e['revision']<=through]
 def source(self,version_id):return next(s for s in value['sources'] if s['space_id']==self.space_id and s['id']==version_id)
results=[]
for job in value['jobs']:
 report={'job':job['id'][:8],'revision':job['expected_revision']}
 try:
  path=PRIVATE/(job['id'][:8]+'.sqlite')
  result=rebuild(Store(job),path,through=job['expected_revision'])
  report['projection']='PASS';report['events']=len(Store(job).entries(through=job['expected_revision']))
 except Exception as error:
  report.update(projection='FAIL',error_type=type(error).__name__,error=str(error),frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)[-6:]])
 results.append(report)
(ROOT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
