import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  ST_LABEL, TYPE_LABEL, formatCost, formatTokens, renderMarkdown,
  type Meeting, type ChatMessage,
} from '../lib/shared'
import type { DbMemoryMetric } from '../supabase'

interface KiPageProps {
  chatMessages: ChatMessage[]
  chatInput: string
  setChatInput: (v: string) => void
  chatLoading: boolean
  sendChat: (overrideText?: string) => void
  memoryMetrics: DbMemoryMetric[]
  getMeeting: (id: string | null) => Meeting | undefined
  openSourceEntity: (entityType: string, entityId: string) => void
  setViewMeeting: (m: Meeting) => void
}

export function KiPage({ chatMessages, chatInput, setChatInput, chatLoading, sendChat, memoryMetrics, getMeeting, openSourceEntity, setViewMeeting }: KiPageProps) {
  const chatEndRef = useRef<HTMLDivElement>(null)
  const chatScrollRef = useRef<HTMLDivElement>(null)
  const [chatAutoFollow, setChatAutoFollow] = useState(true)
  const [showChatScrollButton, setShowChatScrollButton] = useState(false)
  const [expandedChatSources, setExpandedChatSources] = useState<Set<number>>(new Set())
  // KI-Kosten-Tracker
  const [metricsMonth, setMetricsMonth] = useState<string>(() => new Date().toISOString().slice(0, 7))
  const [metricsOpen, setMetricsOpen] = useState(false)

  // Monats-Aggregation der KI-Kosten aus memory_metrics
  const MONTH_LABELS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
  const metricsByMonth = useMemo(() => {
    const map = new Map<string, { count: number; input: number; output: number; cost: number }>()
    for (const m of memoryMetrics) {
      const month = (m.created_at || '').slice(0, 7)
      if (!month) continue
      const cur = map.get(month) || { count: 0, input: 0, output: 0, cost: 0 }
      cur.count += 1
      cur.input += Number(m.uncached_input_tokens || 0) + Number(m.cache_write_tokens || 0) + Number(m.cache_read_tokens || 0)
      cur.output += Number(m.output_tokens || 0)
      cur.cost += Number(m.cost_usd || 0)
      map.set(month, cur)
    }
    return map
  }, [memoryMetrics])
  const availableMonths = useMemo(() => Array.from(metricsByMonth.keys()).sort().reverse(), [metricsByMonth])
  const currentMonthStats = metricsByMonth.get(metricsMonth)

  const scrollChatToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    chatEndRef.current?.scrollIntoView({ behavior })
  }, [])
  const handleChatScroll = useCallback(() => {
    const el = chatScrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    setChatAutoFollow(atBottom)
    setShowChatScrollButton(!atBottom)
  }, [])
  useEffect(() => {
    if (chatAutoFollow) scrollChatToBottom(chatLoading ? 'auto' : 'smooth')
  }, [chatMessages, chatLoading, chatAutoFollow, scrollChatToBottom])
  // Beim Einstieg auf die Seite zuverlässig nach unten scrollen
  // (zweistufig, weil die Chat-Historie asynchron aus localStorage kommt).
  useEffect(() => {
    const t1 = setTimeout(() => scrollChatToBottom('auto'), 50)
    const t2 = setTimeout(() => scrollChatToBottom('auto'), 300)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [scrollChatToBottom])

  const handleChat = (overrideText?: string) => {
    setChatAutoFollow(true)
    setShowChatScrollButton(false)
    sendChat(overrideText)
  }

  return (
            <div className="flex flex-col h-[calc(100vh-104px)]">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">KI-Assistent</h2><p className="text-xs" style={{ color: 'var(--syn-text-muted)' }}>Memory-Antworten aus Meeting-Zusammenfassungen mit verlinkten Quellen.</p>
                </div>
                {availableMonths.length > 0 && (
                  <Popover open={metricsOpen} onOpenChange={setMetricsOpen}>
                    <PopoverTrigger asChild>
                      <button className="h-8 px-3 rounded-md border border-[var(--syn-line)] bg-[var(--syn-surface-2)] text-xs flex items-center gap-2 hover:bg-[var(--syn-hover)] transition-colors">
                        <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--syn-accent)' }} />
                        <span className="truncate">{MONTH_LABELS[Number(metricsMonth.slice(5, 7)) - 1]?.slice(0, 3) || metricsMonth}: {currentMonthStats ? formatCost(currentMonthStats.cost) : '$0.00'}</span>
                        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0 opacity-50" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
                      </button>
                    </PopoverTrigger>
                    <PopoverContent align="end" className="w-[240px] p-2 space-y-2 border-[var(--syn-line)] bg-[var(--syn-bg)]">
                      <div className="flex items-center gap-1.5">
                        <select value={metricsMonth} onChange={e => setMetricsMonth(e.target.value)} className="h-7 flex-1 rounded border border-[var(--syn-line)] bg-[var(--syn-surface-2)] text-xs px-2">
                          {availableMonths.map(mo => <option key={mo} value={mo}>{MONTH_LABELS[Number(mo.slice(5, 7)) - 1]} {mo.slice(0, 4)}</option>)}
                        </select>
                      </div>
                      {currentMonthStats ? (
                        <div className="space-y-1 px-1 py-1 text-xs">
                          <div className="flex justify-between"><span style={{ color: 'var(--syn-text-muted)' }}>Fragen</span><span className="font-medium">{currentMonthStats.count}</span></div>
                          <div className="flex justify-between"><span style={{ color: 'var(--syn-text-muted)' }}>Input-Token</span><span className="font-medium">{formatTokens(currentMonthStats.input)}</span></div>
                          <div className="flex justify-between"><span style={{ color: 'var(--syn-text-muted)' }}>Output-Token</span><span className="font-medium">{formatTokens(currentMonthStats.output)}</span></div>
                          <div className="h-px my-1" style={{ background: 'var(--syn-line)' }} />
                          <div className="flex justify-between"><span style={{ color: 'var(--syn-text-muted)' }}>Gesamtkosten</span><span className="font-semibold" style={{ color: 'var(--syn-accent)' }}>{formatCost(currentMonthStats.cost)}</span></div>
                        </div>
                      ) : (
                        <p className="text-xs text-center py-2" style={{ color: 'var(--syn-text-faint)' }}>Keine Daten für diesen Monat</p>
                      )}
                    </PopoverContent>
                  </Popover>
                )}
              </div>
              <Card className="glass-card border-[var(--syn-line)] flex-1 flex flex-col min-h-0">
                <CardContent className="flex-1 flex flex-col p-4 min-h-0">
                  <div className="relative flex-1 min-h-0 mb-4">
                    <div ref={chatScrollRef} onScroll={handleChatScroll} className="h-full overflow-y-auto pr-2">
                      <div className="space-y-4">
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
                        if (msg.role === 'assistant' && !msg.text) return null
                        const ts = msg.timestamp ? new Date(msg.timestamp) : null
                        const timeStr = ts ? `${String(ts.getDate()).padStart(2,'0')}.${String(ts.getMonth()+1).padStart(2,'0')}.${ts.getFullYear()} ${String(ts.getHours()).padStart(2,'0')}:${String(ts.getMinutes()).padStart(2,'0')}` : null
                        return (
                        <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                          <div className={`max-w-[75%] rounded-xl px-4 py-3 ${msg.role === 'user' ? 'bg-[var(--syn-accent)] text-white' : ''}`} style={msg.role === 'assistant' ? { background: 'var(--syn-surface-2)', color: 'var(--syn-text)' } : {}}>
                            {timeStr && <div className="text-[10px] mb-1" style={{ color: msg.role === 'user' ? 'rgba(255,255,255,.6)' : 'var(--syn-text-faint)' }}>{timeStr}</div>}
                            {msg.role === 'assistant' && msg.scalingNotice && (
                              <div data-testid="scaling-notice-banner" className="mb-3 rounded-lg border px-3 py-2 text-xs leading-relaxed" style={{ borderColor: 'var(--syn-warn)', background: 'var(--syn-warn-soft)', color: 'var(--syn-text)' }}>
                                <span className="font-semibold">Systemhinweis:</span> {msg.scalingNotice}
                              </div>
                            )}
                            {msg.role === 'assistant' ? renderMarkdown(msg.text) : <p className="text-sm whitespace-pre-wrap">{msg.text}</p>}
                            {msg.role === 'assistant' && msg.tokens && (
                              <div className="mt-2 flex items-center gap-2 text-[10px]" style={{ color: 'var(--syn-text-faint)' }}>
                                <span className="truncate">{msg.model?.replace('claude-', '').replace('-20250514', '') || 'KI'}</span>
                                <span>·</span>
                                <span title="Input-Token (inkl. Cache)">↗ {formatTokens(msg.tokens.input)}</span>
                                <span>·</span>
                                <span title="Output-Token">↘ {formatTokens(msg.tokens.output)}</span>
                                {typeof msg.costUsd === 'number' && msg.costUsd > 0 && (<><span>·</span><span title="Kosten">{formatCost(msg.costUsd)}</span></>)}
                              </div>
                            )}
                            {(() => {
                              const sourceCount = (msg.sources?.length || 0) + (msg.chunkSources?.length || 0) + (msg.itemSources?.length || 0)
                              if (sourceCount === 0) return null
                              const expanded = expandedChatSources.has(i)
                              return (
                              <div className="mt-3 pt-2 border-t border-[var(--syn-line)] space-y-1">
                                <button data-testid="chat-sources-toggle" type="button" aria-expanded={expanded} onClick={() => setExpandedChatSources(previous => { const next = new Set(previous); next.has(i) ? next.delete(i) : next.add(i); return next })} className="w-full flex items-center justify-between rounded px-1 py-1 text-[10px] uppercase tracking-wide hover:bg-[var(--syn-hover)] transition-colors" style={{ color: 'var(--syn-text-faint)' }}>
                                  <span>Belege ({sourceCount})</span><span aria-hidden="true">{expanded ? '▴' : '▾'}</span>
                                </button>
                                {expanded && msg.sources?.map((source) => {
                                  const meeting = getMeeting(source.id)
                                  return (
                                    <button key={source.id} disabled={!meeting} onClick={() => meeting && setViewMeeting(meeting)} className="w-full text-left text-xs flex items-center gap-2 rounded px-2 py-1 transition-colors enabled:hover:bg-[var(--syn-hover)] enabled:hover:text-[var(--syn-accent)] disabled:opacity-50" style={{ color: 'var(--syn-text-muted)' }}>
                                      <span className="shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{source.date}</span>
                                      <span className="truncate">{source.title}</span>
                                    </button>
                                  )
                                })}
                                {expanded && msg.chunkSources?.map((chunk) => {
                                  const meeting = getMeeting(chunk.meeting_id)
                                  return (
                                    <button key={chunk.id} disabled={!meeting} onClick={() => meeting && setViewMeeting(meeting)} className="w-full text-left text-xs flex items-start gap-2 rounded px-2 py-1 transition-colors enabled:hover:bg-[var(--syn-hover)] disabled:opacity-50" style={{ color: 'var(--syn-text-muted)' }} title="Transkript-Beleg — öffnet das Meeting">
                                      <Badge variant="outline" className="text-[9px] shrink-0 border-[var(--syn-line)]">Transkript</Badge>
                                      <span className="shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{chunk.meeting_date}{chunk.speaker ? ` · ${chunk.speaker}` : ''}</span>
                                      <span className="truncate italic">„{chunk.excerpt.slice(0, 90)}…“</span>
                                    </button>
                                  )
                                })}
                                {expanded && msg.itemSources?.map((item) => {
                                  const meeting = item.meeting_id ? getMeeting(item.meeting_id) : undefined
                                  const openItem = () => {
                                    if (item.entity_type === 'todo' || item.entity_type === 'blocker' || item.entity_type === 'open_item') {
                                      openSourceEntity(item.entity_type, item.id)
                                    } else if (meeting) setViewMeeting(meeting)
                                  }
                                  return (
                                    <button key={item.id} onClick={openItem} className="w-full text-left text-xs flex items-center gap-2 rounded px-2 py-1 transition-colors hover:bg-[var(--syn-hover)]" style={{ color: 'var(--syn-text-muted)' }}>
                                      <Badge variant="outline" className="text-[9px] shrink-0 border-[var(--syn-line)]">{TYPE_LABEL[item.entity_type] || item.entity_type}</Badge>
                                      <span className="shrink-0" style={{ color: 'var(--syn-text-faint)' }}>{item.meeting_date || item.created_at?.slice(0, 10) || ''}</span>
                                      <span className="truncate">{item.title}</span>
                                      {item.status && <span className="text-[10px] shrink-0" style={{ color: 'var(--syn-text-faint)' }}>({ST_LABEL[item.status] || item.status})</span>}
                                    </button>
                                  )
                                })}
                              </div>
                              )
                            })()}
                          </div>
                        </div>
                      )})}
                      {chatLoading && (!chatMessages.length || chatMessages[chatMessages.length - 1].role !== 'assistant' || !chatMessages[chatMessages.length - 1].text) && <div className="flex justify-start"><div className="rounded-xl px-4 py-3 text-sm" style={{ background: 'var(--syn-surface-2)', color: 'var(--syn-text-muted)' }}>Denkt nach...</div></div>}
                      <div ref={chatEndRef} />
                      </div>
                    </div>
                    {showChatScrollButton && (
                      <Button data-testid="chat-scroll-bottom" size="sm" className="absolute bottom-3 right-4 h-8 rounded-full bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white shadow-lg text-xs" onClick={() => { setChatAutoFollow(true); setShowChatScrollButton(false); scrollChatToBottom('smooth') }}>
                        ↓ Zum Ende
                      </Button>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Input placeholder="Frage stellen..." value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleChat()} className="flex-1 bg-[var(--syn-surface-2)] border-[var(--syn-line)]" disabled={chatLoading} />
                    <Button onClick={() => handleChat()} disabled={chatLoading || !chatInput.trim()} className="bg-[var(--syn-accent)] hover:bg-[var(--syn-accent-strong)] text-white">Senden</Button>
                  </div>
                </CardContent>
              </Card>
            </div>
  )
}
