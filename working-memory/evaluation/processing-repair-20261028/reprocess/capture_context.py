"""Export only existing read-only data, then replay Source16 without any provider."""
import argparse
import base64
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
CT = 'dashboard-memory-canonical-draft-canonical-draft-1'
DB = 'dashboard-supabase-20261003-db-1'
SPACE = '96a2dc44-9b9e-4644-b236-c5c1956cd39d'
JOB = '9266439fe8c4bb320db97d2a4bb1c4f16b5badb43f9bebf51c2f2191df6a61f7'
ATTEMPT = 'e9a2a394-dab8-5585-b7ee-7570223ac4b8'
PRIVATE = '/app/.local/projections-rc1-20260919/worker-reprocess22/' + JOB + '/attempts/' + ATTEMPT + '/context-capture'
REMOTE = r'''import base64,hashlib,json,os,subprocess
from pathlib import Path
CT=CONFIG['ct'];DB=CONFIG['db'];space=CONFIG['space'];job=CONFIG['job'];root=Path('/opt/dashboard-memory-canonical-draft/.local/recovery/reprocess22-20261028/context-capture')
os.umask(0o077);root.mkdir(exist_ok=True,parents=True)
def command(args,data=None):
 r=subprocess.run(args,input=data,capture_output=True)
 if r.returncode:raise RuntimeError('Read-only capture command failed')
 return r.stdout

def lit(v):return "convert_from(decode('"+base64.b64encode(str(v).encode()).decode()+"','base64'),'UTF8')"
def query(sql):
 raw=command(['docker','exec','-i',DB,'psql','-U','postgres','-d','postgres','-XqAt','-v','ON_ERROR_STOP=1'],('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;'+sql+';COMMIT;').encode())
 return json.loads(raw)
sp=lit(space)+'::uuid';jo=lit(job)
data=query("SELECT json_build_object('space',(SELECT row_to_json(s) FROM wm_spaces s WHERE id="+sp+"),'job',(SELECT row_to_json(j) FROM wm_jobs j WHERE space_id="+sp+" AND id="+jo+"),'document',(SELECT row_to_json(d) FROM wm_archive_documents d JOIN wm_jobs j ON j.space_id=d.space_id AND j.document_id=d.id WHERE j.space_id="+sp+" AND j.id="+jo+"),'entries',(SELECT json_agg(to_jsonb(j)||jsonb_build_object('source',v.source) ORDER BY j.revision) FROM wm_journal j LEFT JOIN LATERAL(SELECT to_jsonb(s) source FROM wm_source_versions s WHERE s.space_id=j.space_id AND s.id=j.source_version)v ON true WHERE j.space_id="+sp+" AND j.revision<=355),'calls',(SELECT json_agg(json_build_object('call_index',call_index,'request_json',request_json,'response_json',response_json,'request_hash',request_hash,'response_hash',response_hash) ORDER BY call_index) FROM wm_model_calls WHERE space_id="+sp+" AND job_id="+jo+" AND call_index>=2),'indexed_ids',(SELECT json_agg(id) FROM wm_search_documents WHERE space_id="+sp+"),'snapshot',(SELECT row_to_json(x) FROM (SELECT id,document_ids FROM wm_search_snapshots WHERE space_id="+sp+" ORDER BY created_at DESC LIMIT 1)x))")
assert data['space']['revision']==355 and data['job']['expected_revision']==355
assert data['job']['state']=='review' and data['job']['reason']=='validation_failed'
assert data['calls'] and all(c['response_json'] is not None for c in data['calls'])
# Bind PostgreSQL's exact pgvector/text/jsonb cache identity without executing a search RPC.
queries=[]
for c in data['calls']:
 assert hashlib.sha256(c['request_json'].encode()).hexdigest()==c['request_hash']
 assert hashlib.sha256(c['response_json'].encode()).hexdigest()==c['response_hash']
 req=json.loads(c['request_json']);res=json.loads(c['response_json'])
 if req['model']!='text-embedding-3-small':continue
 texts=json.loads(req['prompt'])
 if len(texts)!=1:continue
 assert res['stop_reason']=='end_turn' and len(res['embeddings'])==1
 for kinds in [['work','knowledge','passage','summary','feedback'],['work']]:
  values=[texts[0],res['embeddings'][0],kinds,20]
  key=hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
  queries.append({'cache_key':key,'text':texts[0],'embedding':res['embeddings'][0],'kinds':kinds})
assert data['snapshot'] and queries
sid=lit(data['snapshot']['id'])
result=query("SELECT coalesce(json_agg(json_build_object('cache_key',q.cache_key,'results',r.results)),'[]'::json) FROM jsonb_to_recordset("+lit(json.dumps(queries))+"::jsonb) q(cache_key text,text text,embedding jsonb,kinds text[]) JOIN wm_search_results r ON r.space_id="+sp+" AND r.snapshot_id="+sid+" AND r.query_hash=encode(extensions.digest(jsonb_build_array('hnsw-plan-v2',q.text,(q.embedding::text)::extensions.vector::text,q.kinds,20)::text,'sha256'),'hex')")
data['search_results']={r['cache_key']:r['results'] for r in result}
data['pipeline']=data['job']['pipeline'];data['private']=CONFIG['private'];data['attempt']=CONFIG['attempt']
blob=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
(root/'input.json').write_bytes(blob)
# Only new owned private diagnostic files are written; service state is untouched.
writer="from pathlib import Path;import sys;p=Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=True,mode=0o700);(p/'input.json').write_bytes(sys.stdin.buffer.read())"
command(['docker','exec','-i',CT,'python','-c',writer,CONFIG['private']],blob)
script=base64.b64decode(CONFIG['worker'])
writer="from pathlib import Path;import sys;(Path(sys.argv[1])/'capture_worker.py').write_bytes(sys.stdin.buffer.read())"
command(['docker','exec','-i',CT,'python','-c',writer,CONFIG['private']],script)
print(json.dumps({'phase':'offline_materialize','revision':355,'known_calls':len(data['calls']),'cached_searches':len(result),'snapshot':data['snapshot']['id']}),flush=True)
with (root/'worker.stdout').open('wb') as out,(root/'worker.stderr').open('wb') as err:
 r=subprocess.run(['docker','exec',CT,'python','-B',CONFIG['private']+'/capture_worker.py',CONFIG['private']+'/input.json'],stdout=out,stderr=err)
if r.returncode:raise RuntimeError('Offline replay stopped safely; private diagnostics retained')
metadata=json.loads((root/'worker.stdout').read_text().splitlines()[-1]);print(json.dumps(metadata),flush=True)
(root/'result.json').write_text(json.dumps(metadata,indent=2)+'\n')
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true');args=parser.parse_args()
    if not args.run:parser.error('Use --run for the read-only capture (no provider)')
    config={'ct':CT,'db':DB,'space':SPACE,'job':JOB,'attempt':ATTEMPT,'private':PRIVATE,'worker':base64.b64encode((HERE/'capture_worker.py').read_bytes()).decode()}
    source='CONFIG='+repr(config)+'\n'+REMOTE
    r=subprocess.run(['ssh','-i','/Users/glebkomzin/.ssh/id_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=30','root@178.105.167.26','python3 -'],input=source.encode())
    raise SystemExit(r.returncode)


if __name__=='__main__':main()
