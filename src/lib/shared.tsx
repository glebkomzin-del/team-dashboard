// Gemeinsame Typen, Konstanten, Helfer und Kleinst-Komponenten des Dashboards.
// Aus App.tsx extrahiert (2026-07-08); Seiten liegen unter src/pages/.
import { useState, useCallback, useEffect, useRef } from 'react'
import type { ComponentProps } from 'react'
import DOMPurify from 'dompurify'
import { CardContent } from '@/components/ui/card'
import { Calendar } from '@/components/ui/calendar'
import { TableHead } from '@/components/ui/table'
import { de } from 'date-fns/locale'
import {
  type DbInboxItem,
  type AskMemoryMeetingSource, type AskMemoryChunkSource, type AskMemoryItemSource,
} from '../supabase'

export type Page = 'uebersicht' | 'sitzungen' | 'aktionen' | 'projekte' | 'ki' | 'textsuche' | 'protokoll' | 'inbox'
export type SortDir = 'asc' | 'desc' | null
export type ProjectView = 'table' | 'kanban' | 'gantt'
export type ActionTab = 'todos' | 'blocker' | 'open'

export const PRI_LABEL: Record<string, string> = { urgent: 'Dringend', high: 'Hoch', medium: 'Mittel', low: 'Niedrig' }
export const mutationErrorMessage = (error: unknown, fallback: string) => {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'object' && error !== null && 'message' in error && typeof error.message === 'string') return error.message
  return fallback
}
export const PRI_RANK: Record<string, number> = { urgent: 0, high: 1, medium: 2, low: 3 }
export const PRI_STYLE: Record<string, string> = {
  urgent: 'bg-[var(--syn-danger)] text-white',
  high: 'bg-[var(--syn-danger-soft)] text-[var(--syn-danger)] border border-[var(--syn-danger)]/20',
  medium: 'bg-[var(--syn-neutral-chip)] text-[var(--syn-text-muted)]',
  low: 'bg-[var(--syn-surface-2)] text-[var(--syn-text-faint)]'
}
export const ST_STYLE: Record<string, string> = {
  open: 'bg-[var(--syn-neutral-chip)] text-[var(--syn-text-muted)]',
  in_progress: 'bg-[var(--syn-info-soft)] text-[var(--syn-info)]',
  done: 'bg-[var(--syn-ok-soft)] text-[var(--syn-ok)]',
  cancelled: 'bg-[var(--syn-surface-2)] text-[var(--syn-text-faint)]',
  active: 'bg-[var(--syn-danger-soft)] text-[var(--syn-danger)]',
  resolved: 'bg-[var(--syn-ok-soft)] text-[var(--syn-ok)]',
  escalated: 'bg-[var(--syn-danger)] text-white',
  watching: 'bg-[var(--syn-warn-soft)] text-[var(--syn-warn)]',
  closed: 'bg-[var(--syn-surface-2)] text-[var(--syn-text-faint)]',
  approved: 'bg-[var(--syn-ok-soft)] text-[var(--syn-ok)]',
  pending: 'bg-[var(--syn-warn-soft)] text-[var(--syn-warn)]',
  paused: 'bg-[var(--syn-warn-soft)] text-[var(--syn-warn)]',
  rejected: 'bg-[var(--syn-danger-soft)] text-[var(--syn-danger)]',
  completed: 'bg-[var(--syn-ok-soft)] text-[var(--syn-ok)]',
  on_hold: 'bg-[var(--syn-warn-soft)] text-[var(--syn-warn)]',
}
export const ST_LABEL: Record<string, string> = { open: 'Offen', in_progress: 'In Arbeit', done: 'Erledigt', cancelled: 'Abgebr.', active: 'Aktiv', resolved: 'Gelöst', escalated: 'Eskaliert', watching: 'Beobachten', closed: 'Geschlossen', approved: 'Genehmigt', pending: 'Ausstehend', rejected: 'Abgelehnt', completed: 'Abgeschlossen', paused: 'Pausiert', on_hold: 'Pausiert' }
export const ACTION_LABEL: Record<string, string> = { status_changed: 'Status geändert', created: 'Erstellt', updated: 'Bearbeitet', deleted: 'Gelöscht', reassigned: 'Zugewiesen' }
export const TYPE_LABEL: Record<string, string> = { todo: 'Todo', blocker: 'Blocker', open_item: 'Offener Punkt', meeting: 'Meeting', decision: 'Entscheidung', project: 'Projekt', activity: 'Änderung' }
export const CAT_LABEL: Record<string, string> = { decision: 'Entscheidung', question: 'Frage', risk: 'Risiko', info: 'Information', general: 'Allgemein', opportunity: 'Chance', follow_up: 'Nachverfolgung' }
export const CAT_ICON: Record<string, string> = { decision: '◉', question: '?', risk: '▲', info: 'ⓘ', general: '○', opportunity: '◆', follow_up: '↩' }
export const MEMBER_ORDER = ['Gleb', 'Niko', 'Mathias', 'Jan Philipp', 'Extern', 'Nicht zugeordnet']
export const FINAL_STATUSES = new Set(['done', 'resolved', 'closed', 'approved', 'completed'])
export const FILTER_INPUT_CLASS = 'h-8 w-[160px] text-xs bg-[var(--syn-surface-2)] border-[var(--syn-line)]'
export const FILTER_TRIGGER_CLASS = 'h-8 w-[160px] text-xs'
export const FILTER_BAR_CLASS = 'flex items-center gap-2 flex-wrap'

