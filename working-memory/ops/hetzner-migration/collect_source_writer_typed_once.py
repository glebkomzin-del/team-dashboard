"""One read-only Management SQL request. Default --prepare is local only.
--collect requires Root's actual fresh host inventory envelope and immutable plan.
No fake PASS: a Source receipt is emitted only after exact current positives.
Host envelope: {observed_at,containers:[actual Docker inspect objects],scope,
primary_receipts:[{path,sha256,host_path}]}; containers must equal one raw primary.
"""
import argparse,ast,base64,datetime as dt,hashlib,json,os,re,sys,urllib.request
from pathlib import Path

def need(ok,message):
 if not ok:raise ValueError(message)
def sha(body):return hashlib.sha256(body).hexdigest()
def read(ref):
 p=Path(ref['path']);need(p.is_absolute() and p.is_file() and not p.is_symlink() and p.stat().st_size<32000000,'Unsafe small primary')
 body=p.read_bytes();need(sha(body)==ref['sha256'],'Changed primary');return body
def constant(path,name):
 tree=ast.parse(Path(path).read_text())
 return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
def save(path,value):
 body=value if isinstance(value,bytes) else (json.dumps(value,indent=2)+'\n').encode()
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'wb') as stream:stream.write(body)
 return {'path':str(path),'sha256':sha(body)}
def fresh(value,now):
 observed=dt.datetime.fromisoformat(value.replace('Z','+00:00'));need(observed.tzinfo and 0<=(now-observed).total_seconds()<=300,'Stale actual observation')
def prepare(ops,local,output):
 ops=Path(ops);local=Path(local);sys.path.insert(0,str(ops))
 import final_quiescence_once as q
 import final_target_readonly_resume_after_return as r
 import final_prewrite_rollback_once as late
 business=(ops/'business-fingerprint.sql').read_bytes();need(sha(business)==late.QUERY_SHA,'Original43 business query differs')
 catalog=constant(ops/'catalog_reconcile_once.py','QUERY')
 bsql=business.decode().removeprefix("SET TIME ZONE 'UTC'; ").rstrip().removesuffix(';')
 queries={'business':bsql,'state':r.STATE_SQL,'auth':r.AUTH_SQL,'roles':q.EFFECTIVE_PRIVILEGES_SQL,'acl':q.acl_query(),'catalog':catalog,'cron':r.CRON_SQL}
 # Original SELECT bodies share one statement snapshot. Preserve proven SET UTC + SELECT-last API contract.
 ctes=',\n'.join(k+' AS ('+v.rstrip(';')+')' for k,v in queries.items())
 fields=[]
 for k in queries:
  if k in ('business','state','auth','cron'):fields+= ["'"+k+"',(SELECT value FROM "+k+")"]
  else:fields+=["'"+k+"',(SELECT coalesce(json_agg(x),'[]'::json) FROM "+k+' x)']
 fields+=["'catalog_function_count',(SELECT count(*) FROM catalog)"]
 query="SET TIME ZONE 'UTC'; WITH "+ctes+" SELECT json_build_object("+','.join(fields)+") AS value;"
 root=local.parent
 paths={'baseline':local/'source-frozen-business-baseline.json','config':local/'source-original-config-private.json','auth':local/'auth-original-user-hashes-primary.json','catalog':root/'current-evidence/catalog-reconcile-1/actual-catalog-private.json'}
 originals={k:{'path':str(p.resolve()),'sha256':sha(p.read_bytes())} for k,p in paths.items()}
 need(len(json.loads(read(originals['catalog'])))==43,'Original actual catalog provenance incomplete')
 out=Path(output);need(out.is_absolute() and not out.exists() and not any(p.is_symlink() for p in (out,*out.parents)),'New private directory required');out.mkdir(mode=0o700)
 sqlref=save(out/'one-source-readonly.sql',query.encode())
 plan={'problem_id':'HZ-MIGRATION-20261003-FINAL-CUTOVER','run_dir':'/opt/dashboard-supabase-20261003/'+local.name,'original_business_query_sha256':late.QUERY_SHA,'catalog_query_sha256':sha(catalog.encode()),'query':sqlref,'originals':originals,'ops':str(ops.resolve()),'table_names':late.TABLES,'source_requests':1,'operational_go':False}
 save(out/'plan.json',plan);return plan

def canonical_oid(value):
 # PostgreSQL oid may be an integer or canonical decimal string in Management JSON.
 if type(value) is int:
  normalized=value
 elif type(value) is str:
  need(re.fullmatch(r'[1-9][0-9]*',value) is not None and len(value)<=10,'Noncanonical actual catalog OID')
  normalized=int(value);need(str(normalized)==value,'Noncanonical actual catalog OID')
 else:
  raise ValueError('Unknown actual catalog OID type')
 need(1<=normalized<=4294967295,'Actual catalog OID outside PostgreSQL range')
 return normalized

def catalog_identity(rows):
 need(type(rows) is list and len(rows)==43,'Actual catalog must contain exactly43 identities')
 pairs=[]
 for row in rows:
  need(type(row) is dict and type(row.get('object')) is str and bool(row['object']),'Actual catalog signature missing')
  pairs.append((canonical_oid(row.get('oid')),row['object']))
 need(len(set(pairs))==43 and len({oid for oid,_ in pairs})==43,'Actual catalog identities duplicate')
 return set(pairs)

