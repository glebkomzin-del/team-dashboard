export type ProcessingStatusKind = 'not-configured' | 'configured' | 'running' | 'waiting' | 'paused' | 'unknown'

export interface ProcessingStatus {
  kind: ProcessingStatusKind
  message: string
}

const reasons: Record<string, string> = {
  earlier_job_leased: 'Ein bestehender Verarbeitungslauf belegt die frühere Quelle. Weitere Verarbeitung wartet; ein Abschluss oder Fortschritt ist damit noch nicht bestätigt.',
  worker_transient: 'Im Verarbeitungslauf ist eine vorübergehende technische Störung gemeldet. Eine Fortsetzung ist noch nicht bestätigt.',
  storage_unavailable: 'Der Datenzugang ist derzeit nicht verfügbar. Die Verarbeitung ist noch nicht als fortgesetzt bestätigt.',
  unexpected_worker_error: 'Im Verarbeitungslauf ist ein unerwarteter technischer Fehler aufgetreten. Ein Abschluss ist nicht bestätigt.',
  historical_source_requires_direct_review: 'Ein älteres Meeting wird direkt geprüft und nicht erneut von der KI ausgewertet.',
  legacy_requires_direct_review: 'Ein älteres Meeting wird direkt geprüft und nicht erneut von der KI ausgewertet.',
  changed_source_requires_review: 'Das Original wurde geändert. Die Folgen für bestehende Aussagen müssen geprüft werden.',
  late_source_requires_review: 'Dieses Meeting gehört zeitlich vor bereits ausgewertete Quellen. Der Verlauf muss abgeglichen werden.',
  context_changed: 'Der Arbeitsstand wurde während der Auswertung geändert. Das gespeicherte Ergebnis wartet auf Abgleich.',
  provider_shared_failure: 'Der KI-Dienst hat die Anfrage abgewiesen oder ist derzeit nicht verfügbar. Weitere Verarbeitung ist angehalten.',
  provider_outcome_unknown: 'Der Ausgang einer KI-Anfrage ist unklar. Sie wird nicht automatisch erneut bezahlt.',
  provider_usage_exceeded_reservation: 'Die gemeldeten KI-Kosten übersteigen die Reservierung. Weitere Anfragen sind angehalten.',
  budget_exceeded: 'Das verbleibende Budget reicht für den nächsten vollständigen Prüfschritt nicht aus.',
  validation_failed: 'Das Ergebnis hat die Prüfung nicht bestanden. Es wurde nicht in den Arbeitsstand übernommen.',
  transport_failed: 'Eine Speicherbestätigung fehlt. Vor einer Fortsetzung wird das gespeicherte Ergebnis geprüft.',
  pipeline_changed: 'Die laufenden Verarbeitungsregeln stimmen nicht mit der freigegebenen Konfiguration überein. Die Einrichtung muss vor der Fortsetzung abgeglichen werden.',
  earlier_job_failed: 'Ein früheres Meeting konnte nicht abgeschlossen werden. Spätere Meetings warten auf seine Prüfung.',
  attempt_limit: 'Der Lauf konnte nach mehreren Versuchen nicht abgeschlossen werden. Eine kontrollierte Fortsetzung ist erforderlich.',
  job_policy_changed: 'Konfiguration, Verarbeitungsregeln oder Quelldatum passen nicht mehr zu diesem Lauf. Vor der Fortsetzung ist ein kontrollierter Abgleich erforderlich.',
  same_source_review: 'Ein früherer Verarbeitungsschritt desselben Originals ist noch ungeklärt. Prüfe diesen Schritt vor der Fortsetzung.',
  unknown_job_state: 'Der Zustand eines früheren Meetings ist unklar. Vor der Fortsetzung ist eine Prüfung erforderlich.',
}

export function processingStatus(configEnabled: boolean | null | undefined, workerState: string | undefined): ProcessingStatus {
  if (configEnabled === null) {
    return { kind: 'not-configured', message: 'Automatische Verarbeitung ist nicht eingerichtet.' }
  }
  if (configEnabled === false) {
    return { kind: 'paused', message: 'Automatische Verarbeitung ist ausgeschaltet.' }
  }
  if (configEnabled !== true) {
    return { kind: 'unknown', message: 'Der Status der automatischen Verarbeitung ist gerade unbekannt.' }
  }
  if (workerState === 'idle') {
    return { kind: 'configured', message: 'Automatische Verarbeitung ist eingerichtet und wartet auf neue Meetings.' }
  }
  if (workerState === 'starting' || workerState === 'ready') {
    return { kind: 'configured', message: 'Automatische Verarbeitung ist eingerichtet und wird gestartet.' }
  }
  if (workerState === 'disabled') return { kind: 'unknown', message: 'Automatik ist eingeschaltet; der gemeldete ausgeschaltete Workerstatus bestätigt den aktuellen Verarbeitungsstand nicht.' }
  if (workerState === 'paused') {
    return { kind: 'paused', message: 'Automatische Verarbeitung ist angehalten.' }
  }
  if (workerState === 'waiting') return { kind: 'waiting', message: 'Automatik ist eingeschaltet und wartet auf den nächsten Verarbeitungsschritt. Ein Abschluss ist noch nicht bestätigt.' }
  if (['running', 'prepared', 'applied'].includes(workerState || '')) {
    return { kind: 'running', message: 'Ein Verarbeitungslauf ist gemeldet. Noch unvollständige Quellen sind getrennt aufgeführt.' }
  }
  return { kind: 'unknown', message: 'Der Status der automatischen Verarbeitung ist gerade unbekannt.' }
}

