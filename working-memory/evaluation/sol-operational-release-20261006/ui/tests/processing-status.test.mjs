import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hasReviewBlocker, isolationMessage, operationsStatus, processingFence, processingReason, processingStatus } from '../src/features/working-memory/processing-status.ts'

test('processing status distinguishes configuration, activity, pauses and unknown states', () => {
  assert.equal(processingStatus(null, 'disabled').kind, 'not-configured')
  assert.deepEqual(processingStatus(false, 'disabled'), { kind: 'paused', message: 'Automatische Verarbeitung ist ausgeschaltet.' })
  assert.equal(processingStatus(true, 'idle').kind, 'configured')
  assert.equal(processingStatus(true, 'starting').kind, 'configured')
  assert.equal(processingStatus(true, 'ready').kind, 'configured')
  assert.equal(processingStatus(true, 'running').kind, 'running')
  assert.equal(processingStatus(true, 'paused').kind, 'paused')
  assert.equal(processingStatus(true, 'disabled').kind, 'unknown')
  assert.equal(processingStatus(true, 'unavailable').kind, 'unknown')
  assert.equal(processingStatus(true, 'unexpected').kind, 'unknown')
})

test('only a review at the head of the chronological queue blocks later jobs', () => {
  assert.equal(hasReviewBlocker([
    { state: 'review' },
    { state: 'queued' },
    { state: 'queued' },
    { state: 'queued' },
  ]), true)
  assert.equal(hasReviewBlocker([{ state: 'queued' }, { state: 'review' }]), false)
  assert.equal(hasReviewBlocker([]), false)
})

test('worker pause reasons use the same human-readable explanations as review jobs', () => {
  assert.match(processingReason('pipeline_changed'), /freigegebenen Konfiguration/)
  assert.equal(processingReason('context_changed'), 'Der Arbeitsstand wurde während der Auswertung geändert. Das gespeicherte Ergebnis wartet auf Abgleich.')
  assert.equal(processingReason('new_reason'), 'Der technische Grund ist noch nicht eingeordnet. Prüfe den Verarbeitungsstand.')
})

const job = (state, technical_isolation) => ({ id: state, event_date: '2026-10-06', state, reason: state === 'review' ? 'validation_failed' : null, ...(technical_isolation === undefined ? {} : { technical_isolation }) })
const operations = (jobs, { enabled = true, worker = 'running', isolated_count = 1 } = {}) => ({
  mode: 'production', worker: { state: worker },
  processing: { config: { enabled, automatic_from: '2026-09-08', budget_micro_usd: null }, accounted_micro_usd: 0, pending_count: jobs.length, isolated_count, jobs },
})

test('only positively proved isolation lets the next valid source continue', () => {
  // Valid A already completed; failed B remains incomplete while valid C runs.
  assert.equal(operationsStatus(operations([job('review', true), job('running', false)])).kind, 'running')
  assert.equal(operationsStatus(operations([job('review', true), job('queued', false)], { worker: 'ready' })).kind, 'configured')
  for (const isolation of [false, undefined, null, 'true']) {
    assert.equal(operationsStatus(operations([job('review', isolation), job('queued', false)])).kind, 'paused')
  }
  // A reason, zero reported errors or a successful worker alone is not isolation proof.
  assert.equal(operationsStatus(operations([{ ...job('review'), reason: 'context_changed' }, job('queued')])).kind, 'paused')
})

test('isolated sources cannot hide disabled processing, a shared outage or a later global fence', () => {
  assert.equal(operationsStatus(operations([job('review', true), job('queued')], { enabled: false })).kind, 'paused')
  assert.equal(operationsStatus(operations([job('review', true), job('queued')], { worker: 'paused' })).kind, 'paused')
  assert.equal(operationsStatus(operations([job('review', true), job('queued')], { worker: 'unavailable' })).kind, 'unknown')
  assert.equal(operationsStatus(undefined).kind, 'unknown')
  assert.equal(operationsStatus(operations([job('review', true), { ...job('review', false), reason: 'budget_exceeded' }, job('queued')])).kind, 'paused')
  assert.equal(hasReviewBlocker([job('review', true), job('queued'), job('review', false)]), false)
})

