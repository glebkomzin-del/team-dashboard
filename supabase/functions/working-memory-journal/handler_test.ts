import { handler } from './handler.ts'
const assert = (value: unknown, message = 'Assertion failed') => { if (!value) throw new Error(message) }
const space = '10000000-0000-4000-8000-000000000001'
const owner = '00000000-0000-4000-8000-000000000001'
const token = 'a'.repeat(64)
function fixture(result: unknown = [], status = 200, scopes = [{ space_id: space, owner_id: owner }]) {
  const calls: {url: string; data: unknown}[] = []
  const upstream = (async (url: string | URL | Request, init?: RequestInit) => {
    const path = String(url); calls.push({url: path,data: init?.body ? JSON.parse(String(init.body)) : null})
    if (path.endsWith('/rpc/wm_service_scope')) return Response.json(scopes)
    return Response.json(result, { status })
  }) as typeof fetch
  return {calls, run: handler({url: 'https://fixture.supabase.co',key: 'private-fixture-key'},upstream)}
}
function request(input: unknown, credential = token) { return new Request('https://fixture.invalid/function', {
  method:'POST',headers:{'X-Memory-Token':credential,'Content-Type':'application/json'},body:JSON.stringify(input)}) }
Deno.test('missing and unknown tokens cannot read journal',async () => {
  const first = fixture(); assert((await first.run(request({},''))).status===401);assert(first.calls.length===0)
  const second=fixture([],200,[]);assert((await second.run(request({space_id:space,op:'space'}))).status===401)
  assert(second.calls.length===1)
})
Deno.test('token cannot select another owner space or forge human actor',async () => {
  const f=fixture()
  assert((await f.run(request({space_id:'other',op:'space'}))).status===403)
  assert((await f.run(request({space_id:space,op:'append',kind:'human',expected_revision:1,
    command_id:'20000000-0000-4000-8000-000000000001',actor_id:'other',payload:{}}))).status===403)
  assert(f.calls.every(c=>c.url.endsWith('/rpc/wm_service_scope')))
})
Deno.test('only allowed operations and validated selectors reach PostgREST',async () => {
  const f=fixture()
  for(const op of ['delete','sql','users','secrets'])assert((await f.run(request({space_id:space,op}))).status===400)
  assert((await f.run(request({space_id:space,op:'source',version_id:'x&space_id=other'}))).status===400)
  assert(f.calls.every(c=>c.url.endsWith('/rpc/wm_service_scope')))
})
Deno.test('snapshot query is bounded and always scoped',async () => {
  const f=fixture([{revision:2}])
  const response=await f.run(request({space_id:space,op:'entries',after:1,through:3}))
  assert(response.status===200)
  const query=new URL(f.calls[1].url).searchParams
  assert(query.get('space_id')==='eq.'+space);assert(query.get('and')==='(revision.gt.1,revision.lte.3)');assert(query.get('order')==='revision.asc')
  assert(query.get('limit')==='10');assert(query.get('select')==='revision,command_id,request_hash,kind,source_version,actor_id,payload,recorded_at,redaction_id,original_payload_hash,source:wm_source_versions(*)')
})
Deno.test('append binds actor and preserves retry identity and expected revision',async () => {
  const f=fixture({revision:2,repeated:false});const command='20000000-0000-4000-8000-000000000001'
  assert((await f.run(request({space_id:space,op:'append',expected_revision:1,command_id:command,kind:'human',actor_id:owner,payload:{reason:'fixture'}}))).status===200)
  const data=f.calls[1].data as Record<string,unknown>
  assert(data.p_space_id===space&&data.p_actor_id===owner&&data.p_command_id===command&&data.p_expected_revision===1)
})
Deno.test('upstream errors redact private content and distinguish conflicts',async () => {
  const f=fixture({code:'40001',message:'PRIVATE ORIGINAL'},500)
  const response=await f.run(request({space_id:space,op:'space'}))
  assert(response.status===409);assert(!(await response.text()).includes('PRIVATE'))
})
Deno.test('oversized and invalid bodies fail without a storage write',async () => {
  const f=fixture()
  assert((await f.run(request({space_id:space,op:'append',payload:'x'.repeat(4_000_001)}))).status===413)
  assert(f.calls.every(c=>c.url.endsWith('/rpc/wm_service_scope')))
  const invalid=new Request('https://fixture.invalid',{method:'POST',headers:{'X-Memory-Token':token},body:'not json'})
  assert((await f.run(invalid)).status===400)
})
Deno.test('archive pages are pinned to scope and snapshot with bounded full originals',async () => {
  for(const [op,limit] of [['archive_documents','10'],['archive_notes','50']]) {
    const f=fixture([])
    assert((await f.run(request({space_id:space,op,after:7,through:21}))).status===200)
    const query=new URL(f.calls[1].url).searchParams
    assert(query.get('space_id')==='eq.'+space && query.get('and')==='(registered_revision.gt.7,registered_revision.lte.21)')
    assert(query.get('limit')===limit)
  }
  const f=fixture()
  assert((await f.run(request({space_id:space,op:'archive_documents',after:-1,through:21}))).status===400)
  assert(f.calls.length===1)
})
Deno.test('archive writes cannot pick another space or use the action journal RPC',async () => {
  for(const [op,field,rpc] of [['archive_put','document','wm_archive_put'],['archive_note_put','note','wm_archive_note_put']]) {
    const f=fixture({archive_revision:1})
    const original={id:'fixture',body:'Original content'}
    assert((await f.run(request({space_id:space,op,[field]:original,p_space_id:'forged'}))).status===200)
    const data=f.calls[1].data as Record<string,unknown>
    assert(data.p_space_id===space && f.calls[1].url.endsWith('/rpc/'+rpc))
    assert(!f.calls.some(call=>call.url.endsWith('/rpc/wm_append')))
    const blocked=fixture()
    assert((await blocked.run(request({space_id:'other',op,[field]:original}))).status===403)
    assert(blocked.calls.length===1)
  }
})
Deno.test('question operations bind the owner, space, revision and budget',async () => {
  const question='20000000-0000-4000-8000-000000000001'
  const begin=fixture({request_hash:'a'.repeat(64)})
  assert((await begin.run(request({space_id:space,op:'question_begin',question_id:question,actor_id:owner,
    request_json:'{"question":"fixture"}',revision:7,archive_revision:9,deletion_revision:2}))).status===200)
  const first=begin.calls[1].data as Record<string,unknown>
  assert(first.p_space_id===space&&first.p_actor_id===owner&&first.p_revision===7&&first.p_archive_revision===9&&first.p_deletion_revision===2)
  const forged=fixture()
  assert((await forged.run(request({space_id:space,op:'question_begin',question_id:question,actor_id:'forged',
    request_json:'{}',revision:7,archive_revision:9,deletion_revision:2}))).status===400)
  assert(forged.calls.length===1)
  const reserve=fixture({send:true,request_hash:'b'.repeat(64)})
  assert((await reserve.run(request({space_id:space,op:'question_reserve',question_id:question,actor_id:owner,
    call_index:0,request_json:'{"model":"fixture"}',reserved_micro_usd:10,budget_micro_usd:100}))).status===200)
  const saved=reserve.calls[1].data as Record<string,unknown>
  assert(saved.p_question_id===question&&saved.p_call_index===0&&saved.p_budget_micro_usd===100)
  const uncapped=fixture({send:true,request_hash:'c'.repeat(64)})
  assert((await uncapped.run(request({space_id:space,op:'question_reserve',question_id:question,actor_id:owner,
    call_index:1,request_json:'{"model":"fixture","uncapped":true}',reserved_micro_usd:10,budget_micro_usd:null}))).status===200)
  assert((uncapped.calls[1].data as Record<string,unknown>).p_budget_micro_usd===null)
})
