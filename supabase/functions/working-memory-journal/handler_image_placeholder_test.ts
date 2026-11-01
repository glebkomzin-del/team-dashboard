import { handler } from './handler.ts'

Deno.test('image placeholder route is service scoped and forwards only lease plus original hash', async () => {
  const space = '66666666-6666-4666-8666-666666666666'
  const lease = '11111111-1111-4111-8111-111111111111'
  const job = 'a'.repeat(64)
  const bodyHash = 'b'.repeat(64)
  const calls: Array<{ path: string; body: Record<string, unknown> }> = []
  const callCount = () => calls.length
  const upstream = async (url: string | URL | Request, init?: RequestInit) => {
    const path = String(url)
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>
    calls.push({ path, body })
    if (path.endsWith('/rpc/wm_service_scope'))
      return Response.json([{ space_id: space, owner_id: '55555555-5555-4555-8555-555555555555' }])
    if (path.endsWith('/rpc/wm_archive_image_placeholder_job'))
      return Response.json({ state: 'archived', reason: 'verified_image_placeholder' })
    throw new Error('unexpected upstream route')
  }
  const serve = handler({ url: 'https://example.supabase.co', key: 'private-fixture' }, upstream)
  const input = { op: 'archive_image_placeholder_job', space_id: space, job_id: job,
    lease_token: lease, body_hash: bodyHash }
  const request = (value: unknown) => new Request('https://fixture', { method: 'POST',
    headers: { 'X-Memory-Token': 'c'.repeat(64) }, body: JSON.stringify(value) })
  const result = await serve(request(input))
  if (result.status !== 200 || (await result.json()).state !== 'archived') throw new Error('valid route failed')
  if (callCount() !== 2 || calls[1].path !== 'https://example.supabase.co/rest/v1/rpc/wm_archive_image_placeholder_job')
    throw new Error('wrong database route')
  const expected = { p_space_id: space, p_job_id: job, p_lease_token: lease, p_body_hash: bodyHash }
  if (JSON.stringify(calls[1].body) !== JSON.stringify(expected)) throw new Error('scope or hash changed')
  const invalid = await serve(request({ ...input, body_hash: 'invalid' }))
  if (invalid.status !== 400 || callCount() !== 3) throw new Error('invalid hash reached mutation')
  const wrongScope = await serve(request({ ...input, space_id: '77777777-7777-4777-8777-777777777777' }))
  if (wrongScope.status !== 403 || callCount() !== 4) throw new Error('wrong scope reached mutation')
})
