import { lazy, Suspense } from 'react'

// Production has one application. The old dashboard is no longer bundled or routed.
const App = import.meta.env.DEV && window.location.pathname === '/memory-preview'
  ? lazy(() => import('./pages/WorkingMemoryPreview'))
  : lazy(() => import('./pages/MemoryApp'))

export default function Entry() {
  return <Suspense fallback={<p role="status">Ansicht wird geladen…</p>}><App /></Suspense>
}