test('isolation count reports incomplete results and does not claim successful application', () => {
  const processing = operations([job('review', true), job('running')]).processing
  assert.match(isolationMessage(processing), /1 Quelle ist technisch isoliert und noch nicht vollständig übernommen/)
  assert.match(isolationMessage(processing), /allein hält die übrige Warteschlange nicht an/)
  assert.equal(isolationMessage({ ...processing, isolated_count: 0 }), 'Keine technisch isolierten Quellen.')
  for (const count of [undefined, null, -1, 1.5, '1']) assert.equal(isolationMessage({ ...processing, isolated_count: count }), 'Der Stand der technischen Isolation ist unbekannt.')
})

test('technical reasons preserve unknown paid outcomes and raw-code-compatible fallback', () => {
  assert.match(processingReason('provider_outcome_unknown'), /nicht automatisch erneut bezahlt/)
  assert.match(processingReason('validation_failed'), /nicht in den Arbeitsstand übernommen/)
  assert.match(processingReason('attempt_limit'), /kontrollierte Fortsetzung/)
  assert.equal(processingReason(undefined), undefined)
})


test('a positively known shared provider failure stops an enabled queue and is never inferred as source isolation', () => {
  const failed = { ...job('review', false), reason: 'provider_shared_failure' }
  assert.equal(operationsStatus(operations([failed, job('queued')], { enabled: true, worker: 'running', isolated_count: 0 })).kind, 'paused')
  assert.match(processingReason(failed.reason), /KI-Dienst hat die Anfrage abgewiesen/)
  assert.match(processingReason(failed.reason), /Verarbeitung ist angehalten/)
})


const hiddenBlocker = reason => ({ ...job('review', false), id: 'hidden-blocker', source_id: 'source-hidden', title: 'Nicht im Ausschnitt sichtbare Quelle', reason })
const isolatedSlice = () => {
  const data = operations(Array.from({ length: 100 }, (_, id) => ({ ...job('review', true), id: `isolated-${id}` })), { isolated_count: 100 })
  data.processing.pending_count = 101
  return data
}

test('the full-queue blocker remains visible even behind 100 isolated displayed sources', () => {
  const data = isolatedSlice()
  data.processing.blocking_job = hiddenBlocker('provider_shared_failure')
  assert.equal(processingFence(data.processing), true)
  assert.equal(operationsStatus(data).kind, 'paused')
  assert.equal(data.processing.jobs.some(job => job.id === data.processing.blocking_job.id), false)
})

test('an explicit null proves no blocking candidate; a later review does not create a global stop', () => {
  const data = isolatedSlice()
  data.processing.blocking_job = null
  assert.equal(processingFence(data.processing), false)
  assert.equal(operationsStatus(data).kind, 'running')
  const ordered = operations([job('queued', false), job('review', false)], { isolated_count: 0 })
  ordered.processing.blocking_job = null
  assert.equal(operationsStatus(ordered).kind, 'running')
  ordered.processing.config.enabled = false
  assert.equal(operationsStatus(ordered).kind, 'paused')
})

test('missing, unknown and malformed aggregate evidence never becomes confirmed null', () => {
  const legacy = isolatedSlice()
  assert.equal(processingFence(legacy.processing), undefined)
  assert.equal(operationsStatus(legacy).kind, 'unknown')
  for (const value of [undefined, false, {}, { ...hiddenBlocker('validation_failed'), technical_isolation: true }]) {
    legacy.processing.blocking_job = value
    assert.equal(processingFence(legacy.processing), undefined)
    assert.equal(operationsStatus(legacy).kind, 'unknown')
  }
  const visibleLegacy = operations([job('review', false), job('queued')], { isolated_count: 0 })
  assert.equal(operationsStatus(visibleLegacy).kind, 'paused')
})

test('a queued aggregate blocker still stops on policy mismatch or an unresolved step of the same source', () => {
  for (const reason of ['job_policy_changed', 'same_source_review']) {
    const data = operations([job('queued', false)], { isolated_count: 0 })
    data.processing.blocking_job = { ...hiddenBlocker(reason), state: 'queued' }
    assert.equal(operationsStatus(data).kind, 'paused')
    assert.notEqual(processingReason(reason), processingReason('unknown-code'))
  }
})


