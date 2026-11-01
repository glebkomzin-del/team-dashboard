import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hasReviewBlocker, isolationMessage, operationsStatus, processingFence, processingJobsBlockerFirst, processingReason, processingStatus } from '../src/features/working-memory/processing-status.ts'

const archiveNow = Date.parse('2026-10-07T00:00:00Z')
const archiveStep = (jobs = []) => {
  const data = operations(jobs, { worker: 'archived', isolated_count: 0 })
  data.read_only = false
  data.worker.reason = 'verified_image_placeholder'
  data.processing.blocking_job = null
  return data
}

test('a verified image archive step is not an unknown fault or proof of queue completion', () => {
  const data = archiveStep([job('queued', false)])
  assert.equal(operationsStatus(data, archiveNow).kind, 'waiting')
  assert.match(operationsStatus(data, archiveNow).message, /noch unvollständig/)
  assert.equal(operationsStatus(archiveStep(), archiveNow).kind, 'configured')
  assert.match(processingReason(data.worker.reason), /ohne KI-Auswertung im Archiv/)
})

test('a real current lease may supersede the last archived image step', () => {
  const active = { ...job('running', false), lease_until: '2026-10-07T00:10:00Z' }
  assert.equal(operationsStatus(archiveStep([active]), archiveNow).kind, 'running')
  for (const lease of [undefined, null, '2026-10-06T23:59:59Z', 'not-a-date', '2026-02-30T00:10:00Z']) {
    assert.equal(operationsStatus(archiveStep([{ ...active, lease_until: lease }]), archiveNow).kind, 'waiting')
  }
  for (const isolation of [undefined, true, 'false']) {
    assert.notEqual(operationsStatus(archiveStep([{ ...active, technical_isolation: isolation }]), archiveNow).kind, 'running')
  }
})

test('archive status requires positive configuration and writing mode, not absence of errors', () => {
  for (const enabled of [false, undefined, null, 'true']) {
    const data = archiveStep([job('queued', false)])
    data.processing.config.enabled = enabled
    assert.notEqual(operationsStatus(data, archiveNow).kind, 'waiting')
    assert.notEqual(operationsStatus(data, archiveNow).kind, 'running')
  }
  for (const mode of [undefined, '', 'readonly', 'unexpected']) {
    const data = archiveStep([{ ...job('running', false), lease_until: '2026-10-07T00:10:00Z' }])
    data.mode = mode
    assert.equal(operationsStatus(data, archiveNow).kind, 'unknown')
  }
  for (const readOnly of [undefined, null, true, 'false']) {
    const data = archiveStep([{ ...job('running', false), lease_until: '2026-10-07T00:10:00Z' }])
    data.read_only = readOnly
    assert.equal(operationsStatus(data, archiveNow).kind, 'unknown')
  }
  for (const pending of [undefined, null, -1, 0.5, '0']) {
    const data = archiveStep()
    data.processing.pending_count = pending
    assert.equal(operationsStatus(data, archiveNow).kind, 'unknown')
  }
})

test('archive completion never hides a real or unproved whole-queue fence', () => {
  const data = archiveStep([job('queued', false)])
  data.processing.blocking_job = hiddenBlocker('provider_shared_failure')
  assert.equal(operationsStatus(data, archiveNow).kind, 'paused')
  data.processing.blocking_job = { id: 'unknown', state: 'review' }
  assert.equal(operationsStatus(data, archiveNow).kind, 'unknown')
  const missing = archiveStep(Array.from({ length: 100 }, () => job('review', true)))
  delete missing.processing.blocking_job
  missing.processing.pending_count = 101
  assert.equal(operationsStatus(missing, archiveNow).kind, 'unknown')
})

test('unknown archive reasons remain unknown even with a current lease', () => {
  for (const reason of [undefined, null, 'new_archive_reason', 'provider_outcome_unknown']) {
    const data = archiveStep([{ ...job('running', false), lease_until: '2026-10-07T00:10:00Z' }])
    data.worker.reason = reason
    assert.equal(operationsStatus(data, archiveNow).kind, 'unknown')
  }
})

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


test('the global blocker uses the full matching job record and precedes all 13 isolated sources', () => {
  const isolates = Array.from({ length: 13 }, (_, i) => ({ ...job('review', true), id: `isolated-${i}` }))
  const blocker = { ...job('review', false), id: '2aaeaa4d7e20c91eefb03cc5c83694b3850202cb651d6ad8ad6f551cc2a57e63', title: 'Global blocking meeting', reason: 'transport_failed' }
  const pending = Array.from({ length: 30 }, (_, i) => ({ ...job('queued', false), id: `pending-${i}` }))
  const processing = operations([...isolates, blocker, ...pending]).processing
  processing.blocking_job = { ...blocker, source_id: 'source-blocker', title: 'Summary metadata must not replace the full job' }
  const before = [...processing.jobs]
  const displayed = processingJobsBlockerFirst(processing)
  assert.equal(displayed[0], blocker)
  assert.equal(displayed.length, 44)
  assert.deepEqual(displayed.slice(1, 3), isolates.slice(0, 2))
  assert.deepEqual(processing.jobs, before)
  assert.equal(new Set(displayed.map(item => item.id)).size, 44)
})

