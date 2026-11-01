import assert from 'node:assert/strict'
import { test } from 'node:test'
import { citationIsNavigable, isCitation, isCoverage, memoryActionState, parseConversationDetail, parseConversationList, parseCreatedConversation, receiptText } from '../src/features/working-memory/notes-chat-context.ts'

const metadata = {
  id: 'conversation-1',
  conversation_id: 'conversation-1',
  title: 'Zeitplan',
  created_at: '2026-09-20T08:00:00Z',
  updated_at: '2026-09-20T08:05:00Z',
}
const conversation = {
  conversation_id: metadata.conversation_id,
  title: metadata.title,
  created_at: metadata.created_at,
  updated_at: metadata.updated_at,
  message_count: 2,
  last_message_preview: 'Der Termin steht fest.',
}

const coverageBase = {
  as_of: '2026-09-20', latest_available_as_of: '2026-09-20', is_latest: true,
  working_sources: 4, archived_sources: 5, archived_only_sources: 1, pending_jobs: 0, task_total: 12,
  context_messages: 2, context_omitted: 0, output_truncated: false,
}
const retrievalCoverage = { ...coverageBase, mode: 'retrieval', matched_tasks: null,
  retrieval: { documents_considered: 8, max_hits_per_round: 10, search_rounds: 2, scope: 'global', time_range: { from: '2026-09-01', to: '2026-09-20' }, hits_returned: 2,
    overview: { key: 'overview-key', source_snapshot_id: 'snapshot-1', incremental_content_hash_cache: true },
    evidence_rows: 3, limited: false, task_candidates_omitted: 0, evidence_bytes_truncated: false } }
// The SQL-backed detail payload strips nulls from the stored response, so
// non-retrieval coverage has no `retrieval` key after a persistent reload.
const structuredCoverage = { ...coverageBase, mode: 'structured_tasks', matched_tasks: 2 }
const plannedCoverage = { ...coverageBase, mode: 'planned_tasks', matched_tasks: 1 }
const memoryWriteCoverage = { ...coverageBase, mode: 'memory_write', matched_tasks: 1 }
const userMemoryCitation = {
  id: 'E001', kind: 'user_memory', label: 'Nutzernotiz: Lieferantenpräferenz',
  quote: 'Bei neuen Bestellungen bevorzugen wir Anbieter A.', event_date: '2026-09-20',
  target: { page: 'wissen', params: { memory: 'memory-1', as_of: '2026-09-20' } },
}

test('conversation create accepts the SQL metadata receipt without list-only fields', () => {
  assert.deepEqual(parseCreatedConversation({ conversation: metadata, repeated: false }, metadata.conversation_id), metadata)
  assert.equal(parseCreatedConversation({ conversation: metadata, repeated: false }, 'another-conversation'), undefined)
  assert.equal(parseCreatedConversation({ conversation: { conversation_id: metadata.conversation_id, title: metadata.title } }, metadata.conversation_id), undefined)
})

test('conversation list accepts the SQL summary contract and rejects partial rows', () => {
  assert.deepEqual(parseConversationList({ conversations: [conversation] }), [conversation])
  assert.equal(parseConversationList({ conversations: [metadata] }), undefined)
  assert.equal(parseConversationList({ conversations: [{ conversation_id: 'missing-fields' }] }), undefined)
})

test('conversation detail accepts the redacted production SQL shape after persistent reload', () => {
  const detail = parseConversationDetail({ conversation: metadata, messages: [
    { message_id: 'message-1', role: 'user', content: 'Was gilt?', created_at: '2026-09-20T08:01:00Z' },
    { message_id: 'message-2', role: 'assistant', content: 'Der Termin steht fest.', created_at: '2026-09-20T08:05:00Z', coverage: retrievalCoverage, citations: [], memory_actions: [{ action_id: 'action-1', kind: 'update_task', status: 'applied', receipt: { summary: 'Termin ergänzt.' } }] },
  ] })
  assert.equal(detail?.messages.length, 2)
  assert.deepEqual(detail?.messages[0].citations, [])
  assert.equal(detail?.messages[1].coverage?.mode, 'retrieval')
  assert.equal(detail?.messages[1].memory_actions[0].status, 'applied')
})

test('coverage accepts every backend route with its real mode-specific fixture', () => {
  for (const coverage of [structuredCoverage, plannedCoverage, memoryWriteCoverage, retrievalCoverage]) assert.equal(isCoverage(coverage), true, coverage.mode)
  assert.equal(isCoverage({ ...plannedCoverage, matched_tasks: null }), false)
  assert.equal(isCoverage({ ...retrievalCoverage, retrieval: { ...retrievalCoverage.retrieval, search_rounds: undefined } }), false)
})

test('persisted coverage restores recursively stripped nulls without accepting missing required fields', () => {
  const parse = coverage => parseConversationDetail({ conversation: metadata, messages: [{
    message_id: 'persisted', role: 'assistant', content: 'Antwort', created_at: metadata.created_at,
    coverage: JSON.parse(JSON.stringify(coverage, (_key, value) => value === null ? undefined : value)),
  }] })
  for (const coverage of [structuredCoverage, plannedCoverage, { ...memoryWriteCoverage, matched_tasks: null },
    { ...retrievalCoverage, retrieval: { ...retrievalCoverage.retrieval, time_range: { from: null, to: null } } }]) {
    assert.equal(parse(coverage)?.messages[0].coverage?.mode, coverage.mode)
  }
  assert.equal(parse({ ...plannedCoverage, matched_tasks: undefined }), undefined)
  assert.equal(parse({ ...retrievalCoverage, retrieval: { ...retrievalCoverage.retrieval, search_rounds: undefined } }), undefined)
})

test('explicit user memory is valid evidence but never an original-source link', () => {
  assert.equal(isCitation(userMemoryCitation), true)
  assert.equal(citationIsNavigable(userMemoryCitation), false)
  assert.equal(citationIsNavigable({ ...userMemoryCitation, kind: 'knowledge' }), true)
})

test('conversation detail rejects invalid evidence instead of silently presenting it', () => {
  assert.equal(parseConversationDetail({ conversation, messages: [{ message_id: 'message-1', role: 'assistant', content: 'Antwort', created_at: '2026-09-20T08:05:00Z', citations: [{ id: 'broken' }] }] }), undefined)
})

test('memory action receipts have clear user-facing states', () => {
  assert.equal(memoryActionState({ action_id: '1', kind: 'update_task', status: 'applied' }), 'confirmed')
  assert.equal(memoryActionState({ action_id: '2', kind: 'journal', status: 'failed' }), 'failed')
  assert.equal(memoryActionState({ action_id: '3', kind: 'update_task', status: 'needs_clarification' }), 'pending')
  assert.equal(receiptText({ summary: 'Entscheidung ergänzt.' }), 'Entscheidung ergänzt.')
  assert.equal(receiptText({ internal_id: 'hidden' }), undefined)
})
