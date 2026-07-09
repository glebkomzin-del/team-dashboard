import { createClient } from '@supabase/supabase-js'

// Konfigurierbar über .env (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY);
// die Fallbacks halten den Build ohne .env lauffähig (Anon-Key ist öffentlich).
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || 'https://lghwikeotbkmojyyjglz.supabase.co'
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM'

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

// ── Types matching DB schema ──
export interface DbTeamMember { id: string; name: string; member_type: string; email: string | null }
export interface DbMeeting { id: string; title: string; meeting_date: string; topics: string[] | null; participants: string[] | null; transcript_url: string | null; ai_summary: string | null; key_decisions: string[] | null; source_file: string | null; raw_transcript?: string | null; created_at: string }
export interface DbMeetingTopic { id: string; meeting_id: string; name: string; summary: string; sequence: number; created_at: string | null }
export interface DbTodo { id: string; assignee: string; assignee_id: string | null; meeting_id: string | null; meeting_source: string | null; project_id: string | null; title: string; description: string | null; status: string; priority: string; due_date: string | null; completed_at: string | null; created_at: string; updated_at: string }
export interface DbBlocker { id: string; reported_by: string; reported_by_id: string | null; meeting_id: string | null; meeting_source: string | null; project_id: string | null; title: string; description: string | null; status: string; resolved_at: string | null; resolution_note: string | null; created_at: string; updated_at: string }
export interface DbOpenItem { id: string; owner: string; owner_id: string | null; meeting_id: string | null; meeting_source: string | null; project_id: string | null; title: string; description: string | null; category: string; status: string; closed_at: string | null; created_at: string; updated_at: string }
export interface DbActivity { id: string; entity_type: string; entity_id: string; action: string; field_changed: string | null; old_value: string | null; new_value: string | null; changed_by: string | null; note: string | null; meeting_id: string | null; created_at: string }
export interface DbProject { id: string; name: string; description: string | null; status: string; start_date: string | null; end_date: string | null; owner: string | null; priority: string; created_at: string; updated_at: string }
export interface DbDecision { id: string; meeting_id: string | null; meeting_source: string | null; project_id: string | null; title: string; description: string | null; decided_by: string | null; status: string; created_at: string; updated_at: string }
export interface DbInboxItem { id: string; entity_type: 'todo' | 'blocker' | 'open_item' | 'meeting' | 'decision' | 'resolution'; payload: Record<string, any>; source: string; status: 'pending' | 'approved' | 'rejected'; created_at: string }
export interface DbMeetingLink { source: string; meeting_id: string | null; title: string; meeting_date: string | null; deleted_at: string | null }
export interface DbMemoryMetric { id: number; created_at: string; meeting_count: number; summary_block_tokens: number; cache_write_tokens: number; cache_read_tokens: number; retrieval_mode: string; output_tokens: number; uncached_input_tokens: number; model: string | null; cost_usd: number }
export interface TableCounts { meetings: number; todos: number; blockers: number; openItems: number; inbox: number }

// ── API Functions ──

export async function fetchProjects() {
  const { data, error } = await supabase.from('projects').select('*').order('name')
  if (error) throw error
  return data as DbProject[]
}

export async function fetchDecisions() {
  const { data, error } = await supabase.from('decisions').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return data as DbDecision[]
}

export async function insertProject(fields: { name: string; description?: string; start_date?: string; end_date?: string; owner?: string; priority?: string }) {
  const { data, error } = await supabase.from('projects').insert(fields).select().single()
  if (error) throw error
  return data as DbProject
}

export async function insertDecision(fields: { title: string; description?: string; meeting_id?: string; project_id?: string; decided_by?: string }) {
  const { data, error } = await supabase.from('decisions').insert(fields).select().single()
  if (error) throw error
  return data as DbDecision
}

export async function deleteDecisionDb(id: string) {
  const { error } = await supabase.from('decisions').delete().eq('id', id)
  if (error) throw error
}

export async function fetchTeamMembers() {
  const { data, error } = await supabase.from('team_members').select('*').order('created_at')
  if (error) throw error
  return data as DbTeamMember[]
}

export async function fetchMeetings() {
  const { data, error } = await supabase
    .from('meetings')
    .select('id,title,meeting_date,topics,participants,transcript_url,ai_summary,key_decisions,source_file,created_at')
    .order('meeting_date', { ascending: false })
  if (error) throw error
  return data as DbMeeting[]
}

export async function fetchMeetingLinks() {
  const { data, error } = await supabase.from('meeting_links').select('source,meeting_id,title,meeting_date,deleted_at')
  if (error) throw error
  return data as DbMeetingLink[]
}