test('an existing lease is waiting, not proof of model work, application or a required content review', () => {
  const data = operations([job('running', false), job('queued', false)], { worker: 'waiting', isolated_count: 0 })
  data.worker.reason = 'earlier_job_leased'
  data.worker.job_id = 'running'
  data.processing.blocking_job = null
  assert.equal(operationsStatus(data).kind, 'waiting')
  assert.match(operationsStatus(data).message, /Abschluss ist noch nicht bestätigt/)
  assert.match(processingReason(data.worker.reason), /bestehender Verarbeitungslauf/)
  assert.doesNotMatch(processingReason(data.worker.reason), /Prüfung ist erforderlich/)
  data.processing.config.enabled = false
  assert.equal(operationsStatus(data).kind, 'paused')
})

test('waiting never hides an actual full-set blocker or unproved aggregate', () => {
  const data = isolatedSlice()
  data.worker = { state: 'waiting', reason: 'earlier_job_leased' }
  data.processing.blocking_job = hiddenBlocker('provider_shared_failure')
  assert.equal(operationsStatus(data).kind, 'paused')
  delete data.processing.blocking_job
  assert.equal(operationsStatus(data).kind, 'unknown')
})

test('an active configuration and unfinished queue do not prove any progress while idle', () => {
  const data = operations([job('queued', false)], { worker: 'idle', isolated_count: 0 })
  data.processing.blocking_job = null
  assert.equal(operationsStatus(data).kind, 'waiting')
  assert.match(operationsStatus(data).message, /kein aktiver Verarbeitungslauf/)
  data.processing.pending_count = 0
  data.processing.jobs = []
  assert.equal(operationsStatus(data).kind, 'configured')
})

test('storage, unexpected and shared provider failures stay technical, visible and unconfirmed', () => {
  for (const reason of ['storage_unavailable', 'unexpected_worker_error']) {
    const data = operations([job('running', false)], { worker: 'unavailable', isolated_count: 0 })
    data.worker.reason = reason
    assert.equal(operationsStatus(data).kind, 'unknown')
    assert.notEqual(processingReason(reason), processingReason('unknown-case'))
  }
  const data = operations([job('review', false)], { worker: 'paused', isolated_count: 0 })
  data.worker.reason = 'provider_shared_failure'
  data.processing.blocking_job = hiddenBlocker('provider_shared_failure')
  assert.equal(operationsStatus(data).kind, 'paused')
})


test('a retained technical interruption remains unconfirmed during lease waiting without becoming a content review', () => {
  const data = operations([job('running', false)], { worker: 'waiting', isolated_count: 0 })
  data.worker.reason = 'earlier_job_leased'
  data.processing.blocking_job = null
  assert.equal(operationsStatus(data).kind, 'waiting')
  assert.doesNotMatch(operationsStatus(data).message, /frühere technische Unterbrechung/)
  for (const diagnostic of [{ error_type: 'JournalTemporaryUnavailable' }, {}]) {
    data.worker.previous_transient = diagnostic
    assert.equal(operationsStatus(data).kind, 'waiting')
    assert.match(operationsStatus(data).message, /Behebung ist noch nicht bestätigt/)
    assert.doesNotMatch(operationsStatus(data).message, /Prüfung ist erforderlich/)
  }
  data.worker = { state: 'unavailable', reason: 'worker_transient', transient: true }
  assert.equal(operationsStatus(data).kind, 'unknown')
  assert.match(processingReason(data.worker.reason), /technische Störung/)
})


test('an enabled configuration with a preceding disabled worker report never proves a halt or progress', () => {
  const data = operations([job('running', false)], { worker: 'disabled', isolated_count: 0 })
  data.processing.blocking_job = null
  data.processing.accounted_micro_usd = 314144
  assert.equal(operationsStatus(data).kind, 'unknown')
  assert.match(operationsStatus(data).message, /bestätigt den aktuellen Verarbeitungsstand nicht/)
  for (const readOnly of [undefined, false]) {
    data.read_only = readOnly
    assert.equal(operationsStatus(data).kind, 'unknown')
  }
  data.read_only = true
  assert.equal(operationsStatus(data).kind, 'paused')
  delete data.read_only
  data.mode = 'readonly'
  assert.equal(operationsStatus(data).kind, 'paused')
  data.mode = 'production'
  data.processing.blocking_job = hiddenBlocker('provider_shared_failure')
  assert.equal(operationsStatus(data).kind, 'paused')
  data.processing.blocking_job = null
  data.processing.config.enabled = false
  assert.equal(operationsStatus(data).kind, 'paused')
  delete data.processing
  assert.equal(operationsStatus(data).kind, 'unknown')
})
