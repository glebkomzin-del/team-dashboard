import { handler } from '../../../../supabase/functions/working-memory-journal/handler.ts'
const space='10000000-0000-4000-8000-000000000001'
const owner='20000000-0000-4000-8000-000000000001'
const job='b'.repeat(64)
const bodyHash='a'.repeat(64)
const request=(input:Record<string,unknown>)=>new Request('https://fixture.invalid',{method:'POST',
  headers:{'X-Memory-Token':'c'.repeat(64)},body:JSON.stringify({space_id:space,...input})})
function fixture(){
  const calls:{url:string,body:Record<string,unknown>}[]=[]
  const fetcher=(async (url:string|URL|Request,init?:RequestInit)=>{
    const body=JSON.parse(String(init?.body||'{}'));calls.push({url:String(url),body})
    return Response.json(String(url).endsWith('wm_service_scope')?[{space_id:space,owner_id:owner}]:{isolated:true})
  }) as typeof fetch
  return {calls,run:handler({url:'https://fixture.supabase.co',key:'test-only'},fetcher)}
}
function assert(value:unknown,message:string){if(!value)throw new Error(message)}
Deno.test('isolation route forwards only fixed typed scope and evidence',async()=>{
  for(const reason of ['validation_failed','provider_outcome_unknown']){
    const f=fixture()
    const response=await f.run(request({op:'isolate_failed_job',job_id:job,lease_token:owner,body_hash:bodyHash,
      reason,p_space_id:'forged',actor_id:'forged',prepared_payload:{fake:true}}))
    assert(response.status===200,'valid route rejected')
    assert(f.calls.length===2 && f.calls[1].url.endsWith('/rpc/wm_isolate_failed_job'),'wrong RPC')
    const body=f.calls[1].body
    assert(body.p_space_id===space && body.p_job_id===job && body.p_lease_token===owner
      && body.p_body_hash===bodyHash && body.p_reason===reason,'scope/evidence mismatch')
    assert(Object.keys(body).sort().join(',')==='p_body_hash,p_job_id,p_lease_token,p_reason,p_space_id','unexpected field forwarded')
  }
})
Deno.test('isolation denies missing, malformed, and shared/global reasons',async()=>{
  const valid={op:'isolate_failed_job',job_id:job,lease_token:owner,body_hash:bodyHash,reason:'validation_failed'}
  for(const change of [{body_hash:'wrong'},{body_hash:null},{job_id:'bad'},{lease_token:'bad'},
    {reason:'provider_shared_failure'},{reason:'budget_exceeded'},{reason:'context_changed'},{reason:null}]){
    const f=fixture();const response=await f.run(request({...valid,...change}))
    assert(response.status===400 && f.calls.length===1,'invalid isolation reached RPC')
  }
  const f=fixture();const response=await f.run(request({op:'pause_job',job_id:job,lease_token:owner,reason:'provider_shared_failure'}))
  assert(response.status===200 && f.calls[1].url.endsWith('/rpc/wm_pause_job'),'shared failure must use nonisolated pause')
})
