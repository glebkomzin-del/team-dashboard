import assert from 'node:assert/strict'
import { test, beforeEach } from 'node:test'
import { readSnapshot, saveSnapshot, clearSnapshots } from '../src/features/working-memory/snapshot-cache.ts'
const values = new Map()
globalThis.sessionStorage = {
 getItem: key => values.get(key) ?? null,
 setItem: (key, value) => values.set(key, value),
 removeItem: key => values.delete(key),
 key: index => [...values.keys()][index] ?? null,
 get length() { return values.size },
}
const data = { mode: 'production', as_of: '2026-09-09', personal: [], waiting: [], waiting_dependencies: [], completed: [], knowledge: [], dates: [], sources: [], changes: [], jobs: [], revision: 5 }
beforeEach(() => values.clear())
test('reload restores same-account same-date snapshot only', () => {
 saveSnapshot('owner-a', '', data)
 assert.deepEqual(readSnapshot('owner-a', ''), data)
 assert.equal(readSnapshot('owner-b', ''), undefined)
 assert.equal(readSnapshot('owner-a', '2026-08-01'), undefined)
 assert.equal(readSnapshot('', ''), undefined)
})
test('expired and malformed snapshots are ignored', () => {
 for (const value of ['not json', JSON.stringify({ asOf: '', savedAt: Date.now(), data: {} }), JSON.stringify({ asOf: '', savedAt: 0, data })]) {
  values.set('meeting-os:review:v1:owner-a', value)
  assert.equal(readSnapshot('owner-a', ''), undefined)
 }
})
test('logout removes every account snapshot but preserves preferences', () => {
 saveSnapshot('owner-a', '', data); saveSnapshot('owner-b', '', data)
 values.set('preferences', 'preserved')
 clearSnapshots()
 assert.deepEqual([...values.entries()], [['preferences', 'preserved']])
})
test('unavailable storage does not break rendering or successful responses', () => {
 const storage=globalThis.sessionStorage
 Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, get() { throw new Error('Unavailable') } })
 try { assert.equal(readSnapshot('owner-a', ''), undefined); saveSnapshot('owner-a', '', data); clearSnapshots() }
 finally { Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, writable: true, value: storage }) }
})
