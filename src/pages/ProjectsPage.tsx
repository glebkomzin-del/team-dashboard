import { useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  PRI_LABEL, PRI_RANK, PRI_STYLE, ST_LABEL, ST_STYLE,
  FILTER_BAR_CLASS, FILTER_INPUT_CLASS, FILTER_TRIGGER_CLASS,
  Av, SH, TrashIcon, useSortState, sortBy, textMatch, getProjectColor, addDays, todoEndDate,
  type ProjectView, type Todo, type Blocker,
} from '../lib/shared'
import { updateTodoStatus, updateTodoFull, type DbProject } from '../supabase'

interface ProjectsPageProps {
  projects: DbProject[]
  projectIds: string[]
  todos: Todo[]
  setTodos: Dispatch<SetStateAction<Todo[]>>
  blockers: Blocker[]
  memberNames: string[]
  today: string
  globalSearch: string
  projectView: ProjectView
  setProjectView: (v: ProjectView) => void
  projectMutationError: string | null
  handleOpenProjectDialog: (p: DbProject | '__new__') => void
  handleDeleteProject: (p: DbProject) => void
  deleteProjects: (ids: string[]) => Promise<string[]>
  getProjectName: (id: string | null) => string | null
  setViewProject: (p: DbProject) => void
  setViewTodo: (t: Todo) => void
  setEditTodo: (t: Todo) => void
  handleDeleteTodo: (t: Todo) => void
  setConfirmDelete: (v: { label: string; action: () => void } | null) => void
}

