import {handler} from './handler.ts';
const space='11111111-1111-4111-8111-111111111111';
const owner='22222222-2222-4222-8222-222222222222';
function assert(value:unknown,message:string){if(!value)throw new Error(message)}
Deno.test('Drive lookup and manifest keep fixed scope; a missing original is optional only for lookup',async()=>{
 const seen:string[]=[];
 const upstream=(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input);seen.push(url);
  if(url.endsWith('/rpc/wm_service_scope'))return Response.json([{space_id:space,owner_id:owner}]);
  if(url.endsWith('/rpc/wm_drive_manifest')){
   assert(JSON.parse(String(init?.body)).p_space_id===space,'manifest scope');return Response.json([]);
  }
  assert(new URL(url).searchParams.get('space_id')==='eq.'+space,'lookup scope');return Response.json([]);
 }) as typeof fetch;
 const route=handler({url:'https://example.supabase.co',key:'private-test-only'},upstream);
 async function call(op:string){return route(new Request('https://example.invalid',{method:'POST',headers:{'X-Memory-Token':'a'.repeat(64)},body:JSON.stringify({space_id:space,op,document_id:'b'.repeat(64)})}))}
 let r=await call('archive_lookup');assert(r.status===200 && await r.json()===null,'missing optional lookup');
 r=await call('archive_document');assert(r.status===404,'worker lookup remains strict');
 r=await call('drive_manifest');assert(r.status===200 && JSON.stringify(await r.json())==='[]','read-only manifest');
 assert(seen.length===6,'only scoped upstream reads');
});
