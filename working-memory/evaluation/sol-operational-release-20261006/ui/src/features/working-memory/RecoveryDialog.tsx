import { useEffect, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { dateLabel, getMemory, kindNames, MemoryWriteError, postMemory } from './types'
import type { Observation } from './types'
import { SourceEditor } from './SourceEditor'

type RecoveryAction = 'retry' | 'archive_only' | 'rebase_prepared'
interface Review {
  job_id: string; title: string; event_date: string; state: string; reason: string | null
  expected_revision: number; expected_updated_at: string; command_id: string
  can_archive: boolean; can_retry: boolean; can_rebase: boolean; unknown_provider_outcome: boolean
  preview_hash: string | null; blocked: string | null; prepared_observations: Observation[]
  decisions: { command_id: string; action: string; reason: string; recorded_at: string }[]
}
interface Request {
  job_id: string; command_id: string; expected_revision: number; expected_updated_at: string
  action: RecoveryAction; reason: string; preview_hash: string | null
}
const labels: Record<RecoveryAction, string> = {
  retry: 'Verarbeitung fortsetzen', archive_only: 'Nur im Archiv behalten', rebase_prepared: 'Gespeichertes Ergebnis übernehmen',
}
export function RecoveryDialog({ jobId, onClose, onSaved }: { jobId: string; onClose: () => void; onSaved: () => void }) {
  const [commandId] = useState(() => crypto.randomUUID())
  const [returnFocus] = useState(() => document.activeElement instanceof HTMLElement ? document.activeElement : null)
  const [review, setReview] = useState<Review>()
  const [loadError, setLoadError] = useState('')
  const [action, setAction] = useState<RecoveryAction | ''>('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<Request>()
  const [error, setError] = useState<MemoryWriteError>()
  const [discard, setDiscard] = useState(false)
  const [editing, setEditing] = useState(false)
  const errorRef = useRef<HTMLParagraphElement>(null)
  const sending = useRef(false)
  useEffect(() => {
    const controller = new AbortController()
    getMemory<Review>(`/operations/jobs/${jobId}?command_id=${commandId}`, controller.signal)
      .then(data => {
        if (data.job_id !== jobId || data.command_id !== commandId || !Array.isArray(data.prepared_observations)) throw new Error('Ungültige Prüfung')
        setReview(data)
      }).catch(() => { if (!controller.signal.aborted) setLoadError('Die Prüfung konnte nicht geladen werden. Bitte schließen und den Verarbeitungsstand aktualisieren.') })
    return () => controller.abort()
  }, [jobId, commandId])
  useEffect(() => {
    if (!reason && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [reason, pending])
  function close() { if (busy) return; if (reason || pending) setDiscard(true); else onClose() }
  async function submit() {
    if (!review || !action || sending.current || error?.status === 409) return
    sending.current = true; setBusy(true); setError(undefined)
    const request = pending || { job_id: jobId, command_id: commandId, expected_revision: review.expected_revision,
      expected_updated_at: review.expected_updated_at, action, reason: reason.trim(), preview_hash: action === 'rebase_prepared' ? review.preview_hash : null }
    setPending(request)
    try { await postMemory('/operations/decisions', request); onSaved() }
    catch (caught) {
      const failure = caught instanceof MemoryWriteError ? caught : new MemoryWriteError('Die Speicherung konnte nicht bestätigt werden. Erneut versuchen sendet dieselbe Entscheidung.', 503)
      if ([400, 401, 403].includes(failure.status)) setPending(undefined)
      setError(failure); requestAnimationFrame(() => errorRef.current?.focus())
    } finally { sending.current = false; setBusy(false) }
  }
  if (editing) return <SourceEditor jobId={jobId} onClose={() => setEditing(false)} onSaved={onSaved} />
  return <Dialog open onOpenChange={open => { if (!open) close() }}>
    <DialogContent className="wm-dialog wm-decision-dialog" overlayClassName="wm-overlay" closeLabel="Verarbeitungsprüfung schließen"
      onEscapeKeyDown={event => { if (busy) event.preventDefault() }} onPointerDownOutside={event => event.preventDefault()}
      onCloseAutoFocus={event => { event.preventDefault(); returnFocus?.focus() }}>
      <DialogHeader><DialogTitle>Verarbeitung prüfen</DialogTitle><DialogDescription>{review ? `${review.title} · ${dateLabel(review.event_date)}` : 'Gespeicherten Stand und sichere Möglichkeiten laden.'}</DialogDescription></DialogHeader>
      <div className="wm-decision-scroll">
        {!review && !loadError && <p role="status">Gespeicherter Stand wird geprüft…</p>}
        {loadError && <p role="alert">{loadError}</p>}
        {review && <>
          {review.unknown_provider_outcome && <p className="wm-note">Der Ausgang einer KI-Anfrage ist noch unklar. Sie wird nicht erneut gesendet. Eine spätere Antwort kann weiterhin gespeichert und abgerechnet werden.</p>}
          {review.blocked === 'source_generation_review' && <p className="wm-note">Dieses Original ist geändert oder nachträglich eingegangen. Vor einer Übernahme müssen betroffene spätere Aussagen gemeinsam neu geprüft werden. Du kannst die Aussagen am Original überarbeiten und einen Vergleich vorbereiten.</p>}
          {review.blocked === 'saved_result_requires_content_review' && <p className="wm-note">Das gespeicherte Ergebnis lässt sich nicht unverändert übernehmen. Eine inhaltliche Prüfung ist erforderlich.</p>}
          {review.can_archive && <button type="button" className="wm-button" disabled={busy || !!pending || !!reason} onClick={() => setEditing(true)}>Aussagen am Original überarbeiten</button>}
          {!review.can_retry && !review.can_rebase && !review.can_archive && <p>Der Lauf arbeitet noch oder wurde bereits abgeschlossen. Bitte schließe die Prüfung und aktualisiere den Stand.</p>}
          {(review.can_retry || review.can_rebase || review.can_archive) && <form className="wm-decision-form" aria-busy={busy} onSubmit={event => { event.preventDefault(); void submit() }}>
            <fieldset disabled={busy || !!pending}>
              <label>Wie soll es weitergehen?<select required value={action} onChange={event => setAction(event.target.value as RecoveryAction)}>
                <option value="" disabled>Bitte auswählen…</option>
                {review.can_retry && <option value="retry">{labels.retry}</option>}
                {review.can_rebase && <option value="rebase_prepared">{labels.rebase_prepared}</option>}
                {review.can_archive && <option value="archive_only">{labels.archive_only}</option>}
              </select></label>
              {action === 'retry' && <p>Vorhandene Antworten werden wiederverwendet. Noch fehlende Prüfschritte dürfen gemäß der eingerichteten Kostenfreigabe laufen. Die Automatik wird durch diese Entscheidung nicht eingeschaltet.</p>}
              {action === 'archive_only' && <p>Das Original bleibt erhalten. Aus diesem Lauf werden keine neuen Aufgaben oder Änderungen übernommen. Spätere Meetings können weiterverarbeitet werden.</p>}
              {action === 'rebase_prepared' && <>
                <p>Diese gespeicherten Aussagen wurden gegen den aktuellen Arbeitsstand geprüft. Dafür wird keine neue KI-Anfrage gesendet. Persönlich bearbeitete Aufgaben bleiben geschützt; entsprechende Änderungsvorschläge bleiben einzeln prüfpflichtig.</p>
                <div className="wm-recovery-observations">{review.prepared_observations.map((item, index) => <article className="wm-row" key={index}>
                  <p className="wm-muted">{kindNames[item.kind]}{item.required_review ? ' · bleibt zur Einzelprüfung offen' : ''}</p>
                  <h3>{item.title}</h3><p>{item.claim}</p>
                  {item.owner && <p>{item.owner}</p>}
                  {item.action_uncertainty && <p className="wm-note">{item.action_uncertainty}</p>}
                  <details><summary>Originalbelege</summary>{item.quotes.map((quote, i) => <blockquote key={i}>{quote}</blockquote>)}</details>
                </article>)}</div>
              </>}
              <label>Deine Begründung<textarea value={reason} onChange={event => setReason(event.target.value)} required maxLength={4000} rows={3} /></label>
            </fieldset>
            {error && <p role="alert" tabIndex={-1} ref={errorRef} className="wm-note">{error.message}</p>}
            <div className="wm-decision-actions"><button type="button" className="wm-button" disabled={busy} onClick={close}>Abbrechen</button>
              {error?.status !== 409 && <button type="submit" className="wm-button" disabled={busy || !action || !reason.trim()}>{busy ? 'Wird gespeichert…' : pending ? 'Erneut versuchen' : 'Entscheidung speichern'}</button>}
              {error?.status === 409 && <button type="button" className="wm-button" onClick={onSaved}>Schließen und aktualisieren</button>}
            </div>
          </form>}
          {review.decisions.length > 0 && <details><summary>Bisherige Entscheidungen</summary>{review.decisions.map(item => <p key={item.command_id}>{labels[item.action as RecoveryAction] || 'Entscheidung'}: {item.reason}</p>)}</details>}
        </>}
        {discard && <div role="alert" className="wm-note"><p>Deine Entscheidung ist noch nicht sicher gespeichert.</p><button className="wm-button" onClick={onSaved}>Schließen und Stand prüfen</button><button className="wm-button" onClick={() => setDiscard(false)}>Weiter bearbeiten</button></div>}
      </div>
    </DialogContent>
  </Dialog>
}
