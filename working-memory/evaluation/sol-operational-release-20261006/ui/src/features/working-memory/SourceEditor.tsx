import { useEffect, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { dateLabel, getMemory, kindNames, MemoryWriteError, postMemory } from './types'
import type { Kind } from './types'
import { GenerationReviewDialog } from './GenerationReviews'

interface Editable {
  matter: string; matter_id: string | null; kind: Kind; title: string; claim: string; owner: string | null
  commitment_strength: string; due_text: string | null; update_target: string | null; update: string
  uncertainty: string | null; required_review: boolean; action_uncertainty: string | null
  condition_text: string | null; work_state: string; evidence_ids: string[]; state_evidence_ids: string[]
}
interface Link { old_id: string; new_index: number; reason: string }
interface FormData {
  job_id: string; expected_revision: number; expected_updated_at: string; can_edit: boolean
  document: { id: string; title: string; event_date: string; units: Record<string, string> }
  observations: Editable[]; previous_observations: { id: string; title: string; claim: string; quotes: string[] }[]
  previous_topics: { id: string; title: string }[]; existing_topics: { id: string; title: string }[]
  existing_work: { id: string; title: string; owner: string | null; status: string; condition_text: string | null }[]; unknown_provider_outcome: boolean
}
interface Request {
  job_id: string; review_id: string; expected_revision: number; expected_updated_at: string; reason: string
  observations: Editable[]; identity_links: Link[]; topic_links: Link[]
}
const blank = (): Editable => ({ matter: '', matter_id: null, kind: 'fact', title: '', claim: '', owner: null,
  commitment_strength: 'not_applicable', due_text: null, update_target: null, update: 'none', uncertainty: null,
  required_review: false, action_uncertainty: null, condition_text: null, work_state: 'not_applicable', evidence_ids: [], state_evidence_ids: [] })

export function SourceEditor({ jobId, onClose, onSaved }: { jobId: string; onClose: () => void; onSaved: () => void }) {
  const [reviewId] = useState(() => crypto.randomUUID())
  const [returnFocus] = useState(() => document.activeElement instanceof HTMLElement ? document.activeElement : null)
  const [data, setData] = useState<FormData>()
  const [rows, setRows] = useState<Editable[]>([])
  const [active, setActive] = useState(0)
  const [query, setQuery] = useState('')
  const [identityLinks, setIdentityLinks] = useState<Link[]>([])
  const [topicLinks, setTopicLinks] = useState<Link[]>([])
  const [reason, setReason] = useState('')
  const [checked, setChecked] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [discard, setDiscard] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<Request>()
  const [error, setError] = useState<MemoryWriteError>()
  const [loadError, setLoadError] = useState('')
  const [staged, setStaged] = useState(false)
  const errorRef = useRef<HTMLParagraphElement>(null)
  const sending = useRef(false)
  useEffect(() => {
    const controller = new AbortController()
    getMemory<FormData>(`/source-edits/jobs/${jobId}`, controller.signal).then(value => {
      if (value.job_id !== jobId || !value.document?.units || !Array.isArray(value.observations)) throw new Error('Invalid source')
      setData(value); setRows(value.observations)
    }).catch(() => { if (!controller.signal.aborted) setLoadError('Das Original kann gerade nicht zum Bearbeiten geladen werden. Bitte schließen und den Verarbeitungsstand aktualisieren.') })
    return () => controller.abort()
  }, [jobId])
  useEffect(() => {
    if (!dirty && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, pending])
  function change(patch: Partial<Editable>) { setRows(previous => previous.map((row, index) => index === active ? { ...row, ...patch } : row)); setDirty(true); setChecked(false) }
  function close() { if (busy) return; if (dirty || pending) setDiscard(true); else onClose() }
  function remove() {
    setRows(previous => previous.filter((_, index) => index !== active))
    const shift = (links: Link[]) => links.filter(link => link.new_index !== active).map(link => ({ ...link, new_index: link.new_index > active ? link.new_index - 1 : link.new_index }))
    setIdentityLinks(shift); setTopicLinks(shift); setActive(Math.max(0, active - 1)); setDirty(true); setChecked(false)
  }
  async function submit() {
    if (!data || !data.can_edit || sending.current || error?.status === 409) return
    const invalid = rows.findIndex(row => !row.title.trim() || !row.claim.trim() || !row.matter.trim() || !row.evidence_ids.length
      || (row.update !== 'none' && !row.update_target) || (row.kind === 'commitment' && ['explicit', 'accepted_request'].includes(row.commitment_strength) && !row.owner?.trim())
      || ((row.work_state === 'done' || row.update === 'condition_met') && !row.state_evidence_ids.length))
    if (!pending && invalid >= 0) { setActive(invalid); setError(new MemoryWriteError('Diese Aussage braucht Titel, Inhalt, Thema und Originalbelege. Zusagen brauchen eine Person, Erledigungen und eingetretene Voraussetzungen eine ausdrückliche Bestätigung. Änderungen brauchen eine vorhandene Aufgabe.', 400)); return }
    if (!pending && (!checked || !reason.trim() || [...identityLinks, ...topicLinks].some(link => !link.reason.trim()))) return
    sending.current = true; setBusy(true); setError(undefined)
    const request = pending || { job_id: jobId, review_id: reviewId, expected_revision: data.expected_revision, expected_updated_at: data.expected_updated_at,
      reason: reason.trim(), observations: rows, identity_links: identityLinks, topic_links: topicLinks }
    setPending(request)
    try {
      const result = await postMemory<{ review_id: string }>('/source-edits', request)
      if (result.review_id !== reviewId) throw new MemoryWriteError('Die Entwurfsbestätigung ist unklar. Bitte denselben Entwurf erneut versuchen.', 503)
      setDirty(false); setPending(undefined); setStaged(true)
    }
    catch (caught) {
      const failure = caught instanceof MemoryWriteError ? caught : new MemoryWriteError('Die Speicherung konnte nicht bestätigt werden. Erneut versuchen sendet denselben Entwurf.', 503)
      if ([400, 401, 403].includes(failure.status)) setPending(undefined)
      setError(failure.status === 400 ? new MemoryWriteError('Der Entwurf ist noch nicht vollständig belegt oder zugeordnet. Prüfe Originalstellen, Frist und Bedingung sowie die Zuordnung früherer Aussagen und Themen. Persönliche Entscheidungen und spätere Bezüge dürfen nicht verloren gehen.', 400) : failure)
      requestAnimationFrame(() => errorRef.current?.focus())
    } finally { sending.current = false; setBusy(false) }
  }
  const row = rows[active]
  const units = Object.entries(data?.document.units || {})
  function mapping(items: { id: string; title: string }[], links: Link[], setLinks: (next: Link[]) => void, title: string) {
    return items.length > 0 && <details><summary>{title}</summary><p>Wähle nur dann eine neue Aussage, wenn sie denselben bisherigen Sachverhalt fortführt. Persönlich bearbeitete Aussagen und spätere Bezüge benötigen eine ausdrückliche Zuordnung.</p>
      {items.map(item => { const link = links.find(value => value.old_id === item.id); return <div className="wm-row" key={item.id}>
        <label>{item.title}<select value={link?.new_index ?? ''} onChange={event => {
          const remaining = links.filter(value => value.old_id !== item.id)
          setLinks(event.target.value === '' ? remaining : [...remaining, { old_id: item.id, new_index: Number(event.target.value), reason: link?.reason || '' }]); setDirty(true); setChecked(false)
        }}><option value="">Keine Zuordnung vorgeschlagen</option>{rows.map((next, index) => <option key={index} value={index}>{index + 1}. {next.title || 'Unbenannte Aussage'}</option>)}</select></label>
        {link && <label>Warum ist es derselbe Sachverhalt?<input value={link.reason} maxLength={1000} required onChange={event => { setLinks(links.map(value => value.old_id === item.id ? { ...value, reason: event.target.value } : value)); setDirty(true); setChecked(false) }} /></label>}
      </div> })}</details>
  }
  if (staged) return <GenerationReviewDialog reviewId={reviewId} onClose={onSaved} onSaved={onSaved} />
  return <Dialog open onOpenChange={open => { if (!open) close() }}>
    <DialogContent className="wm-dialog wm-decision-dialog wm-source-editor" overlayClassName="wm-overlay" closeLabel="Originalbearbeitung schließen"
      onEscapeKeyDown={event => { if (busy) event.preventDefault() }} onPointerDownOutside={event => event.preventDefault()}
      onCloseAutoFocus={event => { event.preventDefault(); returnFocus?.focus() }}>
      <DialogHeader><DialogTitle>Aussagen am Original überarbeiten</DialogTitle><DialogDescription>{data ? `${data.document.title} · ${dateLabel(data.document.event_date)}` : 'Gespeichertes Original laden.'}</DialogDescription></DialogHeader>
      <div className="wm-decision-scroll">
        {!data && !loadError && <p role="status">Original wird geladen…</p>}{loadError && <p role="alert">{loadError}</p>}
        {data && <>
          <p>Hier bereitest du eine erneute Prüfung vor. Der Arbeitsstand ändert sich erst, wenn du danach den Vergleich ausdrücklich übernimmst. Dafür wird keine KI-Anfrage gesendet.</p>
          {data.unknown_provider_outcome && <p className="wm-note">Eine frühere KI-Anfrage hat noch keinen bestätigten Ausgang. Sie wird nicht erneut gesendet; eine spätere Antwort und ihre Kosten bleiben nachvollziehbar.</p>}
          <details><summary>Vollständiges Original lesen</summary>{units.map(([id, text]) => <p className="wm-source-line" key={id}><small>{id.slice(1)}</small> {text}</p>)}</details>
          {data.previous_observations.length > 0 && <details><summary>Bisherige Aussagen aus der früheren Fassung</summary>{data.previous_observations.map(previous => <article className="wm-row" key={previous.id}><h3>{previous.title}</h3><p>{previous.claim}</p>{previous.quotes.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}</article>)}</details>}
          {!data.can_edit ? <p>Dieser Lauf arbeitet noch oder ist bereits abgeschlossen. Bitte schließe diese Ansicht und aktualisiere den Verarbeitungsstand.</p> : <form className="wm-decision-form" aria-busy={busy} onSubmit={event => { event.preventDefault(); void submit() }}>
            <fieldset disabled={busy || !!pending}>
              <label>Aussage auswählen<select value={rows.length ? active : ''} onChange={event => { setActive(Number(event.target.value)); setQuery('') }}>
                {!rows.length && <option value="">Noch keine Aussagen</option>}{rows.map((item, index) => <option key={index} value={index}>{index + 1}. {item.title || 'Neue Aussage'}</option>)}
              </select></label>
              <button type="button" className="wm-button" disabled={rows.length >= 150} onClick={() => { setRows([...rows, blank()]); setActive(rows.length); setQuery(''); setDirty(true); setChecked(false) }}>Aussage hinzufügen</button>
              {row && <div className="wm-source-fields">
                <label>Art<select value={row.kind} onChange={event => change({ kind: event.target.value as Kind })}>{Object.entries(kindNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label>Titel<input value={row.title} maxLength={250} onChange={event => change({ title: event.target.value })} /></label>
                <label>Was wurde tatsächlich gesagt oder vereinbart?<textarea value={row.claim} rows={5} maxLength={5000} onChange={event => change({ claim: event.target.value })} /></label>
                <label>Vorhandenes Thema<select value={row.matter_id || ''} onChange={event => { const topic = data.existing_topics.find(item => item.id === event.target.value); change({ matter_id: topic?.id || null, ...(topic ? { matter: topic.title } : {}) }) }}><option value="">Neues Thema benennen</option>{data.existing_topics.map(topic => <option key={topic.id} value={topic.id}>{topic.title}</option>)}</select></label>
                <label>Thema<input value={row.matter} maxLength={250} disabled={!!row.matter_id} onChange={event => change({ matter: event.target.value })} /></label>
                <label>Person<input value={row.owner || ''} maxLength={250} placeholder="Nur bei verlässlicher Zuordnung" onChange={event => change({ owner: event.target.value || null })} /></label>
                <label>Verbindlichkeit<select value={row.commitment_strength} onChange={event => change({ commitment_strength: event.target.value })}>
                  <option value="not_applicable">Keine Zusage</option><option value="explicit">Ausdrücklich selbst zugesagt</option><option value="accepted_request">Konkrete Bitte angenommen</option><option value="reported">Nur von jemand anderem berichtet</option><option value="conditional">Nur bedingt oder als Möglichkeit genannt</option>
                </select></label>
                <label>Arbeitsstatus<select value={row.work_state} disabled={row.update === 'condition_met'} onChange={event => change({ work_state: event.target.value, ...(event.target.value !== 'done' ? { state_evidence_ids: [] } : {}) })}>
                  <option value="not_applicable">Keine eigene Aufgabe</option><option value="open">Offen</option><option value="waiting">Wartet auf Voraussetzung</option><option value="done">Bereits erledigt</option>
                </select></label>
                <label>Vorhandene Aufgabe fortschreiben<select value={row.update_target || ''} onChange={event => change({ update_target: event.target.value || null, update: event.target.value ? 'progress' : 'none' })}><option value="">Keine vorhandene Aufgabe ändern</option>{data.existing_work.map(work => <option key={work.id} value={work.id}>{work.title}{work.owner ? ` · ${work.owner}` : ''}</option>)}</select></label>
                {row.update_target && <>
                  <label>Welche Änderung?<select value={row.update} onChange={event => change({ update: event.target.value, ...(event.target.value === 'condition_met' ? { work_state: 'open', condition_text: null, state_evidence_ids: [] } : {}) })}>{Object.entries({ progress: 'Fortschritt', done: 'Erledigt', reopened: 'Wieder offen', owner_changed: 'Andere Zuständigkeit', date_changed: 'Andere Frist', condition_met: 'Alle bisherigen Voraussetzungen sind eingetreten' }).map(([value, label]) => <option key={value} value={value} disabled={value === 'condition_met' && !data.existing_work.some(work => work.id === row.update_target && work.condition_text && ['open', 'waiting'].includes(work.status))}>{label}</option>)}</select></label>
                  {data.existing_work.find(work => work.id === row.update_target)?.condition_text && <p style={{ whiteSpace: 'pre-line' }}>Bisherige Voraussetzungen: {data.existing_work.find(work => work.id === row.update_target)?.condition_text}</p>}
                  {row.update === 'condition_met' && <p>Das Original muss bestätigen, dass alle bisherigen Voraussetzungen eingetreten sind. Die Aufgabe bleibt offen.</p>}
                </>}
                <label>Frist im genauen Originalwortlaut<input value={row.due_text || ''} maxLength={300} onChange={event => change({ due_text: event.target.value || null })} /></label>
                <label>Voraussetzungen im genauen Originalwortlaut, je eine pro Zeile<textarea value={row.condition_text || ''} disabled={row.update === 'condition_met'} rows={2} maxLength={2000} onChange={event => change({ condition_text: event.target.value || null })} /></label>
                <label>Was bleibt inhaltlich unsicher?<textarea value={row.uncertainty || ''} rows={2} maxLength={2000} onChange={event => change({ uncertainty: event.target.value || null })} /></label>
                <label>Was ist an der Zusage oder Änderung unsicher?<textarea value={row.action_uncertainty || ''} rows={2} maxLength={2000} onChange={event => change({ action_uncertainty: event.target.value || null })} /></label>
                <label><input type="checkbox" checked={row.required_review} onChange={event => change({ required_review: event.target.checked })} /> Für diese Aussage eine spätere Einzelprüfung offen lassen</label>
                <div className="wm-evidence-picker"><h3>Originalstellen für diese Aussage</h3>
                  <label>Im Original suchen<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
                  <p>{row.evidence_ids.length} Belege ausgewählt. Bei Erledigung oder eingetretenen Voraussetzungen zusätzlich die ausdrückliche Bestätigung markieren.</p>
                  <div className="wm-evidence-lines">{units.filter(([id, text]) => row.evidence_ids.includes(id) || !query || text.toLocaleLowerCase('de').includes(query.toLocaleLowerCase('de'))).map(([id, text]) => <div key={id}>
                    <label><input type="checkbox" checked={row.evidence_ids.includes(id)} onChange={event => change({ evidence_ids: event.target.checked ? [...row.evidence_ids, id] : row.evidence_ids.filter(key => key !== id), state_evidence_ids: row.state_evidence_ids.filter(key => key !== id) })} /><span>{text}</span></label>
                    {(row.work_state === 'done' || row.update === 'condition_met') && row.evidence_ids.includes(id) && <label><input type="checkbox" checked={row.state_evidence_ids.includes(id)} onChange={event => change({ state_evidence_ids: event.target.checked ? [...row.state_evidence_ids, id] : row.state_evidence_ids.filter(key => key !== id) })} /> {row.update === 'condition_met' ? 'Diese Stelle bestätigt die eingetretenen Voraussetzungen' : 'Diese Stelle bestätigt die Erledigung'}</label>}
                  </div>)}</div>
                </div>
                <button type="button" className="wm-button" onClick={remove}>Diese Aussage aus dem Entwurf entfernen</button>
              </div>}
              {mapping(data.previous_observations, identityLinks, setIdentityLinks, 'Bisherige Aussagen den neuen Aussagen zuordnen')}
              {mapping(data.previous_topics, topicLinks, setTopicLinks, 'Bisherige Themen den neuen Aussagen zuordnen')}
              <label>Begründung für diese Überarbeitung<textarea value={reason} maxLength={3000} rows={3} required onChange={event => { setReason(event.target.value); setDirty(true); setChecked(false) }} /></label>
              <label><input type="checkbox" required checked={checked} onChange={event => setChecked(event.target.checked)} /> Ich habe die Aussagen und ihre Originalbelege geprüft. {rows.length === 0 ? 'Dieser Entwurf enthält bewusst keine Aussagen für den Arbeitsstand.' : 'Nicht belegte Zusagen und Zuständigkeiten habe ich entfernt oder als unsicher markiert.'}</label>
            </fieldset>
            {error && <p role="alert" tabIndex={-1} ref={errorRef} className="wm-note">{error.message}</p>}
            <div className="wm-decision-actions"><button type="button" className="wm-button" disabled={busy} onClick={close}>Abbrechen</button>
              {error?.status === 409 ? <button type="button" className="wm-button" onClick={onSaved}>Schließen und aktualisieren</button> : <button type="submit" className="wm-button" disabled={busy || (!pending && (!checked || !reason.trim()))}>{busy ? 'Entwurf wird geprüft…' : pending ? 'Erneut versuchen' : 'Vergleich zur Prüfung vorbereiten'}</button>}
            </div>
          </form>}
        </>}
        {discard && <div role="alert" className="wm-note"><p>Deine Überarbeitung ist noch nicht sicher gespeichert.</p><button type="button" className="wm-button" onClick={onSaved}>Schließen und Stand prüfen</button><button type="button" className="wm-button" onClick={() => setDiscard(false)}>Weiter bearbeiten</button></div>}
      </div>
    </DialogContent>
  </Dialog>
}
