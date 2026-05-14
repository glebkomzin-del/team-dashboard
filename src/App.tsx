import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  fetchTeamMembers, fetchMeetings, fetchTodos, fetchBlockers, fetchOpenItems, fetchActivityLog,
  fetchProjects, insertProject,
  updateTodoStatus, deleteTodoDb, updateBlockerStatus, deleteBlockerDb,
  updateOpenItemStatus, deleteOpenItemDb, deleteMeetingDb,
  updateTodoFull, updateBlockerFull, updateOpenItemFull, updateMeetingFull,
  updateProjectFull, deleteProjectDb,
  insertTodo, insertBlocker, insertOpenItem, logActivity,
  triggerMakeWebhook, MAKE_WEBHOOK_URL,
  isNightlyJobActive, toggleNightlyJob,
  signIn, signOut, resetPassword, getSession, onAuthStateChange,
  semanticSearchStream,
  type DbTeamMember, type DbProject, type SearchMatch
} from './supabase'

type Page = 'uebersicht' | 'sitzungen' | 'aktionen' | 'projekte' | 'ki' | 'textsuche' | 'protokoll'
type SortDir = 'asc' | 'desc' | null
type ProjectView = 'table' | 'kanban' | 'gantt'
type ActionTab = 'todos' | 'blocker' | 'open'

const PRI_LABEL: Record<string, string> = { urgent: 'Urgent', high: 'Hoch', medium: 'Mittel', low: 'Niedrig' }
const PRI_RANK: Record<string, number> = { urgent: 0, high: 1, medium: 2, low: 3 }
const PRI_STYLE: Record<string, string> = {
  urgent: 'bg-[var(--syn-danger)] text-white',
  high: 'bg-[var(--syn-danger-soft)] text-[var(--syn-danger)] border border-[var(--syn-danger)]/20',
  medium: 'bg-[var(--syn-neutral-chip)] text-[var(--syn-text-muted)]',
  low: 'bg-[var(--syn-surface-2)] text-[var(--syn-text-faint)]'
}
const ST_STYLE: Record<string, string> = {
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
  rejected: 'bg-[var(--syn-danger-soft)] text-[var(--syn-danger)]',
  completed: 'bg-[var(--syn-ok-soft)] text-[var(--syn-ok)]',
  on_hold: 'bg-[var(--syn-warn-soft)] text-[var(--syn-warn)]',
}
const ST_LABEL: Record<string, string> = { open: 'Offen', in_progress: 'In Arbeit', done: 'Erledigt', cancelled: 'Abgebr.', active: 'Aktiv', resolved: 'Gelöst', escalated: 'Eskaliert', watching: 'Beobachten', closed: 'Geschlossen', approved: 'Genehmigt', pending: 'Ausstehend', rejected: 'Abgelehnt', completed: 'Abgeschlossen', on_hold: 'Pausiert' }
const ACTION_LABEL: Record<string, string> = { status_changed: 'Status geändert', created: 'Erstellt', updated: 'Bearbeitet', deleted: 'Gelöscht', reassigned: 'Zugewiesen' }
const TYPE_LABEL: Record<string, string> = { todo: 'Todo', blocker: 'Blocker', open_item: 'Open Item', meeting: 'Meeting', decision: 'Entscheidung', project: 'Projekt', activity: 'Änderung' }
const CAT_ICON: Record<string, string> = { risk: '⚠️', opportunity: '💡', question: '❓', follow_up: '↩️', general: '○' }
const MEMBER_ORDER = ['Gleb', 'Niko', 'Mathias', 'Jan Philipp', 'Extern', 'Nicht zugeordnet']
const FINAL_STATUSES = new Set(['done', 'resolved', 'closed', 'approved', 'completed'])

function Av({ name }: { name: string }) {
  return <div className="w-6 h-6 rounded-full bg-[var(--syn-accent-soft)] text-[var(--syn-accent)] flex items-center justify-center text-[10px] font-bold shrink-0 border border-[var(--syn-accent-line)]">{name.split(' ').map(n => n[0]).join('')}</div>
}
function SortIcon({ dir }: { dir: SortDir }) {
  if (!dir) return <span className="text-[var(--syn-text-faint)] ml-1">{'↕'}</span>
  return <span className="ml-1 text-[var(--syn-accent)]">{dir === 'asc' ? '↑' : '↓'}</span>
}
function sortBy<T>(arr: T[], key: string, dir: SortDir): T[] {
  if (!dir) return arr
  return [...arr].sort((a, b) => {
    let va = (a as any)[key], vb = (b as any)[key]
    if (va == null) va = ''; if (vb == null) vb = ''
    if (key === 'priority') { va = PRI_RANK[va] ?? 9; vb = PRI_RANK[vb] ?? 9 }
    if (typeof va === 'number' && typeof vb === 'number') return dir === 'asc' ? va - vb : vb - va
    return dir === 'asc' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va))
  })
}
function textMatch(obj: any, q: string): boolean {
  if (!q) return true
  const lq = q.toLowerCase()
  return Object.values(obj).some(v => {
    if (Array.isArray(v)) return v.some(x => String(x).toLowerCase().includes(lq))
    return v != null && String(v).toLowerCase().includes(lq)
  })
}
function useSortState() {
  const [col, setCol] = useState<string | null>(null)
  const [dir, setDir] = useState<SortDir>(null)
  const toggle = useCallback((c: string) => {
    if (col !== c) { setCol(c); setDir('asc') }
    else if (dir === 'asc') setDir('desc')
    else { setCol(null); setDir(null) }
  }, [col, dir])
  return { col, dir, toggle }
}
function SH({ label, field, sort, onSort, className }: { label: string; field: string; sort: { col: string | null; dir: SortDir }; onSort: (f: string) => void; className?: string }) {
  return <TableHead className={`cursor-pointer select-none hover:bg-[var(--syn-hover)] transition-colors ${className || ''}`} onClick={() => onSort(field)}><span className="flex items-center text-xs">{label}<SortIcon dir={sort.col === field ? sort.dir : null} /></span></TableHead>
}

/* Source Chip — links back to originating meeting */
function SourceChip({ meeting, onClick }: { meeting: { id: string; title: string } | null; onClick?: () => void }) {
  if (!meeting) return null
  return (
    <button onClick={onClick} className="source-chip inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] transition-colors" title={meeting.title}>
      <span className="opacity-60">{'"'}</span><span className="truncate max-w-[120px]">{meeting.title}</span>
    </button>
  )
}

function sanitizeHtml(html: string): string {
  return html.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/on\w+\s*=\s*"[^"]*"/gi, '').replace(/on\w+\s*=\s*'[^']*'/gi, '')
}

function renderMarkdown(text: string) {
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
    const parts = s.split(/\*\*(.+?)\*\*/g)
    if (parts.length === 1) return s
    return parts.map((p, i) => i % 2 === 1 ? <strong key={i} className="font-semibold">{p}</strong> : p)
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
interface Todo { id: string; assignee: string; title: string; description: string; status: string; priority: string; dueDate: string | null; startDate: string | null; durationDays: number; dependsOn: string[]; meetingId: string | null; projectId: string | null; createdAt: string }
interface Blocker { id: string; reportedBy: string; title: string; description: string; status: string; meetingId: string | null; projectId: string | null; createdAt: string }
interface OpenItem { id: string; owner: string; title: string; description: string; category: string; status: string; meetingId: string | null; projectId: string | null; createdAt: string }
interface Meeting { id: string; title: string; date: string; topics: string[]; participants: string[]; summary: string; keyDecisions: string[] }
interface Activity { id: string; entityType: string; entityId: string; entityTitle: string; action: string; field: string | null; oldValue: string | null; newValue: string | null; meetingId: string | null; timestamp: string }
interface ChatMessage { role: 'user' | 'assistant'; text: string; matches?: SearchMatch[]; timestamp?: number }

export default function App() {
  const [session, setSession] = useState<any>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try { return (localStorage.getItem('mos_theme') as 'dark' | 'light') || 'dark' } catch { return 'dark' }
  })
  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    try { localStorage.setItem('mos_theme', theme) } catch {}
  }, [theme])
  useEffect(() => {
    getSession().then(s => { setSession(s); setAuthLoading(false) })
    const { data: listener } = onAuthStateChange(s => setSession(s))
    return () => listener.subscription.unsubscribe()
  }, [])
  if (authLoading) return <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--syn-bg)' }}><div className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Prüfe Anmeldung...</div></div>
  if (!session) return <LoginScreen theme={theme} setTheme={setTheme} />
  return <Dashboard onLogout={async () => { await signOut() }} theme={theme} setTheme={setTheme} />
}

