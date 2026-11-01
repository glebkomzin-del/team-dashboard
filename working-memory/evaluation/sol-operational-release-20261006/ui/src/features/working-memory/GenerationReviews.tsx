import { useEffect, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { dateLabel, getMemory, kindNames, MemoryWriteError, numberLabel, postMemory } from './types'
import type { Kind } from './types'

interface Source { title: string; event_date: string; archive_id: string | null }
interface Item {
  title: string; claim: string; owner: string | null; status?: string; group?: string; kind?: Kind
  due_text: string | null; due_date?: string | null; condition_text: string | null
  required_review: boolean; action_uncertainty: string | null; quotes?: string[]
  source_title?: string; event_date?: string; update?: string | null
}
interface Difference { id: string; before: Item | null; after: Item | null }
interface Review {
  id: string; label: string; expected_revision: number; current_revision: number; review_sha256: string
  state: 'pending' | 'accepted' | 'rejected'; stale: boolean; reason: string; decision_reason?: string
  sources: { source_id: string; reason: string; before: Source | null; after: Source | null }[]
  identity_links: { old_id: string; new_id: string; before_title: string; after_title: string; reason: string }[]
  topic_identity_links?: { old_id: string; new_id: string; before_title: string; after_title: string; reason: string }[]
  source_order_reason?: string | null
  source_order_changes?: { source_id: string; title: string; event_date: string; before_position: number; after_position: number }[]
  diff: Difference[]; observation_diff: Difference[]; personal_decisions_preserved: number
}
interface Decision { review_id: string; command_id: string; expected_revision: number; review_sha256: string; action: 'accept' | 'reject'; reason: string }
const statusNames: Record<string, string> = { open: 'Offen', waiting: 'Wartet', done: 'Erledigt', cancelled: 'Beendet', dismissed: 'Verworfen' }
const groupNames: Record<string, string> = { personal: 'Für mich', waiting_dependencies: 'Meine bedingten Zusagen', waiting: 'Zusagen anderer', completed: 'Erledigt', cancelled: 'Beendet' }

function ArchivedOriginal({ source }: { source: Source }) {
  const [open, setOpen] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ attempt: number; transcript?: string; error?: string }>()
  useEffect(() => {
    if (!open || !source.archive_id) return
    const controller = new AbortController()
    getMemory<{ transcript: string }>(`/archive/${source.archive_id}`, controller.signal).then(data => {
      if (typeof data.transcript !== 'string') throw new Error('Original fehlt')
      setResult({ attempt, transcript: data.transcript })
    }).catch(() => { if (!controller.signal.aborted) setResult({ attempt, error: 'Das Original konnte nicht geladen werden.' }) })
    return () => controller.abort()
  }, [open, source.archive_id, attempt])
  const current = result?.attempt === attempt ? result : undefined
  return <div><p><strong>{source.title}</strong> · {dateLabel(source.event_date)}</p>{source.archive_id ? <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Vollständiges Original lesen</summary>{open && <>
      {!current && <p role="status">Original wird geladen…</p>}
      {current?.error && <p role="alert">{current.error} <button className="wm-button" type="button" onClick={() => setAttempt(n => n + 1)}>Erneut versuchen</button></p>}
      {current?.transcript !== undefined && <pre className="wm-generation-original" tabIndex={0} aria-label={`Original: ${source.title}`}>{current.transcript}</pre>}
    </>}
  </details> : <p className="wm-note">Das vollständige Original ist hier gerade nicht erreichbar.</p>}</div>
}
function ItemView({ item, side }: { item: Item | null; side: 'before' | 'after' }) {
  return <div className="wm-generation-side"><p className="wm-muted">{side === 'before' ? 'Bisher' : 'Nach Übernahme'}</p>{item ? <>
    <h4>{item.title}</h4><p>{item.claim}</p>
    {item.kind && <p>{kindNames[item.kind]}</p>}
    {item.group && <p>{groupNames[item.group] || item.group}{item.status ? ` · ${statusNames[item.status] || item.status}` : ''}</p>}
    <p>{item.owner || 'Keine Person zugeordnet'}</p>
    {(item.due_text || item.due_date) && <p>Frist: {item.due_date ? dateLabel(item.due_date) : item.due_text}</p>}
    {item.condition_text && <p>Voraussetzung: {item.condition_text}</p>}
    {item.required_review && <p className="wm-note">Bleibt zur Einzelprüfung offen.</p>}
    {item.action_uncertainty && <p className="wm-note">{item.action_uncertainty}</p>}
    {item.source_title && <p className="wm-muted">{item.source_title}{item.event_date ? ` · ${dateLabel(item.event_date)}` : ''}</p>}
    {item.quotes?.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}
  </> : <p>{side === 'before' ? 'Neu in diesem Vorschlag.' : 'Wird aus dem aktuellen Arbeitsstand entfernt. Frühere Stände bleiben nachvollziehbar.'}</p>}</div>
}
function Differences({ entries }: { entries: Difference[] }) {
  return <>{entries.map(entry => <article className="wm-row wm-generation-compare" key={entry.id}><ItemView side="before" item={entry.before} /><ItemView side="after" item={entry.after} /></article>)}</>
}
export function GenerationReviewDialog({ reviewId, onClose, onSaved }: { reviewId: string; onClose: () => void; onSaved: () => void }) {
  const [commandId] = useState(() => crypto.randomUUID())
  const [returnFocus] = useState(() => document.activeElement instanceof HTMLElement ? document.activeElement : null)
  const [review, setReview] = useState<Review>()
  const [loadError, setLoadError] = useState('')
  const [action, setAction] = useState<'accept' | 'reject' | ''>('')
  const [reason, setReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<Decision>()
  const [error, setError] = useState<MemoryWriteError>()
  const [discard, setDiscard] = useState(false)
  const sending = useRef(false)
  const errorRef = useRef<HTMLParagraphElement>(null)
  useEffect(() => {
    const controller = new AbortController()
    getMemory<Review>(`/generation-reviews/${reviewId}`, controller.signal).then(data => {
      if (data.id !== reviewId || !Array.isArray(data.sources) || !Array.isArray(data.diff) || !Array.isArray(data.observation_diff)) throw new Error('Ungültige Prüfung')
      setReview(data)
    }).catch(() => { if (!controller.signal.aborted) setLoadError('Die Änderungsvorschau konnte nicht geprüft werden. Bitte schließen und den Stand aktualisieren.') })
    return () => controller.abort()
  }, [reviewId])
  useEffect(() => {
    if (!reason && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [reason, pending])
  function close() { if (busy) return; if (reason || pending) setDiscard(true); else onClose() }
  async function submit() {
    if (!review || !action || sending.current || error?.status === 409 || (action === 'accept' && (review.stale || !confirmed))) return
    sending.current = true; setBusy(true); setError(undefined)
    const request: Decision = pending || { review_id: reviewId, command_id: commandId, expected_revision: review.expected_revision, review_sha256: review.review_sha256, action, reason: reason.trim() }
    setPending(request)
    try { await postMemory('/generation-decisions', request); onSaved() }
    catch (caught) {
      const failure = caught instanceof MemoryWriteError ? caught : new MemoryWriteError('Die Speicherung konnte nicht bestätigt werden. Erneut versuchen sendet dieselbe Entscheidung.', 503)
      if ([400, 401, 403].includes(failure.status)) setPending(undefined)
      setError(failure); requestAnimationFrame(() => errorRef.current?.focus())
    } finally { sending.current = false; setBusy(false) }
  }
  return <Dialog open onOpenChange={open => { if (!open) close() }}><DialogContent className="wm-dialog wm-decision-dialog" overlayClassName="wm-overlay" closeLabel="Änderungsvorschau schließen"
    onEscapeKeyDown={event => { if (busy) event.preventDefault() }} onPointerDownOutside={event => event.preventDefault()}
    onCloseAutoFocus={event => { event.preventDefault(); returnFocus?.focus() }}>
    <DialogHeader><DialogTitle>Änderungen gemeinsam prüfen</DialogTitle><DialogDescription>{review?.label || 'Gespeicherte Änderungen und ihre Auswirkungen laden.'}</DialogDescription></DialogHeader>
    <div className="wm-decision-scroll">
      {!review && !loadError && <p role="status">Vorschlag wird geprüft…</p>}{loadError && <p role="alert">{loadError}</p>}
      {review && <>
        <p>{review.reason}</p>
        {review.stale && review.state === 'pending' && <p role="alert" className="wm-note">Der Arbeitsstand wurde seit dieser Vorschau geändert. Eine Übernahme ist gesperrt. Du kannst den Vorschlag verwerfen oder nach einem neuen Abgleich erneut prüfen.</p>}
        <p>{numberLabel(review.diff.length)} {review.diff.length === 1 ? 'Änderung' : 'Änderungen'} am Arbeitsstand · {numberLabel(review.observation_diff.length)} {review.observation_diff.length === 1 ? 'geänderte Aussage mit Belegen' : 'geänderte Aussagen mit Belegen'}.</p>
        <p className={review.personal_decisions_preserved ? "wm-confirmed" : "wm-muted"}>{review.personal_decisions_preserved ? `${numberLabel(review.personal_decisions_preserved)} persönliche ${review.personal_decisions_preserved === 1 ? "Entscheidung bleibt" : "Entscheidungen bleiben"} erhalten.` : "In diesem Stand gibt es noch keine persönlichen Entscheidungen."}{review.identity_links.length > 0 && " Vorgeschlagene Zuordnungen zu neuen Belegen stehen unten zur Prüfung."}</p>
        {!!review.source_order_changes?.length && <details><summary>Reihenfolge der Termine korrigieren · {numberLabel(review.source_order_changes.length)}</summary><p>{review.source_order_reason}</p>{review.source_order_changes.map(source => <article className="wm-row" key={source.source_id}><p><strong>{source.title}</strong> · {dateLabel(source.event_date)}</p><p>Position {numberLabel(source.before_position)} → {numberLabel(source.after_position)} in der verarbeiteten Terminfolge.</p></article>)}</details>}
        <details><summary>Betroffene Originale · {numberLabel(review.sources.length)}</summary>{review.sources.map(source => <article className="wm-row" key={source.source_id}><p>{source.reason}</p><div className="wm-generation-compare">
          <div><h3>Bisherige Fassung</h3>{source.before ? <ArchivedOriginal source={source.before} /> : <p>Noch nicht im Arbeitsstand.</p>}</div>
          <div><h3>Vorgeschlagene Fassung</h3>{source.after ? <ArchivedOriginal source={source.after} /> : <p>Wird aus dem Arbeitsstand entfernt; das Original bleibt archiviert.</p>}</div>
        </div></article>)}</details>
        <h3>Auswirkungen auf Aufgaben</h3>{review.diff.length ? <Differences entries={review.diff} /> : <p>Aufgaben und ihr Status bleiben gleich.</p>}
        <details><summary>Aussagen und Originalbelege vergleichen · {numberLabel(review.observation_diff.length)}</summary><Differences entries={review.observation_diff} /></details>
        {!!review.identity_links.length && <details><summary>Zuordnung vorhandener Zusagen · {numberLabel(review.identity_links.length)}</summary>{review.identity_links.map(link => <article className="wm-row" key={link.old_id}><p><strong>{link.before_title}</strong> → <strong>{link.after_title}</strong></p><p>{link.reason}</p></article>)}</details>}
        {!!review.topic_identity_links?.length && <details><summary>Zuordnung vorhandener Themen · {numberLabel(review.topic_identity_links.length)}</summary>{review.topic_identity_links.map(link => <article className="wm-row" key={link.old_id}><p><strong>{link.before_title}</strong> → <strong>{link.after_title}</strong></p><p>{link.reason}</p></article>)}</details>}
        {review.state !== 'pending' ? <p className="wm-confirmed">{review.state === 'accepted' ? 'Bereits übernommen' : 'Bereits verworfen'}{review.decision_reason ? `: ${review.decision_reason}` : ''}</p> : <form className="wm-decision-form" aria-busy={busy} onSubmit={event => { event.preventDefault(); void submit() }}>
          <fieldset disabled={busy || !!pending}>
            <label>Deine Entscheidung<select name="generation_decision" autoComplete="off" required value={action} onChange={event => { const value = event.target.value as 'accept' | 'reject'; setAction(value); if (value === 'accept') setReason('') }}><option value="" disabled>Bitte auswählen…</option>{!review.stale && <option value="accept">Änderungen gemeinsam übernehmen</option>}<option value="reject">Vorschlag verwerfen</option></select></label>
            {action === 'accept' && <label className="wm-generation-confirm"><input name="generation_confirmed" autoComplete="off" type="checkbox" checked={confirmed} required onChange={event => setConfirmed(event.target.checked)} />Ich habe Änderungen, Belege und vorgeschlagene Zuordnungen geprüft.</label>}
            {action === 'reject' && <p>Der aktuelle Arbeitsstand bleibt erhalten. Die Originale bleiben im Archiv.</p>}
            {action === 'reject' && <label>Optionale Anmerkung<textarea name="generation_reason" autoComplete="off" value={reason} onChange={event => setReason(event.target.value)} maxLength={4000} rows={3} placeholder="Nur falls du etwas für spätere Prüfungen festhalten möchtest…" /></label>}
          </fieldset>
          {error && <p role="alert" tabIndex={-1} ref={errorRef} className="wm-note">{error.message}</p>}
          <div className="wm-decision-actions"><button type="button" className="wm-button" disabled={busy} onClick={close}>Abbrechen</button>{error?.status === 409 ? <button type="button" className="wm-button" onClick={onSaved}>Schließen und aktualisieren</button> : <button type="submit" className="wm-button" disabled={busy || !action || (action === 'accept' && !confirmed)}>{busy ? 'Wird gespeichert…' : pending ? 'Erneut versuchen' : action === 'accept' ? 'Übernehmen' : 'Verwerfen'}</button>}</div>
        </form>}
      </>}
      {discard && <div role="alert" className="wm-note"><p>Deine Entscheidung ist noch nicht sicher gespeichert.</p><button type="button" className="wm-button" onClick={onSaved}>Schließen und Stand prüfen</button><button type="button" className="wm-button" onClick={() => setDiscard(false)}>Weiter bearbeiten</button></div>}
    </div>
  </DialogContent></Dialog>
}
export function GenerationReviews({ attempt, readOnly, onSaved }: { attempt: number; readOnly?: boolean; onSaved: () => void }) {
  const [result, setResult] = useState<{ attempt: number; reviews?: { id: string; label: string; expected_revision: number }[]; revision?: number; error?: string }>()
  const [selected, setSelected] = useState<string>()
  useEffect(() => {
    const controller = new AbortController()
    getMemory<{ reviews: { id: string; label: string; expected_revision: number }[]; revision: number }>('/generation-reviews', controller.signal).then(data => {
      if (!Array.isArray(data.reviews) || !Number.isInteger(data.revision)) throw new Error('Ungültige Übersicht')
      setResult({ attempt, ...data })
    }).catch(() => { if (!controller.signal.aborted) setResult({ attempt, error: 'Vorbereitete Änderungen können gerade nicht geladen werden. Bitte den Verarbeitungsstand aktualisieren.' }) })
    return () => controller.abort()
  }, [attempt])
  const current = result?.attempt === attempt ? result : undefined
  return <section aria-label="Vorbereitete Änderungen"><h3>Änderungen an früheren Meetings</h3>{!current && <p role="status">Vorschläge werden geladen…</p>}{current?.error && <p role="alert">{current.error}</p>}{current?.reviews && <>
    {!current.reviews.length && <p className="wm-muted">Keine vorbereiteten Änderungen zur Freigabe.</p>}
    {current.reviews.map(review => <article className="wm-row" key={review.id}><h4>{review.label}</h4>{review.expected_revision !== current.revision && <p className="wm-note">Ein neuer Abgleich ist erforderlich.</p>}{!readOnly && <button type="button" className="wm-button" onClick={() => setSelected(review.id)}>Änderungen prüfen</button>}</article>)}
    {current.reviews.length === 50 && <p>Die ersten 50 Vorschläge werden angezeigt.</p>}
  </>}{selected && <GenerationReviewDialog key={selected} reviewId={selected} onClose={() => setSelected(undefined)} onSaved={() => { setSelected(undefined); onSaved() }} />}</section>
}
