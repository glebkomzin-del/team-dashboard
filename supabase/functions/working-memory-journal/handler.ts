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
  if ((!/^https:\/\/[a-z0-9]+\.supabase\.co$/.test(settings.url) && settings.url !== 'http://api-gw:8000') || !settings.key) throw new Error('Invalid private configuration')
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
      throw new Error('unavailable:' + (/^[A-Z0-9]{5}$/.test(code) ? code : 'upstream'))
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
        const rows = await rest('wm_spaces?' + new URLSearchParams({ id: 'eq.' + scope.space_id, select: 'id,owner_id,state,revision,archive_revision,deletion_revision,label' })) as unknown[]
        return rows.length === 1 ? json(rows[0]) : json({ error: 'Space unavailable' }, 404)
      }
      if (input.op === 'source' && typeof input.version_id === 'string' && hash.test(input.version_id)) {
        const rows = await rest('wm_source_versions?' + query({ id: 'eq.' + input.version_id, select: '*' })) as unknown[]
        return rows.length === 1 ? json(rows[0]) : json({ error: 'Unknown source' }, 404)
      }
      if (input.op === 'entries' && validInt(input.after) && validInt(input.through) && input.after <= input.through) {
        return json(await rest('wm_journal?' + query({ and: `(revision.gt.${input.after},revision.lte.${input.through})`,
          order: 'revision.asc', limit: '10', select: 'revision,command_id,request_hash,kind,source_version,actor_id,payload,recorded_at,redaction_id,original_payload_hash,source:wm_source_versions(*)' })))
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
      const hashes = (value: unknown, max = 32): value is string[] => Array.isArray(value) && value.length <= max && value.every(v => typeof v === 'string' && hash.test(v))
      if (input.op === 'search_missing' && hashes(input.document_ids, 1024))
        return json(await rest('rpc/wm_search_missing', {p_space_id:scope.space_id,p_document_ids:input.document_ids}))
      if (input.op === 'search_cached' && hashes(input.content_hashes))
        return json(await rest('rpc/wm_search_cached', {p_space_id:scope.space_id,p_content_hashes:input.content_hashes}))
      if (input.op === 'search_put' && Array.isArray(input.documents) && input.documents.length <= 32) {
        let saved = 0
        // HNSW writes are content-addressed and idempotent in wm_search_put.
        // Bound each database transaction while retaining the 32-document API.
        for (let start = 0; start < input.documents.length; start += 8) {
          const documents = input.documents.slice(start, start + 8)
          const receipt = await rest('rpc/wm_search_put', {p_space_id:scope.space_id,p_documents:documents})
          if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt) || (receipt as { saved?: unknown }).saved !== documents.length)
            throw new Error('unavailable:upstream')
          saved += documents.length
        }
        return json({ saved })
      }
      if (typeof input.search_snapshot_id === 'string' && hash.test(input.search_snapshot_id)) {
        const search = {p_space_id:scope.space_id,p_search_snapshot_id:input.search_snapshot_id}
        if (input.op === 'search_snapshot' && hashes(input.document_ids, 50000))
          return json(await rest('rpc/wm_search_snapshot', {...search,p_document_ids:input.document_ids}))
        if (input.op === 'search_query' && typeof input.query_text === 'string' && input.query_text.length <= 7500
          && Array.isArray(input.query_embedding) && input.query_embedding.length === 1536 && input.query_embedding.every(v => typeof v === 'number' && Number.isFinite(v))
          && Array.isArray(input.kinds) && input.kinds.length <= 5 && input.kinds.every(v => ['knowledge','work','passage','summary','feedback'].includes(v))
          && (input.match_count === 20 || input.match_count === 40))
          return json(await rest('rpc/wm_search_query', {...search,p_query_text:input.query_text,p_query_embedding:input.query_embedding,p_kinds:input.kinds,p_match_count:input.match_count}))
      }
      if (input.actor_id === scope.owner_id) {
        const conversation = {p_space_id:scope.space_id,p_actor_id:scope.owner_id}
        if (input.op === 'conversations_list')
          return json(await rest('rpc/wm_conversations_list', conversation))
        if (input.op === 'conversation_create' && typeof input.conversation_id === 'string' && uuid.test(input.conversation_id)
          && (input.title == null || (typeof input.title === 'string' && input.title.trim().length > 0 && input.title.length <= 200)))
          return json(await rest('rpc/wm_conversation_create', {...conversation,p_conversation_id:input.conversation_id,p_title:input.title || null}))
        if (input.op === 'conversation_get' && typeof input.conversation_id === 'string' && uuid.test(input.conversation_id)
          && (input.before_question_id == null || (typeof input.before_question_id === 'string' && uuid.test(input.before_question_id))))
          return json(await rest('rpc/wm_conversation_get', {...conversation,p_conversation_id:input.conversation_id,
            p_before_question_id:input.before_question_id || null}))
      }
      if (typeof input.question_id === 'string' && uuid.test(input.question_id) && input.actor_id === scope.owner_id) {
        const question = {p_space_id:scope.space_id,p_question_id:input.question_id,p_actor_id:scope.owner_id}
        if (input.op === 'question_begin' && typeof input.request_json === 'string' && input.request_json.length <= 64000
          && validInt(input.revision) && validInt(input.archive_revision) && validInt(input.deletion_revision)
          && (input.conversation_id == null || (typeof input.conversation_id === 'string' && uuid.test(input.conversation_id))))
          return json(await rest('rpc/wm_question_begin', {...question,p_request_json:input.request_json,
            p_revision:input.revision,p_archive_revision:input.archive_revision,p_deletion_revision:input.deletion_revision,
            p_conversation_id:input.conversation_id || null}))
        if (validInt(input.call_index) && input.call_index <= 1023) {
          if (input.op === 'question_reserve' && typeof input.request_json === 'string' && input.request_json.length <= 1000000
            && validInt(input.reserved_micro_usd) && input.reserved_micro_usd > 0
            && (input.budget_micro_usd === null || (validInt(input.budget_micro_usd) && input.budget_micro_usd > 0)))
            return json(await rest('rpc/wm_question_reserve', {...question,p_call_index:input.call_index,
              p_request_json:input.request_json,p_reserved_micro_usd:input.reserved_micro_usd,p_budget_micro_usd:input.budget_micro_usd}))
          if (input.op === 'question_receive' && typeof input.response_json === 'string' && input.response_json.length <= 1000000
            && (input.actual_micro_usd === null || validInt(input.actual_micro_usd)))
            return json(await rest('rpc/wm_question_receive', {...question,p_call_index:input.call_index,
              p_response_json:input.response_json,p_actual_micro_usd:input.actual_micro_usd}))
        }
        if (input.op === 'question_complete' && typeof input.response_json === 'string' && input.response_json.length <= 1000000)
          return json(await rest('rpc/wm_question_complete', {...question,p_response_json:input.response_json}))
      }
      if (input.op === 'processing_status') return json(await rest('rpc/wm_processing_status', { p_space_id: scope.space_id }))
      if (input.actor_id === scope.owner_id) {
        const ownerDeletion = {p_space_id:scope.space_id,p_actor_id:scope.owner_id}
        if (input.op === 'source_deletion_inputs' && typeof input.source_id === 'string'
          && input.source_id.length > 0 && input.source_id.length <= 512)
          return json(await rest('rpc/wm_source_deletion_inputs', {...ownerDeletion,p_source_id:input.source_id}))
        if (input.op === 'source_deletion_ledger')
          return json(await rest('rpc/wm_source_deletion_ledger', ownerDeletion))
        if (typeof input.deletion_id === 'string' && uuid.test(input.deletion_id)) {
          const deletion = {...ownerDeletion,p_deletion_id:input.deletion_id}
          if (input.op === 'source_deletion_status')
            return json(await rest('rpc/wm_source_deletion_status', deletion))
          if (input.op === 'source_deletion_stage' && typeof input.source_id === 'string'
            && input.source_id.length > 0 && input.source_id.length <= 512
            && Array.isArray(input.packages) && input.packages.length <= 128)
            return json(await rest('rpc/wm_source_deletion_stage', {...deletion,p_source_id:input.source_id,p_packages:input.packages}))
          if (input.op === 'source_deletion_candidates' && typeof input.after === 'string' && input.after.length <= 300)
            return json(await rest('rpc/wm_source_deletion_candidates', {...deletion,p_after:input.after}))
          if (input.op === 'source_deletion_plan_put' && typeof input.scope === 'string'
            && ['archive_note','prepared_job','model_call','question','question_call','generation_review','journal_generation','job_decision'].includes(input.scope)
            && typeof input.record_key === 'string' && input.record_key.length > 0 && input.record_key.length <= 256
            && typeof input.before_hash === 'string' && hash.test(input.before_hash)
            && input.replacement && typeof input.replacement === 'object' && !Array.isArray(input.replacement)
            && input.scan_receipt && typeof input.scan_receipt === 'object' && !Array.isArray(input.scan_receipt))
            return json(await rest('rpc/wm_source_deletion_plan_put', {...deletion,p_scope:input.scope,p_record_key:input.record_key,
              p_before_hash:input.before_hash,p_replacement:input.replacement,p_scan_receipt:input.scan_receipt}))
          if (input.op === 'source_deletion_purge' && typeof input.command_id === 'string' && uuid.test(input.command_id)
            && input.projection_snapshot && typeof input.projection_snapshot === 'object' && !Array.isArray(input.projection_snapshot))
            return json(await rest('rpc/wm_source_deletion_purge', {...deletion,p_command_id:input.command_id,p_projection_snapshot:input.projection_snapshot}))
          if (input.op === 'source_deletion_check' && (input.check_scope === 'local_caches' || input.check_scope === 'backup_sets')
            && input.receipt && typeof input.receipt === 'object' && !Array.isArray(input.receipt))
            return json(await rest('rpc/wm_source_deletion_check', {...deletion,p_scope:input.check_scope,p_receipt:input.receipt}))
          if (input.op === 'source_deletion_finalize')
            return json(await rest('rpc/wm_source_deletion_finalize', deletion))
        }
        if (input.op === 'source_reimport_authorize' && typeof input.authorization_id === 'string' && uuid.test(input.authorization_id)
          && typeof input.source_id === 'string' && input.source_id.length > 0 && input.source_id.length <= 512
          && typeof input.content_hash === 'string' && hash.test(input.content_hash)
          && typeof input.reason === 'string' && input.reason.trim().length > 0 && input.reason.length <= 4000)
          return json(await rest('rpc/wm_source_reimport_authorize', {...ownerDeletion,p_authorization_id:input.authorization_id,
            p_source_id:input.source_id,p_content_hash:input.content_hash,p_reason:input.reason}))
      }
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
      if (input.op === 'recover_transport_job' && typeof input.job_id === 'string' && hash.test(input.job_id)
        && typeof input.pipeline === 'string' && input.pipeline.length > 0 && input.pipeline.length <= 512
        && typeof input.failure_id === 'string' && uuid.test(input.failure_id)
        && validInt(input.expected_revision) && typeof input.expected_updated_at === 'string')
        return json(await rest('rpc/wm_recover_transport_job', {p_space_id:scope.space_id,p_job_id:input.job_id,
          p_pipeline:input.pipeline,p_failure_id:input.failure_id,p_expected_revision:input.expected_revision,
          p_expected_updated_at:input.expected_updated_at}))
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
        if (input.op === 'pause_transport_job' && typeof input.failure_id === 'string' && uuid.test(input.failure_id)
          && input.diagnostic && typeof input.diagnostic === 'object' && !Array.isArray(input.diagnostic))
          return json(await rest('rpc/wm_pause_transport_job', {...job,p_failure_id:input.failure_id,p_diagnostic:input.diagnostic}))
        if (input.op === 'publish_job') return json(await rest('rpc/wm_publish_job', job))
        if (input.op === 'archive_image_placeholder_job' && typeof input.body_hash === 'string' && hash.test(input.body_hash))
          return json(await rest('rpc/wm_archive_image_placeholder_job', { ...job, p_body_hash: input.body_hash }))
        if (input.op === 'prepare_job' && input.payload && typeof input.payload === 'object' && !Array.isArray(input.payload))
          return json(await rest('rpc/wm_prepare_job', { ...job, p_payload: input.payload }))
        if (input.op === 'pause_job' && typeof input.reason === 'string' &&
          ['validation_failed', 'budget_exceeded', 'provider_outcome_unknown', 'transport_failed', 'context_changed', 'pipeline_changed', 'provider_shared_failure'].includes(input.reason))
          return json(await rest('rpc/wm_pause_job', { ...job, p_reason: input.reason }))
        if (input.op === 'isolate_failed_job' && typeof input.body_hash === 'string' && hash.test(input.body_hash)
          && (input.reason === 'validation_failed' || input.reason === 'provider_outcome_unknown'))
          return json(await rest('rpc/wm_isolate_failed_job', { ...job, p_reason: input.reason, p_body_hash: input.body_hash }))
        if (validInt(input.call_index) && input.call_index <= 1023) {
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
      const diagnostic = /^unavailable:[A-Z0-9]{5}$/.test(message) ? message.split(':')[1] : undefined
      return json({ code: diagnostic, error: message === 'conflict' ? 'Revision conflict' : message === 'invalid' ? 'Invalid journal request' : 'Journal temporarily unavailable' },
        message === 'conflict' ? 409 : message === 'invalid' ? 400 : 503)
    }
  }
}