export const parseLocalDate = (value: string) => value ? new Date(`${value}T00:00:00`) : undefined
export const toLocalDateValue = (date?: Date) => date
  ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  : ''
export const formatShortDate = (date: Date) => date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })

// ── KI-Kosten-Fallback: greift nur, wenn das Backend (noch) kein cost_usd
// liefert. cacheWrite = 2x Input wegen 1h-Cache-TTL im Backend. ────────────
export const CHAT_PRICING: Record<string, { input: number; output: number; cacheWrite: number; cacheRead: number }> = {
  'claude-sonnet-4-6': { input: 3.0, output: 15.0, cacheWrite: 6.0, cacheRead: 0.3 },
  'claude-sonnet-4-20250514': { input: 3.0, output: 15.0, cacheWrite: 6.0, cacheRead: 0.3 },
}
export const CHAT_DEFAULT_PRICING = CHAT_PRICING['claude-sonnet-4-6']
export const computeChatCost = (model: string | undefined, inputTokens: number, outputTokens: number, cacheWrite: number, cacheRead: number): number => {
  const p = (model && CHAT_PRICING[model]) || CHAT_DEFAULT_PRICING
  const M = 1_000_000
  return (inputTokens / M) * p.input
    + (outputTokens / M) * p.output
    + (cacheWrite / M) * p.cacheWrite
    + (cacheRead / M) * p.cacheRead
}
export const formatCost = (usd: number) => usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`
export const formatTokens = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}k` : String(n)

// ── Datums-Presets für den Meeting-Filter ──────────────────────────────────
export type DatePresetKey = '7d' | '30d' | 'thisMonth' | 'lastMonth'
export const MEETING_DATE_PRESETS: { key: DatePresetKey; label: string }[] = [
  { key: '7d', label: 'Letzte 7 Tage' },
  { key: '30d', label: 'Letzte 30 Tage' },
  { key: 'thisMonth', label: 'Dieser Monat' },
  { key: 'lastMonth', label: 'Letzter Monat' },
]
// Berechnet den {from, to}-Zeitraum für ein relatives Preset (heute-basiert).
export const presetToRange = (key: DatePresetKey): { from: Date; to: Date } => {
  const today = new Date()
  switch (key) {
    case '7d':       return { from: new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6),  to: today }
    case '30d':      return { from: new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29), to: today }
    case 'thisMonth':return { from: new Date(today.getFullYear(), today.getMonth(), 1),                     to: new Date(today.getFullYear(), today.getMonth() + 1, 0) }
    case 'lastMonth':return { from: new Date(today.getFullYear(), today.getMonth() - 1, 1),                 to: new Date(today.getFullYear(), today.getMonth(), 0) }
  }
}
// Erkennt, ob ein {from,to}-Zeitraum exakt einem Preset entspricht.
export const rangeToPresetKey = (from?: string, to?: string): DatePresetKey | undefined => {
  if (!from || !to) return undefined
  for (const p of MEETING_DATE_PRESETS) {
    const r = presetToRange(p.key)
    if (toLocalDateValue(r.from) === from && toLocalDateValue(r.to) === to) return p.key
  }
  return undefined
}

