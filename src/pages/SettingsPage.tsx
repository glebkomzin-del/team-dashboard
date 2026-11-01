import { useReviewSnapshot } from '@/features/working-memory/useReviewSnapshot'
import { useEffect, useRef, useState } from 'react'
import { Check, ChevronRight, Plus, UsersRound } from 'lucide-react'
import { MemoryWriteError, postMemory } from '@/features/working-memory/types'
import { useRoute } from '@/features/working-memory/planning'
import type { Member, PlannedSnapshot } from '@/features/working-memory/planning'
import { defaults, savePreferences, usePreferences } from '@/features/working-memory/preferences'
import type { Preferences } from '@/features/working-memory/preferences'
import { ProcessingPanel } from '@/features/working-memory/ProcessingPanel'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'

function TeamEditor({ data, close, saved, refresh }: { data: PlannedSnapshot; close: () => void; saved: () => void; refresh: () => void }) {
  const [members, setMembers] = useState<Member[]>(() => structuredClone(data.planner!.team))
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [frozen, setFrozen] = useState(false)
  const [stale, setStale] = useState(false)
  const [discard, setDiscard] = useState(false)
  const [focus] = useState(() => document.activeElement as HTMLElement | null)
  const request = useRef<unknown>(null)
  const sending = useRef(false)
  const errorRef = useRef<HTMLParagraphElement>(null)
  const dirty = JSON.stringify(members) !== JSON.stringify(data.planner!.team) || !!name.trim()
  useEffect(() => { if (error) errorRef.current?.focus() }, [error])
  useEffect(() => { if (!dirty && !frozen) return; const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn) }, [dirty, frozen])
  function requestClose() { if (busy) return; if (dirty || frozen) setDiscard(true); else close() }
  function add() {
    const value = name.trim()
    if (!value || members.some(m => [m.name,...m.aliases].some(n=>n.toLocaleLowerCase('de') === value.toLocaleLowerCase('de')))) { setError('Bitte einen neuen, eindeutigen vollständigen Namen eingeben.'); return }
    setMembers(previous => [...previous, { id: `member-${crypto.randomUUID()}`, name: value, active: true, aliases: [] }]); setName(''); setError('')
  }
  function preparedMembers() {
    const original = new Map(data.planner!.team.map(member => [member.id, member]))
    const names = new Set<string>()
    const prepared = members.map(member => {
      const canonical = member.name.trim()
      const previous = original.get(member.id)
      const aliases = [...member.aliases.map(alias => alias.trim()).filter(Boolean)]
      if (previous && previous.name.trim().toLocaleLowerCase('de') !== canonical.toLocaleLowerCase('de')) aliases.push(previous.name.trim())
      const uniqueAliases = [...new Map(aliases.filter(alias => alias.toLocaleLowerCase('de') !== canonical.toLocaleLowerCase('de')).map(alias => [alias.toLocaleLowerCase('de'), alias])).values()]
      return { ...member, name: canonical, aliases: uniqueAliases }
    })
    for (const member of prepared) {
      if (!member.name || member.name.length > 200 || member.aliases.length > 20) { setError('Namen müssen vollständig sein; pro Person sind höchstens 20 bekannte Schreibweisen möglich.'); return null }
      for (const value of [member.name, ...member.aliases]) {
        const key = value.toLocaleLowerCase('de')
        if (names.has(key) || value.length > 200) { setError('Jeder Name und jede bekannte Schreibweise darf nur einer Person zugeordnet sein.'); return null }
        names.add(key)
      }
    }
    return prepared
  }
  async function save() {
    if (sending.current || stale) return
    if (name.trim()) { setError('Füge den eingegebenen Namen zuerst hinzu oder leere das Namensfeld.'); return }
    const prepared = preparedMembers()
    if (!prepared) return
    if (!request.current) request.current = { command_id: crypto.randomUUID(), expected_revision: data.revision, action: 'configure_team', target_id: 'team', reason: 'Direktes Team von dir in den Einstellungen aktualisiert.', patch: { members: prepared } }
    sending.current = true; setBusy(true); setError('')
    try { await postMemory('/decisions', request.current); saved() }
    catch (e) { setError((e as Error).message); const status = e instanceof MemoryWriteError ? e.status : 503; setStale(status === 409); setFrozen(status >= 500); if (status < 500) request.current = null }
    finally { sending.current = false; setBusy(false) }
  }
  return <Dialog open onOpenChange={v=>{if(!v)requestClose()}}><DialogContent className="wm-dialog px-dialog px-editor" overlayClassName="wm-overlay px-overlay" closeLabel="Teamverwaltung schließen" onCloseAutoFocus={e=>{e.preventDefault();focus?.focus()}}><DialogHeader><DialogTitle>Direktes Team verwalten</DialogTitle><DialogDescription>Namen können korrigiert werden. Frühere Namen und weitere bekannte Schreibweisen halten bestehende Todos zuverlässig bei derselben Person.</DialogDescription></DialogHeader><form className="px-form" onSubmit={e=>{e.preventDefault();void save()}}><div className="px-dialog-scroll"><fieldset disabled={busy || frozen || stale}>{members.map(m=><section className="px-team-editor-row" key={m.id}><div className="px-form-grid"><label>Anzeigename<input name={`name_${m.id}`} autoComplete="off" required maxLength={200} value={m.name} onChange={e=>setMembers(old=>old.map(person=>person.id===m.id?{...person,name:e.target.value}:person))} /></label><label className="px-team-active"><span>Status</span><span><input type="checkbox" name={`active_${m.id}`} autoComplete="off" checked={m.active} onChange={e=>setMembers(old=>old.map(person=>person.id===m.id?{...person,active:e.target.checked}:person))} /><strong>{m.active ? 'Aktiv' : 'Ehemalig'}</strong></span></label></div><label>Bekannte Schreibweisen<textarea name={`aliases_${m.id}`} autoComplete="off" rows={2} maxLength={4020} value={m.aliases.join('\n')} onChange={e=>setMembers(old=>old.map(person=>person.id===m.id?{...person,aliases:e.target.value.split('\n')}:person))} placeholder="Eine Schreibweise pro Zeile, zum Beispiel Nachname, Vorname" /><small>Die Zuordnung erfolgt exakt über diese Schreibweisen, nicht über unscharfe Namensähnlichkeit.</small></label></section>)}<label className="px-new-member">Person ergänzen<input name="member_name" autoComplete="off" maxLength={200} value={name} onChange={e=>setName(e.target.value)} placeholder="Vorname Nachname…" /></label><button type="button" className="px-button" onClick={add}><Plus size={14} aria-hidden="true" />Person hinzufügen</button></fieldset>{error&&<p role="alert" ref={errorRef} tabIndex={-1} className="px-error">{error}</p>}{stale&&<button type="button" className="px-button" onClick={refresh}>Aktuellen Teamstand laden</button>}{discard&&<div className="px-notice" role="alert"><p>{frozen ? 'Die Speicherbestätigung ist unklar. Prüfe den aktuellen Stand nach dem Schließen.' : 'Deine Änderungen sind noch nicht gespeichert.'}</p><button type="button" className="px-button" onClick={close}>Verwerfen und schließen</button><button type="button" className="px-button" onClick={()=>setDiscard(false)}>Weiter bearbeiten</button></div>}</div><footer className="px-dialog-footer"><button className="px-button" type="button" onClick={requestClose} disabled={busy}>Abbrechen</button><button type="submit" className="px-button px-primary" disabled={busy||stale}>{busy?<span><span className="wm-spinner" aria-hidden="true" />Wird gespeichert…</span>:frozen?'Speicherung erneut prüfen':'Team speichern'}</button></footer></form></DialogContent></Dialog>
}

