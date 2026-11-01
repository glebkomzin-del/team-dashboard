// Disposable local HTTP gateway: the actual Edge handler calls the restored SQL.
// PSQL uses only the isolated Unix socket/database supplied by this test.
import { handler } from '../../../../supabase/functions/working-memory-journal/handler.ts'

const db = Deno.env.get('TEST_DB') || ''
const socket = Deno.env.get('TEST_SOCKET') || ''
const port = Deno.env.get('TEST_PGPORT') || ''
if (!/^isolated[0-9]+$/.test(db) || !socket.startsWith('/private/tmp/dashboard-sol-operational-20261006/pg-test/socket') || port !== '55442') {
  throw new Error('Disposable SQL test target required')
}
const q = (value: unknown) => `'${String(value).replaceAll("'", "''")}'`
async function sql(statement: string): Promise<unknown> {
  const command = new Deno.Command('psql', {args:['-h',socket,'-p',port,'-d',db,'-XAt','-v','ON_ERROR_STOP=1','-c',statement],
    stdout:'piped',stderr:'piped'})
  const result = await command.output()
  if (!result.success) throw new Error('isolated SQL failed: '+new TextDecoder().decode(result.stderr).slice(0,500))
  const output = new TextDecoder().decode(result.stdout).trim()
  return output ? JSON.parse(output) : null
}
const row = (table:string,where:string,columns='*') => sql(`select coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb) from (select ${columns} from public.${table} where ${where}) x`)
async function upstream(url:string|URL|Request,init?:RequestInit):Promise<Response> {
  const path=String(url).split('/rest/v1/')[1] || ''
  const data=init?.body ? JSON.parse(String(init.body)) as Record<string,unknown> : {}
  try {
    let value:unknown
    if (path.startsWith('rpc/')) {
      const name=path.slice(4)
      if (!/^wm_[a-z_]+$/.test(name)) throw Error('unsupported RPC')
      if (name==='wm_service_scope') return Response.json([{space_id:'10000000-0000-0000-0000-000000000001',owner_id:'00000000-0000-0000-0000-000000000001'}])
      const args=Object.entries(data).map(([key,v])=>{
        if (!/^p_[a-z_]+$/.test(key)) throw Error('invalid argument')
        return `${key} => ${q(typeof v==='object' && v!==null ? JSON.stringify(v) : v)}${typeof v==='object' && v!==null?'::jsonb':''}`
      }).join(',')
      value=await sql(`select to_jsonb(public.${name}(${args}))`)
    } else {
      const [table,search='']=path.split('?');const query=new URLSearchParams(search)
      if (table==='wm_spaces') value=await row(table,`id=${q((query.get('id')||'').replace('eq.',''))}`)
      else if (table==='wm_archive_documents') value=await row(table,`space_id=${q('10000000-0000-0000-0000-000000000001')} and id=${q((query.get('id')||'').replace('eq.',''))}`)
      else if (table==='wm_journal') {
        const range=query.get('and')||''
        const match=/revision\.gt\.(\d+),revision\.lte\.(\d+)/.exec(range)
        if (!match) throw Error('invalid journal range')
        value=await sql(`select coalesce(jsonb_agg(to_jsonb(x) order by x.revision),'[]'::jsonb) from (
          select j.revision,j.command_id,j.request_hash,j.kind,j.source_version,j.actor_id,j.payload,j.recorded_at,
            j.redaction_id,j.original_payload_hash,to_jsonb(s) as source
          from public.wm_journal j left join public.wm_source_versions s on s.space_id=j.space_id and s.id=j.source_version
          where j.space_id='10000000-0000-0000-0000-000000000001' and j.revision>${match[1]} and j.revision<=${match[2]}
          order by j.revision limit 10) x`)
      } else throw Error('unsupported table')
    }
    return Response.json(value)
  } catch (error) {return Response.json({code:'XX000',detail:String(error)}, {status:500})}
}
const dispatch=handler({url:'http://api-gw:8000',key:'disposable-test-key'},upstream as typeof fetch)
Deno.serve({hostname:'127.0.0.1',port:18098},dispatch)
