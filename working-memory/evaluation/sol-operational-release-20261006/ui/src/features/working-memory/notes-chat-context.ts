export type CitationTarget = { page: 'todos' | 'wissen' | 'archiv'; params: Record<string, string> }
export type Citation = { id: string; kind: 'task' | 'task_set' | 'knowledge' | 'user_memory' | 'working_source' | 'archive_source'; label: string; quote: string; event_date: string; target: CitationTarget }
export type Coverage = { mode: 'structured_tasks' | 'planned_tasks' | 'memory_write' | 'retrieval'; as_of: string; latest_available_as_of: string; is_latest: boolean; working_sources: number; archived_sources: number; archived_only_sources: number; pending_jobs: number; task_total: number; matched_tasks: number | null; context_messages: number; context_omitted: number; output_truncated: boolean; retrieval?: { documents_considered: number; max_hits_per_round: number; search_rounds: number; scope: 'targeted' | 'global'; time_range: { from: string | null; to: string | null }; hits_returned: number; overview: { key: string; source_snapshot_id: string; incremental_content_hash_cache: true }; evidence_rows: number; limited: boolean; task_candidates_omitted: number; evidence_bytes_truncated: boolean } | null }
export type MemoryAction = { action_id: string; kind: string; status: string; receipt?: unknown; error?: string }
export type ConversationMetadata = { conversation_id: string; title: string; created_at: string; updated_at: string }
export type ConversationSummary = ConversationMetadata & { message_count: number; last_message_preview: string }
export type ConversationMessage = { message_id: string; role: 'user' | 'assistant'; content: string; created_at: string; request_id?: string; citations: Citation[]; coverage?: Coverage; memory_actions: MemoryAction[] }
export type ConversationDetail = { conversation: ConversationMetadata; messages: ConversationMessage[] }

const record = (value: unknown): Record<string, unknown> | undefined => value && typeof value === 'object' ? value as Record<string, unknown> : undefined

export function isCitation(value: unknown): value is Citation {
  const citation = record(value)
  const target = record(citation?.target)
  const params = record(target?.params)
  return !!citation && !!target && !!params && typeof citation.id === 'string' && typeof citation.label === 'string'
    && typeof citation.quote === 'string' && typeof citation.event_date === 'string'
    && ['task', 'task_set', 'knowledge', 'user_memory', 'working_source', 'archive_source'].includes(String(citation.kind))
    && ['todos', 'wissen', 'archiv'].includes(String(target.page))
    && Object.values(params).every(param => typeof param === 'string')
}

export function citationIsNavigable(citation: Citation) {
  return citation.kind !== 'user_memory'
}

export function isCoverage(value: unknown): value is Coverage {
  const coverage = record(value)
  const retrieval = record(coverage?.retrieval)
  const timeRange = record(retrieval?.time_range)
  const overview = record(retrieval?.overview)
  const mode = String(coverage?.mode)
  const common = !!coverage && ['structured_tasks', 'planned_tasks', 'memory_write', 'retrieval'].includes(mode)
    && typeof coverage.as_of === 'string' && typeof coverage.latest_available_as_of === 'string'
    && typeof coverage.is_latest === 'boolean' && typeof coverage.working_sources === 'number'
    && typeof coverage.archived_sources === 'number' && typeof coverage.archived_only_sources === 'number'
    && typeof coverage.pending_jobs === 'number' && typeof coverage.task_total === 'number'
    && (coverage.matched_tasks === null || typeof coverage.matched_tasks === 'number')
    && typeof coverage.context_messages === 'number' && typeof coverage.context_omitted === 'number'
    && typeof coverage.output_truncated === 'boolean'
  if (!common) return false
  if (mode !== 'retrieval') {
    return (coverage.retrieval === null || coverage.retrieval === undefined)
      && (mode === 'memory_write' || typeof coverage.matched_tasks === 'number')
  }
  return coverage.matched_tasks === null && !!retrieval && typeof retrieval.documents_considered === 'number'
    && typeof retrieval.max_hits_per_round === 'number' && typeof retrieval.search_rounds === 'number'
    && ['targeted', 'global'].includes(String(retrieval.scope)) && !!timeRange
    && (timeRange.from === null || typeof timeRange.from === 'string') && (timeRange.to === null || typeof timeRange.to === 'string')
    && typeof retrieval.hits_returned === 'number' && !!overview && typeof overview.key === 'string'
    && typeof overview.source_snapshot_id === 'string' && overview.incremental_content_hash_cache === true
    && typeof retrieval.evidence_rows === 'number' && typeof retrieval.limited === 'boolean'
    && typeof retrieval.task_candidates_omitted === 'number' && typeof retrieval.evidence_bytes_truncated === 'boolean'
}