export function SettingsPage({ local, onChanged, cacheScope = '' }: { local: boolean; onChanged: () => void; cacheScope?: string }) {
  const location = useRoute()
  const section = ['team','verarbeitung'].includes(location.params.get('section') || '') ? location.params.get('section')! : 'arbeitsbereich'
  const preferences = usePreferences()
  const [notice, setNotice] = useState('')
  const [preferenceError, setPreferenceError] = useState('')
  const [attempt, retry] = useState(0)
  const current = useReviewSnapshot('', String(attempt), cacheScope, section === 'team')
  const [editor, setEditor] = useState(false)
  function update(value: Preferences) { try { savePreferences(value); setPreferenceError(''); setNotice('Auf diesem Gerät gespeichert.')} catch { setNotice('');setPreferenceError('Dein Browser konnte die Einstellung nicht speichern. Erlaube lokalen Speicher und versuche es erneut.') } }
  function saved() { setEditor(false);retry(n=>n+1);onChanged();setNotice(local?'Team in der lokalen Testkopie gespeichert.':'Team gespeichert.') }
  return <div className="px-workspace"><header className="px-heading"><div><p className="px-eyebrow">Dein Arbeitsbereich</p><h1>Einstellungen</h1><p className="px-muted">Ansicht, Team und die konfigurierte Verarbeitung verwalten.</p></div></header>{local&&<p className="px-draft">Lokaler Entwurf · Teamänderungen betreffen nur die Testkopie.</p>}<nav aria-label="Einstellungsbereiche" className="px-settings-tabs">{[['arbeitsbereich','Arbeitsbereich'],['team','Team'],['verarbeitung','Verarbeitung & Sicherungen']].map(([id,label])=><a key={id} href={`#einstellungen?section=${id}`} aria-current={section===id?'page':undefined}>{label}</a>)}</nav>{notice&&<p className="px-success" role="status"><Check size={14} aria-hidden="true" /> {notice}</p>}{preferenceError&&<p role="alert" className="px-error">{preferenceError}</p>}
    {section==='arbeitsbereich'&&<section className="px-surface px-settings-panel"><header className="px-section-heading"><div><h2>So öffnet sich deine App</h2><p>Diese Einstellungen gelten auf diesem Gerät. Die Darstellung verwendet ausschließlich den Hellmodus.</p></div></header><div className="px-setting-row"><label htmlFor="start_page"><strong>Startseite</strong><small>Der Bereich beim Öffnen ohne direkten Seitenlink.</small></label><select id="start_page" name="start_page" autoComplete="off" value={preferences.startPage} onChange={e=>update({...preferences,startPage:e.target.value as Preferences['startPage']})}><option value="uebersicht">Übersicht</option><option value="todos">Meine Todos</option><option value="team">Mein Team</option></select></div><div className="px-setting-row"><label htmlFor="task_view"><strong>Aufgabenansicht</strong><small>Deine bevorzugte Ansicht für Todos und Teamaufgaben.</small></label><select id="task_view" name="task_view" autoComplete="off" value={preferences.taskView} onChange={e=>update({...preferences,taskView:e.target.value as Preferences['taskView']})}><option value="list">Liste</option><option value="week">Wochenplan</option></select></div><div className="px-setting-row"><label htmlFor="density"><strong>Zeilendichte</strong><small>Kompakt für mehr Überblick oder etwas mehr Platz zum Lesen.</small></label><select id="density" name="density" autoComplete="off" value={preferences.density} onChange={e=>update({...preferences,density:e.target.value as Preferences['density']})}><option value="compact">Kompakt</option><option value="comfortable">Mehr Abstand</option></select></div><footer className="px-section-footer"><span>Die Änderungen werden sofort gespeichert.</span><button type="button" className="px-text-button" onClick={()=>update(defaults)}>Ansicht zurücksetzen</button></footer></section>}
    {section==='team'&&<section className="px-surface px-settings-panel"><header className="px-section-heading"><div><h2>Dein direktes Team</h2><p>Nur aktive Mitarbeitende gehören zur regulären Teamübersicht.</p></div><UsersRound size={18} aria-hidden="true" /></header>{!current.data&&current.refreshing&&<p className="px-empty" role="status">Team wird geladen…</p>}{current.data&&current.refreshing&&<p className="px-muted" role="status">Letzter geladener Teamstand · wird aktualisiert…</p>}{current?.error&&<div className="px-empty" role="alert"><p>{current.error}</p><button className="px-button" type="button" onClick={()=>retry(n=>n+1)}>Erneut versuchen</button></div>}{current?.data?.planner?.team.map(m=><div className="px-team-setting" key={m.id}><span><strong>{m.name}</strong><small>{m.active?'Aktives Teammitglied':'Ausgeschieden · bisherige Aufgaben bleiben erhalten'}</small></span><span className="px-status">{m.active?'Aktiv':'Ehemalig'}</span></div>)}{current?.data&&!current.data.planner&&<p className="px-empty">Teamverwaltung ist in diesem Datenstand noch nicht verfügbar.</p>}<footer className="px-section-footer"><a href="#team">Zur Teamübersicht <ChevronRight size={13} aria-hidden="true" /></a>{current?.data?.planner?.supported&&current.confirmed&&current.data.can_edit&&current.data.revision!==undefined&&<button className="px-button px-primary" type="button" onClick={()=>setEditor(true)}>Team bearbeiten</button>}</footer></section>}
    {section==='verarbeitung'&&<div className="working-memory px-settings-processing"><p className="px-muted">Konfigurierte Automatik, Kostenrahmen und Sicherungen verwalten.</p><ProcessingPanel expanded onChanged={onChanged} /></div>}
    {editor&&current?.data&&<TeamEditor data={current.data} close={()=>{setEditor(false);retry(n=>n+1)}} saved={saved} refresh={()=>{setEditor(false);setNotice('Aktuellen Teamstand neu geladen.');retry(n=>n+1)}} />}
  </div>
}
