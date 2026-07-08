import { useMemo } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  PRI_LABEL, PRI_STYLE, ST_LABEL, ST_STYLE, CAT_ICON, textMatch,
  type Todo, type Blocker, type OpenItem, type Meeting,
} from '../lib/shared'

interface TextSearchPageProps {
  globalSearch: string
  meetings: Meeting[]
  todos: Todo[]
  blockers: Blocker[]
  openItems: OpenItem[]
  setViewMeeting: (m: Meeting) => void
  setViewTodo: (t: Todo) => void
  setViewBlocker: (b: Blocker) => void
  setViewOpen: (o: OpenItem) => void
}

export function TextSearchPage({ globalSearch, meetings, todos, blockers, openItems, setViewMeeting, setViewTodo, setViewBlocker, setViewOpen }: TextSearchPageProps) {
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

  return (
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
  )
}
