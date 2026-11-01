import type { PlannedSnapshot } from './planning'

const prefix = 'meeting-os:review:v1:'
const maxAge = 24 * 60 * 60 * 1000
export function validSnapshot(value: unknown): value is PlannedSnapshot {
  if (!value || typeof value !== 'object') return false
  const data = value as PlannedSnapshot
  return ['isolated-preview', 'staging', 'production'].includes(data.mode) &&
    typeof data.as_of === 'string' && ['personal', 'waiting', 'waiting_dependencies', 'completed', 'knowledge', 'dates', 'sources', 'changes', 'jobs'].every(key => Array.isArray((data as unknown as Record<string, unknown>)[key]))
}
export function readSnapshot(scope: string, asOf: string): PlannedSnapshot | undefined {
  if (!scope) return
  try {
    const saved = JSON.parse(sessionStorage.getItem(prefix + scope) || 'null')
    if (saved?.asOf === asOf && typeof saved.savedAt === 'number' && Date.now() - saved.savedAt < maxAge && validSnapshot(saved.data)) return saved.data
  } catch { /* Unavailable or full storage must never block the working view. */ }
}
export function saveSnapshot(scope: string, asOf: string, data: PlannedSnapshot) {
  if (!scope) return
  try { sessionStorage.setItem(prefix + scope, JSON.stringify({ asOf, savedAt: Date.now(), data })) } catch { /* The current response remains usable without persistence. */ }
}
export function clearSnapshots() {
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const key = sessionStorage.key(i)
      if (key?.startsWith(prefix)) sessionStorage.removeItem(key)
    }
  } catch { /* Storage may be disabled. */ }
}
