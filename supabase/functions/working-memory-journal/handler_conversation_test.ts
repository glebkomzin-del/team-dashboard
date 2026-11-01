import { handler } from './handler.ts'
const space='10000000-0000-4000-8000-000000000001'
const owner='20000000-0000-4000-8000-000000000001'
const conversation='30000000-0000-4000-8000-000000000001'
const question='40000000-0000-4000-8000-000000000001'
function fixture(result:unknown={saved:true}) {
  const calls:{url:string;data:Record<string,unknown>}[]=[]
  const fetcher=(async(url:string|URL|Request,init?:RequestInit)=>{
    const data=JSON.parse(String(init?.body||'{}'));calls.push({url:String(url),data})
    return Response.json(String(url).endsWith('wm_service_scope')?[{space_id:space,owner_id:owner}]:result)
  }) as typeof fetch
  return {calls,run:handler({url:'https://fixture.supabase.co',key:'private-test'},fetcher)}
}
const request=(value:Record<string,unknown>)=>new Request('https://fixture.invalid',{method:'POST',
 headers:{'X-Memory-Token':'a'.repeat(64)},body:JSON.stringify({space_id:space,...value})})
const assert=(value:unknown)=>{if(!value)throw new Error('Assertion failed')}

Deno.test('conversation operations bind owner and space',async()=>{
  for(const value of [
    {op:'conversations_list',actor_id:owner},
    {op:'conversation_create',actor_id:owner,conversation_id:conversation,title:'Projekt X'},
    {op:'conversation_get',actor_id:owner,conversation_id:conversation,before_question_id:question},
  ]){
    const f=fixture();assert((await f.run(request({...value,p_space_id:'forged',p_actor_id:'forged'}))).status===200)
    assert(f.calls[1].data.p_space_id===space&&f.calls[1].data.p_actor_id===owner)
  }
  const bad=fixture();assert((await bad.run(request({op:'conversation_get',actor_id:'forged',conversation_id:conversation}))).status===400)
  assert(bad.calls.length===1)
})

Deno.test('question begin binds an optional conversation without changing legacy shape',async()=>{
  const f=fixture({request_hash:'a'.repeat(64)})
  assert((await f.run(request({op:'question_begin',question_id:question,actor_id:owner,conversation_id:conversation,
    request_json:'{"question":"Was ist offen?"}',revision:2,archive_revision:3,deletion_revision:4}))).status===200)
  assert(f.calls[1].url.endsWith('/rpc/wm_question_begin'))
  assert(f.calls[1].data.p_conversation_id===conversation)
  for(const changed of [{conversation_id:'invalid'},{before_question_id:'invalid'}]){
    const g=fixture();const op='before_question_id' in changed?'conversation_get':'question_begin'
    const body=op==='conversation_get'?{op,actor_id:owner,conversation_id:conversation,...changed}:
      {op,question_id:question,actor_id:owner,request_json:'{}',revision:2,archive_revision:3,deletion_revision:4,...changed}
    assert((await g.run(request(body))).status===400);assert(g.calls.length===1)
  }
})
