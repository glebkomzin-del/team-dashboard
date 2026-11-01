import type { Observation } from './types'

const labels = ['Unbelegt', 'Mehrdeutig', 'Eindeutig'] as const
export function EvidenceConfidence({ observation }: { observation: Pick<Observation, 'assignment_score' | 'change_score' | 'confidence_reason'> }) {
  const { assignment_score: assignment, change_score: change, confidence_reason: reason } = observation
  if (assignment === undefined || change === undefined) return null
  return <details className="wm-muted"><summary>KI-Einordnung: {labels[Math.min(assignment, change)]}</summary>
    <p>Zuordnung: {labels[assignment]} ({assignment}/2) · Aussage oder Änderung: {labels[change]} ({change}/2)</p>
    {reason && <p>{reason}</p>}<p>Belegstufen, keine Prozentwahrscheinlichkeiten.</p>
  </details>
}
