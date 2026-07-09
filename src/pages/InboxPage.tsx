import { useMemo, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import type { DateRange } from 'react-day-picker'
import {
  PRI_LABEL, PRI_STYLE, ST_LABEL, ST_STYLE, CAT_LABEL, CAT_ICON,
  MEETING_DATE_PRESETS, type DatePresetKey, presetToRange, rangeToPresetKey,
  parseLocalDate, toLocalDateValue, formatShortDate,
  FILTER_BAR_CLASS, FILTER_INPUT_CLASS, FILTER_TRIGGER_CLASS,
  Av, CompactRangeCalendar, TrashIcon, SourceChip, shortTopic, inboxMeetingView,
  type Meeting, type Todo, type Blocker, type OpenItem,
} from '../lib/shared'
import type { DbInboxItem, DbProject, TableCounts } from '../supabase'

type MeetingReference = { meeting: { id: string; title: string }; deleted: boolean } | null
type InboxTab = 'meetings' | 'todos' | 'blockers' | 'open' | 'resolutions'

interface InboxPageProps {
  inboxItems: DbInboxItem[]
  tableCounts: TableCounts
  projects: DbProject[]
  memberNames: string[]
  globalSearch: string
  today: string
  handleInboxApprove: (item: DbInboxItem) => Promise<void>
  handleInboxReject: (id: string) => Promise<void>
  handleInboxEdit: (item: DbInboxItem) => void
  cycleTodoInbox: (item: DbInboxItem) => void
  setViewMeeting: (m: Meeting) => void
  setViewTodo: (t: Todo) => void
  setViewBlocker: (b: Blocker) => void
  setViewOpen: (o: OpenItem) => void
  resolveMeetingReference: (source?: string | null, meetingId?: string | null) => MeetingReference
  openMeetingReference: (reference: MeetingReference) => void
  openSourceEntity: (entityType: string, entityId: string) => void
  getProjectName: (id: string | null) => string | null
}

export function InboxPage({ inboxItems, tableCounts, projects, memberNames, globalSearch, today, handleInboxApprove, handleInboxReject, handleInboxEdit, cycleTodoInbox, setViewMeeting, setViewTodo, setViewBlocker, setViewOpen, resolveMeetingReference, openMeetingReference, openSourceEntity, getProjectName }: InboxPageProps) {
  const [inboxSelected, setInboxSelected] = useState<Set<string>>(new Set())
  const [inboxTab, setInboxTab] = useState<InboxTab>('meetings')
  const [meetingSearch, setMeetingSearch] = useState('')
  const [meetingFilterParticipant, setMeetingFilterParticipant] = useState<string[]>([])
  const [meetingFilterDateFrom, setMeetingFilterDateFrom] = useState('')
  const [meetingFilterDateTo, setMeetingFilterDateTo] = useState('')
  const [meetingDateFilterOpen, setMeetingDateFilterOpen] = useState(false)
  const [meetingDateDraft, setMeetingDateDraft] = useState<DateRange | undefined>()
  const [meetingDateFilterView, setMeetingDateFilterView] = useState<'list' | 'custom'>('list')
  const [todoSearch, setTodoSearch] = useState('')
  const [todoFilterAssignee, setTodoFilterAssignee] = useState<string[]>([])
  const [todoFilterStatus, setTodoFilterStatus] = useState('all')
  const [todoFilterDue, setTodoFilterDue] = useState('all')
  const [todoFilterProject, setTodoFilterProject] = useState('all')
  const [blockerSearch, setBlockerSearch] = useState('')
  const [blockerFilterAssignee, setBlockerFilterAssignee] = useState<string[]>([])
  const [blockerFilterStatus, setBlockerFilterStatus] = useState('all')
  const [openSearch, setOpenSearch] = useState('')
  const [openFilterOwner, setOpenFilterOwner] = useState<string[]>([])
  const [openFilterStatus, setOpenFilterStatus] = useState('all')
  const [openFilterCategory, setOpenFilterCategory] = useState('all')
  const [statusSearch, setStatusSearch] = useState('')
  const [statusFilterKind, setStatusFilterKind] = useState('all')

  const handleBulkInboxReject = async () => {
    const ids = Array.from(inboxSelected)
    setInboxSelected(new Set())
    await Promise.all(ids.map(id => handleInboxReject(id)))
  }
  const handleBulkInboxApprove = async () => {
    const items = inboxItems.filter(x => inboxSelected.has(x.id))
    setInboxSelected(new Set())
    for (const item of items) await handleInboxApprove(item)
  }

            const ib = { meetings: inboxItems.filter(i => i.entity_type === 'meeting'), todos: inboxItems.filter(i => i.entity_type === 'todo'), blockers: inboxItems.filter(i => i.entity_type === 'blocker'), open: inboxItems.filter(i => i.entity_type === 'open_item'), resolutions: inboxItems.filter(i => i.entity_type === 'resolution') }
            const duplicateItems = inboxItems.filter(i => ['todo', 'blocker', 'open_item'].includes(i.entity_type) && i.payload?.duplicate_of)
            const matchesText = (value: unknown, query: string) => !query.trim() || JSON.stringify(value).toLowerCase().includes(query.trim().toLowerCase())
            const filteredMeetings = useMemo(() => {
              let r = ib.meetings.filter(item => matchesText(item.payload, meetingSearch || globalSearch))
              if (meetingFilterParticipant.length > 0) r = r.filter(item => (item.payload.participants || []).some((p: string) => meetingFilterParticipant.includes(p)))
              if (meetingFilterDateFrom) r = r.filter(item => (item.payload.meeting_date || '') >= meetingFilterDateFrom)
              if (meetingFilterDateTo) r = r.filter(item => (item.payload.meeting_date || '') <= meetingFilterDateTo)
              return r
            }, [ib.meetings, meetingSearch, globalSearch, meetingFilterParticipant, meetingFilterDateFrom, meetingFilterDateTo])
            const filteredTodos = useMemo(() => {
              let r = ib.todos.filter(item => matchesText(item.payload, todoSearch || globalSearch))
              if (todoFilterAssignee.length > 0) r = r.filter(item => todoFilterAssignee.includes(item.payload.assignee || 'Nicht zugeordnet'))
              if (todoFilterStatus !== 'all') r = r.filter(item => (item.payload.status || 'open') === todoFilterStatus)
              if (todoFilterProject !== 'all') r = r.filter(item => item.payload.project_id === todoFilterProject)
              if (todoFilterDue === 'overdue') r = r.filter(item => item.payload.due_date && item.payload.due_date < today && (item.payload.status || 'open') !== 'done')
              else if (todoFilterDue === 'this_week') { const d = new Date(); const s = new Date(d); s.setDate(d.getDate() - d.getDay() + 1); const e = new Date(s); e.setDate(s.getDate() + 6); const ss = s.toISOString().split('T')[0]; const ee = e.toISOString().split('T')[0]; r = r.filter(item => item.payload.due_date && item.payload.due_date >= ss && item.payload.due_date <= ee) }
              else if (todoFilterDue === 'no_date') r = r.filter(item => !item.payload.due_date)
              return r
            }, [ib.todos, todoSearch, globalSearch, todoFilterAssignee, todoFilterStatus, todoFilterProject, todoFilterDue, today])
            const filteredBlockers = useMemo(() => {
              let r = ib.blockers.filter(item => matchesText(item.payload, blockerSearch || globalSearch))
              if (blockerFilterAssignee.length > 0) r = r.filter(item => blockerFilterAssignee.includes(item.payload.reported_by || 'Nicht zugeordnet'))
              if (blockerFilterStatus !== 'all') r = r.filter(item => (item.payload.status || 'active') === blockerFilterStatus)
              return r
            }, [ib.blockers, blockerSearch, globalSearch, blockerFilterAssignee, blockerFilterStatus])
            const filteredOpen = useMemo(() => {
              let r = ib.open.filter(item => matchesText(item.payload, openSearch || globalSearch))
              if (openFilterOwner.length > 0) r = r.filter(item => openFilterOwner.includes(item.payload.owner || 'Nicht zugeordnet'))
              if (openFilterStatus !== 'all') r = r.filter(item => (item.payload.status || 'open') === openFilterStatus)
              if (openFilterCategory !== 'all') r = r.filter(item => (item.payload.category || 'info') === openFilterCategory)
              return r
            }, [ib.open, openSearch, globalSearch, openFilterOwner, openFilterStatus, openFilterCategory])
            const filteredResolutions = useMemo(() => ib.resolutions.filter(item => matchesText(item.payload, statusSearch || globalSearch) && (statusFilterKind === 'all' || statusFilterKind === 'resolution')), [ib.resolutions, statusSearch, globalSearch, statusFilterKind])
            const filteredDuplicates = useMemo(() => duplicateItems.filter(item => matchesText(item.payload, statusSearch || globalSearch) && (statusFilterKind === 'all' || statusFilterKind === 'duplicate')), [duplicateItems, statusSearch, globalSearch, statusFilterKind])
            const inboxTabs: [InboxTab, string, number][] = [
              ['meetings', 'Meetings', ib.meetings.length],
              ['todos', 'Todos', ib.todos.length],
              ['blockers', 'Blocker', ib.blockers.length],
              ['open', 'Offene Punkte', ib.open.length],
              ['resolutions', 'Statusänderung', ib.resolutions.length + duplicateItems.length],
            ]
            // Map source filename → meeting vm (for Quelle column in todos/blockers/open_items)
            const sourceFileMap = new Map<string, Meeting>()
            ib.meetings.forEach(item => { if (item.source) sourceFileMap.set(item.source, inboxMeetingView(item)) })
            const FC = ({ item }: { item: DbInboxItem }) => (
              <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center">
                <button onClick={() => handleInboxEdit(item)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }} title="Bearbeiten">✎</button>
                <button onClick={() => handleInboxApprove(item)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-ok)]/10 transition-colors" style={{ color: 'var(--syn-ok)' }} title={item.payload?.duplicate_of ? 'Dublette bestätigen' : 'Übernehmen'}>✓</button>
                <button onClick={() => handleInboxReject(item.id)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }} title="Ablehnen">✕</button>
                <input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${inboxSelected.has(item.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={inboxSelected.has(item.id)} onChange={() => setInboxSelected(prev => { const n = new Set(prev); n.has(item.id) ? n.delete(item.id) : n.add(item.id); return n })} />
              </div></TableCell>
            )
            const SH2 = ({ label, className }: { label: string; className?: string }) => <TableHead className={`text-xs text-center ${className||''}`}>{label}</TableHead>
            const selRow = (id: string) => setInboxSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
            const targetEntityType = (table?: string) => table === 'todos' ? 'todo' : table === 'blockers' ? 'blocker' : table === 'open_items' ? 'open_item' : ''
            const targetLabel = (table?: string) => table === 'todos' ? 'Todo' : table === 'blockers' ? 'Blocker' : table === 'open_items' ? 'Offener Punkt' : table === 'inbox_items' ? 'Inbox-Eintrag' : 'Eintrag'
            const DuplicateBadge = ({ item }: { item: DbInboxItem }) => {
              const dup = item.payload?.duplicate_of
              if (!dup) return null
              const entityType = targetEntityType(dup.table)
              return (
                <button
                  onClick={e => { e.stopPropagation(); if (entityType) openSourceEntity(entityType, dup.id) }}
                  className="mt-1 inline-flex max-w-full items-center gap-1 rounded border border-[var(--syn-danger)]/40 px-1.5 py-0.5 text-[10px] hover:bg-[var(--syn-danger)]/10"
                  style={{ color: 'var(--syn-danger)' }}
                  title={dup.reason || 'Mögliche Dublette'}
                >
                  <span>Mögliche Dublette von:</span><span className="truncate">{dup.title || dup.id}</span>
                </button>
              )
            }
            return (
              <div className="space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 min-h-7">
                    <h2 className="text-base font-semibold">Inbox <span data-testid="inbox-db-count" className="font-normal" style={{ color: 'var(--syn-text-muted)' }}>({tableCounts.inbox})</span></h2>
                    <div className="flex border border-[var(--syn-line)] rounded-lg overflow-hidden">
                      {inboxTabs.map(([k, l, c]) => (
                        <button key={k} onClick={() => setInboxTab(k)} className={`px-4 py-1.5 text-xs transition-colors ${inboxTab === k ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`} style={inboxTab !== k ? { color: 'var(--syn-text-muted)' } : {}}>
                          {l} {c > 0 && <span className="ml-1 opacity-70">({c})</span>}
                        </button>
                      ))}
                    </div>
                    <div className={`h-7 flex items-center gap-2 transition-opacity ${inboxSelected.size > 0 ? 'opacity-100' : 'opacity-0 pointer-events-none'}`} aria-hidden={inboxSelected.size === 0}>
                      <button onClick={handleBulkInboxApprove} className="h-7 w-32 px-2 flex items-center justify-center gap-1 rounded border border-[var(--syn-ok)]/40 hover:bg-[var(--syn-ok)]/10 transition-colors text-xs" style={{ color: 'var(--syn-ok)' }}>✓ {inboxSelected.size} übernehmen</button>
                      <button onClick={handleBulkInboxReject} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${inboxSelected.size} ablehnen`}><TrashIcon /></button>
                    </div>
                  </div>
                </div>
                {inboxItems.length === 0 && (
                  <div className="rounded-xl border border-[var(--syn-line)] py-14 flex flex-col items-center gap-2" style={{ background: 'var(--syn-surface)' }}>
                    <p className="text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine ausstehenden Einträge</p>
                    <p className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>Sobald Make ein Szenario ausführt, landen neue Einträge hier.</p>
                  </div>
                )}
                {/* ── Meetings ── */}
                {inboxTab === 'meetings' && (
                  <section>
                    <div className="flex items-center justify-end mb-3 flex-wrap gap-2">
                      <div className={FILTER_BAR_CLASS}>
                        <Input placeholder="Suche..." value={meetingSearch} onChange={e => setMeetingSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                        <MultiSelectFilter selected={meetingFilterParticipant} onChange={setMeetingFilterParticipant} options={memberNames} allLabel="Alle Teilnehmer" testId="inbox-meeting-participant-filter" triggerWidth="w-[160px]" />
                        {(() => {
                          const activePreset = rangeToPresetKey(meetingFilterDateFrom, meetingFilterDateTo)
                          const hasFilter = Boolean(meetingFilterDateFrom || meetingFilterDateTo)
                          const compactDate = (v: string) => {
                            const d = parseLocalDate(v)!
                            return d.getFullYear() === new Date().getFullYear() ? d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) : formatShortDate(d)
                          }
                          const triggerLabel = activePreset ? MEETING_DATE_PRESETS.find(p => p.key === activePreset)!.label : meetingFilterDateFrom && meetingFilterDateTo ? `${compactDate(meetingFilterDateFrom)} – ${compactDate(meetingFilterDateTo)}` : meetingFilterDateFrom ? `Ab ${compactDate(meetingFilterDateFrom)}` : meetingFilterDateTo ? `Bis ${compactDate(meetingFilterDateTo)}` : 'Zeitraum'
                          const resetFilter = () => { setMeetingFilterDateFrom(''); setMeetingFilterDateTo(''); setMeetingDateDraft(undefined) }
                          const applyPreset = (key: DatePresetKey) => { const r = presetToRange(key); setMeetingFilterDateFrom(toLocalDateValue(r.from)); setMeetingFilterDateTo(toLocalDateValue(r.to)); setMeetingDateFilterOpen(false) }
                          return (
                            <Popover open={meetingDateFilterOpen} onOpenChange={open => { setMeetingDateFilterOpen(open); if (open) { setMeetingDateFilterView('list'); setMeetingDateDraft(meetingFilterDateFrom || meetingFilterDateTo ? { from: parseLocalDate(meetingFilterDateFrom), to: parseLocalDate(meetingFilterDateTo) } : undefined) } }}>
                              <PopoverTrigger asChild>
                                <button data-testid="inbox-meeting-date-filter" className="h-8 w-[160px] rounded-md border border-[var(--syn-line)] bg-[var(--syn-surface-2)] px-3 text-xs flex items-center gap-2 hover:bg-[var(--syn-hover)] transition-colors">
                                  {hasFilter && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--syn-accent)]" />}
                                  <span className="truncate text-left flex-1">{triggerLabel}</span>
                                  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 shrink-0 opacity-50" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
                                </button>
                              </PopoverTrigger>
                              <PopoverContent align="end" className="w-auto p-0 overflow-hidden border-[var(--syn-line)] bg-[var(--syn-bg)]">
                                {meetingDateFilterView === 'list' ? (
                                  <div className="w-[188px] p-1.5 space-y-0.5">
                                    {MEETING_DATE_PRESETS.map(p => <button key={p.key} onClick={() => applyPreset(p.key)} className={`w-full text-left text-xs px-2.5 py-1.5 rounded transition-colors ${activePreset === p.key ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`}>{p.label}</button>)}
                                    <div className="h-px my-1 bg-[var(--syn-line)]" />
                                    <button onClick={() => { setMeetingDateFilterView('custom'); setMeetingDateDraft(meetingFilterDateFrom || meetingFilterDateTo ? { from: parseLocalDate(meetingFilterDateFrom), to: parseLocalDate(meetingFilterDateTo) } : undefined) }} className="w-full text-left text-xs px-2.5 py-1.5 rounded hover:bg-[var(--syn-hover)] flex items-center justify-between" style={{ color: 'var(--syn-text-muted)' }}><span>Benutzerdefiniert</span><svg aria-hidden="true" viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="m9 18 6-6-6-6" /></svg></button>
                                    {hasFilter && <button onClick={() => { resetFilter(); setMeetingDateFilterOpen(false) }} className="w-full text-left text-xs px-2.5 py-1.5 rounded hover:bg-[var(--syn-hover)]" style={{ color: 'var(--syn-danger)' }}>Alle Zeiträume</button>}
                                  </div>
                                ) : (
                                  <div className="w-auto">
                                    <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--syn-line)]"><button onClick={() => setMeetingDateFilterView('list')} className="flex items-center gap-1 text-xs hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-muted)' }}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6" /></svg>Zurück</button><span className="text-xs font-medium ml-auto">Zeitraum wählen</span></div>
                                    <CompactRangeCalendar mode="range" selected={meetingDateDraft} onSelect={setMeetingDateDraft} defaultMonth={meetingDateDraft?.from} />
                                    <div className="flex items-center justify-between gap-4 px-4 py-2 border-t border-[var(--syn-line)]"><span className="text-xs text-[var(--syn-text-muted)] truncate">{meetingDateDraft?.from ? `${formatShortDate(meetingDateDraft.from)}${meetingDateDraft.to ? ` – ${formatShortDate(meetingDateDraft.to)}` : ''}` : 'Alle Meetings'}</span><Button size="sm" className="h-8 bg-[var(--syn-accent)] text-white" onClick={() => { setMeetingFilterDateFrom(toLocalDateValue(meetingDateDraft?.from)); setMeetingFilterDateTo(toLocalDateValue(meetingDateDraft?.to)); setMeetingDateFilterOpen(false) }}>Übernehmen</Button></div>
                                  </div>
                                )}
                              </PopoverContent>
                            </Popover>
                          )
                        })()}
                      </div>
                    </div>
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="inbox-meetings-scroll" className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <SH2 label="Datum" className="w-[100px]" />
                      <SH2 label="Titel" />
                      <SH2 label="Teilnehmer" className="w-[180px]" />
                      <SH2 label="Themen" className="w-[260px]" />
                      <SH2 label="Anpassen" className="w-[80px]" />
                    </TableRow></TableHeader><TableBody>
                      {filteredMeetings.map(item => { const p = item.payload; const vm = inboxMeetingView(item); return (
                        <TableRow key={item.id} className={`text-sm cursor-pointer select-none border-[var(--syn-line)] group ${inboxSelected.has(item.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => selRow(item.id)}>
                          <TableCell className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>{p.meeting_date||'—'}</TableCell>
                          <TableCell className="text-left font-medium"><button onClick={e => { e.stopPropagation(); setViewMeeting(vm) }} className="text-left hover:text-[var(--syn-accent)] leading-snug">{p.title||'—'}</button></TableCell>
                          <TableCell><div className="flex flex-col gap-0.5">{(p.participants||[]).slice(0,5).map((pt: string,i: number)=><span key={i} className="text-[10px] rounded truncate block" style={{background:'var(--syn-surface-3)',color:'var(--syn-text-muted)',padding:'1px 6px',maxWidth:'164px'}}>{pt}</span>)}{(p.participants||[]).length>5&&<span className="text-[10px] font-medium" style={{color:'var(--syn-text-faint)'}}>+{(p.participants||[]).length-5}</span>}</div></TableCell>
                          <TableCell><div data-testid="inbox-topic-pills" className="flex flex-col gap-0.5">{vm.topics.slice(0, 5).map((topic, i) => <Badge key={i} variant="outline" className="text-[9px] border-[var(--syn-line)] whitespace-nowrap w-fit" style={{ padding: '1px 5px' }}>{shortTopic(topic)}</Badge>)}{vm.topics.length > 5 && <span className="text-[10px] font-medium" style={{ color: 'var(--syn-text-faint)' }}>+{vm.topics.length - 5}</span>}</div></TableCell>
                          <FC item={item} />
                        </TableRow>
                      )})}
                      {filteredMeetings.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-sm py-8" style={{color:'var(--syn-text-faint)'}}>Keine Meetings</TableCell></TableRow>}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
                {/* ── Todos ── */}
                {inboxTab === 'todos' && (
                  <section>
                    <div className="flex items-center justify-end mb-3 flex-wrap gap-2">
                      <div className={FILTER_BAR_CLASS}>
                        <Input placeholder="Suche..." value={todoSearch} onChange={e => setTodoSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                        <MultiSelectFilter selected={todoFilterAssignee} onChange={setTodoFilterAssignee} options={memberNames} allLabel="Zuständig" triggerWidth="w-[160px]" />
                        {projects.length > 0 && <Select value={todoFilterProject} onValueChange={setTodoFilterProject}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Projekte</SelectItem>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>}
                        <Select value={todoFilterStatus} onValueChange={setTodoFilterStatus}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="open">Offen</SelectItem><SelectItem value="in_progress">In Arbeit</SelectItem><SelectItem value="done">Erledigt</SelectItem></SelectContent></Select>
                        <Select value={todoFilterDue} onValueChange={setTodoFilterDue}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Termine</SelectItem><SelectItem value="overdue">Überfällig</SelectItem><SelectItem value="this_week">Diese Woche</SelectItem><SelectItem value="no_date">Ohne Datum</SelectItem></SelectContent></Select>
                      </div>
                    </div>
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="inbox-todos-scroll" className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <SH2 label="Aufgabe" />
                      <SH2 label="Zuständig" className="w-[130px]" />
                      <SH2 label="Priorität" className="w-[100px]" />
                      <SH2 label="Fällig" className="w-[100px]" />
                      <SH2 label="Status" className="w-[100px]" />
                      <SH2 label="Erstellt" className="w-[100px]" />
                      <SH2 label="Quelle" className="w-[140px]" />
                      {projects.length > 0 && <SH2 label="Projekt" className="w-[120px]" />}
                      <SH2 label="Anpassen" className="w-[90px]" />
                    </TableRow></TableHeader><TableBody>
                      {filteredTodos.map(item => { const p = item.payload; const srcDate = p.meeting_date || item.created_at?.split('T')[0] || ''; const vt = { id: 'ib_'+item.id, assignee: p.assignee||'Nicht zugeordnet', title: p.title||'', description: p.description||'', status: p.status||'open', priority: p.priority||'medium', dueDate: p.due_date||null, startDate: null, durationDays: 1, dependsOn: [], meetingId: null, projectId: null, createdAt: srcDate }; return (
                        <TableRow key={item.id} className={`text-sm border-[var(--syn-line)] group select-none ${inboxSelected.has(item.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => selRow(item.id)}>
                          <TableCell className="text-left"><div className="flex items-center gap-2"><button onClick={e => { e.stopPropagation(); cycleTodoInbox(item) }} className="w-4 h-4 rounded border shrink-0 flex items-center justify-center transition-colors hover:border-[var(--syn-accent)] hover:bg-[var(--syn-accent-soft)]" style={{ borderColor: 'var(--syn-line)' }} /><div className="min-w-0"><button onClick={e => { e.stopPropagation(); setViewTodo(vt) }} className="text-left hover:text-[var(--syn-accent)]">{p.title||'—'}</button>{p.description&&<div className="text-xs truncate max-w-sm" style={{color:'var(--syn-text-faint)'}}>{p.description}</div>}<DuplicateBadge item={item} /></div></div></TableCell>
                          <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={p.assignee||'?'}/><span className="text-xs">{p.assignee||'—'}</span></div></TableCell>
                          <TableCell><Badge className={`text-[10px] ${PRI_STYLE[p.priority]||''}`}>{PRI_LABEL[p.priority]||p.priority||'—'}</Badge></TableCell>
                          <TableCell className={`text-xs ${p.due_date && p.due_date < today && (p.status || 'open') !== 'done' ? 'text-[var(--syn-danger)] font-bold' : ''}`} style={!(p.due_date && p.due_date < today && (p.status || 'open') !== 'done') ? {color:'var(--syn-text-muted)'} : {}}>{p.due_date||'—'}</TableCell>
                          <TableCell><Badge className={`text-[10px] ${ST_STYLE[p.status||'open']||''}`}>{ST_LABEL[p.status||'open']||'—'}</Badge></TableCell>
                          <TableCell className="text-xs" style={{color:'var(--syn-text-muted)'}}>{srcDate||'—'}</TableCell>
                          <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}>{(() => { const pendingMeeting = item.source ? sourceFileMap.get(item.source) || null : null; const reference = pendingMeeting ? { meeting: pendingMeeting, deleted: false } : resolveMeetingReference(item.source, p.meeting_id); return <SourceChip meeting={reference?.meeting || null} deleted={reference?.deleted} onClick={() => pendingMeeting ? setViewMeeting(pendingMeeting) : openMeetingReference(reference)} /> })()}</TableCell>
                          {projects.length > 0 && <TableCell className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>{getProjectName(p.project_id || null) || '—'}</TableCell>}
                          <FC item={item} />
                        </TableRow>
                      )})}
                      {filteredTodos.length === 0 && <TableRow><TableCell colSpan={projects.length > 0 ? 9 : 8} className="text-center text-sm py-8" style={{color:'var(--syn-text-faint)'}}>Keine Todos</TableCell></TableRow>}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
                {/* ── Blocker ── */}
                {inboxTab === 'blockers' && (
                  <section>
                    <div className="flex items-center justify-end mb-3 flex-wrap gap-2">
                      <div className={FILTER_BAR_CLASS}>
                        <Input placeholder="Suche..." value={blockerSearch} onChange={e => setBlockerSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                        <MultiSelectFilter selected={blockerFilterAssignee} onChange={setBlockerFilterAssignee} options={memberNames} allLabel="Zuständig" triggerWidth="w-[160px]" />
                        <Select value={blockerFilterStatus} onValueChange={setBlockerFilterStatus}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="active">Aktiv</SelectItem><SelectItem value="resolved">Gelöst</SelectItem><SelectItem value="escalated">Eskaliert</SelectItem></SelectContent></Select>
                      </div>
                    </div>
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="inbox-blockers-scroll" className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <SH2 label="Blocker" />
                      <SH2 label="Zuständig" className="w-[130px]" />
                      <SH2 label="Status" className="w-[100px]" />
                      <SH2 label="Erstellt" className="w-[100px]" />
                      <SH2 label="Quelle" className="w-[140px]" />
                      <SH2 label="Anpassen" className="w-[90px]" />
                    </TableRow></TableHeader><TableBody>
                      {filteredBlockers.map(item => { const p = item.payload; const srcDate = p.meeting_date || item.created_at?.split('T')[0] || ''; const vb = { id: 'ib_'+item.id, reportedBy: p.reported_by||'Nicht zugeordnet', title: p.title||'', description: p.description||'', status: p.status||'active', meetingId: null, projectId: null, createdAt: srcDate }; return (
                        <TableRow key={item.id} className={`text-sm border-[var(--syn-line)] group select-none cursor-pointer ${inboxSelected.has(item.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => selRow(item.id)}>
                          <TableCell className="text-left"><button onClick={e => { e.stopPropagation(); setViewBlocker(vb) }} className="text-left font-medium hover:text-[var(--syn-accent)]">{p.title||'—'}</button>{p.description&&<div className="text-xs truncate max-w-md" style={{color:'var(--syn-text-faint)'}}>{p.description}</div>}<DuplicateBadge item={item} /></TableCell>
                          <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={p.reported_by||'?'}/><span className="text-xs">{p.reported_by||'—'}</span></div></TableCell>
                          <TableCell><Badge className={`text-[10px] ${ST_STYLE[p.status||'active']||''}`}>{ST_LABEL[p.status||'active']||'—'}</Badge></TableCell>
                          <TableCell className="text-xs" style={{color:'var(--syn-text-muted)'}}>{srcDate||'—'}</TableCell>
                          <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}>{(() => { const pendingMeeting = item.source ? sourceFileMap.get(item.source) || null : null; const reference = pendingMeeting ? { meeting: pendingMeeting, deleted: false } : resolveMeetingReference(item.source, p.meeting_id); return <SourceChip meeting={reference?.meeting || null} deleted={reference?.deleted} onClick={() => pendingMeeting ? setViewMeeting(pendingMeeting) : openMeetingReference(reference)} /> })()}</TableCell>
                          <FC item={item} />
                        </TableRow>
                      )})}
                      {filteredBlockers.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm py-8" style={{color:'var(--syn-text-faint)'}}>Keine Blocker</TableCell></TableRow>}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
                {/* ── Offene Punkte ── */}
                {inboxTab === 'open' && (
                  <section>
                    <div className="flex items-center justify-end mb-3 flex-wrap gap-2">
                      <div className={FILTER_BAR_CLASS}>
                        <Input placeholder="Suche..." value={openSearch} onChange={e => setOpenSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                        <MultiSelectFilter selected={openFilterOwner} onChange={setOpenFilterOwner} options={memberNames} allLabel="Zuständig" triggerWidth="w-[160px]" />
                        <Select value={openFilterStatus} onValueChange={setOpenFilterStatus}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Status</SelectItem><SelectItem value="open">Offen</SelectItem><SelectItem value="watching">Beobachten</SelectItem><SelectItem value="closed">Geschlossen</SelectItem></SelectContent></Select>
                        <Select value={openFilterCategory} onValueChange={setOpenFilterCategory}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Kategorien</SelectItem><SelectItem value="decision">Entscheidung</SelectItem><SelectItem value="question">Frage</SelectItem><SelectItem value="risk">Risiko</SelectItem><SelectItem value="info">Information</SelectItem><SelectItem value="general">Allgemein (alt)</SelectItem><SelectItem value="opportunity">Chance (alt)</SelectItem><SelectItem value="follow_up">Nachverfolgung (alt)</SelectItem></SelectContent></Select>
                      </div>
                    </div>
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="inbox-open-scroll" className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <TableHead className="w-10"></TableHead>
                      <SH2 label="Item" />
                      <SH2 label="Kategorie" className="w-[100px]" />
                      <SH2 label="Zuständig" className="w-[130px]" />
                      <SH2 label="Status" className="w-[100px]" />
                      <SH2 label="Erstellt" className="w-[100px]" />
                      <SH2 label="Quelle" className="w-[140px]" />
                      <SH2 label="Anpassen" className="w-[90px]" />
                    </TableRow></TableHeader><TableBody>
                      {filteredOpen.map(item => { const p = item.payload; const srcDate = p.meeting_date || item.created_at?.split('T')[0] || ''; const vo = { id: 'ib_'+item.id, owner: p.owner||'Nicht zugeordnet', title: p.title||'', description: p.description||'', category: p.category||'info', status: p.status||'open', meetingId: null, projectId: null, createdAt: srcDate }; return (
                        <TableRow key={item.id} className={`text-sm border-[var(--syn-line)] group select-none cursor-pointer ${inboxSelected.has(item.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => selRow(item.id)}>
                          <TableCell className="text-center">{CAT_ICON[p.category]||'○'}</TableCell>
                          <TableCell className="text-left"><button onClick={e => { e.stopPropagation(); setViewOpen(vo) }} className="text-left hover:text-[var(--syn-accent)]">{p.title||'—'}</button>{p.description&&<div className="text-xs truncate max-w-sm" style={{color:'var(--syn-text-faint)'}}>{p.description}</div>}<DuplicateBadge item={item} /></TableCell>
                          <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-line)]">{CAT_LABEL[p.category]||p.category||'—'}</Badge></TableCell>
                          <TableCell><div className="flex items-center justify-center gap-1.5"><Av name={p.owner||'?'}/><span className="text-xs">{p.owner||'—'}</span></div></TableCell>
                          <TableCell><Badge className={`text-[10px] ${ST_STYLE[p.status||'open']||''}`}>{ST_LABEL[p.status||'open']||'—'}</Badge></TableCell>
                          <TableCell className="text-xs" style={{color:'var(--syn-text-muted)'}}>{srcDate||'—'}</TableCell>
                          <TableCell className="overflow-hidden" onClick={e => e.stopPropagation()}>{(() => { const pendingMeeting = item.source ? sourceFileMap.get(item.source) || null : null; const reference = pendingMeeting ? { meeting: pendingMeeting, deleted: false } : resolveMeetingReference(item.source, p.meeting_id); return <SourceChip meeting={reference?.meeting || null} deleted={reference?.deleted} onClick={() => pendingMeeting ? setViewMeeting(pendingMeeting) : openMeetingReference(reference)} /> })()}</TableCell>
                          <FC item={item} />
                        </TableRow>
                      )})}
                      {filteredOpen.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-sm py-8" style={{color:'var(--syn-text-faint)'}}>Keine offenen Punkte</TableCell></TableRow>}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
                {/* ── Statusänderungen & Dubletten ── */}
                {inboxTab === 'resolutions' && (
                  <section>
                    <div className="flex items-center justify-end mb-3 flex-wrap gap-2">
                      <div className={FILTER_BAR_CLASS}>
                        <Input placeholder="Suche..." value={statusSearch} onChange={e => setStatusSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                        <Select value={statusFilterKind} onValueChange={setStatusFilterKind}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Alle Vorschläge</SelectItem><SelectItem value="resolution">Statusänderungen</SelectItem><SelectItem value="duplicate">Dubletten</SelectItem></SelectContent></Select>
                      </div>
                    </div>
                    <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="inbox-resolutions-scroll" className="p-0"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                      <SH2 label="Vorschlag" className="w-[130px]" />
                      <SH2 label="Eintrag" />
                      <SH2 label="Beleg / Grund" />
                      <SH2 label="Quelle" className="w-[140px]" />
                      <SH2 label="Bewertung" className="w-[100px]" />
                      <SH2 label="Anpassen" className="w-[90px]" />
                    </TableRow></TableHeader><TableBody>
                      {filteredResolutions.map(item => { const p = item.payload; const reference = resolveMeetingReference(null, p.evidence_meeting_id); const entityType = targetEntityType(p.target_table); return (
                        <TableRow key={item.id} className={`text-sm border-[var(--syn-line)] group select-none cursor-pointer ${inboxSelected.has(item.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => selRow(item.id)}>
                          <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-line)]">{targetLabel(p.target_table)}</Badge></TableCell>
                          <TableCell className="text-left"><button onClick={e => { e.stopPropagation(); if (entityType) openSourceEntity(entityType, p.target_id) }} className="text-left font-medium hover:text-[var(--syn-accent)]">{p.target_title || '—'}</button><div className="text-xs" style={{color:'var(--syn-text-faint)'}}>{ST_LABEL[p.proposed_status] || p.proposed_status || 'gelöst'}</div></TableCell>
                          <TableCell className="text-left"><button onClick={e => { e.stopPropagation(); openMeetingReference(reference) }} className="text-left hover:text-[var(--syn-accent)]"><span className="text-xs italic line-clamp-2">"{p.evidence_quote || '—'}"</span></button><div className="text-[10px] mt-1" style={{color:'var(--syn-text-faint)'}}>{p.evidence_source === 'summary' ? 'Summary' : 'Transkript-Chunk'}</div></TableCell>
                          <TableCell className="text-xs" onClick={e => e.stopPropagation()}><SourceChip meeting={reference?.meeting || null} deleted={reference?.deleted} onClick={() => openMeetingReference(reference)} />{p.evidence_meeting_date && <div className="mt-1" style={{color:'var(--syn-text-faint)'}}>{p.evidence_meeting_date}</div>}</TableCell>
                          <TableCell><Badge className={`text-[10px] ${p.confidence === 'high' ? 'bg-[var(--syn-ok-soft)] text-[var(--syn-ok)]' : 'bg-[var(--syn-warn-soft)] text-[var(--syn-warn)]'}`}>{p.confidence === 'high' ? 'Hoch' : 'Mittel'}</Badge></TableCell>
                          <FC item={item} />
                        </TableRow>
                      )})}
                      {filteredDuplicates.map(item => { const p = item.payload; const dup = p.duplicate_of; const entityType = targetEntityType(dup?.table); const ownType = item.entity_type === 'todo' ? 'Todo' : item.entity_type === 'blocker' ? 'Blocker' : 'Offener Punkt'; const reference = resolveMeetingReference(item.source, p.meeting_id); return (
                        <TableRow key={item.id} className={`text-sm border-[var(--syn-line)] group select-none cursor-pointer ${inboxSelected.has(item.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => selRow(item.id)}>
                          <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-danger)]/40 text-[var(--syn-danger)]">Dublette</Badge></TableCell>
                          <TableCell className="text-left"><div className="font-medium">{p.title || '—'}</div><button onClick={e => { e.stopPropagation(); if (entityType) openSourceEntity(entityType, dup.id) }} className="text-xs text-left hover:text-[var(--syn-accent)]" style={{color:'var(--syn-text-faint)'}}>mögliche Dublette von: {dup?.title || '—'}</button><div className="text-[10px] mt-0.5" style={{color:'var(--syn-text-faint)'}}>{ownType}</div></TableCell>
                          <TableCell className="text-left"><span className="text-xs line-clamp-2">{dup?.reason || 'Fachlich ähnlicher bestehender Eintrag erkannt.'}</span></TableCell>
                          <TableCell className="text-xs" onClick={e => e.stopPropagation()}><SourceChip meeting={reference?.meeting || null} deleted={reference?.deleted} onClick={() => openMeetingReference(reference)} /></TableCell>
                          <TableCell><Badge className="text-[10px] bg-[var(--syn-warn-soft)] text-[var(--syn-warn)]">Prüfen</Badge></TableCell>
                          <FC item={item} />
                        </TableRow>
                      )})}
                      {filteredResolutions.length + filteredDuplicates.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm py-8" style={{color:'var(--syn-text-faint)'}}>Keine Statusänderungen oder Dubletten</TableCell></TableRow>}
                    </TableBody></Table></CardContent></Card>
                  </section>
                )}
              </div>
            )
}
