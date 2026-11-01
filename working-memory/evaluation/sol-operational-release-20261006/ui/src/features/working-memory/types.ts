import { getSession } from '@/auth'
export type Kind = 'commitment' | 'dependency' | 'fact' | 'decision' | 'question' | 'risk' | 'idea' | 'status'
export type Action = 'proposed' | 'created' | 'progress' | 'done' | 'reopened' | 'owner_changed' | 'date_changed' | 'condition_met'
export type DecisionAction = 'approve' | 'reject' | 'correct' | 'set_status' | 'confirm_knowledge' | 'correct_confirm'
export type WorkStatus = 'open' | 'waiting' | 'done' | 'cancelled' | 'dismissed'
export interface HumanDecision { action: DecisionAction; reason: string; event_date: string; command_id: string }
export interface Correction { id: string; reason: string; authority: string; previous_claim: string }
export interface Observation {
  assignment_score?: 0 | 1 | 2; change_score?: 0 | 1 | 2; confidence_reason?: string
  subject?: string; search_keywords?: string[]
  title: string; claim: string; kind: Kind; matter: string; owner: string | null
  quotes: string[]; due_text: string | null; condition_text?: string | null
  work_state?: string
  knowledge_status?: 'active' | 'rejected'
  original_time_expression?: string | null; time_expression_role?: 'event_time' | 'data_reference' | 'unclear'
  uncertainty?: string | null; action_uncertainty?: string | null; required_review: boolean
  human_corrections?: Correction[]; work_gate?: { verdict: string; reason: string }
  original_interpretation?: { title: string; claim: string; owner: string | null; due_text: string | null }
  correction_history?: HumanDecision[]
  human_decision?: HumanDecision; update_target?: string | null; update?: string
}
export interface HistoryEntry {
  event_date: string; action: Action | DecisionAction; source_version?: string; source_title?: string; human?: boolean
  patch?: Record<string, unknown>; content_hash: string; claim: string; quotes: string[]; owner: string | null; due_text: string | null
}
export interface Work extends Observation {
  id: string; status: WorkStatus; last_changed: string; due_date?: string | null
  due_reference_date: string | null; history: HistoryEntry[]
}
export interface Knowledge {
  id: string; matter_id: string; matter_title: string; source_version: string; event_date: string
  kind: Kind; data: Observation
}
export interface Source { id: string; title: string; event_date: string; content_hash: string }
export interface Snapshot {
  mode: 'isolated-preview' | 'staging' | 'production'; archive_total?: number; archive_available?: boolean; as_of: string; dates: string[]; sources: Source[]
  personal: Work[]; waiting_dependencies: Work[]; waiting: Work[]; completed: Work[]
  cancelled?: Work[]; revision?: number; can_edit?: boolean; storage?: string
  knowledge: Knowledge[]
  changes: { id: string; work_id: string | null; event_date: string; action: Action | DecisionAction; matter_id: string; matter_title: string; data: Observation }[]
  jobs: { id: string; status: string; attempts: number; error: string | null; title: string; event_date: string }[]
}
export const kindNames: Record<Kind, string> = { commitment: 'Zusage', dependency: 'Voraussetzung', fact: 'Information', decision: 'Entscheidung', question: 'Offene Frage', risk: 'Risiko', idea: 'Möglichkeit', status: 'Status' }
export const actionNames: Record<Action, string> = { proposed: 'Vorschlag aus dem Original', created: 'Neue Zusage', progress: 'Fortschritt', done: 'Erledigt', reopened: 'Wieder aufgenommen', owner_changed: 'Zuständigkeit geändert', date_changed: 'Frist geändert', condition_met: 'Voraussetzung eingetreten' }
export const decisionNames: Record<DecisionAction, string> = { correct_confirm: 'Von dir korrigiert und bestätigt', confirm_knowledge: 'Aussage von dir bestätigt', approve: 'Von dir bestätigt', reject: 'Von dir verworfen', correct: 'Von dir korrigiert', set_status: 'Status von dir geändert' }
export interface DecisionRequest {
  feedback_kind?: 'interpretation' | 'real_world_change'
  command_id: string; expected_revision: number; action: DecisionAction; target_id: string; reason: string
  patch: { title?: string; claim?: string; owner?: string; due_date?: string | null; status?: Exclude<WorkStatus, 'dismissed'> }
}
export class MemoryWriteError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status } }
export async function saveDecision(request: DecisionRequest): Promise<{ revision: number; repeated: boolean }> {
  return postMemory('/decisions', request)
}
export async function postMemory<T>(path: string, request: unknown): Promise<T> {
  const session = await getSession()
  const response = await fetch(`/api/working-memory${path}`, { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}) }, body: JSON.stringify(request) })
  if (!response.ok) {
    const message = response.status === 409 ? 'Der Stand wurde inzwischen geändert. Lade ihn neu und prüfe deine Entscheidung noch einmal.'
      : response.status === 401 || response.status === 403 ? 'Deine Anmeldung erlaubt diese Änderung gerade nicht. Bitte melde dich erneut an.'
      : response.status === 400 ? 'Die Entscheidung ist für diesen Eintrag nicht zulässig. Prüfe die angezeigten Angaben.'
      : 'Die Speicherung konnte nicht bestätigt werden. Erneut versuchen sendet dieselbe Entscheidung.'
    throw new MemoryWriteError(message, response.status)
  }
  if (!response.headers.get('content-type')?.includes('application/json')) throw new MemoryWriteError('Die Speicherbestätigung ist unklar. Bitte den Stand neu laden.', 503)
  return response.json()
}
export function dateLabel(value: string) {
  return new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T12:00:00Z`))
}
export class MemoryReadError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}
export async function getMemory<T>(path: string, signal: AbortSignal): Promise<T> {
  const session = await getSession()
  const headers: HeadersInit = session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}
  let response: Response
  try { response = await fetch(`/api/working-memory${path}`, { signal, headers, cache: 'no-store', credentials: 'same-origin' }) }
  catch (error) { if (signal.aborted) throw error; throw new Error('Die Verbindung zum Datenzugang ist unterbrochen. Bitte erneut versuchen oder die Vorschau neu öffnen.') }
  if (!response.ok) throw new MemoryReadError(response.status === 401 || response.status === 403 ? 'Deine Anmeldung ist abgelaufen oder für diesen Bestand nicht freigegeben. Bitte melde dich erneut an.' : 'Die Daten sind gerade nicht erreichbar. Bitte erneut versuchen.', response.status)
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Der Datenzugang ist für diese Umgebung noch nicht eingerichtet.')
  return response.json() as Promise<T>
}

const numberFormat = new Intl.NumberFormat('de-DE')
export const numberLabel = (value: number) => numberFormat.format(value)
