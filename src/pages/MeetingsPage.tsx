import { useMemo, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import type { DateRange } from 'react-day-picker'
import {
  MEETING_DATE_PRESETS, type DatePresetKey, presetToRange, rangeToPresetKey,
  parseLocalDate, toLocalDateValue, formatShortDate,
  FILTER_BAR_CLASS, FILTER_INPUT_CLASS, TABLE_COL,
  CompactRangeCalendar, SH, TrashIcon, useSortState, sortBy, textMatch, shortTopic,
  type Meeting,
} from '../lib/shared'
import type { TableCounts } from '../supabase'

interface MeetingsPageProps {
  meetings: Meeting[]
  tableCounts: TableCounts
  memberNames: string[]
  globalSearch: string
  openMeetingEditor: (m: Meeting) => void
  handleDeleteMeeting: (m: Meeting) => void
  deleteMeetings: (ids: string[]) => Promise<void>
  setViewMeeting: (m: Meeting) => void
  setConfirmDelete: (v: { label: string; action: () => void } | null) => void
}

export function MeetingsPage({ meetings, tableCounts, memberNames, globalSearch, openMeetingEditor, handleDeleteMeeting, deleteMeetings, setViewMeeting, setConfirmDelete }: MeetingsPageProps) {
  const [noteSearch, setNoteSearch] = useState('')
  const [noteFilterParticipant, setNoteFilterParticipant] = useState<string[]>([])
  const [noteFilterDateFrom, setNoteFilterDateFrom] = useState('')
  const [noteFilterDateTo, setNoteFilterDateTo] = useState('')
  const [noteDateFilterOpen, setNoteDateFilterOpen] = useState(false)
  const [noteDateDraft, setNoteDateDraft] = useState<DateRange | undefined>()
  // 'list' = Preset-Auswahl, 'custom' = Kalender für benutzerdefinierten Zeitraum
  const [noteDateFilterView, setNoteDateFilterView] = useState<'list' | 'custom'>('list')
  const [meetingSelected, setMeetingSelected] = useState<Set<string>>(new Set())
  const noteSort = useSortState()

  const filteredNotes = useMemo(() => {
    let r = meetings.filter(m => textMatch(m, noteSearch || globalSearch))
    if (noteFilterParticipant.length > 0) r = r.filter(m => m.participants.some(p => noteFilterParticipant.includes(p)))
    if (noteFilterDateFrom) r = r.filter(m => m.date >= noteFilterDateFrom)
    if (noteFilterDateTo) r = r.filter(m => m.date <= noteFilterDateTo)
    return noteSort.col ? sortBy(r, noteSort.col, noteSort.dir) : r.sort((a, b) => b.date.localeCompare(a.date))
  }, [meetings, noteSearch, globalSearch, noteFilterParticipant, noteFilterDateFrom, noteFilterDateTo, noteSort.col, noteSort.dir])

  const handleBulkDeleteMeetings = async () => {
    const ids = [...meetingSelected]
    setMeetingSelected(new Set())
    await deleteMeetings(ids)
  }

  return (
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold">Meetings <span data-testid="meetings-db-count" className="font-normal" style={{ color: 'var(--syn-text-muted)' }}>({tableCounts.meetings})</span></h2>
                  {meetingSelected.size > 0 && <button onClick={handleBulkDeleteMeetings} className="h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors" style={{ color: 'var(--syn-danger)' }} title={`${meetingSelected.size} löschen`}><TrashIcon /></button>}
                </div>
                <div className={FILTER_BAR_CLASS}>
                  <Input placeholder="Suche..." value={noteSearch} onChange={e => setNoteSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                  <MultiSelectFilter selected={noteFilterParticipant} onChange={setNoteFilterParticipant} options={memberNames} allLabel="Alle Teilnehmer" testId="meeting-participant-filter" triggerWidth="w-[160px]" />
                  {(() => {
                    const activePreset = rangeToPresetKey(noteFilterDateFrom, noteFilterDateTo)
                    const hasFilter = Boolean(noteFilterDateFrom || noteFilterDateTo)
                    // Kompaktes Label: bei benutzerdefinierten Zeiträumen im gleichen Jahr ohne Jahreszahl
                    const compactDate = (v: string) => {
                      const d = parseLocalDate(v)!
                      return d.getFullYear() === new Date().getFullYear()
                        ? d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
                        : formatShortDate(d)
                    }
                    const triggerLabel = activePreset
                      ? MEETING_DATE_PRESETS.find(p => p.key === activePreset)!.label
                      : noteFilterDateFrom && noteFilterDateTo
                        ? `${compactDate(noteFilterDateFrom)} – ${compactDate(noteFilterDateTo)}`
                        : noteFilterDateFrom ? `Ab ${compactDate(noteFilterDateFrom)}`
                          : noteFilterDateTo ? `Bis ${compactDate(noteFilterDateTo)}`
                            : 'Zeitraum'
                    const resetFilter = () => { setNoteFilterDateFrom(''); setNoteFilterDateTo(''); setNoteDateDraft(undefined) }
                    const applyPreset = (key: DatePresetKey) => {
                      const r = presetToRange(key)
                      setNoteFilterDateFrom(toLocalDateValue(r.from)); setNoteFilterDateTo(toLocalDateValue(r.to))
                      setNoteDateFilterOpen(false)
                    }
                    return (
                  <Popover open={noteDateFilterOpen} onOpenChange={open => {
                    setNoteDateFilterOpen(open)
                    if (open) { setNoteDateFilterView('list'); setNoteDateDraft(noteFilterDateFrom || noteFilterDateTo ? { from: parseLocalDate(noteFilterDateFrom), to: parseLocalDate(noteFilterDateTo) } : undefined) }
                  }}>
                    <PopoverTrigger asChild>
                      <button data-testid="meeting-date-filter" className="h-8 w-[160px] rounded-md border border-[var(--syn-line)] bg-[var(--syn-surface-2)] px-3 text-xs flex items-center gap-2 hover:bg-[var(--syn-hover)] transition-colors">
                        {hasFilter && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--syn-accent)]" />}
                        <span className="truncate text-left flex-1">{triggerLabel}</span>
                        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 shrink-0 opacity-50" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
                      </button>
                    </PopoverTrigger>
                    <PopoverContent align="end" className="w-auto p-0 overflow-hidden border-[var(--syn-line)] bg-[var(--syn-bg)]">
                      {noteDateFilterView === 'list' ? (
                        <div className="w-[188px] p-1.5 space-y-0.5">
                          {MEETING_DATE_PRESETS.map(p => (
                            <button key={p.key} onClick={() => applyPreset(p.key)} className={`w-full text-left text-xs px-2.5 py-1.5 rounded transition-colors ${activePreset === p.key ? 'bg-[var(--syn-accent)] text-white' : 'hover:bg-[var(--syn-hover)]'}`}>{p.label}</button>
                          ))}
                          <div className="h-px my-1 bg-[var(--syn-line)]" />
                          <button onClick={() => { setNoteDateFilterView('custom'); setNoteDateDraft(noteFilterDateFrom || noteFilterDateTo ? { from: parseLocalDate(noteFilterDateFrom), to: parseLocalDate(noteFilterDateTo) } : undefined) }} className="w-full text-left text-xs px-2.5 py-1.5 rounded hover:bg-[var(--syn-hover)] flex items-center justify-between" style={{ color: 'var(--syn-text-muted)' }}>
                            <span>Benutzerdefiniert</span>
                            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="m9 18 6-6-6-6" /></svg>
                          </button>
                          {hasFilter && !activePreset && (
                            <div className="text-[10px] px-2.5 pt-1 truncate" style={{ color: 'var(--syn-text-faint)' }}>
                              {noteFilterDateFrom && noteFilterDateTo ? `${formatShortDate(parseLocalDate(noteFilterDateFrom)!)} – ${formatShortDate(parseLocalDate(noteFilterDateTo)!)}` : noteFilterDateFrom ? `Ab ${formatShortDate(parseLocalDate(noteFilterDateFrom)!)}` : `Bis ${formatShortDate(parseLocalDate(noteFilterDateTo)!)}`}
                            </div>
                          )}
                          {hasFilter && (
                            <button onClick={() => { resetFilter(); setNoteDateFilterOpen(false) }} className="w-full text-left text-xs px-2.5 py-1.5 rounded hover:bg-[var(--syn-hover)]" style={{ color: 'var(--syn-danger)' }}>Alle Zeiträume</button>
                          )}
                        </div>
                      ) : (
                        <div className="w-auto">
                          <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--syn-line)]">
                            <button onClick={() => setNoteDateFilterView('list')} className="flex items-center gap-1 text-xs hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-muted)' }}>
                              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6" /></svg>
                              Zurück
                            </button>
                            <span className="text-xs font-medium ml-auto">Zeitraum wählen</span>
                          </div>
                          <CompactRangeCalendar
                            mode="range"
                            selected={noteDateDraft}
                            onSelect={setNoteDateDraft}
                            defaultMonth={noteDateDraft?.from}
                          />
                          <div className="flex items-center justify-between gap-4 px-4 py-2 border-t border-[var(--syn-line)]">
                            <span className="text-xs text-[var(--syn-text-muted)] truncate">
                              {noteDateDraft?.from ? `${formatShortDate(noteDateDraft.from)}${noteDateDraft.to ? ` – ${formatShortDate(noteDateDraft.to)}` : ''}` : 'Alle Meetings'}
                            </span>
                            <Button size="sm" className="h-8 bg-[var(--syn-accent)] text-white" onClick={() => { setNoteFilterDateFrom(toLocalDateValue(noteDateDraft?.from)); setNoteFilterDateTo(toLocalDateValue(noteDateDraft?.to)); setNoteDateFilterOpen(false) }}>Übernehmen</Button>
                          </div>
                        </div>
                      )}
                    </PopoverContent>
                  </Popover>
                    )
                  })()}
                </div>
              </div>
              <Card className="glass-card border-[var(--syn-line)]"><CardContent data-testid="meetings-table-scroll" className="p-0 max-h-[calc(100vh-152px)] overflow-y-auto"><Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                <SH label="Datum" field="date" sort={noteSort} onSort={noteSort.toggle} className={TABLE_COL.created} />
                <SH label="Titel" field="title" sort={noteSort} onSort={noteSort.toggle} />
                <TableHead className={`${TABLE_COL.participants} text-xs text-center`}>Teilnehmer</TableHead>
                <TableHead className={`${TABLE_COL.topics} text-xs text-center`}>Themen</TableHead>
                <TableHead className={`${TABLE_COL.actions} text-xs text-center`}>Anpassen</TableHead>
              </TableRow></TableHeader><TableBody>
                {filteredNotes.map(m => (
                  <TableRow key={m.id} className={`text-sm cursor-pointer select-none border-[var(--syn-line)] group ${meetingSelected.has(m.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => setMeetingSelected(prev => { const n = new Set(prev); n.has(m.id) ? n.delete(m.id) : n.add(m.id); return n })}>
                    <TableCell className="text-xs font-medium" style={{ color: 'var(--syn-text-muted)' }}>{m.date}</TableCell>
                    <TableCell className="text-left font-medium"><button onClick={e => { e.stopPropagation(); setViewMeeting(m) }} className="text-left hover:text-[var(--syn-accent)] leading-snug">{m.title}</button></TableCell>
                    <TableCell><div className="flex flex-col gap-0.5">{m.participants.slice(0, 5).map((p, i) => <span key={i} className="text-[10px] rounded truncate block" style={{ background: 'var(--syn-surface-3)', color: 'var(--syn-text-muted)', padding: '1px 6px', maxWidth: '164px' }}>{p}</span>)}{m.participants.length > 5 && <span className="text-[10px] font-medium" style={{ color: 'var(--syn-text-faint)' }}>+{m.participants.length - 5}</span>}</div></TableCell>
                    <TableCell><div className="flex flex-col gap-0.5">{m.topics.slice(0, 5).map((t, i) => <Badge key={i} variant="outline" className="text-[9px] border-[var(--syn-line)] whitespace-nowrap w-fit" style={{ padding: '1px 5px' }}>{shortTopic(t)}</Badge>)}{m.topics.length > 5 && <span className="text-[10px] font-medium" style={{ color: 'var(--syn-text-faint)' }}>+{m.topics.length - 5}</span>}</div></TableCell>
                    <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center"><button onClick={() => openMeetingEditor(m)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => setConfirmDelete({ label: m.title, action: () => handleDeleteMeeting(m) })} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button><input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${meetingSelected.has(m.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={meetingSelected.has(m.id)} onClick={e => e.stopPropagation()} onChange={() => setMeetingSelected(prev => { const n = new Set(prev); n.has(m.id) ? n.delete(m.id) : n.add(m.id); return n })} /></div></TableCell>
                  </TableRow>
                ))}
                {filteredNotes.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-sm py-8" style={{ color: 'var(--syn-text-faint)' }}>Keine Meetings</TableCell></TableRow>}
              </TableBody></Table></CardContent></Card>
            </div>
  )
}
