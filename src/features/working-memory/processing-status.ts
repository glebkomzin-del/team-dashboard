export type ProcessingStatusKind = 'not-configured' | 'configured' | 'running' | 'paused' | 'unknown'

export interface ProcessingStatus {
  kind: ProcessingStatusKind
  message: string
}

const reasons: Record<string, string> = {
  historical_source_requires_direct_review: 'Ein älteres Meeting wird direkt geprüft und nicht erneut von der KI ausgewertet.',
  legacy_requires_direct_review: 'Ein älteres Meeting wird direkt geprüft und nicht erneut von der KI ausgewertet.',
  changed_source_requires_review: 'Das Original wurde geändert. Die Folgen für bestehende Aussagen müssen geprüft werden.',
  late_source_requires_review: 'Dieses Meeting gehört zeitlich vor bereits ausgewertete Quellen. Der Verlauf muss abgeglichen werden.',
  context_changed: 'Der Arbeitsstand wurde während der Auswertung geändert. Das gespeicherte Ergebnis wartet auf Abgleich.',
  provider_outcome_unknown: 'Der Ausgang einer KI-Anfrage ist unklar. Sie wird nicht automatisch erneut bezahlt.',
  provider_usage_exceeded_reservation: 'Die gemeldeten KI-Kosten übersteigen die Reservierung. Weitere Anfragen sind angehalten.',
  budget_exceeded: 'Das verbleibende Budget reicht für den nächsten vollständigen Prüfschritt nicht aus.',
  validation_failed: 'Das Ergebnis hat die Prüfung nicht bestanden. Es wurde nicht in den Arbeitsstand übernommen.',
  transport_failed: 'Eine Speicherbestätigung fehlt. Vor einer Fortsetzung wird das gespeicherte Ergebnis geprüft.',
  pipeline_changed: 'Die laufenden Verarbeitungsregeln stimmen nicht mit der freigegebenen Konfiguration überein. Die Einrichtung muss vor der Fortsetzung abgeglichen werden.',
  earlier_job_failed: 'Ein früheres Meeting konnte nicht abgeschlossen werden. Spätere Meetings warten auf seine Prüfung.',
  attempt_limit: 'Der Lauf konnte nach mehreren Versuchen nicht abgeschlossen werden. Eine kontrollierte Fortsetzung ist erforderlich.',
  job_policy_changed: 'Die Freigabegrenze oder Verarbeitungsregeln passen nicht mehr zu diesem Lauf.',
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
  if (workerState === 'paused' || workerState === 'disabled') {
    return { kind: 'paused', message: 'Automatische Verarbeitung ist angehalten.' }
  }
  if (['waiting', 'running', 'prepared', 'applied'].includes(workerState || '')) {
    return { kind: 'running', message: 'Automatische Verarbeitung läuft.' }
  }
  return { kind: 'unknown', message: 'Der Status der automatischen Verarbeitung ist gerade unbekannt.' }
}

export function hasReviewBlocker(jobs: ReadonlyArray<{ state: string }> | undefined) {
  return jobs?.[0]?.state === 'review'
}

export function processingReason(reason: string | null | undefined) {
  if (!reason) return
  return reasons[reason] || 'Eine Prüfung ist erforderlich, bevor die Verarbeitung fortgesetzt werden kann.'
}
