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
  fetchProjectMeetings, setProjectMeetings,
  insertTodo, insertBlocker, insertOpenItem, insertMeeting,

  fetchInboxItems, updateInboxItemPayload, deleteInboxItemDb, approveInboxItem,
  triggerMakeWebhook, MAKE_WEBHOOK_URL,
  isNightlyJobActive, toggleNightlyJob,
  signIn, signOut, resetPassword, getSession, onAuthStateChange,
  semanticSearchStream,
  type DbTeamMember, type DbProject, type DbInboxItem, type SearchMatch
} from './supabase'

type Page = 'uebersicht' | 'sitzungen' | 'aktionen' | 'projekte' | 'ki' | 'textsuche' | 'protokoll' | 'inbox'
type SortDir = 'asc' | 'desc' | null
type ProjectView = 'table' | 'kanban' | 'gantt'
type ActionTab = 'todos' | 'blocker' | 'open'

const PRI_LABEL: Record<string, string> = { urgent: 'Dringend', high: 'Hoch', medium: 'Mittel', low: 'Niedrig' }
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
const TYPE_LABEL: Record<string, string> = { todo: 'Todo', blocker: 'Blocker', open_item: 'Offener Punkt', meeting: 'Meeting', decision: 'Entscheidung', project: 'Projekt', activity: 'Änderung' }
const CAT_LABEL: Record<string, string> = { general: 'Allgemein', risk: 'Risiko', opportunity: 'Chance', question: 'Frage', follow_up: 'Nachverfolgung' }
const CAT_ICON: Record<string, string> = { risk: '▲', opportunity: '◆', question: '?', follow_up: '↩', general: '○' }
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
  return <TableHead className={`cursor-pointer select-none hover:bg-[var(--syn-hover)] transition-colors ${className || ''}`} onClick={() => onSort(field)}><span className="flex items-center justify-center text-xs">{label}<SortIcon dir={sort.col === field ? sort.dir : null} /></span></TableHead>
}
function TrashIcon() {
  return (
    <svg width="13" height="14" viewBox="0 0 13 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 3.5h11M4.5 3.5v-1a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5v1M3 3.5l.75 8h6.5l.75-8" />
    </svg>
  )
}

/* Source Chip — links back to originating meeting */
// Soft project colors (no pinks, no neon)
const PROJECT_COLORS = [
  '#6b9bd2', '#7ab87a', '#c4a35a', '#8b8bc7', '#5ca8a8',
  '#b0855a', '#7aadad', '#9dab6f', '#a38db8', '#6fa8c7',
]
function getProjectColor(projectId: string | null, projectIds: string[]): string {
  if (!projectId) return '#999'
  const idx = projectIds.indexOf(projectId)
  return PROJECT_COLORS[idx >= 0 ? idx % PROJECT_COLORS.length : 0]
}

