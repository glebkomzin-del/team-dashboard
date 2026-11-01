import { EvidenceConfidence } from '@/features/working-memory/EvidenceConfidence'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { actionNames, decisionNames, dateLabel, getMemory, kindNames, numberLabel } from '@/features/working-memory/types'
import type { Action, DecisionAction, Knowledge, Observation, Snapshot, Source, Work } from '@/features/working-memory/types'
import { DecisionDialog } from '@/features/working-memory/DecisionDialog'
import { ProcessingPanel } from '@/features/working-memory/ProcessingPanel'
import type { DecisionTarget } from '@/features/working-memory/DecisionDialog'
import '@/features/working-memory/working-memory.css'

function Notes({ observation }: { observation: Observation }) {
  return <>
    <EvidenceConfidence observation={observation} />
    {observation.human_corrections?.map(c => <p className="wm-confirmed" key={c.id}>Von dir bestätigt: {c.reason}</p>)}
    {observation.human_decision && <p className="wm-confirmed">{decisionNames[observation.human_decision.action]}: {observation.human_decision.reason}</p>}
    {observation.action_uncertainty && !observation.human_decision && <p className="wm-note">Noch unklar: {observation.action_uncertainty}</p>}
    {observation.uncertainty && observation.uncertainty !== observation.action_uncertainty && <p className="wm-muted">Einordnung: {observation.uncertainty}</p>}
  </>
}
function Quotes({ quotes }: { quotes: string[] }) {
  return <>{quotes.map((quote, i) => <blockquote key={i}>{quote}</blockquote>)}</>
}
function WorkRow({ item, openSource, onEdit }: { item: Work; openSource: (id: string) => void; onEdit?: (target: DecisionTarget) => void }) {
  return <article className="wm-row">
    <div className="wm-row-head"><h3>{item.title}</h3><span className="wm-chip">{item.owner || 'Zuständigkeit offen'}</span></div>
    {item.due_text && <p className="wm-due">Frist: {item.due_text}{item.due_reference_date && <span className="wm-muted"> · genannt am {dateLabel(item.due_reference_date)}</span>}</p>}
    {item.original_time_expression && <p className="wm-due">{item.time_expression_role === 'event_time' ? 'Genannter Termin' : item.time_expression_role === 'data_reference' ? 'Datenstichtag' : 'Zeitangabe zur Klärung'}: {item.original_time_expression}</p>}
    {item.condition_text && <p className="wm-note" style={{ whiteSpace: 'pre-line' }}>Voraussetzungen: {item.condition_text}</p>}
    <p>{item.claim}</p><Notes observation={item} />
    {onEdit && <button type="button" className="wm-button" onClick={() => onEdit({ id: item.id, observation: item, work: item, action: 'correct' })}>Bearbeiten</button>}
    <details><summary>Belege und Verlauf · {numberLabel(item.history.length)} {item.history.length === 1 ? 'Eintrag' : 'Einträge'}</summary>
      <ol className="wm-history">{item.history.map((event, index) => <li key={`${event.source_version}-${index}`}>
        <p><strong>{event.human ? decisionNames[event.action as DecisionAction] : actionNames[event.action as Action]}</strong> · <time dateTime={event.event_date}>{dateLabel(event.event_date)}</time></p>
        <p className="wm-muted">{event.source_title}</p><p>{event.claim}</p><Quotes quotes={event.quotes} />
        {event.source_version && <button className="wm-link" type="button" onClick={() => openSource(event.source_version!)}>Vollständiges Original öffnen</button>}
      </li>)}</ol>
    </details>
  </article>
}
export function SourceDialog({ source, onClose }: { source: Source; onClose: () => void }) {
  const [returnFocus] = useState(() => document.activeElement instanceof HTMLElement ? document.activeElement : null)
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ attempt: number; transcript?: string; error?: string }>()
  useEffect(() => {
    const controller = new AbortController()
    getMemory<Source & { transcript: string }>(`/sources/${source.id}`, controller.signal)
      .then(data => setResult({ attempt, transcript: data.transcript }))
      .catch((error: Error) => { if (!controller.signal.aborted) setResult({ attempt, error: error.message }) })
    return () => controller.abort()
  }, [source.id, attempt])
  const current = result?.attempt === attempt ? result : undefined
  return <Dialog open onOpenChange={open => { if (!open) onClose() }}><DialogContent className="wm-dialog px-dialog" overlayClassName="wm-overlay px-overlay" closeLabel="Original schließen" onCloseAutoFocus={event => { event.preventDefault(); returnFocus?.focus() }}>
    <DialogHeader><DialogTitle>{source.title}</DialogTitle><DialogDescription>Original vom {dateLabel(source.event_date)} · unverändert gespeicherte Quelle</DialogDescription></DialogHeader>
    {!current && <p role="status">Original wird geladen…</p>}
    {current?.error && <div role="alert"><p>{current.error}</p><button type="button" className="wm-button" onClick={() => setAttempt(v => v + 1)}>Erneut versuchen</button></div>}
    {current?.transcript !== undefined && <pre tabIndex={0} aria-label="Vollständiges Originaltranskript">{current.transcript}</pre>}
  </DialogContent></Dialog>
}
export function WorkingMemoryPage() {
  const [date, setDate] = useState(() => {
    const value = new URLSearchParams(window.location.search).get('as_of') || ''
    const parsed = new Date(`${value}T12:00:00Z`)
    return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(parsed.valueOf()) && parsed.toISOString().startsWith(value) ? value : ''
  })
  const [query, setQuery] = useState('')
  const [matter, setMatter] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ text: string } | null>(null)
  const noticeRef = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (notice) noticeRef.current?.focus() }, [notice])
  const [decision, setDecision] = useState<DecisionTarget | null>(null)
  const requestKey = `${date}:${attempt}`
  const [result, setResult] = useState<{ key: string; data?: Snapshot; error?: string }>()
  useEffect(() => {
    const controller = new AbortController()
    getMemory<Snapshot>(`/review${date ? `?as_of=${encodeURIComponent(date)}` : ''}`, controller.signal)
      .then(data => {
        if (!['isolated-preview', 'staging', 'production'].includes(data.mode) || !Array.isArray(data.knowledge) || !Array.isArray(data.dates)) throw new Error('Die Antwort enthält keinen gültigen Arbeitsstand.')
        setResult({ key: requestKey, data })
      }).catch((error: Error) => { if (!controller.signal.aborted) setResult({ key: requestKey, error: error.message }) })
    return () => controller.abort()
  }, [date, requestKey])
  const current = result?.key === requestKey ? result : undefined
  const data = current?.data
  const activeKnowledge = (data?.knowledge || []).filter(k => k.data.knowledge_status !== 'rejected')
  const options = useMemo(() => [...new Map((data?.knowledge || []).filter(k => k.data.knowledge_status !== 'rejected').map(k => [k.matter_id, k.matter_title])).entries()].sort((a, b) => a[1].localeCompare(b[1], 'de')), [data])
  const matterByWork = useMemo(() => new Map((data?.knowledge || []).map(k => [k.id, k.matter_id])), [data])
  const needle = query.trim().toLocaleLowerCase('de')
  const matches = (o: Observation) => !needle || [o.title, o.claim, o.owner, o.matter, ...o.quotes].filter(Boolean).join(' ').toLocaleLowerCase('de').includes(needle)
  const knowledge = activeKnowledge.filter(k => (!matter || k.matter_id === matter) && matches(k.data))
  const work = (items: Work[]) => items.filter(item => (!matter || matterByWork.get(item.id) === matter) && matches(item))
  const groups = new Map<string, Knowledge[]>()
  for (const item of knowledge) groups.set(item.matter_id, [...(groups.get(item.matter_id) || []), item])
  const source = data?.sources.find(s => s.id === sourceId)
  const changes = (data?.changes || []).filter(c => (!matter || c.matter_id === matter) && matches(c.data))
  const jobs = (data?.jobs || []).filter(j => j.status !== 'applied')
  const pending = knowledge.filter(k => k.data.required_review && !k.data.human_decision)
  const canEdit = data?.can_edit === true && data.revision !== undefined && (!date || date === data.dates.at(-1))
  const onEdit = canEdit ? setDecision : undefined
  function refreshAfterDecision() { setDecision(null); setDate(''); setAttempt(value => value + 1); const url = new URL(window.location.href); url.searchParams.delete('as_of'); window.history.replaceState(null, '', url) }
  function workSection(title: string, items: Work[], empty: string) {
    return <section className="wm-panel"><h2>{title} <span className="wm-count">{numberLabel(items.length)}</span></h2>{items.length ? items.map(item => <WorkRow key={item.id} item={item} openSource={setSourceId} onEdit={onEdit} />) : <p className="wm-muted">{empty}</p>}</section>
  }
  return <div className="working-memory">
    <header className="wm-heading"><div><p className="wm-eyebrow"><span translate="no">Meeting OS</span> · Arbeitsgedächtnis</p><h1>Was steht an?</h1><p className="wm-muted">Eigene Arbeit, Zusagen anderer und der belegte Stand deiner Themen.</p></div>
      <button type="button" className="wm-button" onClick={() => setAttempt(v => v + 1)} disabled={!current}>Aktualisieren</button>
    </header>
    {notice && <p className="wm-confirmed" role="status" tabIndex={-1} ref={noticeRef}>{notice.text}</p>}
    {data?.mode !== 'production' && <p className="wm-preview">Arbeitsstand in Prüfung · Die Auswertung umfasst bisher {data ? numberLabel(data.sources.length) : '…'} {data?.sources.length === 1 ? 'Meeting' : 'Meetings'}{data?.archive_total !== undefined ? ` von ${numberLabel(data.archive_total)} vorhandenen Originalen bis zum gewählten Datum` : ''}. Aussagen über weitere Meetings sind hier noch nicht enthalten.</p>}
    <div className="wm-controls">
      <label>Wissensstand<select name="as_of" autoComplete="off" value={date || data?.as_of || ''} onChange={e => {
        setDate(e.target.value); setMatter(''); setSourceId(null)
        const url = new URL(window.location.href); url.searchParams.set('as_of', e.target.value)
        window.history.replaceState(null, '', url)
      }} disabled={!current?.data}>
        {date && !result?.data?.dates.includes(date) && <option value={date}>{dateLabel(date)}</option>}
        {(result?.data?.dates || []).map(d => <option value={d} key={d}>{dateLabel(d)}</option>)}
      </select></label>
      <label>Vorgang<select name="matter" autoComplete="off" value={matter} onChange={e => setMatter(e.target.value)} disabled={!data}><option value="">Alle Vorgänge</option>{options.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>
      <label className="wm-search">Im ausgewählten Stand suchen<input name="memory_search" type="search" autoComplete="off" value={query} onChange={e => setQuery(e.target.value)} placeholder="Thema, Person oder Originalbeleg…" /></label>
      {(query || matter) && <button type="button" className="wm-link" onClick={() => { setQuery(''); setMatter('') }}>Filter zurücksetzen</button>}
    </div>
    {!current && <div className="wm-panel" role="status">Belegter Stand wird geladen…</div>}
    {current?.error && <div className="wm-panel" role="alert"><h2>Stand konnte nicht geladen werden</h2><p>{current.error}</p><button className="wm-button" type="button" onClick={() => setAttempt(v => v + 1)}>Erneut versuchen</button></div>}
    {data && <>
      {data.can_edit && !canEdit && <p className="wm-note">Du siehst einen früheren Stand. <button type="button" className="wm-link" onClick={() => { setDate(''); const url = new URL(window.location.href); url.searchParams.delete('as_of'); window.history.replaceState(null, '', url) }}>Aktuellen Stand zum Bearbeiten öffnen</button></p>}
      <p className="wm-scope" aria-live="polite">{numberLabel(data.sources.length)} {data.sources.length === 1 ? 'Quelle' : 'Quellen'} bis {dateLabel(data.as_of)} · {numberLabel(groups.size)} {groups.size === 1 ? 'Vorgang' : 'Vorgänge'} und {numberLabel(knowledge.length)} {knowledge.length === 1 ? 'Aussage' : 'Aussagen'} in dieser Auswahl</p>
      {workSection('Für mich', work(data.personal), 'Keine offene persönliche Zusage in dieser Auswahl.')}
      {data.waiting_dependencies.length > 0 && workSection('Meine Zusagen mit Voraussetzung', work(data.waiting_dependencies), 'Keine wartende eigene Zusage in dieser Auswahl.')}
      {workSection('Zusagen anderer', work(data.waiting), 'Keine offene fremde Zusage in dieser Auswahl.')}
      <section className="wm-panel"><h2>Änderungen und Entscheidungen <span className="wm-muted">am {dateLabel(data.as_of)}</span></h2>
        {changes.length ? <ul className="wm-changes">{changes.map(c => <li key={c.id}><span className="wm-chip">{c.data.human_decision ? decisionNames[c.action as DecisionAction] : actionNames[c.action as Action]}</span><div><h3>{c.data.title}</h3><p className="wm-muted">{c.matter_title}</p><p>{c.data.claim}</p></div></li>)}</ul> : <p className="wm-muted">Keine Änderung oder Entscheidung in dieser Auswahl. Neue Informationen stehen bei den Vorgängen.</p>}
      </section>
      {pending.length > 0 && <section className="wm-panel"><h2>Von dir zu prüfen <span className="wm-count">{numberLabel(pending.length)}</span></h2><p className="wm-muted">Diese Vorschläge haben keine Aufgabe automatisch verändert.</p>{pending.map(k => <details className="wm-row" key={k.id}><summary>{k.data.title}</summary><p>{k.data.claim}</p><Notes observation={k.data} /><Quotes quotes={k.data.quotes} /><div className="wm-decision-actions"><button type="button" className="wm-link" onClick={() => setSourceId(k.source_version)}>Vollständiges Original öffnen</button>{canEdit && <>{<button type="button" className="wm-button" onClick={() => setDecision({ id: k.id, observation: k.data, action: (k.kind === 'commitment' || k.data.update_target) ? 'approve' : 'confirm_knowledge' })}>Prüfen und bestätigen</button>}<button type="button" className="wm-button" onClick={() => setDecision({ id: k.id, observation: k.data, action: 'reject' })}>Verwerfen</button></>}</div></details>)}</section>}
      <section className="wm-panel"><h2>Vorgänge und Wissen</h2><p className="wm-muted">Informationen, Voraussetzungen und Risiken bleiben beim Thema. Möglichkeiten sind keine Zusagen.</p>
        {groups.size ? [...groups].map(([id, rows]) => <details className="wm-row" key={id}><summary><span>{rows[0].matter_title}</span><span className="wm-muted"> · {numberLabel(rows.length)} {rows.length === 1 ? 'Aussage' : 'Aussagen'}</span></summary>
          {rows.map(k => <details className="wm-statement" key={k.id}><summary><span className="wm-chip">{kindNames[k.kind]}</span>{k.data.title}<span className="wm-muted"> · {dateLabel(k.event_date)}</span></summary>
            <p>{k.data.claim}</p><Notes observation={k.data} /><Quotes quotes={k.data.quotes} /><button type="button" className="wm-link" onClick={() => setSourceId(k.source_version)}>Vollständiges Original öffnen</button>
          </details>)}
        </details>) : <p className="wm-muted">Keine passenden Aussagen. Ändere die Auswahl oder setze die Filter zurück.</p>}
      </section>
      <section className="wm-panel"><details><summary>Erledigt · {numberLabel(work(data.completed).length)}</summary>{work(data.completed).map(item => <WorkRow key={item.id} item={item} openSource={setSourceId} onEdit={onEdit} />)}{!work(data.completed).length && <p className="wm-muted">Kein Abschluss in dieser Auswahl belegt.</p>}</details></section>
      {!!data.cancelled?.length && <section className="wm-panel"><details><summary>Nicht mehr erforderlich oder verworfen · {numberLabel(work(data.cancelled).length)}</summary>{work(data.cancelled).map(item => <WorkRow key={item.id} item={item} openSource={setSourceId} onEdit={onEdit} />)}</details></section>}
      <ProcessingPanel onChanged={refreshAfterDecision} />
      <footer className="wm-muted"><details><summary>Verarbeitungsstand · {jobs.length ? `${numberLabel(jobs.length)} noch nicht vollständig verarbeitet` : data.sources.length ? 'alle Quellen in diesem Stand verarbeitet' : 'keine Quellen in diesem Stand'}</summary><p>Fachliche Gesamtqualität noch in Prüfung. Quellenkorrekturen von dir haben Vorrang vor Modellurteilen.</p>{jobs.map(j => <p key={j.id}>{j.title}: {j.status} · {numberLabel(j.attempts)} Versuche{j.error && ` · ${j.error}`}</p>)}</details></footer>
      {source && <SourceDialog key={source.id} source={source} onClose={() => setSourceId(null)} />}
      {decision && data.revision !== undefined && <DecisionDialog target={decision} revision={data.revision} onClose={() => setDecision(null)} onSaved={() => { setNotice({ text: 'Deine Entscheidung wurde gespeichert.' }); refreshAfterDecision() }} onRefresh={refreshAfterDecision} />}
    </>}
  </div>
}