export async function fetchMeetingRawTranscript(meetingId: string): Promise<string | null> {
  const { data, error } = await supabase
    .from('meetings')
    .select('raw_transcript')
    .eq('id', meetingId)
    .maybeSingle()
  if (error) throw error
  const transcript = data?.raw_transcript?.trim()
  return transcript || null
}

export async function fetchMeetingTopics(meetingId: string): Promise<DbMeetingTopic[]> {
  const { data, error } = await supabase
    .from('meeting_topics')
    .select('id,meeting_id,name,summary,sequence,created_at')
    .eq('meeting_id', meetingId)
    .order('sequence', { ascending: true })
  if (error) throw error
  return data as DbMeetingTopic[]
}

export async function fetchTableCounts(): Promise<TableCounts> {
  const [meetings, todos, blockers, openItems, inbox] = await Promise.all([
    supabase.from('meetings').select('id', { count: 'exact', head: true }),
    supabase.from('todos').select('id', { count: 'exact', head: true }),
    supabase.from('blockers').select('id', { count: 'exact', head: true }),
    supabase.from('open_items').select('id', { count: 'exact', head: true }),
    supabase.from('inbox_items').select('id', { count: 'exact', head: true }).eq('status', 'pending'),
  ])
  const failed = [meetings, todos, blockers, openItems, inbox].find(result => result.error)
  if (failed?.error) throw failed.error
  return {
    meetings: meetings.count ?? 0,
    todos: todos.count ?? 0,
    blockers: blockers.count ?? 0,
    openItems: openItems.count ?? 0,
    inbox: inbox.count ?? 0,
  }
}

export async function fetchTodos() {
  const { data, error } = await supabase.from('todos').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return data as DbTodo[]
}

export async function fetchMemoryMetrics() {
  const { data, error } = await supabase.from('memory_metrics').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return data as DbMemoryMetric[]
}

export async function fetchBlockers() {
  const { data, error } = await supabase.from('blockers').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return data as DbBlocker[]
}

export async function fetchOpenItems() {
  const { data, error } = await supabase.from('open_items').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return data as DbOpenItem[]
}

export async function fetchActivityLog() {
  const { data, error } = await supabase.from('activity_log').select('*').order('created_at', { ascending: false }).limit(200)
  if (error) throw error
  return data as DbActivity[]
}

export async function deleteActivityLogDb(id: string) {
  const { error } = await supabase.from('activity_log').delete().eq('id', id)
  if (error) throw error
}

// Upsert functions for "Ablegen"
export async function upsertTodo(todo: Partial<DbTodo>) {
  const { error } = await supabase.from('todos').upsert(todo)
  if (error) throw error
}

export async function updateTodoStatus(id: string, status: string) {
  const payload: any = { status }
  if (status === 'done') payload.completed_at = new Date().toISOString()
  const { error } = await supabase.from('todos').update(payload).eq('id', id)
  if (error) throw error
}

export async function deleteTodoDb(id: string) {
  const { error } = await supabase.from('todos').delete().eq('id', id)
  if (error) throw error
}

export async function updateBlockerStatus(id: string, status: string) {
  const payload: any = { status }
  if (status === 'resolved') payload.resolved_at = new Date().toISOString()
  const { error } = await supabase.from('blockers').update(payload).eq('id', id)
  if (error) throw error
}

export async function deleteBlockerDb(id: string) {
  const { error } = await supabase.from('blockers').delete().eq('id', id)
  if (error) throw error
}

export async function updateOpenItemStatus(id: string, status: string) {
  const payload: any = { status }
  if (status === 'closed') payload.closed_at = new Date().toISOString()
  const { error } = await supabase.from('open_items').update(payload).eq('id', id)
  if (error) throw error
}

export async function deleteOpenItemDb(id: string) {
  const { error } = await supabase.from('open_items').delete().eq('id', id)
  if (error) throw error
}

export async function deleteMeetingDb(id: string) {
  const { error } = await supabase.from('meetings').delete().eq('id', id)
  if (error) throw error
}

export async function updateTodoFull(id: string, fields: Partial<DbTodo>) {
  const { error } = await supabase.from('todos').update(fields).eq('id', id)
  if (error) throw error
}

export async function updateBlockerFull(id: string, fields: Partial<DbBlocker>) {
  const { error } = await supabase.from('blockers').update(fields).eq('id', id)
  if (error) throw error
}

export async function updateOpenItemFull(id: string, fields: Partial<DbOpenItem>) {
  const { error } = await supabase.from('open_items').update(fields).eq('id', id)
  if (error) throw error
}

export async function updateMeetingFull(id: string, fields: Partial<DbMeeting>) {
  const { error } = await supabase.from('meetings').update(fields).eq('id', id)
  if (error) throw error
}

