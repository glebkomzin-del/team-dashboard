import { useEffect, useState } from 'react'
import { dateLabel, getMemory, numberLabel } from './types'
import { RecoveryDialog } from './RecoveryDialog'
import { GenerationReviews } from './GenerationReviews'
import { isolationMessage, operationsStatus, processingFence, processingReason } from './processing-status'
import type { Operations } from './processing-status'

const money = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const states: Record<string, string> = { queued: 'Wartet auf Verarbeitung', running: 'Verarbeitungslauf belegt · Abschluss noch unbestätigt', prepared: 'Ergebnis geprüft, Speicherung läuft', review: 'Verarbeitung wartet auf Klärung' }
const backupState = (state: string, stale?: boolean) => stale ? 'muss geprüft werden' : state === 'running' ? 'läuft gerade' : state === 'failed' ? 'muss geprüft werden' : state === 'unavailable' ? 'ist gerade nicht prüfbar' : state === 'not_configured' ? 'ist noch nicht eingerichtet' : 'ist eingerichtet'

export function ProcessingPanel({ onChanged, expanded = true, showJobs = true }: { onChanged?: () => void; expanded?: boolean; showJobs?: boolean }) {
  const [open, setOpen] = useState(expanded)
  const [attempt, setAttempt] = useState(0)
  const [selectedJob, setSelectedJob] = useState<string>()
  const [result, setResult] = useState<{ attempt: number; data?: Operations; error?: string; checkedAt: string }>()
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    getMemory<Operations>('/operations', controller.signal).then(data => {
      if (!data.worker || (data.processing && (!Array.isArray(data.processing.jobs) || !Number.isFinite(data.processing.accounted_micro_usd)))) throw new Error('Ungültiger Betriebsstand')
      setResult({ attempt, data, checkedAt: new Date().toISOString() })
    }).catch(error => { if (!controller.signal.aborted) setResult({ attempt, error: error instanceof Error ? error.message : 'Der Verarbeitungsstand ist gerade nicht erreichbar. Bitte erneut versuchen.', checkedAt: new Date().toISOString() }) })
    return () => controller.abort()
  }, [open, attempt])
  const current = result?.attempt === attempt ? result : undefined
  const processing = current?.data?.processing
  const automaticStatus = operationsStatus(current?.data)
  const aggregateBlocker = processingFence(processing) === true ? processing?.blocking_job : undefined
  const workerReason = ['paused', 'unknown', 'waiting'].includes(automaticStatus.kind) ? processingReason(current?.data?.worker.reason || aggregateBlocker?.reason || processing?.jobs.find(job => job.technical_isolation !== true)?.reason) : undefined
  return <section className="wm-panel" style={{ overflowWrap: 'anywhere' }}><details open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{showJobs ? 'Betrieb · fachliche und technische Prüfungen' : 'Verarbeitung, Kosten und Sicherungen'}</summary>
    {open && <>
      {!current && <p role="status">Verarbeitungsstand wird geladen…</p>}
      {current?.error && <><p role="alert">{current.error}</p><p className="wm-muted">Letzter Abrufversuch: {new Date(current.checkedAt).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin' })}.</p></>}
      {current?.data && <>
        {showJobs && <section className="wm-processing-section" aria-labelledby="fachliche-pruefungen"><h2 id="fachliche-pruefungen">Fachliche Prüfungen</h2><p className="wm-muted">Hier entscheidest du, ob vorbereitete inhaltliche Änderungen in den Arbeitsstand übernommen werden.</p><GenerationReviews attempt={attempt} readOnly={current.data.read_only} onSaved={() => { setAttempt(value => value + 1); onChanged?.() }} /></section>}
        {showJobs && <div className="wm-processing-section"><h2>Technischer Betrieb</h2><p className="wm-muted">Hier prüfst du angehaltene oder unvollständige Verarbeitungsschritte.</p></div>}
        <p role={['paused', 'unknown'].includes(automaticStatus.kind) ? 'alert' : automaticStatus.kind === 'waiting' ? 'status' : undefined} className={['paused', 'unknown', 'waiting'].includes(automaticStatus.kind) ? 'wm-note' : undefined}>{automaticStatus.message}</p>
        {workerReason && <p className="wm-note">Grund: {workerReason}{current.data.worker.reason && <> <small>Technischer Grund: <code>{current.data.worker.reason}</code>.</small></>}</p>}
        {current.data.worker.error_type && <p className="wm-note">Gemeldeter technischer Fehler: <code>{current.data.worker.error_type}</code>.{current.data.worker.transient === true && ' Eine vorübergehende Störung ist gemeldet; eine Fortsetzung ist noch nicht bestätigt.'}</p>}
        {current.data.worker.previous_transient && <p className="wm-note">Frühere technische Unterbrechung: {current.data.worker.previous_transient.error_type ? <code>{current.data.worker.previous_transient.error_type}</code> : 'Fehlertyp nicht angegeben'}. Ihre Behebung ist noch nicht bestätigt.</p>}
        <p className="wm-muted">Letzter bestätigter Abruf: {new Date(current.checkedAt).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin' })}. Dieser Betriebsstand wird mit „Verarbeitungsstand aktualisieren“ neu geladen.</p>
        {current.data.model && <p className="wm-muted">Modell: {current.data.model === 'gpt-5.6-terra' ? 'GPT-5.6 Terra' : current.data.model === 'gpt-6.1-sol' ? 'GPT-6.1 Sol' : current.data.model}.</p>}
        {showJobs && current.data.backup && <div className="wm-row">
          <h3>Sicherung</h3>
          {current.data.backup.last_success_at && <p>Zuletzt vollständig geprüft: {new Date(current.data.backup.last_success_at).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin' })}.</p>}
          {current.data.backup.state === 'running' && <p role="status">Sicherung und Wiederherstellungsprüfung laufen.</p>}
          {current.data.backup.state === 'failed' && <p role="alert" className="wm-note">Die letzte Sicherung ist fehlgeschlagen. Frühere geprüfte Sicherungen bleiben erhalten.</p>}
          {current.data.backup.stale && <p role="alert" className="wm-note">Seit mehr als 36 Stunden wurde keine erfolgreiche Sicherung bestätigt.</p>}
          {current.data.backup.state === 'unavailable' && <p role="alert" className="wm-note">Der Sicherungsstatus kann gerade nicht geprüft werden.</p>}
          {current.data.backup.state === 'not_configured' && <p className="wm-muted">Regelmäßige Sicherungen sind für diesen Entwurf noch nicht eingerichtet.</p>}
        </div>}
        {showJobs && current.data.offserver_backup && <div className="wm-row">
          <h3>Zweite Sicherung auf deinem Mac</h3>
          {current.data.offserver_backup.last_backup_at && <p>Sicherungsstand: {new Date(current.data.offserver_backup.last_backup_at).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin' })}.</p>}
          {current.data.offserver_backup.last_success_at && <p className="wm-muted">Kopie zuletzt geprüft: {new Date(current.data.offserver_backup.last_success_at).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin' })}.</p>}
          {current.data.offserver_backup.stale && <p role="alert" className="wm-note">Die zweite Kopie ist älter als 36 Stunden. Dein Mac muss online sein, damit sie aktualisiert wird.</p>}
          {['failed', 'unavailable'].includes(current.data.offserver_backup.state) && <p role="alert" className="wm-note">Die zweite Sicherungskopie kann gerade nicht bestätigt werden.</p>}
          {current.data.offserver_backup.state === 'not_configured' && <p className="wm-muted">Eine zweite Sicherung außerhalb des Servers ist noch nicht bestätigt.</p>}
        </div>}
        {!showJobs && (current.data.backup || current.data.offserver_backup) && <div className="wm-row"><h3>Sicherungen</h3>{current.data.backup && <p>Serversicherung {backupState(current.data.backup.state, current.data.backup.stale)}{current.data.backup.last_success_at ? ` · zuletzt geprüft ${new Date(current.data.backup.last_success_at).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin' })}` : ''}.</p>}{current.data.offserver_backup && <p>Zweite Sicherung {backupState(current.data.offserver_backup.state, current.data.offserver_backup.stale)}{current.data.offserver_backup.last_backup_at ? ` · Stand ${new Date(current.data.offserver_backup.last_backup_at).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin' })}` : ''}.</p>}</div>}
        {processing?.config?.automatic_from && <p className="wm-muted">Automatisch ausgewertet werden neue Quellen ab {dateLabel(processing.config.automatic_from)}. Ältere Originale bleiben ohne erneute KI-Auswertung erhalten.</p>}
        {processing && <>
          <p>{processing.pending_count === 1 ? 'Eine neue Quelle ist noch nicht vollständig verarbeitet.' : processing.pending_count ? `${numberLabel(processing.pending_count)} neue Quellen sind noch nicht vollständig verarbeitet.` : 'Keine neuen Quellen in der Warteschlange.'}</p>
          {processing.config && <p>Reserviert oder verbraucht: <strong>{money.format(processing.accounted_micro_usd / 1_000_000)}</strong>{processing.config.budget_micro_usd === null ? ' · Keine Kostenobergrenze.' : ` von ${money.format(processing.config.budget_micro_usd / 1_000_000)}.`}</p>}
          {processing.accounted_micro_usd > 0 && <p className="wm-muted">Bei unklaren Kosten bleibt die volle Reservierung angerechnet. Der Betrag ist eine Kostenübersicht, keine Anbieterrechnung.</p>}
          {!!processing.archived_count && <p className="wm-muted">{numberLabel(processing.archived_count)} Quellen werden nur im Archiv behalten.</p>}
          <p className="wm-note">{isolationMessage(processing)}</p>
          <h2>Technische Verarbeitung</h2>
          {aggregateBlocker && !processing.jobs.some(job => job.id === aggregateBlocker.id) && <article className="wm-row"><h3>{aggregateBlocker.title || 'Blockierende Quelle'}</h3><p>Weitere Verarbeitung ist angehalten. Diese Quelle liegt außerhalb des angezeigten Ausschnitts.</p>{aggregateBlocker.reason && <p className="wm-note">{processingReason(aggregateBlocker.reason)} <small>Technischer Grund: <code>{aggregateBlocker.reason}</code>.</small></p>}{!current.data?.read_only && <button type="button" className="wm-button" onClick={() => setSelectedJob(aggregateBlocker.id)}>Verarbeitung prüfen / wiederaufnehmen</button>}</article>}
          {processing.jobs.map(job => <article className="wm-row" key={job.id}><h3>{job.title || `Meeting vom ${dateLabel(job.event_date)}`}</h3><p>{job.technical_isolation === true ? 'Technisch isoliert · noch nicht vollständig übernommen' : states[job.state] || 'Verarbeitung wird geprüft'}</p>{job.reason && <p className="wm-note">{processingReason(job.reason)} <small>Technischer Grund: <code>{job.reason}</code>.</small></p>}{!current.data?.read_only && job.state !== 'queued' && <button type="button" className="wm-button" onClick={() => setSelectedJob(job.id)}>Verarbeitung prüfen / wiederaufnehmen</button>}</article>)}
          {processing.pending_count > processing.jobs.length && <p className="wm-muted">Die frühesten {numberLabel(processing.jobs.length)} unvollständigen Quellen werden angezeigt. Insgesamt warten noch {numberLabel(processing.pending_count)} Quellen.</p>}
        </>}
      </>}
      {current && <button type="button" className="wm-button" onClick={() => setAttempt(value => value + 1)}>Verarbeitungsstand aktualisieren</button>}
    </>}
  </details>{selectedJob && <RecoveryDialog key={selectedJob} jobId={selectedJob} onClose={() => setSelectedJob(undefined)} onSaved={() => { setSelectedJob(undefined); setAttempt(value => value + 1); onChanged?.() }} />}</section>
}