function LoginScreen(_props: { theme: 'dark' | 'light'; setTheme: (t: 'dark' | 'light') => void }) {
  const [email, setEmail] = useState('')
  const [pass, setPass] = useState('')
  const [error, setError] = useState('')
  const [mode, setMode] = useState<'login' | 'reset'>('login')
  const [resetSent, setResetSent] = useState(false)
  const handleLogin = async () => { setError(''); try { await signIn(email, pass) } catch (e: any) { setError(e.message || 'Login fehlgeschlagen') } }
  const handleReset = async () => { setError(''); try { await resetPassword(email); setResetSent(true) } catch (e: any) { setError(e.message || 'Fehler') } }

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--syn-bg)' }}>
      <div className="w-80 glass-card rounded-xl p-6 space-y-4 border border-[var(--syn-line)]">
        <div className="flex items-center justify-center mb-2">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: 'var(--syn-accent)' }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 1L16 5V13L9 17L2 13V5Z" stroke="white" strokeWidth="1.5" fill="none"/><circle cx="9" cy="9" r="2.5" fill="white"/></svg>
          </div>
        </div>
        <p className="text-center text-sm font-medium" style={{ color: 'var(--syn-text)' }}>Meeting OS</p>
        {mode === 'login' ? <>
          <Input placeholder="E-Mail" type="email" value={email} onChange={e => setEmail(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleLogin()} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
          <Input placeholder="Passwort" type="password" value={pass} onChange={e => setPass(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleLogin()} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
          {error && <p className="text-xs text-[var(--syn-danger)]">{error}</p>}
          <Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={handleLogin}>Anmelden</Button>
          <button onClick={() => { setMode('reset'); setError(''); setResetSent(false) }} className="text-xs w-full text-center" style={{ color: 'var(--syn-text-faint)' }}>Passwort vergessen?</button>
        </> : <>
          <p className="text-sm text-center" style={{ color: 'var(--syn-text-muted)' }}>Passwort zurücksetzen</p>
          <Input placeholder="E-Mail" type="email" value={email} onChange={e => setEmail(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleReset()} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
          {error && <p className="text-xs text-[var(--syn-danger)]">{error}</p>}
          {resetSent ? <p className="text-xs text-[var(--syn-ok)] text-center">Reset-Link gesendet.</p> : <Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={handleReset}>Link senden</Button>}
          <button onClick={() => { setMode('login'); setError('') }} className="text-xs w-full text-center" style={{ color: 'var(--syn-text-faint)' }}>{'←'} Zurück</button>
        </>}
      </div>
    </div>
  )
}

function Dashboard({ onLogout, theme, setTheme }: { onLogout: () => void; theme: 'dark' | 'light'; setTheme: (t: 'dark' | 'light') => void }) {
  // Hash routing with backward compat
  const getPageFromHash = (): Page => {
    const raw = window.location.hash.replace('#', '')
    const map: Record<string, Page> = { dashboard: 'uebersicht', uebersicht: 'uebersicht', notizen: 'sitzungen', protokoll: 'protokoll', projekte: 'projekte', ki: 'ki', textsuche: 'textsuche', sitzungen: 'sitzungen', aktionen: 'aktionen' }
    return map[raw] || 'uebersicht'
  }
  const [page, setPageRaw] = useState<Page>(getPageFromHash)
  const setPage = (p: Page) => { setPageRaw(p); window.location.hash = p }
  useEffect(() => {
    const handler = () => setPageRaw(getPageFromHash())
    window.addEventListener('hashchange', handler)
    return () => window.removeEventListener('hashchange', handler)
  }, [])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [nightlyActive, setNightlyActive] = useState(true)
  const [globalSearch, setGlobalSearch] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const [projectView, setProjectView] = useState<ProjectView>('table')
  const [actionTab, setActionTab] = useState<ActionTab>('todos')

  const [members, setMembers] = useState<DbTeamMember[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [blockers, setBlockers] = useState<Blocker[]>([])
  const [openItems, setOpenItems] = useState<OpenItem[]>([])
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [activity, setActivity] = useState<Activity[]>([])
  const [projects, setProjects] = useState<DbProject[]>([])

  // Chat
  const CHAT_STORAGE_KEY = 'mos_chat_history'
  const CHAT_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000
  const loadChatHistory = (): ChatMessage[] => {
    try {
      const raw = localStorage.getItem(CHAT_STORAGE_KEY)
      if (!raw) return []
      const stored: { messages: ChatMessage[]; savedAt: number }[] = JSON.parse(raw)
      const cutoff = Date.now() - CHAT_MAX_AGE_MS
      const valid = stored.filter(e => e.savedAt > cutoff)
      if (valid.length < stored.length) localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(valid))
      return valid.flatMap(e => e.messages)
    } catch { return [] }
  }
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(loadChatHistory)
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Filters
  const [todoSearch, setTodoSearch] = useState('')
  const [blockerSearch, setBlockerSearch] = useState('')
  const [blockerFilterAssignee, setBlockerFilterAssignee] = useState('all')
  const [blockerFilterStatus, setBlockerFilterStatus] = useState('all')
  const [openSearch, setOpenSearch] = useState('')
  const [openFilterOwner, setOpenFilterOwner] = useState('all')
  const [openFilterStatus, setOpenFilterStatus] = useState('all')
  const [openFilterCategory, setOpenFilterCategory] = useState('all')
  const [noteSearch, setNoteSearch] = useState('')
  const [logSearch, setLogSearch] = useState('')
  const [projectSearch, setProjectSearch] = useState('')
  const [todoFilterAssignee, setTodoFilterAssignee] = useState('all')
  const [todoFilterDue, setTodoFilterDue] = useState('all')
  const [todoFilterStatus, setTodoFilterStatus] = useState('all')
  const [todoFilterProject, setTodoFilterProject] = useState('all')
  const [noteFilterParticipant, setNoteFilterParticipant] = useState('all')
  const [noteFilterDateFrom, setNoteFilterDateFrom] = useState('')
  const [noteFilterDateTo, setNoteFilterDateTo] = useState('')
  const [logFilterType, setLogFilterType] = useState('all')
  const [projectFilterStatus, setProjectFilterStatus] = useState('all')
  const todoSort = useSortState(); const blockerSort = useSortState(); const openSort = useSortState()
  const noteSort = useSortState(); const logSort = useSortState(); const projectSort = useSortState()

  // Edit state
  const [editTodo, setEditTodo] = useState<Todo | null>(null)
  const [editBlocker, setEditBlocker] = useState<Blocker | null>(null)
  const [editOpen, setEditOpen] = useState<OpenItem | null>(null)
  const [editMeeting, setEditMeeting] = useState<Meeting | null>(null)
  const [editProject, setEditProject] = useState<DbProject | null>(null)
  const [viewMeeting, setViewMeeting] = useState<Meeting | null>(null)
  const [viewTodo, setViewTodo] = useState<Todo | null>(null)
  const [viewBlocker, setViewBlocker] = useState<Blocker | null>(null)
  const [viewOpen, setViewOpen] = useState<OpenItem | null>(null)
  const [viewProject, setViewProject] = useState<DbProject | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [dragTodo, setDragTodo] = useState<string | null>(null)
  const [kanbanFields, setKanbanFields] = useState<Set<string>>(new Set(['priority', 'assignee', 'duration', 'project']))
  const [ganttFields, setGanttFields] = useState<Set<string>>(new Set(['assignee', 'duration']))
  type GanttGranularity = 'month' | 'quarter' | 'year'
  const [ganttGranularity, setGanttGranularity] = useState<GanttGranularity>('month')
  const [ganttFilterProject, setGanttFilterProject] = useState('all')
  const [ganttFilterAssignee, setGanttFilterAssignee] = useState('all')
  const [ganttSortKey, setGanttSortKey] = useState<'start' | 'assignee' | 'priority' | 'project'>('start')
  const [ganttSortDir, setGanttSortDir] = useState<'asc' | 'desc'>('asc')
  const ganttDragRef = useRef<{ todoId: string; mode: 'move' | 'resize'; startX: number; origStart: string; origDuration: number } | null>(null)
  const toggleField = (set: Set<string>, setFn: (s: Set<string>) => void, field: string) => { const n = new Set(set); if (n.has(field)) n.delete(field); else n.add(field); setFn(n) }

  const memberNames = useMemo(() => {
    const names = members.map(m => m.name)
    return names.sort((a, b) => {
      const ia = MEMBER_ORDER.indexOf(a); const ib = MEMBER_ORDER.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
  }, [members])

  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

  const loadData = useCallback(async () => {
    try {
      setError(null)
      const [mems, mtgs, tds, blk, oi, act, prj] = await Promise.all([
        fetchTeamMembers(), fetchMeetings(), fetchTodos(), fetchBlockers(), fetchOpenItems(), fetchActivityLog(), fetchProjects()
      ])
      setMembers(mems); setProjects(prj)
      setMeetings(mtgs.map(m => ({ id: m.id, title: m.title, date: m.meeting_date?.split('T')[0] || '', topics: m.topics || [], participants: m.participants || [], summary: m.ai_summary || '', keyDecisions: m.key_decisions || [] })))
      setTodos(tds.map(t => ({ id: t.id, assignee: t.assignee || 'Nicht zugeordnet', title: t.title, description: t.description || '', status: t.status, priority: t.priority, dueDate: t.due_date, startDate: (t as any).start_date || null, durationDays: (t as any).duration_days || 1, dependsOn: (t as any).depends_on || [], meetingId: t.meeting_id, projectId: (t as any).project_id || null, createdAt: t.created_at?.split('T')[0] || '' })))
      setBlockers(blk.map(b => ({ id: b.id, reportedBy: b.reported_by || 'Nicht zugeordnet', title: b.title, description: b.description || '', status: b.status, meetingId: b.meeting_id, projectId: (b as any).project_id || null, createdAt: b.created_at?.split('T')[0] || '' })))
      setOpenItems(oi.map(o => ({ id: o.id, owner: o.owner || 'Nicht zugeordnet', title: o.title, description: o.description || '', category: o.category, status: o.status, meetingId: o.meeting_id, projectId: (o as any).project_id || null, createdAt: o.created_at?.split('T')[0] || '' })))
      const todoMap: Record<string, string> = {}; tds.forEach(t => { todoMap[t.id] = t.title })
      const blkMap: Record<string, string> = {}; blk.forEach(b => { blkMap[b.id] = b.title })
      const oiMap: Record<string, string> = {}; oi.forEach(o => { oiMap[o.id] = o.title })
      const mtgMap: Record<string, string> = {}; mtgs.forEach(m => { mtgMap[m.id] = m.title })
      const decMap: Record<string, string> = {}
      const prjMap: Record<string, string> = {}; prj.forEach(p => { prjMap[p.id] = p.name })
      setActivity(act.map(a => {
        let title = ''
        const note = (a as any).note || ''
        if (a.entity_type === 'todo') title = todoMap[a.entity_id] || note || a.new_value || '?'
        else if (a.entity_type === 'blocker') title = blkMap[a.entity_id] || note || a.new_value || '?'
        else if (a.entity_type === 'open_item') title = oiMap[a.entity_id] || note || a.new_value || '?'
        else if (a.entity_type === 'meeting') title = mtgMap[a.entity_id] || note || a.new_value || '?'
        else if (a.entity_type === 'decision') title = decMap[a.entity_id] || note || a.new_value || '?'
        else if (a.entity_type === 'project') title = prjMap[a.entity_id] || note || a.new_value || '?'
        return { id: a.id, entityType: a.entity_type, entityId: a.entity_id, entityTitle: title, action: a.action, field: a.field_changed, oldValue: a.old_value, newValue: a.new_value, meetingId: (a as any).meeting_id || null, timestamp: a.created_at }
      }))
    } catch (e: any) { setError(e.message || 'Fehler beim Laden') } finally { setLoading(false) }
  }, [])

  useEffect(() => { loadData(); isNightlyJobActive().then(setNightlyActive).catch(() => {}) }, [loadData])
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chatMessages])
  useEffect(() => { if (page === 'ki') setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'auto' }), 100) }, [page])
  useEffect(() => {
    if (chatMessages.length === 0) return
    try {
      const sessionEntry = { messages: chatMessages, savedAt: Date.now() }
      localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify([sessionEntry]))
    } catch { }
  }, [chatMessages])

  const handleToggleNightly = async () => { const next = !nightlyActive; setNightlyActive(next); try { await toggleNightlyJob(next) } catch { setNightlyActive(!next) } }

  // CRUD Handlers — identical logic
  const cycleTodo = async (t: Todo) => { const order = ['open', 'in_progress', 'done']; const next = order[(order.indexOf(t.status) + 1) % 3]; setTodos(prev => prev.map(x => x.id === t.id ? { ...x, status: next } : x)); try { await updateTodoStatus(t.id, next) } catch { } }
  const handleDeleteTodo = async (t: Todo) => { setTodos(prev => prev.filter(x => x.id !== t.id)); try { await deleteTodoDb(t.id) } catch { } }
  const handleSaveTodo = async (t: Todo) => { setTodos(prev => prev.map(x => x.id === t.id ? t : x)); setEditTodo(null); try { await updateTodoFull(t.id, { title: t.title, description: t.description, assignee: t.assignee, priority: t.priority, status: t.status, due_date: t.dueDate, start_date: t.startDate, duration_days: t.durationDays, project_id: t.projectId, depends_on: t.dependsOn } as any) } catch { } }
  const handleResolveBlocker = async (b: Blocker) => { setBlockers(prev => prev.map(x => x.id === b.id ? { ...x, status: 'resolved' } : x)); try { await updateBlockerStatus(b.id, 'resolved') } catch { } }
  const handleDeleteBlocker = async (b: Blocker) => { setBlockers(prev => prev.filter(x => x.id !== b.id)); try { await deleteBlockerDb(b.id) } catch { } }
  const handleSaveBlocker = async (b: Blocker) => { setBlockers(prev => prev.map(x => x.id === b.id ? b : x)); setEditBlocker(null); try { await updateBlockerFull(b.id, { title: b.title, description: b.description, reported_by: b.reportedBy, status: b.status }) } catch { } }
  const handleCloseItem = async (o: OpenItem) => { setOpenItems(prev => prev.map(x => x.id === o.id ? { ...x, status: 'closed' } : x)); try { await updateOpenItemStatus(o.id, 'closed') } catch { } }
  const handleDeleteOpen = async (o: OpenItem) => { setOpenItems(prev => prev.filter(x => x.id !== o.id)); try { await deleteOpenItemDb(o.id) } catch { } }
  const handleSaveOpen = async (o: OpenItem) => { setOpenItems(prev => prev.map(x => x.id === o.id ? o : x)); setEditOpen(null); try { await updateOpenItemFull(o.id, { title: o.title, description: o.description, owner: o.owner, category: o.category, status: o.status }) } catch { } }
  const handleDeleteMeeting = async (m: Meeting) => { setMeetings(prev => prev.filter(x => x.id !== m.id)); try { await deleteMeetingDb(m.id) } catch { } }
  const handleSaveMeeting = async (m: Meeting) => { setMeetings(prev => prev.map(x => x.id === m.id ? m : x)); setEditMeeting(null); try { await updateMeetingFull(m.id, { title: m.title, meeting_date: m.date, topics: m.topics, participants: m.participants, ai_summary: m.summary, key_decisions: m.keyDecisions }) } catch { } }
  const handleCreateTodo = async (t: Todo) => { setEditTodo(null); try { const c = await insertTodo({ title: t.title, description: t.description || undefined, assignee: t.assignee, priority: t.priority, due_date: t.dueDate || undefined } as any); setTodos(prev => [{ id: c.id, assignee: c.assignee, title: c.title, description: c.description || '', status: c.status, priority: c.priority, dueDate: c.due_date, startDate: t.startDate, durationDays: t.durationDays, dependsOn: [], meetingId: null, projectId: t.projectId, createdAt: new Date().toISOString().split('T')[0] }, ...prev]); if (t.startDate || t.projectId || t.durationDays > 1) { await updateTodoFull(c.id, { start_date: t.startDate, duration_days: t.durationDays, project_id: t.projectId } as any) } } catch { } }
  const handleCreateBlocker = async (b: Blocker) => { setEditBlocker(null); try { const c = await insertBlocker({ title: b.title, description: b.description || undefined, reported_by: b.reportedBy }); setBlockers(prev => [{ id: c.id, reportedBy: c.reported_by, title: c.title, description: c.description || '', status: c.status, meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev]); await logActivity('blocker', c.id, 'created', c.title) } catch { } }
  const handleCreateOpen = async (o: OpenItem) => { setEditOpen(null); try { const c = await insertOpenItem({ title: o.title, description: o.description || undefined, owner: o.owner, category: o.category }); setOpenItems(prev => [{ id: c.id, owner: c.owner, title: c.title, description: c.description || '', category: c.category, status: c.status, meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev]); await logActivity('open_item', c.id, 'created', c.title) } catch { } }
  const handleSaveProject = async (p: DbProject) => { if (p.id === '__new__') { setEditProject(null); try { const c = await insertProject({ name: p.name, description: p.description || undefined }); setProjects(prev => [...prev, c]) } catch { } } else { setProjects(prev => prev.map(x => x.id === p.id ? p : x)); setEditProject(null); try { await updateProjectFull(p.id, { name: p.name, description: p.description, status: p.status }) } catch { } } }
  const handleDeleteProject = async (p: DbProject) => { setProjects(prev => prev.filter(x => x.id !== p.id)); try { await deleteProjectDb(p.id) } catch { } }

  const handleQuickStatusToggle = async (t: Todo) => {
    const newStatus = t.status === 'done' ? 'open' : 'done'
    setTodos(prev => prev.map(x => x.id === t.id ? { ...x, status: newStatus } : x))
    try { await updateTodoStatus(t.id, newStatus); await logActivity('todo', t.id, 'status_changed', newStatus) } catch { setTodos(prev => prev.map(x => x.id === t.id ? { ...x, status: t.status } : x)) }
  }

  // Chat
  const handleChat = async (overrideText?: string) => {
    const text = overrideText || chatInput
    if (!text.trim() || chatLoading) return
    const q = text.trim(); setChatInput('')
    const updatedMessages = [...chatMessages, { role: 'user' as const, text: q, timestamp: Date.now() }]
    setChatMessages(updatedMessages)
    setChatLoading(true)
    const history = updatedMessages.slice(-10).map(m => ({ role: m.role, text: m.text.slice(0, 500) }))
    // Add empty assistant message that will be streamed into
    const assistantMsg: ChatMessage = { role: 'assistant', text: '', timestamp: Date.now() }
    setChatMessages(prev => [...prev, assistantMsg])
    try {
      await semanticSearchStream(
        q, history,
        (matches) => { setChatMessages(prev => { const msgs = [...prev]; const last = msgs[msgs.length - 1]; if (last.role === 'assistant') { msgs[msgs.length - 1] = { ...last, matches }; } return msgs; }) },
        (delta) => { setChatMessages(prev => { const msgs = [...prev]; const last = msgs[msgs.length - 1]; if (last.role === 'assistant') { msgs[msgs.length - 1] = { ...last, text: last.text + delta }; } return msgs; }) },
        () => { setChatLoading(false) },
        (err) => { setChatMessages(prev => { const msgs = [...prev]; const last = msgs[msgs.length - 1]; if (last.role === 'assistant') { msgs[msgs.length - 1] = { ...last, text: `Fehler: ${err}` }; } return msgs; }); setChatLoading(false) },
      )
    } catch (e: any) {
      setChatMessages(prev => { const msgs = [...prev]; const last = msgs[msgs.length - 1]; if (last.role === 'assistant') { msgs[msgs.length - 1] = { ...last, text: `Fehler: ${e.message}` }; } return msgs; })
      setChatLoading(false)
    }
  }

  const handleAblegen = async () => { await loadData() }
  const handleRefresh = async () => { setRefreshing(true); try { if (MAKE_WEBHOOK_URL) { try { await triggerMakeWebhook() } catch { } await new Promise(r => setTimeout(r, 10000)) } await loadData() } catch (e: any) { setError(e.message) } finally { setRefreshing(false) } }

  const getMeeting = (id: string | null) => meetings.find(m => m.id === id)
  const getProjectName = (id: string | null) => projects.find(p => p.id === id)?.name || null

  const openSourceEntity = (entityType: string, entityId: string) => {
    switch (entityType) {
      case 'todo': { const t = todos.find(x => x.id === entityId); if (t) setViewTodo(t); break }
      case 'blocker': { const b = blockers.find(x => x.id === entityId); if (b) setViewBlocker(b); break }
      case 'open_item': { const o = openItems.find(x => x.id === entityId); if (o) setViewOpen(o); break }
      case 'meeting': { const m = meetings.find(x => x.id === entityId); if (m) setViewMeeting(m); break }
      case 'decision': { break }
      case 'project': { const p = projects.find(x => x.id === entityId); if (p) setViewProject(p); break }
    }
  }

  // Filtered data — identical logic
  const filteredTodos = useMemo(() => {
    let r = todos.filter(t => textMatch(t, todoSearch || globalSearch))
    if (todoFilterAssignee !== 'all') r = r.filter(t => t.assignee === todoFilterAssignee)
    if (todoFilterStatus !== 'all') r = r.filter(t => t.status === todoFilterStatus)
    if (todoFilterProject !== 'all') r = r.filter(t => t.projectId === todoFilterProject)
    if (todoFilterDue === 'overdue') r = r.filter(t => t.dueDate && t.dueDate < today && t.status !== 'done')
    else if (todoFilterDue === 'this_week') { const d = new Date(); const s = new Date(d); s.setDate(d.getDate() - d.getDay() + 1); const e = new Date(s); e.setDate(s.getDate() + 6); const ss = s.toISOString().split('T')[0]; const ee = e.toISOString().split('T')[0]; r = r.filter(t => t.dueDate && t.dueDate >= ss && t.dueDate <= ee) }
    else if (todoFilterDue === 'no_date') r = r.filter(t => !t.dueDate)
    return todoSort.col ? sortBy(r, todoSort.col, todoSort.dir) : r.sort((a, b) => PRI_RANK[a.priority] - PRI_RANK[b.priority])
  }, [todos, todoSearch, globalSearch, todoFilterAssignee, todoFilterDue, todoFilterStatus, todoFilterProject, todoSort.col, todoSort.dir, today])
  const filteredBlockers = useMemo(() => {
    let r = blockers.filter(b => textMatch(b, blockerSearch || globalSearch))
    if (blockerFilterAssignee !== 'all') r = r.filter(b => b.reportedBy === blockerFilterAssignee)
    if (blockerFilterStatus !== 'all') r = r.filter(b => b.status === blockerFilterStatus)
    return blockerSort.col ? sortBy(r, blockerSort.col, blockerSort.dir) : r
  }, [blockers, blockerSearch, globalSearch, blockerFilterAssignee, blockerFilterStatus, blockerSort.col, blockerSort.dir])
  const filteredOpen = useMemo(() => {
    let r = openItems.filter(o => textMatch(o, openSearch || globalSearch))
    if (openFilterOwner !== 'all') r = r.filter(o => o.owner === openFilterOwner)
    if (openFilterStatus !== 'all') r = r.filter(o => o.status === openFilterStatus)
    if (openFilterCategory !== 'all') r = r.filter(o => o.category === openFilterCategory)
    return openSort.col ? sortBy(r, openSort.col, openSort.dir) : r
  }, [openItems, openSearch, globalSearch, openFilterOwner, openFilterStatus, openFilterCategory, openSort.col, openSort.dir])
  const filteredNotes = useMemo(() => {
    let r = meetings.filter(m => textMatch(m, noteSearch || globalSearch))
    if (noteFilterParticipant !== 'all') r = r.filter(m => m.participants.some(p => p.includes(noteFilterParticipant)))
    if (noteFilterDateFrom) r = r.filter(m => m.date >= noteFilterDateFrom)
    if (noteFilterDateTo) r = r.filter(m => m.date <= noteFilterDateTo)
    return noteSort.col ? sortBy(r, noteSort.col, noteSort.dir) : r.sort((a, b) => b.date.localeCompare(a.date))
  }, [meetings, noteSearch, globalSearch, noteFilterParticipant, noteFilterDateFrom, noteFilterDateTo, noteSort.col, noteSort.dir])
  const filteredLog = useMemo(() => {
    let r = activity.filter(a => {
      if (a.action === 'deleted') return false
      if (a.action === 'status_changed' && a.newValue && !FINAL_STATUSES.has(a.newValue)) return false
      if (a.action === 'status_changed' || a.action === 'created') return true
      return false
    })
    r = r.filter(a => textMatch(a, logSearch || globalSearch))
    if (logFilterType !== 'all') r = r.filter(a => a.entityType === logFilterType)
    return logSort.col ? sortBy(r, logSort.col, logSort.dir) : r
  }, [activity, logSearch, globalSearch, logFilterType, logSort.col, logSort.dir])
  const filteredProjects = useMemo(() => {
    let r = projects.filter(p => textMatch(p, projectSearch || globalSearch))
    if (projectFilterStatus !== 'all') r = r.filter(p => p.status === projectFilterStatus)
    return projectSort.col ? sortBy(r, projectSort.col, projectSort.dir) : r
  }, [projects, projectSearch, globalSearch, projectFilterStatus, projectSort.col, projectSort.dir])

  const searchResults = useMemo(() => {
    const q = globalSearch.trim().toLowerCase()
    if (!q) return { meetings: [] as Meeting[], todos: [] as Todo[], blockers: [] as Blocker[] }
    const matchMeetings = meetings.filter(m => textMatch(m, q)).slice(0, 5)
    const matchTodos = todos.filter(t => textMatch(t, q)).slice(0, 5)
    const matchBlockers = blockers.filter(b => textMatch(b, q)).slice(0, 5)
    return { meetings: matchMeetings, todos: matchTodos, blockers: matchBlockers }
  }, [globalSearch, meetings, todos, blockers])

  const searchResultsFull = useMemo(() => {
    const q = globalSearch.trim().toLowerCase()
    if (!q) return { meetings: [] as Meeting[], todos: [] as Todo[], blockers: [] as Blocker[], openItems: [] as OpenItem[] }
    return {
      meetings: meetings.filter(m => textMatch(m, q)),
      todos: todos.filter(t => textMatch(t, q)),
      blockers: blockers.filter(b => textMatch(b, q)),
      openItems: openItems.filter(o => textMatch(o, q)),
    }
  }, [globalSearch, meetings, todos, blockers, openItems])

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (searchRef.current && !searchRef.current.contains(e.target as Node)) setSearchFocused(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Kanban helpers
  const kanbanColumns = ['open', 'in_progress', 'done'] as const
  const kanbanLabels: Record<string, string> = { open: 'Offen', in_progress: 'In Arbeit', done: 'Erledigt' }
  const handleKanbanDrop = async (todoId: string, newStatus: string) => {
    setDragTodo(null)
    const todo = todos.find(t => t.id === todoId)
    if (!todo || todo.status === newStatus) return
    setTodos(prev => prev.map(t => t.id === todoId ? { ...t, status: newStatus } : t))
    try { await updateTodoStatus(todoId, newStatus) } catch { }
  }

  // Gantt helpers
  const addDays = (d: string, n: number) => { const dt = new Date(d); dt.setDate(dt.getDate() + n); return dt.toISOString().split('T')[0] }
  const todoEndDate = (t: Todo) => t.startDate ? addDays(t.startDate, Math.max(t.durationDays - 1, 0)) : t.dueDate
  const ganttTodos = useMemo(() => {
    let r = todos.filter(t => t.startDate)
    if (ganttFilterProject !== 'all') r = r.filter(t => t.projectId === ganttFilterProject)
    if (ganttFilterAssignee !== 'all') r = r.filter(t => t.assignee === ganttFilterAssignee)
    r.sort((a, b) => {
      let va: any, vb: any
      if (ganttSortKey === 'start') { va = a.startDate || ''; vb = b.startDate || '' }
      else if (ganttSortKey === 'assignee') { va = a.assignee; vb = b.assignee }
      else if (ganttSortKey === 'priority') { va = PRI_RANK[a.priority] ?? 9; vb = PRI_RANK[b.priority] ?? 9 }
      else if (ganttSortKey === 'project') { va = getProjectName(a.projectId) || ''; vb = getProjectName(b.projectId) || '' }
      if (typeof va === 'number' && typeof vb === 'number') return ganttSortDir === 'asc' ? va - vb : vb - va
      return ganttSortDir === 'asc' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va))
    })
    return r
  }, [todos, ganttFilterProject, ganttFilterAssignee, ganttSortKey, ganttSortDir])
  const ganttRange = useMemo(() => {
    if (!ganttTodos.length) return { min: today, max: today, days: 1 }
    const starts = ganttTodos.map(t => t.startDate!).filter(Boolean)
    const ends = ganttTodos.map(t => todoEndDate(t) || t.startDate!).filter(Boolean) as string[]
    const all = [...starts, ...ends]
    let min = all.reduce((a, b) => a < b ? a : b, all[0])
    let max = all.reduce((a, b) => a > b ? a : b, all[0])
    const dMin = new Date(min); dMin.setDate(1); min = dMin.toISOString().split('T')[0]
    const dMax = new Date(max); dMax.setMonth(dMax.getMonth() + 1, 1); max = dMax.toISOString().split('T')[0]
    const days = Math.max(Math.ceil((dMax.getTime() - dMin.getTime()) / 86400000), 14)
    return { min, max, days }
  }, [ganttTodos, today])
  const ganttOffset = (date: string) => {
    const d1 = new Date(ganttRange.min); const d2 = new Date(date)
    return Math.max(0, Math.ceil((d2.getTime() - d1.getTime()) / 86400000))
  }
  const hasOverlap = (dep: Todo, dependent: Todo) => {
    if (!dep.startDate || !dependent.startDate) return false
    const depEnd = todoEndDate(dep)
    if (!depEnd) return false
    return depEnd >= dependent.startDate
  }

  const projectTodos = (pid: string) => todos.filter(t => t.projectId === pid)
  const projectBlockers = (pid: string) => blockers.filter(b => b.projectId === pid)

  if (loading) return <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--syn-bg)' }}><div className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Lade Daten...</div></div>
  if (error && todos.length === 0) return <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--syn-bg)' }}><div className="text-sm" style={{ color: 'var(--syn-danger)' }}>Fehler: {error}</div></div>

  const navSections: { label: string; items: { key: Page; label: string; icon: string; count?: number }[] }[] = [
    { label: 'HEUTE', items: [
      { key: 'uebersicht', label: 'Command Center', icon: '⬡' },
      { key: 'sitzungen', label: 'Meetings', icon: '☰', count: meetings.length },
      { key: 'aktionen', label: 'Aktionen', icon: '✓', count: todos.filter(t => t.status !== 'done').length + blockers.filter(b => b.status === 'active').length },
    ]},
    { label: 'ARBEIT', items: [
      { key: 'projekte', label: 'Projekte', icon: '◈', count: projects.length },
    ]},
    { label: 'INTELLIGENZ', items: [
      { key: 'ki', label: 'AI-Suche', icon: '◉' },
      { key: 'textsuche', label: 'Textsuche', icon: '⌕' },
      { key: 'protokoll', label: 'Aktivität', icon: '⏱', count: filteredLog.length },
    ]},
  ]

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--syn-bg)', color: 'var(--syn-text)' }}>
      {/* ═══ SIDEBAR ═══ */}
      <aside className={`${sidebarCollapsed ? 'w-14' : 'w-52'} glass-sidebar flex flex-col shrink-0 transition-all duration-200 sticky top-0 h-screen border-r border-[var(--syn-line)] overflow-hidden`}>
        <div className={`flex items-center ${sidebarCollapsed ? 'justify-center px-2' : 'px-4'} h-14 border-b border-[var(--syn-line)]`}>
          <div className="w-7 h-7 rounded-md flex items-center justify-center shrink-0" style={{ background: 'var(--syn-accent)' }}>
            <svg width="16" height="16" viewBox="0 0 18 18" fill="none"><path d="M9 1L16 5V13L9 17L2 13V5Z" stroke="white" strokeWidth="1.5" fill="none"/><circle cx="9" cy="9" r="2.5" fill="white"/></svg>
          </div>
          {!sidebarCollapsed && <span className="ml-3 font-semibold text-sm tracking-tight" style={{ color: 'var(--syn-text)' }}>Meeting OS</span>}
        </div>
        <nav className="flex-1 py-3 px-2 overflow-y-auto">
          {navSections.map((section, si) => (
            <div key={si} className={si > 0 ? 'mt-4' : ''}>
              {!sidebarCollapsed && <div className="px-3 mb-1.5 text-[10px] font-semibold tracking-widest" style={{ color: 'var(--syn-text-faint)' }}>{section.label}</div>}
              {sidebarCollapsed && si > 0 && <div className="mx-2 my-2 border-t border-[var(--syn-line)]" />}
              <div className="space-y-0.5">
                {section.items.map(n => (
                  <button key={n.key} onClick={() => setPage(n.key)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${page === n.key ? 'bg-[var(--syn-accent-soft)] text-[var(--syn-accent)]' : 'hover:bg-[var(--syn-hover)]'}`}
                    style={page !== n.key ? { color: 'var(--syn-text-muted)' } : {}}>
                    <span className="text-base w-5 text-center shrink-0">{n.icon}</span>
                    {!sidebarCollapsed && <><span className="flex-1 text-left whitespace-nowrap">{n.label}</span>{n.count != null && n.count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded-full whitespace-nowrap" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>{n.count}</span>}</>}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="border-t border-[var(--syn-line)] py-3 px-2 space-y-1">
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm hover:bg-[var(--syn-hover)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>
            <span className="text-base w-5 text-center shrink-0">{sidebarCollapsed ? '❯' : '❮'}</span>{!sidebarCollapsed && <span className="whitespace-nowrap">Einklappen</span>}
          </button>
          <button onClick={onLogout} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm hover:bg-[var(--syn-hover)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>
            <span className="text-base w-5 text-center shrink-0">{'⏻'}</span>{!sidebarCollapsed && <span className="whitespace-nowrap">Abmelden</span>}
          </button>
        </div>
      </aside>

      {/* ═══ MAIN ═══ */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="glass-header border-b border-[var(--syn-line)] h-14 flex items-center px-6 gap-4 shrink-0 sticky top-0 z-20">
          <div ref={searchRef} className="relative">
            <Input placeholder="Suche überall..." value={globalSearch} onChange={e => { setGlobalSearch(e.target.value); setSearchFocused(true) }} onFocus={() => setSearchFocused(true)} onKeyDown={e => { if (e.key === 'Enter' && globalSearch.trim()) { setSearchFocused(false); setPage('textsuche' as any) } if (e.key === 'Escape') setSearchFocused(false) }} className="h-8 text-sm w-72 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
            {searchFocused && globalSearch.trim() && (searchResults.meetings.length > 0 || searchResults.todos.length > 0 || searchResults.blockers.length > 0) && (
              <div className="absolute top-full left-0 mt-1 w-96 glass-card rounded-xl border border-[var(--syn-line)] shadow-xl z-50 overflow-hidden max-h-[70vh] overflow-y-auto">
                {searchResults.meetings.length > 0 && <div>
                  <div className="px-3 py-2 text-[10px] font-semibold tracking-widest uppercase" style={{ color: 'var(--syn-text-faint)', background: 'var(--syn-surface-2)' }}>Meetings ({searchResults.meetings.length})</div>
                  {searchResults.meetings.map(m => (
                    <button key={m.id} onClick={() => { setSearchFocused(false); setViewMeeting(m) }} className="w-full text-left px-3 py-2 text-sm hover:bg-[var(--syn-hover)] transition-colors flex items-center gap-2">
                      <span className="text-xs shrink-0">☰</span><span className="truncate">{m.title}</span><span className="text-[10px] ml-auto shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{m.date}</span>
                    </button>
                  ))}
                </div>}
                {searchResults.todos.length > 0 && <div>
                  <div className="px-3 py-2 text-[10px] font-semibold tracking-widest uppercase" style={{ color: 'var(--syn-text-faint)', background: 'var(--syn-surface-2)' }}>Todos ({searchResults.todos.length})</div>
                  {searchResults.todos.map(t => (
                    <button key={t.id} onClick={() => { setSearchFocused(false); setViewTodo(t) }} className="w-full text-left px-3 py-2 text-sm hover:bg-[var(--syn-hover)] transition-colors flex items-center gap-2">
                      <span className="text-xs shrink-0">✓</span><span className="truncate">{t.title}</span><Badge className={`text-[9px] shrink-0 ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]}</Badge>
                    </button>
                  ))}
                </div>}
                {searchResults.blockers.length > 0 && <div>
                  <div className="px-3 py-2 text-[10px] font-semibold tracking-widest uppercase" style={{ color: 'var(--syn-text-faint)', background: 'var(--syn-surface-2)' }}>Blocker ({searchResults.blockers.length})</div>
                  {searchResults.blockers.map(b => (
                    <button key={b.id} onClick={() => { setSearchFocused(false); setViewBlocker(b) }} className="w-full text-left px-3 py-2 text-sm hover:bg-[var(--syn-hover)] transition-colors flex items-center gap-2">
                      <span className="text-xs shrink-0">⚠</span><span className="truncate">{b.title}</span><Badge className={`text-[9px] shrink-0 ${ST_STYLE[b.status]}`}>{ST_LABEL[b.status]}</Badge>
                    </button>
                  ))}
                </div>}
                <button onClick={() => { setSearchFocused(false); setPage('textsuche' as any) }} className="w-full px-3 py-2 text-xs text-center hover:bg-[var(--syn-hover)] transition-colors border-t border-[var(--syn-line)]" style={{ color: 'var(--syn-accent)' }}>
                  Alle Ergebnisse anzeigen →
                </button>
              </div>
            )}
          </div>
          <div className="flex-1" />
          {error && <span className="text-xs text-[var(--syn-danger)]">{error}</span>}
          <Button size="sm" variant="outline" onClick={handleToggleNightly} className={`text-xs border-[var(--syn-line)] ${nightlyActive ? 'text-[var(--syn-text-muted)]' : 'text-[var(--syn-text-faint)]'}`}>{nightlyActive ? '☾ An' : '☾ Aus'}</Button>
          <Button size="sm" variant="outline" onClick={handleAblegen} className="text-xs border-[var(--syn-line)] text-[var(--syn-text-muted)]">{'↻'} Neu laden</Button>
          <Button size="sm" onClick={handleRefresh} disabled={refreshing} className="bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white text-xs">{refreshing ? 'Make läuft...' : 'Aktualisieren'}</Button>
          <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--syn-hover)] transition-colors text-sm" title="Theme wechseln">{theme === 'dark' ? '☀' : '☾'}</button>
        </header>

        <main className="flex-1 p-6 overflow-auto">

          {/* ═══ COMMAND CENTER / ÜBERSICHT ═══ */}
          {page === 'uebersicht' && (() => {
            const reviewQueue = meetings.slice(0, 5)
            const activeBlockersList = blockers.filter(b => b.status === 'active')
            const recentDec = meetings.flatMap(m => m.keyDecisions.map(d => ({ text: d, meetingTitle: m.title, meetingDate: m.date, meetingId: m.id }))).slice(0, 8)
            const now = new Date()
            const dayNames = ['Sonntag','Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag']
            const monthNames = ['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember']
            const kw = (() => { const d = new Date(now); d.setHours(0,0,0,0); d.setDate(d.getDate()+3-(d.getDay()+6)%7); const w1 = new Date(d.getFullYear(),0,4); return 1+Math.round(((d.getTime()-w1.getTime())/86400000-3+(w1.getDay()+6)%7)/7) })()
            const greeting = now.getHours() < 12 ? 'Guten Morgen' : now.getHours() < 18 ? 'Guten Tag' : 'Guten Abend'

            return (
              <div className="space-y-6">
                {/* Page Head + Stats */}
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-[11px] font-medium tracking-widest uppercase" style={{ color: 'var(--syn-text-faint)' }}>
                      {dayNames[now.getDay()]} · {now.getDate()}. {monthNames[now.getMonth()]} · KW {kw}
                    </div>
                    <h1 className="text-2xl font-semibold mt-1" style={{ color: 'var(--syn-text)' }}>{greeting}, Gleb.</h1>
                  </div>
                  <div className="glass-card rounded-xl border border-[var(--syn-line)] px-6 py-3 flex items-center gap-6 shrink-0">
                    <div className="text-center"><div className="text-xl font-bold" style={{ color: 'var(--syn-accent)' }}>{meetings.length}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Meetings</div></div>
                    <div className="w-px h-8" style={{ background: 'var(--syn-line)' }} />
                    <div className="text-center"><div className="text-xl font-bold" style={{ color: 'var(--syn-warn)' }}>{todos.filter(t => t.status !== 'done').length}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Offene Todos</div></div>
                    <div className="w-px h-8" style={{ background: 'var(--syn-line)' }} />
                    <div className="text-center"><div className="text-xl font-bold" style={{ color: 'var(--syn-danger)' }}>{activeBlockersList.length}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Aktive Blocker</div></div>
                  </div>
                </div>

                {/* AI Prompt */}
                <div className="glass-card rounded-xl border border-[var(--syn-line)] p-5 space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: 'var(--syn-accent-soft)', color: 'var(--syn-accent)' }}>✦ AI</span>
                    <span className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Stelle eine Frage über deine Meetings, Projekte oder Aufgaben.</span>
                    <span className="flex-1" />
                    <span className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Antwort mit Quellen</span>
                  </div>
                  <Textarea
                    placeholder='Frage stellen...'
                    className="text-sm bg-[var(--syn-surface-2)] border-[var(--syn-line)] min-h-[56px] resize-none"
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (chatInput.trim()) { const q = chatInput.trim(); setPage('ki'); setTimeout(() => handleChat(q), 200) } } }}
                  />
                  <div className="flex items-center flex-wrap gap-2">
                    {['Welche Todos sind diese Woche fällig?', 'Fasse die letzten 3 Meetings zusammen', 'Welche Blocker sind gerade aktiv?'].map(q => (
                      <button key={q} onClick={() => { setPage('ki'); setTimeout(() => handleChat(q), 200) }} className="text-[11px] px-3 py-1.5 rounded-lg border transition-colors hover:bg-[var(--syn-hover)]" style={{ borderColor: 'var(--syn-line)', color: 'var(--syn-text-muted)' }}>{q}</button>
                    ))}
                    <span className="flex-1" />
                    <Button size="sm" onClick={() => { if (chatInput.trim()) { const q = chatInput.trim(); setPage('ki'); setTimeout(() => handleChat(q), 200) } }} className="bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white text-xs gap-1.5">
                      → Fragen
                    </Button>
                  </div>
                </div>

                {/* 2x2 Grid: left 1/3 (Todos+Blocker), right 2/3 (Meetings+Entscheidungen), rows equal height */}
                <div className="grid grid-cols-[1fr_2fr] grid-rows-[1fr_1fr] gap-5" style={{ gridAutoRows: '1fr' }}>
                  {/* Top-left: Offene Todos */}
                  <div className="glass-card rounded-xl border border-[var(--syn-line)] overflow-hidden flex flex-col">
                    <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--syn-line)] shrink-0">
                      <div className="flex items-center gap-2 text-sm font-semibold"><span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-warn)' }} /> Offene Todos</div>
                      <button onClick={() => { setActionTab('todos'); setPage('aktionen'); window.scrollTo(0, 0) }} className="text-[11px] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>Alle Todos →</button>
                    </div>
                    <div className="divide-y divide-[var(--syn-line)] flex-1 overflow-y-auto">
                      {todos.filter(t => t.status !== 'done').length === 0 && <div className="px-5 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine offenen Todos.</div>}
                      {todos.filter(t => t.status !== 'done').sort((a, b) => (PRI_RANK[a.priority] ?? 9) - (PRI_RANK[b.priority] ?? 9)).slice(0, 10).map(t => (
                        <div key={t.id} className="px-4 py-2.5 flex items-center gap-2.5 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer" onClick={() => setViewTodo(t)}>
                          <button onClick={(e) => { e.stopPropagation(); handleQuickStatusToggle(t) }} className="w-4 h-4 rounded border shrink-0 flex items-center justify-center transition-colors hover:border-[var(--syn-accent)] hover:bg-[var(--syn-accent-soft)]" style={{ borderColor: 'var(--syn-line)' }} />
                          <div className="flex-1 min-w-0 text-sm truncate">{t.title}</div>
                          <Badge className={`text-[8px] shrink-0 ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]?.charAt(0)}</Badge>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Top-right: Letzte Meetings */}
                  <div className="glass-card rounded-xl border border-[var(--syn-line)] overflow-hidden flex flex-col">
                    <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--syn-line)] shrink-0">
                      <div className="flex items-center gap-2 text-sm font-semibold"><span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-accent)' }} /> Letzte Meetings</div>
                      <button onClick={() => setPage('sitzungen')} className="text-[11px] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>Alle Meetings →</button>
                    </div>
                    <div className="divide-y divide-[var(--syn-line)] flex-1 overflow-y-auto">
                      {reviewQueue.length === 0 && <div className="px-5 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Meetings vorhanden.</div>}
                      {reviewQueue.slice(0, 5).map(m => (
                        <div key={m.id} className="px-5 py-3 flex items-start gap-3 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer" onClick={() => setViewMeeting(m)}>
                          <span className="w-2 h-2 mt-1.5 rounded-full shrink-0" style={{ background: 'var(--syn-accent)' }} />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate">{m.title}</div>
                            <div className="flex items-center gap-2 mt-0.5 text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>
                              <span>{m.date}</span>
                              <span>{m.participants.slice(0, 3).join(', ')}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Bottom-left: Aktive Blocker */}
                  <div className="glass-card rounded-xl border border-[var(--syn-line)] overflow-hidden flex flex-col">
                    <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--syn-line)] shrink-0">
                      <div className="flex items-center gap-2 text-sm font-semibold"><span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-danger)' }} /> Aktive Blocker</div>
                      <button onClick={() => { setActionTab('blocker'); setPage('aktionen'); window.scrollTo(0, 0) }} className="text-[11px] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>Alle Blocker →</button>
                    </div>
                    <div className="divide-y divide-[var(--syn-line)] flex-1 overflow-y-auto">
                      {activeBlockersList.length === 0 && <div className="px-5 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine aktiven Blocker.</div>}
                      {activeBlockersList.slice(0, 10).map(b => (
                        <div key={b.id} className="px-4 py-2.5 flex items-center gap-2.5 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer" onClick={() => setViewBlocker(b)}>
                          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: 'var(--syn-danger)' }} />
                          <div className="flex-1 min-w-0 text-sm truncate">{b.title}</div>
                          <span className="text-[10px] shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{b.reportedBy}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Bottom-right: Letzte Entscheidungen */}
                  <div className="glass-card rounded-xl border border-[var(--syn-line)] overflow-hidden flex flex-col">
                    <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--syn-line)] shrink-0">
                      <div className="flex items-center gap-2 text-sm font-semibold"><span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-info)' }} /> Letzte Entscheidungen</div>
                      <button onClick={() => setPage('protokoll')} className="text-[11px] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>Audit-Trail →</button>
                    </div>
                    <div className="divide-y divide-[var(--syn-line)] flex-1 overflow-y-auto">
                      {recentDec.length === 0 && <div className="px-5 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Entscheidungen.</div>}
                      {recentDec.map((d, i) => (
                        <div key={i} className="px-5 py-3 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer" onClick={() => { const m = meetings.find(mt => mt.id === d.meetingId); if (m) setViewMeeting(m) }}>
                          <div className="flex items-center gap-2 text-[11px] mb-1" style={{ color: 'var(--syn-text-faint)' }}>
                            <span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-accent)' }} />
                            {d.meetingDate}
                            <span className="px-1.5 py-0.5 rounded text-[10px]" style={{ background: 'var(--syn-accent-soft)', color: 'var(--syn-accent)' }}>
                              {d.meetingTitle}
                            </span>
                          </div>
                          <div className="text-sm font-medium" style={{ color: 'var(--syn-text)' }}>{d.text}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )
          })()}

          {/* ═══ SITZUNGEN ═══ */}
          {page === 'sitzungen' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h2 className="text-base font-semibold">Meetings</h2>
                <div className="flex items-center gap-2">
                  <Input placeholder="Suche..." value={noteSearch} onChange={e => setNoteSearch(e.target.value)} className="h-8 text-xs w-[180px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                  <Select value={noteFilterParticipant} onValueChange={setNoteFilterParticipant}><SelectTrigger className="h-8 text-xs w-[160px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Teilnehmer</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                  <Input type="date" value={noteFilterDateFrom} onChange={e => setNoteFilterDateFrom(e.target.value)} className="h-8 text-xs w-[140px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" placeholder="Von" />
                  <Input type="date" value={noteFilterDateTo} onChange={e => setNoteFilterDateTo(e.target.value)} className="h-8 text-xs w-[140px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" placeholder="Bis" />
                  {(noteFilterDateFrom || noteFilterDateTo) && <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => { setNoteFilterDateFrom(''); setNoteFilterDateTo('') }}>{'✕'}</Button>}
                </div>
              </div>
              <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                <SH label="Datum" field="date" sort={noteSort} onSort={noteSort.toggle} className="w-[110px]" />
                <SH label="Titel" field="title" sort={noteSort} onSort={noteSort.toggle} />
                <TableHead className="w-[200px] text-xs">Teilnehmer</TableHead>
                <TableHead className="w-[200px] text-xs">Themen</TableHead>
                <TableHead className="w-[80px] text-xs">Entsch.</TableHead>
                <TableHead className="w-[80px]"></TableHead>
              </TableRow></TableHeader><TableBody>
                {filteredNotes.map(m => (
                  <TableRow key={m.id} className="text-sm cursor-pointer hover:bg-[var(--syn-hover)] border-[var(--syn-line)]" onClick={() => setViewMeeting(m)}>
                    <TableCell className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>{m.date}</TableCell>
                    <TableCell className="font-medium">{m.title}</TableCell>
                    <TableCell><div className="flex flex-wrap gap-1">{m.participants.slice(0, 3).map((p, i) => <span key={i} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>{p}</span>)}{m.participants.length > 3 && <span className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>+{m.participants.length - 3}</span>}</div></TableCell>
                    <TableCell><div className="flex flex-wrap gap-1">{m.topics.slice(0, 2).map((t, i) => <Badge key={i} variant="outline" className="text-[9px] border-[var(--syn-line)]">{t}</Badge>)}{m.topics.length > 2 && <span className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>+{m.topics.length - 2}</span>}</div></TableCell>
                    <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{m.keyDecisions.length > 0 ? <span className="font-medium">{m.keyDecisions.length}</span> : '—'}</TableCell>
                    <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1 justify-end"><button onClick={() => setEditMeeting({...m})} className="text-xs hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => handleDeleteMeeting(m)} className="text-xs hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button></div></TableCell>
                  </TableRow>
                ))}
                {filteredNotes.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine Meetings</TableCell></TableRow>}
              </TableBody></Table></CardContent></Card>
              {meetings.length > 0 && <p className="text-xs text-center" style={{ color: 'var(--syn-text-faint)' }}>{filteredNotes.length} von {meetings.length} Meetings</p>}
            </div>
          )}

          {/* ═══ AKTIONEN (Tabs: Todos / Blocker / Open Items) ═══ */}
          {page === 'aktionen' && (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <h2 className="text-base font-semibold">Aktionen</h2>
                <div className="flex border border-[var(--syn-line)] rounded-lg overflow-hidden">
                  {([['todos', 'Todos', todos.filter(t => t.status !== 'done').length], ['blocker', 'Blocker', blockers.filter(b => b.status === 'active').length], ['open', 'Open Items', openItems.filter(o => o.status !== 'closed').length]] as [ActionTab, string, number][]).map(([k, l, c]) => (
                    <button key={k} onClick={() => setActionTab(k)} className={`px-4 py-1.5 text-xs transition-colors ${actionTab === k ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`} style={actionTab !== k ? { color: 'var(--syn-text-muted)' } : {}}>
                      {l} {c > 0 && <span className="ml-1 opacity-70">({c})</span>}
                    </button>
                  ))}
                </div>
              </div>

              {/* TODOS TAB */}
              {actionTab === 'todos' && (
                <section>
                  <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => setEditTodo({ id: '__new__', assignee: 'Nicht zugeordnet', title: '', description: '', status: 'open', priority: 'medium', dueDate: null, startDate: null, durationDays: 1, dependsOn: [], meetingId: null, projectId: null, createdAt: '' })}>+ Neu</Button>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Input placeholder="Suche..." value={todoSearch} onChange={e => setTodoSearch(e.target.value)} className="h-8 text-xs w-[150px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                      <Select value={todoFilterAssignee} onValueChange={setTodoFilterAssignee}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Mitglieder</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                      <Select value={todoFilterDue} onValueChange={setTodoFilterDue}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Termine</SelectItem><SelectItem value="overdue">Überfällig</SelectItem><SelectItem value="this_week">Diese Woche</SelectItem><SelectItem value="no_date">Ohne Datum</SelectItem></SelectContent></Select>
                      <Select value={todoFilterStatus} onValueChange={setTodoFilterStatus}><SelectTrigger className="h-8 text-xs w-[120px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="open">Offen</SelectItem><SelectItem value="in_progress">In Arbeit</SelectItem><SelectItem value="done">Erledigt</SelectItem></SelectContent></Select>
                      {projects.length > 0 && <Select value={todoFilterProject} onValueChange={setTodoFilterProject}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Projekte</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>}
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                    <TableHead className="w-10"></TableHead>
                    <SH label="Aufgabe" field="title" sort={todoSort} onSort={todoSort.toggle} />
                    <SH label="Zuständig" field="assignee" sort={todoSort} onSort={todoSort.toggle} className="w-[140px]" />
                    <SH label="Priorität" field="priority" sort={todoSort} onSort={todoSort.toggle} className="w-[110px]" />
                    <SH label="Fällig" field="dueDate" sort={todoSort} onSort={todoSort.toggle} className="w-[110px]" />
                    <SH label="Status" field="status" sort={todoSort} onSort={todoSort.toggle} className="w-[110px]" />
                    <TableHead className="w-[160px] text-xs">Quelle</TableHead>
                    {projects.length > 0 && <TableHead className="w-[120px] text-xs">Projekt</TableHead>}
                    <TableHead className="w-[80px]"></TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredTodos.map(t => { const overdue = t.dueDate && t.dueDate < today && t.status !== 'done'; return (
                      <TableRow key={t.id} className={`text-sm border-[var(--syn-line)] ${t.status === 'done' ? 'opacity-40' : ''} hover:bg-[var(--syn-hover)]`}>
                        <TableCell className="pr-0"><button onClick={() => cycleTodo(t)} className={`w-5 h-5 rounded border-2 flex items-center justify-center text-xs transition-colors ${t.status === 'done' ? 'bg-[var(--syn-ok)] border-[var(--syn-ok)] text-white' : t.status === 'in_progress' ? 'border-[var(--syn-info)] bg-[var(--syn-info-soft)]' : 'border-[var(--syn-line-strong)] hover:border-[var(--syn-accent)]'}`}>{t.status === 'done' ? '✓' : t.status === 'in_progress' ? '›' : ''}</button></TableCell>
                        <TableCell><button onClick={() => setViewTodo(t)} className={`text-left hover:text-[var(--syn-accent)] ${t.status === 'done' ? 'line-through' : ''}`}>{t.title}</button>{t.description && <div className="text-xs truncate max-w-sm" style={{ color: 'var(--syn-text-faint)' }}>{t.description}</div>}</TableCell>
                        <TableCell><div className="flex items-center gap-1.5"><Av name={t.assignee} /><span className="text-xs">{t.assignee}</span></div></TableCell>
                        <TableCell><Badge className={`text-[10px] ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority] || t.priority}</Badge></TableCell>
                        <TableCell className={`text-xs ${overdue ? 'text-[var(--syn-danger)] font-bold' : ''}`} style={!overdue ? { color: 'var(--syn-text-muted)' } : {}}>{t.dueDate || '—'}{overdue && ' ❗'}</TableCell>
                        <TableCell><Badge className={`text-[10px] ${ST_STYLE[t.status]}`}>{ST_LABEL[t.status]}</Badge></TableCell>
                        <TableCell><SourceChip meeting={getMeeting(t.meetingId) || null} onClick={() => { const m = getMeeting(t.meetingId); if (m) setViewMeeting(m) }} /></TableCell>
                        {projects.length > 0 && <TableCell className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>{getProjectName(t.projectId) || '—'}</TableCell>}
                        <TableCell><div className="flex gap-1 justify-end"><button onClick={() => setEditTodo({...t})} className="text-xs hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => handleDeleteTodo(t)} className="text-xs hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button></div></TableCell>
                      </TableRow>
                    )})}
                    {filteredTodos.length === 0 && <TableRow><TableCell colSpan={9} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine Todos</TableCell></TableRow>}
                  </TableBody></Table></CardContent></Card>
                </section>
              )}

              {/* BLOCKER TAB */}
              {actionTab === 'blocker' && (
                <section>
                  <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => setEditBlocker({ id: '__new__', reportedBy: 'Nicht zugeordnet', title: '', description: '', status: 'active', meetingId: null, projectId: null, createdAt: '' })}>+ Neu</Button>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Input placeholder="Suche..." value={blockerSearch} onChange={e => setBlockerSearch(e.target.value)} className="h-8 text-xs w-[150px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                      <Select value={blockerFilterAssignee} onValueChange={setBlockerFilterAssignee}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Zuständige</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                      <Select value={blockerFilterStatus} onValueChange={setBlockerFilterStatus}><SelectTrigger className="h-8 text-xs w-[120px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="active">Aktiv</SelectItem><SelectItem value="resolved">Gelöst</SelectItem><SelectItem value="escalated">Eskaliert</SelectItem></SelectContent></Select>
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                    <SH label="Blocker" field="title" sort={blockerSort} onSort={blockerSort.toggle} />
                    <SH label="Zuständig" field="reportedBy" sort={blockerSort} onSort={blockerSort.toggle} className="w-[140px]" />
                    <SH label="Status" field="status" sort={blockerSort} onSort={blockerSort.toggle} className="w-[110px]" />
                    <TableHead className="w-[150px] text-xs">Quelle</TableHead>
                    <SH label="Erstellt" field="createdAt" sort={blockerSort} onSort={blockerSort.toggle} className="w-[100px]" />
                    <TableHead className="w-[150px]"></TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredBlockers.map(b => (
                      <TableRow key={b.id} className={`text-sm border-[var(--syn-line)] ${b.status !== 'active' ? 'opacity-50' : ''} hover:bg-[var(--syn-hover)]`}>
                        <TableCell><button onClick={() => setViewBlocker(b)} className="text-left font-medium hover:text-[var(--syn-accent)]">{b.title}</button><div className="text-xs truncate max-w-md" style={{ color: 'var(--syn-text-faint)' }}>{b.description}</div></TableCell>
                        <TableCell><div className="flex items-center gap-1.5"><Av name={b.reportedBy} /><span className="text-xs">{b.reportedBy}</span></div></TableCell>
                        <TableCell><Badge className={`text-[10px] ${ST_STYLE[b.status]}`}>{ST_LABEL[b.status]}</Badge></TableCell>
                        <TableCell><SourceChip meeting={getMeeting(b.meetingId) || null} onClick={() => { const m = getMeeting(b.meetingId); if (m) setViewMeeting(m) }} /></TableCell>
                        <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{b.createdAt}</TableCell>
                        <TableCell><div className="flex gap-1 items-center justify-end">{b.status === 'active' && <Button variant="outline" size="sm" className="text-xs h-7 border-[var(--syn-line)]" onClick={() => handleResolveBlocker(b)}>Lösen</Button>}<button onClick={() => setEditBlocker({...b})} className="text-xs hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => handleDeleteBlocker(b)} className="text-xs hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button></div></TableCell>
                      </TableRow>
                    ))}
                    {filteredBlockers.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine Blocker</TableCell></TableRow>}
                  </TableBody></Table></CardContent></Card>
                </section>
              )}

              {/* OPEN ITEMS TAB */}
              {actionTab === 'open' && (
                <section>
                  <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => setEditOpen({ id: '__new__', owner: 'Nicht zugeordnet', title: '', description: '', category: 'general', status: 'open', meetingId: null, projectId: null, createdAt: '' })}>+ Neu</Button>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Input placeholder="Suche..." value={openSearch} onChange={e => setOpenSearch(e.target.value)} className="h-8 text-xs w-[150px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                      <Select value={openFilterOwner} onValueChange={setOpenFilterOwner}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Zuständige</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                      <Select value={openFilterStatus} onValueChange={setOpenFilterStatus}><SelectTrigger className="h-8 text-xs w-[120px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="open">Offen</SelectItem><SelectItem value="watching">Beobachten</SelectItem><SelectItem value="closed">Geschlossen</SelectItem></SelectContent></Select>
                      <Select value={openFilterCategory} onValueChange={setOpenFilterCategory}><SelectTrigger className="h-8 text-xs w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Kategorien</SelectItem><SelectItem value="general">General</SelectItem><SelectItem value="risk">Risk</SelectItem><SelectItem value="opportunity">Opportunity</SelectItem><SelectItem value="question">Question</SelectItem><SelectItem value="follow_up">Follow-up</SelectItem></SelectContent></Select>
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                    <TableHead className="w-10"></TableHead>
                    <SH label="Item" field="title" sort={openSort} onSort={openSort.toggle} />
                    <SH label="Kategorie" field="category" sort={openSort} onSort={openSort.toggle} className="w-[120px]" />
                    <SH label="Zuständig" field="owner" sort={openSort} onSort={openSort.toggle} className="w-[140px]" />
                    <SH label="Status" field="status" sort={openSort} onSort={openSort.toggle} className="w-[110px]" />
                    <TableHead className="w-[150px] text-xs">Quelle</TableHead>
                    <SH label="Erstellt" field="createdAt" sort={openSort} onSort={openSort.toggle} className="w-[100px]" />
                    <TableHead className="w-[150px]"></TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredOpen.map(o => (
                      <TableRow key={o.id} className={`text-sm border-[var(--syn-line)] ${o.status === 'closed' ? 'opacity-40' : ''} hover:bg-[var(--syn-hover)]`}>
                        <TableCell className="text-center">{CAT_ICON[o.category] || '○'}</TableCell>
                        <TableCell><button onClick={() => setViewOpen(o)} className="text-left hover:text-[var(--syn-accent)]">{o.title}</button><div className="text-xs truncate max-w-sm" style={{ color: 'var(--syn-text-faint)' }}>{o.description}</div></TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-line)]">{o.category}</Badge></TableCell>
                        <TableCell><div className="flex items-center gap-1.5"><Av name={o.owner} /><span className="text-xs">{o.owner}</span></div></TableCell>
                        <TableCell><Badge className={`text-[10px] ${ST_STYLE[o.status]}`}>{ST_LABEL[o.status]}</Badge></TableCell>
                        <TableCell><SourceChip meeting={getMeeting(o.meetingId) || null} onClick={() => { const m = getMeeting(o.meetingId); if (m) setViewMeeting(m) }} /></TableCell>
                        <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{o.createdAt}</TableCell>
                        <TableCell><div className="flex gap-1 items-center justify-end">{o.status !== 'closed' && <Button variant="ghost" size="sm" className="text-xs h-7" onClick={() => handleCloseItem(o)}>Schließen</Button>}<button onClick={() => setEditOpen({...o})} className="text-xs hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => handleDeleteOpen(o)} className="text-xs hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button></div></TableCell>
                      </TableRow>
                    ))}
                    {filteredOpen.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine Open Items</TableCell></TableRow>}
                  </TableBody></Table></CardContent></Card>
                </section>
              )}
            </div>
          )}

          {/* ═══ PROJEKTE ═══ */}
          {page === 'projekte' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold">Projekte</h2>
                  <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => setEditProject({ id: '__new__', name: '', description: null, status: 'active', created_at: '', updated_at: '' } as DbProject)}>+ Neu</Button>
                </div>
                <div className="flex items-center gap-2">
                  <Input placeholder="Suche..." value={projectSearch} onChange={e => setProjectSearch(e.target.value)} className="h-8 text-xs w-[180px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                  <Select value={projectFilterStatus} onValueChange={setProjectFilterStatus}><SelectTrigger className="h-8 text-xs w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="active">Aktiv</SelectItem><SelectItem value="completed">Abgeschlossen</SelectItem><SelectItem value="on_hold">Pausiert</SelectItem></SelectContent></Select>
                  <div className="flex border border-[var(--syn-line)] rounded-lg overflow-hidden">
                    {(['table', 'kanban', 'gantt'] as ProjectView[]).map(v => (
                      <button key={v} onClick={() => setProjectView(v)} className={`px-3 py-1.5 text-xs transition-colors ${projectView === v ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`} style={projectView !== v ? { color: 'var(--syn-text-muted)' } : {}}>
                        {v === 'table' ? '▤ Tabelle' : v === 'kanban' ? '▥ Kanban' : '▰ Gantt'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* TABLE VIEW */}
              {projectView === 'table' && (
                <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                  <SH label="Projekt" field="name" sort={projectSort} onSort={projectSort.toggle} />
                  <SH label="Beschreibung" field="description" sort={projectSort} onSort={projectSort.toggle} />
                  <TableHead className="w-[80px] text-xs">Todos</TableHead>
                  <TableHead className="w-[80px] text-xs">Blocker</TableHead>
                  <SH label="Status" field="status" sort={projectSort} onSort={projectSort.toggle} className="w-[130px]" />
                  <TableHead className="w-[80px]"></TableHead>
                </TableRow></TableHeader><TableBody>
                  {filteredProjects.map(p => {
                    const pTodos = projectTodos(p.id); const pBlockers = projectBlockers(p.id)
                    return (
                    <TableRow key={p.id} className="text-sm cursor-pointer hover:bg-[var(--syn-hover)] border-[var(--syn-line)]" onClick={() => setViewProject(p)}>
                      <TableCell className="font-medium">{p.name}</TableCell>
                      <TableCell className="text-xs truncate" style={{ color: 'var(--syn-text-muted)' }}>{p.description || '—'}</TableCell>
                      <TableCell className="text-xs"><span className="font-medium">{pTodos.filter(t => t.status === 'done').length}</span><span style={{ color: 'var(--syn-text-faint)' }}>/{pTodos.length}</span></TableCell>
                      <TableCell className="text-xs">{pBlockers.filter(b => b.status === 'active').length > 0 ? <span className="font-bold text-[var(--syn-danger)]">{pBlockers.filter(b => b.status === 'active').length} aktiv</span> : <span style={{ color: 'var(--syn-text-faint)' }}>0</span>}</TableCell>
                      <TableCell><Badge className={`text-[10px] ${ST_STYLE[p.status] || ''}`}>{ST_LABEL[p.status] || p.status}</Badge></TableCell>
                      <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1 justify-end"><button onClick={() => setEditProject({...p})} className="text-xs hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => handleDeleteProject(p)} className="text-xs hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button></div></TableCell>
                    </TableRow>
                  )})}
                  {filteredProjects.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine Projekte</TableCell></TableRow>}
                </TableBody></Table></CardContent></Card>
              )}

              {/* KANBAN VIEW */}
              {projectView === 'kanban' && (
                <div className="space-y-3">
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-xs mr-1" style={{ color: 'var(--syn-text-muted)' }}>Anzeigen:</span>
                    {[['priority','Priorität'],['assignee','Zuständig'],['duration','Dauer'],['project','Projekt'],['dueDate','Fällig']].map(([k,l]) => (
                      <button key={k} onClick={() => toggleField(kanbanFields, setKanbanFields, k)} className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${kanbanFields.has(k) ? 'bg-[var(--syn-accent)] text-white border-[var(--syn-accent)]' : 'border-[var(--syn-line)]'}`} style={!kanbanFields.has(k) ? { color: 'var(--syn-text-faint)' } : {}}>{l}</button>
                    ))}
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    {kanbanColumns.map(status => (
                      <div key={status}
                        onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('!bg-[var(--syn-accent-soft)]') }}
                        onDragLeave={e => { e.currentTarget.classList.remove('!bg-[var(--syn-accent-soft)]') }}
                        onDrop={e => { e.preventDefault(); e.currentTarget.classList.remove('!bg-[var(--syn-accent-soft)]'); if (dragTodo) handleKanbanDrop(dragTodo, status) }}
                        className="rounded-xl border border-[var(--syn-line)] p-3 min-h-[300px] transition-colors" style={{ background: 'var(--syn-surface)' }}
                      >
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="text-sm font-semibold">{kanbanLabels[status]}</h3>
                          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>{todos.filter(t => t.status === status).length}</span>
                        </div>
                        <div className="space-y-2">
                          {todos.filter(t => t.status === status).map(t => (
                            <div key={t.id} draggable onDragStart={() => setDragTodo(t.id)} onDragEnd={() => setDragTodo(null)}
                              className={`glass-card border border-[var(--syn-line)] rounded-lg p-3 cursor-grab active:cursor-grabbing hover:border-[var(--syn-accent-line)] transition-colors group ${dragTodo === t.id ? 'opacity-50' : ''}`}
                            >
                              <button onClick={() => setViewTodo(t)} className="text-sm font-medium text-left hover:text-[var(--syn-accent)] w-full">{t.title}</button>
                              <div className="flex items-center gap-2 mt-2 flex-wrap">
                                {kanbanFields.has('priority') && <Badge className={`text-[9px] ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]}</Badge>}
                                {kanbanFields.has('assignee') && <div className="flex items-center gap-1"><Av name={t.assignee} /><span className="text-[10px]" style={{ color: 'var(--syn-text-muted)' }}>{t.assignee}</span></div>}
                                {kanbanFields.has('duration') && t.durationDays > 0 && <span className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>{t.durationDays}d</span>}
                              </div>
                              {kanbanFields.has('dueDate') && t.dueDate && <div className={`text-[10px] mt-1.5 ${t.dueDate < today && t.status !== 'done' ? 'text-[var(--syn-danger)] font-bold' : ''}`} style={!(t.dueDate < today && t.status !== 'done') ? { color: 'var(--syn-text-faint)' } : {}}>Fällig: {t.dueDate}</div>}
                              {kanbanFields.has('project') && t.projectId && <div className="text-[10px] mt-0.5" style={{ color: 'var(--syn-text-faint)' }}>{getProjectName(t.projectId)}</div>}
                              <div className="flex gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity"><button onClick={e => { e.stopPropagation(); setEditTodo({...t}) }} className="text-xs hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={e => { e.stopPropagation(); handleDeleteTodo(t) }} className="text-xs hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button></div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* GANTT VIEW */}
              {projectView === 'gantt' && (() => {
                const COL_W = ganttGranularity === 'month' ? 28 : ganttGranularity === 'quarter' ? 6 : 2
                const ROW_H = 32; const LABEL_W = 220
                const isWeekend = (d: Date) => d.getDay() === 0 || d.getDay() === 6
                const MONTH_NAMES = ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez']
                const handleGanttMouseDown = (e: React.MouseEvent, todoId: string, mode: 'move' | 'resize') => {
                  e.preventDefault(); e.stopPropagation()
                  const t = todos.find(x => x.id === todoId); if (!t || !t.startDate) return
                  ganttDragRef.current = { todoId, mode, startX: e.clientX, origStart: t.startDate, origDuration: t.durationDays }
                  const onMove = (ev: MouseEvent) => {
                    if (!ganttDragRef.current) return
                    const dx = ev.clientX - ganttDragRef.current.startX
                    const daysDelta = Math.round(dx / COL_W)
                    if (daysDelta === 0 && ganttDragRef.current.mode === 'move') return
                    setTodos(prev => prev.map(x => {
                      if (x.id !== todoId) return x
                      if (ganttDragRef.current!.mode === 'move') return { ...x, startDate: addDays(ganttDragRef.current!.origStart, daysDelta) }
                      else return { ...x, durationDays: Math.max(1, ganttDragRef.current!.origDuration + daysDelta) }
                    }))
                  }
                  const onUp = () => {
                    document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp)
                    if (!ganttDragRef.current) return
                    const t2 = todos.find(x => x.id === todoId)
                    if (t2) { updateTodoFull(t2.id, { start_date: t2.startDate, duration_days: t2.durationDays } as any).catch(() => {}) }
                    ganttDragRef.current = null
                  }
                  document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onUp)
                }
                const timelineDays: { date: Date; label: string; isWE: boolean }[] = []
                for (let i = 0; i < Math.min(ganttRange.days, 120); i++) {
                  const d = new Date(ganttRange.min); d.setDate(d.getDate() + i)
                  timelineDays.push({ date: d, label: String(d.getDate()), isWE: isWeekend(d) })
                }
                const monthGroups: { label: string; span: number }[] = []
                let prevMonth = -1
                timelineDays.forEach(td => {
                  const m = td.date.getMonth(); const y = td.date.getFullYear()
                  if (m !== prevMonth) { monthGroups.push({ label: `${MONTH_NAMES[m]} ${y}`, span: 1 }); prevMonth = m }
                  else { monthGroups[monthGroups.length - 1].span++ }
                })
                const totalW = timelineDays.length * COL_W

                return (
                <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-4">
                  {ganttTodos.length === 0 && todos.filter(t => t.startDate).length === 0 ? (
                    <div className="py-12 text-center text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Todos mit Startdatum. Bearbeite Todos und setze ein Startdatum und Dauer.</div>
                  ) : (<>
                    <div className="flex items-center gap-2 mb-3 flex-wrap">
                      <div className="flex border border-[var(--syn-line)] rounded-lg overflow-hidden mr-2">
                        {(['month','quarter','year'] as const).map(g => (
                          <button key={g} onClick={() => setGanttGranularity(g)} className={`px-2.5 py-1 text-[10px] transition-colors ${ganttGranularity === g ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`} style={ganttGranularity !== g ? { color: 'var(--syn-text-muted)' } : {}}>
                            {g === 'month' ? 'Monat' : g === 'quarter' ? 'Quartal' : 'Jahr'}
                          </button>
                        ))}
                      </div>
                      <Select value={ganttFilterProject} onValueChange={setGanttFilterProject}><SelectTrigger className="h-7 text-[10px] w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Projekte</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>
                      <Select value={ganttFilterAssignee} onValueChange={setGanttFilterAssignee}><SelectTrigger className="h-7 text-[10px] w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Zuständig</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                      <Select value={`${ganttSortKey}-${ganttSortDir}`} onValueChange={v => { const [k,d] = v.split('-') as [any,any]; setGanttSortKey(k); setGanttSortDir(d) }}><SelectTrigger className="h-7 text-[10px] w-[130px]"><SelectValue /></SelectTrigger><SelectContent>
                        <SelectItem value="start-asc">Start {'↑'}</SelectItem><SelectItem value="start-desc">Start {'↓'}</SelectItem>
                        <SelectItem value="assignee-asc">Zuständig {'↑'}</SelectItem><SelectItem value="assignee-desc">Zuständig {'↓'}</SelectItem>
                        <SelectItem value="priority-asc">Prio {'↑'}</SelectItem><SelectItem value="priority-desc">Prio {'↓'}</SelectItem>
                        <SelectItem value="project-asc">Projekt {'↑'}</SelectItem><SelectItem value="project-desc">Projekt {'↓'}</SelectItem>
                      </SelectContent></Select>
                      <div className="flex items-center gap-1 ml-2">
                        <span className="text-[10px]" style={{ color: 'var(--syn-text-muted)' }}>Balken:</span>
                        {[['assignee','Zuständig'],['duration','Dauer'],['project','Projekt']].map(([k,l]) => (
                          <button key={k} onClick={() => toggleField(ganttFields, setGanttFields, k)} className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${ganttFields.has(k) ? 'bg-[var(--syn-accent)] text-white border-[var(--syn-accent)]' : 'border-[var(--syn-line)]'}`} style={!ganttFields.has(k) ? { color: 'var(--syn-text-faint)' } : {}}>{l}</button>
                        ))}
                      </div>
                    </div>
                    <div className="overflow-x-auto border border-[var(--syn-line)] rounded-lg">
                      <div style={{ minWidth: `${LABEL_W + totalW}px` }} className="relative select-none">
                        <svg className="absolute" width="0" height="0"><defs>
                          <marker id="arrow" viewBox="0 0 5 5" refX="4" refY="2.5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L5,2.5 L0,5 Z" fill="var(--syn-text-faint)" /></marker>
                          <marker id="arrow-red" viewBox="0 0 5 5" refX="4" refY="2.5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L5,2.5 L0,5 Z" fill="var(--syn-danger)" /></marker>
                        </defs></svg>
                        <div className="flex border-b border-[var(--syn-line)]" style={{ background: 'var(--syn-surface-2)' }}>
                          <div className="shrink-0 border-r border-[var(--syn-line)]" style={{ width: LABEL_W, background: 'var(--syn-surface-3)' }} />
                          {monthGroups.map((mg, i) => (
                            <div key={i} className="text-[10px] font-semibold border-r border-[var(--syn-line)] flex items-center justify-center py-1" style={{ width: mg.span * COL_W, color: 'var(--syn-text-muted)' }}>{mg.label}</div>
                          ))}
                        </div>
                        <div className="flex border-b border-[var(--syn-line-strong)]" style={{ background: 'var(--syn-surface-2)' }}>
                          <div className="shrink-0 border-r border-[var(--syn-line)] text-[10px] flex items-center px-3 font-medium" style={{ width: LABEL_W, background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>Aufgabe</div>
                          {timelineDays.map((td, i) => {
                            let cellLabel = ''
                            if (ganttGranularity === 'month') cellLabel = td.label
                            else if (ganttGranularity === 'quarter') { if (td.date.getDate() === 1) cellLabel = `${td.date.getDate()}.${td.date.getMonth()+1}` }
                            else { if (td.date.getDate() === 1) cellLabel = MONTH_NAMES[td.date.getMonth()] }
                            return <div key={i} className={`text-[9px] text-center flex items-center justify-center border-r border-[var(--syn-line)] py-0.5`} style={{ width: COL_W, color: td.isWE && ganttGranularity === 'month' ? 'var(--syn-text-faint)' : 'var(--syn-text-muted)', background: td.isWE && ganttGranularity === 'month' ? 'var(--syn-surface-3)' : undefined }}>{cellLabel}</div>
                          })}
                        </div>
                        {ganttTodos.map((t) => {
                          const start = t.startDate!
                          const offsetDays = ganttOffset(start)
                          const duration = Math.max(t.durationDays, 1)
                          const endDate = addDays(start, duration - 1)
                          const barLabel = [ganttFields.has('assignee') ? t.assignee.split(' ')[0] : '', ganttFields.has('duration') ? `${duration}d` : '', ganttFields.has('project') && t.projectId ? getProjectName(t.projectId) : ''].filter(Boolean).join(' · ')
                          const deps = t.dependsOn.map(depId => todos.find(x => x.id === depId)).filter(Boolean) as Todo[]
                          return (
                            <div key={t.id} className="flex group" style={{ height: ROW_H }}>
                              <div className="shrink-0 border-r border-[var(--syn-line)] flex items-center gap-1 px-2" style={{ width: LABEL_W, background: 'var(--syn-surface)' }}>
                                <button onClick={() => setViewTodo(t)} className="text-xs hover:text-[var(--syn-accent)] truncate flex-1 text-left">{t.title}</button>
                                <span className="hidden group-hover:flex gap-0.5 shrink-0">
                                  <button onClick={() => setEditTodo({...t})} className="text-[10px] hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button>
                                  <button onClick={() => handleDeleteTodo(t)} className="text-[10px] hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button>
                                </span>
                              </div>
                              <div className="flex-1 relative" style={{ height: ROW_H }}>
                                {ganttGranularity === 'month' && timelineDays.map((td, i) => td.isWE ? <div key={i} className="absolute top-0 h-full" style={{ left: i * COL_W, width: COL_W, background: 'var(--syn-surface-2)', opacity: 0.5 }} /> : null)}
                                <div className="absolute top-0 left-0 right-0 h-full border-b border-[var(--syn-line)]" />
                                {(() => { const tOff = ganttOffset(today); return tOff >= 0 && tOff < timelineDays.length ? <div className="absolute top-0 h-full w-px z-10" style={{ left: tOff * COL_W + COL_W / 2, background: 'var(--syn-danger)' }} /> : null })()}
                                <div
                                  className="absolute top-1.5 rounded cursor-grab active:cursor-grabbing"
                                  style={{ left: offsetDays * COL_W, width: Math.max(duration * COL_W, 8), height: ROW_H - 12, background: t.status === 'done' ? 'var(--syn-ok)' : t.status === 'in_progress' ? 'var(--syn-info)' : 'var(--syn-accent)' }}
                                  title={`${t.title} (${start} → ${endDate}, ${duration}d)`}
                                  onMouseDown={e => handleGanttMouseDown(e, t.id, 'move')}
                                >
                                  <span className="text-[8px] text-white px-1.5 truncate block" style={{ lineHeight: `${ROW_H - 12}px` }}>{barLabel}</span>
                                  <div className="absolute right-0 top-0 w-2 h-full cursor-ew-resize hover:bg-white/20 rounded-r" onMouseDown={e => handleGanttMouseDown(e, t.id, 'resize')} />
                                </div>
                                {deps.map(dep => {
                                  const depEnd = todoEndDate(dep)
                                  if (!depEnd || !dep.startDate) return null
                                  const depEndOff = (ganttOffset(depEnd) + 1) * COL_W
                                  const thisStartOff = offsetDays * COL_W
                                  const overlap = hasOverlap(dep, t)
                                  const y = ROW_H / 2
                                  return <svg key={dep.id} className="absolute top-0 pointer-events-none" style={{ left: 0, width: '100%', height: ROW_H, overflow: 'visible' }}>
                                    <line x1={depEndOff} y1={y} x2={thisStartOff - 2} y2={y} stroke={overlap ? 'var(--syn-danger)' : 'var(--syn-line-strong)'} strokeWidth="0.75" markerEnd={overlap ? 'url(#arrow-red)' : 'url(#arrow)'} />
                                  </svg>
                                })}
                              </div>
                            </div>
                          )
                        })}
                        {ganttTodos.length === 0 && <div className="py-8 text-center text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Todos mit Startdatum für diesen Filter.</div>}
                      </div>
                    </div>
                    <p className="text-[10px] mt-2 text-center" style={{ color: 'var(--syn-text-faint)' }}>{ganttTodos.length} Aufgaben — Balken verschieben oder am rechten Rand ziehen um Dauer zu ändern</p>
                  </>)}
                </CardContent></Card>)
              })()}
            </div>
          )}

          {/* ═══ PROTOKOLL ═══ */}
          {page === 'protokoll' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <h2 className="text-base font-semibold">Protokoll</h2>
                  <p className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Endgültige Statusänderungen: Erledigt, Beschlossen, Gelöst, Geschlossen</p>
                </div>
                <div className="flex items-center gap-2">
                  <Input placeholder="Suche..." value={logSearch} onChange={e => setLogSearch(e.target.value)} className="h-8 text-xs w-[180px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                  <Select value={logFilterType} onValueChange={setLogFilterType}><SelectTrigger className="h-8 text-xs w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Typen</SelectItem><SelectItem value="todo">Todos</SelectItem><SelectItem value="blocker">Blocker</SelectItem><SelectItem value="open_item">Open Items</SelectItem><SelectItem value="meeting">Meetings</SelectItem><SelectItem value="decision">Entscheidung</SelectItem></SelectContent></Select>
                </div>
              </div>
              <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0">
                {filteredLog.length > 0 ? (
                  <Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                    <SH label="Zeitpunkt" field="timestamp" sort={logSort} onSort={logSort.toggle} className="w-[160px]" />
                    <SH label="Typ" field="entityType" sort={logSort} onSort={logSort.toggle} className="w-[110px]" />
                    <SH label="Element" field="entityTitle" sort={logSort} onSort={logSort.toggle} />
                    <SH label="Aktion" field="action" sort={logSort} onSort={logSort.toggle} className="w-[130px]" />
                    <TableHead className="w-[100px] text-xs">Vorher</TableHead>
                    <TableHead className="w-[120px] text-xs">Nachher</TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredLog.map(a => (
                      <TableRow key={a.id} className="text-sm hover:bg-[var(--syn-hover)] border-[var(--syn-line)]">
                        <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{new Date(a.timestamp).toLocaleString('de-DE')}</TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-line)]">{TYPE_LABEL[a.entityType] || a.entityType}</Badge></TableCell>
                        <TableCell><button onClick={() => openSourceEntity(a.entityType, a.entityId)} className="font-medium text-left hover:text-[var(--syn-accent)]">{a.entityTitle}</button></TableCell>
                        <TableCell className="text-xs">{a.action === 'status_changed' ? <span>Status geändert</span> : ACTION_LABEL[a.action] || a.action}</TableCell>
                        <TableCell>{a.action === 'status_changed' && a.oldValue ? <Badge className={`text-[9px] ${ST_STYLE[a.oldValue] || ''}`}>{ST_LABEL[a.oldValue] || a.oldValue}</Badge> : <span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>—</span>}</TableCell>
                        <TableCell>{a.action === 'status_changed' && a.newValue ? <Badge className={`text-[9px] ${ST_STYLE[a.newValue] || ''}`}>{ST_LABEL[a.newValue] || a.newValue}</Badge> : <span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>—</span>}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody></Table>
                ) : <div className="py-12 text-center text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine abgeschlossenen Einträge im Protokoll.</div>}
              </CardContent></Card>
              {filteredLog.length > 0 && <p className="text-xs text-center" style={{ color: 'var(--syn-text-faint)' }}>{filteredLog.length} Einträge</p>}
            </div>
          )}

          {/* ═══ TEXTSUCHE ═══ */}
          {page === 'textsuche' && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold">Textsuche</h2>
                <p className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Volltextsuche über alle Dashboard-Daten{globalSearch.trim() ? ` — "${globalSearch.trim()}"` : ''}.</p>
              </div>
              {!globalSearch.trim() ? (
                <div className="text-sm py-8 text-center" style={{ color: 'var(--syn-text-faint)' }}>Gib einen Suchbegriff in die Suchleiste oben ein.</div>
              ) : (
                <div className="space-y-6">
                  {searchResultsFull.meetings.length > 0 && (
                    <Card className="glass-card border-[var(--syn-line)] overflow-hidden">
                      <div className="px-5 py-3 border-b border-[var(--syn-line)]"><span className="text-sm font-semibold">Meetings ({searchResultsFull.meetings.length})</span></div>
                      <div className="divide-y divide-[var(--syn-line)]">{searchResultsFull.meetings.map(m => (
                        <div key={m.id} className="px-5 py-3 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer flex items-center gap-3" onClick={() => setViewMeeting(m)}>
                          <span className="text-xs">☰</span>
                          <div className="flex-1 min-w-0"><div className="text-sm font-medium truncate">{m.title}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>{m.date} · {m.participants.slice(0, 3).join(', ')}</div></div>
                        </div>
                      ))}</div>
                    </Card>
                  )}
                  {searchResultsFull.todos.length > 0 && (
                    <Card className="glass-card border-[var(--syn-line)] overflow-hidden">
                      <div className="px-5 py-3 border-b border-[var(--syn-line)]"><span className="text-sm font-semibold">Todos ({searchResultsFull.todos.length})</span></div>
                      <div className="divide-y divide-[var(--syn-line)]">{searchResultsFull.todos.map(t => (
                        <div key={t.id} className="px-5 py-3 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer flex items-center gap-3" onClick={() => setViewTodo(t)}>
                          <span className="text-xs">✓</span>
                          <div className="flex-1 min-w-0"><div className="text-sm font-medium truncate">{t.title}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>{t.assignee} · {t.dueDate || 'kein Datum'}</div></div>
                          <Badge className={`text-[9px] ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]}</Badge>
                          <Badge className={`text-[9px] ${ST_STYLE[t.status]}`}>{ST_LABEL[t.status]}</Badge>
                        </div>
                      ))}</div>
                    </Card>
                  )}
                  {searchResultsFull.blockers.length > 0 && (
                    <Card className="glass-card border-[var(--syn-line)] overflow-hidden">
                      <div className="px-5 py-3 border-b border-[var(--syn-line)]"><span className="text-sm font-semibold">Blocker ({searchResultsFull.blockers.length})</span></div>
                      <div className="divide-y divide-[var(--syn-line)]">{searchResultsFull.blockers.map(b => (
                        <div key={b.id} className="px-5 py-3 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer flex items-center gap-3" onClick={() => setViewBlocker(b)}>
                          <span className="text-xs">⚠</span>
                          <div className="flex-1 min-w-0"><div className="text-sm font-medium truncate">{b.title}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>{b.reportedBy} · seit {b.createdAt}</div></div>
                          <Badge className={`text-[9px] ${ST_STYLE[b.status]}`}>{ST_LABEL[b.status]}</Badge>
                        </div>
                      ))}</div>
                    </Card>
                  )}
                  {searchResultsFull.openItems.length > 0 && (
                    <Card className="glass-card border-[var(--syn-line)] overflow-hidden">
                      <div className="px-5 py-3 border-b border-[var(--syn-line)]"><span className="text-sm font-semibold">Open Items ({searchResultsFull.openItems.length})</span></div>
                      <div className="divide-y divide-[var(--syn-line)]">{searchResultsFull.openItems.map(o => (
                        <div key={o.id} className="px-5 py-3 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer flex items-center gap-3" onClick={() => setViewOpen(o)}>
                          <span className="text-xs">{CAT_ICON[o.category] || '○'}</span>
                          <div className="flex-1 min-w-0"><div className="text-sm font-medium truncate">{o.title}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>{o.owner} · seit {o.createdAt}</div></div>
                          <Badge className={`text-[9px] ${ST_STYLE[o.status]}`}>{ST_LABEL[o.status]}</Badge>
                        </div>
                      ))}</div>
                    </Card>
                  )}
                  {searchResultsFull.meetings.length === 0 && searchResultsFull.todos.length === 0 && searchResultsFull.blockers.length === 0 && searchResultsFull.openItems.length === 0 && (
                    <div className="text-sm py-8 text-center" style={{ color: 'var(--syn-text-faint)' }}>Keine Ergebnisse für "{globalSearch.trim()}".</div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ═══ KI-ASSISTENT ═══ */}
          {page === 'ki' && (
            <div className="flex flex-col h-[calc(100vh-8rem)]">
              <div className="mb-4">
                <h2 className="text-base font-semibold">KI-Assistent</h2><p className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Semantische Suche über alle Dashboard-Daten — Einträge werden automatisch indexiert.</p>
              </div>
              <Card className="glass-card border-[var(--syn-line)] flex-1 flex flex-col min-h-0">
                <CardContent className="flex-1 flex flex-col p-4 min-h-0">
                  <ScrollArea className="flex-1 mb-4">
                    <div className="space-y-4 pr-2">
                      {chatMessages.length === 0 && (
                        <div className="text-center py-12 space-y-3">
                          <div className="text-3xl" style={{ color: 'var(--syn-accent)' }}>◉</div>
                          <p className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Stelle eine Frage zu deinen Dashboard-Daten.</p>
                          <div className="flex flex-wrap gap-2 justify-center">
                            {['Welche Todos sind diese Woche fällig?', 'Fasse die letzten 3 Meetings zusammen', 'Welche Blocker sind gerade aktiv?', 'Welche Entscheidungen wurden zuletzt getroffen?'].map((q, i) => (
                              <button key={i} onClick={() => handleChat(q)} className="text-xs px-3 py-1.5 rounded-full transition-colors border border-[var(--syn-line)] hover:border-[var(--syn-accent-line)] hover:bg-[var(--syn-accent-soft)]" style={{ color: 'var(--syn-text-muted)' }}>{q}</button>
                            ))}
                          </div>
                        </div>
                      )}
                      {chatMessages.map((msg, i) => {
                        if (msg.role === 'assistant' && !msg.text && !msg.matches?.length) return null
                        const ts = msg.timestamp ? new Date(msg.timestamp) : null
                        const timeStr = ts ? `${String(ts.getDate()).padStart(2,'0')}.${String(ts.getMonth()+1).padStart(2,'0')}.${ts.getFullYear()} ${String(ts.getHours()).padStart(2,'0')}:${String(ts.getMinutes()).padStart(2,'0')}` : null
                        return (
                        <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                          <div className={`max-w-[75%] rounded-xl px-4 py-3 ${msg.role === 'user' ? 'bg-[var(--syn-accent)] text-white' : ''}`} style={msg.role === 'assistant' ? { background: 'var(--syn-surface-2)', color: 'var(--syn-text)' } : {}}>
                            {timeStr && <div className="text-[10px] mb-1" style={{ color: msg.role === 'user' ? 'rgba(255,255,255,.6)' : 'var(--syn-text-faint)' }}>{timeStr}</div>}
                            {msg.role === 'assistant' ? renderMarkdown(msg.text) : <p className="text-sm whitespace-pre-wrap">{msg.text}</p>}
                            {msg.matches && msg.matches.length > 0 && (
                              <div className="mt-3 pt-2 border-t border-[var(--syn-line)] space-y-1">
                                <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--syn-text-faint)' }}>Quellen ({msg.matches.length})</p>
                                {msg.matches.slice(0, 5).map((m, j) => (
                                  <button key={j} onClick={() => openSourceEntity(m.entity_type, m.entity_id)} className="w-full text-left text-xs flex items-center gap-1.5 rounded px-1 py-0.5 -mx-1 transition-colors cursor-pointer hover:bg-[var(--syn-hover)]" style={{ color: 'var(--syn-text-muted)' }}>
                                    <Badge variant="outline" className="text-[9px] shrink-0 border-[var(--syn-line)]">{TYPE_LABEL[m.entity_type] || m.entity_type}</Badge>
                                    <span className="truncate hover:text-[var(--syn-accent)]">{m.content.slice(0, 80)}...</span>
                                    <span className="text-[10px] shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{Math.round(m.similarity * 100)}%</span>
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )})}
                      {chatLoading && (!chatMessages.length || chatMessages[chatMessages.length - 1].role !== 'assistant' || !chatMessages[chatMessages.length - 1].text) && <div className="flex justify-start"><div className="rounded-xl px-4 py-3 text-sm" style={{ background: 'var(--syn-surface-2)', color: 'var(--syn-text-muted)' }}>Denkt nach...</div></div>}
                      <div ref={chatEndRef} />
                    </div>
                  </ScrollArea>
                  <div className="flex gap-2">
                    <Input placeholder="Frage stellen..." value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleChat()} className="flex-1 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" disabled={chatLoading} />
                    <Button onClick={() => handleChat()} disabled={chatLoading || !chatInput.trim()} className="bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white">Senden</Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </main>
      </div>

      {/* ═══ DIALOGS ═══ */}
      {/* View Meeting */}
      <Dialog open={!!viewMeeting} onOpenChange={() => setViewMeeting(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh]">{viewMeeting && <ScrollArea className="max-h-[75vh] pr-4">
          <DialogHeader className="pb-3"><DialogTitle>{viewMeeting.title}</DialogTitle><div className="flex items-center gap-3 text-xs mt-1" style={{ color: 'var(--syn-text-muted)' }}><span>{viewMeeting.date}</span><span>{'·'}</span><span>{viewMeeting.participants.length} Teilnehmer</span></div></DialogHeader>
          <div className="space-y-4 pt-2">
            <div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Themen</h3><div className="flex flex-wrap gap-1.5">{viewMeeting.topics.map((t, i) => <Badge key={i} variant="outline" className="border-[var(--syn-line)]">{t}</Badge>)}</div></div>
            <Separator className="bg-[var(--syn-line)]" />
            <div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Teilnehmer</h3><div className="flex flex-wrap gap-2">{viewMeeting.participants.map((p, i) => <span key={i} className="text-sm px-2.5 py-1 rounded" style={{ background: 'var(--syn-surface-3)' }}>{p}</span>)}</div></div>
            <Separator className="bg-[var(--syn-line)]" />
            <div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Zusammenfassung</h3>{viewMeeting.summary ? <div className="text-sm leading-relaxed prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: sanitizeHtml(viewMeeting.summary) }} /> : <p className="text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Zusammenfassung.</p>}</div>
            {viewMeeting.keyDecisions.length > 0 && <><Separator className="bg-[var(--syn-line)]" /><div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Entscheidungen</h3><div className="space-y-1.5">{viewMeeting.keyDecisions.map((d, i) => <div key={i} className="flex items-start gap-2 text-sm"><span style={{ color: 'var(--syn-ok)' }} className="mt-0.5">{'✓'}</span>{d}</div>)}</div></div></>}
            {(() => { const rel = todos.filter(t => t.meetingId === viewMeeting.id); if (!rel.length) return null; return <><Separator className="bg-[var(--syn-line)]" /><div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Todos</h3><ul className="space-y-1 list-disc list-inside">{rel.map(t => <li key={t.id} className="text-sm"><button onClick={() => { setViewMeeting(null); setViewTodo(t) }} className="hover:text-[var(--syn-accent)]">{t.title}</button><span className="text-xs ml-2" style={{ color: 'var(--syn-text-faint)' }}>({t.assignee})</span></li>)}</ul></div></> })()}
            <Separator className="bg-[var(--syn-line)]" />
            <div className="flex gap-2"><Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { const m = viewMeeting; setViewMeeting(null); setEditMeeting({...m}) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => { handleDeleteMeeting(viewMeeting); setViewMeeting(null) }}>{'✕'} Löschen</Button></div>
          </div>
        </ScrollArea>}</DialogContent>
      </Dialog>

      {/* View Project Detail */}
      <Dialog open={!!viewProject} onOpenChange={() => setViewProject(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh]">{viewProject && <ScrollArea className="max-h-[75vh] pr-4">
          <DialogHeader className="pb-3">
            <DialogTitle>{viewProject.name}</DialogTitle>
            <div className="flex items-center gap-3 mt-1">
              <Badge className={`text-xs ${ST_STYLE[viewProject.status]}`}>{ST_LABEL[viewProject.status]}</Badge>
              <span className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Erstellt: {viewProject.created_at?.split('T')[0]}</span>
            </div>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            {viewProject.description && <><div className="text-sm">{viewProject.description}</div><Separator className="bg-[var(--syn-line)]" /></>}
            {(() => { const pT = projectTodos(viewProject.id); if (!pT.length) return null; return <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--syn-text-faint)' }}>Todos ({pT.filter(t => t.status === 'done').length}/{pT.length} erledigt)</h3>
              <div className="space-y-1.5">{pT.map(t => (
                <div key={t.id} className="flex items-center gap-2 text-sm">
                  <span className={`w-4 h-4 rounded border flex items-center justify-center text-[10px] ${t.status === 'done' ? 'bg-[var(--syn-ok)] border-[var(--syn-ok)] text-white' : 'border-[var(--syn-line-strong)]'}`}>{t.status === 'done' ? '✓' : ''}</span>
                  <button onClick={() => { setViewProject(null); setViewTodo(t) }} className={`hover:text-[var(--syn-accent)] ${t.status === 'done' ? 'line-through opacity-50' : ''}`}>{t.title}</button>
                  <span className="text-xs ml-auto" style={{ color: 'var(--syn-text-faint)' }}>{t.assignee}</span>
                  <Badge className={`text-[9px] ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]}</Badge>
                </div>
              ))}</div>
            </div> })()}
            {(() => { const pB = projectBlockers(viewProject.id); if (!pB.length) return null; return <><Separator className="bg-[var(--syn-line)]" /><div>
              <h3 className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--syn-text-faint)' }}>Blocker ({pB.filter(b => b.status === 'active').length} aktiv)</h3>
              <div className="space-y-1">{pB.map(b => (
                <div key={b.id} className="flex items-center gap-2 text-sm">
                  <Badge className={`text-[9px] ${ST_STYLE[b.status]}`}>{ST_LABEL[b.status]}</Badge>
                  <button onClick={() => { setViewProject(null); setViewBlocker(b) }} className="hover:text-[var(--syn-accent)]">{b.title}</button>
                </div>
              ))}</div>
            </div></> })()}
            <Separator className="bg-[var(--syn-line)]" />
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { const p = viewProject!; setViewProject(null); setEditProject({...p}) }}>{'✎'} Bearbeiten</Button>
              <Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => { handleDeleteProject(viewProject!); setViewProject(null) }}>{'✕'} Löschen</Button>
              <div className="ml-auto flex gap-1">
                <Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewProject(null); setPage('projekte'); setProjectView('gantt') }}>{'▰'} Gantt</Button>
                <Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewProject(null); setPage('projekte'); setProjectView('kanban') }}>{'▥'} Kanban</Button>
              </div>
            </div>
          </div>
        </ScrollArea>}</DialogContent>
      </Dialog>

      {/* Edit Todo */}
      <Dialog open={!!editTodo} onOpenChange={() => setEditTodo(null)}><DialogContent className="max-w-lg"><DialogHeader><DialogTitle>{editTodo?.id === '__new__' ? 'Neuer Todo' : 'Todo bearbeiten'}</DialogTitle></DialogHeader>{editTodo && <div className="space-y-3 pt-2"><Input placeholder="Titel" value={editTodo.title} onChange={e => setEditTodo({...editTodo, title: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea placeholder="Beschreibung" value={editTodo.description} onChange={e => setEditTodo({...editTodo, description: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><div className="grid grid-cols-2 gap-3"><Select value={editTodo.assignee} onValueChange={v => setEditTodo({...editTodo, assignee: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select><Select value={editTodo.priority} onValueChange={v => setEditTodo({...editTodo, priority: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="urgent">Urgent</SelectItem><SelectItem value="high">Hoch</SelectItem><SelectItem value="medium">Mittel</SelectItem><SelectItem value="low">Niedrig</SelectItem></SelectContent></Select></div><div className="grid grid-cols-2 gap-3"><Select value={editTodo.status} onValueChange={v => setEditTodo({...editTodo, status: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="open">Offen</SelectItem><SelectItem value="in_progress">In Arbeit</SelectItem><SelectItem value="done">Erledigt</SelectItem><SelectItem value="cancelled">Abgebrochen</SelectItem></SelectContent></Select><div><label className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Startdatum</label><Input type="date" value={editTodo.startDate || ''} onChange={e => setEditTodo({...editTodo, startDate: e.target.value || null})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /></div></div><div className="grid grid-cols-2 gap-3"><div><label className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Dauer (Tage)</label><Input type="number" min={1} value={editTodo.durationDays} onChange={e => setEditTodo({...editTodo, durationDays: Math.max(1, parseInt(e.target.value) || 1)})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /></div><div>{editTodo.startDate && <><label className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Enddatum (berechnet)</label><div className="text-sm mt-1.5">{addDays(editTodo.startDate, Math.max(editTodo.durationDays - 1, 0))}</div></>}</div></div><div><label className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Projekt</label><Select value={editTodo.projectId || 'none'} onValueChange={v => setEditTodo({...editTodo, projectId: v === 'none' ? null : v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">— Kein Projekt</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select></div><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editTodo.title.trim()} onClick={() => editTodo.id === '__new__' ? handleCreateTodo(editTodo) : handleSaveTodo(editTodo)}>{editTodo.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button></div>}</DialogContent></Dialog>

      {/* Edit Blocker */}
      <Dialog open={!!editBlocker} onOpenChange={() => setEditBlocker(null)}><DialogContent className="max-w-lg"><DialogHeader><DialogTitle>{editBlocker?.id === '__new__' ? 'Neuer Blocker' : 'Blocker bearbeiten'}</DialogTitle></DialogHeader>{editBlocker && <div className="space-y-3 pt-2"><Input placeholder="Titel" value={editBlocker.title} onChange={e => setEditBlocker({...editBlocker, title: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea placeholder="Beschreibung" value={editBlocker.description} onChange={e => setEditBlocker({...editBlocker, description: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><div className="grid grid-cols-2 gap-3"><Select value={editBlocker.reportedBy} onValueChange={v => setEditBlocker({...editBlocker, reportedBy: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select><Select value={editBlocker.status} onValueChange={v => setEditBlocker({...editBlocker, status: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="active">Aktiv</SelectItem><SelectItem value="resolved">Gelöst</SelectItem><SelectItem value="escalated">Eskaliert</SelectItem></SelectContent></Select></div><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editBlocker.title.trim()} onClick={() => editBlocker.id === '__new__' ? handleCreateBlocker(editBlocker) : handleSaveBlocker(editBlocker)}>{editBlocker.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button></div>}</DialogContent></Dialog>

      {/* Edit Open Item */}
      <Dialog open={!!editOpen} onOpenChange={() => setEditOpen(null)}><DialogContent className="max-w-lg"><DialogHeader><DialogTitle>{editOpen?.id === '__new__' ? 'Neues Open Item' : 'Open Item bearbeiten'}</DialogTitle></DialogHeader>{editOpen && <div className="space-y-3 pt-2"><Input placeholder="Titel" value={editOpen.title} onChange={e => setEditOpen({...editOpen, title: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea placeholder="Beschreibung" value={editOpen.description} onChange={e => setEditOpen({...editOpen, description: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><div className="grid grid-cols-2 gap-3"><Select value={editOpen.owner} onValueChange={v => setEditOpen({...editOpen, owner: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select><Select value={editOpen.category} onValueChange={v => setEditOpen({...editOpen, category: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="general">General</SelectItem><SelectItem value="risk">Risk</SelectItem><SelectItem value="opportunity">Opportunity</SelectItem><SelectItem value="question">Question</SelectItem><SelectItem value="follow_up">Follow-up</SelectItem></SelectContent></Select></div><Select value={editOpen.status} onValueChange={v => setEditOpen({...editOpen, status: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="open">Offen</SelectItem><SelectItem value="watching">Beobachten</SelectItem><SelectItem value="closed">Geschlossen</SelectItem></SelectContent></Select><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editOpen.title.trim()} onClick={() => editOpen.id === '__new__' ? handleCreateOpen(editOpen) : handleSaveOpen(editOpen)}>{editOpen.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button></div>}</DialogContent></Dialog>

      {/* Edit Meeting */}
      <Dialog open={!!editMeeting} onOpenChange={() => setEditMeeting(null)}><DialogContent className="max-w-lg"><DialogHeader><DialogTitle>Meeting bearbeiten</DialogTitle></DialogHeader>{editMeeting && <div className="space-y-3 pt-2"><Input value={editMeeting.title} onChange={e => setEditMeeting({...editMeeting, title: e.target.value})} placeholder="Titel" className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Input type="date" value={editMeeting.date} onChange={e => setEditMeeting({...editMeeting, date: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Input value={editMeeting.topics.join(', ')} onChange={e => setEditMeeting({...editMeeting, topics: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} placeholder="Themen (kommagetrennt)" className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Input value={editMeeting.participants.join(', ')} onChange={e => setEditMeeting({...editMeeting, participants: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} placeholder="Teilnehmer (kommagetrennt)" className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea value={editMeeting.summary} onChange={e => setEditMeeting({...editMeeting, summary: e.target.value})} placeholder="Zusammenfassung" rows={4} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Input value={editMeeting.keyDecisions.join(', ')} onChange={e => setEditMeeting({...editMeeting, keyDecisions: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} placeholder="Entscheidungen (kommagetrennt)" className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={() => handleSaveMeeting(editMeeting)}>Speichern</Button></div>}</DialogContent></Dialog>

      {/* Edit Project */}
      <Dialog open={!!editProject} onOpenChange={() => setEditProject(null)}><DialogContent className="max-w-lg"><DialogHeader><DialogTitle>{editProject?.id === '__new__' ? 'Neues Projekt' : 'Projekt bearbeiten'}</DialogTitle></DialogHeader>{editProject && <div className="space-y-3 pt-2"><Input placeholder="Name" value={editProject.name} onChange={e => setEditProject({...editProject, name: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea placeholder="Beschreibung" value={editProject.description || ''} onChange={e => setEditProject({...editProject, description: e.target.value || null})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Select value={editProject.status} onValueChange={v => setEditProject({...editProject, status: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="active">Aktiv</SelectItem><SelectItem value="completed">Abgeschlossen</SelectItem><SelectItem value="on_hold">Pausiert</SelectItem></SelectContent></Select><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editProject.name.trim()} onClick={() => handleSaveProject(editProject)}>{editProject.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button></div>}</DialogContent></Dialog>

      {/* View Todo */}
      <Dialog open={!!viewTodo} onOpenChange={() => setViewTodo(null)}><DialogContent className="max-w-lg">{viewTodo && <><DialogHeader className="text-left"><DialogTitle>{viewTodo.title}</DialogTitle></DialogHeader><div className="space-y-3 pt-2 text-left"><div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm"><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Zuständig</span><div className="flex items-center gap-1.5 mt-0.5"><Av name={viewTodo.assignee} /><span>{viewTodo.assignee}</span></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Priorität</span><div className="mt-0.5"><Badge className={`text-xs ${PRI_STYLE[viewTodo.priority]}`}>{PRI_LABEL[viewTodo.priority]}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Status</span><div className="mt-0.5"><Badge className={`text-xs ${ST_STYLE[viewTodo.status]}`}>{ST_LABEL[viewTodo.status]}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Dauer</span><div className="mt-0.5">{viewTodo.durationDays} Tag{viewTodo.durationDays !== 1 ? 'e' : ''}</div></div>{viewTodo.startDate && <div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Startdatum</span><div className="mt-0.5">{viewTodo.startDate}</div></div>}{viewTodo.startDate && <div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Enddatum</span><div className="mt-0.5">{addDays(viewTodo.startDate, Math.max(viewTodo.durationDays - 1, 0))}</div></div>}<div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Erstellt</span><div className="mt-0.5">{viewTodo.createdAt || '—'}</div></div>{getProjectName(viewTodo.projectId) && <div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Projekt</span><div className="mt-0.5 flex items-center gap-2"><span>{getProjectName(viewTodo.projectId)}</span><button onClick={() => { setViewTodo(null); setPage('projekte'); setProjectView('gantt') }} className="text-[10px] underline hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-muted)' }}>Gantt</button><button onClick={() => { setViewTodo(null); setPage('projekte'); setProjectView('kanban') }} className="text-[10px] underline hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-muted)' }}>Kanban</button></div></div>}</div>{viewTodo.description && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Beschreibung</span><p className="text-sm mt-1 leading-relaxed whitespace-pre-wrap">{viewTodo.description}</p></div></>}{viewTodo.dependsOn.length > 0 && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Abhängig von</span><div className="mt-1 space-y-1">{viewTodo.dependsOn.map(depId => { const dep = todos.find(t => t.id === depId); return dep ? <button key={depId} onClick={() => { setViewTodo(null); setTimeout(() => setViewTodo(dep), 100) }} className="block text-sm hover:text-[var(--syn-accent)]">{dep.title}</button> : null })}</div></div></>}{viewTodo.meetingId && getMeeting(viewTodo.meetingId) && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Meeting</span><div className="mt-0.5"><SourceChip meeting={getMeeting(viewTodo.meetingId)!} onClick={() => { setViewTodo(null); setViewMeeting(getMeeting(viewTodo.meetingId!)!) }} /></div></div></>}<Separator className="bg-[var(--syn-line)]" /><div className="flex gap-2"><Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewTodo(null); setEditTodo({...viewTodo}) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => { handleDeleteTodo(viewTodo); setViewTodo(null) }}>{'✕'} Löschen</Button></div></div></>}</DialogContent></Dialog>

      {/* View Blocker */}
      <Dialog open={!!viewBlocker} onOpenChange={() => setViewBlocker(null)}><DialogContent className="max-w-lg">{viewBlocker && <><DialogHeader className="text-left"><DialogTitle>{viewBlocker.title}</DialogTitle></DialogHeader><div className="space-y-3 pt-2 text-left"><div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm"><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Zuständig</span><div className="flex items-center gap-1.5 mt-0.5"><Av name={viewBlocker.reportedBy} /><span>{viewBlocker.reportedBy}</span></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Status</span><div className="mt-0.5"><Badge className={`text-xs ${ST_STYLE[viewBlocker.status]}`}>{ST_LABEL[viewBlocker.status]}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Erstellt</span><div className="mt-0.5">{viewBlocker.createdAt || '—'}</div></div></div>{viewBlocker.description && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Beschreibung</span><p className="text-sm mt-1 leading-relaxed whitespace-pre-wrap">{viewBlocker.description}</p></div></>}{viewBlocker.meetingId && getMeeting(viewBlocker.meetingId) && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Meeting</span><div className="mt-0.5"><SourceChip meeting={getMeeting(viewBlocker.meetingId)!} onClick={() => { setViewBlocker(null); setViewMeeting(getMeeting(viewBlocker.meetingId!)!) }} /></div></div></>}<Separator className="bg-[var(--syn-line)]" /><div className="flex gap-2">{viewBlocker.status === 'active' && <Button size="sm" className="text-xs bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={() => { handleResolveBlocker(viewBlocker); setViewBlocker(null) }}>Lösen</Button>}<Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewBlocker(null); setEditBlocker({...viewBlocker}) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => { handleDeleteBlocker(viewBlocker); setViewBlocker(null) }}>{'✕'} Löschen</Button></div></div></>}</DialogContent></Dialog>

      {/* View Open Item */}
      <Dialog open={!!viewOpen} onOpenChange={() => setViewOpen(null)}><DialogContent className="max-w-lg">{viewOpen && <><DialogHeader className="text-left"><DialogTitle>{viewOpen.title}</DialogTitle></DialogHeader><div className="space-y-3 pt-2 text-left"><div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm"><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Zuständig</span><div className="flex items-center gap-1.5 mt-0.5"><Av name={viewOpen.owner} /><span>{viewOpen.owner}</span></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Kategorie</span><div className="mt-0.5"><Badge variant="outline" className="text-xs border-[var(--syn-line)]">{viewOpen.category}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Status</span><div className="mt-0.5"><Badge className={`text-xs ${ST_STYLE[viewOpen.status]}`}>{ST_LABEL[viewOpen.status]}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Erstellt</span><div className="mt-0.5">{viewOpen.createdAt || '—'}</div></div></div>{viewOpen.description && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Beschreibung</span><p className="text-sm mt-1 leading-relaxed whitespace-pre-wrap">{viewOpen.description}</p></div></>}{viewOpen.meetingId && getMeeting(viewOpen.meetingId) && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Meeting</span><div className="mt-0.5"><SourceChip meeting={getMeeting(viewOpen.meetingId)!} onClick={() => { setViewOpen(null); setViewMeeting(getMeeting(viewOpen.meetingId!)!) }} /></div></div></>}<Separator className="bg-[var(--syn-line)]" /><div className="flex gap-2">{viewOpen.status !== 'closed' && <Button size="sm" className="text-xs bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={() => { handleCloseItem(viewOpen); setViewOpen(null) }}>Schließen</Button>}<Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewOpen(null); setEditOpen({...viewOpen}) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => { handleDeleteOpen(viewOpen); setViewOpen(null) }}>{'✕'} Löschen</Button></div></div></>}</DialogContent></Dialog>
    </div>
  )
}