export async function updateMeetingWithTopics(fields: {
  meetingId: string
  title: string
  meetingDate: string
  participants: string[]
  aiSummary: string
  keyDecisions: string[]
  topics: { name: string; summary: string; sequence: number }[]
}) {
  const { error } = await supabase.rpc('update_meeting_with_topics', {
    p_meeting_id: fields.meetingId,
    p_title: fields.title,
    p_meeting_date: fields.meetingDate,
    p_participants: fields.participants,
    p_ai_summary: fields.aiSummary,
    p_key_decisions: fields.keyDecisions,
    p_topics: fields.topics,
  })
  if (error) throw error
}

// Insert functions
export async function insertTodo(fields: { title: string; description?: string; assignee: string; priority: string; due_date?: string | null; created_at?: string; meeting_id?: string | null; meeting_source?: string | null }) {
  const { data, error } = await supabase.from('todos').insert(fields).select().single()
  if (error) throw error
  return data as DbTodo
}

export async function insertBlocker(fields: { title: string; description?: string; reported_by: string; created_at?: string; meeting_id?: string | null; meeting_source?: string | null }) {
  const { data, error } = await supabase.from('blockers').insert(fields).select().single()
  if (error) throw error
  return data as DbBlocker
}

export async function insertMeeting(fields: { title: string; meeting_date: string; topics?: string[]; participants?: string[]; ai_summary?: string; key_decisions?: string[] }) {
  const { data, error } = await supabase.from('meetings').insert(fields).select().single()
  if (error) throw error
  return data as DbMeeting
}

export async function insertOpenItem(fields: { title: string; description?: string; owner: string; category: string; created_at?: string; meeting_id?: string | null; meeting_source?: string | null }) {
  const { data, error } = await supabase.from('open_items').insert(fields).select().single()
  if (error) throw error
  return data as DbOpenItem
}

// ── Auth ──
export async function signIn(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password })
  if (error) throw error
  return data
}

export async function signOut() {
  const { error } = await supabase.auth.signOut()
  if (error) throw error
}

export async function resetPassword(email: string) {
  const { error } = await supabase.auth.resetPasswordForEmail(email)
  if (error) throw error
}

export async function getSession() {
  const { data } = await supabase.auth.getSession()
  return data.session
}

export function onAuthStateChange(callback: (session: any) => void) {
  return supabase.auth.onAuthStateChange((_event, session) => callback(session))
}

// Nightly job toggle
export async function isNightlyJobActive(): Promise<boolean> {
  const { data, error } = await supabase.rpc('is_nightly_job_active')
  if (error) { console.error('nightly check error', error); return true }
  return data as boolean
}

export async function toggleNightlyJob(enable: boolean): Promise<string> {
  const { data, error } = await supabase.rpc('toggle_nightly_job', { enable })
  if (error) throw error
  return data as string
}

// Log to activity_log
export async function logActivity(entityType: string, entityId: string, action: string, newValue?: string) {
  const { error } = await supabase.from('activity_log').insert({ entity_type: entityType, entity_id: entityId, action, new_value: newValue || null })
  if (error) console.error('activity log error', error)
}

// ── Projects CRUD ──
export async function updateProjectFull(id: string, fields: Partial<DbProject>) {
  const { data, error } = await supabase.from('projects').update(fields).eq('id', id).select('id').maybeSingle()
  if (error) throw error
  if (!data) throw new Error('Projekt konnte nicht gespeichert werden: kein Datensatz wurde geändert.')
}

export async function deleteProjectDb(id: string) {
  const { data, error } = await supabase.from('projects').delete().eq('id', id).select('id').maybeSingle()
  if (error) throw error
  if (!data) throw new Error('Projekt konnte nicht gelöscht werden: kein Datensatz wurde entfernt.')
}

// ── Project–Meeting links ──
export async function fetchProjectMeetings(projectId: string): Promise<string[]> {
  const { data, error } = await supabase.from('project_meetings').select('meeting_id').eq('project_id', projectId)
  if (error) throw error
  return (data || []).map((r: any) => r.meeting_id)
}

export async function setProjectMeetings(projectId: string, meetingIds: string[]): Promise<void> {
  const { error: deleteError } = await supabase.from('project_meetings').delete().eq('project_id', projectId)
  if (deleteError) throw deleteError
  if (meetingIds.length > 0) {
    const rows = meetingIds.map(mid => ({ project_id: projectId, meeting_id: mid }))
    const { error } = await supabase.from('project_meetings').insert(rows)
    if (error) throw error
  }
}

// ── Inbox ──
export async function fetchInboxItems() {
  const { data, error } = await supabase.from('inbox_items').select('*').eq('status', 'pending').order('created_at', { ascending: false })
  if (error) throw error
  return data as DbInboxItem[]
}