export function CompactRangeCalendar({ className = '', classNames, components, ...props }: ComponentProps<typeof Calendar>) {
  return (
    <Calendar
      numberOfMonths={2}
      locale={de}
      className={`[--cell-size:1.5rem] p-2 text-[0.65rem] ${className}`.trim()}
      classNames={{
        months: 'relative flex flex-col gap-3 md:flex-row',
        month: 'flex w-full flex-col gap-1.5',
        week: 'mt-0.5 flex w-full',
        weekday: 'flex-1 select-none rounded-md text-[0.6rem] font-normal text-muted-foreground',
        caption_label: 'select-none text-[0.65rem] font-medium',
        ...classNames,
      }}
      components={{
        DayButton: ({ day, modifiers, ...buttonProps }: any) => (
          <button
            {...buttonProps}
            ref={undefined}
            data-day={day.date.toLocaleDateString()}
            className="flex items-center justify-center font-normal leading-none transition-colors rounded-md hover:bg-[var(--syn-hover)]"
            style={{
              width: '1.5rem',
              height: '1.5rem',
              fontSize: '0.65rem',
              ...(modifiers.selected && !modifiers.range_start && !modifiers.range_end ? { background: 'var(--syn-accent)', color: 'white' } : {}),
              ...((modifiers.range_start || modifiers.range_end) ? { background: 'var(--syn-accent)', color: 'white' } : {}),
              ...(modifiers.range_middle ? { background: 'var(--syn-accent-soft)', color: 'var(--syn-text)', borderRadius: 0 } : {}),
              ...(modifiers.selected && modifiers.range_start ? { borderRadius: '0.25rem 0 0 0.25rem' } : {}),
              ...(modifiers.selected && modifiers.range_end ? { borderRadius: '0 0.25rem 0.25rem 0' } : {}),
            }}
          >
            {day.date.getDate()}
          </button>
        ),
        ...components,
      }}
      {...props}
    />
  )
}

export function Av({ name }: { name: string }) {
  return <div className="w-6 h-6 rounded-full bg-[var(--syn-accent-soft)] text-[var(--syn-accent)] flex items-center justify-center text-[10px] font-bold shrink-0 border border-[var(--syn-accent-line)]">{name.split(' ').map(n => n[0]).join('')}</div>
}

export function TenRowTableViewport({ testId, rowCount, children }: { testId: string; rowCount: number; children: React.ReactNode }) {
  const viewportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return

    const fitTenRows = () => {
      const header = viewport.querySelector('thead')
      const rows = Array.from(viewport.querySelectorAll('tbody tr')).slice(0, 10)
      const height = (header?.getBoundingClientRect().height ?? 0)
        + rows.reduce((sum, row) => sum + row.getBoundingClientRect().height, 0)
      viewport.style.maxHeight = `${Math.ceil(height)}px`
    }

    fitTenRows()
    const observer = new ResizeObserver(fitTenRows)
    const table = viewport.querySelector('table')
    if (table) observer.observe(table)
    return () => observer.disconnect()
  }, [rowCount])

  return <CardContent ref={viewportRef} data-testid={testId} className="p-0 overflow-y-auto">{children}</CardContent>
}
export function SortIcon({ dir }: { dir: SortDir }) {
  if (!dir) return <span className="text-[var(--syn-text-faint)] ml-1">{'↕'}</span>
  return <span className="ml-1 text-[var(--syn-accent)]">{dir === 'asc' ? '↑' : '↓'}</span>
}
export function sortBy<T>(arr: T[], key: string, dir: SortDir): T[] {
  if (!dir) return arr
  return [...arr].sort((a, b) => {
    let va = (a as any)[key], vb = (b as any)[key]
    if (va == null) va = ''; if (vb == null) vb = ''
    if (key === 'priority') { va = PRI_RANK[va] ?? 9; vb = PRI_RANK[vb] ?? 9 }
    if (typeof va === 'number' && typeof vb === 'number') return dir === 'asc' ? va - vb : vb - va
    return dir === 'asc' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va))
  })
}
export function textMatch(obj: any, q: string): boolean {
  if (!q) return true
  const lq = q.toLowerCase()
  return Object.values(obj).some(v => {
    if (Array.isArray(v)) return v.some(x => String(x).toLowerCase().includes(lq))
    return v != null && String(v).toLowerCase().includes(lq)
  })
}
export function useSortState() {
  const [col, setCol] = useState<string | null>(null)
  const [dir, setDir] = useState<SortDir>(null)
  const toggle = useCallback((c: string) => {
    if (col !== c) { setCol(c); setDir('asc') }
    else if (dir === 'asc') setDir('desc')
    else { setCol(null); setDir(null) }
  }, [col, dir])
  return { col, dir, toggle }
}
export function SH({ label, field, sort, onSort, className }: { label: string; field: string; sort: { col: string | null; dir: SortDir }; onSort: (f: string) => void; className?: string }) {
  return <TableHead className={`text-xs text-center cursor-pointer select-none hover:bg-[var(--syn-hover)] transition-colors ${className || ''}`} onClick={() => onSort(field)}><span className="flex items-center justify-center">{label}<SortIcon dir={sort.col === field ? sort.dir : null} /></span></TableHead>
}
export function shortTopic(t: any): string {
  return typeof t === 'object' && t !== null ? (t.name || '') : String(t || '')
}
export function TrashIcon() {
  return (
    <svg width="13" height="14" viewBox="0 0 13 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 3.5h11M4.5 3.5v-1a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5v1M3 3.5l.75 8h6.5l.75-8" />
    </svg>
  )
}

