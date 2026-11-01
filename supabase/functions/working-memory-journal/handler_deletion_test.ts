import {handler} from './handler.ts'
const space='10000000-0000-4000-8000-000000000001'
const owner='20000000-0000-4000-8000-000000000001'
const deletion='30000000-0000-4000-8000-000000000001'
const command='40000000-0000-4000-8000-000000000001'
const token='a'.repeat(64)
const assert=(value:unknown)=>{if(!value)throw new Error('Assertion failed')}
function fixture(){
 const calls:{url:string;body:Record<string,unknown>}[]=[]
 const fetcher=(async(url:string|URL|Request,init?:RequestInit)=>{calls.push({url:String(url),body:JSON.parse(String(init?.body||'{}'))});return Response.json(String(url).endsWith('wm_service_scope')?[{space_id:space,owner_id:owner}]:[])}) as typeof fetch
 return {calls,run:handler({url:'https://fixture.supabase.co',key:'private-test'},fetcher)}
}
const req=(input:Record<string,unknown>)=>new Request('https://fixture.invalid',{method:'POST',headers:{'X-Memory-Token':token},body:JSON.stringify({space_id:space,actor_id:owner,...input})})
Deno.test('deletion workflow binds owner space and bounded plan rows',async()=>{
 const f=fixture();let response=await f.run(req({op:'source_deletion_stage',deletion_id:deletion,source_id:'drive:fixture',packages:[{format:'wm-redacted-source-v1'}]}))
 assert(response.status===200);assert(f.calls[1].url.endsWith('/rpc/wm_source_deletion_stage'));assert(f.calls[1].body.p_actor_id===owner&&f.calls[1].body.p_space_id===space)
 response=await f.run(req({op:'source_deletion_candidates',deletion_id:deletion,after:''}));assert(response.status===200);assert(f.calls[3].url.endsWith('/rpc/wm_source_deletion_candidates'))
 response=await f.run(req({op:'source_deletion_plan_put',deletion_id:deletion,scope:'model_call',record_key:'a'.repeat(64)+':0',before_hash:'b'.repeat(64),replacement:{request_json:'{}',response_json:null},scan_receipt:{changed:true,removed_characters:72}}))
 assert(response.status===200);const body=f.calls[5].body;assert(body.p_scope==='model_call'&&body.p_before_hash==='b'.repeat(64)&&!('p_actor_id' in (body.replacement as object||{})))
 response=await f.run(req({op:'source_deletion_purge',deletion_id:deletion,command_id:command,projection_snapshot:{format:'wm-projection-snapshot-v1'}}));assert(response.status===200);assert(f.calls[7].url.endsWith('/rpc/wm_source_deletion_purge'))
 response=await f.run(req({op:'source_deletion_status',deletion_id:deletion}));assert(response.status===200);assert(f.calls[9].url.endsWith('/rpc/wm_source_deletion_status'))
})
Deno.test('deletion gateway rejects forged actor and unbounded selectors',async()=>{
 for(const input of [
  {op:'source_deletion_stage',deletion_id:deletion,source_id:'drive:fixture',packages:[],actor_id:'forged'},
  {op:'source_deletion_candidates',deletion_id:deletion,after:'x'.repeat(301)},
  {op:'source_deletion_plan_put',deletion_id:deletion,scope:'unknown',record_key:'row',before_hash:'b'.repeat(64),replacement:{},scan_receipt:{}},
  {op:'source_reimport_authorize',authorization_id:command,source_id:'drive:fixture',content_hash:'bad',reason:'Owner restore'},
 ]) {const f=fixture();assert((await f.run(req(input))).status===400);assert(f.calls.length===1)}
})
