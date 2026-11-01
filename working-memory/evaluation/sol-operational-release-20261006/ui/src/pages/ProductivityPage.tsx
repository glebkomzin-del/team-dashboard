import { useReviewSnapshot } from '@/features/working-memory/useReviewSnapshot'
import { EvidenceConfidence } from '@/features/working-memory/EvidenceConfidence'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, CircleCheck, Clock3, Filter, List, Pencil, Plus, RotateCcw, Search, SlidersHorizontal, X } from 'lucide-react'
import * as Popover from '@radix-ui/react-popover'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { postMemory, MemoryWriteError, dateLabel, numberLabel, kindNames, actionNames, decisionNames } from '@/features/working-memory/types'
import type { Knowledge, Work } from '@/features/working-memory/types'
import { DecisionDialog } from '@/features/working-memory/DecisionDialog'
import type { DecisionTarget } from '@/features/working-memory/DecisionDialog'
import { ProcessingPanel } from '@/features/working-memory/ProcessingPanel'
import { PlannerEditor } from '@/features/working-memory/PlannerEditor'
import { addDays, allWork, completedOn, dueDate, localDay, memberFor, monday, navigate, rememberScroll, rememberedScroll, isoDate, pageNames, personal, priorityNames, statusNames, useRoute } from '@/features/working-memory/planning'
import type { Page, PlannedWork } from '@/features/working-memory/planning'
import { SourceDialog } from './WorkingMemoryPage'
import { WorkspaceOverview } from '@/features/working-memory/WorkspaceOverview'
import { usePreferences } from '@/features/working-memory/preferences'
import '@/features/working-memory/productivity.css'

interface Filters { query: string; owners: string[]; matters: string[]; statuses: string[]; kinds: string[]; due: string; sort: string; teamScope: string; from: string; to: string }
const initialFilters = (): Filters => ({ query: '', owners: [], matters: [], statuses: ['open', 'waiting'], kinds: [], due: '', sort: 'priority_desc', teamScope: 'active', from: '', to: '' })

function MultiFilter({ label, values, options, change }: { label: string; values: string[]; options: { value: string; label: string }[]; change: (values: string[]) => void }) {
  const [query, setQuery] = useState('')
  const matches = options.filter(o => o.label.toLocaleLowerCase('de').includes(query.toLocaleLowerCase('de')))
  return <Popover.Root><Popover.Trigger asChild><button type="button" className={`px-button px-filter ${values.length ? 'is-selected' : ''}`}>{label}{values.length > 0 && <span className="px-count">{values.length}</span>}<ChevronDown size={13} aria-hidden="true" /></button></Popover.Trigger><Popover.Portal><Popover.Content className="px-popover" sideOffset={7} align="start" collisionPadding={12}>
    <div className="px-popover-head"><strong>{label}</strong><button type="button" className="px-text-button" onClick={() => change([])}>Alle anzeigen</button></div><label className="px-search"><Search size={14} aria-hidden="true" /><input aria-label={`${label} durchsuchen`} name="filter_option_search" autoComplete="off" value={query} onChange={e => setQuery(e.target.value)} placeholder="Auswahl durchsuchen…" /></label><div className="px-options">{matches.map(option => <label key={option.value}><input type="checkbox" name="filter_value" autoComplete="off" checked={values.includes(option.value)} onChange={() => change(values.includes(option.value) ? values.filter(v => v !== option.value) : [...values, option.value])} /><span>{option.label}</span></label>)}{!matches.length && <p>Keine passende Auswahl.</p>}</div><Popover.Close className="px-button px-popover-close">Fertig</Popover.Close></Popover.Content></Popover.Portal></Popover.Root>
}

function TaskRow({ task, open, edit, teamName, toggle, busy }: { task: PlannedWork; open: () => void; edit?: () => void; teamName?: string; toggle?: () => void; busy: boolean }) {
  const due = dueDate(task)
  const overdue = due && due < localDay() && ['open', 'waiting'].includes(task.status)
  return <div className="px-task-row"><button type="button" className="px-toggle" disabled={!toggle || busy} aria-label={`${task.status === 'done' ? 'Wieder öffnen' : 'Als erledigt markieren'}: ${task.title}`} onClick={toggle}>
    <span className={`px-state-icon ${task.status === 'done' ? 'is-done' : ''}`} aria-hidden="true">{task.status === 'done' ? <CircleCheck size={17} /> : task.status === 'waiting' ? <Clock3 size={17} /> : <span />}</span>
    </button><button type="button" className="px-task" onClick={open}><span className="px-task-main"><span className="px-task-title">{task.title}</span><span className="px-task-meta">{task.origin === 'manual' ? 'Manuelles Todo' : task.matter || 'Aus Meeting'}{task.priority === 'high' && <span className="px-priority">Hohe Priorität</span>}</span></span>
    {teamName && <span className="px-task-owner">{teamName}</span>}<span className={`px-status status-${task.status}`}>{statusNames[task.status]}</span><span className={`px-task-date ${overdue ? 'is-overdue' : ''}`}>{due ? `${overdue ? 'Überfällig · ' : ''}${dateLabel(due)}` : task.due_text ? 'Frist klären' : 'Ohne Frist'}</span><ChevronRight size={14} className="px-row-arrow" aria-hidden="true" />
  </button>{edit && <button type="button" className="px-row-action" disabled={busy} onClick={edit} aria-label={`Bearbeiten: ${task.title}`} title="Bearbeiten"><Pencil size={15} aria-hidden="true" /></button>}</div>
}