function SourceChip({ meeting, onClick }: { meeting: { id: string; title: string } | null; onClick?: () => void }) {
  if (!meeting) return null
  const label = meeting.title.length > 18 ? meeting.title.slice(0, 18) + '…' : meeting.title
  return (
    <button onClick={onClick} className="source-chip inline-flex items-center justify-center gap-1 px-3 py-0.5 rounded text-[10px] transition-colors w-full" title={meeting.title}>
      <span className="opacity-60">{'"'}</span><span className="text-center">{label}</span>
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
    const map: Record<string, Page> = { dashboard: 'uebersicht', uebersicht: 'uebersicht', notizen: 'sitzungen', protokoll: 'protokoll', projekte: 'projekte', ki: 'ki', textsuche: 'textsuche', sitzungen: 'sitzungen', aktionen: 'aktionen', inbox: 'inbox' }
    return map[raw] || 'uebersicht'
  }
  const [page, setPageRaw] = useState<Page>(getPageFromHash)
  const setPage = (p: Page) => { setPageRaw(p); window.location.hash = p }
  useEffect(() => {
    const handler = () => setPageRaw(getPageFromHash())
    window.addEventListener('hashchange', handler)
    return () => window.removeEventListener('hashchange', handler)
  }, [])
  // Persist scroll position across refreshes (save on unload)
  const scrollRestored = useRef(false)
  useEffect(() => {
    const saveScroll = () => sessionStorage.setItem('mos_scrollY', String(window.scrollY))
    window.addEventListener('beforeunload', saveScroll)
    return () => window.removeEventListener('beforeunload', saveScroll)
  }, [])
  const [loading, setLoading] = useState(true)
  // Restore scroll position after data finishes loading
  useEffect(() => {
    if (!loading && !scrollRestored.current) {
      scrollRestored.current = true
      const saved = sessionStorage.getItem('mos_scrollY')
      if (saved) { const y = parseInt(saved, 10); requestAnimationFrame(() => window.scrollTo(0, y)) }
    }
  }, [loading])
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [nightlyActive, setNightlyActive] = useState(true)
  const [globalSearch, setGlobalSearch] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const [projectView, setProjectViewRaw] = useState<ProjectView>(() => (sessionStorage.getItem('mos_projectView') as ProjectView) || 'table')
  const setProjectView = (v: ProjectView) => { setProjectViewRaw(v); sessionStorage.setItem('mos_projectView', v) }
  const [actionTab, setActionTabRaw] = useState<ActionTab>(() => (sessionStorage.getItem('mos_actionTab') as ActionTab) || 'todos')
  const setActionTab = (v: ActionTab) => { setActionTabRaw(v); sessionStorage.setItem('mos_actionTab', v) }

  const [members, setMembers] = useState<DbTeamMember[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [blockers, setBlockers] = useState<Blocker[]>([])
  const [openItems, setOpenItems] = useState<OpenItem[]>([])
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [activity, setActivity] = useState<Activity[]>([])
  const [projects, setProjects] = useState<DbProject[]>([])
  const projectIds = useMemo(() => projects.map(p => p.id), [projects])
  const [inboxItems, setInboxItems] = useState<DbInboxItem[]>([])

  const [inboxEditModeFor, setInboxEditModeFor] = useState<string | null>(null)

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
  const projectFilterStatus = 'all'
  const todoSort = useSortState(); const blockerSort = useSortState(); const openSort = useSortState()
  const noteSort = useSortState(); const logSort = useSortState(); const projectSort = useSortState()

  // Edit state
  const [editTodo, setEditTodo] = useState<Todo | null>(null)
  const [editBlocker, setEditBlocker] = useState<Blocker | null>(null)
  const [editOpen, setEditOpen] = useState<OpenItem | null>(null)
  const [editMeeting, setEditMeeting] = useState<Meeting | null>(null)
  const [editProject, setEditProject] = useState<DbProject | null>(null)
  // projectInitTodos kept for reset calls
  const [, setProjectInitTodos] = useState('')
  // Project-dialog relations
  const [projTodoQueue, setProjTodoQueue] = useState<Todo[]>([])
  const [projTodoNewForm, setProjTodoNewForm] = useState<Todo | null>(null)
  const [projTodoSearch, setProjTodoSearch] = useState('')
  const [projLinkedTodoIds, setProjLinkedTodoIds] = useState<Set<string>>(new Set())
  const [projMeetingSearch, setProjMeetingSearch] = useState('')
  const [projLinkedMeetingIds, setProjLinkedMeetingIds] = useState<Set<string>>(new Set())
  const [projMeetingPickerOpen, setProjMeetingPickerOpen] = useState(false)
  const [projTodoPickerOpen, setProjTodoPickerOpen] = useState(false)
  const [viewMeeting, setViewMeeting] = useState<Meeting | null>(null)
  const [viewTodo, setViewTodo] = useState<Todo | null>(null)
  const [viewBlocker, setViewBlocker] = useState<Blocker | null>(null)
  const [viewOpen, setViewOpen] = useState<OpenItem | null>(null)
  const [viewProject, setViewProject] = useState<DbProject | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ label: string; action: () => void } | null>(null)
  const [printView, setPrintView] = useState<'kanban' | 'gantt' | null>(null)
  const [ganttVisibleCols, setGanttVisibleCols] = useState<string[]>(['project', 'title', 'assignee', 'priority'])
  const [ganttColDropOpen, setGanttColDropOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsedRaw] = useState(() => sessionStorage.getItem('mos_sidebar') === '1')
  const setSidebarCollapsed = (v: boolean | ((prev: boolean) => boolean)) => {
    setSidebarCollapsedRaw(prev => { const next = typeof v === 'function' ? v(prev) : v; sessionStorage.setItem('mos_sidebar', next ? '1' : '0'); return next })
  }
  const [dragTodo, setDragTodo] = useState<string | null>(null)
  const [kanbanFields, setKanbanFields] = useState<Set<string>>(new Set(['priority', 'assignee', 'duration', 'project']))
  const [kanbanFilterProject, setKanbanFilterProject] = useState('all')
  const [kanbanFilterAssignee, setKanbanFilterAssignee] = useState('all')
  type KanbanGroupBy = 'none' | 'project' | 'assignee'
  const [kanbanGroupBy, setKanbanGroupBy] = useState<KanbanGroupBy>('none')
  const [kanbanSortKey, setKanbanSortKey] = useState<'start' | 'priority' | 'assignee' | 'title' | 'project'>('priority')
  const [kanbanSortDir, setKanbanSortDir] = useState<'asc' | 'desc'>('desc')
  const [ganttFields, setGanttFields] = useState<Set<string>>(new Set(['assignee', 'duration']))
  type GanttGranularity = 'month' | 'quarter' | 'year'
  const [ganttGranularity, setGanttGranularity] = useState<GanttGranularity>('month')
  const [ganttFilterProject, setGanttFilterProject] = useState('all')
  const [ganttFilterAssignee, setGanttFilterAssignee] = useState('all')
  type GanttGroupBy = 'none' | 'project' | 'assignee'
  const [ganttGroupBy, setGanttGroupBy] = useState<GanttGroupBy>('none')
  const [ganttSortKey, setGanttSortKey] = useState<'start' | 'assignee' | 'priority' | 'project' | 'title'>('start')
  const [ganttSortDir, setGanttSortDir] = useState<'asc' | 'desc'>('asc')
  const ganttDragRef = useRef<{ todoId: string; mode: 'move' | 'resize' | 'resize-left'; startX: number; origStart: string; origDuration: number } | null>(null)
  const ganttColDragRef = useRef<string | null>(null)
  const toggleField = (set: Set<string>, setFn: (s: Set<string>) => void, field: string) => { const n = new Set(set); if (n.has(field)) n.delete(field); else n.add(field); setFn(n) }

  // Bulk-select sets
  const [todoSelected, setTodoSelected] = useState<Set<string>>(new Set())
  const [blockerSelected, setBlockerSelected] = useState<Set<string>>(new Set())
  const [openSelected, setOpenSelected] = useState<Set<string>>(new Set())
  const [meetingSelected, setMeetingSelected] = useState<Set<string>>(new Set())
  const [projectSelected, setProjectSelected] = useState<Set<string>>(new Set())

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
      const [mems, mtgs, tds, blk, oi, act, prj, inbox] = await Promise.all([
        fetchTeamMembers(), fetchMeetings(), fetchTodos(), fetchBlockers(), fetchOpenItems(), fetchActivityLog(), fetchProjects(), fetchInboxItems()
      ])
      setInboxItems(inbox)
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
  // Reset inbox edit mode whenever any edit modal closes
  useEffect(() => { if (!editTodo && !editBlocker && !editOpen && !editMeeting) setInboxEditModeFor(null) }, [editTodo, editBlocker, editOpen, editMeeting])
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
  const handleSaveTodo = async (t: Todo) => {
    if (inboxEditModeFor) {
      const payload = { title: t.title, description: t.description, assignee: t.assignee, priority: t.priority, due_date: t.dueDate, status: t.status }
      setInboxItems(prev => prev.map(x => x.id === inboxEditModeFor ? { ...x, payload: { ...x.payload, ...payload } } : x))
      updateInboxItemPayload(inboxEditModeFor, payload).catch(() => {})
      setEditTodo(null); setInboxEditModeFor(null); return
    }
    setTodos(prev => prev.map(x => x.id === t.id ? t : x)); setEditTodo(null); try { await updateTodoFull(t.id, { title: t.title, description: t.description, assignee: t.assignee, priority: t.priority, status: t.status, due_date: t.dueDate, start_date: t.startDate, duration_days: t.durationDays, project_id: t.projectId, depends_on: t.dependsOn } as any) } catch { }
  }
  const handleResolveBlocker = async (b: Blocker) => { setBlockers(prev => prev.map(x => x.id === b.id ? { ...x, status: 'resolved' } : x)); try { await updateBlockerStatus(b.id, 'resolved') } catch { } }
  const handleDeleteBlocker = async (b: Blocker) => { setBlockers(prev => prev.filter(x => x.id !== b.id)); try { await deleteBlockerDb(b.id) } catch { } }
  const handleSaveBlocker = async (b: Blocker) => {
    if (inboxEditModeFor) {
      const payload = { title: b.title, description: b.description, reported_by: b.reportedBy, status: b.status }
      setInboxItems(prev => prev.map(x => x.id === inboxEditModeFor ? { ...x, payload: { ...x.payload, ...payload } } : x))
      updateInboxItemPayload(inboxEditModeFor, payload).catch(() => {})
      setEditBlocker(null); setInboxEditModeFor(null); return
    }
    setBlockers(prev => prev.map(x => x.id === b.id ? b : x)); setEditBlocker(null); try { await updateBlockerFull(b.id, { title: b.title, description: b.description, reported_by: b.reportedBy, status: b.status }) } catch { }
  }
  const handleCloseItem = async (o: OpenItem) => { setOpenItems(prev => prev.map(x => x.id === o.id ? { ...x, status: 'closed' } : x)); try { await updateOpenItemStatus(o.id, 'closed') } catch { } }
  const handleDeleteOpen = async (o: OpenItem) => { setOpenItems(prev => prev.filter(x => x.id !== o.id)); try { await deleteOpenItemDb(o.id) } catch { } }
  const handleSaveOpen = async (o: OpenItem) => {
    if (inboxEditModeFor) {
      const payload = { title: o.title, description: o.description, owner: o.owner, category: o.category, status: o.status }
      setInboxItems(prev => prev.map(x => x.id === inboxEditModeFor ? { ...x, payload: { ...x.payload, ...payload } } : x))
      updateInboxItemPayload(inboxEditModeFor, payload).catch(() => {})
      setEditOpen(null); setInboxEditModeFor(null); return
    }
    setOpenItems(prev => prev.map(x => x.id === o.id ? o : x)); setEditOpen(null); try { await updateOpenItemFull(o.id, { title: o.title, description: o.description, owner: o.owner, category: o.category, status: o.status }) } catch { }
  }
  const handleDeleteMeeting = async (m: Meeting) => { setMeetings(prev => prev.filter(x => x.id !== m.id)); try { await deleteMeetingDb(m.id) } catch { } }

  // ── Inbox handlers ──
  const handleInboxApprove = async (item: DbInboxItem) => {
    const p = item.payload
    try {
      if (item.entity_type === 'todo') {
        const c = await insertTodo({ title: p.title, description: p.description, assignee: p.assignee || 'Nicht zugeordnet', priority: p.priority || 'medium', due_date: p.due_date || null })
        setTodos(prev => [{ id: c.id, assignee: c.assignee, title: c.title, description: c.description || '', status: c.status, priority: c.priority, dueDate: c.due_date, startDate: null, durationDays: 1, dependsOn: [], meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev])
      } else if (item.entity_type === 'blocker') {
        const c = await insertBlocker({ title: p.title, description: p.description, reported_by: p.reported_by || 'Nicht zugeordnet' })
        setBlockers(prev => [{ id: c.id, reportedBy: c.reported_by, title: c.title, description: c.description || '', status: c.status, meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev])
      } else if (item.entity_type === 'open_item') {
        const c = await insertOpenItem({ title: p.title, description: p.description, owner: p.owner || 'Nicht zugeordnet', category: p.category || 'general' })
        setOpenItems(prev => [{ id: c.id, owner: c.owner, title: c.title, description: c.description || '', category: c.category, status: c.status, meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev])
      } else if (item.entity_type === 'meeting') {
        const c = await insertMeeting({ title: p.title, meeting_date: p.meeting_date, topics: p.topics || [], participants: p.participants || [], ai_summary: p.ai_summary, key_decisions: p.key_decisions || [] })
        setMeetings(prev => [{ id: c.id, title: c.title, date: c.meeting_date?.split('T')[0] || '', topics: c.topics || [], participants: c.participants || [], summary: c.ai_summary || '', keyDecisions: c.key_decisions || [] }, ...prev])
      }
      await approveInboxItem(item.id, 'approved')
      setInboxItems(prev => prev.filter(x => x.id !== item.id))
    } catch (e: any) { setError(e.message || 'Fehler beim Übernehmen') }
  }
  const handleInboxReject = async (id: string) => {
    setInboxItems(prev => prev.filter(x => x.id !== id))
    await deleteInboxItemDb(id).catch(() => {})
  }
  const handleInboxEdit = (item: DbInboxItem) => {
    const p = item.payload
    setInboxEditModeFor(item.id)
    if (item.entity_type === 'todo') {
      setEditTodo({ id: 'inbox_' + item.id, assignee: p.assignee || 'Nicht zugeordnet', title: p.title || '', description: p.description || '', status: p.status || 'open', priority: p.priority || 'medium', dueDate: p.due_date || null, startDate: null, durationDays: 1, dependsOn: [], meetingId: null, projectId: null, createdAt: '' })
    } else if (item.entity_type === 'blocker') {
      setEditBlocker({ id: 'inbox_' + item.id, reportedBy: p.reported_by || 'Nicht zugeordnet', title: p.title || '', description: p.description || '', status: p.status || 'active', meetingId: null, projectId: null, createdAt: '' })
    } else if (item.entity_type === 'open_item') {
      setEditOpen({ id: 'inbox_' + item.id, owner: p.owner || 'Nicht zugeordnet', title: p.title || '', description: p.description || '', category: p.category || 'general', status: p.status || 'open', meetingId: null, projectId: null, createdAt: '' })
    } else if (item.entity_type === 'meeting') {
      setEditMeeting({ id: 'inbox_' + item.id, title: p.title || '', date: p.meeting_date || '', topics: p.topics || [], participants: p.participants || [], summary: p.ai_summary || '', keyDecisions: p.key_decisions || [] })
    }
  }

  const handleBulkDeleteTodos = async () => { const ids = [...todoSelected]; setTodos(prev => prev.filter(x => !ids.includes(x.id))); setTodoSelected(new Set()); await Promise.all(ids.map(id => deleteTodoDb(id).catch(() => {}))) }
  const handleBulkDeleteBlockers = async () => { const ids = [...blockerSelected]; setBlockers(prev => prev.filter(x => !ids.includes(x.id))); setBlockerSelected(new Set()); await Promise.all(ids.map(id => deleteBlockerDb(id).catch(() => {}))) }
  const handleBulkDeleteOpen = async () => { const ids = [...openSelected]; setOpenItems(prev => prev.filter(x => !ids.includes(x.id))); setOpenSelected(new Set()); await Promise.all(ids.map(id => deleteOpenItemDb(id).catch(() => {}))) }
  const handleBulkDeleteMeetings = async () => { const ids = [...meetingSelected]; setMeetings(prev => prev.filter(x => !ids.includes(x.id))); setMeetingSelected(new Set()); await Promise.all(ids.map(id => deleteMeetingDb(id).catch(() => {}))) }
  const handleBulkDeleteProjects = async () => { const ids = [...projectSelected]; setProjects(prev => prev.filter(x => !ids.includes(x.id))); setProjectSelected(new Set()); await Promise.all(ids.map(id => deleteProjectDb(id).catch(() => {}))) }
  const handleSaveMeeting = async (m: Meeting) => {
    if (inboxEditModeFor) {
      const payload = { title: m.title, meeting_date: m.date, topics: m.topics, participants: m.participants, ai_summary: m.summary, key_decisions: m.keyDecisions }
      setInboxItems(prev => prev.map(x => x.id === inboxEditModeFor ? { ...x, payload: { ...x.payload, ...payload } } : x))
      updateInboxItemPayload(inboxEditModeFor, payload).catch(() => {})
      setEditMeeting(null); setInboxEditModeFor(null); return
    }
    setMeetings(prev => prev.map(x => x.id === m.id ? m : x)); setEditMeeting(null); try { await updateMeetingFull(m.id, { title: m.title, meeting_date: m.date, topics: m.topics, participants: m.participants, ai_summary: m.summary, key_decisions: m.keyDecisions }) } catch { }
  }
  const handleCreateTodo = async (t: Todo) => { setEditTodo(null); try { const c = await insertTodo({ title: t.title, description: t.description || undefined, assignee: t.assignee, priority: t.priority, due_date: t.dueDate || undefined } as any); setTodos(prev => [{ id: c.id, assignee: c.assignee, title: c.title, description: c.description || '', status: c.status, priority: c.priority, dueDate: c.due_date, startDate: t.startDate, durationDays: t.durationDays, dependsOn: [], meetingId: null, projectId: t.projectId, createdAt: new Date().toISOString().split('T')[0] }, ...prev]); if (t.startDate || t.projectId || t.durationDays > 1) { await updateTodoFull(c.id, { start_date: t.startDate, duration_days: t.durationDays, project_id: t.projectId } as any) } } catch { } }
  const handleCreateBlocker = async (b: Blocker) => { setEditBlocker(null); try { const c = await insertBlocker({ title: b.title, description: b.description || undefined, reported_by: b.reportedBy }); setBlockers(prev => [{ id: c.id, reportedBy: c.reported_by, title: c.title, description: c.description || '', status: c.status, meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev]) } catch { } }
  const handleCreateOpen = async (o: OpenItem) => { setEditOpen(null); try { const c = await insertOpenItem({ title: o.title, description: o.description || undefined, owner: o.owner, category: o.category }); setOpenItems(prev => [{ id: c.id, owner: c.owner, title: c.title, description: c.description || '', category: c.category, status: c.status, meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev]) } catch { } }
  const saveProjectRelations = async (projectId: string) => {
    // Save meeting links
    try { await setProjectMeetings(projectId, Array.from(projLinkedMeetingIds)) } catch {}
    // Create new todos from queue
    for (const td of projTodoQueue) {
      try {
        const c = await insertTodo({ title: td.title, description: td.description || undefined, assignee: td.assignee, priority: td.priority, due_date: td.dueDate || undefined } as any)
        await updateTodoFull(c.id, { project_id: projectId, start_date: td.startDate, duration_days: td.durationDays } as any)
        setTodos(prev => [{ ...td, id: c.id, projectId, createdAt: new Date().toISOString().split('T')[0] }, ...prev])
      } catch {}
    }
    // Link selected existing todos (if not already linked)
    for (const todoId of projLinkedTodoIds) {
      const todo = todos.find(t => t.id === todoId)
      if (todo && todo.projectId !== projectId) {
        try { await updateTodoFull(todoId, { project_id: projectId } as any); setTodos(prev => prev.map(t => t.id === todoId ? { ...t, projectId } : t)) } catch {}
      }
    }
    setProjTodoQueue([]); setProjLinkedTodoIds(new Set()); setProjLinkedMeetingIds(new Set())
  }
  const handleSaveProject = async (p: DbProject) => {
    if (p.id === '__new__') {
      setEditProject(null)
      try {
        const c = await insertProject({ name: p.name, description: p.description || undefined, start_date: p.start_date || undefined, end_date: p.end_date || undefined, owner: p.owner || undefined, priority: p.priority || 'medium' })
        setProjects(prev => [...prev, c])
        await saveProjectRelations(c.id)
      } catch {}
    } else {
      setProjects(prev => prev.map(x => x.id === p.id ? p : x)); setEditProject(null)
      try { await updateProjectFull(p.id, { name: p.name, description: p.description, status: p.status, start_date: p.start_date, end_date: p.end_date, owner: p.owner, priority: p.priority }) } catch {}
      await saveProjectRelations(p.id)
    }
  }
  const handleOpenProjectDialog = (p: DbProject | '__new__') => {
    if (p === '__new__') {
      setEditProject({ id: '__new__', name: '', description: null, status: 'active', start_date: null, end_date: null, owner: null, priority: 'medium', created_at: '', updated_at: '' } as DbProject)
      setProjLinkedTodoIds(new Set()); setProjLinkedMeetingIds(new Set())
    } else {
      setEditProject({...p})
      setProjLinkedTodoIds(new Set(todos.filter(t => t.projectId === p.id).map(t => t.id)))
      fetchProjectMeetings(p.id).then(ids => setProjLinkedMeetingIds(new Set(ids))).catch(() => {})
    }
    setProjTodoQueue([]); setProjTodoNewForm(null); setProjTodoSearch(''); setProjTodoPickerOpen(false); setProjMeetingSearch(''); setProjMeetingPickerOpen(false); setProjectInitTodos('')
  }
  const handleDeleteProject = async (p: DbProject) => { setProjects(prev => prev.filter(x => x.id !== p.id)); try { await deleteProjectDb(p.id) } catch { } }

  const handleQuickStatusToggle = async (t: Todo) => {
    const newStatus = t.status === 'done' ? 'open' : 'done'
    setTodos(prev => prev.map(x => x.id === t.id ? { ...x, status: newStatus } : x))
    try { await updateTodoStatus(t.id, newStatus) } catch { setTodos(prev => prev.map(x => x.id === t.id ? { ...x, status: t.status } : x)) }
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

  const kanbanTodosMemo = useMemo(() => {
    const priOrd: Record<string, number> = { urgent: 0, critical: 0, high: 1, medium: 2, low: 3 }
    let result = [...todos]
    if (kanbanFilterProject !== 'all') result = result.filter(t => t.projectId === kanbanFilterProject)
    if (kanbanFilterAssignee !== 'all') result = result.filter(t => t.assignee === kanbanFilterAssignee)
    result.sort((a, b) => {
      let cmp = 0
      if (kanbanSortKey === 'start') cmp = (a.startDate || '9').localeCompare(b.startDate || '9')
      else if (kanbanSortKey === 'priority') cmp = (priOrd[a.priority] ?? 9) - (priOrd[b.priority] ?? 9)
      else if (kanbanSortKey === 'assignee') cmp = a.assignee.localeCompare(b.assignee)
      else if (kanbanSortKey === 'title') cmp = a.title.localeCompare(b.title)
      else if (kanbanSortKey === 'project') cmp = (getProjectName(a.projectId) || '').localeCompare(getProjectName(b.projectId) || '')
      return kanbanSortDir === 'asc' ? cmp : -cmp
    })
    return result
  }, [todos, kanbanFilterProject, kanbanFilterAssignee, kanbanSortKey, kanbanSortDir, projects])

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
  const editSourceEntity = (entityType: string, entityId: string) => {
    switch (entityType) {
      case 'todo': { const t = todos.find(x => x.id === entityId); if (t) setEditTodo({...t}); break }
      case 'blocker': { const b = blockers.find(x => x.id === entityId); if (b) setEditBlocker({...b}); break }
      case 'open_item': { const o = openItems.find(x => x.id === entityId); if (o) setEditOpen({...o}); break }
      case 'meeting': { const m = meetings.find(x => x.id === entityId); if (m) setEditMeeting({...m}); break }
      case 'project': { const p = projects.find(x => x.id === entityId); if (p) handleOpenProjectDialog(p); break }
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
    if (!q) return { meetings: [] as Meeting[] }
    const matchMeetings = meetings
      .filter(m => !q || textMatch(m, q))
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, 10)
    return { meetings: matchMeetings }
  }, [globalSearch, meetings])

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

  // Clear global search when navigating away from Textsuche
  const prevPageRef = useRef<Page>(page)
  useEffect(() => {
    if (prevPageRef.current === 'textsuche' && page !== 'textsuche') { setGlobalSearch(''); setSearchFocused(false) }
    prevPageRef.current = page
  }, [page])

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
      else if (ganttSortKey === 'title') { va = a.title; vb = b.title }
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
    return depEnd > dependent.startDate
  }

  const projectTodos = (pid: string) => todos.filter(t => t.projectId === pid)
  const projectBlockers = (pid: string) => blockers.filter(b => b.projectId === pid)

  if (loading) return <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--syn-bg)' }}><div className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Lade Daten...</div></div>
  if (error && todos.length === 0) return <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--syn-bg)' }}><div className="text-sm" style={{ color: 'var(--syn-danger)' }}>Fehler: {error}</div></div>

  const navSections: { label: string; items: { key: Page; label: string; icon: string; count?: number }[] }[] = [
    { label: 'ÜBERBLICK', items: [
      { key: 'uebersicht', label: 'Command Center', icon: '⬡' },
      { key: 'inbox', label: 'Inbox', icon: '⬇', count: inboxItems.length },
      { key: 'sitzungen', label: 'Meetings', icon: '☰', count: meetings.length },
      { key: 'aktionen', label: 'Aktionen', icon: '✓', count: todos.filter(t => t.status !== 'done').length + blockers.filter(b => b.status === 'active').length },
    ]},
    { label: 'PLANUNG', items: [
      { key: 'projekte', label: 'Projekte', icon: '◈', count: projects.length },
    ]},
    { label: 'SUCHE', items: [
      { key: 'ki', label: 'AI-Suche', icon: '◉' },
      { key: 'textsuche', label: 'Textsuche', icon: '⌕' },
      { key: 'protokoll', label: 'Aktivität', icon: '⏱', count: filteredLog.length },
    ]},
  ]

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--syn-bg)', color: 'var(--syn-text)' }}>
      {/* ═══ SIDEBAR ═══ */}
      <aside className={`${sidebarCollapsed ? 'w-14' : 'w-52'} glass-sidebar flex flex-col shrink-0 transition-[width] duration-200 sticky top-0 h-screen border-r border-[var(--syn-line)]`} style={{ overflow: 'clip' }}>
        <div className="flex items-center h-14 border-b border-[var(--syn-line)]" style={{ overflow: 'clip' }}>
          <div className="w-14 flex items-center justify-center shrink-0">
            <div className="w-7 h-7 rounded-md flex items-center justify-center" style={{ background: 'var(--syn-accent)' }}>
              <svg width="16" height="16" viewBox="0 0 18 18" fill="none"><path d="M9 1L16 5V13L9 17L2 13V5Z" stroke="white" strokeWidth="1.5" fill="none"/><circle cx="9" cy="9" r="2.5" fill="white"/></svg>
            </div>
          </div>
          {!sidebarCollapsed && <span className="font-semibold text-sm tracking-tight whitespace-nowrap" style={{ color: 'var(--syn-text)' }}>Meeting OS</span>}
        </div>
        <nav className="flex-1 py-3 overflow-x-hidden" style={{ overflowY: 'auto', scrollbarGutter: 'stable' }}>
          {navSections.map((section, si) => (
            <div key={si} className={si > 0 ? 'mt-4' : ''}>
              {/* Spacer: same h-[22px] whether label is shown or not */}
              <div className="h-[22px]">
                {!sidebarCollapsed && <div className="pl-[22px] text-[10px] font-semibold tracking-widest whitespace-nowrap" style={{ color: 'var(--syn-text-faint)' }}>{section.label}</div>}
              </div>
              <div className="space-y-0.5">
                {section.items.map(n => (
                  <button key={n.key} onClick={() => setPage(n.key)}
                    className={`w-full flex items-center py-2 rounded-lg text-sm transition-colors whitespace-nowrap ${page === n.key ? 'bg-[var(--syn-accent-soft)] text-[var(--syn-accent)]' : 'hover:bg-[var(--syn-hover)]'}`}
                    style={page !== n.key ? { color: 'var(--syn-text-muted)' } : {}}>
                    <span className="w-14 text-base text-center shrink-0">{n.icon}</span>
                    {!sidebarCollapsed && <><span className="flex-1 text-left whitespace-nowrap">{n.label}</span>{n.count != null && n.count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded-full whitespace-nowrap mr-3" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>{n.count}</span>}</>}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="border-t border-[var(--syn-line)] py-3 space-y-1">
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="w-full flex items-center py-2 rounded-lg text-sm hover:bg-[var(--syn-hover)] transition-colors whitespace-nowrap" style={{ color: 'var(--syn-text-faint)' }}>
            <span className="w-14 text-base text-center shrink-0">{sidebarCollapsed ? '❯' : '❮'}</span>{!sidebarCollapsed && <span className="whitespace-nowrap">Einklappen</span>}
          </button>
          <button onClick={onLogout} className="w-full flex items-center py-2 rounded-lg text-sm hover:bg-[var(--syn-hover)] transition-colors whitespace-nowrap" style={{ color: 'var(--syn-text-faint)' }}>
            <span className="w-14 text-base text-center shrink-0">{'⏻'}</span>{!sidebarCollapsed && <span className="whitespace-nowrap">Abmelden</span>}
          </button>
        </div>
      </aside>

      {/* ═══ MAIN ═══ */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="glass-header border-b border-[var(--syn-line)] h-14 flex items-center px-6 gap-4 shrink-0 sticky top-0 z-20">
          <div ref={searchRef} className="relative">
            <Input placeholder="Meetings durchsuchen..." value={globalSearch} onChange={e => { setGlobalSearch(e.target.value); setSearchFocused(true) }} onFocus={() => setSearchFocused(true)} onKeyDown={e => { if (e.key === 'Enter' && globalSearch.trim()) { setSearchFocused(false); setPage('textsuche' as any) } if (e.key === 'Escape') setSearchFocused(false) }} className="h-8 text-sm w-72 bg-[var(--syn-surface-2)] border-[var(--syn-line)] pr-8" />
            {globalSearch && (
              <button onClick={() => { setGlobalSearch(''); setSearchFocused(false) }} className="absolute right-2 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full flex items-center justify-center hover:bg-[var(--syn-hover)] transition-colors text-xs" style={{ color: 'var(--syn-text-faint)' }}>✕</button>
            )}
            {searchFocused && globalSearch.trim() && searchResults.meetings.length > 0 && (
              <div className="absolute top-full left-0 mt-1 w-[430px] rounded-xl border border-[var(--syn-line)] shadow-xl z-50 overflow-hidden max-h-[70vh] overflow-y-auto" style={{ background: 'var(--syn-bg)' }}>
                <div className="px-3 py-2 text-[10px] font-semibold tracking-widest uppercase" style={{ color: 'var(--syn-text-faint)', background: 'var(--syn-surface-2)' }}>Meetings ({searchResults.meetings.length})</div>
                {searchResults.meetings.map(m => (
                  <button key={m.id} onClick={() => { setGlobalSearch(''); setSearchFocused(false); setViewMeeting(m) }} className="w-full text-left px-3 py-2 text-sm hover:bg-[var(--syn-hover)] transition-colors flex items-center gap-2">
                    <span className="text-xs shrink-0">☰</span><span className="truncate">{m.title}</span><span className="text-[10px] ml-auto shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{m.date}</span>
                  </button>
                ))}
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
            const reviewQueue = meetings.slice(0, 10)
            const activeBlockersList = blockers.filter(b => b.status === 'active')
            const recentDec = meetings.flatMap(m => m.keyDecisions.map(d => ({ text: d, meetingTitle: m.title, meetingDate: m.date, meetingId: m.id }))).slice(0, 10)
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
                  <div className="flex items-center gap-3 shrink-0">
                  <Button size="sm" className="bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white text-xs gap-1.5 h-9" onClick={() => setEditTodo({ id: '__new__', assignee: 'Nicht zugeordnet', title: '', description: '', status: 'open', priority: 'medium', dueDate: null, startDate: null, durationDays: 1, dependsOn: [], meetingId: null, projectId: null, createdAt: '' })}>+ Neuer Todo</Button>
                  <div className="glass-card rounded-xl border border-[var(--syn-line)] px-6 py-3 flex items-center gap-6 shrink-0">
                    <div className="text-center"><div className="text-xl font-bold" style={{ color: 'var(--syn-accent)' }}>{meetings.length}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Meetings</div></div>
                    <div className="w-px h-8" style={{ background: 'var(--syn-line)' }} />
                    <div className="text-center"><div className="text-xl font-bold" style={{ color: 'var(--syn-warn)' }}>{todos.filter(t => t.status !== 'done').length}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Offene Todos</div></div>
                    <div className="w-px h-8" style={{ background: 'var(--syn-line)' }} />
                    <div className="text-center"><div className="text-xl font-bold" style={{ color: 'var(--syn-danger)' }}>{activeBlockersList.length}</div><div className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Aktive Blocker</div></div>
                  </div>
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

                {/* 2x2 Grid: left 1/3, right 2/3, rows identical height */}
                <div className="grid grid-cols-[1fr_2fr] gap-5">
                  {(() => {
                    const cardClass = "rounded-xl border border-[var(--syn-line)] overflow-hidden flex flex-col"
                    const cardStyle = { background: 'var(--syn-surface)', height: 290 }
                    const headerClass = "flex items-center justify-between px-4 h-10 border-b border-[var(--syn-line)] shrink-0"
                    const listClass = "divide-y divide-[var(--syn-line)] flex-1 overflow-y-auto"
                    const itemClass = "px-4 h-[52px] flex flex-col justify-center hover:bg-[var(--syn-hover)] transition-colors cursor-pointer"
                    const subClass = "flex items-center gap-1.5 h-5 text-[11px] leading-tight"
                    return <>
                      {/* Top-left: Offene Todos */}
                      <div className={cardClass} style={cardStyle}>
                        <div className={headerClass}>
                          <div className="flex items-center gap-2 text-sm font-semibold"><span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-warn)' }} /> Offene Todos</div>
                          <button onClick={() => { setActionTab('todos'); setPage('aktionen'); window.scrollTo(0, 0) }} className="text-[11px] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>Alle Todos →</button>
                        </div>
                        <div className={listClass} style={{ minHeight: 0 }}>
                          {todos.filter(t => t.status !== 'done').length === 0 && <div className="px-4 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine offenen Todos.</div>}
                          {todos.filter(t => t.status !== 'done').sort((a, b) => (PRI_RANK[a.priority] ?? 9) - (PRI_RANK[b.priority] ?? 9)).slice(0, 10).map(t => (
                            <div key={t.id} className={itemClass} onClick={() => setViewTodo(t)}>
                              <div className="flex items-center gap-2">
                                <button onClick={(e) => { e.stopPropagation(); handleQuickStatusToggle(t) }} className="w-4 h-4 rounded border shrink-0 flex items-center justify-center transition-colors hover:border-[var(--syn-accent)] hover:bg-[var(--syn-accent-soft)]" style={{ borderColor: 'var(--syn-line)' }} />
                                <div className="flex-1 min-w-0 text-sm truncate">{t.title}</div>
                              </div>
                              <div className={subClass} style={{ color: 'var(--syn-text-faint)', paddingLeft: 24 }}>
                                <Badge className={`text-[10px] leading-none py-0.5 px-1.5 ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]}</Badge>
                                <span>{t.assignee}</span>
                                {t.dueDate && <span>· {t.dueDate}</span>}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Top-right: Letzte Meetings */}
                      <div className={cardClass} style={cardStyle}>
                        <div className={headerClass}>
                          <div className="flex items-center gap-2 text-sm font-semibold"><span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-accent)' }} /> Letzte Meetings</div>
                          <button onClick={() => setPage('sitzungen')} className="text-[11px] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>Alle Meetings →</button>
                        </div>
                        <div className={listClass} style={{ minHeight: 0 }}>
                          {reviewQueue.length === 0 && <div className="px-4 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Meetings vorhanden.</div>}
                          {reviewQueue.map(m => (
                            <div key={m.id} className={itemClass} onClick={() => setViewMeeting(m)}>
                              <div className="text-sm font-medium truncate">{m.title}</div>
                              <div className={subClass} style={{ color: 'var(--syn-text-faint)' }}>
                                <span>{m.date}</span>
                                <span>· {m.participants.slice(0, 3).join(', ')}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Bottom-left: Aktive Blocker */}
                      <div className={cardClass} style={cardStyle}>
                        <div className={headerClass}>
                          <div className="flex items-center gap-2 text-sm font-semibold"><span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-danger)' }} /> Aktive Blocker</div>
                          <button onClick={() => { setActionTab('blocker'); setPage('aktionen'); window.scrollTo(0, 0) }} className="text-[11px] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>Alle Blocker →</button>
                        </div>
                        <div className={listClass} style={{ minHeight: 0 }}>
                          {activeBlockersList.length === 0 && <div className="px-4 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine aktiven Blocker.</div>}
                          {activeBlockersList.slice(0, 10).map(b => (
                            <div key={b.id} className={itemClass} onClick={() => setViewBlocker(b)}>
                              <div className="text-sm truncate">{b.title}</div>
                              <div className={subClass} style={{ color: 'var(--syn-text-faint)' }}>
                                <Badge className={`text-[10px] leading-none py-0.5 px-1.5 ${ST_STYLE[b.status]}`}>{ST_LABEL[b.status]}</Badge>
                                <span>{b.reportedBy}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Bottom-right: Letzte Entscheidungen */}
                      <div className={cardClass} style={cardStyle}>
                        <div className={headerClass}>
                          <div className="flex items-center gap-2 text-sm font-semibold"><span className="w-2 h-2 rounded-full" style={{ background: 'var(--syn-info)' }} /> Letzte Entscheidungen</div>
                          <button onClick={() => setPage('protokoll')} className="text-[11px] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>Audit-Trail →</button>
                        </div>
                        <div className={listClass} style={{ minHeight: 0 }}>
                          {recentDec.length === 0 && <div className="px-4 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Entscheidungen.</div>}
                          {recentDec.map((d, i) => (
                            <div key={i} className={itemClass} onClick={() => { const m = meetings.find(mt => mt.id === d.meetingId); if (m) setViewMeeting(m) }}>
                              <div className="text-sm truncate">{d.text}</div>
                              <div className={subClass} style={{ color: 'var(--syn-text-faint)' }}>
                                <span>{d.meetingDate}</span>
                                <span className="text-[10px] leading-none py-0.5 px-1.5 rounded" style={{ background: 'var(--syn-accent-soft)', color: 'var(--syn-accent)' }}>{d.meetingTitle}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  })()}
                </div>
              </div>
            )
          })()}

          {/* ═══ INBOX ═══ */}
          {page === 'inbox' && (() => {
            const ib = { meetings: inboxItems.filter(i => i.entity_type === 'meeting').slice(0,10), todos: inboxItems.filter(i => i.entity_type === 'todo').slice(0,10), blockers: inboxItems.filter(i => i.entity_type === 'blocker').slice(0,10), open: inboxItems.filter(i => i.entity_type === 'open_item').slice(0,10) }
            const FreigabeCell = ({ item }: { item: DbInboxItem }) => (
              <TableCell onClick={e => e.stopPropagation()}>
                <div className="flex gap-1 items-center justify-center">
                  <button onClick={() => handleInboxEdit(item)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }} title="Bearbeiten">✎</button>
                  <button onClick={() => handleInboxApprove(item)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-ok)]/10 transition-colors" style={{ color: 'var(--syn-ok)' }} title="Übernehmen">✓</button>
                  <button onClick={() => handleInboxReject(item.id)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-danger)]/10 hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }} title="Ablehnen">✕</button>
                </div>
              </TableCell>
            )
            const SectionHeader = ({ dot, label, count }: { dot: string; label: string; count: number }) => (
              <div className="flex items-center gap-2 mb-2">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: dot }} />
                <h3 className="text-sm font-semibold">{label}</h3>
                <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>{count}</span>
              </div>
            )
            return (
              <div className="space-y-6">
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold">Inbox</h2>
                  {inboxItems.length > 0 && <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: 'var(--syn-warn-soft)', color: 'var(--syn-warn)' }}>{inboxItems.length} ausstehend</span>}
                </div>
                {inboxItems.length === 0 && (
                  <div className="rounded-xl border border-[var(--syn-line)] py-14 flex flex-col items-center gap-2" style={{ background: 'var(--syn-surface)' }}>
                    <p className="text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine ausstehenden Einträge</p>
                    <p className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Sobald Make ein Szenario ausführt, landen neue Einträge hier.</p>
                  </div>
                )}
                {/* Meetings */}
                {ib.meetings.length > 0 && (
                  <section>
                    <SectionHeader dot="var(--syn-accent)" label="Meetings" count={ib.meetings.length} />
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <TableHead className="w-[110px] text-xs text-center">Datum</TableHead>
                      <SH label="Titel" field="title" sort={{ col: null, dir: null }} onSort={() => {}} />
                      <TableHead className="w-[200px] text-xs text-center">Teilnehmer</TableHead>
                      <TableHead className="w-[200px] text-xs text-center">Themen</TableHead>
                      <TableHead className="w-[70px] text-xs text-center">Entsch.</TableHead>
                      <TableHead className="w-[110px] text-xs text-center">Freigabe</TableHead>
                    </TableRow></TableHeader><TableBody>
                      {ib.meetings.map(item => { const p = item.payload; return (
                        <TableRow key={item.id} className="text-sm border-[var(--syn-line)] hover:bg-[var(--syn-hover)]">
                          <TableCell className="text-xs font-medium text-center" style={{ color: 'var(--syn-text-muted)' }}>{p.meeting_date || '—'}</TableCell>
                          <TableCell className="text-left font-medium">{p.title || '—'}</TableCell>
                          <TableCell><div className="flex flex-nowrap gap-1 items-center overflow-hidden">{(p.participants||[]).slice(0,2).map((pt: string,i: number)=><span key={i} className="text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap shrink-0" style={{background:'var(--syn-surface-3)',color:'var(--syn-text-muted)',maxWidth:'88px',textOverflow:'ellipsis'}}>{pt}</span>)}{(p.participants||[]).length>2&&<span className="text-[10px] font-medium shrink-0" style={{color:'var(--syn-text-faint)'}}>+{(p.participants||[]).length-2}</span>}</div></TableCell>
                          <TableCell><div className="flex flex-nowrap gap-1 items-center overflow-hidden">{(p.topics||[]).slice(0,2).map((t: string,i: number)=><Badge key={i} variant="outline" className="text-[9px] border-[var(--syn-line)] whitespace-nowrap shrink-0 overflow-hidden" style={{maxWidth:'88px',textOverflow:'ellipsis'}}>{t}</Badge>)}{(p.topics||[]).length>2&&<span className="text-[10px] font-medium shrink-0" style={{color:'var(--syn-text-faint)'}}>+{(p.topics||[]).length-2}</span>}</div></TableCell>
                          <TableCell className="text-xs text-center">{(p.key_decisions||[]).length>0?<span className="font-medium">{(p.key_decisions||[]).length}</span>:'—'}</TableCell>
                          <FreigabeCell item={item} />
                        </TableRow>
                      )})}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
                {/* Todos */}
                {ib.todos.length > 0 && (
                  <section>
                    <SectionHeader dot="var(--syn-warn)" label="Todos" count={ib.todos.length} />
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <SH label="Aufgabe" field="title" sort={{ col: null, dir: null }} onSort={() => {}} />
                      <SH label="Zuständig" field="assignee" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[130px]" />
                      <SH label="Priorität" field="priority" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[100px]" />
                      <SH label="Fällig" field="due_date" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[100px]" />
                      <SH label="Status" field="status" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[100px]" />
                      <TableHead className="w-[110px] text-xs text-center">Freigabe</TableHead>
                    </TableRow></TableHeader><TableBody>
                      {ib.todos.map(item => { const p = item.payload; return (
                        <TableRow key={item.id} className="text-sm border-[var(--syn-line)] hover:bg-[var(--syn-hover)]">
                          <TableCell className="text-left"><span className="font-medium">{p.title||'—'}</span>{p.description&&<div className="text-xs truncate max-w-sm" style={{color:'var(--syn-text-faint)'}}>{p.description}</div>}</TableCell>
                          <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={p.assignee||'?'}/><span className="text-xs">{p.assignee||'—'}</span></div></TableCell>
                          <TableCell><Badge className={`text-[10px] ${PRI_STYLE[p.priority]||''}`}>{PRI_LABEL[p.priority]||p.priority||'—'}</Badge></TableCell>
                          <TableCell className="text-xs" style={{color:'var(--syn-text-muted)'}}>{p.due_date||'—'}</TableCell>
                          <TableCell><Badge className={`text-[10px] ${ST_STYLE[p.status]||''}`}>{ST_LABEL[p.status]||p.status||'—'}</Badge></TableCell>
                          <FreigabeCell item={item} />
                        </TableRow>
                      )})}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
                {/* Blocker */}
                {ib.blockers.length > 0 && (
                  <section>
                    <SectionHeader dot="var(--syn-danger)" label="Blocker" count={ib.blockers.length} />
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <SH label="Blocker" field="title" sort={{ col: null, dir: null }} onSort={() => {}} />
                      <SH label="Zuständig" field="reported_by" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[130px]" />
                      <SH label="Status" field="status" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[100px]" />
                      <TableHead className="w-[110px] text-xs text-center">Freigabe</TableHead>
                    </TableRow></TableHeader><TableBody>
                      {ib.blockers.map(item => { const p = item.payload; return (
                        <TableRow key={item.id} className="text-sm border-[var(--syn-line)] hover:bg-[var(--syn-hover)]">
                          <TableCell className="text-left"><span className="font-medium">{p.title||'—'}</span>{p.description&&<div className="text-xs truncate max-w-md" style={{color:'var(--syn-text-faint)'}}>{p.description}</div>}</TableCell>
                          <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={p.reported_by||'?'}/><span className="text-xs">{p.reported_by||'—'}</span></div></TableCell>
                          <TableCell><Badge className={`text-[10px] ${ST_STYLE[p.status]||''}`}>{ST_LABEL[p.status]||p.status||'—'}</Badge></TableCell>
                          <FreigabeCell item={item} />
                        </TableRow>
                      )})}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
                {/* Offene Punkte */}
                {ib.open.length > 0 && (
                  <section>
                    <SectionHeader dot="var(--syn-info)" label="Offene Punkte" count={ib.open.length} />
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <TableHead className="w-10"></TableHead>
                      <SH label="Item" field="title" sort={{ col: null, dir: null }} onSort={() => {}} />
                      <SH label="Kategorie" field="category" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[100px]" />
                      <SH label="Zuständig" field="owner" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[130px]" />
                      <SH label="Status" field="status" sort={{ col: null, dir: null }} onSort={() => {}} className="w-[100px]" />
                      <TableHead className="w-[110px] text-xs text-center">Freigabe</TableHead>
                    </TableRow></TableHeader><TableBody>
                      {ib.open.map(item => { const p = item.payload; return (
                        <TableRow key={item.id} className="text-sm border-[var(--syn-line)] hover:bg-[var(--syn-hover)]">
                          <TableCell className="text-center">{CAT_ICON[p.category]||'○'}</TableCell>
                          <TableCell className="text-left"><span>{p.title||'—'}</span>{p.description&&<div className="text-xs truncate max-w-sm" style={{color:'var(--syn-text-faint)'}}>{p.description}</div>}</TableCell>
                          <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-line)]">{CAT_LABEL[p.category]||p.category||'—'}</Badge></TableCell>
                          <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={p.owner||'?'}/><span className="text-xs">{p.owner||'—'}</span></div></TableCell>
                          <TableCell><Badge className={`text-[10px] ${ST_STYLE[p.status]||''}`}>{ST_LABEL[p.status]||p.status||'—'}</Badge></TableCell>
                          <FreigabeCell item={item} />
                        </TableRow>
                      )})}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
              </div>
            )
          })()}

          {/* ═══ SITZUNGEN ═══ */}
          {page === 'sitzungen' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold">Meetings</h2>
                  {meetingSelected.size > 0 && <button onClick={handleBulkDeleteMeetings} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${meetingSelected.size} löschen`}><TrashIcon /></button>}
                </div>
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
                <TableHead className="w-[200px] text-xs text-center">Teilnehmer</TableHead>
                <TableHead className="w-[200px] text-xs text-center">Themen</TableHead>
                <TableHead className="w-[80px] text-xs text-center">Entsch.</TableHead>
                <TableHead className="w-[90px] text-xs text-center">Anpassen</TableHead>
              </TableRow></TableHeader><TableBody>
                {filteredNotes.map(m => (
                  <TableRow key={m.id} className={`text-sm cursor-pointer select-none border-[var(--syn-line)] group ${meetingSelected.has(m.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => setMeetingSelected(prev => { const n = new Set(prev); n.has(m.id) ? n.delete(m.id) : n.add(m.id); return n })}>
                    <TableCell className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>{m.date}</TableCell>
                    <TableCell className="text-left font-medium"><button onClick={e => { e.stopPropagation(); setViewMeeting(m) }} className="text-left hover:text-[var(--syn-accent)]">{m.title}</button></TableCell>
                    <TableCell><div className="flex flex-nowrap gap-1 items-center overflow-hidden">{m.participants.slice(0, 2).map((p, i) => <span key={i} className="text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap overflow-hidden shrink-0" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)', maxWidth: '88px', textOverflow: 'ellipsis' }}>{p}</span>)}{m.participants.length > 2 && <span className="text-[10px] font-medium shrink-0" style={{ color: 'var(--syn-text-faint)' }}>+{m.participants.length - 2}</span>}</div></TableCell>
                    <TableCell><div className="flex flex-nowrap gap-1 items-center overflow-hidden">{m.topics.slice(0, 2).map((t, i) => <Badge key={i} variant="outline" className="text-[9px] border-[var(--syn-line)] whitespace-nowrap shrink-0 overflow-hidden" style={{ maxWidth: '88px', textOverflow: 'ellipsis' }}>{t}</Badge>)}{m.topics.length > 2 && <span className="text-[10px] font-medium shrink-0" style={{ color: 'var(--syn-text-faint)' }}>+{m.topics.length - 2}</span>}</div></TableCell>
                    <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{m.keyDecisions.length > 0 ? <span className="font-medium">{m.keyDecisions.length}</span> : '—'}</TableCell>
                    <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center"><button onClick={() => setEditMeeting({...m})} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => setConfirmDelete({ label: m.title, action: () => handleDeleteMeeting(m) })} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button><input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${meetingSelected.has(m.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={meetingSelected.has(m.id)} onChange={() => setMeetingSelected(prev => { const n = new Set(prev); n.has(m.id) ? n.delete(m.id) : n.add(m.id); return n })} /></div></TableCell>
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
                  {([['todos', 'Todos', todos.filter(t => t.status !== 'done').length], ['blocker', 'Blocker', blockers.filter(b => b.status === 'active').length], ['open', 'Offene Punkte', openItems.filter(o => o.status !== 'closed').length]] as [ActionTab, string, number][]).map(([k, l, c]) => (
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
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => setEditTodo({ id: '__new__', assignee: 'Nicht zugeordnet', title: '', description: '', status: 'open', priority: 'medium', dueDate: null, startDate: null, durationDays: 1, dependsOn: [], meetingId: null, projectId: null, createdAt: '' })}>+ Neu</Button>
                      {todoSelected.size > 0 && <button onClick={handleBulkDeleteTodos} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${todoSelected.size} löschen`}><TrashIcon /></button>}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Input placeholder="Suche..." value={todoSearch} onChange={e => setTodoSearch(e.target.value)} className="h-8 text-xs w-[150px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                      <Select value={todoFilterAssignee} onValueChange={setTodoFilterAssignee}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Mitglieder</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                      <Select value={todoFilterDue} onValueChange={setTodoFilterDue}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Termine</SelectItem><SelectItem value="overdue">Überfällig</SelectItem><SelectItem value="this_week">Diese Woche</SelectItem><SelectItem value="no_date">Ohne Datum</SelectItem></SelectContent></Select>
                      <Select value={todoFilterStatus} onValueChange={setTodoFilterStatus}><SelectTrigger className="h-8 text-xs w-[120px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="open">Offen</SelectItem><SelectItem value="in_progress">In Arbeit</SelectItem><SelectItem value="done">Erledigt</SelectItem></SelectContent></Select>
                      {projects.length > 0 && <Select value={todoFilterProject} onValueChange={setTodoFilterProject}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Projekte</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>}
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                    <SH label="Aufgabe" field="title" sort={todoSort} onSort={todoSort.toggle} />
                    <SH label="Zuständig" field="assignee" sort={todoSort} onSort={todoSort.toggle} className="w-[130px]" />
                    <SH label="Priorität" field="priority" sort={todoSort} onSort={todoSort.toggle} className="w-[100px]" />
                    <SH label="Fällig" field="dueDate" sort={todoSort} onSort={todoSort.toggle} className="w-[100px]" />
                    <SH label="Status" field="status" sort={todoSort} onSort={todoSort.toggle} className="w-[100px]" />
                    <SH label="Erstellt" field="createdAt" sort={todoSort} onSort={todoSort.toggle} className="w-[100px]" />
                    <TableHead className="w-[140px] text-xs text-center">Quelle</TableHead>
                    {projects.length > 0 && <TableHead className="w-[120px] text-xs text-center">Projekt</TableHead>}
                    <TableHead className="w-[90px] text-xs text-center">Anpassen</TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredTodos.map(t => { const overdue = t.dueDate && t.dueDate < today && t.status !== 'done'; return (
                      <TableRow key={t.id} className={`text-sm border-[var(--syn-line)] group select-none ${t.status === 'done' ? 'opacity-40' : ''} ${todoSelected.has(t.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => setTodoSelected(prev => { const n = new Set(prev); n.has(t.id) ? n.delete(t.id) : n.add(t.id); return n })}>
                        <TableCell className="text-left"><div className="flex items-center gap-2"><button onClick={e => { e.stopPropagation(); cycleTodo(t) }} className="w-4 h-4 rounded border shrink-0 flex items-center justify-center transition-colors hover:border-[var(--syn-accent)] hover:bg-[var(--syn-accent-soft)]" style={{ borderColor: 'var(--syn-line)' }} /><div className="min-w-0"><button onClick={e => { e.stopPropagation(); setViewTodo(t) }} className={`text-left hover:text-[var(--syn-accent)] ${t.status === 'done' ? 'line-through' : ''}`}>{t.title}</button>{t.description && <div className="text-xs truncate max-w-sm" style={{ color: 'var(--syn-text-faint)' }}>{t.description}</div>}</div></div></TableCell>
                        <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={t.assignee} /><span className="text-xs">{t.assignee}</span></div></TableCell>
                        <TableCell><Badge className={`text-[10px] ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority] || t.priority}</Badge></TableCell>
                        <TableCell className={`text-xs ${overdue ? 'text-[var(--syn-danger)] font-bold' : ''}`} style={!overdue ? { color: 'var(--syn-text-muted)' } : {}}>{t.dueDate || '—'}</TableCell>
                        <TableCell><Badge className={`text-[10px] ${ST_STYLE[t.status]}`}>{ST_LABEL[t.status]}</Badge></TableCell>
                        <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{t.createdAt || '—'}</TableCell>
                        <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}><SourceChip meeting={getMeeting(t.meetingId) || null} onClick={() => { const m = getMeeting(t.meetingId); if (m) setViewMeeting(m) }} /></TableCell>
                        {projects.length > 0 && <TableCell className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>{getProjectName(t.projectId) || '—'}</TableCell>}
                        <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center"><button onClick={() => setEditTodo({...t})} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => setConfirmDelete({ label: t.title, action: () => handleDeleteTodo(t) })} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button><input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${todoSelected.has(t.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={todoSelected.has(t.id)} onChange={() => setTodoSelected(prev => { const n = new Set(prev); n.has(t.id) ? n.delete(t.id) : n.add(t.id); return n })} /></div></TableCell>
                      </TableRow>
                    )})}
                    {filteredTodos.length === 0 && <TableRow><TableCell colSpan={projects.length > 0 ? 9 : 8} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine Todos</TableCell></TableRow>}
                  </TableBody></Table></CardContent></Card>
                </section>
              )}

              {/* BLOCKER TAB */}
              {actionTab === 'blocker' && (
                <section>
                  <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => setEditBlocker({ id: '__new__', reportedBy: 'Nicht zugeordnet', title: '', description: '', status: 'active', meetingId: null, projectId: null, createdAt: '' })}>+ Neu</Button>
                      {blockerSelected.size > 0 && <button onClick={handleBulkDeleteBlockers} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${blockerSelected.size} löschen`}><TrashIcon /></button>}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Input placeholder="Suche..." value={blockerSearch} onChange={e => setBlockerSearch(e.target.value)} className="h-8 text-xs w-[150px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                      <Select value={blockerFilterAssignee} onValueChange={setBlockerFilterAssignee}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Zuständige</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                      <Select value={blockerFilterStatus} onValueChange={setBlockerFilterStatus}><SelectTrigger className="h-8 text-xs w-[120px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="active">Aktiv</SelectItem><SelectItem value="resolved">Gelöst</SelectItem><SelectItem value="escalated">Eskaliert</SelectItem></SelectContent></Select>
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                    <SH label="Blocker" field="title" sort={blockerSort} onSort={blockerSort.toggle} />
                    <SH label="Zuständig" field="reportedBy" sort={blockerSort} onSort={blockerSort.toggle} className="w-[130px]" />
                    <SH label="Status" field="status" sort={blockerSort} onSort={blockerSort.toggle} className="w-[100px]" />
                    <SH label="Erstellt" field="createdAt" sort={blockerSort} onSort={blockerSort.toggle} className="w-[100px]" />
                    <TableHead className="w-[140px] text-xs text-center">Quelle</TableHead>
                    <TableHead className="w-[90px] text-xs text-center">Anpassen</TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredBlockers.map(b => (
                      <TableRow key={b.id} className={`text-sm border-[var(--syn-line)] group select-none cursor-pointer ${b.status !== 'active' ? 'opacity-50' : ''} ${blockerSelected.has(b.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => setBlockerSelected(prev => { const n = new Set(prev); n.has(b.id) ? n.delete(b.id) : n.add(b.id); return n })}>
                        <TableCell className="text-left"><button onClick={e => { e.stopPropagation(); setViewBlocker(b) }} className="text-left font-medium hover:text-[var(--syn-accent)]">{b.title}</button><div className="text-xs truncate max-w-md" style={{ color: 'var(--syn-text-faint)' }}>{b.description}</div></TableCell>
                        <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={b.reportedBy} /><span className="text-xs">{b.reportedBy}</span></div></TableCell>
                        <TableCell><Badge className={`text-[10px] ${ST_STYLE[b.status]}`}>{ST_LABEL[b.status]}</Badge></TableCell>
                        <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{b.createdAt}</TableCell>
                        <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}><SourceChip meeting={getMeeting(b.meetingId) || null} onClick={() => { const m = getMeeting(b.meetingId); if (m) setViewMeeting(m) }} /></TableCell>
                        <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center"><button onClick={() => setEditBlocker({...b})} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => setConfirmDelete({ label: b.title, action: () => handleDeleteBlocker(b) })} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button><input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${blockerSelected.has(b.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={blockerSelected.has(b.id)} onChange={() => setBlockerSelected(prev => { const n = new Set(prev); n.has(b.id) ? n.delete(b.id) : n.add(b.id); return n })} /></div></TableCell>
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
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => setEditOpen({ id: '__new__', owner: 'Nicht zugeordnet', title: '', description: '', category: 'general', status: 'open', meetingId: null, projectId: null, createdAt: '' })}>+ Neu</Button>
                      {openSelected.size > 0 && <button onClick={handleBulkDeleteOpen} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${openSelected.size} löschen`}><TrashIcon /></button>}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Input placeholder="Suche..." value={openSearch} onChange={e => setOpenSearch(e.target.value)} className="h-8 text-xs w-[150px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                      <Select value={openFilterOwner} onValueChange={setOpenFilterOwner}><SelectTrigger className="h-8 text-xs w-[140px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Zuständige</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                      <Select value={openFilterStatus} onValueChange={setOpenFilterStatus}><SelectTrigger className="h-8 text-xs w-[120px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="open">Offen</SelectItem><SelectItem value="watching">Beobachten</SelectItem><SelectItem value="closed">Geschlossen</SelectItem></SelectContent></Select>
                      <Select value={openFilterCategory} onValueChange={setOpenFilterCategory}><SelectTrigger className="h-8 text-xs w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Kategorien</SelectItem><SelectItem value="general">Allgemein</SelectItem><SelectItem value="risk">Risiko</SelectItem><SelectItem value="opportunity">Chance</SelectItem><SelectItem value="question">Frage</SelectItem><SelectItem value="follow_up">Nachverfolgung</SelectItem></SelectContent></Select>
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                    <TableHead className="w-10"></TableHead>
                    <SH label="Item" field="title" sort={openSort} onSort={openSort.toggle} />
                    <SH label="Kategorie" field="category" sort={openSort} onSort={openSort.toggle} className="w-[100px]" />
                    <SH label="Zuständig" field="owner" sort={openSort} onSort={openSort.toggle} className="w-[130px]" />
                    <SH label="Status" field="status" sort={openSort} onSort={openSort.toggle} className="w-[100px]" />
                    <SH label="Erstellt" field="createdAt" sort={openSort} onSort={openSort.toggle} className="w-[100px]" />
                    <TableHead className="w-[140px] text-xs text-center">Quelle</TableHead>
                    <TableHead className="w-[90px] text-xs text-center">Anpassen</TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredOpen.map(o => (
                      <TableRow key={o.id} className={`text-sm border-[var(--syn-line)] group select-none cursor-pointer ${o.status === 'closed' ? 'opacity-40' : ''} ${openSelected.has(o.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => setOpenSelected(prev => { const n = new Set(prev); n.has(o.id) ? n.delete(o.id) : n.add(o.id); return n })}>
                        <TableCell className="text-center">{CAT_ICON[o.category] || '○'}</TableCell>
                        <TableCell className="text-left"><button onClick={e => { e.stopPropagation(); setViewOpen(o) }} className="text-left hover:text-[var(--syn-accent)]">{o.title}</button><div className="text-xs truncate max-w-sm" style={{ color: 'var(--syn-text-faint)' }}>{o.description}</div></TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-line)]">{CAT_LABEL[o.category] || o.category}</Badge></TableCell>
                        <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={o.owner} /><span className="text-xs">{o.owner}</span></div></TableCell>
                        <TableCell><Badge className={`text-[10px] ${ST_STYLE[o.status]}`}>{ST_LABEL[o.status]}</Badge></TableCell>
                        <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{o.createdAt}</TableCell>
                        <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}><SourceChip meeting={getMeeting(o.meetingId) || null} onClick={() => { const m = getMeeting(o.meetingId); if (m) setViewMeeting(m) }} /></TableCell>
                        <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center"><button onClick={() => setEditOpen({...o})} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => setConfirmDelete({ label: o.title, action: () => handleDeleteOpen(o) })} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button><input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${openSelected.has(o.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={openSelected.has(o.id)} onChange={() => setOpenSelected(prev => { const n = new Set(prev); n.has(o.id) ? n.delete(o.id) : n.add(o.id); return n })} /></div></TableCell>
                      </TableRow>
                    ))}
                    {filteredOpen.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine offenen Punkte</TableCell></TableRow>}
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
                  <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => handleOpenProjectDialog('__new__')}>+ Neu</Button>
                  {projectSelected.size > 0 && <button onClick={handleBulkDeleteProjects} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${projectSelected.size} löschen`}><TrashIcon /></button>}
                </div>
                <div className="flex items-center gap-2">
                  <Input placeholder="Suche..." value={projectSearch} onChange={e => setProjectSearch(e.target.value)} className="h-8 text-xs w-[180px] bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
                  <div className="flex border border-[var(--syn-line)] rounded-lg overflow-hidden">
                    {(['table', 'kanban', 'gantt'] as ProjectView[]).map(v => (
                      <button key={v} onClick={() => setProjectView(v)} className={`px-3 py-1.5 text-xs transition-colors ${projectView === v ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`} style={projectView !== v ? { color: 'var(--syn-text-muted)' } : {}}>
                        {v === 'table' ? '▤ Tabelle' : v === 'kanban' ? '▥ Kanban' : '▰ Gantt'}
                      </button>
                    ))}
                  </div>
                  {(projectView === 'kanban' || projectView === 'gantt') && (
                    <Button size="sm" variant="outline" className="h-8 text-xs border-[var(--syn-line)] gap-1" onClick={() => setPrintView(projectView as 'kanban' | 'gantt')}>Drucken</Button>
                  )}
                </div>
              </div>

              {/* TABLE VIEW */}
              {projectView === 'table' && (
                <div className="space-y-1">
                <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                  <SH label="Projekt" field="name" sort={projectSort} onSort={projectSort.toggle} />
                  <SH label="Beschreibung" field="description" sort={projectSort} onSort={projectSort.toggle} />
                  <TableHead className="w-[80px] text-xs text-center">Todos</TableHead>
                  <TableHead className="w-[80px] text-xs text-center">Blocker</TableHead>
                  <SH label="Status" field="status" sort={projectSort} onSort={projectSort.toggle} className="w-[130px]" />
                  <TableHead className="w-[90px] text-xs text-center">Anpassen</TableHead>
                </TableRow></TableHeader><TableBody>
                  {filteredProjects.map(p => {
                    const pTodos = projectTodos(p.id); const pBlockers = projectBlockers(p.id)
                    return (
                    <TableRow key={p.id} className={`text-sm cursor-pointer select-none group ${projectSelected.has(p.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} style={{ borderLeftWidth: 3, borderLeftStyle: 'solid', borderLeftColor: getProjectColor(p.id, projectIds) }} onClick={() => setProjectSelected(prev => { const n = new Set(prev); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n })}>
                      <TableCell className="text-left font-medium"><button onClick={e => { e.stopPropagation(); setViewProject(p) }} className="text-left hover:text-[var(--syn-accent)]">{p.name}</button></TableCell>
                      <TableCell className="text-left text-xs truncate" style={{ color: 'var(--syn-text-muted)' }}>{p.description || '—'}</TableCell>
                      <TableCell className="text-xs text-center"><span className="font-medium">{pTodos.filter(t => t.status === 'done').length}</span><span style={{ color: 'var(--syn-text-faint)' }}>/{pTodos.length}</span></TableCell>
                      <TableCell className="text-xs text-center">{pBlockers.filter(b => b.status === 'active').length > 0 ? <span className="font-bold text-[var(--syn-danger)]">{pBlockers.filter(b => b.status === 'active').length} aktiv</span> : <span style={{ color: 'var(--syn-text-faint)' }}>0</span>}</TableCell>
                      <TableCell><Badge className={`text-[10px] ${ST_STYLE[p.status] || ''}`}>{ST_LABEL[p.status] || p.status}</Badge></TableCell>
                      <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center"><button onClick={() => handleOpenProjectDialog(p)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => setConfirmDelete({ label: p.name, action: () => handleDeleteProject(p) })} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button><input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${projectSelected.has(p.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={projectSelected.has(p.id)} onChange={() => setProjectSelected(prev => { const n = new Set(prev); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n })} /></div></TableCell>
                    </TableRow>
                  )})}
                  {filteredProjects.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine Projekte</TableCell></TableRow>}
                </TableBody></Table></CardContent></Card>
                </div>
              )}

              {/* KANBAN VIEW */}
              {projectView === 'kanban' && (() => {
                const kanbanTodos = kanbanTodosMemo

                const renderKanbanCard = (t: Todo) => (
                  <div key={t.id} draggable onDragStart={() => setDragTodo(t.id)} onDragEnd={() => setDragTodo(null)}
                    className={`glass-card border border-[var(--syn-line)] rounded-lg p-3 cursor-grab active:cursor-grabbing hover:border-[var(--syn-accent-line)] transition-colors group ${dragTodo === t.id ? 'opacity-50' : ''}`}
                    style={{ borderLeftWidth: 3, borderLeftColor: getProjectColor(t.projectId, projectIds) }}
                  >
                    <button onClick={() => setViewTodo(t)} className="text-sm font-medium text-left hover:text-[var(--syn-accent)] w-full">{t.title}</button>
                    <div className="flex items-center gap-2 mt-2 flex-wrap">
                      {kanbanFields.has('priority') && <Badge className={`text-[9px] ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]}</Badge>}
                      {kanbanFields.has('assignee') && <div className="flex items-center gap-1"><Av name={t.assignee} /><span className="text-[10px]" style={{ color: 'var(--syn-text-muted)' }}>{t.assignee}</span></div>}
                      {kanbanFields.has('duration') && t.durationDays > 0 && <span className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>{t.durationDays}d</span>}
                    </div>
                    {kanbanFields.has('dueDate') && t.dueDate && <div className={`text-[10px] mt-1.5 ${t.dueDate < today && t.status !== 'done' ? 'text-[var(--syn-danger)] font-bold' : ''}`} style={!(t.dueDate < today && t.status !== 'done') ? { color: 'var(--syn-text-faint)' } : {}}>Fällig: {t.dueDate}</div>}
                    {kanbanFields.has('project') && t.projectId && <div className="text-[10px] mt-0.5" style={{ color: 'var(--syn-text-faint)' }}>{getProjectName(t.projectId)}</div>}
                    <div className="flex gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity"><button onClick={e => { e.stopPropagation(); setEditTodo({...t}) }} className="text-xs hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={e => { e.stopPropagation(); setConfirmDelete({ label: t.title, action: () => handleDeleteTodo(t) }) }} className="text-xs hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button></div>
                  </div>
                )

                return (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Select value={kanbanFilterProject} onValueChange={setKanbanFilterProject}><SelectTrigger className="h-7 text-[10px] w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Projekte</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>
                    <Select value={kanbanFilterAssignee} onValueChange={setKanbanFilterAssignee}><SelectTrigger className="h-7 text-[10px] w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Zuständig</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                    <Select value={kanbanGroupBy} onValueChange={v => setKanbanGroupBy(v as KanbanGroupBy)}><SelectTrigger className="h-7 text-[10px] w-[130px]"><SelectValue /></SelectTrigger><SelectContent>
                      <SelectItem value="none">Keine Gruppe</SelectItem>
                      <SelectItem value="project">Gruppe: Projekt</SelectItem>
                      <SelectItem value="assignee">Gruppe: Zuständig</SelectItem>
                    </SelectContent></Select>
                    <div className="flex items-center h-7 rounded border border-[var(--syn-line)] overflow-hidden">
                      <button onClick={() => setKanbanSortDir(d => d === 'asc' ? 'desc' : 'asc')} className="h-full px-1.5 text-[10px] hover:bg-[var(--syn-hover)] border-r border-[var(--syn-line)]" style={{ color: 'var(--syn-text-muted)' }}>{kanbanSortDir === 'asc' ? '↑' : '↓'}</button>
                      <Select value={kanbanSortKey} onValueChange={v => setKanbanSortKey(v as any)}><SelectTrigger className="h-7 text-[10px] w-[100px] border-0"><SelectValue /></SelectTrigger><SelectContent>
                        <SelectItem value="start">Start</SelectItem><SelectItem value="assignee">Zuständig</SelectItem><SelectItem value="title">Titel</SelectItem><SelectItem value="priority">Priorität</SelectItem><SelectItem value="project">Projekt</SelectItem>
                      </SelectContent></Select>
                    </div>
                    <div className="flex items-center gap-1 ml-2">
                      <span className="text-[10px] mr-0.5" style={{ color: 'var(--syn-text-muted)' }}>Anzeigen:</span>
                      {[['priority','Priorität'],['assignee','Zuständig'],['duration','Dauer'],['project','Projekt'],['dueDate','Fällig']].map(([k,l]) => (
                        <button key={k} onClick={() => toggleField(kanbanFields, setKanbanFields, k)} className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${kanbanFields.has(k) ? 'bg-[var(--syn-accent)] text-white border-[var(--syn-accent)]' : 'border-[var(--syn-line)]'}`} style={!kanbanFields.has(k) ? { color: 'var(--syn-text-faint)' } : {}}>{l}</button>
                      ))}
                    </div>
                  </div>

                  {kanbanGroupBy === 'none' ? (
                    <div className="grid grid-cols-3 gap-4">
                      {kanbanColumns.map(status => {
                        const colTodos = kanbanTodos.filter(t => t.status === status)
                        return (
                          <div key={status}
                            onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('!bg-[var(--syn-accent-soft)]') }}
                            onDragLeave={e => { e.currentTarget.classList.remove('!bg-[var(--syn-accent-soft)]') }}
                            onDrop={e => { e.preventDefault(); e.currentTarget.classList.remove('!bg-[var(--syn-accent-soft)]'); if (dragTodo) handleKanbanDrop(dragTodo, status) }}
                            className="rounded-xl border border-[var(--syn-line)] p-3 min-h-[300px] transition-colors" style={{ background: 'var(--syn-surface)' }}
                          >
                            <div className="flex items-center justify-between mb-3">
                              <h3 className="text-sm font-semibold">{kanbanLabels[status]}</h3>
                              <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>{colTodos.length}</span>
                            </div>
                            <div className="space-y-2">{colTodos.map(renderKanbanCard)}</div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    (() => {
                      const groups = new Map<string, Todo[]>()
                      kanbanTodos.forEach(t => {
                        const key = kanbanGroupBy === 'project' ? (getProjectName(t.projectId) || 'Kein Projekt') : t.assignee
                        if (!groups.has(key)) groups.set(key, [])
                        groups.get(key)!.push(t)
                      })
                      return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([label, groupTodos]) => (
                        <div key={label} className="space-y-2">
                          <h3 className="text-xs font-bold tracking-wide px-1" style={{ color: 'var(--syn-text-muted)' }}>{label} ({groupTodos.length})</h3>
                          <div className="grid grid-cols-3 gap-4">
                            {kanbanColumns.map(status => {
                              const colTodos = groupTodos.filter(t => t.status === status)
                              return (
                                <div key={status}
                                  onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('!bg-[var(--syn-accent-soft)]') }}
                                  onDragLeave={e => { e.currentTarget.classList.remove('!bg-[var(--syn-accent-soft)]') }}
                                  onDrop={e => { e.preventDefault(); e.currentTarget.classList.remove('!bg-[var(--syn-accent-soft)]'); if (dragTodo) handleKanbanDrop(dragTodo, status) }}
                                  className="rounded-xl border border-[var(--syn-line)] p-3 min-h-[120px] transition-colors" style={{ background: 'var(--syn-surface)' }}
                                >
                                  <div className="flex items-center justify-between mb-2">
                                    <h4 className="text-[11px] font-semibold">{kanbanLabels[status]}</h4>
                                    <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>{colTodos.length}</span>
                                  </div>
                                  <div className="space-y-2">{colTodos.map(renderKanbanCard)}</div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      ))
                    })()
                  )}
                </div>)
              })()}

              {/* GANTT VIEW */}
              {projectView === 'gantt' && (() => {
                const COL_W = ganttGranularity === 'month' ? 28 : ganttGranularity === 'quarter' ? 6 : 2
                const ROW_H = 32; const GROUP_H = 26
                const GANTT_COL_W: Record<string, number> = { project: 120, title: 180, assignee: 100, priority: 80 }
                const GANTT_COL_LABEL: Record<string, string> = { project: 'Projekt', title: 'Aufgabe', assignee: 'Zuständig', priority: 'Priorität' }
                const LABEL_W = ganttVisibleCols.reduce((s, c) => s + (GANTT_COL_W[c] || 100), 0)
                const isWeekend = (d: Date) => d.getDay() === 0 || d.getDay() === 6
                const MONTH_NAMES = ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez']
                const handleGanttMouseDown = (e: React.MouseEvent, todoId: string, mode: 'move' | 'resize' | 'resize-left') => {
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
                      else if (ganttDragRef.current!.mode === 'resize-left') {
                        const newDur = Math.max(1, ganttDragRef.current!.origDuration - daysDelta)
                        const newStart = addDays(ganttDragRef.current!.origStart, ganttDragRef.current!.origDuration - newDur)
                        return { ...x, startDate: newStart, durationDays: newDur }
                      }
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

                // Build flat row list with group headers
                type GanttRow = { type: 'group'; label: string } | { type: 'todo'; todo: Todo }
                const ganttRows: GanttRow[] = []
                if (ganttGroupBy === 'none') {
                  ganttTodos.forEach(t => ganttRows.push({ type: 'todo', todo: t }))
                } else {
                  const groups = new Map<string, Todo[]>()
                  ganttTodos.forEach(t => {
                    const key = ganttGroupBy === 'project' ? (getProjectName(t.projectId) || 'Kein Projekt') : t.assignee
                    if (!groups.has(key)) groups.set(key, [])
                    groups.get(key)!.push(t)
                  })
                  Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0])).forEach(([label, items]) => {
                    ganttRows.push({ type: 'group', label: `${label} (${items.length})` })
                    items.forEach(t => ganttRows.push({ type: 'todo', todo: t }))
                  })
                }

                // Build index map: todoId → visual row index (for dependency arrows)
                const todoRowIndex = new Map<string, number>()
                let rowIdx = 0
                ganttRows.forEach(row => {
                  if (row.type === 'todo') { todoRowIndex.set(row.todo.id, rowIdx); rowIdx++ }
                  else rowIdx++ // group headers count as a row for offset
                })

                // Compute Y offset for each row (mix of ROW_H and GROUP_H)
                const rowYOffsets: number[] = []
                let yAcc = 0
                ganttRows.forEach(row => {
                  rowYOffsets.push(yAcc)
                  yAcc += row.type === 'group' ? GROUP_H : ROW_H
                })
                const totalBodyH = yAcc

                // Collect all dependency lines for SVG overlay
                const depLines: { x1: number; y1: number; x2: number; y2: number; overlap: boolean }[] = []
                ganttRows.forEach((row, ri) => {
                  if (row.type !== 'todo') return
                  const t = row.todo
                  const offsetDays = ganttOffset(t.startDate!)
                  const thisStartX = offsetDays * COL_W
                  const thisY = rowYOffsets[ri] + ROW_H / 2
                  t.dependsOn.forEach(depId => {
                    const dep = ganttTodos.find(x => x.id === depId)
                    if (!dep || !dep.startDate) return
                    const depStartOff = ganttOffset(dep.startDate)
                    const depEndX = (depStartOff + Math.max(dep.durationDays, 1)) * COL_W
                    const depRi = ganttRows.findIndex(r => r.type === 'todo' && r.todo.id === depId)
                    if (depRi < 0) return
                    const depY = rowYOffsets[depRi] + ROW_H / 2
                    const overlap = hasOverlap(dep, t)
                    depLines.push({ x1: depEndX, y1: depY, x2: thisStartX, y2: thisY, overlap })
                  })
                })

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
                      <Select value={ganttGroupBy} onValueChange={v => setGanttGroupBy(v as GanttGroupBy)}><SelectTrigger className="h-7 text-[10px] w-[130px]"><SelectValue /></SelectTrigger><SelectContent>
                        <SelectItem value="none">Keine Gruppe</SelectItem>
                        <SelectItem value="project">Gruppe: Projekt</SelectItem>
                        <SelectItem value="assignee">Gruppe: Zuständig</SelectItem>
                      </SelectContent></Select>
                      <div className="flex items-center h-7 rounded border border-[var(--syn-line)] overflow-hidden">
                        <button onClick={() => setGanttSortDir(d => d === 'asc' ? 'desc' : 'asc')} className="h-full px-1.5 text-[10px] hover:bg-[var(--syn-hover)] border-r border-[var(--syn-line)]" style={{ color: 'var(--syn-text-muted)' }}>{ganttSortDir === 'asc' ? '↑' : '↓'}</button>
                        <Select value={ganttSortKey} onValueChange={v => setGanttSortKey(v as any)}><SelectTrigger className="h-7 text-[10px] w-[100px] border-0"><SelectValue /></SelectTrigger><SelectContent>
                          <SelectItem value="start">Start</SelectItem><SelectItem value="assignee">Zuständig</SelectItem><SelectItem value="title">Titel</SelectItem><SelectItem value="priority">Priorität</SelectItem><SelectItem value="project">Projekt</SelectItem>
                        </SelectContent></Select>
                      </div>
                      {/* Column visibility dropdown — styled like sort control */}
                      {(() => {
                        const allCols = [{ key: 'project', label: 'Projekt' }, { key: 'title', label: 'Aufgabe' }, { key: 'assignee', label: 'Zuständig' }, { key: 'priority', label: 'Priorität' }]
                        const handleReorder = (targetKey: string) => {
                          const src = ganttColDragRef.current; if (!src || src === targetKey) return
                          const next = [...ganttVisibleCols]; const si = next.indexOf(src); const ti = next.indexOf(targetKey)
                          if (si < 0 || ti < 0) return; next.splice(si, 1); next.splice(ti, 0, src); setGanttVisibleCols(next)
                        }
                        return <div className="relative">
                          <div className="flex items-center h-7 rounded border border-[var(--syn-line)] overflow-hidden">
                            <button onClick={() => setGanttColDropOpen(!ganttColDropOpen)} className="h-full px-2 text-[10px] hover:bg-[var(--syn-hover)] flex items-center gap-1" style={{ color: 'var(--syn-text-muted)' }}>☰ Spalten ({ganttVisibleCols.length})</button>
                          </div>
                          {ganttColDropOpen && <>
                            <div className="fixed inset-0 z-40" onClick={() => setGanttColDropOpen(false)} />
                            <div className="absolute left-0 top-8 z-50 rounded-lg border border-[var(--syn-line)] shadow-lg p-1.5 min-w-[180px]" style={{ background: 'var(--syn-surface)' }}>
                              {/* Show active columns first (in order), then inactive ones */}
                              {[...ganttVisibleCols.map(k => allCols.find(c => c.key === k)!), ...allCols.filter(c => !ganttVisibleCols.includes(c.key))].map(c => {
                                const active = ganttVisibleCols.includes(c.key)
                                return <div key={c.key}
                                  className={`flex items-center gap-2 px-2 py-1 rounded text-xs hover:bg-[var(--syn-hover)] transition-colors ${active ? 'cursor-grab' : 'cursor-pointer'}`}
                                  draggable={active}
                                  onDragStart={() => { ganttColDragRef.current = c.key }}
                                  onDragOver={e => { if (active && ganttColDragRef.current) e.preventDefault() }}
                                  onDrop={() => handleReorder(c.key)}
                                  onDragEnd={() => { ganttColDragRef.current = null }}
                                  onClick={() => { if (!active) setGanttVisibleCols([...ganttVisibleCols, c.key]); else if (ganttVisibleCols.length > 1) setGanttVisibleCols(ganttVisibleCols.filter(k => k !== c.key)) }}
                                >
                                  <span className="w-3 text-center text-[10px]" style={{ color: active ? 'var(--syn-accent)' : 'var(--syn-text-faint)' }}>{active ? '✓' : ''}</span>
                                  {active && <span className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>⠿</span>}
                                  <span style={{ color: active ? 'var(--syn-text)' : 'var(--syn-text-faint)' }}>{c.label}</span>
                                </div>
                              })}
                            </div>
                          </>}
                        </div>
                      })()}
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
                          <marker id="arrow" viewBox="0 0 5 5" refX="4" refY="2.5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L5,2.5 L0,5 Z" fill="#ccc" /></marker>
                          <marker id="arrow-red" viewBox="0 0 5 5" refX="4" refY="2.5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L5,2.5 L0,5 Z" fill="var(--syn-danger)" /></marker>
                        </defs></svg>
                        {/* Month header */}
                        <div className="flex border-b border-[var(--syn-line)]" style={{ background: 'var(--syn-surface-2)' }}>
                          {ganttVisibleCols.map(c => <div key={c} className="shrink-0 border-r border-[var(--syn-line)]" style={{ width: GANTT_COL_W[c], background: 'var(--syn-surface-3)' }} />)}
                          {monthGroups.map((mg, i) => (
                            <div key={i} className="text-[10px] font-semibold border-r border-[var(--syn-line)] flex items-center justify-center py-1" style={{ width: mg.span * COL_W, color: 'var(--syn-text-muted)' }}>{mg.label}</div>
                          ))}
                        </div>
                        {/* Day header */}
                        <div className="flex border-b border-[var(--syn-line-strong)]" style={{ background: 'var(--syn-surface-2)' }}>
                          {ganttVisibleCols.map(c => <div key={c} className="shrink-0 border-r border-[var(--syn-line)] text-[10px] flex items-center px-3 py-0.5 font-medium" style={{ width: GANTT_COL_W[c], background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)' }}>{GANTT_COL_LABEL[c]}</div>)}
                          {timelineDays.map((td, i) => {
                            let cellLabel = ''
                            if (ganttGranularity === 'month') cellLabel = td.label
                            else if (ganttGranularity === 'quarter') { if (td.date.getDate() === 1) cellLabel = `${td.date.getDate()}.${td.date.getMonth()+1}` }
                            else { if (td.date.getDate() === 1) cellLabel = MONTH_NAMES[td.date.getMonth()] }
                            return <div key={i} className="text-[9px] text-center flex items-center justify-center border-r border-[var(--syn-line)] py-0.5" style={{ width: COL_W, color: td.isWE && ganttGranularity === 'month' ? 'var(--syn-text-faint)' : 'var(--syn-text-muted)', background: td.isWE && ganttGranularity === 'month' ? 'var(--syn-surface-3)' : undefined }}>{cellLabel}</div>
                          })}
                        </div>
                        {/* Body with rows + dependency overlay */}
                        <div className="relative" style={{ height: totalBodyH }}>
                          {/* Dependency arrows overlay */}
                          <svg className="absolute pointer-events-none z-20" style={{ left: LABEL_W, top: 0, width: totalW, height: totalBodyH, overflow: 'visible' }}>
                            {depLines.map((dl, i) => {
                              const color = dl.overlap ? 'var(--syn-danger)' : '#ccc'
                              const marker = dl.overlap ? 'url(#arrow-red)' : 'url(#arrow)'
                              const GAP = 8
                              const exitX = dl.x1 + GAP
                              const enterX = dl.x2 - GAP
                              const cornerX = Math.max(exitX, enterX < exitX ? exitX : (exitX + enterX) / 2)
                              const sameRow = Math.abs(dl.y1 - dl.y2) < 2
                              return sameRow
                                ? <line key={i} x1={dl.x1} y1={dl.y1} x2={dl.x2} y2={dl.y2} stroke={color} strokeWidth="1" markerEnd={marker} />
                                : <path key={i} d={`M${dl.x1},${dl.y1} L${cornerX},${dl.y1} L${cornerX},${dl.y2} L${dl.x2},${dl.y2}`} fill="none" stroke={color} strokeWidth="1" markerEnd={marker} />
                            })}
                          </svg>
                          {/* Rows */}
                          {ganttRows.map((row, ri) => {
                            if (row.type === 'group') {
                              return (
                                <div key={`g-${ri}`} className="flex" style={{ height: GROUP_H, position: 'absolute', top: rowYOffsets[ri], width: '100%' }}>
                                  <div className="shrink-0 border-r border-b border-[var(--syn-line)] flex items-center px-3 text-[10px] font-bold tracking-wide" style={{ width: LABEL_W, background: 'var(--syn-surface-2)', color: 'var(--syn-text-muted)' }}>{row.label}</div>
                                  <div className="flex-1 border-b border-[var(--syn-line)]" style={{ background: 'var(--syn-surface-2)' }} />
                                </div>
                              )
                            }
                            const t = row.todo
                            const start = t.startDate!
                            const offsetDays = ganttOffset(start)
                            const duration = Math.max(t.durationDays, 1)
                            const endDate = addDays(start, duration - 1)
                            const barLabel = [ganttFields.has('assignee') ? t.assignee.split(' ')[0] : '', ganttFields.has('duration') ? `${duration}d` : '', ganttFields.has('project') && t.projectId ? getProjectName(t.projectId) : ''].filter(Boolean).join(' · ')
                            return (
                              <div key={t.id} className="flex group" style={{ height: ROW_H, position: 'absolute', top: rowYOffsets[ri], width: '100%' }}>
                                {ganttVisibleCols.map((c, ci) => {
                                  const isLast = ci === ganttVisibleCols.length - 1
                                  const base = "shrink-0 border-r border-[var(--syn-line)] flex items-center px-2 text-xs truncate"
                                  const actionBtns = isLast ? <span className="hidden group-hover:flex gap-0.5 shrink-0 ml-1">
                                    <button onClick={() => setEditTodo({...t})} className="text-[10px] hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button>
                                    <button onClick={() => setConfirmDelete({ label: t.title, action: () => handleDeleteTodo(t) })} className="text-[10px] hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button>
                                  </span> : null
                                  if (c === 'title') return <div key={c} className={base} style={{ width: GANTT_COL_W[c], background: 'var(--syn-surface)' }}>
                                    <button onClick={() => setViewTodo(t)} className="hover:text-[var(--syn-accent)] truncate flex-1 text-left">{t.title}</button>{actionBtns}
                                  </div>
                                  if (c === 'project') return <div key={c} className={base} style={{ width: GANTT_COL_W[c], background: 'var(--syn-surface)', color: 'var(--syn-text-muted)' }}><span className="truncate flex-1">{getProjectName(t.projectId) || '—'}</span>{actionBtns}</div>
                                  if (c === 'assignee') return <div key={c} className={base} style={{ width: GANTT_COL_W[c], background: 'var(--syn-surface)', color: 'var(--syn-text-muted)' }}><span className="truncate flex-1">{t.assignee}</span>{actionBtns}</div>
                                  if (c === 'priority') return <div key={c} className={base} style={{ width: GANTT_COL_W[c], background: 'var(--syn-surface)' }}><Badge className={`text-[9px] ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]}</Badge>{actionBtns}</div>
                                  return null
                                })}
                                <div className="flex-1 relative" style={{ height: ROW_H }}>
                                  {ganttGranularity === 'month' && timelineDays.map((td, i) => td.isWE ? <div key={i} className="absolute top-0 h-full" style={{ left: i * COL_W, width: COL_W, background: 'var(--syn-surface-2)', opacity: 0.5 }} /> : null)}
                                  <div className="absolute top-0 left-0 right-0 h-full border-b border-[var(--syn-line)]" />
                                  {(() => { const tOff = ganttOffset(today); return tOff >= 0 && tOff < timelineDays.length ? <div className="absolute top-0 h-full w-px z-10" style={{ left: tOff * COL_W + COL_W / 2, background: 'var(--syn-danger)' }} /> : null })()}
                                  <div
                                    className="absolute top-1.5 rounded cursor-grab active:cursor-grabbing z-10"
                                    style={{ left: offsetDays * COL_W, width: Math.max(duration * COL_W, 8), height: ROW_H - 12, background: getProjectColor(t.projectId, projectIds), opacity: t.status === 'done' ? 0.5 : 1 }}
                                    title={`${t.title} (${start} → ${endDate}, ${duration}d)`}
                                    onMouseDown={e => handleGanttMouseDown(e, t.id, 'move')}
                                  >
                                    <div className="absolute left-0 top-0 w-2 h-full cursor-ew-resize hover:bg-white/20 rounded-l" onMouseDown={e => handleGanttMouseDown(e, t.id, 'resize-left')} />
                                    <span className="text-[8px] text-white px-2.5 truncate block" style={{ lineHeight: `${ROW_H - 12}px` }}>{barLabel}</span>
                                    <div className="absolute right-0 top-0 w-2 h-full cursor-ew-resize hover:bg-white/20 rounded-r" onMouseDown={e => handleGanttMouseDown(e, t.id, 'resize')} />
                                  </div>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                        {ganttTodos.length === 0 && <div className="py-8 text-center text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Todos mit Startdatum für diesen Filter.</div>}
                      </div>
                    </div>
                    <p className="text-[10px] mt-2 text-center" style={{ color: 'var(--syn-text-faint)' }}>{ganttTodos.length} Aufgaben — Balken verschieben oder an beiden Enden ziehen um Dauer/Start zu ändern</p>
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
                  <Select value={logFilterType} onValueChange={setLogFilterType}><SelectTrigger className="h-8 text-xs w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Typen</SelectItem><SelectItem value="todo">Todos</SelectItem><SelectItem value="blocker">Blocker</SelectItem><SelectItem value="open_item">Offene Punkte</SelectItem><SelectItem value="meeting">Meetings</SelectItem><SelectItem value="decision">Entscheidung</SelectItem></SelectContent></Select>
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
                    <TableHead className="w-[90px] text-xs">Anpassen</TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredLog.map(a => (
                      <TableRow key={a.id} className="text-sm hover:bg-[var(--syn-hover)] border-[var(--syn-line)]">
                        <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{new Date(a.timestamp).toLocaleString('de-DE')}</TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-line)]">{TYPE_LABEL[a.entityType] || a.entityType}</Badge></TableCell>
                        <TableCell className="text-left"><button onClick={() => openSourceEntity(a.entityType, a.entityId)} className="font-medium text-left hover:text-[var(--syn-accent)]">{a.entityTitle}</button></TableCell>
                        <TableCell className="text-xs">{a.action === 'status_changed' ? <span>Status geändert</span> : ACTION_LABEL[a.action] || a.action}</TableCell>
                        <TableCell>{a.action === 'status_changed' && a.oldValue ? <Badge className={`text-[9px] ${ST_STYLE[a.oldValue] || ''}`}>{ST_LABEL[a.oldValue] || a.oldValue}</Badge> : <span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>—</span>}</TableCell>
                        <TableCell>{a.action === 'status_changed' && a.newValue ? <Badge className={`text-[9px] ${ST_STYLE[a.newValue] || ''}`}>{ST_LABEL[a.newValue] || a.newValue}</Badge> : <span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>—</span>}</TableCell>
                        <TableCell><div className="flex gap-2 items-center justify-center"><button onClick={() => editSourceEntity(a.entityType, a.entityId)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button></div></TableCell>
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
                      <div className="px-5 py-3 border-b border-[var(--syn-line)]"><span className="text-sm font-semibold">Offene Punkte ({searchResultsFull.openItems.length})</span></div>
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
        <DialogContent className="max-w-4xl max-h-[85vh]">{viewMeeting && <ScrollArea className="max-h-[75vh] pr-4">
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
            <div className="flex gap-2"><Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { const m = viewMeeting; setViewMeeting(null); setEditMeeting({...m}) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => setConfirmDelete({ label: viewMeeting.title, action: () => { handleDeleteMeeting(viewMeeting); setViewMeeting(null) } })}>{'✕'} Löschen</Button></div>
          </div>
        </ScrollArea>}</DialogContent>
      </Dialog>

      {/* View Project Detail */}
      <Dialog open={!!viewProject} onOpenChange={() => setViewProject(null)}>
        <DialogContent className="max-w-4xl max-h-[85vh]">{viewProject && <ScrollArea className="max-h-[75vh] pr-4">
          <DialogHeader className="pb-3">
            <DialogTitle>{viewProject.name}</DialogTitle>
            <div className="flex items-center gap-3 mt-1">
              <Badge className={`text-xs ${ST_STYLE[viewProject.status]}`}>{ST_LABEL[viewProject.status]}</Badge>
              <span className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Erstellt: {viewProject.created_at?.split('T')[0]}</span>
            </div>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            {/* Project Meta */}
            {(() => {
              const pT = projectTodos(viewProject.id)
              const done = pT.filter(t => t.status === 'done').length
              const pct = pT.length ? Math.round((done / pT.length) * 100) : 0
              const owners = [...new Set(pT.map(t => t.assignee).filter(a => a && a !== 'Nicht zugeordnet'))]
              const starts = pT.map(t => t.startDate).filter(Boolean).sort()
              const ends = pT.filter(t => t.startDate).map(t => addDays(t.startDate!, Math.max(t.durationDays - 1, 0))).sort()
              return <div className="space-y-3">
                <div className="flex items-center gap-4 flex-wrap text-[11px]" style={{ color: 'var(--syn-text-muted)' }}>
                  {owners.length > 0 && <span>👥 {owners.join(', ')}</span>}
                  {starts.length > 0 && <span>Projektstart: {starts[0]}</span>}
                  {ends.length > 0 && <span>Projektende: {ends[ends.length - 1]}</span>}
                </div>
                {pT.length > 0 && <div>
                  <div className="flex items-center justify-between text-[11px] mb-1">
                    <span style={{ color: 'var(--syn-text-muted)' }}>Fortschritt</span>
                    <span style={{ color: 'var(--syn-text-faint)' }}>{pct}%</span>
                  </div>
                  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--syn-surface-3)' }}>
                    <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: pct === 100 ? 'var(--syn-ok)' : 'var(--syn-accent)' }} />
                  </div>
                </div>}
                <Separator className="bg-[var(--syn-line)]" />
              </div>
            })()}
            {viewProject.description && <><div className="text-sm">{viewProject.description}</div><Separator className="bg-[var(--syn-line)]" /></>}
            {(() => { const pT = projectTodos(viewProject.id); if (!pT.length) return null; return <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--syn-text-faint)' }}>Todos ({pT.filter(t => t.status === 'done').length}/{pT.length} erledigt)</h3>
              <div className="space-y-2">{pT.map(t => (
                <div key={t.id} className="rounded-lg border border-[var(--syn-line)] p-2.5 hover:bg-[var(--syn-hover)] transition-colors cursor-pointer" onClick={() => { setViewProject(null); setViewTodo(t) }}>
                  <div className="flex items-center gap-2">
                    <span className={`w-4 h-4 rounded border flex items-center justify-center text-[10px] shrink-0 ${t.status === 'done' ? 'bg-[var(--syn-ok)] border-[var(--syn-ok)] text-white' : 'border-[var(--syn-line-strong)]'}`}>{t.status === 'done' ? '✓' : ''}</span>
                    <span className={`text-sm font-medium flex-1 ${t.status === 'done' ? 'line-through opacity-50' : ''}`}>{t.title}</span>
                    <Badge className={`text-[9px] ${PRI_STYLE[t.priority]}`}>{PRI_LABEL[t.priority]}</Badge>
                    <Badge className={`text-[9px] ${ST_STYLE[t.status]}`}>{ST_LABEL[t.status]}</Badge>
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 ml-6 text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>
                    {t.assignee && t.assignee !== 'Nicht zugeordnet' && <span>👤 {t.assignee}</span>}
                    {t.startDate && <span>Start: {t.startDate}</span>}
                    {t.startDate && <span>Ende: {addDays(t.startDate, Math.max(t.durationDays - 1, 0))}</span>}
                    {!t.startDate && t.dueDate && <span>Fällig: {t.dueDate}</span>}
                    {t.durationDays > 1 && <span>{t.durationDays} Tage</span>}
                    {t.dependsOn && t.dependsOn.length > 0 && <span>⛓ {t.dependsOn.length} Abhängigkeit{t.dependsOn.length > 1 ? 'en' : ''}</span>}
                  </div>
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
              <Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { const p = viewProject!; setViewProject(null); handleOpenProjectDialog(p) }}>{'✎'} Bearbeiten</Button>
              <Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => setConfirmDelete({ label: viewProject!.name, action: () => { handleDeleteProject(viewProject!); setViewProject(null) } })}>{'✕'} Löschen</Button>
              <div className="ml-auto flex gap-1">
                <Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewProject(null); setPage('projekte'); setProjectView('gantt') }}>{'▰'} Gantt</Button>
                <Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewProject(null); setPage('projekte'); setProjectView('kanban') }}>{'▥'} Kanban</Button>
              </div>
            </div>
          </div>
        </ScrollArea>}</DialogContent>
      </Dialog>

      {/* Edit Todo */}
      <Dialog open={!!editTodo} onOpenChange={() => setEditTodo(null)}><DialogContent className="max-w-4xl"><DialogHeader><DialogTitle>{editTodo?.id === '__new__' ? 'Neuer Todo' : 'Todo bearbeiten'}</DialogTitle></DialogHeader>{editTodo && <div className="space-y-3 pt-2"><Input placeholder="Titel" value={editTodo.title} onChange={e => setEditTodo({...editTodo, title: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea placeholder="Beschreibung" value={editTodo.description} onChange={e => setEditTodo({...editTodo, description: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><div className="grid grid-cols-2 gap-3"><Select value={editTodo.assignee} onValueChange={v => setEditTodo({...editTodo, assignee: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select><Select value={editTodo.priority} onValueChange={v => setEditTodo({...editTodo, priority: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="urgent">Dringend</SelectItem><SelectItem value="high">Hoch</SelectItem><SelectItem value="medium">Mittel</SelectItem><SelectItem value="low">Niedrig</SelectItem></SelectContent></Select></div><div className="grid grid-cols-2 gap-3"><Select value={editTodo.status} onValueChange={v => setEditTodo({...editTodo, status: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="open">Offen</SelectItem><SelectItem value="in_progress">In Arbeit</SelectItem><SelectItem value="done">Erledigt</SelectItem><SelectItem value="cancelled">Abgebrochen</SelectItem></SelectContent></Select><div><label className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Startdatum</label><Input type="date" value={editTodo.startDate || ''} onChange={e => setEditTodo({...editTodo, startDate: e.target.value || null})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /></div></div><div className="grid grid-cols-2 gap-3"><div><label className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Dauer (Tage)</label><Input type="number" min={1} value={editTodo.durationDays} onChange={e => setEditTodo({...editTodo, durationDays: Math.max(1, parseInt(e.target.value) || 1)})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /></div><div>{editTodo.startDate && <><label className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Enddatum (berechnet)</label><div className="text-sm mt-1.5">{addDays(editTodo.startDate, Math.max(editTodo.durationDays - 1, 0))}</div></>}</div></div><div><label className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Projekt</label><Select value={editTodo.projectId || 'none'} onValueChange={v => setEditTodo({...editTodo, projectId: v === 'none' ? null : v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">— Kein Projekt</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select></div><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editTodo.title.trim()} onClick={() => editTodo.id === '__new__' ? handleCreateTodo(editTodo) : handleSaveTodo(editTodo)}>{editTodo.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button></div>}</DialogContent></Dialog>

      {/* Edit Blocker */}
      <Dialog open={!!editBlocker} onOpenChange={() => setEditBlocker(null)}><DialogContent className="max-w-4xl"><DialogHeader><DialogTitle>{editBlocker?.id === '__new__' ? 'Neuer Blocker' : 'Blocker bearbeiten'}</DialogTitle></DialogHeader>{editBlocker && <div className="space-y-3 pt-2"><Input placeholder="Titel" value={editBlocker.title} onChange={e => setEditBlocker({...editBlocker, title: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea placeholder="Beschreibung" value={editBlocker.description} onChange={e => setEditBlocker({...editBlocker, description: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><div className="grid grid-cols-2 gap-3"><Select value={editBlocker.reportedBy} onValueChange={v => setEditBlocker({...editBlocker, reportedBy: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select><Select value={editBlocker.status} onValueChange={v => setEditBlocker({...editBlocker, status: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="active">Aktiv</SelectItem><SelectItem value="resolved">Gelöst</SelectItem><SelectItem value="escalated">Eskaliert</SelectItem></SelectContent></Select></div><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editBlocker.title.trim()} onClick={() => editBlocker.id === '__new__' ? handleCreateBlocker(editBlocker) : handleSaveBlocker(editBlocker)}>{editBlocker.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button></div>}</DialogContent></Dialog>

      {/* Edit Open Item */}
      <Dialog open={!!editOpen} onOpenChange={() => setEditOpen(null)}><DialogContent className="max-w-4xl"><DialogHeader><DialogTitle>{editOpen?.id === '__new__' ? 'Neuer offener Punkt' : 'Offenen Punkt bearbeiten'}</DialogTitle></DialogHeader>{editOpen && <div className="space-y-3 pt-2"><Input placeholder="Titel" value={editOpen.title} onChange={e => setEditOpen({...editOpen, title: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea placeholder="Beschreibung" value={editOpen.description} onChange={e => setEditOpen({...editOpen, description: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><div className="grid grid-cols-2 gap-3"><Select value={editOpen.owner} onValueChange={v => setEditOpen({...editOpen, owner: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select><Select value={editOpen.category} onValueChange={v => setEditOpen({...editOpen, category: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="general">Allgemein</SelectItem><SelectItem value="risk">Risiko</SelectItem><SelectItem value="opportunity">Chance</SelectItem><SelectItem value="question">Frage</SelectItem><SelectItem value="follow_up">Nachverfolgung</SelectItem></SelectContent></Select></div><Select value={editOpen.status} onValueChange={v => setEditOpen({...editOpen, status: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="open">Offen</SelectItem><SelectItem value="watching">Beobachten</SelectItem><SelectItem value="closed">Geschlossen</SelectItem></SelectContent></Select><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editOpen.title.trim()} onClick={() => editOpen.id === '__new__' ? handleCreateOpen(editOpen) : handleSaveOpen(editOpen)}>{editOpen.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button></div>}</DialogContent></Dialog>

      {/* Edit Meeting */}
      <Dialog open={!!editMeeting} onOpenChange={() => setEditMeeting(null)}><DialogContent className="max-w-4xl"><DialogHeader><DialogTitle>Meeting bearbeiten</DialogTitle></DialogHeader>{editMeeting && <div className="space-y-3 pt-2"><Input value={editMeeting.title} onChange={e => setEditMeeting({...editMeeting, title: e.target.value})} placeholder="Titel" className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Input type="date" value={editMeeting.date} onChange={e => setEditMeeting({...editMeeting, date: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Input value={editMeeting.topics.join(', ')} onChange={e => setEditMeeting({...editMeeting, topics: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} placeholder="Themen (kommagetrennt)" className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Input value={editMeeting.participants.join(', ')} onChange={e => setEditMeeting({...editMeeting, participants: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} placeholder="Teilnehmer (kommagetrennt)" className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea value={editMeeting.summary} onChange={e => setEditMeeting({...editMeeting, summary: e.target.value})} placeholder="Zusammenfassung" rows={4} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Input value={editMeeting.keyDecisions.join(', ')} onChange={e => setEditMeeting({...editMeeting, keyDecisions: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} placeholder="Entscheidungen (kommagetrennt)" className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={() => handleSaveMeeting(editMeeting)}>Speichern</Button></div>}</DialogContent></Dialog>

      {/* Edit Project */}
      <Dialog open={!!editProject} onOpenChange={() => { setEditProject(null); setProjTodoQueue([]); setProjTodoNewForm(null); setProjLinkedTodoIds(new Set()); setProjLinkedMeetingIds(new Set()); setProjTodoPickerOpen(false); setProjMeetingPickerOpen(false); setProjectInitTodos('') }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editProject?.id === '__new__' ? 'Neues Projekt' : 'Projekt bearbeiten'}</DialogTitle></DialogHeader>
          {editProject && <div className="space-y-4 pt-2">
            {/* ── Basis ── */}
            <div>
              <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Projektname *</label>
              <Input placeholder="Name" value={editProject.name} onChange={e => setEditProject({...editProject, name: e.target.value})} className="mt-1 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
            </div>
            <div>
              <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Beschreibung</label>
              <Textarea placeholder="Beschreibung (optional)" value={editProject.description || ''} onChange={e => setEditProject({...editProject, description: e.target.value || null})} rows={2} className="mt-1 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Status</label>
                <Select value={editProject.status} onValueChange={v => setEditProject({...editProject, status: v})}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="active">Aktiv</SelectItem><SelectItem value="completed">Abgeschlossen</SelectItem><SelectItem value="on_hold">Pausiert</SelectItem></SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Priorität</label>
                <Select value={editProject.priority || 'medium'} onValueChange={v => setEditProject({...editProject, priority: v})}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="urgent">Dringend</SelectItem><SelectItem value="high">Hoch</SelectItem><SelectItem value="medium">Mittel</SelectItem><SelectItem value="low">Niedrig</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Verantwortlicher</label>
              <Select value={editProject.owner || 'none'} onValueChange={v => setEditProject({...editProject, owner: v === 'none' ? null : v})}>
                <SelectTrigger className="mt-1"><SelectValue placeholder="— Nicht zugeordnet" /></SelectTrigger>
                <SelectContent><SelectItem value="none">— Nicht zugeordnet</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Startdatum</label>
                <Input type="date" value={editProject.start_date || ''} onChange={e => setEditProject({...editProject, start_date: e.target.value || null})} className="mt-1 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
              </div>
              <div>
                <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Enddatum</label>
                <Input type="date" value={editProject.end_date || ''} onChange={e => setEditProject({...editProject, end_date: e.target.value || null})} className="mt-1 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
              </div>
            </div>

            {/* ── Todos ── */}
            <Separator className="bg-[var(--syn-line)]" />
            <div className="space-y-2">
              <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Todos</label>
              {/* Queue: neue Todos die beim Speichern erstellt werden */}
              {projTodoQueue.map((td, i) => (
                <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded" style={{ background: 'var(--syn-surface-2)' }}>
                  <span className="text-xs flex-1 truncate">{td.title}</span>
                  <Badge className={`text-[9px] shrink-0 ${PRI_STYLE[td.priority]}`}>{PRI_LABEL[td.priority]}</Badge>
                  <Badge className={`text-[9px] shrink-0 ${ST_STYLE[td.status]}`}>{ST_LABEL[td.status]}</Badge>
                  {td.assignee && td.assignee !== 'Nicht zugeordnet' && <Av name={td.assignee} />}
                  <button onClick={() => setProjTodoQueue(prev => prev.filter((_, j) => j !== i))} className="text-xs w-5 h-5 flex items-center justify-center rounded hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>✕</button>
                </div>
              ))}
              {/* Bereits verknüpfte bestehende Todos (nur Anzeige, kein X zum Entverknüpfen hier) */}
              {Array.from(projLinkedTodoIds).filter(id => !projTodoQueue.some(() => false) && todos.find(t => t.id === id)).map(id => {
                const td = todos.find(t => t.id === id)!
                return (
                  <div key={id} className="flex items-center gap-2 px-2 py-1.5 rounded border" style={{ background: 'var(--syn-surface-2)', borderColor: 'var(--syn-accent-line)' }}>
                    <span className="text-[10px] px-1 rounded" style={{ background: 'var(--syn-accent-soft)', color: 'var(--syn-accent)' }}>↗</span>
                    <span className="text-xs flex-1 truncate">{td.title}</span>
                    <Badge className={`text-[9px] shrink-0 ${ST_STYLE[td.status]}`}>{ST_LABEL[td.status]}</Badge>
                    <button onClick={() => { const s = new Set(projLinkedTodoIds); s.delete(id); setProjLinkedTodoIds(s) }} className="text-xs w-5 h-5 flex items-center justify-center rounded hover:text-[var(--syn-danger)]" style={{ color: 'var(--syn-text-faint)' }}>✕</button>
                  </div>
                )
              })}
              {/* Inline-Form neues Todo */}
              {projTodoNewForm !== null ? (
                <div className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'var(--syn-accent-line)', background: 'var(--syn-surface-2)' }}>
                  <Input placeholder="Titel *" value={projTodoNewForm.title} onChange={e => setProjTodoNewForm({...projTodoNewForm, title: e.target.value})} className="bg-[var(--syn-surface-3)] border-[var(--syn-line)] text-sm" />
                  <Textarea placeholder="Beschreibung" value={projTodoNewForm.description} onChange={e => setProjTodoNewForm({...projTodoNewForm, description: e.target.value})} rows={2} className="bg-[var(--syn-surface-3)] border-[var(--syn-line)] text-sm" />
                  <div className="grid grid-cols-3 gap-2">
                    <Select value={projTodoNewForm.assignee} onValueChange={v => setProjTodoNewForm({...projTodoNewForm, assignee: v})}>
                      <SelectTrigger className="text-xs h-8"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="Nicht zugeordnet">— Zuständig</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
                    </Select>
                    <Select value={projTodoNewForm.priority} onValueChange={v => setProjTodoNewForm({...projTodoNewForm, priority: v})}>
                      <SelectTrigger className="text-xs h-8"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="urgent">Dringend</SelectItem><SelectItem value="high">Hoch</SelectItem><SelectItem value="medium">Mittel</SelectItem><SelectItem value="low">Niedrig</SelectItem></SelectContent>
                    </Select>
                    <Select value={projTodoNewForm.status} onValueChange={v => setProjTodoNewForm({...projTodoNewForm, status: v})}>
                      <SelectTrigger className="text-xs h-8"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="open">Offen</SelectItem><SelectItem value="in_progress">In Arbeit</SelectItem><SelectItem value="done">Erledigt</SelectItem></SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div><label className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>Fällig</label><Input type="date" value={projTodoNewForm.dueDate || ''} onChange={e => setProjTodoNewForm({...projTodoNewForm, dueDate: e.target.value || null})} className="h-8 text-xs bg-[var(--syn-surface-3)] border-[var(--syn-line)]" /></div>
                    <div><label className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>Start</label><Input type="date" value={projTodoNewForm.startDate || ''} onChange={e => setProjTodoNewForm({...projTodoNewForm, startDate: e.target.value || null})} className="h-8 text-xs bg-[var(--syn-surface-3)] border-[var(--syn-line)]" /></div>
                    <div><label className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>Dauer (Tage)</label><Input type="number" min={1} value={projTodoNewForm.durationDays} onChange={e => setProjTodoNewForm({...projTodoNewForm, durationDays: Math.max(1, parseInt(e.target.value) || 1)})} className="h-8 text-xs bg-[var(--syn-surface-3)] border-[var(--syn-line)]" /></div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" className="text-xs bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!projTodoNewForm.title.trim()} onClick={() => { setProjTodoQueue(prev => [...prev, {...projTodoNewForm}]); setProjTodoNewForm(null) }}>Hinzufügen</Button>
                    <Button size="sm" variant="outline" className="text-xs border-[var(--syn-line)]" onClick={() => setProjTodoNewForm(null)}>Abbrechen</Button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="text-xs border-[var(--syn-line)] flex-1" onClick={() => setProjTodoNewForm({ id: '__new__', assignee: editProject.owner || 'Nicht zugeordnet', title: '', description: '', status: 'open', priority: 'medium', dueDate: null, startDate: null, durationDays: 1, dependsOn: [], meetingId: null, projectId: null, createdAt: '' })}>+ Todo erstellen</Button>
                </div>
              )}
              {/* Toggle: Vorhandene Todos verknüpfen */}
              <div className="flex items-center justify-between">
                <span className="text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Vorhandene verknüpfen</span>
                <button onClick={() => setProjTodoPickerOpen(v => !v)} className="text-[10px] px-2 py-0.5 rounded border hover:bg-[var(--syn-hover)]" style={{ borderColor: 'var(--syn-line)', color: 'var(--syn-accent)' }}>
                  {projTodoPickerOpen ? '▲ Schließen' : `▼ Verknüpfen${projLinkedTodoIds.size > 0 ? ` (${projLinkedTodoIds.size})` : ''}`}
                </button>
              </div>
              {projTodoPickerOpen && (
                <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--syn-line)' }}>
                  <Input placeholder="Todos durchsuchen…" value={projTodoSearch} onChange={e => setProjTodoSearch(e.target.value)} className="h-8 text-xs border-0 border-b rounded-none bg-[var(--syn-surface-2)]" style={{ borderColor: 'var(--syn-line)' }} />
                  {/* Header */}
                  <div className="grid text-[10px] font-semibold px-3 py-1 uppercase tracking-wide" style={{ gridTemplateColumns: '20px 72px 1fr 80px', background: 'var(--syn-surface-2)', color: 'var(--syn-text-faint)', borderBottom: '1px solid var(--syn-line)' }}>
                    <span />
                    <span>Datum</span>
                    <span>Name</span>
                    <span>Owner</span>
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {todos
                      .filter(t => { const q = projTodoSearch.toLowerCase(); return !q || t.title.toLowerCase().includes(q) })
                      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
                      .map(t => (
                        <label key={t.id} className="grid items-center px-3 py-1.5 cursor-pointer hover:bg-[var(--syn-hover)] border-b last:border-b-0 text-xs" style={{ gridTemplateColumns: '20px 72px 1fr 80px', borderColor: 'var(--syn-line)' }}>
                          <input type="checkbox" checked={projLinkedTodoIds.has(t.id)} onChange={e => { const s = new Set(projLinkedTodoIds); e.target.checked ? s.add(t.id) : s.delete(t.id); setProjLinkedTodoIds(s) }} className="rounded" />
                          <span className="shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{t.createdAt || '—'}</span>
                          <span className="truncate px-1">{t.title}</span>
                          <span className="truncate text-[10px]" style={{ color: 'var(--syn-text-muted)' }}>{t.assignee !== 'Nicht zugeordnet' ? t.assignee : '—'}</span>
                        </label>
                      ))}
                  </div>
                </div>
              )}
            </div>

            {/* ── Meetings verknüpfen ── */}
            <Separator className="bg-[var(--syn-line)]" />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Meetings verknüpfen</label>
                <button onClick={() => setProjMeetingPickerOpen(v => !v)} className="text-[10px] px-2 py-0.5 rounded border hover:bg-[var(--syn-hover)]" style={{ borderColor: 'var(--syn-line)', color: 'var(--syn-accent)' }}>
                  {projMeetingPickerOpen ? '▲ Schließen' : `▼ Auswählen${projLinkedMeetingIds.size > 0 ? ` (${projLinkedMeetingIds.size})` : ''}`}
                </button>
              </div>
              {/* Chips ausgewählter Meetings */}
              {projLinkedMeetingIds.size > 0 && (
                <div className="flex flex-wrap gap-1">
                  {Array.from(projLinkedMeetingIds).map(mid => {
                    const m = meetings.find(x => x.id === mid)
                    if (!m) return null
                    return <span key={mid} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'var(--syn-accent-soft)', color: 'var(--syn-accent)' }}>
                      {m.date} · {m.title.length > 22 ? m.title.slice(0, 22) + '…' : m.title}
                      <button onClick={() => { const s = new Set(projLinkedMeetingIds); s.delete(mid); setProjLinkedMeetingIds(s) }} className="hover:text-[var(--syn-danger)]">✕</button>
                    </span>
                  })}
                </div>
              )}
              {projMeetingPickerOpen && (
                <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--syn-line)' }}>
                  <Input placeholder="Meetings durchsuchen…" value={projMeetingSearch} onChange={e => setProjMeetingSearch(e.target.value)} className="h-8 text-xs border-0 border-b rounded-none bg-[var(--syn-surface-2)]" style={{ borderColor: 'var(--syn-line)' }} />
                  {/* Header */}
                  <div className="grid text-[10px] font-semibold px-3 py-1 uppercase tracking-wide" style={{ gridTemplateColumns: '20px 72px 1fr 120px', background: 'var(--syn-surface-2)', color: 'var(--syn-text-faint)', borderBottom: '1px solid var(--syn-line)' }}>
                    <span />
                    <span>Datum</span>
                    <span>Name</span>
                    <span>Themen</span>
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {meetings
                      .filter(m => { const q = projMeetingSearch.toLowerCase(); return !q || m.title.toLowerCase().includes(q) || m.date.includes(q) || m.topics.some(t => t.toLowerCase().includes(q)) })
                      .sort((a, b) => b.date.localeCompare(a.date))
                      .map(m => (
                        <label key={m.id} className="grid items-center px-3 py-1.5 cursor-pointer hover:bg-[var(--syn-hover)] border-b last:border-b-0 text-xs" style={{ gridTemplateColumns: '20px 72px 1fr 120px', borderColor: 'var(--syn-line)' }}>
                          <input type="checkbox" checked={projLinkedMeetingIds.has(m.id)} onChange={e => { const s = new Set(projLinkedMeetingIds); e.target.checked ? s.add(m.id) : s.delete(m.id); setProjLinkedMeetingIds(s) }} className="mt-0.5 rounded" />
                          <span className="shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{m.date}</span>
                          <span className="truncate px-1 font-medium">{m.title}</span>
                          <span className="truncate text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>{m.topics.slice(0, 3).join(', ')}{m.topics.length > 3 ? ` +${m.topics.length - 3}` : ''}</span>
                        </label>
                      ))}
                  </div>
                </div>
              )}
            </div>

            {/* ── Projektübersicht (nur Edit) ── */}
            {editProject.id !== '__new__' && (() => {
              const pT = projectTodos(editProject.id)
              const pB = projectBlockers(editProject.id)
              if (!pT.length && !pB.length) return null
              return <>
                <Separator className="bg-[var(--syn-line)]" />
                <div>
                  <label className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>Projektübersicht</label>
                  <div className="grid grid-cols-3 gap-3 mt-2">
                    <div className="rounded-lg p-2.5 text-center" style={{ background: 'var(--syn-surface-2)' }}><div className="text-lg font-bold" style={{ color: 'var(--syn-accent)' }}>{pT.length}</div><div className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>Todos</div></div>
                    <div className="rounded-lg p-2.5 text-center" style={{ background: 'var(--syn-surface-2)' }}><div className="text-lg font-bold" style={{ color: 'var(--syn-ok)' }}>{pT.filter(t => t.status === 'done').length}</div><div className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>Erledigt</div></div>
                    <div className="rounded-lg p-2.5 text-center" style={{ background: 'var(--syn-surface-2)' }}><div className="text-lg font-bold" style={{ color: 'var(--syn-info)' }}>{pT.filter(t => t.status === 'in_progress').length}</div><div className="text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>In Arbeit</div></div>
                  </div>
                  {pB.filter(b => b.status === 'active').length > 0 && <div className="mt-2 text-xs" style={{ color: 'var(--syn-danger)' }}>⚠ {pB.filter(b => b.status === 'active').length} aktive Blocker</div>}
                  <div className="mt-1 text-[11px]" style={{ color: 'var(--syn-text-faint)' }}>Erstellt: {editProject.created_at?.split('T')[0] || '—'}</div>
                </div>
              </>
            })()}

            <Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editProject.name.trim()} onClick={() => handleSaveProject(editProject)}>{editProject.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button>
          </div>}
        </DialogContent>
      </Dialog>

      {/* View Todo */}
      <Dialog open={!!viewTodo} onOpenChange={() => setViewTodo(null)}><DialogContent className="max-w-4xl">{viewTodo && <><DialogHeader className="text-left"><DialogTitle><div className="flex items-center gap-2">{viewTodo.title}<Badge variant="outline" className="text-[9px] border-[var(--syn-line)] shrink-0">Todo</Badge></div></DialogTitle></DialogHeader><div className="space-y-3 pt-2 text-left"><div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm"><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Zuständig</span><div className="flex items-center gap-1.5 mt-0.5"><Av name={viewTodo.assignee} /><span>{viewTodo.assignee}</span></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Priorität</span><div className="mt-0.5"><Badge className={`text-xs ${PRI_STYLE[viewTodo.priority]}`}>{PRI_LABEL[viewTodo.priority]}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Status</span><div className="mt-0.5"><Badge className={`text-xs ${ST_STYLE[viewTodo.status]}`}>{ST_LABEL[viewTodo.status]}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Dauer</span><div className="mt-0.5">{viewTodo.durationDays} Tag{viewTodo.durationDays !== 1 ? 'e' : ''}</div></div>{viewTodo.startDate && <div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Startdatum</span><div className="mt-0.5">{viewTodo.startDate}</div></div>}{viewTodo.startDate && <div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Enddatum</span><div className="mt-0.5">{addDays(viewTodo.startDate, Math.max(viewTodo.durationDays - 1, 0))}</div></div>}<div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Erstellt</span><div className="mt-0.5">{viewTodo.createdAt || '—'}</div></div>{getProjectName(viewTodo.projectId) && <div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Projekt</span><div className="mt-0.5 flex items-center gap-2"><span>{getProjectName(viewTodo.projectId)}</span><button onClick={() => { setViewTodo(null); setPage('projekte'); setProjectView('gantt') }} className="text-[10px] underline hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-muted)' }}>Gantt</button><button onClick={() => { setViewTodo(null); setPage('projekte'); setProjectView('kanban') }} className="text-[10px] underline hover:text-[var(--syn-accent)]" style={{ color: 'var(--syn-text-muted)' }}>Kanban</button></div></div>}</div>{viewTodo.description && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Beschreibung</span><p className="text-sm mt-1 leading-relaxed whitespace-pre-wrap">{viewTodo.description}</p></div></>}{viewTodo.dependsOn.length > 0 && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Abhängig von</span><div className="mt-1 space-y-1">{viewTodo.dependsOn.map(depId => { const dep = todos.find(t => t.id === depId); return dep ? <button key={depId} onClick={() => { setViewTodo(null); setTimeout(() => setViewTodo(dep), 100) }} className="block text-sm hover:text-[var(--syn-accent)]">{dep.title}</button> : null })}</div></div></>}{viewTodo.meetingId && getMeeting(viewTodo.meetingId) && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Meeting</span><div className="mt-0.5"><SourceChip meeting={getMeeting(viewTodo.meetingId)!} onClick={() => { setViewTodo(null); setViewMeeting(getMeeting(viewTodo.meetingId!)!) }} /></div></div></>}<Separator className="bg-[var(--syn-line)]" /><div className="flex gap-2"><Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewTodo(null); setEditTodo({...viewTodo}) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => setConfirmDelete({ label: viewTodo.title, action: () => { handleDeleteTodo(viewTodo); setViewTodo(null) } })}>{'✕'} Löschen</Button></div></div></>}</DialogContent></Dialog>

      {/* View Blocker */}
      <Dialog open={!!viewBlocker} onOpenChange={() => setViewBlocker(null)}><DialogContent className="max-w-4xl">{viewBlocker && <><DialogHeader className="text-left"><DialogTitle><div className="flex items-center gap-2">{viewBlocker.title}<Badge variant="outline" className="text-[9px] border-[var(--syn-line)] shrink-0">Blocker</Badge></div></DialogTitle></DialogHeader><div className="space-y-3 pt-2 text-left"><div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm"><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Zuständig</span><div className="flex items-center gap-1.5 mt-0.5"><Av name={viewBlocker.reportedBy} /><span>{viewBlocker.reportedBy}</span></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Status</span><div className="mt-0.5"><Badge className={`text-xs ${ST_STYLE[viewBlocker.status]}`}>{ST_LABEL[viewBlocker.status]}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Erstellt</span><div className="mt-0.5">{viewBlocker.createdAt || '—'}</div></div></div>{viewBlocker.description && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Beschreibung</span><p className="text-sm mt-1 leading-relaxed whitespace-pre-wrap">{viewBlocker.description}</p></div></>}{viewBlocker.meetingId && getMeeting(viewBlocker.meetingId) && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Meeting</span><div className="mt-0.5"><SourceChip meeting={getMeeting(viewBlocker.meetingId)!} onClick={() => { setViewBlocker(null); setViewMeeting(getMeeting(viewBlocker.meetingId!)!) }} /></div></div></>}<Separator className="bg-[var(--syn-line)]" /><div className="flex gap-2">{viewBlocker.status === 'active' && <Button size="sm" className="text-xs bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={() => { handleResolveBlocker(viewBlocker); setViewBlocker(null) }}>Lösen</Button>}<Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewBlocker(null); setEditBlocker({...viewBlocker}) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => setConfirmDelete({ label: viewBlocker.title, action: () => { handleDeleteBlocker(viewBlocker); setViewBlocker(null) } })}>{'✕'} Löschen</Button></div></div></>}</DialogContent></Dialog>

      {/* View Open Item */}
      <Dialog open={!!viewOpen} onOpenChange={() => setViewOpen(null)}><DialogContent className="max-w-4xl">{viewOpen && <><DialogHeader className="text-left"><DialogTitle><div className="flex items-center gap-2">{viewOpen.title}<Badge variant="outline" className="text-[9px] border-[var(--syn-line)] shrink-0">Offener Punkt</Badge></div></DialogTitle></DialogHeader><div className="space-y-3 pt-2 text-left"><div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm"><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Zuständig</span><div className="flex items-center gap-1.5 mt-0.5"><Av name={viewOpen.owner} /><span>{viewOpen.owner}</span></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Kategorie</span><div className="mt-0.5"><Badge variant="outline" className="text-xs border-[var(--syn-line)]">{CAT_LABEL[viewOpen.category] || viewOpen.category}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Status</span><div className="mt-0.5"><Badge className={`text-xs ${ST_STYLE[viewOpen.status]}`}>{ST_LABEL[viewOpen.status]}</Badge></div></div><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Erstellt</span><div className="mt-0.5">{viewOpen.createdAt || '—'}</div></div></div>{viewOpen.description && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Beschreibung</span><p className="text-sm mt-1 leading-relaxed whitespace-pre-wrap">{viewOpen.description}</p></div></>}{viewOpen.meetingId && getMeeting(viewOpen.meetingId) && <><Separator className="bg-[var(--syn-line)]" /><div><span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Meeting</span><div className="mt-0.5"><SourceChip meeting={getMeeting(viewOpen.meetingId)!} onClick={() => { setViewOpen(null); setViewMeeting(getMeeting(viewOpen.meetingId!)!) }} /></div></div></>}<Separator className="bg-[var(--syn-line)]" /><div className="flex gap-2">{viewOpen.status !== 'closed' && <Button size="sm" className="text-xs bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={() => { handleCloseItem(viewOpen); setViewOpen(null) }}>Schließen</Button>}<Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { setViewOpen(null); setEditOpen({...viewOpen}) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => setConfirmDelete({ label: viewOpen.title, action: () => { handleDeleteOpen(viewOpen); setViewOpen(null) } })}>{'✕'} Löschen</Button></div></div></>}</DialogContent></Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!confirmDelete} onOpenChange={() => setConfirmDelete(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Element endgültig löschen</DialogTitle></DialogHeader>
          <div className="space-y-4 pt-2">
            <p className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Bist du sicher, dass du <strong>{confirmDelete?.label}</strong> löschen möchtest? Diese Aktion kann nicht rückgängig gemacht werden.</p>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => setConfirmDelete(null)}>Abbrechen</Button>
              <Button size="sm" className="text-xs bg-[var(--syn-danger)] hover:bg-[var(--syn-danger)] text-white" onClick={() => { confirmDelete?.action(); setConfirmDelete(null) }}>Löschen</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ═══ PRINT VIEW ═══ */}
      {printView && <div className="fixed inset-0 z-[9999] bg-white text-black overflow-auto print-view" style={{ colorScheme: 'light' }}>
        <div className="p-6 print:p-0">
          <div className="flex items-center justify-between mb-6 print:hidden">
            <h1 className="text-xl font-bold text-black">{printView === 'kanban' ? 'Kanban-Ansicht' : 'Gantt-Ansicht'} — Projekte</h1>
            <div className="flex gap-2">
              <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white text-xs" onClick={() => window.print()}>Drucken</Button>
              <Button size="sm" className="text-xs bg-white hover:bg-gray-100 text-black border border-gray-300" onClick={() => setPrintView(null)}>✕ Schließen</Button>
            </div>
          </div>
          <div className="text-xs text-gray-400 mb-4 print:mb-2 print:block hidden">Gedruckt am {new Date().toLocaleDateString('de-DE')} — Meeting OS</div>

          {printView === 'kanban' && (() => {
            const statuses = ['open', 'in_progress', 'done'] as const
            const statusLabels: Record<string, string> = { open: 'Offen', in_progress: 'In Arbeit', done: 'Erledigt' }
            const statusColors: Record<string, string> = { open: '#e5e7eb', in_progress: '#dbeafe', done: '#dcfce7' }
            const allProjectTodos = kanbanTodosMemo
            const renderPrintCard = (t: Todo) => (
              <div key={t.id} className="bg-white rounded border border-gray-200 p-2.5 text-xs" style={{ borderLeftWidth: 3, borderLeftStyle: 'solid', borderLeftColor: getProjectColor(t.projectId, projectIds) }}>
                <div className="font-medium text-sm text-black">{t.title}</div>
                <div className="flex items-center gap-2 mt-1 text-gray-500 flex-wrap">
                  {kanbanFields.has('priority') && <span className="font-medium" style={{ color: t.priority === 'urgent' || t.priority === 'high' ? '#dc2626' : '#6b7280' }}>{PRI_LABEL[t.priority]}</span>}
                  {kanbanFields.has('assignee') && t.assignee && t.assignee !== 'Nicht zugeordnet' && <span>{t.assignee}</span>}
                  {kanbanFields.has('duration') && t.durationDays > 0 && <span>{t.durationDays}d</span>}
                </div>
                {kanbanFields.has('dueDate') && t.dueDate && <div className={`text-[10px] mt-1 ${t.dueDate < today && t.status !== 'done' ? 'text-red-600 font-bold' : 'text-gray-400'}`}>Fällig: {t.dueDate}</div>}
                {kanbanFields.has('project') && t.projectId && <div className="text-[10px] mt-0.5 text-gray-400">{getProjectName(t.projectId)}</div>}
              </div>
            )
            const renderPrintColumns = (todosForGroup: Todo[]) => (
              <div className="grid grid-cols-3 gap-4">
                {statuses.map(st => {
                  const colTodos = todosForGroup.filter(t => t.status === st)
                  return (
                    <div key={st} className="rounded-lg border border-gray-200 overflow-hidden">
                      <div className="px-4 py-2 font-semibold text-sm border-b border-gray-200" style={{ background: statusColors[st] }}>{statusLabels[st]} ({colTodos.length})</div>
                      <div className="p-2 space-y-2 bg-gray-50 min-h-[60px]">
                        {colTodos.map(renderPrintCard)}
                      </div>
                    </div>
                  )
                })}
              </div>
            )
            if (kanbanGroupBy === 'none') return renderPrintColumns(allProjectTodos)
            // Grouped view
            const groups = new Map<string, Todo[]>()
            allProjectTodos.forEach(t => {
              const key = kanbanGroupBy === 'project' ? (getProjectName(t.projectId) || 'Kein Projekt') : t.assignee
              if (!groups.has(key)) groups.set(key, [])
              groups.get(key)!.push(t)
            })
            return <div className="space-y-6">
              {Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([label, groupTodos]) => (
                <div key={label}>
                  <h3 className="text-sm font-bold text-gray-700 mb-2 pb-1 border-b border-gray-200">{label} ({groupTodos.length})</h3>
                  {renderPrintColumns(groupTodos)}
                </div>
              ))}
            </div>
          })()}

          {printView === 'gantt' && (() => {
            const colLabels: Record<string, string> = { project: 'Projekt', title: 'Aufgabe', assignee: 'Zuständig', priority: 'Priorität' }
            const printColW: Record<string, number> = { project: 120, title: 180, assignee: 100, priority: 80 }
            const renderCol = (col: string, t: Todo) => {
              if (col === 'project') return <div key={col} className="shrink-0 border-r border-gray-200 flex items-center px-2 text-xs text-gray-600 truncate" style={{ width: printColW[col] }}>{getProjectName(t.projectId) || '—'}</div>
              if (col === 'title') return <div key={col} className="shrink-0 border-r border-gray-200 flex items-center px-2 text-xs font-medium text-black truncate" style={{ width: printColW[col] }}>{t.title}</div>
              if (col === 'assignee') return <div key={col} className="shrink-0 border-r border-gray-200 flex items-center px-2 text-xs text-gray-600 truncate" style={{ width: printColW[col] }}>{t.assignee}</div>
              if (col === 'priority') return <div key={col} className="shrink-0 border-r border-gray-200 flex items-center px-2" style={{ width: printColW[col] }}><span className={`px-1.5 py-0.5 rounded text-[10px] ${t.priority === 'urgent' || t.priority === 'high' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>{PRI_LABEL[t.priority]}</span></div>
              return null
            }
            const printTodos = ganttTodos
            if (!printTodos.length) return <div className="text-gray-400 text-sm">Keine Todos mit Startdatum vorhanden.</div>
            const minDate = printTodos.reduce((m, t) => t.startDate! < m ? t.startDate! : m, printTodos[0].startDate!)
            const maxDate = printTodos.reduce((m, t) => { const e = addDays(t.startDate!, t.durationDays - 1); return e > m ? e : m }, printTodos[0].startDate!)
            const dayDiff = (a: string, b: string) => Math.round((new Date(a).getTime() - new Date(b).getTime()) / 86400000)
            const totalDays = Math.max(dayDiff(maxDate, minDate) + 1, 7)
            const pLabelW = ganttVisibleCols.reduce((s, c) => s + (printColW[c] || 100), 0)
            const PMONTH_NAMES = ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez']
            // Build month groups for print header
            const pMonthGroups: { label: string; days: number }[] = []
            for (let d = 0; d < totalDays; d++) {
              const dt = new Date(new Date(minDate).getTime() + d * 86400000)
              const lbl = `${PMONTH_NAMES[dt.getMonth()]} ${dt.getFullYear()}`
              if (pMonthGroups.length && pMonthGroups[pMonthGroups.length - 1].label === lbl) pMonthGroups[pMonthGroups.length - 1].days++
              else pMonthGroups.push({ label: lbl, days: 1 })
            }
            // Build day labels
            const pDays: { label: string; isWE: boolean }[] = []
            for (let d = 0; d < totalDays; d++) {
              const dt = new Date(new Date(minDate).getTime() + d * 86400000)
              pDays.push({ label: String(dt.getDate()), isWE: dt.getDay() === 0 || dt.getDay() === 6 })
            }
            const pColW = Math.max(Math.floor((typeof window !== 'undefined' ? window.innerWidth - pLabelW - 60 : 800) / totalDays), 14)
            return <div className="overflow-x-auto border border-gray-200 rounded-lg">
              <div style={{ minWidth: `${pLabelW + totalDays * pColW}px` }}>
                {/* Month header row */}
                <div className="flex border-b border-gray-200" style={{ background: '#f3f4f6' }}>
                  {ganttVisibleCols.map(c => <div key={c} className="shrink-0 border-r border-gray-200" style={{ width: printColW[c], background: '#e5e7eb' }} />)}
                  {pMonthGroups.map((mg, i) => <div key={i} className="text-[10px] font-semibold border-r border-gray-200 flex items-center justify-center py-1 text-gray-600" style={{ width: mg.days * pColW }}>{mg.label}</div>)}
                </div>
                {/* Day header row */}
                <div className="flex border-b-2 border-gray-300" style={{ background: '#f3f4f6' }}>
                  {ganttVisibleCols.map(c => <div key={c} className="shrink-0 border-r border-gray-200 text-[10px] flex items-center px-2 py-0.5 font-medium text-gray-500" style={{ width: printColW[c], background: '#e5e7eb' }}>{colLabels[c]}</div>)}
                  {pDays.map((pd, i) => <div key={i} className="text-[9px] text-center flex items-center justify-center border-r border-gray-100 py-0.5" style={{ width: pColW, color: pd.isWE ? '#9ca3af' : '#6b7280', background: pd.isWE ? '#f9fafb' : undefined }}>{pd.label}</div>)}
                </div>
                {/* Body rows */}
                {printTodos.map(t => {
                  const offset = dayDiff(t.startDate!, minDate)
                  return <div key={t.id} className="flex border-b border-gray-100" style={{ height: 28 }}>
                    {ganttVisibleCols.map(c => renderCol(c, t))}
                    <div className="flex-1 relative" style={{ height: 28 }}>
                      {pDays.map((pd, i) => pd.isWE ? <div key={i} className="absolute top-0 h-full" style={{ left: i * pColW, width: pColW, background: '#f9fafb' }} /> : null)}
                      <div className="absolute top-1.5 rounded" style={{ left: offset * pColW, width: Math.max(t.durationDays * pColW, 6), height: 16, background: getProjectColor(t.projectId, projectIds), opacity: t.status === 'done' ? 0.4 : 0.85 }}>
                        <span className="text-[7px] text-white px-1 truncate block" style={{ lineHeight: '16px' }}>{t.title}</span>
                      </div>
                    </div>
                  </div>
                })}
              </div>
            </div>
          })()}
        </div>
      </div>}
    </div>
  )
}
