import { useEffect, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { MemoryWriteError, postMemory } from './types'
import { priorityNames, statusNames } from './planning'
import type { Member, PlannedWork } from './planning'

export function PlannerEditor({ task, revision, team, onClose, onSaved }: { task?: PlannedWork; revision: number; team: Member[]; onClose: () => void; onSaved: () => void }) {
  const manual = !task || task.origin === 'manual'
  const [initial] = useState(() => ({ title: task?.title || '', owner: task?.owner || 'Komzin, Gleb', status: task?.status === 'dismissed' ? 'cancelled' : task?.status || 'open', due_date: task?.due_date || '', scheduled_date: task?.scheduled_date || '', priority: task?.priority || 'normal', estimate_minutes: task?.estimate_minutes?.toString() || '', note: task?.note || '' }))
  const [fields, setFields] = useState(initial)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [discard, setDiscard] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [stale, setStale] = useState(false)
  const [focus] = useState(() => document.activeElement as HTMLElement | null)
  const [identity] = useState(() => ({ command_id: crypto.randomUUID(), target_id: task?.id || crypto.randomUUID() }))
  const request = useRef<unknown>(null)
  const sending = useRef(false)
  const errorRef = useRef<HTMLParagraphElement>(null)
  const dirty = JSON.stringify(initial) !== JSON.stringify(fields)
  useEffect(() => { if (error) errorRef.current?.focus() }, [error])
  useEffect(() => { if (!dirty && !uncertain) return; const leave = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }; window.addEventListener('beforeunload', leave); return () => window.removeEventListener('beforeunload', leave) }, [dirty, uncertain])
  function close() { if (saving) return; if (dirty || uncertain) setDiscard(true); else onClose() }
  async function save() {
    if (sending.current) return
    sending.current = true
    if (!request.current) {
      const planning = { scheduled_date: fields.scheduled_date || null, priority: fields.priority, estimate_minutes: fields.estimate_minutes ? Number(fields.estimate_minutes) : null, note: fields.note }
      const patch = manual ? { ...planning, title: fields.title.trim(), owner: fields.owner.trim(), due_date: fields.due_date || null, status: fields.status } : planning
      request.current = { ...identity, expected_revision: revision, action: !task ? 'create_task' : manual ? 'update_task' : 'plan_task', reason: !task ? 'Todo von dir angelegt.' : manual ? 'Todo von dir aktualisiert.' : 'Arbeitsplanung von dir angepasst; die Meetingzusage bleibt unverändert.', patch }
    }
    setSaving(true); setError('')
    try { await postMemory('/decisions', request.current); onSaved() }
    catch (e) { const problem = e as Error; setError(problem.message); const status = e instanceof MemoryWriteError ? e.status : 503; setStale(status === 409); setUncertain(status >= 500); if (status < 500) request.current = null }
    finally { sending.current = false; setSaving(false) }
  }
  const set = (key: keyof typeof fields, value: string) => setFields(f => ({ ...f, [key]: value }))
  return <Dialog open onOpenChange={open => { if (!open) close() }}><DialogContent className="wm-dialog px-dialog px-editor" overlayClassName="wm-overlay px-overlay" closeLabel="Todo-Fenster schließen" onCloseAutoFocus={e => { e.preventDefault(); focus?.focus() }}>
    <DialogHeader><DialogTitle>{!task ? 'Neues Todo' : manual ? 'Todo bearbeiten' : 'Arbeit einplanen'}</DialogTitle><DialogDescription>{manual ? 'Deine Aufgabe – unabhängig von einem Meeting.' : task.title}</DialogDescription></DialogHeader>
    <form className="px-form" onSubmit={e => { e.preventDefault(); void save() }}>
      <div className="px-dialog-scroll"><fieldset disabled={saving || uncertain || stale}>
        {manual && <><label>Titel<input name="title" autoComplete="off" required maxLength={1000} value={fields.title} onChange={e => set('title', e.target.value)} placeholder="Zum Beispiel Bericht freigeben…" /></label><div className="px-form-grid"><label>Zuständig<select name="owner" autoComplete="off" value={fields.owner} onChange={e => set('owner', e.target.value)}><option value="Komzin, Gleb">Ich · Gleb Komzin</option>{team.filter(m => m.active).map(m => <option key={m.id}>{m.name}</option>)}{fields.owner !== 'Komzin, Gleb' && !team.some(m => m.active && m.name === fields.owner) && <option>{fields.owner}</option>}</select></label><label>Status<select name="status" autoComplete="off" value={fields.status} onChange={e => set('status', e.target.value)}>{Object.entries(statusNames).filter(([key]) => key !== 'dismissed').map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></div></>}
        <div className="px-form-grid"><label>Geplant für<input name="scheduled_date" autoComplete="off" type="date" value={fields.scheduled_date} onChange={e => set('scheduled_date', e.target.value)} /><small>Der Tag, an dem du daran arbeiten möchtest.</small></label>{manual && <label>Fällig am<input name="due_date" autoComplete="off" type="date" value={fields.due_date} onChange={e => set('due_date', e.target.value)} /><small>Die verbindliche Frist bleibt unabhängig vom Plantag.</small></label>}</div>
        <div className="px-form-grid"><label>Priorität<select name="priority" autoComplete="off" value={fields.priority} onChange={e => set('priority', e.target.value)}>{Object.entries(priorityNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>Geschätzter Aufwand · Minuten<input name="estimate_minutes" autoComplete="off" type="number" inputMode="numeric" min="1" max="10080" step="1" value={fields.estimate_minutes} onChange={e => set('estimate_minutes', e.target.value)} placeholder="Zum Beispiel 30…" /></label></div>
        <label>Arbeitsnotiz<textarea name="note" autoComplete="off" rows={4} maxLength={10000} value={fields.note} onChange={e => set('note', e.target.value)} placeholder="Nächster Schritt, Ergebnis oder Hindernis…" /></label>
      </fieldset>{error && <p className="px-error" ref={errorRef} role="alert" tabIndex={-1}>{error}</p>}{stale && <button type="button" className="px-button" onClick={onSaved}>Aktuellen Stand laden</button>}
      {discard && <div className="px-notice" role="alert"><p>{uncertain ? 'Die Speicherung ist unklar. Lade nach dem Schließen den aktuellen Stand neu.' : 'Deine ungespeicherten Änderungen gehen beim Schließen verloren.'}</p><button type="button" className="px-button" onClick={onClose}>Änderungen verwerfen und schließen</button><button type="button" className="px-button" onClick={() => setDiscard(false)}>Weiter bearbeiten</button></div>}</div>
      <footer className="px-dialog-footer"><button type="button" className="px-button" onClick={close} disabled={saving}>Abbrechen</button><button type="submit" className="px-button px-primary" disabled={saving || stale}>{saving ? <span><span className="wm-spinner" aria-hidden="true" />Wird gespeichert…</span> : uncertain ? 'Speicherung erneut prüfen' : !task ? 'Todo anlegen' : 'Änderungen speichern'}</button></footer>
    </form>
  </DialogContent></Dialog>
}
