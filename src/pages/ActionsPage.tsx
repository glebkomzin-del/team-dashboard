import { useMemo, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import {
  PRI_LABEL, PRI_RANK, PRI_STYLE, ST_LABEL, ST_STYLE, CAT_LABEL, CAT_ICON,
  FILTER_BAR_CLASS, FILTER_INPUT_CLASS, FILTER_TRIGGER_CLASS,
  Av, SH, TrashIcon, SourceChip, useSortState, sortBy, textMatch,
  type ActionTab, type Todo, type Blocker, type OpenItem,
} from '../lib/shared'
import type { DbProject, TableCounts } from '../supabase'

type MeetingReference = { meeting: { id: string; title: string }; deleted: boolean } | null

interface ActionsPageProps {
  todos: Todo[]
  blockers: Blocker[]
  openItems: OpenItem[]
  tableCounts: TableCounts
  memberNames: string[]
  projects: DbProject[]
  actionTab: ActionTab
  setActionTab: (t: ActionTab) => void
  globalSearch: string
  today: string
  cycleTodo: (t: Todo) => void
  handleDeleteTodo: (t: Todo) => void
  handleDeleteBlocker: (b: Blocker) => void
  handleDeleteOpen: (o: OpenItem) => void
  deleteTodos: (ids: string[]) => Promise<void>
  deleteBlockers: (ids: string[]) => Promise<void>
  deleteOpenItems: (ids: string[]) => Promise<void>
  setViewTodo: (t: Todo) => void
  setEditTodo: (t: Todo) => void
  setViewBlocker: (b: Blocker) => void
  setEditBlocker: (b: Blocker) => void
  setViewOpen: (o: OpenItem) => void
  setEditOpen: (o: OpenItem) => void
  resolveMeetingReference: (source?: string | null, meetingId?: string | null) => MeetingReference
  openMeetingReference: (reference: MeetingReference) => void
  getProjectName: (id: string | null) => string | null
  setConfirmDelete: (v: { label: string; action: () => void } | null) => void
}

export function ActionsPage({ todos, blockers, openItems, tableCounts, memberNames, projects, actionTab, setActionTab, globalSearch, today, cycleTodo, handleDeleteTodo, handleDeleteBlocker, handleDeleteOpen, deleteTodos, deleteBlockers, deleteOpenItems, setViewTodo, setEditTodo, setViewBlocker, setEditBlocker, setViewOpen, setEditOpen, resolveMeetingReference, openMeetingReference, getProjectName, setConfirmDelete }: ActionsPageProps) {
  const [todoSearch, setTodoSearch] = useState('')
  const [blockerSearch, setBlockerSearch] = useState('')
  const [blockerFilterAssignee, setBlockerFilterAssignee] = useState<string[]>([])
  const [blockerFilterStatus, setBlockerFilterStatus] = useState('all')
  const [openSearch, setOpenSearch] = useState('')
  const [openFilterOwner, setOpenFilterOwner] = useState<string[]>([])
  const [openFilterStatus, setOpenFilterStatus] = useState('all')
  const [openFilterCategory, setOpenFilterCategory] = useState('all')
  const [todoFilterAssignee, setTodoFilterAssignee] = useState<string[]>([])
  const [todoFilterDue, setTodoFilterDue] = useState('all')
  const [todoFilterStatus, setTodoFilterStatus] = useState('all')
  const [todoFilterProject, setTodoFilterProject] = useState('all')
  const todoSort = useSortState(); const blockerSort = useSortState(); const openSort = useSortState()
  const [todoSelected, setTodoSelected] = useState<Set<string>>(new Set())
  const [blockerSelected, setBlockerSelected] = useState<Set<string>>(new Set())
  const [openSelected, setOpenSelected] = useState<Set<string>>(new Set())

  const filteredTodos = useMemo(() => {
    let r = todos.filter(t => textMatch(t, todoSearch || globalSearch))
    if (todoFilterAssignee.length > 0) r = r.filter(t => todoFilterAssignee.includes(t.assignee))
    if (todoFilterStatus !== 'all') r = r.filter(t => t.status === todoFilterStatus)
    if (todoFilterProject !== 'all') r = r.filter(t => t.projectId === todoFilterProject)
    if (todoFilterDue === 'overdue') r = r.filter(t => t.dueDate && t.dueDate < today && t.status !== 'done')
    else if (todoFilterDue === 'this_week') { const d = new Date(); const s = new Date(d); s.setDate(d.getDate() - d.getDay() + 1); const e = new Date(s); e.setDate(s.getDate() + 6); const ss = s.toISOString().split('T')[0]; const ee = e.toISOString().split('T')[0]; r = r.filter(t => t.dueDate && t.dueDate >= ss && t.dueDate <= ee) }
    else if (todoFilterDue === 'no_date') r = r.filter(t => !t.dueDate)
    return todoSort.col ? sortBy(r, todoSort.col, todoSort.dir) : r.sort((a, b) => PRI_RANK[a.priority] - PRI_RANK[b.priority])
  }, [todos, todoSearch, globalSearch, todoFilterAssignee, todoFilterDue, todoFilterStatus, todoFilterProject, todoSort.col, todoSort.dir, today])
  const filteredBlockers = useMemo(() => {
    let r = blockers.filter(b => textMatch(b, blockerSearch || globalSearch))
    if (blockerFilterAssignee.length > 0) r = r.filter(b => blockerFilterAssignee.includes(b.reportedBy))
    if (blockerFilterStatus !== 'all') r = r.filter(b => b.status === blockerFilterStatus)
    return blockerSort.col ? sortBy(r, blockerSort.col, blockerSort.dir) : r
  }, [blockers, blockerSearch, globalSearch, blockerFilterAssignee, blockerFilterStatus, blockerSort.col, blockerSort.dir])
  const filteredOpen = useMemo(() => {
    let r = openItems.filter(o => textMatch(o, openSearch || globalSearch))
    if (openFilterOwner.length > 0) r = r.filter(o => openFilterOwner.includes(o.owner))
    if (openFilterStatus !== 'all') r = r.filter(o => o.status === openFilterStatus)
    if (openFilterCategory !== 'all') r = r.filter(o => o.category === openFilterCategory)
    return openSort.col ? sortBy(r, openSort.col, openSort.dir) : r
  }, [openItems, openSearch, globalSearch, openFilterOwner, openFilterStatus, openFilterCategory, openSort.col, openSort.dir])

  const handleBulkDeleteTodos = async () => { const ids = [...todoSelected]; setTodoSelected(new Set()); await deleteTodos(ids) }
  const handleBulkDeleteBlockers = async () => { const ids = [...blockerSelected]; setBlockerSelected(new Set()); await deleteBlockers(ids) }
  const handleBulkDeleteOpen = async () => { const ids = [...openSelected]; setOpenSelected(new Set()); await deleteOpenItems(ids) }

  return (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <h2 className="text-base font-semibold">Aktionen</h2>
                <div className="flex border border-[var(--syn-line)] rounded-lg overflow-hidden">
                  {([['todos', 'Todos', tableCounts.todos], ['blocker', 'Blocker', tableCounts.blockers], ['open', 'Offene Punkte', tableCounts.openItems]] as [ActionTab, string, number][]).map(([k, l, c]) => (
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
                    <div className={FILTER_BAR_CLASS}>
                      <Input placeholder="Suche..." value={todoSearch} onChange={e => setTodoSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                      <MultiSelectFilter selected={todoFilterAssignee} onChange={setTodoFilterAssignee} options={memberNames} allLabel="Zuständig" triggerWidth="w-[160px]" />
                      {projects.length > 0 && <Select value={todoFilterProject} onValueChange={setTodoFilterProject}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Projekte</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>}
                      <Select value={todoFilterStatus} onValueChange={setTodoFilterStatus}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="open">Offen</SelectItem><SelectItem value="in_progress">In Arbeit</SelectItem><SelectItem value="done">Erledigt</SelectItem></SelectContent></Select>
                      <Select value={todoFilterDue} onValueChange={setTodoFilterDue}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Termine</SelectItem><SelectItem value="overdue">Überfällig</SelectItem><SelectItem value="this_week">Diese Woche</SelectItem><SelectItem value="no_date">Ohne Datum</SelectItem></SelectContent></Select>
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="todos-table-scroll" className="p-0 max-h-[calc(100vh-196px)] overflow-y-auto"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
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
                        <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}>{(() => { const reference = resolveMeetingReference(t.meetingSource, t.meetingId); return <SourceChip meeting={reference?.meeting || null} deleted={reference?.deleted} onClick={() => openMeetingReference(reference)} /> })()}</TableCell>
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
                    <div className={FILTER_BAR_CLASS}>
                      <Input placeholder="Suche..." value={blockerSearch} onChange={e => setBlockerSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                      <MultiSelectFilter selected={blockerFilterAssignee} onChange={setBlockerFilterAssignee} options={memberNames} allLabel="Zuständig" triggerWidth="w-[160px]" />
                      <Select value={blockerFilterStatus} onValueChange={setBlockerFilterStatus}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="active">Aktiv</SelectItem><SelectItem value="resolved">Gelöst</SelectItem><SelectItem value="escalated">Eskaliert</SelectItem></SelectContent></Select>
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="blockers-table-scroll" className="p-0 max-h-[calc(100vh-196px)] overflow-y-auto"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
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
                        <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}>{(() => { const reference = resolveMeetingReference(b.meetingSource, b.meetingId); return <SourceChip meeting={reference?.meeting || null} deleted={reference?.deleted} onClick={() => openMeetingReference(reference)} /> })()}</TableCell>
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
                      <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => setEditOpen({ id: '__new__', owner: 'Nicht zugeordnet', title: '', description: '', category: 'info', status: 'open', meetingId: null, projectId: null, createdAt: '' })}>+ Neu</Button>
                      {openSelected.size > 0 && <button onClick={handleBulkDeleteOpen} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${openSelected.size} löschen`}><TrashIcon /></button>}
                    </div>
                    <div className={FILTER_BAR_CLASS}>
                      <Input placeholder="Suche..." value={openSearch} onChange={e => setOpenSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                      <MultiSelectFilter selected={openFilterOwner} onChange={setOpenFilterOwner} options={memberNames} allLabel="Zuständig" triggerWidth="w-[160px]" />
                      <Select value={openFilterStatus} onValueChange={setOpenFilterStatus}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="open">Offen</SelectItem><SelectItem value="watching">Beobachten</SelectItem><SelectItem value="closed">Geschlossen</SelectItem></SelectContent></Select>
                      <Select value={openFilterCategory} onValueChange={setOpenFilterCategory}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Kategorien</SelectItem><SelectItem value="decision">Entscheidung</SelectItem><SelectItem value="question">Frage</SelectItem><SelectItem value="risk">Risiko</SelectItem><SelectItem value="info">Information</SelectItem><SelectItem value="general">Allgemein (alt)</SelectItem><SelectItem value="opportunity">Chance (alt)</SelectItem><SelectItem value="follow_up">Nachverfolgung (alt)</SelectItem></SelectContent></Select>
                    </div>
                  </div>
                  <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="open-items-table-scroll" className="p-0 max-h-[calc(100vh-196px)] overflow-y-auto"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
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
                        <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}>{(() => { const reference = resolveMeetingReference(o.meetingSource, o.meetingId); return <SourceChip meeting={reference?.meeting || null} deleted={reference?.deleted} onClick={() => openMeetingReference(reference)} /> })()}</TableCell>
                        <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center"><button onClick={() => setEditOpen({...o})} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => setConfirmDelete({ label: o.title, action: () => handleDeleteOpen(o) })} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button><input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${openSelected.has(o.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={openSelected.has(o.id)} onChange={() => setOpenSelected(prev => { const n = new Set(prev); n.has(o.id) ? n.delete(o.id) : n.add(o.id); return n })} /></div></TableCell>
                      </TableRow>
                    ))}
                    {filteredOpen.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine offenen Punkte</TableCell></TableRow>}
                  </TableBody></Table></CardContent></Card>
                </section>
              )}
            </div>
  )
}