/* Source Chip — links back to originating meeting */
// Soft project colors (no pinks, no neon)
export const PROJECT_COLORS = [
  '#6b9bd2', '#7ab87a', '#c4a35a', '#8b8bc7', '#5ca8a8',
  '#b0855a', '#7aadad', '#9dab6f', '#a38db8', '#6fa8c7',
]
export function getProjectColor(projectId: string | null, projectIds: string[]): string {
  if (!projectId) return '#999'
  const idx = projectIds.indexOf(projectId)
  return PROJECT_COLORS[idx >= 0 ? idx % PROJECT_COLORS.length : 0]
}

export function SourceChip({ meeting, deleted = false, onClick }: { meeting: { id: string; title: string } | null; deleted?: boolean; onClick?: () => void }) {
  if (!meeting) return null
  const label = meeting.title.length > 18 ? meeting.title.slice(0, 18) + '…' : meeting.title
  return (
    <button onClick={onClick} className={`source-chip ${deleted ? 'source-chip-deleted' : ''} inline-flex items-center justify-center gap-1 px-3 py-0.5 rounded text-[10px] transition-colors w-full`} title={deleted ? `${meeting.title} — Meeting gelöscht` : meeting.title}>
      <span className="opacity-60">{'"'}</span><span className="text-center">{label}</span>
    </button>
  )
}

export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['style'],
  })
}