def positives(payload,plan,host,now):
 originals={k:json.loads(read(ref)) for k,ref in plan['originals'].items()}
 def projection(rows):return {r['table_name']:(r['rows'],r['sha256']) for r in rows}
 need(len(payload['business'])==len(plan['table_names']) and set(projection(payload['business']))==set(plan['table_names']) and projection(payload['business'])==projection(originals['baseline']['tables']),'Source actual original43 business differs')
 catalog=payload['catalog'];need(type(payload['catalog_function_count']) is int and payload['catalog_function_count']==len(catalog),'Catalog count not actual')
 need(catalog_identity(catalog)==catalog_identity(originals['catalog']),'Actual catalog OIDs/signatures changed')
 need(all(r[k] is False for r in catalog for k in ('anon_execute','authenticated_execute','service_execute')),'Actual catalog function executable')
 expected=[{'role':r,'writable_tables':0,'executable_writers':0} for r in ('anon','authenticated','service_role')]
 need(payload['roles']==expected and all(type(r[k]) is int for r in payload['roles'] for k in ('writable_tables','executable_writers')),'Source effective rights not zero')
 state=payload['state'];need(all(type(state[k]) is int and state[k]==0 for k in ('running','unknown_model','unknown_question','cron','queued_http')),'Source work/calls/cron/queue not zero')
 need(state['config']==[{**c,'enabled':False} for c in originals['config']] and bool(state['config']) and payload['acl']==[],'Source config/ACL not closed')
 need(payload['auth']==originals['auth']['original_user_hashes'] and bool(payload['auth']),'Original Source Auth differs')
 fresh(host['observed_at'],now);need(host['primary_receipts'] and host['scope'],'Actual bounded host inventory absent')
 need(any(json.loads(read(ref))==host['containers'] for ref in host['primary_receipts']),'Actual host containers not raw bound')
 need(host['containers'] and all(c['State']['Running'] is True for c in host['containers']),'Running host inventory ambiguous')
 for c in host['containers']:
  env=dict(x.split('=',1) for x in c['Config'].get('Env',[]) if '=' in x)
  need(env.get('SUPABASE_URL','').rstrip('/')!='https://lghwikeotbkmojyyjglz.supabase.co','Source backend running')
 return originals

def collect(plan_path,host_path,output):
 plan=json.loads(Path(plan_path).read_bytes());query=read(plan['query']);host=json.loads(Path(host_path).read_bytes())
 out=Path(output);need(out.is_absolute() and not out.exists(),'Exclusive output required');out.mkdir(mode=0o700)
 save(out/'source-read-intent.json',{'source_requests':1,'query_sha256':sha(query),'writes':0,'automatic_retries':0})
 sys.path.insert(0,plan['ops']);import final_phase_common as common
 common.ERROR_DIR=out/'errors'
 try:
  token=common.source_token();req=urllib.request.Request('https://api.supabase.com/v1/projects/'+common.PROJECT+'/database/query',data=json.dumps({'query':query.decode()}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=45) as response:
   body=response.read();save(out/'http-primary.json',{'status':response.status,'headers':list(response.headers.items()),'body_b64':base64.b64encode(body).decode()})
  rawref=save(out/'source-raw-response.json',body);observed=dt.datetime.now(dt.timezone.utc);rows=json.loads(body)
  need(isinstance(rows,list) and len(rows)==1 and set(rows[0])=={'value'},'Actual one Source payload required');payload=rows[0]['value'];positives(payload,plan,host,observed)
  refs=[rawref,plan['query'],{'path':str(Path(host_path).resolve()),'sha256':sha(Path(host_path).read_bytes())},*plan['originals'].values(),*host['primary_receipts']]
  # Destination mapping remains explicit and no receipt source fields are invented.
  hostdir=plan['run_dir']+'/'+out.name;mapping=[];primaries=[]
  for i,ref in enumerate(refs):
   local=save(out/('bound-'+str(i)+'.raw'),read(ref));dest=hostdir+'/bound-'+str(i)+'.raw';mapping.append({**local,'host_path':dest});primaries.append({'path':dest,'sha256':local['sha256']})
  receipt={'problem_id':plan['problem_id'],'run_dir':plan['run_dir'],'observed_at':observed.isoformat(),'query_sha256':sha(query),'catalog_query_sha256':plan['catalog_query_sha256'],'original_business_query_sha256':plan['original_business_query_sha256'],'catalog_function_count':payload['catalog_function_count'],'roles':payload['roles'],'source_config':payload['state']['config'],'source_backend_running':False,'process_scope':host['scope'],'primary_receipts':primaries}
  receiptref=save(out/'source-effective-before-writer-open.json',receipt)
  save(out/'assembler-input-fragment.json',{'receipts':{'source':{**receiptref,'host_path':plan['run_dir']+'/source-effective-before-writer-open.json'}},'primary_files':mapping,'source_query_sha256':sha(query),'operational_go':False})
  return {'status':'ACTUAL_SOURCE_POSITIVES_VALIDATED','receipt':receiptref,'assembler_fragment':str(out/'assembler-input-fragment.json')}
 except Exception as e:
  err={'type':type(e).__name__,'cause':str(e)}
  if hasattr(e,'read'):err['body_b64']=base64.b64encode(e.read()).decode()
  save(out/'failure-private.json',err);raise RuntimeError('Source receipt not emitted; private failure retained; no retry') from None

def main():
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--ops');p.add_argument('--local-run');p.add_argument('--output',required=True);p.add_argument('--collect-plan');p.add_argument('--host-observation');a=p.parse_args();os.umask(0o077)
 result=prepare(a.ops,a.local_run,a.output) if a.prepare else collect(a.collect_plan,a.host_observation,a.output)
 print(json.dumps({'prepared':a.prepare,'result':result if not a.prepare else {'query_sha256':result['query']['sha256'],'operational_go':False}}))
if __name__=='__main__':main()
