import { handler } from './handler.ts'
const space='10000000-0000-4000-8000-000000000001'
const owner='20000000-0000-4000-8000-000000000001'
const review='30000000-0000-4000-8000-000000000001'
function fixture() {
  const calls: {url:string;body:Record<string,unknown>}[]=[]
  const fetcher=(async (url:string|URL|Request,init?:RequestInit)=>{
    calls.push({url:String(url),body:JSON.parse(String(init?.body||'{}'))})
    return Response.json(String(url).endsWith('wm_service_scope')?[{space_id:space,owner_id:owner}]:[])
  }) as typeof fetch
  return {calls,run:handler({url:'https://fixture.supabase.co',key:'private-test'},fetcher)}
}
const request=(input:Record<string,unknown>)=>new Request('https://fixture.invalid',{method:'POST',headers:{'X-Memory-Token':'a'.repeat(64)},body:JSON.stringify({space_id:space,...input})})
const assert=(value:unknown)=>{if(!value)throw new Error('Assertion failed')}
Deno.test('generation list and detail stay in fixed space and list excludes full payload',async()=>{
  const f=fixture();assert((await f.run(request({op:'generation_reviews'}))).status===200)
  const url=new URL(f.calls[1].url);assert(url.searchParams.get('space_id')==='eq.'+space);assert(url.searchParams.get('state')==='eq.pending');assert(!url.searchParams.get('select')?.includes('payload'))
  const g=fixture();assert((await g.run(request({op:'generation_review',review_id:review}))).status===200)
  assert(new URL(g.calls[1].url).searchParams.get('id')==='eq.'+review)
  const bad=fixture();assert((await bad.run(request({op:'generation_review',review_id:'id&space_id=other'}))).status===400);assert(bad.calls.length===1)
})
Deno.test('generation staging cannot change processing configuration or space',async()=>{
  const f=fixture();assert((await f.run(request({op:'generation_stage',review_id:review,expected_revision:4,label:'Geprüfte Originalfassung',payload:{format:'wm-generation-review-v1'},job_id:null,p_space_id:'other',budget_micro_usd:999999}))).status===200)
  assert(f.calls[1].url.endsWith('/rpc/wm_generation_stage'));assert(f.calls[1].body.p_space_id===space);assert(!('budget_micro_usd' in f.calls[1].body))
  for(const change of [{expected_revision:-1},{label:''},{job_id:'invalid'},{review_id:'invalid'},{payload:[]}]) {
    const g=fixture();assert((await g.run(request({op:'generation_stage',review_id:review,expected_revision:0,label:'Checked',payload:{},...change}))).status===400);assert(g.calls.length===1)
  }
})
Deno.test('generation acceptance requires scoped owner and pinned review hash; generic append stays closed',async()=>{
  const values={op:'generation_decide',review_id:review,actor_id:owner,command_id:owner,expected_revision:4,review_sha256:'a'.repeat(64),action:'accept',reason:'Alle Änderungen geprüft'}
  const f=fixture();assert((await f.run(request({...values,p_actor_id:'forged'}))).status===200);assert(f.calls[1].body.p_actor_id===owner)
  // Review notes have been optional since 20260909155014; null/oversized are invalid.
  const optional=fixture();assert((await optional.run(request({...values,reason:''}))).status===200)
  for(const change of [{actor_id:'other'},{review_sha256:'bad'},{action:'overwrite'},{reason:null},{reason:'x'.repeat(4001)},{expected_revision:1.2}]) {
    const g=fixture();assert((await g.run(request({...values,...change}))).status===400);assert(g.calls.length===1)
  }
  const direct=fixture();assert((await direct.run(request({op:'append',command_id:owner,expected_revision:0,kind:'generation',actor_id:owner,payload:{}}))).status===400);assert(direct.calls.length===1)
})