export function isConversationMetadata(value: unknown): value is ConversationMetadata {
  const conversation = record(value)
  return !!conversation && typeof conversation.conversation_id === 'string' && typeof conversation.title === 'string'
    && typeof conversation.created_at === 'string' && typeof conversation.updated_at === 'string'
}

export function isConversationSummary(value: unknown): value is ConversationSummary {
  const conversation = record(value)
  return !!conversation && typeof conversation.message_count === 'number'
    && typeof conversation.last_message_preview === 'string' && isConversationMetadata(conversation)
}

function isMemoryAction(value: unknown): value is MemoryAction {
  const action = record(value)
  return !!action && typeof action.action_id === 'string' && typeof action.kind === 'string' && typeof action.status === 'string'
    && (action.error === undefined || typeof action.error === 'string')
}

function parseMessage(value: unknown): ConversationMessage | undefined {
  const message = record(value)
  if (!message || typeof message.message_id !== 'string' || !['user', 'assistant'].includes(String(message.role))
    || typeof message.content !== 'string' || typeof message.created_at !== 'string') return
  const citations = message.citations === undefined ? [] : Array.isArray(message.citations) && message.citations.every(isCitation) ? message.citations : undefined
  const memoryActions = message.memory_actions === undefined ? [] : Array.isArray(message.memory_actions) && message.memory_actions.every(isMemoryAction) ? message.memory_actions : undefined
  // The persisted SQL response uses jsonb_strip_nulls recursively. Restore only
  // known nullable fields; missing required counts and evidence still fail validation.
  const storedCoverage = record(message.coverage)
  const storedRetrieval = record(storedCoverage?.retrieval)
  const storedRange = record(storedRetrieval?.time_range)
  const coverage = storedCoverage ? {
    ...storedCoverage,
    ...(['retrieval', 'memory_write'].includes(String(storedCoverage.mode))
      && storedCoverage.matched_tasks === undefined ? { matched_tasks: null } : {}),
    ...(storedRetrieval && storedRange ? { retrieval: { ...storedRetrieval,
      time_range: { ...storedRange, from: storedRange.from ?? null, to: storedRange.to ?? null },
    } } : {}),
  } : message.coverage
  if (!citations || !memoryActions || (coverage !== undefined && !isCoverage(coverage))) return
  return {
    message_id: message.message_id,
    role: message.role as 'user' | 'assistant',
    content: message.content,
    created_at: message.created_at,
    ...(typeof message.request_id === 'string' ? { request_id: message.request_id } : {}),
    citations,
    ...(coverage ? { coverage: coverage as Coverage } : {}),
    memory_actions: memoryActions,
  }
}

export function parseConversationList(value: unknown): ConversationSummary[] | undefined {
  const body = record(value)
  return body && Array.isArray(body.conversations) && body.conversations.every(isConversationSummary) ? body.conversations : undefined
}

export function parseCreatedConversation(value: unknown, expectedId: string): ConversationMetadata | undefined {
  const body = record(value)
  return body && isConversationMetadata(body.conversation) && body.conversation.conversation_id === expectedId
    ? body.conversation : undefined
}

export function parseConversationDetail(value: unknown): ConversationDetail | undefined {
  const body = record(value)
  if (!body || !isConversationMetadata(body.conversation) || !Array.isArray(body.messages)) return
  const messages = body.messages.map(parseMessage)
  if (messages.some(message => !message)) return
  return { conversation: body.conversation, messages: messages as ConversationMessage[] }
}

export function receiptText(receipt: unknown): string | undefined {
  if (typeof receipt === 'string' && receipt.trim()) return receipt.trim()
  const value = record(receipt)
  for (const key of ['summary', 'message', 'title']) {
    if (typeof value?.[key] === 'string' && value[key].trim()) return value[key].trim()
  }
}

export function memoryActionState(action: MemoryAction) {
  if (['applied', 'completed', 'saved', 'succeeded'].includes(action.status)) return 'confirmed' as const
  if (['failed', 'rejected', 'cancelled'].includes(action.status)) return 'failed' as const
  return 'pending' as const
}