function TaskDialog({ task, canEdit, plannerAvailable, onClose, onPlan, onEdit, openSource }: { task: PlannedWork; canEdit: boolean; plannerAvailable: boolean; onClose: () => void; onPlan: () => void; onEdit: () => void; openSource: (id: string) => void }) {
  const [tab, setTab] = useState('details')
  const [focus] = useState(() => document.activeElement as HTMLElement | null)
  const history = [...task.history.map((e, index) => ({ ...e, key: `source-${index}`, label: e.human ? decisionNames[e.action as keyof typeof decisionNames] : actionNames[e.action as keyof typeof actionNames], text: e.claim, actor: e.human ? 'Von dir' : e.source_title, source: e.source_version })), ...(task.planning_history || []).map(e => ({ ...e, key: e.command_id, label: e.action === 'create_task' ? 'Todo angelegt' : 'Planung aktualisiert', text: e.reason, actor: 'Von dir', source: undefined, quotes: [] as string[] }))].reverse().sort((a, b) => b.event_date.localeCompare(a.event_date))
  return <Dialog open onOpenChange={v => { if (!v) onClose() }}><DialogContent className="wm-dialog px-dialog" overlayClassName="wm-overlay px-overlay" closeLabel="Zur Aufgabenliste zurück" onCloseAutoFocus={e => { e.preventDefault(); focus?.focus() }}><DialogHeader><DialogTitle>{task.title}</DialogTitle><DialogDescription>{task.owner || 'Zuständigkeit offen'} · {task.origin === 'manual' ? 'Manuell angelegt' : 'Aus einem Meeting belegt'}</DialogDescription></DialogHeader>
    <div className="px-dialog-tabs" role="group" aria-label="Aufgabendetails"><button type="button" aria-pressed={tab === 'details'} onClick={() => setTab('details')}>Aufgabe</button><button type="button" aria-pressed={tab === 'history'} onClick={() => setTab('history')}>Verlauf <span>{history.length}</span></button></div>
    <div className="px-dialog-scroll">{tab === 'details' ? <><dl className="px-task-properties"><div><dt>Status</dt><dd><span className={`px-status status-${task.status}`}>{statusNames[task.status]}</span></dd></div><div><dt>Priorität</dt><dd>{priorityNames[task.priority || 'normal']}</dd></div><div><dt>Geplant für</dt><dd>{task.scheduled_date ? dateLabel(task.scheduled_date) : 'Noch nicht eingeplant'}</dd></div><div><dt>Fällig am</dt><dd>{dueDate(task) ? dateLabel(dueDate(task)!) : task.due_text || 'Keine Frist festgelegt'}{task.due_reference_date && <small>Genannt am {dateLabel(task.due_reference_date)}</small>}</dd></div><div><dt>Geschätzter Aufwand</dt><dd>{task.estimate_minutes ? `${numberLabel(task.estimate_minutes)} Minuten` : 'Nicht geschätzt'}</dd></div></dl>
      {task.claim && <section><h3>{task.origin === 'manual' ? 'Beschreibung' : 'Belegter Arbeitsstand'}</h3><p className="px-prose">{task.claim}</p></section>}{task.condition_text && <section className="px-notice"><h3>Voraussetzungen</h3><p className="px-prose">{task.condition_text}</p></section>}{task.note && task.origin !== 'manual' && <section><h3>Deine Arbeitsnotiz</h3><p className="px-prose">{task.note}</p></section>}<EvidenceConfidence observation={task} />{task.action_uncertainty && <p className="px-notice">Noch zu klären: {task.action_uncertainty}</p>}{task.uncertainty && task.uncertainty !== task.action_uncertainty && <p className="px-muted">Einordnung: {task.uncertainty}</p>}{task.original_time_expression && <p className="px-muted">Zeitangabe im Original: {task.original_time_expression}</p>}
    </> : <ol className="px-timeline">{history.map(event => <li key={event.key}><div><strong>{event.label || event.action}</strong><time>{dateLabel(event.event_date)}</time></div><p className="px-muted">{event.actor}</p>{event.text && <p className="px-prose">{event.text}</p>}{'patch' in event && event.patch && <dl className="px-event-patch">{Object.entries(event.patch).map(([key, value]) => <div key={key}><dt>{{ scheduled_date: 'Geplant für', due_date: 'Fällig am', status: 'Status', title: 'Titel', owner: 'Zuständig', priority: 'Priorität', estimate_minutes: 'Aufwand in Minuten', note: 'Notiz' }[key] || key}</dt><dd>{value === null || value === '' ? 'Entfernt' : key.endsWith('_date') ? dateLabel(String(value)) : key === 'status' ? statusNames[value as keyof typeof statusNames] : key === 'priority' ? priorityNames[value as keyof typeof priorityNames] : String(value)}</dd></div>)}</dl>}{event.quotes.map((quote, i) => <blockquote key={i}>{quote}</blockquote>)}{event.source && <button type="button" className="px-text-button" onClick={() => openSource(event.source!)}>Original öffnen</button>}</li>)}</ol>}</div>
    <footer className="px-dialog-footer"><button className="px-button" type="button" onClick={onClose}>Zurück</button>{canEdit && <><button className="px-button" type="button" onClick={onEdit}>{task.origin === 'manual' ? 'Todo bearbeiten' : 'Status & Fälligkeit ändern'}</button>{plannerAvailable && task.origin !== 'manual' && <button type="button" className="px-button px-primary" onClick={onPlan}>Einplanen</button>}</>}</footer>
  </DialogContent></Dialog>
}

