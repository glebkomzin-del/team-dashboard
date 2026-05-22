import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = 'https://lghwikeotbkmojyyjglz.supabase.co'
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM'

// TODO: Ersetze mit deiner Make Webhook URL
export const MAKE_WEBHOOK_URL = 'https://hook.eu1.make.com/9lxc5o11p61np3aergy88jsxkrshk7cx'

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

// ── Types matching DB schema ──
export interface DbTeamMember { id: string; name: string; member_type: string; email: string | null }
export interface DbMeeting { id: string; title: string; meeting_date: string; topics: string[] | null; participants: string[] | null; transcript_url: string | null; ai_summary: string | null; key_decisions: string[] | null; source_file: string | null; created_at: string }
export interface DbTodo { id: string; assignee: string; assignee_id: string | null; meeting_id: string | null; project_id: string | null; title: string; description: string | null; status: string; priority: string; due_date: string | null; completed_at: string | null; created_at: string; updated_at: string }
export interface DbBlocker { id: string; reported_by: string; reported_by_id: string | null; meeting_id: string | null; project_id: string | null; title: string; description: string | null; status: string; resolved_at: string | null; resolution_note: string | null; created_at: string; updated_at: string }
export interface DbOpenItem { id: string; owner: string; owner_id: string | null; meeting_id: string | null; project_id: string | null; title: string; description: string | null; category: string; status: string; closed_at: string | null; created_at: string; updated_at: string }
export interface DbActivity { id: string; entity_type: string; entity_id: string; action: string; field_changed: string | null; old_value: string | null; new_value: string | null; changed_by: string | null; note: string | null; meeting_id: string | null; created_at: string }
export interface DbProject { id: string; name: string; description: string | null; status: string; start_date: string | null; end_date: string | null; owner: string | null; priority: string; created_at: string; updated_at: string }
export interface DbDecision { id: string; meeting_id: string | null; project_id: string | null; title: string; description: string | null; decided_by: string | null; status: string; created_at: string; updated_at: string }
export interface DbInboxItem { id: string; entity_type: 'todo' | 'blocker' | 'open_item' | 'meeting' | 'decision'; payload: Record<string, any>; source: string; status: 'pending' | 'approved' | 'rejected'; created_at: string }

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
  const { data, error } = await supabase.from('meetings').select('*').order('meeting_date', { ascending: false })
  if (error) throw error
  return data as DbMeeting[]
}

export async function fetchTodos() {
  const { data, error } = await supabase.from('todos').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return data as DbTodo[]
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

// Insert functions
export async function insertTodo(fields: { title: string; description?: string; assignee: string; priority: string; due_date?: string | null; created_at?: string }) {
  const { data, error } = await supabase.from('todos').insert(fields).select().single()
  if (error) throw error
  return data as DbTodo
}

export async function insertBlocker(fields: { title: string; description?: string; reported_by: string; created_at?: string }) {
  const { data, error } = await supabase.from('blockers').insert(fields).select().single()
  if (error) throw error
  return data as DbBlocker
}

export async function insertMeeting(fields: { title: string; meeting_date: string; topics?: string[]; participants?: string[]; ai_summary?: string; key_decisions?: string[] }) {
  const { data, error } = await supabase.from('meetings').insert(fields).select().single()
  if (error) throw error
  return data as DbMeeting
}

export async function insertOpenItem(fields: { title: string; description?: string; owner: string; category: string; created_at?: string }) {
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

export async function signUp(email: string, password: string) {
  const { data, error } = await supabase.auth.signUp({ email, password })
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

// Trigger Make webhook
export async function triggerMakeWebhook() {
  if (!MAKE_WEBHOOK_URL) {
    throw new Error('Make Webhook URL ist noch nicht konfiguriert. Trage sie in src/supabase.ts ein.')
  }
  await fetch(MAKE_WEBHOOK_URL, { method: 'POST', mode: 'no-cors' })
}

// ── Projects CRUD ──
export async function updateProjectFull(id: string, fields: Partial<DbProject>) {
  const { error } = await supabase.from('projects').update(fields).eq('id', id)
  if (error) throw error
}

export async function deleteProjectDb(id: string) {
  const { error } = await supabase.from('projects').delete().eq('id', id)
  if (error) throw error
}

// ── Project–Meeting links ──
export async function fetchProjectMeetings(projectId: string): Promise<string[]> {
  const { data, error } = await supabase.from('project_meetings').select('meeting_id').eq('project_id', projectId)
  if (error) throw error
  return (data || []).map((r: any) => r.meeting_id)
}

export async function setProjectMeetings(projectId: string, meetingIds: string[]): Promise<void> {
  // Replace all links for this project atomically
  await supabase.from('project_meetings').delete().eq('project_id', projectId)
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
  const { error } = await supabase.from('inbox_items').update({ payload }).eq('id', id)
  if (error) throw error
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

// ── Semantic Search ──
export interface SearchMatch {
  entity_type: string
  entity_id: string
  content: string
  similarity: number
}

export interface SearchResult {
  answer: string
  matches: SearchMatch[]
}

export async function semanticSearch(query: string, history: { role: string; text: string }[] = []): Promise<SearchResult> {
  console.log('[KI] Sending query:', query, '| History:', history.length)
  const res = await fetch(`${SUPABASE_URL}/functions/v1/semantic-search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
    },
    body: JSON.stringify({ query, match_threshold: 0.25, match_count: 10, history }),
  })
  console.log('[KI] Response status:', res.status)
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Search error: ${err}`)
  }
  const data = await res.json() as SearchResult
  console.log('[KI] Result:', data.answer?.slice(0, 100), '| Matches:', data.matches?.length)
  return data
}

export async function semanticSearchStream(
  query: string,
  history: { role: string; text: string }[] = [],
  onMatches: (matches: SearchMatch[]) => void,
  onDelta: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
): Promise<void> {
  console.log('[KI-Stream] Sending query:', query)
  const res = await fetch(`${SUPABASE_URL}/functions/v1/semantic-search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
    },
    body: JSON.stringify({ query, match_threshold: 0.25, match_count: 10, history, stream: true }),
  })
  if (!res.ok) {
    const err = await res.text()
    onError(`Search error: ${err}`)
    return
  }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (!data) continue
      try {
        const evt = JSON.parse(data)
        if (evt.type === 'matches') onMatches(evt.matches || [])
        else if (evt.type === 'delta') onDelta(evt.text)
        else if (evt.type === 'done') onDone()
        else if (evt.type === 'error') onError(evt.error)
      } catch { /* skip */ }
    }
  }
  onDone()
}

export async function triggerBackfillEmbeddings(): Promise<{ embedded: number; errors: number }> {
  const session = await getSession()
  const res = await fetch(`${SUPABASE_URL}/functions/v1/backfill-embeddings`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${session?.access_token || SUPABASE_ANON_KEY}`,
    },
    body: JSON.stringify({}),
  })
  if (!res.ok) throw new Error(`Backfill error: ${await res.text()}`)
  return await res.json()
}
