import { handler } from './handler.ts'
const space='10000000-0000-4000-8000-000000000001'
const lease='20000000-0000-4000-8000-000000000001'
const job='b'.repeat(64)
function fixture() {
  const calls: {url:string;body:Record<string,unknown>}[]=[]
  const fetcher=(async (url: string|URL|Request,init?:RequestInit)=>{
    const body=JSON.parse(String(init?.body||'{}'));calls.push({url:String(url),body})
    return Response.json(String(url).endsWith('wm_service_scope')?[{space_id:space,owner_id:lease}]:
      String(url).endsWith('wm_search_put')?{saved:(body.p_documents as unknown[]).length}:{saved:true})
  }) as typeof fetch
  return {calls,run:handler({url:'https://fixture.supabase.co',key:'private-test'},fetcher)}
}
const request=(input:Record<string,unknown>)=>new Request('https://fixture.invalid',{method:'POST',
  headers:{'X-Memory-Token':'a'.repeat(64)},body:JSON.stringify({space_id:space,...input})})
const assert=(value:unknown)=>{if(!value)throw new Error('Assertion failed')}
Deno.test('hybrid query is scoped and rejects wrong dimensions or unbounded retrieval',async()=>{
  const valid={op:'search_query',search_snapshot_id:job,query_text:'C++ XMLA',query_embedding:Array(1536).fill(0.1),kinds:['work'],match_count:20}
  const f=fixture();assert((await f.run(request({...valid,p_space_id:'forged'}))).status===200)
  assert(f.calls[1].body.p_space_id===space && f.calls[1].url.endsWith('/rpc/wm_search_query'))
  for(const change of [{query_embedding:[0.1]},{match_count:100},{kinds:['private']},{search_snapshot_id:'invalid'}]){
    const g=fixture();assert((await g.run(request({...valid,...change}))).status===400);assert(g.calls.length===1)
  }
})
Deno.test('search put keeps the 32-document contract while bounding HNSW RPC batches',async()=>{
  const documents=Array.from({length:32},(_,i)=>({id:String(i)}))
  const f=fixture();const response=await f.run(request({op:'search_put',documents}))
  assert(response.status===200 && (await response.json()).saved===32)
  const writes=f.calls.slice(1);assert(writes.length===4)
  assert(writes.every((call,i)=>call.url.endsWith('/rpc/wm_search_put')
    && call.body.p_space_id===space && Array.isArray(call.body.p_documents)
    && (call.body.p_documents as unknown[]).length===8 && (call.body.p_documents as {id:string}[])[0].id===String(i*8)))
  const invalid=fixture();assert((await invalid.run(request({op:'search_put',documents:[...documents,{id:'32'}]}))).status===400)
  assert(invalid.calls.length===1)
})
Deno.test('search put retry accepts earlier idempotent chunks and returns the full saved count',async()=>{
  const documents=Array.from({length:32},(_,i)=>({id:String(i)}));const persisted=new Set<string>();let fail=true
  const calls: Record<string,unknown>[]=[]
  const fetcher=(async (url: string|URL|Request,init?:RequestInit)=>{
    const body=JSON.parse(String(init?.body||'{}'));calls.push(body)
    if (String(url).endsWith('wm_service_scope')) return Response.json([{space_id:space,owner_id:lease}])
    const chunk=body.p_documents as {id:string}[]
    if (fail && chunk[0].id==='16') { fail=false; return Response.json({code:'57014'},{status:503}) }
    chunk.forEach(document=>persisted.add(document.id));return Response.json({saved:chunk.length})
  }) as typeof fetch
  const run=handler({url:'https://fixture.supabase.co',key:'private-test'},fetcher)
  assert((await run(request({op:'search_put',documents}))).status===503)
  const response=await run(request({op:'search_put',documents}));assert(response.status===200 && (await response.json()).saved===32)
  assert(persisted.size===32 && calls.filter(call=>'p_documents' in call).length===7)
})
Deno.test('model call reservation and receipt are fixed-scope RPCs',async()=>{
  for(const op of ['reserve_call','receive_call']){
    const f=fixture();const response=await f.run(request({op,job_id:job,lease_token:lease,call_index:2,
      request_json:'{"prompt":"fiction"}',reserved_micro_usd:600,response_json:'{"content":[]}',actual_micro_usd:null,p_space_id:'forged'}))
    assert(response.status===200)
    assert(f.calls[1].url.endsWith('/rpc/wm_'+op))
    assert(f.calls[1].body.p_space_id===space && f.calls[1].body.p_job_id===job && f.calls[1].body.p_lease_token===lease)
  }
})
Deno.test('malformed reservations and worker configuration mutations are rejected',async()=>{
  for(const fields of [{call_index:-1},{call_index:1024},{reserved_micro_usd:0},{reserved_micro_usd:1.5},{lease_token:'invalid'},{job_id:'x&space_id=other'}]){
    const f=fixture();const response=await f.run(request({op:'reserve_call',job_id:job,lease_token:lease,
      call_index:0,request_json:'{}',reserved_micro_usd:50,...fields}))
    assert(response.status===400);assert(f.calls.length===1)
  }
  for(const op of ['enable_processing','set_budget','delete_job','retry_model_call']){
    const f=fixture();assert((await f.run(request({op,job_id:job,lease_token:lease}))).status===400);assert(f.calls.length===1)
  }
})
Deno.test('queue claim cannot cross space or omit lease identity',async()=>{
  const f=fixture()
  assert((await f.run(request({op:'claim_job',pipeline:'v9',lease_token:lease,space_id:'other'}))).status===403)
  assert((await f.run(request({op:'claim_job',pipeline:'v9'}))).status===400)
  assert(f.calls.every(c=>c.url.endsWith('wm_service_scope')))
})
Deno.test('owner recovery pins actor and input scope and cannot raise budget',async()=>{
  const values={op:'resolve_job',job_id:job,actor_id:lease,command_id:lease,expected_revision:3,
    expected_updated_at:'2026-09-07T00:00:00Z',action:'retry',reason:'Stored output reviewed',payload:null}
  const f=fixture();const r=await f.run(request({...values,p_actor_id:'forged',p_space_id:'forged',budget_micro_usd:999999}))
  assert(r.status===200);assert(f.calls[1].body.p_actor_id===lease && f.calls[1].body.p_space_id===space)
  assert(!('budget_micro_usd' in f.calls[1].body))
  for(const changed of [{actor_id:'forged'},{action:'retry_model_call'},{reason:''},{job_id:'invalid'},{command_id:'invalid'},{expected_revision:-1}]){
    const g=fixture();assert((await g.run(request({...values,...changed}))).status===400);assert(g.calls.length===1)
  }
})
Deno.test('job detail is scoped and no provider response bodies are queried directly',async()=>{
  const f=fixture();assert((await f.run(request({op:'job_detail',job_id:job}))).status===200)
  assert(f.calls[1].url.endsWith('/rpc/wm_job_detail'));assert(f.calls[1].body.p_space_id===space)
})
Deno.test('transport recovery is fixed-scope and does not accept an actor override',async()=>{
  const values={op:'recover_transport_job',job_id:job,pipeline:'canonical-v1',expected_revision:7,
    failure_id:lease,expected_updated_at:'2026-09-20T10:00:00Z',actor_id:'forged'}
  const f=fixture();assert((await f.run(request(values))).status===200)
  assert(f.calls[1].url.endsWith('/rpc/wm_recover_transport_job'))
  assert(f.calls[1].body.p_space_id===space && f.calls[1].body.p_job_id===job && f.calls[1].body.p_pipeline==='canonical-v1')
  assert(!('p_actor_id' in f.calls[1].body))
  assert(f.calls[1].body.p_failure_id===lease)
  for(const changed of [{job_id:'invalid'},{pipeline:''},{pipeline:'x'.repeat(513)},{failure_id:'invalid'},{expected_revision:-1},{expected_updated_at:7}]){
    const g=fixture();assert((await g.run(request({...values,...changed}))).status===400);assert(g.calls.length===1)
  }
})
Deno.test('transport pause binds lease and structured diagnostic without accepting actor scope',async()=>{
  const values={op:'pause_transport_job',job_id:job,lease_token:lease,failure_id:lease,
    diagnostic:{operation:'question_begin',http_status:503,sqlstate:null,retryable:true},actor_id:'forged'}
  const f=fixture();assert((await f.run(request(values))).status===200)
  assert(f.calls[1].url.endsWith('/rpc/wm_pause_transport_job'))
  assert(f.calls[1].body.p_space_id===space&&f.calls[1].body.p_lease_token===lease&&f.calls[1].body.p_failure_id===lease)
  assert(!('p_actor_id' in f.calls[1].body))
  for(const changed of [{job_id:'invalid'},{lease_token:'invalid'},{failure_id:'invalid'},{diagnostic:[]},{diagnostic:null}]){
    const g=fixture();assert((await g.run(request({...values,...changed}))).status===400);assert(g.calls.length===1)
  }
})
Deno.test('backup export is fixed-scope, paginated, and cannot query arbitrary tables',async()=>{
  const f=fixture();assert((await f.run(request({op:'backup_page',snapshot_id:lease,after:0,p_space_id:'forged',table:'auth.users'}))).status===200)
  assert(f.calls[1].url.endsWith('/rpc/wm_backup_page') && f.calls[1].body.p_space_id===space)
  assert(!('table' in f.calls[1].body))
  for(const values of [{snapshot_id:'invalid',after:0},{snapshot_id:lease,after:-1}]){
    const g=fixture();assert((await g.run(request({op:'backup_page',...values}))).status===400)
    assert(g.calls.length===1)
  }
})