export interface ProcessingJob {
  id: string; title?: string; event_date: string; state: string; reason: string | null; technical_isolation?: boolean
}
export interface Processing {
  config: { enabled: boolean; automatic_from: string | null; budget_micro_usd: number | null } | null
  accounted_micro_usd: number; pending_count: number; archived_count?: number; isolated_count?: number
  jobs: ProcessingJob[]
  blocking_job?: (ProcessingJob & { source_id: string }) | null
}
export interface Operations {
  processing?: Processing; worker: { state: string; reason?: string; job_id?: string; error_type?: string; transient?: boolean; retryable?: boolean; retry_in_seconds?: number; previous_transient?: { error_type?: string } }; mode: string; model?: string; read_only?: boolean
  backup?: { state: string; last_success_at?: string | null; stale?: boolean }
  offserver_backup?: { state: string; last_success_at?: string | null; last_backup_at?: string | null; stale?: boolean }
}

export function hasReviewBlocker(jobs: ReadonlyArray<{ state: string; technical_isolation?: boolean }> | undefined) {
  return jobs?.find(job => job.technical_isolation !== true)?.state === 'review'
}

export function processingFence(processing: Processing | undefined): boolean | undefined {
  if (!processing) return
  if (Object.prototype.hasOwnProperty.call(processing, 'blocking_job')) {
    if (processing.blocking_job === null) return false
    const job = processing.blocking_job
    if (job && typeof job.id === 'string' && typeof job.state === 'string' && job.technical_isolation === false) return true
    return
  }
  // Older contracts can only establish the first candidate within the displayed slice.
  if (!processing.jobs.some(job => job.technical_isolation !== true) && processing.pending_count > processing.jobs.length) return
  return hasReviewBlocker(processing.jobs)
}

export function operationsStatus(operations: Operations | undefined): ProcessingStatus {
  const processing = operations?.processing
  let status = processingStatus(processing === undefined ? undefined : processing.config?.enabled ?? null, operations?.worker.state)
  if (processing?.config?.enabled === true && operations?.worker.state === 'disabled' && (operations.read_only === true || operations.mode === 'readonly')) status = { kind: 'paused', message: 'Automatische Verarbeitung ist im Lesemodus ausgeschaltet.' }
  if (processing?.config?.enabled === true && (status.kind !== 'unknown' || operations?.worker.state === 'disabled')) {
    const fence = processingFence(processing)
    if (fence === true) return { kind: 'paused', message: 'Weitere Quellen warten auf die Klärung eines nicht isolierten Verarbeitungsschritts.' }
    if (fence === undefined && status.kind !== 'paused') return { kind: 'unknown', message: 'Ob eine weitere Quelle die Verarbeitung blockiert, ist derzeit nicht bestätigt.' }
  }
  if (status.kind === 'configured' && operations?.worker.state === 'idle' && processing && processing.pending_count > 0) return { kind: 'waiting', message: 'Automatik ist eingeschaltet. Quellen sind noch unvollständig; aktuell ist kein aktiver Verarbeitungslauf gemeldet.' }
  if (status.kind === 'waiting' && operations?.worker.previous_transient) return { ...status, message: `${status.message} Eine frühere technische Unterbrechung ist gemeldet; ihre Behebung ist noch nicht bestätigt.` }
  return status
}

export function isolationMessage(processing: Processing | undefined): string {
  const count = processing?.isolated_count
  if (!Number.isInteger(count) || count === undefined || count < 0) return 'Der Stand der technischen Isolation ist unbekannt.'
  if (!count) return 'Keine technisch isolierten Quellen.'
  return `${count} Quelle${count === 1 ? ' ist' : 'n sind'} technisch isoliert und noch nicht vollständig übernommen. Diese Isolation allein hält die übrige Warteschlange nicht an.`
}


export function processingReason(reason: string | null | undefined) {
  if (!reason) return
  return reasons[reason] || 'Der technische Grund ist noch nicht eingeordnet. Prüfe den Verarbeitungsstand.'
}
