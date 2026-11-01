import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hasReviewBlocker, processingReason, processingStatus } from '../src/features/working-memory/processing-status.ts'

test('processing status distinguishes configuration, activity, pauses and unknown states', () => {
  assert.equal(processingStatus(null, 'disabled').kind, 'not-configured')
  assert.deepEqual(processingStatus(false, 'disabled'), { kind: 'paused', message: 'Automatische Verarbeitung ist ausgeschaltet.' })
  assert.equal(processingStatus(true, 'idle').kind, 'configured')
  assert.equal(processingStatus(true, 'starting').kind, 'configured')
  assert.equal(processingStatus(true, 'ready').kind, 'configured')
  assert.equal(processingStatus(true, 'running').kind, 'running')
  assert.equal(processingStatus(true, 'paused').kind, 'paused')
  assert.equal(processingStatus(true, 'disabled').kind, 'paused')
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
  assert.equal(processingReason('new_reason'), 'Eine Prüfung ist erforderlich, bevor die Verarbeitung fortgesetzt werden kann.')
})
