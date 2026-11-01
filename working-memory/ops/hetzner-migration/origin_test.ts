import { handler } from '../../../../supabase/functions/working-memory-journal/handler.ts'

Deno.test('internal migration upstream preserves token scope and REST path', async () => {
  const urls: string[] = []
  const run = handler({ url: 'http://api-gw:8000', key: 'synthetic-service-key' }, (async (url) => {
    urls.push(String(url))
    return Response.json([])
  }) as typeof fetch)
  const response = await run(new Request('http://fixture.invalid', { method: 'POST',
    headers: { 'X-Memory-Token': 'a'.repeat(64) }, body: JSON.stringify({ op: 'space' }) }))
  if (response.status !== 401 || urls[0] !== 'http://api-gw:8000/rest/v1/rpc/wm_service_scope' || urls.length !== 1) {
    throw new Error('Unauthorized internal request crossed the scope boundary')
  }
})

Deno.test('unapproved internal origins fail during configuration', () => {
  for (const url of ['http://other:8000', 'http://api-gw:8000/private', 'http://user@api-gw:8000', 'http://api-gw:8000?x=1']) {
    let rejected = false
    try { handler({ url, key: 'synthetic-service-key' }) } catch { rejected = true }
    if (!rejected) throw new Error('Unexpected origin accepted')
  }
})
