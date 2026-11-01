import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = readFileSync(new URL('../src/features/working-memory/planning.ts', import.meta.url), 'utf8')

test('betrieb remains a dedicated technical review route', () => {
  assert.match(source, /betrieb: 'Verarbeitung'/)
  assert.doesNotMatch(source, /raw === 'betrieb'/)
})
