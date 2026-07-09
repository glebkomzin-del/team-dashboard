import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  fetchTeamMembers, fetchMeetings, fetchMeetingLinks, fetchMeetingRawTranscript, fetchMeetingTopics, fetchTableCounts, fetchTodos, fetchBlockers, fetchOpenItems, fetchActivityLog,
  fetchMemoryMetrics,
  fetchProjects, insertProject,
  updateTodoStatus, deleteTodoDb, updateBlockerStatus, deleteBlockerDb,
  updateOpenItemStatus, deleteOpenItemDb, deleteMeetingDb,
  deleteActivityLogDb,
  updateTodoFull, updateBlockerFull, updateOpenItemFull, updateMeetingWithTopics,
  updateProjectFull, deleteProjectDb,
  fetchProjectMeetings, setProjectMeetings,
  insertTodo, insertBlocker, insertOpenItem, supabase,

  fetchInboxItems, updateInboxItemPayload, deleteInboxItemDb, approveInboxItem,
  isNightlyJobActive, toggleNightlyJob,
  signIn, signOut, resetPassword, getSession, onAuthStateChange,
  askMemory, askMemoryStream,
  type DbTeamMember, type DbProject, type DbInboxItem, type DbMeetingLink, type DbMeetingTopic, type TableCounts, type DbMemoryMetric
} from './supabase'