export function renderMarkdown(text: string) {
  const lines = text.split('\n')
  const elements: any[] = []
  let listBuffer: string[] = []
  let numberedBuffer: { num: string; text: string }[] = []
  let key = 0

  const flushList = () => {
    if (listBuffer.length > 0) {
      elements.push(<ul key={key++} className="my-1.5 space-y-0.5">{listBuffer.map((item, i) => <li key={i} className="flex gap-2 text-sm"><span className="text-[var(--syn-text-faint)] mt-0.5 shrink-0">•</span><span>{applyInline(item)}</span></li>)}</ul>)
      listBuffer = []
    }
    if (numberedBuffer.length > 0) {
      elements.push(<ol key={key++} className="my-1.5 space-y-0.5">{numberedBuffer.map((item, i) => <li key={i} className="flex gap-2 text-sm"><span className="text-[var(--syn-text-muted)] font-medium shrink-0 w-5 text-right">{item.num}</span><span>{applyInline(item.text)}</span></li>)}</ol>)
      numberedBuffer = []
    }
  }

  const applyInline = (s: string): any => {
    const parts = s.split(/(\*\*.+?\*\*|\*[^*\n]+?\*)/g)
    if (parts.length === 1) return s
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>
      if (part.startsWith('*') && part.endsWith('*')) return <em key={i}>{part.slice(1, -1)}</em>
      return part
    })
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (/^#{1,3}\s/.test(trimmed)) {
      flushList()
      const text = trimmed.replace(/^#{1,3}\s+/, '')
      const level = (trimmed.match(/^#+/) || [''])[0].length
      if (level === 1) elements.push(<div key={key++} className="text-base font-semibold mt-3 mb-1">{applyInline(text)}</div>)
      else if (level === 2) elements.push(<div key={key++} className="text-sm font-semibold text-[var(--syn-text-muted)] mt-2.5 mb-1">{applyInline(text)}</div>)
      else elements.push(<div key={key++} className="text-sm font-medium text-[var(--syn-text-faint)] mt-2 mb-0.5">{applyInline(text)}</div>)
      continue
    }
    const ulMatch = trimmed.match(/^[-*]\s+(.+)/)
    if (ulMatch) { if (numberedBuffer.length > 0) flushList(); listBuffer.push(ulMatch[1]); continue }
    const olMatch = trimmed.match(/^(\d+)\.\s+(.+)/)
    if (olMatch) { if (listBuffer.length > 0) flushList(); numberedBuffer.push({ num: olMatch[1] + '.', text: olMatch[2] }); continue }
    if (!trimmed) { flushList(); elements.push(<div key={key++} className="h-1.5" />); continue }
    flushList()
    elements.push(<p key={key++} className="text-sm">{applyInline(trimmed)}</p>)
  }
  flushList()
  return <div className="space-y-0.5">{elements}</div>
}

// Types
export interface Todo { id: string; assignee: string; title: string; description: string; status: string; priority: string; dueDate: string | null; startDate: string | null; durationDays: number; dependsOn: string[]; meetingId: string | null; meetingSource?: string | null; projectId: string | null; createdAt: string }
export interface Blocker { id: string; reportedBy: string; title: string; description: string; status: string; meetingId: string | null; meetingSource?: string | null; projectId: string | null; createdAt: string }
export interface OpenItem { id: string; owner: string; title: string; description: string; category: string; status: string; meetingId: string | null; meetingSource?: string | null; projectId: string | null; createdAt: string }
export interface MeetingTopicDetail { name: string; summary: string; sequence: number }
export interface Meeting {
  id: string
  title: string
  date: string
  topics: string[]
  participants: string[]
  summary: string
  keyDecisions: string[]
  sourceKind?: 'promoted' | 'pending'
  pendingRawTranscript?: string | null
  topicDetails?: MeetingTopicDetail[]
  participantsDraft?: string
  keyDecisionsDraft?: string
}

export function normalizeTopicDetails(topics: unknown): MeetingTopicDetail[] {
  if (!Array.isArray(topics)) return []
  return topics
    .map((topic, index) => {
      if (typeof topic === 'object' && topic !== null) {
        const value = topic as Record<string, unknown>
        return {
          name: String(value.name || '').trim(),
          summary: String(value.summary || '').trim(),
          sequence: Number.isFinite(Number(value.sequence)) ? Number(value.sequence) : index + 1,
        }
      }
      return { name: String(topic || '').trim(), summary: '', sequence: index + 1 }
    })
    .filter(topic => topic.name)
    .sort((a, b) => a.sequence - b.sequence)
}

export function stripEmbeddedTopicsFromSummary(summary: string): string {
  const marker = summary.search(/(?:<br\s*\/?>\s*)*---\s*Themen\s*---/i)
  if (marker === -1) return summary
  return summary.slice(0, marker).replace(/(?:<br\s*\/?>|\s)+$/gi, '').trim()
}

export function inboxMeetingView(item: DbInboxItem): Meeting {
  const payload = item.payload || {}
  const topicDetails = normalizeTopicDetails(payload.topics)
  return {
    id: `inbox_${item.id}`,
    title: payload.title || '',
    date: payload.meeting_date || '',
    topics: topicDetails.map(topic => topic.name),
    participants: payload.participants || [],
    summary: payload.ai_summary || '',
    keyDecisions: payload.key_decisions || [],
    sourceKind: 'pending',
    pendingRawTranscript: typeof payload.raw_transcript === 'string' ? payload.raw_transcript : null,
    topicDetails,
  }
}
export interface Activity { id: string; entityType: string; entityId: string; entityTitle: string; action: string; field: string | null; oldValue: string | null; newValue: string | null; meetingId: string | null; timestamp: string }
export interface ChatMessage { role: 'user' | 'assistant'; text: string; sources?: AskMemoryMeetingSource[]; chunkSources?: AskMemoryChunkSource[]; itemSources?: AskMemoryItemSource[]; mode?: string; scalingNotice?: string; timestamp?: number; tokens?: { input: number; output: number }; model?: string; costUsd?: number }

// Datums-Arithmetik fuer Gantt/Projekt-Ansichten und Todo-Dialoge.
export const addDays = (d: string, n: number) => { const dt = new Date(d); dt.setDate(dt.getDate() + n); return dt.toISOString().split('T')[0] }
export const todoEndDate = (t: Todo) => t.startDate ? addDays(t.startDate, Math.max(t.durationDays - 1, 0)) : t.dueDate