export function ProductivityPage({ page, local = false, dataVersion = 0, cacheScope = '' }: { page: Page; local?: boolean; dataVersion?: number; cacheScope?: string }) {
  const location = useRoute()
  const preferences = usePreferences()
  const rawAsOf = location.params.get('as_of')
  const asOf = isoDate(rawAsOf) || ''
  const [attempt, retry] = useState(0)
  const key = `${asOf}:${attempt}:${dataVersion}`
  const { data, error: loadError, refreshing, confirmed } = useReviewSnapshot(asOf, key, cacheScope)
  const [byPage, setByPage] = useState<Partial<Record<Page, Filters>>>({})
  const memberId = location.params.get('member')
  const storedFilters = byPage[page] || initialFilters()
  const selectedMember = data?.planner?.team.find(m => m.id === memberId)
  const filters = selectedMember && page === 'team' ? { ...storedFilters, teamScope: selectedMember.active ? 'active' : 'former', owners: [selectedMember.name] } : storedFilters
  const [limits, setLimits] = useState<Partial<Record<Page, number>>>({})
  const limit = limits[page] || 25
  function setLimit(next: number | ((previous: number) => number)) { setLimits(previous => ({ ...previous, [page]: typeof next === 'function' ? next(previous[page] || 25) : next })) }
  const [edit, setEdit] = useState<DecisionTarget | null>(null)
  const [planner, setPlanner] = useState<{ task?: PlannedWork } | null>(null)
  const [notice, setNotice] = useState('')
  const [quickError, setQuickError] = useState('')
  const [quickBusy, setQuickBusy] = useState(false)
  const [undo, setUndo] = useState<{ task: PlannedWork; status: string } | null>(null)
  const quickRequest = useRef<Record<string, unknown> | null>(null)
  const quickSending = useRef(false)
  const [quickRetry, setQuickRetry] = useState(false)
  const quickUndo = useRef<{task: PlannedWork; status: string} | null>(null)
  const week = isoDate(location.params.get('week')) || monday(localDay())
  const layout = location.params.has('view') ? location.params.get('view') === 'week' ? 'week' : 'list' : preferences.taskView
  useEffect(() => {
    if (!rawAsOf || asOf) return
    const params = new URLSearchParams(location.params)
    params.delete('as_of')
    navigate(page, params, true)
  }, [asOf, location.params, page, rawAsOf])
  function setWeek(value: string) { const p = new URLSearchParams(location.params); p.set('week', value); navigate(page, p) }
  function setLayout(value: string) { const p = new URLSearchParams(location.params); p.set('view', value); navigate(page, p) }
  const sourceId = location.params.get('source')
  const knowledgeId = location.params.get('knowledge')
  const openedLayers = useRef<Set<string>>(new Set())
  function layer(name: string, id: string | null) {
    if (id) { const params = new URLSearchParams(location.params); params.set(name, id); openedLayers.current.add(name); navigate(page, params) }
    else if (openedLayers.current.has(name)) { openedLayers.current.delete(name); window.history.back() }
    else { const params = new URLSearchParams(location.params); params.delete(name); navigate(page, params, true) }
  }
  const setSourceId = (id: string | null) => layer('source', id)
  const setKnowledgeId = (id: string | null) => layer('knowledge', id)
  const pendingDialogRoute = useRef(false)
  useLayoutEffect(() => {
    window.history.scrollRestoration = 'manual'
    window.scrollTo({ top: rememberedScroll(page), behavior: 'instant' })
    const track = () => { if (window.location.hash.split('?')[0] === `#${page}`) rememberScroll(page) }
    window.addEventListener('scroll', track, { passive: true })
    return () => window.removeEventListener('scroll', track)
  }, [page])
  const team = data?.planner?.team || []
  const canEdit = confirmed && data?.can_edit === true && data.revision !== undefined && (!asOf || asOf === data.dates.at(-1))
  const supportsPlanning = data?.planner?.supported === true
  const work = useMemo(() => data ? allWork(data) : [], [data])
  const pageWork = work.filter(w => page === 'todos' ? personal(w.owner) : page === 'team' ? filters.teamScope === 'external' ? !personal(w.owner) && !memberFor(w.owner, team) : !!memberFor(w.owner, team) && memberFor(w.owner, team)?.active === (filters.teamScope !== 'former') : true)
  const needle = filters.query.trim().toLocaleLowerCase('de')
  function change(values: Partial<Filters>) { if (memberId) { const p = new URLSearchParams(location.params); p.delete('member'); navigate(page, p, true) } setByPage(previous => ({ ...previous, [page]: { ...filters, ...values } })); setLimit(25) }
  function resetFilters() {
    const params = new URLSearchParams(location.params)
    params.delete('as_of')
    params.delete('member')
    if (params.toString() !== location.params.toString()) navigate(page, params, true)
    setByPage(previous => ({ ...previous, [page]: initialFilters() }))
    setLimit(25)
  }
  function matching(o: { title: string; claim?: string; owner: string | null; matter: string; quotes?: string[]; last_changed?: string }, kind?: string) {
    return (!needle || [o.title, o.claim, o.owner, o.matter, ...(o.quotes || [])].join(' ').toLocaleLowerCase('de').includes(needle)) && (!filters.owners.length || filters.owners.includes(page === 'team' ? memberFor(o.owner, team)?.name || o.owner || '' : o.owner || '')) && (!filters.matters.length || filters.matters.includes(o.matter)) && (!kind || !filters.kinds.length || filters.kinds.includes(kind)) && (!filters.from || !!o.last_changed && o.last_changed >= filters.from) && (!filters.to || !!o.last_changed && o.last_changed <= filters.to)
  }
  function matchesDue(w: PlannedWork) {
    const due = dueDate(w)
    if (!filters.due) return true
    if (filters.due === 'none') return !due
    if (filters.due === 'overdue') return !!due && due < localDay() && ['open', 'waiting'].includes(w.status)
    return !!due && due >= week && due <= addDays(week, 6)
  }
  const filtered = pageWork.filter(w => matching(w) && (!filters.statuses.length || filters.statuses.includes(w.status)) && matchesDue(w))
    .sort((a, b) => filters.sort === 'title_asc' ? a.title.localeCompare(b.title, 'de')
      : filters.sort === 'title_desc' ? b.title.localeCompare(a.title, 'de')
      : filters.sort === 'due_asc' ? (dueDate(a) || '9999').localeCompare(dueDate(b) || '9999')
      : filters.sort === 'due_desc' ? (dueDate(b) || '').localeCompare(dueDate(a) || '')
      : filters.sort === 'changed_asc' ? a.last_changed.localeCompare(b.last_changed)
      : filters.sort === 'changed_desc' ? b.last_changed.localeCompare(a.last_changed)
      : filters.sort === 'priority_asc' ? ({ high: 2, normal: 1, low: 0 }[a.priority || 'normal'] - { high: 2, normal: 1, low: 0 }[b.priority || 'normal']) || a.title.localeCompare(b.title, 'de')
      : ({ high: 0, normal: 1, low: 2 }[a.priority || 'normal'] - { high: 0, normal: 1, low: 2 }[b.priority || 'normal']) || (dueDate(a) || '9999').localeCompare(dueDate(b) || '9999') || a.title.localeCompare(b.title, 'de'))
  const knowledgeSort = ['oldest', 'title_asc', 'title_desc', 'kind'].includes(filters.sort) ? filters.sort : 'newest'
  const activeKnowledge = (data?.knowledge || []).filter(k => k.data.knowledge_status !== 'rejected')
  const knowledge = activeKnowledge.filter(k => matching({ ...k.data, matter: k.matter_title, last_changed: k.event_date }, k.kind) && (page !== 'pruefen' || k.data.required_review && !k.data.human_decision))
    .sort((a, b) => knowledgeSort === 'oldest' ? a.event_date.localeCompare(b.event_date)
      : knowledgeSort === 'title_asc' ? a.data.title.localeCompare(b.data.title, 'de')
      : knowledgeSort === 'title_desc' ? b.data.title.localeCompare(a.data.title, 'de')
      : knowledgeSort === 'kind' ? kindNames[a.kind].localeCompare(kindNames[b.kind], 'de') || a.data.title.localeCompare(b.data.title, 'de')
      : b.event_date.localeCompare(a.event_date))
  const options = (items: string[]) => [...new Set(items.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'de')).map(value => ({ value, label: value }))
  const owners = options((page === 'wissen' || page === 'pruefen' ? activeKnowledge.map(k => k.data.owner || '') : pageWork.map(w => memberFor(w.owner, team)?.name || w.owner || '')) || [])
  const matters = options((page === 'wissen' || page === 'pruefen' ? activeKnowledge.map(k => k.matter_title) : pageWork.map(w => w.matter)) || [])
  const task = work.find(w => w.id === location.params.get('task'))
  const source = data?.sources.find(s => s.id === sourceId)
  const detail = data?.knowledge.find(k => k.id === knowledgeId)
  const isKnowledge = page === 'wissen' || page === 'pruefen'
  const metricWork = pageWork.filter(w => matching(w))
  const weekTasks = metricWork.filter(w => w.scheduled_date && w.scheduled_date >= week && w.scheduled_date <= addDays(week, 6))
  const weeklyDone = metricWork.filter(w => { const d = completedOn(w); return d && d >= week && d <= addDays(week, 6) && w.status === 'done' })
  const plannedDone = weekTasks.filter(w => w.status === 'done').length
  const blocked = metricWork.filter(w => w.status === 'waiting').length
  function openTask(id: string) { const params = new URLSearchParams(location.params); params.set('task', id); pendingDialogRoute.current = true; navigate(page, params) }
  function closeTask() { if (pendingDialogRoute.current) { pendingDialogRoute.current = false; window.history.back() } else { const params = new URLSearchParams(location.params); params.delete('task'); navigate(page, params, true) } }
  function saved() { setPlanner(null); setEdit(null); setNotice(local ? 'In der lokalen Testkopie gespeichert.' : 'Änderung gespeichert.'); retry(v => v + 1) }
  async function runQuick(request?: Record<string, unknown>, undoState: { task: PlannedWork; status: string } | null = null) {
    if (quickSending.current || !data || data.revision === undefined || !canEdit) return
    if (!quickRequest.current && request) { quickUndo.current = undoState; quickRequest.current = request }
    if (!quickRequest.current) return
    const action = quickRequest.current.action
    quickSending.current = true; setQuickBusy(true); setQuickError('')
    try {
      await postMemory('/decisions', quickRequest.current)
      quickRequest.current = null
      setUndo(quickUndo.current); setQuickRetry(false)
      const message = action === 'reject' ? 'Vorschlag verworfen.' : action === 'approve' || action === 'confirm_knowledge' ? 'Vorschlag übernommen.' : 'Status gespeichert.'
      setNotice(local ? `${message} Nur in der lokalen Testkopie.` : message)
      retry(v => v + 1)
    } catch (e) {
      setQuickError((e as Error).message); setQuickRetry(!(e instanceof MemoryWriteError) || e.status >= 500)
      if (e instanceof MemoryWriteError && e.status < 500) quickRequest.current = null
    } finally { quickSending.current = false; setQuickBusy(false) }
  }
  function quickStatus(task?: PlannedWork, status?: string) {
    if (!task || !status || data?.revision === undefined) { void runQuick(); return }
    void runQuick({ command_id: crypto.randomUUID(), expected_revision: data.revision, target_id: task.id, action: task.origin === 'manual' ? 'update_task' : 'set_status', patch: { status }, reason: status === 'done' ? 'Von dir in der Aufgabenliste als erledigt markiert.' : 'Statusänderung von dir in der Aufgabenliste zurückgenommen.' }, status === 'done' ? { task, status: task.status } : null)
  }
  function quickReview(item: Knowledge, action: 'approve' | 'confirm_knowledge' | 'reject') {
    if (data?.revision === undefined) return
    if (action === 'reject') {
      setEdit({ id: item.id, observation: item.data, action: 'reject' })
      return
    }
    void runQuick({ command_id: crypto.randomUUID(), expected_revision: data.revision, target_id: item.id, action, patch: {}, reason: '' })
  }
  function editTask(task: PlannedWork) {
    if (task.origin === 'manual') setPlanner({ task })
    else setEdit({ id: task.id, observation: task, work: task, action: 'correct' })
  }
  function editKnowledge(item: Knowledge) {
    const workItem = work.find(w => w.id === (item.data.update_target || item.id))
    const pendingReview = item.data.required_review && !item.data.human_decision
    setEdit({ id: workItem && !pendingReview ? workItem.id : item.id, observation: workItem && !pendingReview ? workItem : item.data, work: workItem, action: workItem && !pendingReview ? 'correct' : 'correct_confirm' })
  }
  const count = isKnowledge ? knowledge.length : filtered.length
  const activeFilters = [...filters.owners.map(value => ({ key: 'owners' as const, value })), ...filters.matters.map(value => ({ key: 'matters' as const, value })), ...filters.kinds.map(value => ({ key: 'kinds' as const, value }))]
  const taskRows = (items: PlannedWork[]) => items.map(w => <TaskRow key={w.id} task={w} open={() => openTask(w.id)} edit={canEdit ? () => editTask(w) : undefined} busy={quickBusy || !!quickError} toggle={canEdit && ['open', 'waiting', 'done'].includes(w.status) ? () => quickStatus(w, w.status === 'done' ? 'open' : 'done') : undefined} teamName={page === 'team' ? memberFor(w.owner, team)?.name || w.owner || undefined : undefined} />)
  return <div className="px-workspace">
    <header className="px-heading"><div><p className="px-eyebrow">{page === 'uebersicht' ? 'Dein Arbeitstag' : page === 'team' ? 'Teamführung' : page === 'todos' ? 'Deine Arbeitswoche' : page === 'betrieb' ? 'Betriebsprüfung' : 'Arbeitsgedächtnis'}</p><h1>{pageNames[page]}</h1><p className="px-muted">{page === 'uebersicht' ? 'Dein Tag, dein Team und die nächsten Schritte.' : page === 'todos' ? 'Aufgaben im Blick. Zeit bewusst einplanen.' : page === 'team' ? 'Zuständigkeit, Fortschritt und offene Hindernisse.' : page === 'wissen' ? 'Belegte Informationen, Entscheidungen und offene Fragen.' : page === 'pruefen' ? 'Unklare Vorschläge prüfen und bewusst entscheiden.' : page === 'betrieb' ? 'Fachliche Vorschläge und technische Unterbrechungen getrennt prüfen.' : 'Aufnahme, Auswertung und gespeicherte Korrekturen.'}</p></div><div className="px-actions"><button className="px-icon-button" type="button" aria-label="Arbeitsstand aktualisieren" onClick={() => retry(v => v + 1)} disabled={refreshing}><RotateCcw size={16} aria-hidden="true" /></button>{canEdit && supportsPlanning && ['todos', 'team'].includes(page) && <button className="px-button px-primary" type="button" onClick={() => setPlanner({})}><Plus size={15} aria-hidden="true" />Todo anlegen</button>}</div></header>
    {local && <p className="px-draft">Lokaler Entwurf · Änderungen betreffen ausschließlich die Testkopie.</p>}{notice && <p className="px-success" role="status">{notice}{undo && <button type="button" className="px-text-button" disabled={!canEdit || quickBusy} onClick={() => quickStatus(undo.task, undo.status)}>Rückgängig</button>}</p>}{quickBusy && <p role="status" className="px-muted"><span className="wm-spinner" aria-hidden="true" /> Änderung wird gespeichert…</p>}{quickError && <div className="px-error" role="alert">{quickError}{quickRetry && <button className="px-button" type="button" disabled={quickBusy} onClick={() => void runQuick()}>Speicherung erneut prüfen</button>}<button className="px-button" type="button" onClick={() => { quickRequest.current = null; setQuickError(''); setUndo(null); retry(v => v + 1) }}>Aktuellen Stand laden</button></div>}
    {data && data.mode !== 'production' && <p className="px-draft">In Prüfung · {numberLabel(data.sources.length)} ausgewertete Meetings{data.archive_total !== undefined ? ` / ${numberLabel(data.archive_total)} Originale` : ''} · Stand {dateLabel(data.as_of)}</p>}
    {!data && refreshing && <div className="px-surface px-empty" role="status">Dein Arbeitsstand wird geladen…</div>}{data && refreshing && <p className="px-muted" role="status">Letzter geladener Stand · wird im Hintergrund aktualisiert…</p>}{loadError && <div className="px-surface px-empty" role="alert"><h2>{data ? 'Aktualisierung nicht möglich' : 'Arbeitsstand nicht erreichbar'}</h2>{data && <p>Du siehst den letzten geladenen Stand. Bearbeiten ist nach erfolgreicher Aktualisierung wieder möglich.</p>}<p>{loadError}</p><button type="button" className="px-button" onClick={() => retry(v => v + 1)}>Erneut versuchen</button></div>}
    {data && <>
      {asOf && !canEdit && <p className="px-notice">Historischer Wissensstand · Änderungen sind hier gesperrt. <button className="px-text-button" type="button" onClick={() => { const p = new URLSearchParams(location.params); p.delete('as_of'); navigate(page, p) }}>Zum aktuellen Stand</button></p>}
      {['todos', 'team'].includes(page) && <><div className="px-week-toolbar"><div className="px-actions"><button className="px-icon-button" aria-label="Vorherige Woche" type="button" onClick={() => setWeek(addDays(week, -7))}><ChevronLeft size={16} aria-hidden="true" /></button><strong>{dateLabel(week)} – {dateLabel(addDays(week, 6))}</strong><button className="px-icon-button" aria-label="Nächste Woche" type="button" onClick={() => setWeek(addDays(week, 7))}><ChevronRight size={16} aria-hidden="true" /></button><button className="px-text-button" type="button" onClick={() => setWeek(monday(localDay()))}>Diese Woche</button></div><div className="px-segmented" role="group" aria-label="Aufgabenansicht"><button type="button" aria-pressed={layout === 'list'} onClick={() => setLayout('list')}><List size={14} aria-hidden="true" />Liste</button><button type="button" aria-pressed={layout === 'week'} onClick={() => setLayout('week')}><CalendarDays size={14} aria-hidden="true" />Woche</button></div></div>
      <p className="px-metric-scope">Wochenüberblick für Person, Thema und Suche · alle Status</p><div className="px-metrics"><div><span>Wochenplan erledigt</span><strong>{plannedDone}<small> / {weekTasks.length}</small></strong><p>{weekTasks.length ? 'Todos mit Plantag in dieser Woche' : 'Noch keine Todos für diese Woche geplant'}</p></div><div><span>Abgeschlossen in der Woche</span><strong>{weeklyDone.length}</strong><p>Belegte Abschlüsse · aktuell erledigt</p></div><div><span>Blockierte Arbeit</span><strong>{blocked}</strong><p>Offene Hindernisse im gesamten Bereich</p></div></div>
      {page === 'team' && <><div className="px-segmented px-team-switch" role="group" aria-label="Teamumfang">{[['active', 'Aktives Team'], ['former', 'Ehemalige'], ['external', 'Weitere Kontakte']].map(([value, label]) => <button key={value} type="button" aria-pressed={filters.teamScope === value} onClick={() => change({ teamScope: value, owners: [] })}>{label}</button>)}</div>{filters.teamScope !== 'external' && <div className="px-members">{team.filter(m => m.active === (filters.teamScope === 'active')).map(m => { const items = work.filter(w => memberFor(w.owner, team)?.id === m.id); const open = items.filter(w => ['open', 'waiting'].includes(w.status)); const ownerValues = [...new Set(items.map(() => m.name))]; return <button key={m.id} className={`px-member ${filters.owners.some(o => [m.name, ...m.aliases].includes(o)) ? 'is-selected' : ''}`} type="button" onClick={() => change({ owners: ownerValues.length ? ownerValues : [m.name] })}><span className="px-avatar" aria-hidden="true">{m.name.split(' ').map(n => n[0]).slice(0, 2).join('')}</span><span><strong>{m.name}</strong><small>{m.active ? open.length ? `${open.length} offen · ${open.filter(w => w.status === 'waiting').length} blockiert` : 'Keine offenen Todos erfasst' : `${open.length} offen · ausgeschieden`}</small></span><ChevronRight size={14} aria-hidden="true" /></button> })}</div>}{filters.teamScope === 'former' && <p className="px-muted">Bestehende Aufgaben bleiben nachvollziehbar. Eine Übergabe erfolgt ausdrücklich über die Zuständigkeit.</p>}</>}
      </>}
      {!['betrieb', 'uebersicht', 'einstellungen'].includes(page) && <><div className="px-filterbar"><label className="px-search"><Search size={15} aria-hidden="true" /><input name="workspace_search" autoComplete="off" type="search" aria-label="Im Arbeitsbereich suchen" placeholder="Aufgabe, Thema oder Beleg suchen…" value={filters.query} onChange={e => change({ query: e.target.value })} /></label>{page !== 'todos' && <MultiFilter label="Person" options={owners} values={filters.owners} change={owners => change({ owners })} />}<MultiFilter label="Thema" options={matters} values={filters.matters} change={matters => change({ matters })} />{isKnowledge ? <MultiFilter label="Art" options={Object.entries(kindNames).map(([value, label]) => ({ value, label }))} values={filters.kinds} change={kinds => change({ kinds })} /> : <MultiFilter label="Status" options={Object.entries(statusNames).map(([value, label]) => ({ value, label }))} values={filters.statuses} change={statuses => change({ statuses })} />}
        <Popover.Root><Popover.Trigger asChild><button type="button" className="px-button"><SlidersHorizontal size={14} aria-hidden="true" />Mehr Filter</button></Popover.Trigger><Popover.Portal><Popover.Content className="px-popover px-form" sideOffset={7} align="end" collisionPadding={12}><strong>Zeitraum & Ansicht</strong><label>Geändert ab<input name="changed_from" autoComplete="off" type="date" max={filters.to || undefined} value={filters.from} onChange={e => change({ from: e.target.value })} /></label><label>Geändert bis<input name="changed_to" autoComplete="off" type="date" min={filters.from || undefined} value={filters.to} onChange={e => change({ to: e.target.value })} /></label>{filters.from && filters.to && filters.from > filters.to && <p role="alert">Das Enddatum muss nach dem Startdatum liegen.</p>}{!isKnowledge && <label>Fälligkeit<select name="due_filter" autoComplete="off" value={filters.due} onChange={e => change({ due: e.target.value })}><option value="">Alle Fristen</option><option value="overdue">Überfällig</option><option value="week">In der angezeigten Woche fällig</option><option value="none">Ohne eindeutig datierte Frist</option></select></label>}<label>Wissensstand<select name="as_of" autoComplete="off" value={asOf} onChange={e => { const p = new URLSearchParams(location.params); if (e.target.value) p.set('as_of', e.target.value); else p.delete('as_of'); p.delete('task'); navigate(page, p) }}><option value="">Aktueller Stand</option>{data.dates.map(d => <option key={d} value={d}>{d === data.dates.at(-1) ? `Aktueller Stand · ${dateLabel(d)}` : dateLabel(d)}</option>)}</select><small>Der letzte datierte Stand entspricht dem aktuellen Stand. Frühere Wissensstände sind nur zum Nachschlagen.</small></label><Popover.Close className="px-button">Fertig</Popover.Close></Popover.Content></Popover.Portal></Popover.Root><button className="px-icon-button" type="button" aria-label="Alle Filter zurücksetzen" onClick={resetFilters}><RotateCcw size={14} aria-hidden="true" /></button>
      </div><div className="px-selection"><span role="status">{numberLabel(count)} {isKnowledge ? 'Aussagen' : 'Todos'} in dieser Auswahl</span>{activeFilters.map(({ key, value }) => <button type="button" className="px-filter-chip" key={`${key}:${value}`} onClick={() => change({ [key]: filters[key].filter(v => v !== value) })}>{key === 'kinds' ? kindNames[value as keyof typeof kindNames] : value}<X size={12} aria-label="Filter entfernen" /></button>)}<label className="px-sort">Sortieren<select name="sort" autoComplete="off" value={isKnowledge ? knowledgeSort : filters.sort} onChange={e => change({ sort: e.target.value })}>{isKnowledge ? <><option value="newest">Neueste zuerst</option><option value="oldest">Älteste zuerst</option><option value="title_asc">Titel A–Z</option><option value="title_desc">Titel Z–A</option><option value="kind">Art & Titel</option></> : <><option value="priority_desc">Hohe Priorität zuerst</option><option value="priority_asc">Niedrige Priorität zuerst</option><option value="due_asc">Früheste Fälligkeit</option><option value="due_desc">Späteste Fälligkeit</option><option value="changed_desc">Zuletzt geändert</option><option value="changed_asc">Längst nicht geändert</option><option value="title_asc">Titel A–Z</option><option value="title_desc">Titel Z–A</option></>}</select></label></div></>}
      {page === 'uebersicht' ? <WorkspaceOverview data={data} openTask={openTask} /> : page === 'betrieb' ? <div className="working-memory"><ProcessingPanel onChanged={saved} /></div> : isKnowledge ? <div className="px-surface"><div className="px-list-head"><strong>{page === 'pruefen' ? 'Deine Prüfung ist gefragt' : 'Belegte Aussagen'}</strong><span>{page === 'pruefen' && canEdit ? 'Direkt übernehmen, verwerfen oder bearbeiten' : 'Details & Original im Popup'}</span></div>{knowledge.slice(0, limit).map(k => <div className="px-knowledge-row" key={k.id}><button type="button" className="px-knowledge-main" onClick={() => setKnowledgeId(k.id)}><span className={`px-kind kind-${k.kind}`}>{kindNames[k.kind]}</span><span><strong>{k.data.title}</strong><small>{k.matter_title}</small></span><time dateTime={k.event_date}>{dateLabel(k.event_date)}</time><ChevronRight size={14} aria-hidden="true" /></button>{canEdit && <div className="px-row-actions"><button type="button" className="px-row-action" onClick={() => editKnowledge(k)} aria-label={`Bearbeiten: ${k.data.title}`} title="Bearbeiten"><Pencil size={15} aria-hidden="true" /></button>{page === 'pruefen' && <><button type="button" className="px-row-action is-reject" disabled={quickBusy || !!quickError} onClick={() => quickReview(k, 'reject')} aria-label={`Verwerfen: ${k.data.title}`} title="Verwerfen"><X size={16} aria-hidden="true" /></button><button type="button" className="px-row-action is-accept" disabled={quickBusy || !!quickError} onClick={() => quickReview(k, k.kind === 'commitment' || !!k.data.update_target ? 'approve' : 'confirm_knowledge')} aria-label={`Übernehmen: ${k.data.title}`} title="Übernehmen"><Check size={17} aria-hidden="true" /></button></>}</div>}</div>)}{!knowledge.length && <div className="px-empty"><Filter size={23} aria-hidden="true" /><h2>{page === 'pruefen' ? 'Keine offenen Prüfungen in dieser Auswahl' : 'Keine passenden Aussagen'}</h2><p>Du kannst die Filter ändern oder zurücksetzen.</p></div>}{knowledge.length > limit && <button type="button" className="px-load-more" onClick={() => setLimit(v => v + 25)}>Weitere 25 anzeigen · {limit} von {knowledge.length}</button>}</div> : layout === 'list' ? <div className="px-surface"><div className="px-list-head"><strong>{page === 'todos' ? 'Deine Aufgaben' : 'Aufgaben im gewählten Teamumfang'}</strong><span>Fälligkeit</span></div>{taskRows(filtered.slice(0, limit))}{!filtered.length && <div className="px-empty"><CircleCheck size={24} aria-hidden="true" /><h2>Keine Todos in dieser Auswahl</h2><p>Ändere die Filter oder lege ein neues Todo an.</p></div>}{filtered.length > limit && <button type="button" className="px-load-more" onClick={() => setLimit(v => v + 25)}>Weitere 25 anzeigen · {limit} von {filtered.length}</button>}</div> : <><div className="px-calendar-scroll" tabIndex={0} aria-label="Wochenplanung, horizontal scrollbar"><div className="px-calendar">{Array.from({ length: 7 }, (_, i) => { const day = addDays(week, i); const tasks = filtered.filter(w => w.scheduled_date === day); const estimate = tasks.reduce((sum, w) => sum + (w.estimate_minutes || 0), 0); return <section key={day} className={`px-day ${day === localDay() ? 'is-today' : ''}`}><header><span>{new Intl.DateTimeFormat('de-DE', { weekday: 'short' }).format(new Date(`${day}T12:00:00`))}</span><strong>{new Intl.DateTimeFormat('de-DE', { day: 'numeric', month: 'short' }).format(new Date(`${day}T12:00:00`))}</strong><small>{tasks.length} Todos{estimate ? ` · ${estimate} Min. geschätzt` : ''}</small></header>{tasks.map(w => <button type="button" key={w.id} className={`px-calendar-task status-${w.status}`} onClick={() => openTask(w.id)}><span className="px-status">{statusNames[w.status]}</span><strong>{w.title}</strong>{page === 'team' && <small>{memberFor(w.owner, team)?.name || w.owner}</small>}{dueDate(w) && <small>Fällig {dateLabel(dueDate(w)!)}</small>}</button>)}{!tasks.length && <p className="px-day-empty">Noch nichts geplant</p>}</section> })}</div></div><div className="px-surface px-unplanned"><div className="px-list-head"><strong>Noch nicht eingeplant <span className="px-count">{filtered.filter(w => !w.scheduled_date).length}</span></strong><span>Todo öffnen → Einplanen</span></div>{taskRows(filtered.filter(w => !w.scheduled_date).slice(0, limit))}{filtered.filter(w => !w.scheduled_date).length > limit && <button type="button" className="px-load-more" onClick={() => setLimit(v => v + 25)}>Weitere 25 anzeigen</button>}<p className="px-muted px-list-foot">{filtered.filter(w => w.scheduled_date && (w.scheduled_date < week || w.scheduled_date > addDays(week, 6))).length} weitere Todos sind für andere Wochen eingeplant.</p></div></>}
      {task && <TaskDialog key={task.id} task={task} canEdit={canEdit} plannerAvailable={supportsPlanning} onClose={closeTask} onPlan={() => setPlanner({ task })} onEdit={() => editTask(task)} openSource={setSourceId} />}
      {detail && <KnowledgeDialog item={detail} close={() => setKnowledgeId(null)} openSource={() => setSourceId(detail.source_version)} edit={canEdit ? setEdit : undefined} work={[...data.personal, ...data.waiting, ...data.waiting_dependencies, ...data.completed, ...(data.cancelled || [])].find(w => w.id === (detail.data.update_target || detail.id))} />}
      {source && <SourceDialog key={source.id} source={source} onClose={() => setSourceId(null)} />}
      {edit && data.revision !== undefined && <DecisionDialog target={edit} revision={data.revision} onClose={() => setEdit(null)} onSaved={saved} onRefresh={saved} />}
      {planner && data.revision !== undefined && <PlannerEditor task={planner.task} revision={data.revision} team={team} onClose={() => setPlanner(null)} onSaved={saved} />}
    </>}
  </div>
}