import {
  type Page, type ProjectView, type ActionTab,
  PRI_LABEL, PRI_STYLE, ST_STYLE, ST_LABEL, CAT_LABEL,
  MEMBER_ORDER,
  mutationErrorMessage, computeChatCost,
  Av, SourceChip,
  sanitizeHtml, shortTopic,
  normalizeTopicDetails, stripEmbeddedTopicsFromSummary,
  addDays, textMatch,
  type Todo, type Blocker, type OpenItem, type Meeting, type MeetingTopicDetail, type Activity, type ChatMessage,
} from './lib/shared'
import { TextSearchPage } from './pages/TextSearchPage'
import { ActivityPage } from './pages/ActivityPage'
import { MeetingsPage } from './pages/MeetingsPage'
import { ActionsPage } from './pages/ActionsPage'
import { InboxPage } from './pages/InboxPage'
import { CommandCenterPage } from './pages/CommandCenterPage'
import { KiPage } from './pages/KiPage'
import { ProjectsPage } from './pages/ProjectsPage'


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
  // Restore scroll position after data finishes loading.
  // Auf der KI-Seite überspringen wir die Saved-Position und scrollen den Chat-
  // Container direkt nach unten (nicht das Window — der Chat hat eigenes overflow).
  useEffect(() => {
    if (!loading && !scrollRestored.current) {
      scrollRestored.current = true
      const hash = window.location.hash.replace('#', '')
      if (hash === 'ki') {
        // KI-Seite scrollt ihren Chat-Container selbst (KiPage-Mount-Effekt).
        window.scrollTo(0, 0)
      } else {
        const saved = sessionStorage.getItem('mos_scrollY')
        if (saved) { const y = parseInt(saved, 10); requestAnimationFrame(() => window.scrollTo(0, y)) }
      }
    }
  }, [loading])
  const [error, setError] = useState<string | null>(null)
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
  const [meetingLinks, setMeetingLinks] = useState<DbMeetingLink[]>([])
  const [activity, setActivity] = useState<Activity[]>([])
  const [projects, setProjects] = useState<DbProject[]>([])
  const projectIds = useMemo(() => projects.map(p => p.id), [projects])
  const [inboxItems, setInboxItems] = useState<DbInboxItem[]>([])
  const [tableCounts, setTableCounts] = useState<TableCounts>({ meetings: 0, todos: 0, blockers: 0, openItems: 0, inbox: 0 })

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
      // Pro Nachricht anhand des eigenen Zeitstempels bereinigen — der Eintrags-
      // savedAt wird bei jedem Speichern erneuert und taugt nicht als Verfallsdatum.
      const messages = stored
        .flatMap(e => e.messages.map(m => ({ ...m, timestamp: m.timestamp ?? e.savedAt })))
        .filter(m => (m.timestamp ?? 0) > cutoff)
      return messages
    } catch { return [] }
  }
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(loadChatHistory)
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  // KI-Kosten-Tracker
  const [memoryMetrics, setMemoryMetrics] = useState<DbMemoryMetric[]>([])

  // Filters

  // Edit state
  const [editTodo, setEditTodo] = useState<Todo | null>(null)
  const [editBlocker, setEditBlocker] = useState<Blocker | null>(null)
  const [editOpen, setEditOpen] = useState<OpenItem | null>(null)
  const [editMeeting, setEditMeeting] = useState<Meeting | null>(null)
  const [editProject, setEditProject] = useState<DbProject | null>(null)
  const [projectMutationError, setProjectMutationError] = useState<string | null>(null)
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
  const [rawTranscript, setRawTranscript] = useState<string | null>(null)
  const [rawTranscriptLoaded, setRawTranscriptLoaded] = useState(false)
  const [rawTranscriptOpen, setRawTranscriptOpen] = useState(false)
  const [rawTranscriptLoading, setRawTranscriptLoading] = useState(false)
  const [rawTranscriptError, setRawTranscriptError] = useState<string | null>(null)
  const [meetingTopicDetails, setMeetingTopicDetails] = useState<MeetingTopicDetail[]>([])
  const [meetingTopicsLoading, setMeetingTopicsLoading] = useState(false)
  const [meetingTopicsError, setMeetingTopicsError] = useState<string | null>(null)
  const [viewTodo, setViewTodo] = useState<Todo | null>(null)
  const [viewBlocker, setViewBlocker] = useState<Blocker | null>(null)
  const [viewOpen, setViewOpen] = useState<OpenItem | null>(null)
  const [viewProject, setViewProject] = useState<DbProject | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ label: string; action: () => void } | null>(null)
  const [sidebarCollapsed, setSidebarCollapsedRaw] = useState(() => sessionStorage.getItem('mos_sidebar') === '1')
  const setSidebarCollapsed = (v: boolean | ((prev: boolean) => boolean)) => {
    setSidebarCollapsedRaw(prev => { const next = typeof v === 'function' ? v(prev) : v; sessionStorage.setItem('mos_sidebar', next ? '1' : '0'); return next })
  }

  // Bulk-select sets

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
      const [mems, mtgs, links, tds, blk, oi, act, prj, inbox, counts] = await Promise.all([
        fetchTeamMembers(), fetchMeetings(), fetchMeetingLinks(), fetchTodos(), fetchBlockers(), fetchOpenItems(), fetchActivityLog(), fetchProjects(), fetchInboxItems(), fetchTableCounts()
      ])
      setInboxItems(inbox)
      setTableCounts(counts)
      setMembers(mems); setProjects(prj)
      setMeetingLinks(links)
      setMeetings(mtgs.map(m => ({ id: m.id, title: m.title, date: m.meeting_date?.split('T')[0] || '', topics: m.topics || [], participants: m.participants || [], summary: m.ai_summary || '', keyDecisions: m.key_decisions || [], sourceKind: 'promoted' as const })))
      setTodos(tds.map(t => ({ id: t.id, assignee: t.assignee || 'Nicht zugeordnet', title: t.title, description: t.description || '', status: t.status, priority: t.priority, dueDate: t.due_date, startDate: (t as any).start_date || null, durationDays: (t as any).duration_days || 1, dependsOn: (t as any).depends_on || [], meetingId: t.meeting_id, meetingSource: t.meeting_source, projectId: (t as any).project_id || null, createdAt: t.created_at?.split('T')[0] || '' })))
      setBlockers(blk.map(b => ({ id: b.id, reportedBy: b.reported_by || 'Nicht zugeordnet', title: b.title, description: b.description || '', status: b.status, meetingId: b.meeting_id, meetingSource: b.meeting_source, projectId: (b as any).project_id || null, createdAt: b.created_at?.split('T')[0] || '' })))
      setOpenItems(oi.map(o => ({ id: o.id, owner: o.owner || 'Nicht zugeordnet', title: o.title, description: o.description || '', category: o.category, status: o.status, meetingId: o.meeting_id, meetingSource: o.meeting_source, projectId: (o as any).project_id || null, createdAt: o.created_at?.split('T')[0] || '' })))
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

  // KI-Kosten: Metriken laden (beim Mount + nach jeder Chat-Antwort)
  const refreshMemoryMetrics = useCallback(async () => {
    try { setMemoryMetrics(await fetchMemoryMetrics()) } catch { /* stillgestillt */ }
  }, [])
  useEffect(() => { refreshMemoryMetrics() }, [refreshMemoryMetrics])


  useEffect(() => { loadData(); isNightlyJobActive().then(setNightlyActive).catch(() => {}) }, [loadData])
  useEffect(() => {
    if (loading) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      fetchTableCounts().then(counts => { if (!cancelled) setTableCounts(counts) }).catch(() => {})
    }, 150)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [loading, meetings.length, todos.length, blockers.length, openItems.length, inboxItems.length])
  // Reset inbox edit mode whenever any edit modal closes
  useEffect(() => { if (!editTodo && !editBlocker && !editOpen && !editMeeting) setInboxEditModeFor(null) }, [editTodo, editBlocker, editOpen, editMeeting])
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
      try {
        const current = inboxItems.find(item => item.id === inboxEditModeFor)
        if (!current) throw new Error('Inbox-Eintrag nicht mehr vorhanden')
        const savedPayload = await updateInboxItemPayload(inboxEditModeFor, { ...current.payload, ...payload })
        setInboxItems(prev => prev.map(x => x.id === inboxEditModeFor ? { ...x, payload: savedPayload } : x))
        setEditTodo(null); setInboxEditModeFor(null)
      } catch (e: any) { setError(e.message || 'Änderungen konnten nicht gespeichert werden') }
      return
    }
    setTodos(prev => prev.map(x => x.id === t.id ? t : x)); setEditTodo(null); try { await updateTodoFull(t.id, { title: t.title, description: t.description, assignee: t.assignee, priority: t.priority, status: t.status, due_date: t.dueDate, start_date: t.startDate, duration_days: t.durationDays, project_id: t.projectId, depends_on: t.dependsOn } as any) } catch { }
  }
  const handleResolveBlocker = async (b: Blocker) => { setBlockers(prev => prev.map(x => x.id === b.id ? { ...x, status: 'resolved' } : x)); try { await updateBlockerStatus(b.id, 'resolved') } catch { } }
  const handleDeleteBlocker = async (b: Blocker) => { setBlockers(prev => prev.filter(x => x.id !== b.id)); try { await deleteBlockerDb(b.id) } catch { } }
  const handleSaveBlocker = async (b: Blocker) => {
    if (inboxEditModeFor) {
      const payload = { title: b.title, description: b.description, reported_by: b.reportedBy, status: b.status }
      try {
        const current = inboxItems.find(item => item.id === inboxEditModeFor)
        if (!current) throw new Error('Inbox-Eintrag nicht mehr vorhanden')
        const savedPayload = await updateInboxItemPayload(inboxEditModeFor, { ...current.payload, ...payload })
        setInboxItems(prev => prev.map(x => x.id === inboxEditModeFor ? { ...x, payload: savedPayload } : x))
        setEditBlocker(null); setInboxEditModeFor(null)
      } catch (e: any) { setError(e.message || 'Änderungen konnten nicht gespeichert werden') }
      return
    }
    setBlockers(prev => prev.map(x => x.id === b.id ? b : x)); setEditBlocker(null); try { await updateBlockerFull(b.id, { title: b.title, description: b.description, reported_by: b.reportedBy, status: b.status }) } catch { }
  }
  const handleCloseItem = async (o: OpenItem) => { setOpenItems(prev => prev.map(x => x.id === o.id ? { ...x, status: 'closed' } : x)); try { await updateOpenItemStatus(o.id, 'closed') } catch { } }
  const handleDeleteOpen = async (o: OpenItem) => { setOpenItems(prev => prev.filter(x => x.id !== o.id)); try { await deleteOpenItemDb(o.id) } catch { } }
  const handleSaveOpen = async (o: OpenItem) => {
    if (inboxEditModeFor) {
      const payload = { title: o.title, description: o.description, owner: o.owner, category: o.category, status: o.status }
      try {
        const current = inboxItems.find(item => item.id === inboxEditModeFor)
        if (!current) throw new Error('Inbox-Eintrag nicht mehr vorhanden')
        const savedPayload = await updateInboxItemPayload(inboxEditModeFor, { ...current.payload, ...payload })
        setInboxItems(prev => prev.map(x => x.id === inboxEditModeFor ? { ...x, payload: savedPayload } : x))
        setEditOpen(null); setInboxEditModeFor(null)
      } catch (e: any) { setError(e.message || 'Änderungen konnten nicht gespeichert werden') }
      return
    }
    setOpenItems(prev => prev.map(x => x.id === o.id ? o : x)); setEditOpen(null); try { await updateOpenItemFull(o.id, { title: o.title, description: o.description, owner: o.owner, category: o.category, status: o.status }) } catch { }
  }
  const handleDeleteMeeting = async (m: Meeting) => { setMeetings(prev => prev.filter(x => x.id !== m.id)); setMeetingLinks(prev => prev.map(link => link.meeting_id === m.id ? { ...link, deleted_at: new Date().toISOString() } : link)); try { await deleteMeetingDb(m.id) } catch { await loadData().catch(() => {}) } }
  const handleDeleteActivity = async (a: Activity) => {
    setActivity(prev => prev.filter(x => x.id !== a.id))
    try { await deleteActivityLogDb(a.id) } catch { loadData().catch(() => {}) }
  }

  // ── Inbox handlers ──
  const handleInboxApprove = async (item: DbInboxItem) => {
    const p = item.payload
    try {
      if (item.entity_type === 'todo') {
        const srcDate = p.meeting_date || item.created_at?.split('T')[0] || new Date().toISOString().split('T')[0]
        const c = await insertTodo({ title: p.title, description: p.description, assignee: p.assignee || 'Nicht zugeordnet', priority: p.priority || 'medium', due_date: p.due_date || null, created_at: srcDate, meeting_id: p.meeting_id || null, meeting_source: p.meeting_source || item.source || null })
        setTodos(prev => [{ id: c.id, assignee: c.assignee, title: c.title, description: c.description || '', status: c.status, priority: c.priority, dueDate: c.due_date, startDate: null, durationDays: 1, dependsOn: [], meetingId: c.meeting_id, meetingSource: c.meeting_source, projectId: null, createdAt: srcDate }, ...prev])
      } else if (item.entity_type === 'blocker') {
        const srcDate = p.meeting_date || item.created_at?.split('T')[0] || new Date().toISOString().split('T')[0]
        const c = await insertBlocker({ title: p.title, description: p.description, reported_by: p.reported_by || 'Nicht zugeordnet', created_at: srcDate, meeting_id: p.meeting_id || null, meeting_source: p.meeting_source || item.source || null })
        setBlockers(prev => [{ id: c.id, reportedBy: c.reported_by, title: c.title, description: c.description || '', status: c.status, meetingId: c.meeting_id, meetingSource: c.meeting_source, projectId: null, createdAt: srcDate }, ...prev])
      } else if (item.entity_type === 'open_item') {
        const srcDate = p.meeting_date || item.created_at?.split('T')[0] || new Date().toISOString().split('T')[0]
        const c = await insertOpenItem({ title: p.title, description: p.description, owner: p.owner || 'Nicht zugeordnet', category: p.category || 'info', created_at: srcDate, meeting_id: p.meeting_id || null, meeting_source: p.meeting_source || item.source || null })
        setOpenItems(prev => [{ id: c.id, owner: c.owner, title: c.title, description: c.description || '', category: c.category, status: c.status, meetingId: c.meeting_id, meetingSource: c.meeting_source, projectId: null, createdAt: srcDate }, ...prev])
      } else if (item.entity_type === 'resolution') {
        const targetId = String(p.target_id || '')
        const evidenceDate = p.evidence_meeting_date || new Date().toISOString().split('T')[0]
        const quote = String(p.evidence_quote || '')
        if (p.target_table === 'todos') {
          if (!todos.some(t => t.id === targetId)) {
            await approveInboxItem(item.id, 'rejected')
            setInboxItems(prev => prev.filter(x => x.id !== item.id))
            setError('Vorschlag verworfen: Das Ziel-Todo existiert nicht mehr.')
            return
          }
          await updateTodoFull(targetId, { status: 'done', completed_at: evidenceDate } as any)
          setTodos(prev => prev.map(t => t.id === targetId ? { ...t, status: 'done' } : t))
        } else if (p.target_table === 'blockers') {
          if (!blockers.some(b => b.id === targetId)) {
            await approveInboxItem(item.id, 'rejected')
            setInboxItems(prev => prev.filter(x => x.id !== item.id))
            setError('Vorschlag verworfen: Der Ziel-Blocker existiert nicht mehr.')
            return
          }
          const shortQuote = quote.length > 180 ? `${quote.slice(0, 177)}...` : quote
          await updateBlockerFull(targetId, { status: 'resolved', resolved_at: evidenceDate, resolution_note: `lt. Meeting vom ${evidenceDate}: ${shortQuote}` } as any)
          setBlockers(prev => prev.map(b => b.id === targetId ? { ...b, status: 'resolved' } : b))
        } else if (p.target_table === 'open_items') {
          if (!openItems.some(o => o.id === targetId)) {
            await approveInboxItem(item.id, 'rejected')
            setInboxItems(prev => prev.filter(x => x.id !== item.id))
            setError('Vorschlag verworfen: Der offene Punkt existiert nicht mehr.')
            return
          }
          await updateOpenItemFull(targetId, { status: 'closed', closed_at: evidenceDate } as any)
          setOpenItems(prev => prev.map(o => o.id === targetId ? { ...o, status: 'closed' } : o))
        } else if (p.target_table === 'inbox_items') {
          if (!inboxItems.some(x => x.id === targetId && x.status === 'pending')) {
            await approveInboxItem(item.id, 'rejected')
            setInboxItems(prev => prev.filter(x => x.id !== item.id))
            setError('Vorschlag verworfen: Der Ziel-Inbox-Eintrag existiert nicht mehr.')
            return
          }
          await approveInboxItem(targetId, 'rejected')
          setInboxItems(prev => prev.filter(x => x.id !== targetId))
        } else {
          throw new Error('Unbekannter Zieltyp für Lösungsvorschlag')
        }
      } else if (item.entity_type === 'meeting') {
        const { data: meetingId, error: promoteError } = await supabase.rpc('promote_inbox_meeting', { p_inbox_id: item.id })
        if (promoteError) throw promoteError
        if (!meetingId) throw new Error('Meeting-Promotion hat keine Meeting-ID zurückgegeben')

        const { data: c, error: meetingError } = await supabase
          .from('meetings')
          .select('id,title,meeting_date,topics,participants,ai_summary,key_decisions')
          .eq('id', meetingId)
          .single()
        if (meetingError) throw meetingError

        setMeetings(prev => [{ id: c.id, title: c.title, date: c.meeting_date?.split('T')[0] || '', topics: c.topics || [], participants: c.participants || [], summary: c.ai_summary || '', keyDecisions: c.key_decisions || [], sourceKind: 'promoted' }, ...prev.filter(m => m.id !== c.id)])
        setMeetingLinks(prev => {
          const nextLink: DbMeetingLink = { source: item.source, meeting_id: c.id, title: c.title, meeting_date: c.meeting_date?.split('T')[0] || null, deleted_at: null }
          return prev.some(link => link.source === item.source)
            ? prev.map(link => link.source === item.source ? nextLink : link)
            : [...prev, nextLink]
        })
        setInboxItems(prev => prev
          .filter(x => x.id !== item.id)
          .map(x => x.source === item.source && x.entity_type !== 'meeting'
            ? { ...x, payload: { ...x.payload, meeting_id: c.id, meeting_source: item.source, meeting_title: c.title } }
            : x))
        return
      }
      await approveInboxItem(item.id, 'approved')
      setInboxItems(prev => prev.filter(x => x.id !== item.id))
    } catch (e: any) { setError(e.message || 'Fehler beim Übernehmen') }
  }
  const handleInboxReject = async (id: string) => {
    setInboxItems(prev => prev.filter(x => x.id !== id))
    await deleteInboxItemDb(id).catch(() => {})
  }
  const cycleTodoInbox = (item: DbInboxItem) => {
    const p = item.payload
    const cycles: Record<string, string> = { open: 'in_progress', in_progress: 'done', done: 'open' }
    const newPayload = { ...p, status: cycles[p.status || 'open'] || 'open' }
    setInboxItems(prev => prev.map(x => x.id === item.id ? { ...x, payload: newPayload } : x))
    updateInboxItemPayload(item.id, newPayload).catch(() => {})
  }
  const handleInboxEdit = (item: DbInboxItem) => {
    const p = item.payload
    setInboxEditModeFor(item.id)
    if (item.entity_type === 'todo') {
      setEditTodo({ id: 'inbox_' + item.id, assignee: p.assignee || 'Nicht zugeordnet', title: p.title || '', description: p.description || '', status: p.status || 'open', priority: p.priority || 'medium', dueDate: p.due_date || null, startDate: null, durationDays: 1, dependsOn: [], meetingId: null, projectId: null, createdAt: '' })
    } else if (item.entity_type === 'blocker') {
      setEditBlocker({ id: 'inbox_' + item.id, reportedBy: p.reported_by || 'Nicht zugeordnet', title: p.title || '', description: p.description || '', status: p.status || 'active', meetingId: null, projectId: null, createdAt: '' })
    } else if (item.entity_type === 'open_item') {
      setEditOpen({ id: 'inbox_' + item.id, owner: p.owner || 'Nicht zugeordnet', title: p.title || '', description: p.description || '', category: p.category || 'info', status: p.status || 'open', meetingId: null, projectId: null, createdAt: '' })
    } else if (item.entity_type === 'meeting') {
      const topicDetails = normalizeTopicDetails(p.topics)
      const participants = Array.isArray(p.participants) ? p.participants.map(String) : []
      const keyDecisions = Array.isArray(p.key_decisions) ? p.key_decisions.map(String) : []
      setEditMeeting({ id: 'inbox_' + item.id, title: p.title || '', date: p.meeting_date || '', topics: topicDetails.map(topic => topic.name), topicDetails, participants, participantsDraft: participants.join(', '), summary: p.ai_summary || '', keyDecisions, keyDecisionsDraft: keyDecisions.join(', ') })
    }
  }

  const openMeetingEditor = async (meeting: Meeting) => {
    setError(null)
    try {
      const details = await fetchMeetingTopics(meeting.id)
      setEditMeeting({
        ...meeting,
        topics: details.length > 0 ? details.map(topic => topic.name) : meeting.topics,
        topicDetails: details.length > 0
          ? details.map(topic => ({ name: topic.name, summary: topic.summary || '', sequence: topic.sequence }))
          : meeting.topics.map((name, index) => ({ name, summary: '', sequence: index + 1 })),
        participantsDraft: meeting.participants.join(', '),
        keyDecisionsDraft: meeting.keyDecisions.join(', '),
      })
    } catch (e: any) {
      setError(e.message || 'Meeting konnte nicht zum Bearbeiten geladen werden')
    }
  }

  const deleteTodos = async (ids: string[]) => { setTodos(prev => prev.filter(x => !ids.includes(x.id))); await Promise.all(ids.map(id => deleteTodoDb(id).catch(() => {}))) }
  const deleteBlockers = async (ids: string[]) => { setBlockers(prev => prev.filter(x => !ids.includes(x.id))); await Promise.all(ids.map(id => deleteBlockerDb(id).catch(() => {}))) }
  const deleteOpenItems = async (ids: string[]) => { setOpenItems(prev => prev.filter(x => !ids.includes(x.id))); await Promise.all(ids.map(id => deleteOpenItemDb(id).catch(() => {}))) }
  const deleteMeetings = async (ids: string[]) => { setMeetings(prev => prev.filter(x => !ids.includes(x.id))); setMeetingLinks(prev => prev.map(link => link.meeting_id && ids.includes(link.meeting_id) ? { ...link, deleted_at: new Date().toISOString() } : link)); const results = await Promise.allSettled(ids.map(id => deleteMeetingDb(id))); if (results.some(result => result.status === 'rejected')) await loadData().catch(() => {}) }
  const deleteActivities = async (ids: string[]) => { setActivity(prev => prev.filter(x => !ids.includes(x.id))); await Promise.all(ids.map(id => deleteActivityLogDb(id).catch(() => {}))) }
  const deleteProjects = async (ids: string[]): Promise<string[]> => {
    setProjectMutationError(null)
    const results = await Promise.allSettled(ids.map(id => deleteProjectDb(id)))
    const deletedIds = ids.filter((_, index) => results[index].status === 'fulfilled')
    const failed = results.filter(result => result.status === 'rejected') as PromiseRejectedResult[]
    setProjects(prev => prev.filter(project => !deletedIds.includes(project.id)))
    if (failed.length > 0) {
      const firstReason = mutationErrorMessage(failed[0].reason, 'Unbekannter Datenbankfehler')
      setProjectMutationError(`${failed.length} Projekt(e) konnten nicht gelöscht werden: ${firstReason}`)
      await loadData()
    }
    return ids.filter(id => !deletedIds.includes(id))
  }
  const handleSaveMeeting = async (m: Meeting) => {
    const participants = (m.participantsDraft ?? m.participants.join(', ')).split(',').map(value => value.trim()).filter(Boolean)
    const keyDecisions = (m.keyDecisionsDraft ?? m.keyDecisions.join(', ')).split(',').map(value => value.trim()).filter(Boolean)
    const topicDetails = (m.topicDetails || m.topics.map((name, index) => ({ name, summary: '', sequence: index + 1 })))
      .map((topic, index) => ({ name: topic.name.trim(), summary: topic.summary.trim(), sequence: index + 1 }))
      .filter(topic => topic.name)
    const normalizedMeeting = { ...m, topics: topicDetails.map(topic => topic.name), participants, keyDecisions, topicDetails }
    if (inboxEditModeFor) {
      const payload = { title: normalizedMeeting.title, meeting_date: normalizedMeeting.date, topics: topicDetails, participants, ai_summary: normalizedMeeting.summary, key_decisions: keyDecisions }
      try {
        const current = inboxItems.find(item => item.id === inboxEditModeFor)
        if (!current) throw new Error('Inbox-Eintrag nicht mehr vorhanden')
        const savedPayload = await updateInboxItemPayload(inboxEditModeFor, { ...current.payload, ...payload })
        setInboxItems(prev => prev.map(x => x.id === inboxEditModeFor ? { ...x, payload: savedPayload } : x))
        setEditMeeting(null); setInboxEditModeFor(null)
      } catch (e: any) { setError(e.message || 'Änderungen konnten nicht gespeichert werden') }
      return
    }
    try {
      await updateMeetingWithTopics({ meetingId: m.id, title: normalizedMeeting.title, meetingDate: normalizedMeeting.date, participants, aiSummary: normalizedMeeting.summary, keyDecisions, topics: topicDetails })
      setMeetings(prev => prev.map(x => x.id === m.id ? normalizedMeeting : x))
      setEditMeeting(null)
    } catch (e: any) { setError(e.message || 'Änderungen konnten nicht gespeichert werden') }
  }
  const handleCreateTodo = async (t: Todo) => { setEditTodo(null); try { const c = await insertTodo({ title: t.title, description: t.description || undefined, assignee: t.assignee, priority: t.priority, due_date: t.dueDate || undefined } as any); setTodos(prev => [{ id: c.id, assignee: c.assignee, title: c.title, description: c.description || '', status: c.status, priority: c.priority, dueDate: c.due_date, startDate: t.startDate, durationDays: t.durationDays, dependsOn: [], meetingId: null, projectId: t.projectId, createdAt: new Date().toISOString().split('T')[0] }, ...prev]); if (t.startDate || t.projectId || t.durationDays > 1) { await updateTodoFull(c.id, { start_date: t.startDate, duration_days: t.durationDays, project_id: t.projectId } as any) } } catch { } }
  const handleCreateBlocker = async (b: Blocker) => { setEditBlocker(null); try { const c = await insertBlocker({ title: b.title, description: b.description || undefined, reported_by: b.reportedBy }); setBlockers(prev => [{ id: c.id, reportedBy: c.reported_by, title: c.title, description: c.description || '', status: c.status, meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev]) } catch { } }
  const handleCreateOpen = async (o: OpenItem) => { setEditOpen(null); try { const c = await insertOpenItem({ title: o.title, description: o.description || undefined, owner: o.owner, category: o.category }); setOpenItems(prev => [{ id: c.id, owner: c.owner, title: c.title, description: c.description || '', category: c.category, status: c.status, meetingId: null, projectId: null, createdAt: new Date().toISOString().split('T')[0] }, ...prev]) } catch { } }
  const saveProjectRelations = async (projectId: string) => {
    await setProjectMeetings(projectId, Array.from(projLinkedMeetingIds))
    // Create new todos from queue
    for (const td of projTodoQueue) {
      const c = await insertTodo({ title: td.title, description: td.description || undefined, assignee: td.assignee, priority: td.priority, due_date: td.dueDate || undefined } as any)
      await updateTodoFull(c.id, { project_id: projectId, start_date: td.startDate, duration_days: td.durationDays } as any)
    }
    // Remove links that were deselected in the project dialog.
    for (const todo of todos.filter(todo => todo.projectId === projectId && !projLinkedTodoIds.has(todo.id))) {
      await updateTodoFull(todo.id, { project_id: null } as any)
    }
    // Link selected existing todos (if not already linked).
    for (const todoId of projLinkedTodoIds) {
      const todo = todos.find(t => t.id === todoId)
      if (todo && todo.projectId !== projectId) {
        await updateTodoFull(todoId, { project_id: projectId } as any)
      }
    }
  }
  const handleSaveProject = async (p: DbProject) => {
    setProjectMutationError(null)
    if (p.id === '__new__') {
      try {
        const c = await insertProject({ name: p.name, description: p.description || undefined, start_date: p.start_date || undefined, end_date: p.end_date || undefined, owner: p.owner || undefined, priority: p.priority || 'medium' })
        await saveProjectRelations(c.id)
        await loadData()
        setEditProject(null)
        setProjTodoQueue([]); setProjLinkedTodoIds(new Set()); setProjLinkedMeetingIds(new Set())
      } catch (error) {
        setProjectMutationError(mutationErrorMessage(error, 'Projekt konnte nicht erstellt werden.'))
        await loadData()
      }
    } else {
      try {
        await updateProjectFull(p.id, { name: p.name, description: p.description, status: p.status, start_date: p.start_date, end_date: p.end_date, owner: p.owner, priority: p.priority })
        await saveProjectRelations(p.id)
        await loadData()
        setEditProject(null)
        setProjTodoQueue([]); setProjLinkedTodoIds(new Set()); setProjLinkedMeetingIds(new Set())
      } catch (error) {
        setProjectMutationError(mutationErrorMessage(error, 'Projekt konnte nicht gespeichert werden.'))
        await loadData()
      }
    }
  }
  const handleOpenProjectDialog = (p: DbProject | '__new__') => {
    setProjectMutationError(null)
    if (p === '__new__') {
      setEditProject({ id: '__new__', name: '', description: null, status: 'active', start_date: null, end_date: null, owner: null, priority: 'medium', created_at: '', updated_at: '' } as DbProject)
      setProjLinkedTodoIds(new Set()); setProjLinkedMeetingIds(new Set())
    } else {
      setEditProject({...p})
      setProjLinkedTodoIds(new Set(todos.filter(t => t.projectId === p.id).map(t => t.id)))
      fetchProjectMeetings(p.id).then(ids => setProjLinkedMeetingIds(new Set(ids))).catch(error => {
        setProjectMutationError(mutationErrorMessage(error, 'Meeting-Verknüpfungen konnten nicht geladen werden.'))
      })
    }
    setProjTodoQueue([]); setProjTodoNewForm(null); setProjTodoSearch(''); setProjTodoPickerOpen(false); setProjMeetingSearch(''); setProjMeetingPickerOpen(false); setProjectInitTodos('')
  }
  const handleDeleteProject = async (p: DbProject) => {
    setProjectMutationError(null)
    try {
      await deleteProjectDb(p.id)
      setProjects(prev => prev.filter(x => x.id !== p.id))
      if (viewProject?.id === p.id) setViewProject(null)
    } catch (error) {
      setProjectMutationError(mutationErrorMessage(error, 'Projekt konnte nicht gelöscht werden.'))
      await loadData()
    }
  }

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
    const assistantTimestamp = Date.now() + 1
    setChatMessages([...updatedMessages, { role: 'assistant', text: '', sources: [], timestamp: assistantTimestamp }])
    setChatLoading(true)
    // Nur die 10 vorherigen Messages senden; die aktuelle Frage steckt separat in `question`.
    const historyWindow = chatMessages.slice(-10)
    const history = historyWindow.map((m, i, arr) => ({
      role: m.role,
      text: i >= arr.length - 3 ? m.text.slice(0, 2000) : m.text.slice(0, 200),
    }))
    const updateAssistant = (patch: Partial<ChatMessage> | ((message: ChatMessage) => Partial<ChatMessage>)) => {
      setChatMessages(prev => prev.map(msg => {
        if (msg.timestamp !== assistantTimestamp) return msg
        const nextPatch = typeof patch === 'function' ? patch(msg) : patch
        return { ...msg, ...nextPatch }
      }))
    }
    try {
      await askMemoryStream(q, history, {
        onMetadata: metadata => updateAssistant({
          mode: metadata.retrieval.mode,
          scalingNotice: metadata.scaling_notice?.trim() || undefined,
          model: metadata.model,
          tokens: {
            input: Number(metadata.cache?.uncached_input_tokens ?? metadata.usage?.input_tokens ?? 0),
            output: Number(metadata.usage?.output_tokens ?? 0),
          },
        }),
        onDelta: delta => updateAssistant(msg => ({ text: `${msg.text}${delta}` })),
        onSources: sources => updateAssistant({ sources: sources.meetings, chunkSources: sources.chunks, itemSources: sources.items }),
        onDone: done => {
          // done-Event enthält die vollständige usage (inkl. Output-Token).
          // inputTokens = NUR uncached (cacheWrite/cacheRead werden separat berechnet).
          const outputTokens = Number(done.usage?.output_tokens ?? 0)
          const inputTokens = Number(done.cache?.uncached_input_tokens ?? done.usage?.input_tokens ?? 0)
          const cacheWrite = Number(done.cache?.cache_creation_input_tokens ?? 0)
          const cacheRead = Number(done.cache?.cache_read_input_tokens ?? 0)
          updateAssistant(msg => ({
            tokens: { input: inputTokens + cacheWrite + cacheRead, output: outputTokens || msg.tokens?.output || 0 },
            // Backend-berechnete Kosten bevorzugen; lokale Preisliste nur als Fallback.
            costUsd: typeof done.cost_usd === 'number' ? done.cost_usd : computeChatCost(msg.model, inputTokens, outputTokens, cacheWrite, cacheRead),
          }))
          // Metriken neu laden, damit der Monats-Tracker aktuell ist.
          refreshMemoryMetrics()
        },
      })
    } catch (streamError: unknown) {
      try {
        const result = await askMemory(q, history)
        const usage = result.usage ?? {}
        const inputTokens = Number(result.cache?.uncached_input_tokens ?? usage.input_tokens ?? 0)
        const cacheWrite = Number(result.cache?.cache_creation_input_tokens ?? 0)
        const cacheRead = Number(result.cache?.cache_read_input_tokens ?? 0)
        const outputTokens = Number(usage.output_tokens ?? 0)
        updateAssistant({
          text: result.answer,
          sources: result.sources.meetings,
          chunkSources: result.sources.chunks,
          itemSources: result.sources.items,
          mode: result.retrieval.mode,
          scalingNotice: result.scaling_notice?.trim() || undefined,
          model: result.model,
          tokens: { input: inputTokens + cacheWrite + cacheRead, output: outputTokens },
          costUsd: typeof result.cost_usd === 'number' ? result.cost_usd : computeChatCost(result.model, inputTokens, outputTokens, cacheWrite, cacheRead),
        })
        refreshMemoryMetrics()
      } catch (fallbackError: unknown) {
        const message = fallbackError instanceof Error
          ? fallbackError.message
          : streamError instanceof Error
            ? streamError.message
            : String(fallbackError || streamError)
        updateAssistant({ text: `Fehler: ${message}` })
      }
    } finally {
      setChatLoading(false)
    }
  }

  const handleRawTranscript = async () => {
    if (!viewMeeting || rawTranscriptLoading) return
    setRawTranscriptOpen(true)
    if (rawTranscriptLoaded) return
    setRawTranscriptLoading(true)
    setRawTranscriptError(null)
    try {
      if (viewMeeting.sourceKind === 'pending') {
        setRawTranscript(viewMeeting.pendingRawTranscript?.trim() || null)
      } else {
        setRawTranscript(await fetchMeetingRawTranscript(viewMeeting.id))
      }
      setRawTranscriptLoaded(true)
    } catch (error: unknown) {
      setRawTranscriptError(error instanceof Error ? error.message : 'Rohtranskript konnte nicht geladen werden.')
    } finally { setRawTranscriptLoading(false) }
  }

  useEffect(() => {
    setRawTranscript(null)
    setRawTranscriptLoaded(false)
    setRawTranscriptOpen(false)
    setRawTranscriptLoading(false)
    setRawTranscriptError(null)
  }, [viewMeeting?.id])

  useEffect(() => {
    let cancelled = false
    setMeetingTopicDetails([])
    setMeetingTopicsError(null)
    if (!viewMeeting) return () => { cancelled = true }
    if (viewMeeting.sourceKind === 'pending') {
      setMeetingTopicDetails(viewMeeting.topicDetails || [])
      setMeetingTopicsLoading(false)
      return () => { cancelled = true }
    }
    setMeetingTopicsLoading(true)
    fetchMeetingTopics(viewMeeting.id)
      .then((topics: DbMeetingTopic[]) => {
        if (!cancelled) setMeetingTopicDetails(topics.map(topic => ({ name: topic.name, summary: topic.summary || '', sequence: topic.sequence })))
      })
      .catch((error: unknown) => {
        if (!cancelled) setMeetingTopicsError(error instanceof Error ? error.message : 'Teil-Summaries konnten nicht geladen werden.')
      })
      .finally(() => { if (!cancelled) setMeetingTopicsLoading(false) })
    return () => { cancelled = true }
  }, [viewMeeting?.id, viewMeeting?.sourceKind])

  const getMeeting = (id: string | null) => meetings.find(m => m.id === id)
  const meetingLinkMap = useMemo(() => new Map(meetingLinks.map(link => [link.source, link])), [meetingLinks])
  const resolveMeetingReference = (source?: string | null, meetingId?: string | null) => {
    const link = source ? meetingLinkMap.get(source) : undefined
    const liveMeeting = getMeeting(meetingId || link?.meeting_id || null)
    if (liveMeeting) return { meeting: liveMeeting, deleted: false }
    if (link && (link.deleted_at || link.meeting_id)) return { meeting: { id: link.meeting_id || `deleted_${link.source}`, title: link.title }, deleted: true }
    return null
  }
  const openMeetingReference = (reference: { meeting: { id: string; title: string }; deleted: boolean } | null) => {
    if (!reference) return
    if (reference.deleted) { setError('Meeting gelöscht'); return }
    const meeting = getMeeting(reference.meeting.id)
    if (meeting) setViewMeeting(meeting)
  }
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
  const editSourceEntity = (entityType: string, entityId: string) => {
    switch (entityType) {
      case 'todo': { const t = todos.find(x => x.id === entityId); if (t) setEditTodo({...t}); break }
      case 'blocker': { const b = blockers.find(x => x.id === entityId); if (b) setEditBlocker({...b}); break }
      case 'open_item': { const o = openItems.find(x => x.id === entityId); if (o) setEditOpen({...o}); break }
      case 'meeting': { const m = meetings.find(x => x.id === entityId); if (m) openMeetingEditor(m); break }
      case 'project': { const p = projects.find(x => x.id === entityId); if (p) handleOpenProjectDialog(p); break }
    }
  }

  // Filtered data — identical logic

  const searchResults = useMemo(() => {
    const q = globalSearch.trim().toLowerCase()
    if (!q) return { meetings: [] as Meeting[] }
    const matchMeetings = meetings
      .filter(m => !q || textMatch(m, q))
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, 10)
    return { meetings: matchMeetings }
  }, [globalSearch, meetings])


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


  // Gantt helpers: addDays/todoEndDate kommen aus lib/shared

  const projectTodos = (pid: string) => todos.filter(t => t.projectId === pid)
  const projectBlockers = (pid: string) => blockers.filter(b => b.projectId === pid)

  if (loading) return <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--syn-bg)' }}><div className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Lade Daten...</div></div>
  if (error && todos.length === 0) return <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--syn-bg)' }}><div className="text-sm" style={{ color: 'var(--syn-danger)' }}>Fehler: {error}</div></div>

  const navSections: { label: string; items: { key: Page; label: string; icon: string; count?: number }[] }[] = [
    { label: 'ÜBERBLICK', items: [
      { key: 'uebersicht', label: 'Command Center', icon: '⬡' },
      { key: 'inbox', label: 'Inbox', icon: '⬇' },
      { key: 'sitzungen', label: 'Meetings', icon: '☰' },
      { key: 'aktionen', label: 'Aktionen', icon: '✓' },
    ]},
    { label: 'PLANUNG', items: [
      { key: 'projekte', label: 'Projekte', icon: '◈' },
    ]},
    { label: 'SUCHE', items: [
      { key: 'ki', label: 'AI-Suche', icon: '◉' },
      { key: 'textsuche', label: 'Textsuche', icon: '⌕' },
      { key: 'protokoll', label: 'Aktivität', icon: '⏱' },
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
            <Input placeholder="Meetings durchsuchen..." value={globalSearch} onChange={e => { setGlobalSearch(e.target.value); setSearchFocused(true) }} onFocus={() => setSearchFocused(true)} onKeyDown={e => { if (e.key === 'Enter' && globalSearch.trim()) { setSearchFocused(false); setPage('textsuche') } if (e.key === 'Escape') setSearchFocused(false) }} className="h-8 text-sm w-72 bg-[var(--syn-surface-2)] border-[var(--syn-line)] pr-8" />
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
                <button onClick={() => { setSearchFocused(false); setPage('textsuche') }} className="w-full px-3 py-2 text-xs text-center hover:bg-[var(--syn-hover)] transition-colors border-t border-[var(--syn-line)]" style={{ color: 'var(--syn-accent)' }}>
                  Alle Ergebnisse anzeigen →
                </button>
              </div>
            )}
          </div>
          <div className="flex-1" />
          {error && <span className="text-xs text-[var(--syn-danger)]">{error}</span>}
          <Button size="sm" variant="outline" onClick={handleToggleNightly} className={`text-xs border-[var(--syn-line)] ${nightlyActive ? 'text-[var(--syn-text-muted)]' : 'text-[var(--syn-text-faint)]'}`}>{nightlyActive ? '☾ An' : '☾ Aus'}</Button>
          <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--syn-hover)] transition-colors text-sm" title="Theme wechseln">{theme === 'dark' ? '☀' : '☾'}</button>
        </header>

        <main data-testid="main-content" className="flex-1 px-6 pt-6 pb-6 overflow-auto">

          {/* ═══ COMMAND CENTER / ÜBERSICHT ═══ */}
          {page === 'uebersicht' && <CommandCenterPage meetings={meetings} todos={todos} blockers={blockers} chatInput={chatInput} setChatInput={setChatInput} handleChat={handleChat} setPage={setPage} setActionTab={setActionTab} setEditTodo={setEditTodo} setViewTodo={setViewTodo} setViewMeeting={setViewMeeting} setViewBlocker={setViewBlocker} handleQuickStatusToggle={handleQuickStatusToggle} />}

          {/* ═══ INBOX ═══ */}
          {page === 'inbox' && <InboxPage inboxItems={inboxItems} todos={todos} blockers={blockers} openItems={openItems} tableCounts={tableCounts} projects={projects} memberNames={memberNames} globalSearch={globalSearch} today={today} handleInboxApprove={handleInboxApprove} handleInboxReject={handleInboxReject} handleInboxEdit={handleInboxEdit} cycleTodoInbox={cycleTodoInbox} setViewMeeting={setViewMeeting} setViewTodo={setViewTodo} setViewBlocker={setViewBlocker} setViewOpen={setViewOpen} resolveMeetingReference={resolveMeetingReference} openMeetingReference={openMeetingReference} openSourceEntity={openSourceEntity} getProjectName={getProjectName} />}

          {/* ═══ SITZUNGEN ═══ */}
          {page === 'sitzungen' && <MeetingsPage meetings={meetings} tableCounts={tableCounts} memberNames={memberNames} globalSearch={globalSearch} openMeetingEditor={openMeetingEditor} handleDeleteMeeting={handleDeleteMeeting} deleteMeetings={deleteMeetings} setViewMeeting={setViewMeeting} setConfirmDelete={setConfirmDelete} />}

          {/* ═══ AKTIONEN (Tabs: Todos / Blocker / Open Items) ═══ */}
          {page === 'aktionen' && <ActionsPage todos={todos} blockers={blockers} openItems={openItems} tableCounts={tableCounts} memberNames={memberNames} projects={projects} actionTab={actionTab} setActionTab={setActionTab} globalSearch={globalSearch} today={today} cycleTodo={cycleTodo} handleDeleteTodo={handleDeleteTodo} handleDeleteBlocker={handleDeleteBlocker} handleDeleteOpen={handleDeleteOpen} deleteTodos={deleteTodos} deleteBlockers={deleteBlockers} deleteOpenItems={deleteOpenItems} setViewTodo={setViewTodo} setEditTodo={setEditTodo} setViewBlocker={setViewBlocker} setEditBlocker={setEditBlocker} setViewOpen={setViewOpen} setEditOpen={setEditOpen} resolveMeetingReference={resolveMeetingReference} openMeetingReference={openMeetingReference} getProjectName={getProjectName} setConfirmDelete={setConfirmDelete} />}

          {/* ═══ PROJEKTE ═══ */}
          {page === 'projekte' && <ProjectsPage projects={projects} projectIds={projectIds} todos={todos} setTodos={setTodos} blockers={blockers} memberNames={memberNames} today={today} globalSearch={globalSearch} projectView={projectView} setProjectView={setProjectView} projectMutationError={projectMutationError} handleOpenProjectDialog={handleOpenProjectDialog} handleDeleteProject={handleDeleteProject} deleteProjects={deleteProjects} getProjectName={getProjectName} setViewProject={setViewProject} setViewTodo={setViewTodo} setEditTodo={setEditTodo} handleDeleteTodo={handleDeleteTodo} setConfirmDelete={setConfirmDelete} />}

          {/* ═══ PROTOKOLL ═══ */}
          {page === 'protokoll' && <ActivityPage activity={activity} globalSearch={globalSearch} handleDeleteActivity={handleDeleteActivity} deleteActivities={deleteActivities} openSourceEntity={openSourceEntity} editSourceEntity={editSourceEntity} setConfirmDelete={setConfirmDelete} />}

          {/* ═══ TEXTSUCHE ═══ */}
          {page === 'textsuche' && <TextSearchPage globalSearch={globalSearch} meetings={meetings} todos={todos} blockers={blockers} openItems={openItems} setViewMeeting={setViewMeeting} setViewTodo={setViewTodo} setViewBlocker={setViewBlocker} setViewOpen={setViewOpen} />}

          {/* ═══ KI-ASSISTENT ═══ */}
          {page === 'ki' && <KiPage chatMessages={chatMessages} chatInput={chatInput} setChatInput={setChatInput} chatLoading={chatLoading} sendChat={handleChat} memoryMetrics={memoryMetrics} getMeeting={getMeeting} openSourceEntity={openSourceEntity} setViewMeeting={setViewMeeting} />}
        </main>
      </div>

      {/* ═══ DIALOGS ═══ */}
      {/* View Meeting */}
      <Dialog open={!!viewMeeting} onOpenChange={() => setViewMeeting(null)}>
        <DialogContent className="max-w-4xl max-h-[85vh]">{viewMeeting && <ScrollArea className="max-h-[75vh] pr-4">
          <DialogHeader className="pb-3"><DialogTitle>{viewMeeting.title}</DialogTitle><div className="flex items-center gap-3 text-xs mt-1" style={{ color: 'var(--syn-text-muted)' }}><span>{viewMeeting.date}</span><span>{'·'}</span><span>{viewMeeting.participants.length} Teilnehmer</span></div></DialogHeader>
          <div className="space-y-4 pt-2">
            <div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Teilnehmer</h3><div className="flex flex-wrap gap-2">{viewMeeting.participants.map((p, i) => <span key={i} className="text-sm px-2.5 py-1 rounded" style={{ background: 'var(--syn-surface-3)' }}>{p}</span>)}</div></div>
            <Separator className="bg-[var(--syn-line)]" />
            <div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Zusammenfassung</h3>{stripEmbeddedTopicsFromSummary(viewMeeting.summary) ? <div className="text-sm leading-relaxed prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: sanitizeHtml(stripEmbeddedTopicsFromSummary(viewMeeting.summary)) }} /> : <p className="text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Zusammenfassung.</p>}</div>
            <Separator className="bg-[var(--syn-line)]" />
            <div data-testid="meeting-topic-details">
              <div className="mb-3 text-sm" style={{ color: 'var(--syn-text-faint)' }}>--- Themen ---</div>
              {meetingTopicsLoading ? <p className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Themen werden geladen…</p> : meetingTopicsError ? <p className="text-sm text-[var(--syn-danger)]">{meetingTopicsError}</p> : meetingTopicDetails.length > 0 ? <div className="space-y-4">{meetingTopicDetails.map(topic => <div data-testid="meeting-topic-summary" key={`${topic.sequence}-${topic.name}`} className="text-sm leading-relaxed"><strong>{topic.name}</strong>{topic.summary ? <><br /><span style={{ color: 'var(--syn-text-muted)' }}>{topic.summary}</span></> : <><br /><span style={{ color: 'var(--syn-text-faint)' }}>Keine Teil-Summary hinterlegt.</span></>}</div>)}</div> : <p className="text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Themen-Summaries hinterlegt.</p>}
            </div>
            <Separator className="bg-[var(--syn-line)]" />
            <div>
              <div className="flex items-center justify-between gap-3"><div><h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--syn-text-faint)' }}>Rohtranskript</h3><p className="mt-1 text-xs" style={{ color: 'var(--syn-text-faint)' }}>Wird erst beim Öffnen vollständig geladen.</p></div><Button data-testid="open-full-transcript" variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={handleRawTranscript}>Vollständig öffnen</Button></div>
            </div>
            {viewMeeting.keyDecisions.length > 0 && <><Separator className="bg-[var(--syn-line)]" /><div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Entscheidungen</h3><div className="space-y-1.5">{viewMeeting.keyDecisions.map((d, i) => <div key={i} className="flex items-start gap-2 text-sm"><span style={{ color: 'var(--syn-ok)' }} className="mt-0.5">{'✓'}</span>{d}</div>)}</div></div></>}
            {(() => { const rel = todos.filter(t => t.meetingId === viewMeeting.id); if (!rel.length) return null; return <><Separator className="bg-[var(--syn-line)]" /><div><h3 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--syn-text-faint)' }}>Todos</h3><ul className="space-y-1 list-disc list-inside">{rel.map(t => <li key={t.id} className="text-sm"><button onClick={() => { setViewMeeting(null); setViewTodo(t) }} className="hover:text-[var(--syn-accent)]">{t.title}</button><span className="text-xs ml-2" style={{ color: 'var(--syn-text-faint)' }}>({t.assignee})</span></li>)}</ul></div></> })()}
            <Separator className="bg-[var(--syn-line)]" />
            <div className="flex gap-2"><Button variant="outline" size="sm" className="text-xs border-[var(--syn-line)]" onClick={() => { const m = viewMeeting; setViewMeeting(null); if (m.sourceKind === 'pending') { const inboxItem = inboxItems.find(item => `inbox_${item.id}` === m.id); if (inboxItem) handleInboxEdit(inboxItem); else setError('Inbox-Eintrag nicht mehr vorhanden') } else openMeetingEditor(m) }}>{'✎'} Bearbeiten</Button><Button variant="outline" size="sm" className="text-xs text-[var(--syn-danger)] border-[var(--syn-line)]" onClick={() => setConfirmDelete({ label: viewMeeting.title, action: () => { handleDeleteMeeting(viewMeeting); setViewMeeting(null) } })}>{'✕'} Löschen</Button></div>
          </div>
        </ScrollArea>}</DialogContent>
      </Dialog>

      {/* Full raw transcript viewer */}
      <Dialog open={rawTranscriptOpen} onOpenChange={setRawTranscriptOpen}>
        <DialogContent className="max-w-5xl h-[88vh] flex flex-col overflow-hidden">
          <DialogHeader className="shrink-0"><DialogTitle>Rohtranskript{viewMeeting?.title ? ` · ${viewMeeting.title}` : ''}</DialogTitle></DialogHeader>
          <div data-testid="raw-transcript-full-view" className="flex-1 min-h-0 overflow-y-auto rounded-lg border border-[var(--syn-line)] p-4" style={{ background: 'var(--syn-surface-2)' }}>
            {rawTranscriptLoading ? <p className="text-sm" style={{ color: 'var(--syn-text-muted)' }}>Rohtranskript wird geladen…</p> : rawTranscriptError ? <p className="text-sm text-[var(--syn-danger)]">{rawTranscriptError}</p> : rawTranscript ? <pre data-testid="raw-transcript-content" className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed">{rawTranscript}</pre> : <p className="text-sm" style={{ color: 'var(--syn-text-faint)' }}>Kein Rohtranskript hinterlegt.</p>}
          </div>
        </DialogContent>
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
      <Dialog open={!!editOpen} onOpenChange={() => setEditOpen(null)}><DialogContent className="max-w-4xl"><DialogHeader><DialogTitle>{editOpen?.id === '__new__' ? 'Neuer offener Punkt' : 'Offenen Punkt bearbeiten'}</DialogTitle></DialogHeader>{editOpen && <div className="space-y-3 pt-2"><Input placeholder="Titel" value={editOpen.title} onChange={e => setEditOpen({...editOpen, title: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><Textarea placeholder="Beschreibung" value={editOpen.description} onChange={e => setEditOpen({...editOpen, description: e.target.value})} className="bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /><div className="grid grid-cols-2 gap-3"><Select value={editOpen.owner} onValueChange={v => setEditOpen({...editOpen, owner: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select><Select value={editOpen.category} onValueChange={v => setEditOpen({...editOpen, category: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="decision">Entscheidung</SelectItem><SelectItem value="question">Frage</SelectItem><SelectItem value="risk">Risiko</SelectItem><SelectItem value="info">Information</SelectItem><SelectItem value="general">Allgemein (alt)</SelectItem><SelectItem value="opportunity">Chance (alt)</SelectItem><SelectItem value="follow_up">Nachverfolgung (alt)</SelectItem></SelectContent></Select></div><Select value={editOpen.status} onValueChange={v => setEditOpen({...editOpen, status: v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="open">Offen</SelectItem><SelectItem value="watching">Beobachten</SelectItem><SelectItem value="closed">Geschlossen</SelectItem></SelectContent></Select><Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" disabled={!editOpen.title.trim()} onClick={() => editOpen.id === '__new__' ? handleCreateOpen(editOpen) : handleSaveOpen(editOpen)}>{editOpen.id === '__new__' ? 'Erstellen' : 'Speichern'}</Button></div>}</DialogContent></Dialog>

      {/* Edit Meeting */}
      <Dialog open={!!editMeeting} onOpenChange={() => setEditMeeting(null)}><DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto"><DialogHeader><DialogTitle>Meeting bearbeiten</DialogTitle></DialogHeader>{editMeeting && <div className="space-y-4 pt-2">
        <Input value={editMeeting.title} onChange={e => setEditMeeting({...editMeeting, title: e.target.value})} placeholder="Titel" className="h-11 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
        <Input type="date" value={editMeeting.date} onChange={e => setEditMeeting({...editMeeting, date: e.target.value})} className="h-11 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" />
        <div className="space-y-1.5">
          <div className="text-xs font-medium" style={{color:'var(--syn-text-muted)'}}>Themen</div>
          {(editMeeting.topicDetails || editMeeting.topics.map((name, index) => ({ name, summary: '', sequence: index + 1 }))).map((topic, i) => (
            <div key={i} className="flex gap-1 items-start">
              <div className="flex-1 space-y-1.5 rounded-lg border border-[var(--syn-line)] p-2">
                <Input value={topic.name} onChange={e => { const details = [...(editMeeting.topicDetails || editMeeting.topics.map((name, index) => ({ name, summary: '', sequence: index + 1 })))]; details[i] = { ...details[i], name: e.target.value }; setEditMeeting({...editMeeting, topics: details.map(item => item.name), topicDetails: details}) }} className="h-10 bg-[var(--syn-surface-2)] border-[var(--syn-line)] text-sm" placeholder={`Thema ${i+1}`} />
                <Textarea value={topic.summary} onChange={e => { const details = [...(editMeeting.topicDetails || [])]; details[i] = { ...details[i], summary: e.target.value }; setEditMeeting({...editMeeting, topicDetails: details}) }} className="min-h-[96px] resize-y bg-[var(--syn-surface-2)] border-[var(--syn-line)] text-sm leading-relaxed" placeholder="Teil-Summary" />
              </div>
              <button onClick={() => { const details = (editMeeting.topicDetails || editMeeting.topics.map((name, index) => ({ name, summary: '', sequence: index + 1 }))).filter((_, j) => j !== i).map((item, index) => ({ ...item, sequence: index + 1 })); setEditMeeting({...editMeeting, topics: details.map(item => item.name), topicDetails: details}) }} className="w-10 h-10 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors text-sm shrink-0" style={{color:'var(--syn-text-faint)'}}>✕</button>
            </div>
          ))}
          <button onClick={() => { const details = [...(editMeeting.topicDetails || editMeeting.topics.map((name, index) => ({ name, summary: '', sequence: index + 1 }))), { name: '', summary: '', sequence: editMeeting.topics.length + 1 }]; setEditMeeting({...editMeeting, topics: details.map(item => item.name), topicDetails: details}) }} className="text-xs px-2 py-1 rounded border border-dashed border-[var(--syn-line)] hover:border-[var(--syn-accent)] hover:text-[var(--syn-accent)] transition-colors w-full" style={{color:'var(--syn-text-faint)'}}>+ Thema hinzufügen</button>
        </div>
        <div className="space-y-1.5"><label className="text-xs font-medium" style={{color:'var(--syn-text-muted)'}}>Teilnehmer</label><Textarea value={editMeeting.participantsDraft ?? editMeeting.participants.join(', ')} onChange={e => setEditMeeting({...editMeeting, participantsDraft: e.target.value})} placeholder="Teilnehmer (kommagetrennt)" rows={3} className="min-h-[88px] resize-y bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /></div>
        <div className="space-y-1.5"><label className="text-xs font-medium" style={{color:'var(--syn-text-muted)'}}>Zusammenfassung</label><Textarea value={editMeeting.summary} onChange={e => setEditMeeting({...editMeeting, summary: e.target.value})} placeholder="Zusammenfassung" rows={10} className="min-h-[260px] resize-y bg-[var(--syn-surface-2)] border-[var(--syn-line)] leading-relaxed" /></div>
        <div className="space-y-1.5"><label className="text-xs font-medium" style={{color:'var(--syn-text-muted)'}}>Entscheidungen</label><Textarea value={editMeeting.keyDecisionsDraft ?? editMeeting.keyDecisions.join(', ')} onChange={e => setEditMeeting({...editMeeting, keyDecisionsDraft: e.target.value})} placeholder="Entscheidungen (kommagetrennt)" rows={5} className="min-h-[140px] resize-y bg-[var(--syn-surface-2)] border-[var(--syn-line)]" /></div>
        <Button className="w-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white" onClick={() => handleSaveMeeting(editMeeting)}>Speichern</Button>
      </div>}</DialogContent></Dialog>

      {/* Edit Project */}
      <Dialog open={!!editProject} onOpenChange={() => { setEditProject(null); setProjTodoQueue([]); setProjTodoNewForm(null); setProjLinkedTodoIds(new Set()); setProjLinkedMeetingIds(new Set()); setProjTodoPickerOpen(false); setProjMeetingPickerOpen(false); setProjectInitTodos('') }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editProject?.id === '__new__' ? 'Neues Projekt' : 'Projekt bearbeiten'}</DialogTitle></DialogHeader>
          {editProject && <div className="space-y-4 pt-2">
            {projectMutationError && (
              <div role="alert" className="rounded-lg border border-[var(--syn-danger)]/30 bg-[var(--syn-danger-soft)] px-3 py-2 text-xs text-[var(--syn-danger)]">
                {projectMutationError}
              </div>
            )}
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
                  <SelectContent><SelectItem value="active">Aktiv</SelectItem><SelectItem value="completed">Abgeschlossen</SelectItem><SelectItem value="paused">Pausiert</SelectItem></SelectContent>
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
                          <span className="truncate text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>{m.topics.slice(0, 3).map(shortTopic).join(', ')}{m.topics.length > 3 ? ` +${m.topics.length - 3}` : ''}</span>
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

    </div>
  )
}
