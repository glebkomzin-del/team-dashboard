import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  PRI_LABEL, PRI_RANK, PRI_STYLE, ST_LABEL, ST_STYLE, shortTopic,
  type Page, type ActionTab, type Meeting, type Todo, type Blocker,
} from '../lib/shared'

interface CommandCenterPageProps {
  meetings: Meeting[]
  todos: Todo[]
  blockers: Blocker[]
  chatInput: string
  setChatInput: (v: string) => void
  handleChat: (overrideText?: string) => void
  setPage: (p: Page) => void
  setActionTab: (t: ActionTab) => void
  setEditTodo: (t: Todo) => void
  setViewTodo: (t: Todo) => void
  setViewMeeting: (m: Meeting) => void
  setViewBlocker: (b: Blocker) => void
  handleQuickStatusToggle: (t: Todo) => void
}

export function CommandCenterPage({ meetings, todos, blockers, chatInput, setChatInput, handleChat, setPage, setActionTab, setEditTodo, setViewTodo, setViewMeeting, setViewBlocker, handleQuickStatusToggle }: CommandCenterPageProps) {
            const reviewQueue = meetings.slice(0, 10)
            const activeBlockersList = blockers.filter(b => b.status === 'active').slice(0, 10)
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
                    const cardStyle = { background: 'var(--syn-surface)', height: 562 }
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
                        <div data-testid="command-todos-list" className={listClass} style={{ minHeight: 0 }}>
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
                        <div data-testid="command-meetings-list" className={listClass} style={{ minHeight: 0 }}>
                          {reviewQueue.length === 0 && <div className="px-4 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine Meetings vorhanden.</div>}
                          {reviewQueue.map(m => (
                            <div key={m.id} className={itemClass} onClick={() => setViewMeeting(m)}>
                              <div className="text-sm font-medium truncate">{m.title}</div>
                              <div className={`${subClass} overflow-hidden`} style={{ color: 'var(--syn-text-faint)' }}>
                                <span>{m.date}</span>
                                <div data-testid="command-meeting-topic-pills" className="flex items-center gap-1 min-w-0 overflow-hidden">
                                  {m.topics.slice(0, 3).map((topic, i) => <Badge key={i} variant="outline" className="text-[9px] border-[var(--syn-line)] whitespace-nowrap w-fit shrink-0" style={{ padding: '1px 5px' }}>{shortTopic(topic)}</Badge>)}
                                  {m.topics.length > 3 && <span className="text-[10px] shrink-0">+{m.topics.length - 3}</span>}
                                </div>
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
                        <div data-testid="command-blockers-list" className={listClass} style={{ minHeight: 0 }}>
                          {activeBlockersList.length === 0 && <div className="px-4 py-4 text-sm" style={{ color: 'var(--syn-text-faint)' }}>Keine aktiven Blocker.</div>}
                          {activeBlockersList.map(b => (
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
                        <div data-testid="command-decisions-list" className={listClass} style={{ minHeight: 0 }}>
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
}
