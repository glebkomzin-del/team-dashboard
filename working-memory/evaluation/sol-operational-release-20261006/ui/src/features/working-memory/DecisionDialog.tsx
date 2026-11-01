import { useEffect, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { MemoryWriteError, saveDecision } from './types'
import type { DecisionAction, DecisionRequest, Observation, Work } from './types'

export interface DecisionTarget { id: string; observation: Observation; work?: Work; action: DecisionAction }
export function DecisionDialog({ target, revision, onClose, onSaved, onRefresh }: {
  target: DecisionTarget; revision: number; onClose: () => void; onSaved: () => void; onRefresh: () => void
}) {
  const [returnFocus] = useState(() => document.activeElement instanceof HTMLElement ? document.activeElement : null)
  const correcting = target.action === 'correct' || target.action === 'correct_confirm'
  const workFields = target.observation.kind === 'commitment' || !!target.observation.update_target || !!target.work
  const initialOwner = target.action === 'correct_confirm' && target.observation.update_target && target.observation.update !== 'owner_changed' ? target.work?.owner || target.observation.owner || '' : target.observation.owner || ''
  const initialStatus = target.action === 'correct_confirm' && target.observation.update_target
    ? target.observation.update === 'done' ? 'done' : target.observation.update === 'reopened' || target.observation.update === 'condition_met' ? 'open' : target.observation.update === 'progress' && target.observation.work_state === 'waiting' ? 'waiting' : target.work?.status === 'dismissed' ? 'cancelled' : target.work?.status || 'open'
    : target.work?.status === 'dismissed' ? 'cancelled' : target.work?.status || (target.observation.work_state === 'waiting' ? 'waiting' : target.observation.work_state === 'done' ? 'done' : 'open')
  const [claim, setClaim] = useState(target.observation.claim)
  const [title, setTitle] = useState(target.observation.title)
  const [owner, setOwner] = useState(initialOwner)
  const [reason, setReason] = useState('')
  const [feedbackKind, setFeedbackKind] = useState<'interpretation' | 'real_world_change'>('real_world_change')
  const [status, setStatus] = useState<NonNullable<DecisionRequest['patch']['status']>>(initialStatus)
  const [dueMode, setDueMode] = useState('unchanged')
  const [due, setDue] = useState(target.work?.due_date || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<MemoryWriteError>()
  const [pending, setPending] = useState<DecisionRequest | null>(null)
  const [discardWarning, setDiscardWarning] = useState(false)
  const sending = useRef(false)
  const errorRef = useRef<HTMLParagraphElement>(null)
  const labels: Record<DecisionAction, string> = { correct_confirm: 'Korrigieren und bestätigen', confirm_knowledge: 'Aussage bestätigen', approve: 'Vorschlag bestätigen', reject: 'Vorschlag verwerfen', correct: 'Aufgabe bearbeiten', set_status: 'Status ändern' }
  const chooseOwner = (correcting && workFields) || (target.action === 'approve' && (!target.observation.update_target || target.observation.update === 'owner_changed'))
  const reasonRequired = correcting || target.action === 'set_status'
  const showReason = reasonRequired || target.action === 'reject'
  const frozen = busy || !!pending
  const dirty = !!reason || claim !== target.observation.claim || title !== target.observation.title || owner !== initialOwner || status !== initialStatus || dueMode !== 'unchanged'
  useEffect(() => {
    if (!dirty && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, pending])
  function requestClose() { if (busy) return; if (dirty || pending) setDiscardWarning(true); else onClose() }
  async function submit() {
    if (sending.current || error?.status === 409) return
    sending.current = true
    setBusy(true); setError(undefined)
    const patch: DecisionRequest['patch'] = {}
    if (target.action === 'approve' && chooseOwner) patch.owner = owner.trim()
    if (target.action === 'set_status') patch.status = status
    if (correcting) {
      if (title !== target.observation.title) patch.title = title.trim()
      if (claim !== target.observation.claim) patch.claim = claim.trim()
      if (workFields && (owner !== initialOwner || (target.action === 'correct_confirm' && (!target.observation.update_target || target.observation.update === 'owner_changed')))) patch.owner = owner.trim()
      if (workFields && (status !== initialStatus || target.action === 'correct_confirm')) patch.status = status
      if (dueMode === 'set') patch.due_date = due
      if (dueMode === 'remove') patch.due_date = null
    }
    const request = pending || { command_id: crypto.randomUUID(), expected_revision: revision,
      target_id: target.id, action: target.action, reason: reason.trim(), patch,
      feedback_kind: target.action === 'correct' ? feedbackKind : target.action === 'set_status' ? 'real_world_change' : 'interpretation' }
    setPending(request)
    try { await saveDecision(request); onSaved() }
    catch (caught) {
      const failure = caught instanceof MemoryWriteError ? caught : new MemoryWriteError('Die Verbindung wurde unterbrochen. Erneut versuchen sendet dieselbe Entscheidung.', 503)
      if (failure.status === 400 || failure.status === 401 || failure.status === 403) setPending(null)
      setError(failure)
      requestAnimationFrame(() => errorRef.current?.focus())
    } finally { sending.current = false; setBusy(false) }
  }
  return <Dialog open onOpenChange={open => { if (!open) requestClose() }}>
    <DialogContent className="wm-dialog wm-decision-dialog px-dialog" overlayClassName="wm-overlay px-overlay" closeLabel="Bearbeitung schließen"
      onEscapeKeyDown={event => { if (busy) event.preventDefault() }} onPointerDownOutside={event => event.preventDefault()}
      onCloseAutoFocus={event => { event.preventDefault(); returnFocus?.focus() }}>
      <DialogHeader><DialogTitle>{labels[target.action]}</DialogTitle><DialogDescription>{target.observation.title}</DialogDescription></DialogHeader>
      <div className="wm-decision-scroll">
        <p>{target.observation.claim}</p>
        <details><summary>Originalbelege ansehen</summary>{target.observation.quotes.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}</details>
        {target.action === 'approve' && <p className="wm-muted">{target.observation.update_target ? 'Du bestätigst die vorgeschlagene Änderung an der bestehenden Aufgabe.' : 'Diese Zusage wird als Aufgabe übernommen.'} Deine Entscheidung bleibt im Verlauf sichtbar.</p>}
        {target.action === 'confirm_knowledge' && <p className="wm-muted">Du bestätigst die Aussage und ihre Zuordnung. Daraus entsteht keine Aufgabe.</p>}
        {target.action === 'correct_confirm' && <p className="wm-muted">Ändere nur den falsch verstandenen Teil. Du bestätigst die korrigierte Fassung{workFields ? ' und die unten angezeigten Aufgabendaten' : ''}. Originalbelege und frühere Fassung bleiben erhalten.</p>}
        {target.action === 'reject' && <p className="wm-muted">Dieser Vorschlag wird verworfen. Das Original und eine optionale Anmerkung bleiben nachvollziehbar.</p>}
        <form className="wm-decision-form" aria-busy={busy} onSubmit={event => { event.preventDefault(); void submit() }}>
          <fieldset disabled={frozen}>
            {correcting && <label>Titel<input name="title" value={title} onChange={event => setTitle(event.target.value)} required maxLength={1000} autoComplete="off" /></label>}
            {correcting && <label>Aussage<textarea name="claim" autoComplete="off" value={claim} onChange={event => setClaim(event.target.value)} required maxLength={12000} rows={6} /></label>}
            {chooseOwner && <label>Verantwortliche Person<input name="owner" value={owner} onChange={event => setOwner(event.target.value)} required maxLength={1000} autoComplete="off" placeholder="Vollständiger Name…" /></label>}
            {target.action === 'set_status' && <label>Status<select name="status" value={status} onChange={event => setStatus(event.target.value as typeof status)} autoComplete="off"><option value="open">Offen</option><option value="waiting">Wartet auf Voraussetzung</option><option value="done">Erledigt</option><option value="cancelled">Nicht mehr erforderlich</option></select></label>}
            {correcting && workFields && <>
              <label>Status<select name="status" autoComplete="off" value={status} onChange={event => setStatus(event.target.value as typeof status)}><option value="open">Offen</option><option value="waiting">Wartet auf Voraussetzung</option><option value="done">Erledigt</option><option value="cancelled">Nicht mehr erforderlich</option></select></label>
              <label>Frist<select name="due_mode" autoComplete="off" value={dueMode} onChange={event => setDueMode(event.target.value)}><option value="unchanged">Unverändert lassen{target.observation.due_text ? `: ${target.observation.due_text}` : ''}</option><option value="set">Datum festlegen</option><option value="remove">Frist entfernen</option></select></label>
              {dueMode === 'set' && <label>Neues Datum<input name="due_date" autoComplete="off" type="date" value={due} onChange={event => setDue(event.target.value)} required /></label>}
            </>}
            {target.action === 'correct' && <label>Was ist der Anlass?<select name="feedback_kind" autoComplete="off" value={feedbackKind} onChange={event => setFeedbackKind(event.target.value as typeof feedbackKind)}><option value="real_world_change">Die Sachlage hat sich geändert</option><option value="interpretation">Die KI hat das Original falsch verstanden</option></select></label>}
            {showReason && <label>{reasonRequired ? 'Deine Begründung' : 'Optionale Anmerkung'}<textarea name="reason" autoComplete="off" value={reason} onChange={event => setReason(event.target.value)} required={reasonRequired} maxLength={4000} rows={3} placeholder={reasonRequired ? 'Zum Beispiel: Die Sachlage hat sich geändert…' : 'Nur falls du den Grund später festhalten möchtest…'} /></label>}
          </fieldset>
          {error && <p role="alert" tabIndex={-1} ref={errorRef} className="wm-note">{error.message}</p>}
          <div className="wm-decision-actions">
            <button className="wm-button" type="button" disabled={busy} onClick={error ? onRefresh : requestClose}>{error ? 'Schließen und Stand neu laden' : 'Abbrechen'}</button>
            {error?.status !== 409 && <button className="wm-button" type="submit" disabled={busy || (reasonRequired && !reason.trim())}>{busy ? <span role="status"><span className="wm-spinner" aria-hidden="true" />Wird gespeichert…</span> : pending ? 'Erneut versuchen' : target.action === 'correct_confirm' ? 'Korrigieren und bestätigen' : target.action === 'reject' ? 'Verwerfen' : target.action === 'approve' ? 'Übernehmen' : target.action === 'confirm_knowledge' ? 'Bestätigen' : 'Änderung speichern'}</button>}
          </div>
          {discardWarning && <div className="wm-note" role="alert"><p>Deine Eingaben wurden noch nicht sicher gespeichert.</p><button type="button" className="wm-button" onClick={onRefresh}>Bearbeitung schließen und Stand prüfen</button><button type="button" className="wm-button" onClick={() => setDiscardWarning(false)}>Weiter bearbeiten</button></div>}
        </form>
      </div>
    </DialogContent>
  </Dialog>
}