export async function updateInboxItemPayload(id: string, payload: Record<string, any>) {
  const { data, error } = await supabase.from('inbox_items').update({ payload }).eq('id', id).select('payload').single()
  if (error) throw error
  return data.payload as Record<string, any>
}

export async function deleteInboxItemDb(id: string) {
  const { error } = await supabase.from('inbox_items').delete().eq('id', id)
  if (error) throw error
}

export async function approveInboxItem(id: string, status: 'approved' | 'rejected') {
  const { error } = await supabase.from('inbox_items').update({ status }).eq('id', id)
  if (error) throw error
}

// ── Decisions CRUD ──
export async function updateDecisionFull(id: string, fields: Partial<DbDecision>) {
  const { error } = await supabase.from('decisions').update(fields).eq('id', id)
  if (error) throw error
}

// ── Ask Memory (KI-Assistent) ──
export interface AskMemoryMeetingSource {
  id: string
  date: string
  title: string
  participants: string[]
}

export interface AskMemoryChunkSource {
  id: string
  meeting_id: string
  speaker: string | null
  meeting_date: string
  excerpt: string
  fused_score: number
}

export interface AskMemoryItemSource {
  entity_type: string
  id: string
  title: string
  description: string | null
  status: string | null
  meeting_id: string | null
  meeting_date: string | null
  created_at: string | null
  closed_ts: string | null
}

export interface AskMemoryResult {
  answer: string
  sources: {
    meetings: AskMemoryMeetingSource[]
    chunks: AskMemoryChunkSource[]
    items?: AskMemoryItemSource[]
  }
  retrieval: {
    mode: string
    [key: string]: unknown
  }
  model: string
  usage: Record<string, unknown>
  cache: Record<string, unknown>
  cost_usd?: number
  scaling_notice?: string
}

export interface AskMemoryStreamMetadata {
  retrieval: {
    mode: string
    [key: string]: unknown
  }
  model: string
  usage: Record<string, unknown>
  cache: Record<string, unknown>
  scaling_notice?: string
}

export interface AskMemoryStreamHandlers {
  onMetadata?: (metadata: AskMemoryStreamMetadata) => void
  onDelta?: (text: string) => void
  onSources?: (sources: AskMemoryResult['sources']) => void
  onDone?: (done: { usage?: Record<string, unknown>; cache?: Record<string, unknown>; cost_usd?: number }) => void
}

async function requireAccessToken(): Promise<string> {
  const session = await getSession()
  if (!session?.access_token) throw new Error('Authentication required')
  return session.access_token
}

export async function askMemory(question: string, history: { role: string; text: string }[] = []): Promise<AskMemoryResult> {
  const accessToken = await requireAccessToken()
  const res = await fetch(`${SUPABASE_URL}/functions/v1/ask-memory`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ question, history }),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Ask Memory error: ${err}`)
  }
  const data = await res.json() as AskMemoryResult
  if (typeof data.answer !== 'string' || !Array.isArray(data.sources?.meetings) || typeof data.retrieval?.mode !== 'string') {
    throw new Error('Ask Memory returned an unexpected response shape')
  }
  return data
}

export async function askMemoryStream(question: string, history: { role: string; text: string }[] = [], handlers: AskMemoryStreamHandlers = {}): Promise<void> {
  const accessToken = await requireAccessToken()
  const res = await fetch(`${SUPABASE_URL}/functions/v1/ask-memory`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ question, history, stream: true }),
  })
  if (!res.ok || !res.body) {
    const err = await res.text().catch(() => '')
    throw new Error(`Ask Memory stream error: ${err || res.statusText}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const handleEvent = (raw: string) => {
    const event = raw.split(/\r?\n/).find(line => line.startsWith('event:'))?.slice('event:'.length).trim()
    const dataText = raw.split(/\r?\n/)
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice('data:'.length).trimStart())
      .join('\n')
    if (!event || !dataText) return
    const data = JSON.parse(dataText)
    if (event === 'metadata') handlers.onMetadata?.(data as AskMemoryStreamMetadata)
    else if (event === 'delta') handlers.onDelta?.(typeof data.text === 'string' ? data.text : '')
    else if (event === 'sources') handlers.onSources?.(data as AskMemoryResult['sources'])
    else if (event === 'done') handlers.onDone?.(data)
    else if (event === 'error') throw new Error(typeof data.error === 'string' ? data.error : 'Ask Memory stream failed')
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split(/\r?\n\r?\n/)
    buffer = events.pop() || ''
    for (const raw of events) {
      if (raw.trim()) handleEvent(raw)
    }
  }
  buffer += decoder.decode()
  if (buffer.trim()) handleEvent(buffer)
}
