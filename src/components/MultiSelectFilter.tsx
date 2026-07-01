import { useState } from 'react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

interface MultiSelectFilterProps {
  /** Aktuell ausgewählte Werte. Leer = „alle". */
  selected: string[]
  /** Auswahl-Optionen. */
  options: string[]
  /** Callback bei Änderung der Auswahl. */
  onChange: (next: string[]) => void
  /** Label wenn nichts ausgewählt ist, z.B. „Alle Teilnehmer". */
  allLabel: string
  /** Test-ID für den Trigger-Button. */
  testId?: string
  /** Breite des Trigger-Buttons (Tailwind-Klasse), default w-[160px]. */
  triggerWidth?: string
}

/**
 * Multi-Select-Filter als Popover mit Checkbox-Liste.
 * Konsistent mit dem Design des Datumsfilters: fester Trigger-Button,
 * Akzent-Punkt bei aktiver Auswahl, dezent,Outside-Click schließt.
 */
export function MultiSelectFilter({ selected, options, onChange, allLabel, testId, triggerWidth = 'w-[160px]' }: MultiSelectFilterProps) {
  const [open, setOpen] = useState(false)
  const hasFilter = selected.length > 0

  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter(v => v !== value) : [...selected, value])
  }

  const label = !hasFilter
    ? allLabel
    : selected.length === 1
      ? selected[0]
      : `${selected.length} ausgewählt`

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button data-testid={testId} className={`h-8 ${triggerWidth} rounded-md border border-[var(--syn-line)] bg-[var(--syn-surface-2)] px-3 text-xs flex items-center gap-2 hover:bg-[var(--syn-hover)] transition-colors`}>
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${hasFilter ? 'bg-[var(--syn-accent)]' : 'bg-transparent'}`} />
          <span className="truncate text-left flex-1">{label}</span>
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 shrink-0 opacity-50" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-auto p-0 border-[var(--syn-line)] bg-[var(--syn-bg)]">
        <div className="p-1.5 max-h-[280px] overflow-y-auto" style={{ minWidth: '180px' }}>
          {options.map(opt => (
            <button
              key={opt}
              onClick={() => toggle(opt)}
              className="w-full flex items-center gap-2 text-left text-xs px-2 py-1.5 rounded hover:bg-[var(--syn-hover)] transition-colors"
              style={{ color: selected.includes(opt) ? 'var(--syn-accent)' : 'var(--syn-text)' }}
            >
              <span className={`w-3.5 h-3.5 shrink-0 rounded border flex items-center justify-center ${selected.includes(opt) ? 'bg-[var(--syn-accent)] border-[var(--syn-accent)]' : 'border-[var(--syn-line)]'}`}>
                {selected.includes(opt) && <svg viewBox="0 0 24 24" className="h-2.5 w-2.5 text-white" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5L20 7" /></svg>}
              </span>
              <span className="truncate">{opt}</span>
            </button>
          ))}
        </div>
        {hasFilter && (
          <button
            onClick={() => onChange([])}
            className="w-full text-left text-xs px-3 py-1.5 border-t border-[var(--syn-line)] hover:bg-[var(--syn-hover)]"
            style={{ color: 'var(--syn-danger)' }}
          >
            Auswahl zurücksetzen
          </button>
        )}
      </PopoverContent>
    </Popover>
  )
}
