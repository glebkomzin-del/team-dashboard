// Narrow server-to-server journal gateway. No model calls and no browser CORS.
// The database service key stays within Supabase's own Edge runtime.
type Scope = { space_id: string; owner_id: string }
type Settings = { url: string; key: string }
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const hash = /^[0-9a-f]{64}$/
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status,
  headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } })
const validInt = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0

export function handler(settings: Settings, requestUpstream: typeof fetch = fetch) {
  if (!/^https:\/\/[a-z0-9]+\.supabase\.co$/.test(settings.url) || !settings.key) throw new Error('Invalid private configuration')
  async function rest(path: string, data?: unknown): Promise<unknown> {
    const response = await requestUpstream(settings.url + '/rest/v1/' + path, {
      method: data === undefined ? 'GET' : 'POST', signal: AbortSignal.timeout(25000),
      headers: { apikey: settings.key, Authorization: 'Bearer ' + settings.key, 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
    })
    if (!response.ok) {
      let code = ''
      try { code = (await response.json()).code || '' } catch { /* Redacted error below. */ }
      if (['40001', '23505'].includes(code)) throw new Error('conflict')
      if (['22023', '23514', '23502', '22P02'].includes(code)) throw new Error('invalid')
      throw new Error('unavailable')
    }
    return response.json()
  }
  return async (req: Request): Promise<Response> => {
    if (req.method !== 'POST') return json({ error: 'Method not allowed' }, 405)
    const token = req.headers.get('X-Memory-Token') || ''
    if (!/^[0-9a-f]{64}$/.test(token)) return json({ error: 'Unauthorized' }, 401)
    try {
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token))
      const tokenHash = [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, '0')).join('')
      const scopes = await rest('rpc/wm_service_scope', { p_token_hash: tokenHash }) as Scope[]
      if (!Array.isArray(scopes) || scopes.length !== 1) return json({ error: 'Unauthorized' }, 401)
      const scope = scopes[0]
      // Read at most 4 MB even if a caller omits or lies about Content-Length.
      const reader = req.body?.getReader()
      if (!reader) return json({ error: 'Invalid request' }, 400)
      const chunks: Uint8Array[] = []; let size = 0
      while (true) {
        const next = await reader.read()
        if (next.done) break
        size += next.value.length
        if (size > 4_000_000) { await reader.cancel(); return json({ error: 'Request too large' }, 413) }
        chunks.push(next.value)
      }
      const bytes = new Uint8Array(size); let offset = 0
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length }
      let input: Record<string, unknown>
      try { input = JSON.parse(new TextDecoder().decode(bytes)) } catch { return json({ error: 'Invalid JSON' }, 400) }
      if (!input || Array.isArray(input) || input.space_id !== scope.space_id) return json({ error: 'Scope mismatch' }, 403)
      const query = (fields: Record<string, string>) => new URLSearchParams({ space_id: 'eq.' + scope.space_id, ...fields }).toString()
      if (input.op === 'space') {
        const rows = await rest('wm_spaces?' + new URLSearchParams({ id: 'eq.' + scope.space_id, select: 'id,owner_id,state,revision,archive_revision,label' })) as unknown[]
        return rows.length === 1 ? json(rows[0]) : json({ error: 'Space unavailable' }, 404)
      }
      if (input.op === 'source' && typeof input.version_id === 'string' && hash.test(input.version_id)) {
        const rows = await rest('wm_source_versions?' + query({ id: 'eq.' + input.version_id, select: '*' })) as unknown[]
        return rows.length === 1 ? json(rows[0]) : json({ error: 'Unknown source' }, 404)
      }
      if (input.op === 'entries' && validInt(input.after) && validInt(input.through) && input.after <= input.through) {
        return json(await rest('wm_journal?' + query({ and: `(revision.gt.${input.after},revision.lte.${input.through})`,
          order: 'revision.asc', limit: '100', select: 'revision,command_id,request_hash,kind,source_version,actor_id,payload,recorded_at,source:wm_source_versions(*)' })))
      }
      if (input.op === 'command' && typeof input.command_id === 'string' && uuid.test(input.command_id)) {
        const rows = await rest('wm_journal?' + query({ command_id: 'eq.' + input.command_id, select: 'revision,kind,actor_id,payload' })) as unknown[]
        return json(rows[0] || null)
      }
      if ((input.op === 'archive_documents' || input.op === 'archive_notes')
        && validInt(input.after) && validInt(input.through) && input.after <= input.through) {
        const table = input.op === 'archive_documents' ? 'wm_archive_documents' : 'wm_archive_notes'
        return json(await rest(table + '?' + query({ and: `(registered_revision.gt.${input.after},registered_revision.lte.${input.through})`,
          order: 'registered_revision.asc', limit: input.op === 'archive_documents' ? '10' : '50', select: '*' })))
      }
      if (input.op === 'archive_put' && input.document && typeof input.document === 'object' && !Array.isArray(input.document)) {
        return json(await rest('rpc/wm_archive_put', { p_space_id: scope.space_id, p_document: input.document }))
      }
      if (input.op === 'archive_note_put' && input.note && typeof input.note === 'object' && !Array.isArray(input.note)) {
        return json(await rest('rpc/wm_archive_note_put', { p_space_id: scope.space_id, p_note: input.note }))
      }

      if ((input.op === 'archive_document' || input.op === 'archive_lookup') && typeof input.document_id === 'string' && hash.test(input.document_id)) {
        const rows = await rest('wm_archive_documents?' + query({ id: 'eq.' + input.document_id, select: '*' })) as unknown[]
        return rows.length === 1 ? json(rows[0]) : input.op === 'archive_lookup' ? json(null) : json({ error: 'Unknown original' }, 404)
      }
      if (input.op === 'drive_manifest') return json(await rest('rpc/wm_drive_manifest', { p_space_id: scope.space_id }))
      if (input.op === 'processing_status') return json(await rest('rpc/wm_processing_status', { p_space_id: scope.space_id }))
      if (typeof input.snapshot_id === 'string' && uuid.test(input.snapshot_id)) {
        const snapshot = {p_space_id:scope.space_id,p_snapshot_id:input.snapshot_id}
        if (input.op === 'backup_begin') return json(await rest('rpc/wm_backup_begin', snapshot))
        if (input.op === 'backup_release') return json(await rest('rpc/wm_backup_release', snapshot))
        if (input.op === 'backup_page' && validInt(input.after)) return json(await rest('rpc/wm_backup_page', {...snapshot,p_after:input.after}))
      }
      if (input.op === 'generation_reviews')
        return json(await rest('wm_generation_reviews?' + query({state:'eq.pending',order:'created_at.asc',limit:'50',select:'id,label,expected_revision,review_sha256,state,created_at,job_id'})))
      if (typeof input.review_id === 'string' && uuid.test(input.review_id)) {
        if (input.op === 'generation_review') {
          const rows = await rest('wm_generation_reviews?' + query({id:'eq.'+input.review_id,select:'*'})) as unknown[]
          return json(rows[0] || null)
        }
        if (input.op === 'generation_stage' && validInt(input.expected_revision)
          && typeof input.label === 'string' && input.label.trim().length > 0 && input.label.length <= 200
          && input.payload && typeof input.payload === 'object' && !Array.isArray(input.payload)
          && (input.job_id == null || (typeof input.job_id === 'string' && hash.test(input.job_id))))
          return json(await rest('rpc/wm_generation_stage', {p_space_id:scope.space_id,p_review_id:input.review_id,
            p_expected_revision:input.expected_revision,p_label:input.label,p_payload:input.payload,p_job_id:input.job_id || null}))
        if (input.op === 'generation_decide' && input.actor_id === scope.owner_id
          && typeof input.command_id === 'string' && uuid.test(input.command_id) && validInt(input.expected_revision)
          && typeof input.review_sha256 === 'string' && hash.test(input.review_sha256)
          && (input.action === 'accept' || input.action === 'reject')
          && typeof input.reason === 'string' && input.reason.trim().length <= 4000)
          return json(await rest('rpc/wm_generation_decide', {p_space_id:scope.space_id,p_review_id:input.review_id,
            p_actor_id:scope.owner_id,p_command_id:input.command_id,p_expected_revision:input.expected_revision,
            p_review_sha256:input.review_sha256,p_action:input.action,p_reason:input.reason}))
      }
      if (input.op === 'job_detail' && typeof input.job_id === 'string' && hash.test(input.job_id))
        return json(await rest('rpc/wm_job_detail', { p_space_id: scope.space_id, p_job_id: input.job_id }))
      if (input.op === 'job_decision' && typeof input.command_id === 'string' && uuid.test(input.command_id)) {
        const rows = await rest('wm_job_decisions?' + query({command_id:'eq.' + input.command_id, select:'actor_id,request,result'})) as unknown[]
        return json(rows[0] || null)
      }
      if (input.op === 'resolve_job' && input.actor_id === scope.owner_id
        && typeof input.job_id === 'string' && hash.test(input.job_id)
        && typeof input.command_id === 'string' && uuid.test(input.command_id)
        && validInt(input.expected_revision) && typeof input.expected_updated_at === 'string'
        && typeof input.action === 'string' && ['retry','archive_only','rebase_prepared'].includes(input.action)
        && typeof input.reason === 'string' && input.reason.trim().length > 0 && input.reason.length <= 4000
        && (input.payload == null || (typeof input.payload === 'object' && !Array.isArray(input.payload)))) {
        return json(await rest('rpc/wm_resolve_job', {p_space_id:scope.space_id,p_actor_id:scope.owner_id,
          p_command_id:input.command_id,p_job_id:input.job_id,p_expected_revision:input.expected_revision,
          p_expected_updated_at:input.expected_updated_at,p_action:input.action,p_reason:input.reason,p_payload:input.payload || null}))
      }
      if (input.op === 'enqueue' && typeof input.document_id === 'string' && hash.test(input.document_id)
        && typeof input.pipeline === 'string' && input.pipeline.length > 0 && input.pipeline.length <= 512) {
        return json(await rest('rpc/wm_enqueue', { p_space_id: scope.space_id, p_document_id: input.document_id, p_pipeline: input.pipeline }))
      }
      if (input.op === 'claim_job' && typeof input.lease_token === 'string' && uuid.test(input.lease_token)
        && typeof input.pipeline === 'string' && input.pipeline.length > 0 && input.pipeline.length <= 512) {
        return json(await rest('rpc/wm_claim_job', { p_space_id: scope.space_id, p_pipeline: input.pipeline, p_lease_token: input.lease_token }))
      }
      if (typeof input.job_id === 'string' && hash.test(input.job_id) && typeof input.lease_token === 'string' && uuid.test(input.lease_token)) {
        const job = { p_space_id: scope.space_id, p_job_id: input.job_id, p_lease_token: input.lease_token }
        if (input.op === 'publish_job') return json(await rest('rpc/wm_publish_job', job))
        if (input.op === 'prepare_job' && input.payload && typeof input.payload === 'object' && !Array.isArray(input.payload))
          return json(await rest('rpc/wm_prepare_job', { ...job, p_payload: input.payload }))
        if (input.op === 'pause_job' && typeof input.reason === 'string' &&
          ['validation_failed', 'budget_exceeded', 'provider_outcome_unknown', 'transport_failed', 'context_changed', 'pipeline_changed'].includes(input.reason))
          return json(await rest('rpc/wm_pause_job', { ...job, p_reason: input.reason }))
        if (validInt(input.call_index) && input.call_index <= 31) {
          if (input.op === 'reserve_call' && typeof input.request_json === 'string' &&
            validInt(input.reserved_micro_usd) && input.reserved_micro_usd > 0)
            return json(await rest('rpc/wm_reserve_call', { ...job, p_call_index: input.call_index,
              p_request_json: input.request_json, p_reserved_micro_usd: input.reserved_micro_usd }))
          if (input.op === 'receive_call' && typeof input.response_json === 'string' &&
            (input.actual_micro_usd === null || validInt(input.actual_micro_usd)))
            return json(await rest('rpc/wm_receive_call', { ...job, p_call_index: input.call_index,
              p_response_json: input.response_json, p_actual_micro_usd: input.actual_micro_usd }))
        }
      }
      if (input.op === 'append' && validInt(input.expected_revision) && typeof input.command_id === 'string' && uuid.test(input.command_id)
        && (input.kind === 'source' || input.kind === 'human') && input.payload && typeof input.payload === 'object' && !Array.isArray(input.payload)) {
        // The caller cannot choose an actor or another space. Python performs
        // semantic/source validation before this restricted persistence boundary.
        if (input.kind === 'human' && input.actor_id !== scope.owner_id) return json({ error: 'Actor mismatch' }, 403)
        if (input.kind === 'source' && input.actor_id != null) return json({ error: 'Invalid source actor' }, 400)
        return json(await rest('rpc/wm_append', { p_space_id: scope.space_id, p_expected_revision: input.expected_revision,
          p_command_id: input.command_id, p_kind: input.kind, p_payload: input.payload,
          p_source: input.source || null, p_actor_id: input.kind === 'human' ? scope.owner_id : null }))
      }
      return json({ error: 'Unsupported operation' }, 400)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'unavailable'
      return json({ error: message === 'conflict' ? 'Revision conflict' : message === 'invalid' ? 'Invalid journal request' : 'Journal temporarily unavailable' },
        message === 'conflict' ? 409 : message === 'invalid' ? 400 : 503)
    }
  }
}