export function ProjectsPage({ projects, projectIds, todos, setTodos, blockers, memberNames, today, globalSearch, projectView, setProjectView, projectMutationError, handleOpenProjectDialog, handleDeleteProject, deleteProjects, getProjectName, setViewProject, setViewTodo, setEditTodo, handleDeleteTodo, setConfirmDelete }: ProjectsPageProps) {
  const [projectSearch, setProjectSearch] = useState('')
  const [projectSelected, setProjectSelected] = useState<Set<string>>(new Set())
  const projectSort = useSortState()
  const projectFilterStatus = 'all'
  const [printView, setPrintView] = useState<'table' | 'kanban' | 'gantt' | null>(null)
  const [ganttVisibleCols, setGanttVisibleCols] = useState<string[]>(['project', 'title', 'assignee', 'priority'])
  const [ganttColDropOpen, setGanttColDropOpen] = useState(false)
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

  const projectTodos = (pid: string) => todos.filter(t => t.projectId === pid)
  const projectBlockers = (pid: string) => blockers.filter(b => b.projectId === pid)

  const filteredProjects = useMemo(() => {
    let r = projects.filter(p => textMatch(p, projectSearch || globalSearch))
    if (projectFilterStatus !== 'all') r = r.filter(p => p.status === projectFilterStatus)
    return projectSort.col ? sortBy(r, projectSort.col, projectSort.dir) : r
  }, [projects, projectSearch, globalSearch, projectFilterStatus, projectSort.col, projectSort.dir])

  const kanbanTodosMemo = useMemo(() => {
    const priOrd: Record<string, number> = { urgent: 0, critical: 0, high: 1, medium: 2, low: 3 }
    const validProjectIds = new Set(projects.map(project => project.id))
    let result = todos.filter(todo => Boolean(todo.projectId) && validProjectIds.has(todo.projectId!))
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
  }, [todos, kanbanFilterProject, kanbanFilterAssignee, kanbanSortKey, kanbanSortDir, projects, getProjectName])

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
  }, [todos, ganttFilterProject, ganttFilterAssignee, ganttSortKey, ganttSortDir, getProjectName])
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

  const handleBulkDeleteProjects = async () => {
    const remaining = await deleteProjects([...projectSelected])
    setProjectSelected(new Set(remaining))
  }

  return (
    <>
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold">Projekte</h2>
                  <Button size="sm" variant="outline" className="h-7 text-xs border-[var(--syn-line)]" onClick={() => handleOpenProjectDialog('__new__')}>+ Neu</Button>
                  {projectSelected.size > 0 && <button onClick={handleBulkDeleteProjects} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${projectSelected.size} löschen`}><TrashIcon /></button>}
                </div>
                <div className={FILTER_BAR_CLASS}>
                  <Input placeholder="Suche..." value={projectSearch} onChange={e => setProjectSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                  <div className="flex border border-[var(--syn-line)] rounded-lg overflow-hidden">
                    {(['table', 'kanban', 'gantt'] as ProjectView[]).map(v => (
                      <button key={v} onClick={() => setProjectView(v)} className={`px-3 py-1.5 text-xs transition-colors ${projectView === v ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`} style={projectView !== v ? { color: 'var(--syn-text-muted)' } : {}}>
                        {v === 'table' ? '▤ Tabelle' : v === 'kanban' ? '▥ Kanban' : '▰ Gantt'}
                      </button>
                    ))}
                  </div>
                  <Button size="sm" variant="outline" className="h-8 text-xs border-[var(--syn-line)] gap-1" onClick={() => setPrintView(projectView)}>Drucken</Button>
                </div>
              </div>

              {projectMutationError && (
                <div role="alert" className="rounded-lg border border-[var(--syn-danger)]/30 bg-[var(--syn-danger-soft)] px-3 py-2 text-xs text-[var(--syn-danger)]">
                  {projectMutationError}
                </div>
              )}

              {/* TABLE VIEW */}
              {projectView === 'table' && (
                <div className="space-y-1">
                <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                  <SH label="Titel" field="name" sort={projectSort} onSort={projectSort.toggle} />
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
                  <div className={FILTER_BAR_CLASS}>
                    <Select value={kanbanFilterProject} onValueChange={setKanbanFilterProject}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Projekte</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>
                    <Select value={kanbanFilterAssignee} onValueChange={setKanbanFilterAssignee}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Zuständige</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                    <Select value={kanbanGroupBy} onValueChange={v => setKanbanGroupBy(v as KanbanGroupBy)}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent>
                      <SelectItem value="none">Keine Gruppe</SelectItem>
                      <SelectItem value="project">Gruppe: Projekt</SelectItem>
                      <SelectItem value="assignee">Gruppe: Zuständig</SelectItem>
                    </SelectContent></Select>
                    <div className="flex items-center h-8 w-[160px] rounded border border-[var(--syn-line)] overflow-hidden">
                      <button onClick={() => setKanbanSortDir(d => d === 'asc' ? 'desc' : 'asc')} className="h-full px-1.5 text-[10px] hover:bg-[var(--syn-hover)] border-r border-[var(--syn-line)]" style={{ color: 'var(--syn-text-muted)' }}>{kanbanSortDir === 'asc' ? '↑' : '↓'}</button>
                      <Select value={kanbanSortKey} onValueChange={v => setKanbanSortKey(v as any)}><SelectTrigger className="h-8 text-xs flex-1 border-0"><SelectValue /></SelectTrigger><SelectContent>
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
                    <div className={`${FILTER_BAR_CLASS} mb-3`}>
                      <Select value={ganttFilterProject} onValueChange={setGanttFilterProject}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Projekte</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>
                      <Select value={ganttFilterAssignee} onValueChange={setGanttFilterAssignee}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Zuständige</SelectItem>{memberNames.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select>
                      <Select value={ganttGroupBy} onValueChange={v => setGanttGroupBy(v as GanttGroupBy)}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent>
                        <SelectItem value="none">Keine Gruppe</SelectItem>
                        <SelectItem value="project">Gruppe: Projekt</SelectItem>
                        <SelectItem value="assignee">Gruppe: Zuständig</SelectItem>
                      </SelectContent></Select>
                      <div className="flex items-center h-8 w-[160px] rounded border border-[var(--syn-line)] overflow-hidden">
                        <button onClick={() => setGanttSortDir(d => d === 'asc' ? 'desc' : 'asc')} className="h-full px-1.5 text-[10px] hover:bg-[var(--syn-hover)] border-r border-[var(--syn-line)]" style={{ color: 'var(--syn-text-muted)' }}>{ganttSortDir === 'asc' ? '↑' : '↓'}</button>
                        <Select value={ganttSortKey} onValueChange={v => setGanttSortKey(v as any)}><SelectTrigger className="h-8 text-xs flex-1 border-0"><SelectValue /></SelectTrigger><SelectContent>
                          <SelectItem value="start">Start</SelectItem><SelectItem value="assignee">Zuständig</SelectItem><SelectItem value="title">Titel</SelectItem><SelectItem value="priority">Priorität</SelectItem><SelectItem value="project">Projekt</SelectItem>
                        </SelectContent></Select>
                      </div>
                      <div className="flex h-8 w-[160px] border border-[var(--syn-line)] rounded-lg overflow-hidden">
                        {(['month','quarter','year'] as const).map(g => (
                          <button key={g} onClick={() => setGanttGranularity(g)} className={`flex-1 px-2 py-1 text-[10px] transition-colors ${ganttGranularity === g ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`} style={ganttGranularity !== g ? { color: 'var(--syn-text-muted)' } : {}}>
                            {g === 'month' ? 'Monat' : g === 'quarter' ? 'Quartal' : 'Jahr'}
                          </button>
                        ))}
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

      {/* ═══ PRINT VIEW ═══ */}
      {printView && <div className="fixed inset-0 z-[9999] bg-white text-black overflow-auto print-view" style={{ colorScheme: 'light' }}>
        <div className="p-6 print:p-0">
          <div className="flex items-center justify-between mb-6 print:hidden">
            <h1 className="text-xl font-bold text-black">{printView === 'table' ? 'Tabellenansicht' : printView === 'kanban' ? 'Kanban-Ansicht' : 'Gantt-Ansicht'} — Projekte</h1>
            <div className="flex gap-2">
              <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white text-xs" onClick={() => window.print()}>Drucken</Button>
              <Button size="sm" className="text-xs bg-white hover:bg-gray-100 text-black border border-gray-300" onClick={() => setPrintView(null)}>✕ Schließen</Button>
            </div>
          </div>
          <div className="text-xs text-gray-400 mb-4 print:mb-2 print:block hidden">Gedruckt am {new Date().toLocaleDateString('de-DE')} — Meeting OS</div>

          {printView === 'table' && (
            <div className="overflow-hidden rounded-lg border border-gray-300">
              <table className="w-full border-collapse text-left text-xs">
                <thead className="bg-gray-100 text-gray-600">
                  <tr><th className="px-3 py-2">Projekt</th><th className="px-3 py-2">Beschreibung</th><th className="px-3 py-2 text-center">Todos</th><th className="px-3 py-2 text-center">Blocker</th><th className="px-3 py-2">Status</th></tr>
                </thead>
                <tbody>
                  {filteredProjects.map(project => (
                    <tr key={project.id} className="border-t border-gray-200">
                      <td className="px-3 py-2 font-medium text-black">{project.name}</td>
                      <td className="px-3 py-2 text-gray-600">{project.description || '—'}</td>
                      <td className="px-3 py-2 text-center text-gray-600">{todos.filter(todo => todo.projectId === project.id).length}</td>
                      <td className="px-3 py-2 text-center text-gray-600">{blockers.filter(blocker => blocker.projectId === project.id).length}</td>
                      <td className="px-3 py-2 text-gray-600">{ST_LABEL[project.status || 'active'] || project.status || '—'}</td>
                    </tr>
                  ))}
                  {filteredProjects.length === 0 && <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-400">Keine Projekte</td></tr>}
                </tbody>
              </table>
            </div>
          )}

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
    </>
  )
}