test('a missing full job never creates a synthetic actionable row; null or unknown fences preserve order', () => {
  const processing = isolatedSlice().processing
  processing.blocking_job = hiddenBlocker('transport_failed')
  assert.equal(processingJobsBlockerFirst(processing), processing.jobs)
  assert.equal(processingJobsBlockerFirst(processing).some(item => item.id === 'hidden-blocker'), false)
  for (const evidence of [null, undefined, {}, { ...hiddenBlocker('transport_failed'), technical_isolation: true }]) {
    processing.blocking_job = evidence
    assert.equal(processingJobsBlockerFirst(processing), processing.jobs)
  }
})


const leaseNow = Date.parse('2026-10-06T13:00:00Z')
const leaseOperations = () => {
  const data = operations([{ ...job('running', false), id: 'new-running-job', lease_until: '2026-10-06T13:10:00.123456+00:00' }, job('queued', false)], { worker: 'paused', isolated_count: 0 })
  data.worker.reason = 'transport_failed'
  data.worker.job_id = 'previous-completed-job'
  data.processing.blocking_job = null
  return data
}

test('fresh running lease plus enabled config and explicit no-blocker supersedes last completed paused/disabled step', () => {
  for (const state of ['paused', 'disabled']) {
    const data = leaseOperations(); data.worker.state = state
    assert.equal(operationsStatus(data, leaseNow).kind, 'running')
    assert.match(operationsStatus(data, leaseNow).message, /Abschluss oder Fortschritt ist noch nicht bestätigt/)
    // Worker job_id can belong to the previous source, not this active lease.
    assert.notEqual(data.worker.job_id, data.processing.jobs[0].id)
  }
})

test('expired, absent or malformed leases and non-running/isolated/reasoned jobs never supersede paused status', () => {
  for (const lease of [null, undefined, '', '2099', 'not-a-date', '2026-13-01T13:10:00Z', '2026-10-06T13:00:00Z', '2026-10-06T12:59:59Z']) {
    const data = leaseOperations(); data.processing.jobs[0].lease_until = lease
    assert.equal(operationsStatus(data, leaseNow).kind, 'paused')
  }
  for (const patch of [{state:'queued'}, {state:'prepared'}, {state:'review'}, {technical_isolation:true}, {technical_isolation:undefined}, {reason:'transport_failed'}]) {
    const data=leaseOperations();Object.assign(data.processing.jobs[0],patch)
    assert.notEqual(operationsStatus(data,leaseNow).kind,'running')
  }
  assert.notEqual(operationsStatus(leaseOperations(),NaN).kind,'running')
})

test('an active lease cannot override disabled config, owner readonly, global blocker or unknown/unavailable state', () => {
  const data = leaseOperations(); data.processing.config.enabled = false
  assert.equal(operationsStatus(data,leaseNow).kind,'paused')
  data.processing.config.enabled = true
  for (const patch of [{read_only:true},{mode:'readonly'}]) {
    assert.notEqual(operationsStatus({...data,...patch},leaseNow).kind,'running')
  }
  for (const state of ['unavailable','unknown','unexpected']) {
    assert.equal(operationsStatus({...data,worker:{state}},leaseNow).kind,'unknown')
  }
  for (const blocker of [undefined, {}, hiddenBlocker('transport_failed')]) {
    data.processing.blocking_job=blocker
    assert.notEqual(operationsStatus(data,leaseNow).kind,'running')
  }
  data.processing.blocking_job=null
  data.processing.config=null
  assert.notEqual(operationsStatus(data,leaseNow).kind,'running')
})


test('calendar-invalid lease days cannot become active by Date.parse normalization; valid leap dates and PG zones/microseconds remain accepted', () => {
  const now = Date.parse('2027-01-01T12:00:00Z')
  for (const lease of ['2027-02-30T13:10:00Z', '2027-04-31T13:10:00Z', '2027-02-29T13:10:00Z', '2100-02-29T13:10:00Z']) {
    const data=leaseOperations();data.processing.jobs[0].lease_until=lease
    assert.equal(operationsStatus(data,now).kind,'paused',lease)
  }
  for (const lease of ['2028-02-29T13:10:00Z', '2028-02-29T13:10:00.123456+02:00', '2028-02-29T13:10:00.123456-05:30']) {
    const data=leaseOperations();data.processing.jobs[0].lease_until=lease
    assert.equal(operationsStatus(data,now).kind,'running',lease)
    data.worker.state='unavailable'
    assert.equal(operationsStatus(data,now).kind,'unknown')
  }
})
