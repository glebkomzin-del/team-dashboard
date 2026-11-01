import { useEffect, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { dateLabel, getMemory, numberLabel, postMemory } from '@/features/working-memory/types'
import '@/features/working-memory/working-memory.css'
import { navigate, useRoute } from '@/features/working-memory/planning'

interface ArchiveSource { id: string; source_id: string; title: string; summary_title?: string | null; display_title_method?: string | null; summary_available?: boolean; event_date: string; observed_at: string; content_hash: string; characters: number; match?: { start: number; end: number; text: string } }
interface Catalogue { sources: ArchiveSource[]; total: number; limit: number; offset: number; as_of: string }
interface ArchivedSummary {
  id: string; origin: string; legacy_status?: string; ai_summary: string; executive_summary: string
  topics: (string | { name: string; summary: string; sequence?: number })[]; key_decisions: string[]; participants: string[]
  provenance?: { content_conflict?: boolean }
}
interface Original extends ArchiveSource { transcript?: string; full_export?: string; export_hash: string; summaries?: ArchivedSummary[]; deleted?: boolean; redaction_id?: string }
interface DeletionStatus { deletion_id: string; source_id: string; state: 'prepared' | 'purging' | 'verified' | 'processing'; requested_at?: string; completed_at?: string }
function SummaryText({ summary }: { summary: ArchivedSummary }) {
  return <div className="wm-archive-summary">
    {summary.provenance?.content_conflict && <p className="wm-summary-warning">In der alten App war hier ein anderes Transkript hinterlegt. Die Zusammenfassung wurde erhalten und am zugehörigen Drive-Original zugeordnet.</p>}
    {summary.legacy_status === 'pending' && <p className="wm-muted">Diese Notiz war in der bisherigen Inbox noch nicht bestätigt.</p>}
    {summary.executive_summary && summary.executive_summary !== summary.ai_summary && <p className="wm-summary-text">{summary.executive_summary}</p>}
    {summary.ai_summary && <p className="wm-summary-text">{summary.ai_summary}</p>}
    {summary.topics.length > 0 && <section aria-label="Besprochene Themen"><h3>Themen</h3>{summary.topics.map((topic, index) => typeof topic === 'string'
      ? <p key={index}>{topic}</p>
      : <details key={index}><summary>{topic.name}</summary><p className="wm-summary-text">{topic.summary}</p></details>)}</section>}
    {summary.key_decisions.length > 0 && <details><summary>Entscheidungen in der Notiz</summary><ul>{summary.key_decisions.map((text, index) => <li key={index}>{text}</li>)}</ul></details>}
    {summary.participants.length > 0 && <p className="wm-muted">Teilnehmende: {summary.participants.join(', ')}</p>}
  </div>
}
function OriginalDialog({ source, close }: { source: ArchiveSource; close: () => void }) {
  const [focus] = useState(() => document.activeElement instanceof HTMLElement ? document.activeElement : null)
  const [attempt, retry] = useState(0)
  const [exportView, setExportView] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteAccepted, setDeleteAccepted] = useState(false)
  const [deletion, setDeletion] = useState<DeletionStatus | null>(null)
  const [deletionAvailable, setDeletionAvailable] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const deletionRequest = useRef<{ deletion_id: string; source_id: string } | null>(null)
  const location = useRoute()
  const view = location.params.get('meeting_view') || 'summary'
  function setView(value: string) { const params = new URLSearchParams(location.params); params.set('meeting_view', value); navigate('archiv', params, true) }
  const [result, setResult] = useState<{ attempt: number; data?: Original; error?: string }>()
  useEffect(() => {
    const controller = new AbortController()
    getMemory<Original>(`/archive/${source.id}`, controller.signal).then(data => {
      if (data.deleted && data.redaction_id) setDeletion({ deletion_id: data.redaction_id, source_id: data.source_id, state: 'verified' })
      setResult({ attempt, data })
    })
      .catch((error: Error) => { if (!controller.signal.aborted) setResult({ attempt, error: error.message }) })
    return () => controller.abort()
  }, [source.id, attempt])
  const current = result?.attempt === attempt ? result : undefined
  const sourceId = current?.data?.source_id || source.source_id
  useEffect(() => {
    if (!sourceId) return
    const controller = new AbortController()
    getMemory<{ deletion: DeletionStatus | null }>(`/source-deletions?source_id=${encodeURIComponent(sourceId)}`, controller.signal)
      .then(value => { setDeletionAvailable(true);if (value.deletion) { deletionRequest.current = { deletion_id: value.deletion.deletion_id, source_id: value.deletion.source_id };setDeletion(value.deletion) } })
      .catch(() => { /* The feature is deliberately absent while disabled. */ })
    return () => controller.abort()
  }, [sourceId])
  async function deleteOriginal(resume = false) {
    if (!sourceId || (!resume && !deleteAccepted)) return
    const request = deletionRequest.current || { deletion_id: crypto.randomUUID(), source_id: sourceId }
    deletionRequest.current = request;setDeleteError('');setDeleting(true);setDeletion({ ...request, state: 'processing' });setDeleteOpen(false)
    try {
      const deadline = Date.now() + 15 * 60_000
      while (true) {
        const value = await postMemory<DeletionStatus>('/source-deletions', request)
        setDeletion(value)
        if (value.state !== 'processing') break
        if (Date.now() >= deadline) throw new Error('Der Löschvorgang wird weiter abgeschlossen. Bitte später mit derselben Lösch-ID fortsetzen.')
        await new Promise(resolve => window.setTimeout(resolve, 2000))
      }
    } catch (error) { setDeleteError(error instanceof Error ? error.message : 'Der Löschvorgang konnte noch nicht abgeschlossen werden.') }
    finally { setDeleting(false) }
  }
  const summaries = current?.data?.summaries || []
  const detailedNote = summaries.find(note => note.topics.some(topic => typeof topic !== 'string' && !!topic.summary?.trim()))
  const topicNote = detailedNote || summaries.find(note => note.topics.length > 0)
  const showTopics = view === 'topics' && !!topicNote
  const showSummary = !showTopics && view !== 'original' && summaries.length > 0
  return <Dialog open onOpenChange={open => { if (!open) close() }}><DialogContent className="wm-dialog px-dialog" overlayClassName="wm-overlay px-overlay" closeLabel="Meeting schließen" onCloseAutoFocus={event => { event.preventDefault(); focus?.focus() }}>
    <DialogHeader><DialogTitle>{current?.data?.summary_title || current?.data?.title || source.summary_title || source.title}</DialogTitle><DialogDescription>Meeting{(current?.data?.event_date || source.event_date) ? ` vom ${dateLabel(current?.data?.event_date || source.event_date)}` : ''}{deletion?.state === 'verified' ? ' · Original gelöscht' : ` · Vollständiges Original${summaries.length > 0 ? ' und gespeicherte Zusammenfassung' : ''}`}</DialogDescription></DialogHeader>
    {!current && <p role="status">Vollständiges Original wird geladen…</p>}
    {current?.error && <div role="alert"><p>{current.error}</p><button type="button" className="wm-button" onClick={() => retry(n => n + 1)}>Erneut versuchen</button></div>}
    {deletion && deletion.state !== 'verified' && <div className="wm-panel" role="status"><p>Das Original wird aus der aktiven App und ihren technischen Arbeitskopien entfernt. Dieser Vorgang kann nach einem Neustart mit derselben Lösch-ID fortgesetzt werden.</p>{deleteError && <p role="alert">{deleteError}</p>}<button type="button" className="wm-button" disabled={deleting} onClick={() => void deleteOriginal(true)}>{deleting ? 'Abschluss läuft…' : 'Abschluss fortsetzen'}</button></div>}
    {deletion?.state === 'verified' && <div className="wm-panel" role="status"><p>Das Original wurde aus der aktiven App gelöscht. Aufgaben, Wissen und ausdrücklich übernommene Belegzitate bleiben erhalten.</p><p className="wm-muted">Ältere Sicherungen laufen nach der regulären Aufbewahrung aus. Der Lösch-Wasserstand verhindert, dass sie das Original wieder in die aktive App einspielen.</p></div>}
    {current?.data && !current.data.deleted && !deletion && <>{summaries.length > 0 && <div className="wm-original-controls" role="group" aria-label="Meetingansicht"><button type="button" className="wm-button" aria-pressed={showSummary} onClick={() => setView('summary')}>Zusammenfassung</button>{topicNote && <button type="button" className="wm-button" aria-pressed={showTopics} onClick={() => setView('topics')}>Nach Themen</button>}<button type="button" className="wm-button" aria-pressed={!showSummary && !showTopics} onClick={() => setView('original')}>Original</button></div>}
      {showTopics && topicNote ? <div className="wm-summary-scroll" aria-label="Zusammenfassung nach Themen">
        <p className="wm-muted">{topicNote.origin === 'legacy_meeting_inbox' ? 'Erhaltene Themenzusammenfassungen aus der ursprünglichen Inbox-Notiz.' : 'Erhaltene Themenübersicht dieser Meetingfassung.'}</p>
        {topicNote.legacy_status === 'pending' && <p className="wm-muted">Diese Notiz war in der bisherigen Inbox noch nicht bestätigt.</p>}
        {topicNote.provenance?.content_conflict && <p className="wm-summary-warning">In der alten App war dieser Notiz ein anderes Transkript zugeordnet. Sie wurde erhalten und dem zugehörigen Drive-Original zugeordnet.</p>}
        {!detailedNote && <p className="wm-muted">Für dieses Meeting sind Themennamen, aber keine separaten Themenzusammenfassungen gespeichert.</p>}
        {topicNote.topics.map((topic, index) => <section key={index} className="wm-archive-topic"><h3>{typeof topic === 'string' ? topic : topic.name}</h3>{typeof topic !== 'string' && <p className="wm-summary-text">{topic.summary}</p>}</section>)}
      </div> : showSummary ? <div className="wm-summary-scroll">{detailedNote && <p><button type="button" className="px-text-button" onClick={() => setView('topics')}>Ausführliche Zusammenfassungen nach Themen öffnen</button></p>}<SummaryText summary={summaries[0]} />{summaries.length > 1 && <details className="wm-provenance"><summary>Frühere gespeicherte Fassungen</summary>{summaries.slice(1).map(summary => <SummaryText key={summary.id} summary={summary} />)}</details>}</div> : <>
        <div className="wm-original-controls"><button type="button" className="wm-button" aria-pressed={exportView} onClick={() => setExportView(v => !v)}>{exportView ? 'Transkript anzeigen' : 'Export mit Kopfzeile anzeigen'}</button><span className="wm-muted">{numberLabel(Array.from(current.data.transcript || '').length)} Zeichen im Transkript</span></div>
        <pre tabIndex={0} aria-label={exportView ? 'Vollständiger Drive-Export' : 'Vollständiges Originaltranskript'}>{exportView ? current.data.full_export : current.data.transcript}</pre></>}
      <details className="wm-provenance"><summary>Herkunft und Prüfsumme</summary>{current.data.summary_title && current.data.summary_title !== current.data.title && <p>Originaltitel: {current.data.title}</p>}<p>Archiviert: {new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(current.data.observed_at))}</p><p>Drive-ID: <code translate="no">{current.data.source_id.replace(/^drive:/, '')}</code></p><p>SHA-256: <code translate="no">{exportView ? current.data.export_hash : current.data.content_hash}</code></p></details>
      {deletionAvailable && !deletion && <p><button type="button" className="wm-link" onClick={() => { setDeleteAccepted(false);setDeleteOpen(true) }}>Vollständiges Original löschen</button></p>}</>}
    <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}><DialogContent className="wm-dialog px-dialog" overlayClassName="wm-overlay px-overlay" closeLabel="Abbrechen"><DialogHeader><DialogTitle>Vollständiges Original löschen?</DialogTitle><DialogDescription>Diese Entscheidung entfernt das Transkript und weitere aktive technische Originalkopien. Sie lässt Aufgaben, Wissen und ausdrücklich übernommene Belegzitate unverändert.</DialogDescription></DialogHeader>
      <p>Übernommene Belegzitate bleiben sichtbar und können große Teile des ursprünglichen Wortlauts enthalten. Die Funktion löscht sie bewusst nicht.</p>
      <p>Ältere Sicherungen werden nicht sofort verändert. Sie laufen nach der regulären Aufbewahrung aus: 14 neueste Sicherungen plus acht beobachtete Wochen; bei Offlinezeiten oder Fehlern können Kopien länger bestehen. Ein unabhängiger Lösch-Wasserstand sperrt ihre Wiederherstellung in die aktive App.</p>
      <label><input type="checkbox" checked={deleteAccepted} onChange={event => setDeleteAccepted(event.target.checked)} /> Ich möchte nur das vollständige Original löschen und Aufgaben, Wissen sowie übernommene Belegzitate behalten.</label>
      <div className="wm-original-controls"><button type="button" className="wm-button" onClick={() => setDeleteOpen(false)}>Abbrechen</button><button type="button" className="wm-button" disabled={!deleteAccepted} onClick={() => void deleteOriginal()}>Original endgültig löschen</button></div>
    </DialogContent></Dialog>
  </DialogContent></Dialog>
}
export function ArchivePage() {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState({ query: '', date: '', sort: 'relevance', offset: 0 })
  const [attempt, retry] = useState(0)
  const location = useRoute()
  const [selected, selectSource] = useState<ArchiveSource | null>(null)
  const opened = useRef(false)
  const meetingId = location.page === 'archiv' ? location.params.get('meeting') : null
  const source: ArchiveSource | null = meetingId ? selected?.id === meetingId ? selected : { id: meetingId, source_id: '', title: 'Meeting', event_date: '', observed_at: '', content_hash: '', characters: 0 } : null
  function setSource(value: ArchiveSource | null) {
    if (value) { selectSource(value); opened.current = true; const params = new URLSearchParams(location.params); params.set('meeting', value.id); params.delete('meeting_view'); navigate('archiv', params) }
    else if (opened.current) { opened.current = false; window.history.back() }
    else { const params = new URLSearchParams(location.params); params.delete('meeting'); params.delete('meeting_view'); navigate('archiv', params, true) }
  }
  const key = JSON.stringify([filter, attempt])
  const [result, setResult] = useState<{ key: string; data?: Catalogue; error?: string }>()
  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams({ q: filter.query, order: filter.sort, offset: String(filter.offset), limit: '25' })
    if (filter.date) params.set('as_of', filter.date)
    getMemory<Catalogue>(`/archive?${params}`, controller.signal).then(data => {
      if (!Array.isArray(data.sources) || typeof data.total !== 'number') throw new Error('Die Archivantwort ist unvollständig.')
      setResult({ key, data })
    }).catch((error: Error) => { if (!controller.signal.aborted) setResult({ key, error: error.message }) })
    return () => controller.abort()
  }, [filter, key])
  const current = result?.key === key ? result : undefined
  const data = current?.data
  return <div className="working-memory"><header className="wm-heading"><div><p className="wm-eyebrow">Wissen nachschlagen</p><h1>Meeting-Archiv</h1><p className="wm-muted">Zusammenfassungen und vollständige Originale. Die Suche findet Wörter und Wortanfänge im Transkript.</p></div></header>
    <form className="wm-controls" onSubmit={event => { event.preventDefault(); const date = String(new FormData(event.currentTarget).get('archive_date') || ''); setFilter(value => ({ ...value, query: query.trim(), date, offset: 0 })) }}>
      <label className="wm-search">Im Original suchen<input name="archive_query" type="search" autoComplete="off" maxLength={500} value={query} onChange={event => setQuery(event.target.value)} placeholder="Zum Beispiel Umrechnungskurse…" /></label>
      <label>Meetings bis einschließlich<input name="archive_date" autoComplete="off" type="date" defaultValue="" /></label><label>Sortieren<select name="archive_sort" autoComplete="off" value={filter.sort} onChange={event => setFilter(value => ({ ...value, sort: event.target.value, offset: 0 }))}><option value="relevance">Relevanz, sonst neueste</option><option value="newest">Neueste zuerst</option><option value="oldest">Älteste zuerst</option><option value="title">Originaltitel A–Z</option></select></label><button className="wm-button" type="submit">Suchen</button>
      {(filter.query || filter.date) && <button type="reset" className="wm-link" onClick={() => { setQuery(''); setFilter(value => ({ ...value, query: '', date: '', offset: 0 })) }}>Alle Originale anzeigen</button>}
    </form>
    {!current && <p className="wm-panel" role="status">Archiv wird durchsucht…</p>}
    {current?.error && <div className="wm-panel" role="alert"><h2>Archiv konnte nicht geladen werden</h2><p>{current.error}</p><button className="wm-button" type="button" onClick={() => retry(n => n + 1)}>Erneut versuchen</button></div>}
    {data && <><p className="wm-scope" role="status">{numberLabel(data.total)} {data.total === 1 ? 'Original' : 'Originale'}{filter.query ? ` für „${filter.query}“` : ''} · Meetings bis {dateLabel(data.as_of)}{data.total > 0 ? ` · ${numberLabel(filter.offset + 1)}–${numberLabel(Math.min(filter.offset + 25, data.total))} angezeigt` : ''}</p>
      <section className="wm-panel" aria-label="Originale">{data.sources.length ? data.sources.map(item => <article className="wm-row" key={item.id}><div className="wm-row-head"><h2><button type="button" className="wm-title-link" onClick={() => setSource(item)}>{item.summary_title || item.title}</button></h2><time className="wm-muted" dateTime={item.event_date}>{dateLabel(item.event_date)}</time></div><p className="wm-muted">{numberLabel(item.characters)} Zeichen · vollständiges Transkript</p>{item.match && <details><summary>Fundstelle im Original</summary><blockquote>{item.match.text}</blockquote><p className="wm-muted">Zeichen {numberLabel(item.match.start + 1)}–{numberLabel(item.match.end)} im Transkript</p></details>}<button className="wm-link" type="button" onClick={() => setSource(item)}>Meeting öffnen</button></article>) : <p>Keine passenden Originale. Versuche einen anderen Suchbegriff oder ein späteres Datum.</p>}</section>
      {data.total > 25 && <nav className="wm-pagination" aria-label="Archivseiten"><button type="button" className="wm-button" disabled={filter.offset === 0} onClick={() => setFilter(value => ({ ...value, offset: Math.max(0, value.offset - 25) }))}>Vorherige Seite</button><button type="button" className="wm-button" disabled={filter.offset + 25 >= data.total} onClick={() => setFilter(value => ({ ...value, offset: value.offset + 25 }))}>Nächste Seite</button></nav>}</>}
    {source && <OriginalDialog key={source.id} source={source} close={() => setSource(null)} />}
  </div>
}
