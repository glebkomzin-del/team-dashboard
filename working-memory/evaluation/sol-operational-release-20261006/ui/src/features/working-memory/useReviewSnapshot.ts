import { useEffect, useState } from 'react'
import { getMemory, MemoryReadError } from './types'
import type { PlannedSnapshot } from './planning'
import { clearSnapshots, readSnapshot, saveSnapshot, validSnapshot } from './snapshot-cache'

type Result = { selection: string; request?: string; data?: PlannedSnapshot; error?: string; denied?: boolean }
export function useReviewSnapshot(asOf: string, request: string, scope = '', enabled = true) {
  const selection = `${scope}:${asOf}`
  const [result, setResult] = useState<Result>(() => ({ selection, data: readSnapshot(scope, asOf) }))
  useEffect(() => {
    if (!enabled) return
    let active = true
    const controller = new AbortController()
    // A finite wait makes transient failures retryable while keeping the last view.
    let timedOut = false
    const timer = window.setTimeout(() => { timedOut = true; controller.abort() }, 90_000)
    getMemory<PlannedSnapshot>(`/review${asOf ? `?as_of=${encodeURIComponent(asOf)}` : ''}`, controller.signal)
      .then(data => {
        if (!active || controller.signal.aborted) return
        if (!validSnapshot(data)) throw new Error('Der Arbeitsstand ist unvollständig. Bitte erneut laden.')
        saveSnapshot(scope, asOf, data)
        setResult({ selection, request, data })
      })
      .catch((error: Error) => {
        if (!active || (controller.signal.aborted && !timedOut)) return
        const denied = error instanceof MemoryReadError && (error.status === 401 || error.status === 403)
        if (denied) clearSnapshots()
        setResult(previous => ({ selection, request, denied,
          data: denied ? undefined : previous.selection === selection ? previous.data : undefined,
          error: timedOut ? 'Die Aktualisierung dauert zu lange. Bitte erneut versuchen.' : error.message }))
      }).finally(() => window.clearTimeout(timer))
    return () => { active = false; window.clearTimeout(timer); controller.abort() }
  }, [asOf, request, scope, selection, enabled])
  const current = result.selection === selection ? result : undefined
  const refreshing = current?.request !== request
  // A persisted or not-yet-refreshed revision is display-only. Existing server-side
  // revision checks remain authoritative for every write.
  const confirmed = !refreshing && !current?.error && !current?.denied
  return { data: current?.data, error: current?.error, refreshing, confirmed }
}
