import { useEffect, useState } from 'react'
import { dateLabel, getMemory, numberLabel } from './types'
import { RecoveryDialog } from './RecoveryDialog'
import { GenerationReviews } from './GenerationReviews'
import { hasReviewBlocker, processingReason, processingStatus } from './processing-status'

interface Processing {
  config: { enabled: boolean; automatic_from: string | null; budget_micro_usd: number | null } | null
  accounted_micro_usd: number
  pending_count: number
  archived_count?: number
  jobs: { id: string; title?: string; event_date: string; state: string; reason: string | null }[]
}
interface Operations { processing?: Processing; worker: { state: string; reason?: string }; mode: string; model?: string; read_only?: boolean
  backup?: { state: string; last_success_at?: string | null; stale?: boolean }
  offserver_backup?: { state: string; last_success_at?: string | null; last_backup_at?: string | null; stale?: boolean } }
const money = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const states: Record<string, string> = { queued: 'Wartet auf Verarbeitung', running: 'Wird ausgewertet', prepared: 'Ergebnis geprüft, Speicherung läuft', review: 'Verarbeitung angehalten' }
const backupState = (state: string, stale?: boolean) => stale ? 'muss geprüft werden' : state === 'running' ? 'läuft gerade' : state === 'failed' ? 'muss geprüft werden' : state === 'unavailable' ? 'ist gerade nicht prüfbar' : state === 'not_configured' ? 'ist noch nicht eingerichtet' : 'ist eingerichtet'

export function ProcessingPanel({ onChanged, expanded = true, showJobs = true }: { onChanged?: () => void; expanded?: boolean; showJobs?: boolean }) {
  const [open, setOpen] = useState(expanded)
  const [attempt, setAttempt] = useState(0)
  const [selectedJob, setSelectedJob] = useState<string>()
  const [result, setResult] = useState<{ attempt: number; data?: Operations; error?: string }>()
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    getMemory<Operations>('/operations', controller.signal).then(data => {
      if (!data.worker || (data.processing && (!Array.isArray(data.processing.jobs) || !Number.isFinite(data.processing.accounted_micro_usd)))) throw new Error('Ungültiger Betriebsstand')
      setResult({ attempt, data })
    }).catch(() => { if (!controller.signal.aborted) setResult({ attempt, error: 'Der Verarbeitungsstand ist gerade nicht erreichbar. Bitte erneut versuchen.' }) })
    return () => controller.abort()
  }, [open, attempt])
  const current = result?.attempt === attempt ? result : undefined
  const processing = current?.data?.processing
  const automaticStatus = processingStatus(processing === undefined ? undefined : processing.config?.enabled ?? null, current?.data?.worker.state)
  const workerReason = automaticStatus.kind === 'paused' ? processingReason(current?.data?.worker.reason) : undefined
  const reviewBlocker = hasReviewBlocker(processing?.jobs)
  return <section className="wm-panel"><details open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{showJobs ? 'Betrieb · fachliche und technische Prüfungen' : 'Verarbeitung, Kosten und Sicherungen'}</summary>
    {open && <>
      {!current && <p role="status">Verarbeitungsstand wird geladen…</p>}
      {current?.error && <p role="alert">{current.error}</p>}
      {current?.data && <>
        {showJobs && <section className="wm-processing-section" aria-labelledby="fachliche-pruefungen"><h2 id="fachliche-pruefungen">Fachliche Prüfungen</h2><p className="wm-muted">Hier entscheidest du, ob vorbereitete inhaltliche Änderungen in den Arbeitsstand übernommen werden.</p><GenerationReviews attempt={attempt} readOnly={current.data.read_only} onSaved={() => { setAttempt(value => value + 1); onChanged?.() }} /></section>}
        {showJobs && <div className="wm-processing-section"><h2>Technischer Betrieb</h2><p className="wm-muted">Hier prüfst du angehaltene oder unvollständige Verarbeitungsschritte.</p></div>}
        <p role={showJobs && ['paused', 'unknown'].includes(automaticStatus.kind) ? 'alert' : undefined} className={showJobs && ['paused', 'unknown'].includes(automaticStatus.kind) ? 'wm-note' : undefined}>{automaticStatus.message}</p>
        {showJobs && workerReason && <p className="wm-note">Grund: {workerReason}</p>}
        {current.data.model && <p className="wm-muted">Modell: {current.data.model === 'gpt-5.6-terra' ? 'GPT-5.6 Terra' : current.data.model}.</p>}
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
          {showJobs && processing.jobs.map(job => <article className="wm-row" key={job.id}><h3>{job.title || `Meeting vom ${dateLabel(job.event_date)}`}</h3><p>{states[job.state] || 'Verarbeitung wird geprüft'}</p>{job.reason && <p className="wm-note">{processingReason(job.reason)}</p>}{!current.data?.read_only && job.state !== 'queued' && <button type="button" className="wm-button" onClick={() => setSelectedJob(job.id)}>Verarbeitung prüfen</button>}</article>)}
          {showJobs && (processing.pending_count > processing.jobs.length || reviewBlocker) && <p className="wm-muted">{processing.pending_count > processing.jobs.length && <>Die frühesten {numberLabel(processing.jobs.length)} Quellen werden angezeigt. </>}Ein angehaltener früherer Schritt verhindert, dass spätere Meetings mit unvollständigem Kontext verarbeitet werden.</p>}
        </>}
      </>}
      {current && <button type="button" className="wm-button" onClick={() => setAttempt(value => value + 1)}>Verarbeitungsstand aktualisieren</button>}
    </>}
  </details>{selectedJob && <RecoveryDialog key={selectedJob} jobId={selectedJob} onClose={() => setSelectedJob(undefined)} onSaved={() => { setSelectedJob(undefined); setAttempt(value => value + 1); onChanged?.() }} />}</section>
}
