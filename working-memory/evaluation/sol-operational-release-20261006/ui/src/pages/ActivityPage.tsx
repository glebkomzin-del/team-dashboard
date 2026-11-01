import { useMemo, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  ACTION_LABEL, TYPE_LABEL, ST_LABEL, ST_STYLE, FINAL_STATUSES,
  FILTER_BAR_CLASS, FILTER_INPUT_CLASS, FILTER_TRIGGER_CLASS,
  SH, TrashIcon, useSortState, sortBy, textMatch,
  type Activity,
} from '../lib/shared'

interface ActivityPageProps {
  activity: Activity[]
  globalSearch: string
  handleDeleteActivity: (a: Activity) => void
  deleteActivities: (ids: string[]) => Promise<void>
  openSourceEntity: (entityType: string, entityId: string) => void
  editSourceEntity: (entityType: string, entityId: string) => void
  setConfirmDelete: (v: { label: string; action: () => void } | null) => void
}

export function ActivityPage({ activity, globalSearch, handleDeleteActivity, deleteActivities, openSourceEntity, editSourceEntity, setConfirmDelete }: ActivityPageProps) {
  const [logSearch, setLogSearch] = useState('')
  const [logFilterType, setLogFilterType] = useState('all')
  const [logSelected, setLogSelected] = useState<Set<string>>(new Set())
  const logSort = useSortState()

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

  const handleBulkDeleteActivity = async () => {
    const ids = [...logSelected]
    setLogSelected(new Set())
    await deleteActivities(ids)
  }

  return (
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <div className="flex items-center gap-2 min-h-7">
                    <h2 className="text-base font-semibold">Protokoll</h2>
                    <button onClick={handleBulkDeleteActivity} className={`h-7 w-7 flex items-center justify-center rounded border border-[var(--syn-danger)]/40 hover:bg-[var(--syn-danger)]/10 transition-colors ${logSelected.size > 0 ? 'opacity-100' : 'opacity-0 pointer-events-none'}`} style={{ color: 'var(--syn-danger)' }} title={`${logSelected.size} löschen`} aria-hidden={logSelected.size === 0}><TrashIcon /></button>
                  </div>
                  <p className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Endgültige Statusänderungen: Erledigt, Beschlossen, Gelöst, Geschlossen</p>
                </div>
                <div className={FILTER_BAR_CLASS}>
                  <Input placeholder="Suche..." value={logSearch} onChange={e => setLogSearch(e.target.value)} className={FILTER_INPUT_CLASS} />
                  <Select value={logFilterType} onValueChange={setLogFilterType}><SelectTrigger className={FILTER_TRIGGER_CLASS}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Typen</SelectItem><SelectItem value="todo">Todos</SelectItem><SelectItem value="blocker">Blocker</SelectItem><SelectItem value="open_item">Offene Punkte</SelectItem><SelectItem value="meeting">Meetings</SelectItem><SelectItem value="decision">Entscheidung</SelectItem></SelectContent></Select>
                </div>
              </div>
              <Card className="glass-card border-[var(--syn-line)]"><CardContent className="p-0">
                {filteredLog.length > 0 ? (
                  <Table className="table-fixed w-full"><TableHeader><TableRow className="border-[var(--syn-line)]">
                    <SH label="Zeitpunkt" field="timestamp" sort={logSort} onSort={logSort.toggle} className="w-[160px]" />
                    <SH label="Typ" field="entityType" sort={logSort} onSort={logSort.toggle} className="w-[110px]" />
                    <SH label="Titel" field="entityTitle" sort={logSort} onSort={logSort.toggle} />
                    <SH label="Aktion" field="action" sort={logSort} onSort={logSort.toggle} className="w-[130px]" />
                    <TableHead className="w-[100px] text-xs text-center">Vorher</TableHead>
                    <TableHead className="w-[120px] text-xs text-center">Nachher</TableHead>
                    <TableHead className="w-[80px] text-xs text-center">Anpassen</TableHead>
                  </TableRow></TableHeader><TableBody>
                    {filteredLog.map(a => (
                      <TableRow key={a.id} className={`text-sm cursor-pointer select-none border-[var(--syn-line)] group ${logSelected.has(a.id) ? 'bg-[var(--syn-accent)]/5' : 'hover:bg-[var(--syn-hover)]'}`} onClick={() => setLogSelected(prev => { const n = new Set(prev); n.has(a.id) ? n.delete(a.id) : n.add(a.id); return n })}>
                        <TableCell className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>{new Date(a.timestamp).toLocaleString('de-DE')}</TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px] border-[var(--syn-line)]">{TYPE_LABEL[a.entityType] || a.entityType}</Badge></TableCell>
                        <TableCell className="text-left"><button onClick={e => { e.stopPropagation(); openSourceEntity(a.entityType, a.entityId) }} className="font-medium text-left hover:text-[var(--syn-accent)]">{a.entityTitle}</button></TableCell>
                        <TableCell className="text-xs">{a.action === 'status_changed' ? <span>Status geändert</span> : ACTION_LABEL[a.action] || a.action}</TableCell>
                        <TableCell>{a.action === 'status_changed' && a.oldValue ? <Badge className={`text-[9px] ${ST_STYLE[a.oldValue] || ''}`}>{ST_LABEL[a.oldValue] || a.oldValue}</Badge> : <span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>—</span>}</TableCell>
                        <TableCell>{a.action === 'status_changed' && a.newValue ? <Badge className={`text-[9px] ${ST_STYLE[a.newValue] || ''}`}>{ST_LABEL[a.newValue] || a.newValue}</Badge> : <span className="text-xs" style={{ color: 'var(--syn-text-faint)' }}>—</span>}</TableCell>
                        <TableCell onClick={e => e.stopPropagation()}><div className="flex gap-1.5 items-center justify-center"><button onClick={() => editSourceEntity(a.entityType, a.entityId)} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-accent)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✎'}</button><button onClick={() => setConfirmDelete({ label: `Protokoll-Eintrag: ${a.entityTitle}`, action: () => handleDeleteActivity(a) })} className="text-base w-7 h-7 flex items-center justify-center rounded hover:bg-[var(--syn-hover)] hover:text-[var(--syn-danger)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>{'✕'}</button><input type="checkbox" className={`w-3.5 h-3.5 cursor-pointer transition-opacity block ${logSelected.has(a.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'}`} style={{ accentColor: 'var(--syn-accent)' }} checked={logSelected.has(a.id)} onChange={() => setLogSelected(prev => { const n = new Set(prev); n.has(a.id) ? n.delete(a.id) : n.add(a.id); return n })} /></div></TableCell>
                      </TableRow>
                    ))}
                  </TableBody></Table>
                ) : <div className="py-12 text-center text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine abgeschlossenen Einträge im Protokoll.</div>}
              </CardContent></Card>
              {filteredLog.length > 0 && <p className="text-xs text-center" style={{ color: 'var(--syn-text-faint)' }}>{filteredLog.length} Einträge</p>}
            </div>
  )
}