function KnowledgeDialog({ item, close, openSource, edit, work }: { work?: Work; item: Knowledge; close: () => void; openSource: () => void; edit?: (target: DecisionTarget) => void }) {
  const [focus] = useState(() => document.activeElement as HTMLElement | null)
  return <Dialog open onOpenChange={v => { if (!v) close() }}><DialogContent className="wm-dialog px-dialog" overlayClassName="wm-overlay px-overlay" closeLabel="Zur Auswahl zurück" onCloseAutoFocus={e => { e.preventDefault(); focus?.focus() }}><DialogHeader><DialogTitle>{item.data.title}</DialogTitle><DialogDescription>{kindNames[item.kind]} · {item.matter_title} · {dateLabel(item.event_date)}</DialogDescription></DialogHeader><div className="px-dialog-scroll"><p className="px-prose">{item.data.claim}</p><EvidenceConfidence observation={item.data} />{item.data.human_corrections?.map(c => <p className="px-success" key={c.id}>Von dir bestätigt: {c.reason}</p>)}{item.data.human_decision && <p className="px-success">{decisionNames[item.data.human_decision.action]}{item.data.human_decision.reason ? `: ${item.data.human_decision.reason}` : ''}</p>}{item.data.original_interpretation && <details><summary>Ursprüngliche KI-Fassung und Korrekturen</summary><p>{item.data.original_interpretation.title}</p><p className="px-prose">{item.data.original_interpretation.claim}</p>{item.data.correction_history?.map(c => <p key={c.command_id}>{dateLabel(c.event_date)}: {c.reason}</p>)}</details>}{item.data.action_uncertainty && <p className="px-notice">{item.data.action_uncertainty}</p>}{item.data.uncertainty && <p className="px-muted">{item.data.uncertainty}</p>}{item.data.quotes.map((q, i) => <blockquote key={i}>{q}</blockquote>)}</div><footer className="px-dialog-footer"><button className="px-button" type="button" onClick={close}>Zurück</button><button className="px-button" type="button" onClick={openSource}>Original öffnen</button>{edit && <><button className="px-button" type="button" onClick={() => edit({ id: work && !(item.data.required_review && !item.data.human_decision) ? work.id : item.id, observation: work && !(item.data.required_review && !item.data.human_decision) ? work : item.data, work, action: work && !(item.data.required_review && !item.data.human_decision) ? 'correct' : 'correct_confirm' })}>{work && !(item.data.required_review && !item.data.human_decision) ? 'Aufgabe korrigieren' : 'Korrigieren und bestätigen'}</button>{item.data.required_review && !item.data.human_decision && <><button className="px-button" type="button" onClick={() => edit({ id: item.id, observation: item.data, action: 'reject' })}>Verwerfen</button>{<button className="px-button px-primary" type="button" onClick={() => edit({ id: item.id, observation: item.data, action: (item.kind === 'commitment' || item.data.update_target) ? 'approve' : 'confirm_knowledge' })}>Prüfen & bestätigen</button>}</>}</>}</footer></DialogContent></Dialog>
}
