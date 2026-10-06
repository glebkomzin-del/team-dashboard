import { getMemory, numberLabel } from '@/features/working-memory/types'
import { isolationMessage, operationsStatus, processingFence, processingReason } from '@/features/working-memory/processing-status'
import type { Operations } from '@/features/working-memory/processing-status'
import { clearSnapshots } from '@/features/working-memory/snapshot-cache'
import { useEffect, useRef, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { getSession, onAuthStateChange, signOut, recoveryRequested, recoveryLinkFailed, SUPABASE_URL } from '@/auth'
import { Login, PasswordRecovery } from '@/features/auth/AuthForms'
import { ProductivityPage } from './ProductivityPage'
import { pageNames, rememberScroll, useRoute } from '@/features/working-memory/planning'
import type { Page } from '@/features/working-memory/planning'
import { Archive, BookOpen, CircleDot, ClipboardCheck, ListTodo, LogOut, Settings2, LayoutDashboard, Menu, Search, ChevronRight, UsersRound, MessageCircle } from 'lucide-react'
import { usePreferences } from '@/features/working-memory/preferences'
import { SettingsPage } from './SettingsPage'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ArchivePage } from './ArchivePage'
import { NotesChat } from '@/features/working-memory/NotesChat'
import '@/features/working-memory/working-memory.css'

const groups: { label: string; items: Page[] }[] = [
  { label: 'Arbeit', items: ['uebersicht', 'todos', 'team'] },
  { label: 'Wissen', items: ['fragen', 'pruefen', 'archiv', 'wissen'] },
]
const destinations = [...groups.flatMap(g => g.items), 'einstellungen' as Page]
const navIcons = { uebersicht: LayoutDashboard, todos: ListTodo, team: UsersRound, wissen: BookOpen, fragen: MessageCircle, pruefen: ClipboardCheck, archiv: Archive, einstellungen: Settings2, betrieb: Settings2 }
const hints: Partial<Record<Page, string>> = { uebersicht: 'Tag und Team im Blick', todos: 'Eigene Aufgaben und Wochenplanung', team: 'Aufgaben deiner Mitarbeitenden', fragen: 'Belegte Antworten aus Notizen', pruefen: 'Unklare Vorschläge entscheiden', archiv: 'Zusammenfassungen und Originale', wissen: 'Aussagen, Entscheidungen und offene Fragen', einstellungen: 'Ansicht, Team und Verarbeitung' }
export function MemoryShell({ local = false, userId = '' }: { local?: boolean; userId?: string }) {
  const location = useRoute()
  const [archiveVisited, setArchiveVisited] = useState(location.page === 'archiv')
  if (location.page === 'archiv' && !archiveVisited) setArchiveVisited(true)
  const preferences = usePreferences()
  const [error, setError] = useState('')
  const [savedRoutes, setSavedRoutes] = useState<Partial<Record<Page, string>>>({})
  const [navigation, setNavigation] = useState<'search' | 'menu' | null>(null)
  const [query, setQuery] = useState('')
  const navigationFocus = useRef<HTMLElement | null>(null)
  const navigationDestination = useRef(false)
  const [dataVersion, setDataVersion] = useState(0)
  const [operations, setOperations] = useState<{ data?: Operations; error?: string; checkedAt: string; updating?: boolean }>()
  useEffect(() => {
    if (local) return
    let controller: AbortController | undefined
    const refresh = () => {
      controller?.abort()
      const request = new AbortController()
      controller = request
      setOperations(previous => previous ? { ...previous, updating: true } : undefined)
      getMemory<Operations>('/operations', request.signal).then(data => {
        if (!data.worker || (data.processing && !Array.isArray(data.processing.jobs))) throw new Error('Ungültiger Betriebsstand')
        if (!request.signal.aborted) setOperations({ data, checkedAt: new Date().toISOString() })
      }).catch(error => {
        if (!request.signal.aborted) setOperations({ error: error instanceof Error ? error.message : 'Der Verarbeitungsstand ist nicht erreichbar.', checkedAt: new Date().toISOString() })
      })
    }
    refresh()
    const timer = window.setInterval(refresh, 30_000)
    return () => { controller?.abort(); window.clearInterval(timer) }
  }, [local, dataVersion, location.page])
  const operationalStatus = operationsStatus(operations?.updating ? undefined : operations?.data)
  const processing = operations?.updating ? undefined : operations?.data?.processing
  const aggregateBlocker = processingFence(processing) === true ? processing?.blocking_job : undefined
  const leasedJob = processing?.jobs.find(job => job.id === operations?.data?.worker.job_id)
  const problemJob = aggregateBlocker || leasedJob || (operationalStatus.kind === 'paused' ? processing?.jobs.find(job => job.technical_isolation !== true && job.state === 'review') : processing?.jobs.find(job => job.state === 'review'))
  const problemReason = operations?.data?.worker.reason || problemJob?.reason
  useEffect(() => {
    document.documentElement.classList.add('light')
    document.documentElement.style.colorScheme = 'light'
    let meta = document.querySelector<HTMLMetaElement>('meta[name=theme-color]')
    if (!meta) { meta = document.createElement('meta'); meta.name = 'theme-color'; document.head.append(meta) }
    meta.content = '#f2f5f5'
    try { localStorage.removeItem('mos_theme') } catch { /* Light mode does not depend on storage. */ }
    const shortcut = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { if (document.querySelector('[role=dialog]') && !document.querySelector('.px-navigation-dialog')) return; e.preventDefault(); if (!document.querySelector('.px-navigation-dialog')) { navigationFocus.current = document.activeElement as HTMLElement; navigationDestination.current = false } setQuery(''); setNavigation(value => value ? null : 'search') } }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])
  useEffect(() => { document.documentElement.lang = 'de'; document.title = `${pageNames[location.page]} · Meeting OS` }, [location.page])
  function leaving() { navigationDestination.current = true; rememberScroll(location.page); setSavedRoutes(previous => ({ ...previous, [location.page]: window.location.hash })); setNavigation(null) }
  const link = (id: Page, compact = false) => { const Icon = navIcons[id]; return <a href={savedRoutes[id] || `#${id}`} onClick={leaving} key={id} aria-current={location.page === id ? 'page' : undefined}><Icon size={17} aria-hidden="true" /><span>{pageNames[id]}{!compact && navigation && <small>{hints[id]}</small>}</span>{navigation && <ChevronRight size={14} aria-hidden="true" />}</a> }
  return <div className="px-shell" data-density={preferences.density}><a className="wm-skip" href="#working-memory-main" onClick={event => { event.preventDefault(); document.getElementById('working-memory-main')?.focus() }}>Zum Inhalt springen</a>
    <aside className="px-sidebar px-appnav"><a className="px-brand" href="#uebersicht" onClick={leaving}><span className="px-brand-mark" aria-hidden="true"><CircleDot size={21} /></span><span translate="no">Meeting OS</span></a><button type="button" className="px-nav-search" onClick={()=>{navigationFocus.current=document.activeElement as HTMLElement;navigationDestination.current=false;setQuery('');setNavigation('search')}}><Search size={15} aria-hidden="true" /><span>Bereich öffnen</span><kbd>⌘ K</kbd></button><nav aria-label="Hauptnavigation">{groups.map(g=><div className="px-nav-group" key={g.label}><p>{g.label}</p>{g.items.map(id=>link(id,true))}</div>)}</nav><div className="px-sidebar-bottom"><nav aria-label="Verwaltung">{link('einstellungen',true)}</nav>{!local&&<button type="button" onClick={async()=>{try{await signOut()}catch{setError('Abmelden fehlgeschlagen. Bitte erneut versuchen.')}}}><LogOut size={17} aria-hidden="true" />Abmelden</button>}<div className="px-profile"><span className="px-avatar" aria-hidden="true">GK</span><span><strong>Gleb Komzin</strong><small>Teamleitung{local?' · Entwurf':''}</small></span></div></div></aside>
    <main id="working-memory-main" tabIndex={-1}><div className="px-contextbar"><nav aria-label="Seitenpfad"><a href="#uebersicht" onClick={leaving}>Arbeitsbereich</a><ChevronRight size={12} aria-hidden="true" /><span aria-current="page">{pageNames[location.page]}</span></nav><button className="px-icon-button" type="button" aria-label="Bereich suchen" onClick={()=>{navigationFocus.current=document.activeElement as HTMLElement;navigationDestination.current=false;setQuery('');setNavigation('search')}}><Search size={15} aria-hidden="true" /></button></div>{error&&<p role="alert">{error}</p>}{!local && <section className="wm-panel" style={{ overflowWrap: 'anywhere' }} aria-label="Verarbeitungsstatus" role="status" aria-live="polite"><strong>Verarbeitung</strong>{!operations ? <p>Verarbeitungsstand wird geladen…</p> : <><p className={operations.error || ['paused', 'unknown', 'waiting'].includes(operationalStatus.kind) ? 'wm-note' : undefined}>{operations.updating ? 'Der Verarbeitungsstand wird aktualisiert; der aktuelle Status ist noch unbestätigt.' : operations.error ? `Verarbeitungsstatus unbekannt: ${operations.error}` : operationalStatus.message}</p>{processing && <p>{numberLabel(processing.pending_count)} Quellen noch unvollständig. {isolationMessage(processing)}</p>}{!operations.updating && problemReason && <p className="wm-note">{problemJob?.title && <>{problemJob.title}: </>}{processingReason(problemReason)} <small>Technischer Grund: <code>{problemReason}</code>.</small></p>}{!operations.updating && operations.data?.worker.error_type && <p className="wm-note">Gemeldeter technischer Fehler: <code>{operations.data.worker.error_type}</code>.{operations.data.worker.transient === true && ' Eine vorübergehende Störung ist gemeldet; eine Fortsetzung ist noch nicht bestätigt.'}</p>}{!operations.updating && operations.data?.worker.previous_transient && <p className="wm-note">Frühere technische Unterbrechung: {operations.data.worker.previous_transient.error_type ? <code>{operations.data.worker.previous_transient.error_type}</code> : 'Fehlertyp nicht angegeben'}. Ihre Behebung ist noch nicht bestätigt.</p>}<p className="wm-muted">{operations.error ? 'Letzter Abrufversuch' : 'Letzter bestätigter Abruf'}: {new Date(operations.checkedAt).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin' })} · Aktualisierung alle 30 Sekunden.</p></>}<a className="wm-button" style={{ display: 'inline-flex', marginTop: 8 }} href="#einstellungen?section=verarbeitung" onClick={leaving}>Verarbeitung und Fehler prüfen</a></section>}<div hidden={['archiv','einstellungen','fragen'].includes(location.page)}><ProductivityPage page={location.page} local={local} dataVersion={dataVersion} cacheScope={userId ? `${SUPABASE_URL}:${userId}` : ''} /></div><div hidden={location.page!=='fragen'}><NotesChat /></div><div hidden={location.page!=='archiv'} className="px-archive">{archiveVisited && <ArchivePage />}</div>{location.page==='einstellungen'&&<SettingsPage cacheScope={userId ? `${SUPABASE_URL}:${userId}` : ''} local={local} onChanged={()=>setDataVersion(v=>v+1)} />}</main>
    <nav className="px-mobile-nav" aria-label="Mobile Hauptnavigation">{['uebersicht','todos','team'].map(id=>link(id as Page,true))}<button type="button" aria-label="Alle Bereiche öffnen" aria-expanded={navigation==='menu'} onClick={()=>{navigationFocus.current=document.activeElement as HTMLElement;navigationDestination.current=false;setQuery('');setNavigation('menu')}}><Menu size={18} aria-hidden="true" /><span>Mehr</span></button></nav>
    {navigation&&<Dialog open onOpenChange={open=>{if(!open)setNavigation(null)}}><DialogContent className="wm-dialog px-dialog px-navigation-dialog" overlayClassName="wm-overlay px-overlay" closeLabel="Navigation schließen" onCloseAutoFocus={e=>{e.preventDefault(); if(navigationDestination.current) document.getElementById('working-memory-main')?.focus(); else navigationFocus.current?.focus()}}><DialogHeader><DialogTitle>{navigation==='search'?'Bereich öffnen':'Alle Bereiche'}</DialogTitle><DialogDescription>Wechsle direkt zu deiner Arbeit, deinem Wissen oder den Einstellungen.</DialogDescription></DialogHeader><label className="px-search"><Search size={16} aria-hidden="true" /><input type="search" name="navigation_search" autoComplete="off" aria-label="Bereiche durchsuchen" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Zum Beispiel Team oder Meetings…" /></label><nav className="px-destination-list" aria-label="Bereichsauswahl">{destinations.filter(id=>`${pageNames[id]} ${hints[id]}`.toLocaleLowerCase('de').includes(query.trim().toLocaleLowerCase('de'))).map(id=>link(id))}{!destinations.some(id=>`${pageNames[id]} ${hints[id]}`.toLocaleLowerCase('de').includes(query.trim().toLocaleLowerCase('de')))&&<p className="px-empty">Kein passender Bereich. Versuche einen anderen Begriff.</p>}</nav>{!local&&navigation==='menu'&&<button className="px-button" type="button" onClick={async()=>{try{await signOut()}catch{setError('Abmelden fehlgeschlagen. Bitte erneut versuchen.');setNavigation(null)}}}>Abmelden</button>}<p className="px-navigation-hint">Tastatur: Tab zum Auswählen · Enter zum Öffnen · Esc zum Schließen</p></DialogContent></Dialog>}
  </div>
}
export default function MemoryApp() {
  const [auth, setAuth] = useState<{ session: Session | null; error?: string }>()
  const [recovery, setRecovery] = useState(recoveryRequested)
  const [failedLink, setFailedLink] = useState(recoveryLinkFailed)
  useEffect(() => {
    document.documentElement.lang = 'de'
    let active = true
    let observed = false
    const { data: { subscription } } = onAuthStateChange((session, event) => {
      if (!active) return
      observed = true
      if (event === 'PASSWORD_RECOVERY') { setRecovery(true); setFailedLink(false) }
      if (!session) clearSnapshots()
      setAuth({ session })
    })
    getSession().then(session => { if (active && !observed) setAuth({ session }) }).catch(() => {
      if (active && !observed) setAuth({ session: null, error: 'Die Anmeldung konnte nicht geprüft werden. Bitte lade die Seite erneut.' })
    })
    return () => { active = false; subscription.unsubscribe() }
  }, [])
  function finishRecovery() {
    const url = new URL(window.location.href)
    url.searchParams.delete('recovery'); url.hash = '#arbeitsstand'
    window.history.replaceState(null, '', url)
    setRecovery(false); setFailedLink(false)
  }
  if (!auth) return <p className="wm-panel" role="status">Anmeldung wird geprüft…</p>
  if (auth.error) return <p className="wm-panel" role="alert">{auth.error}</p>
  if (failedLink || (recovery && !auth.session)) return <Login expired onSignedIn={finishRecovery} />
  if (recovery && auth.session) return <PasswordRecovery onComplete={finishRecovery} />
  return auth.session ? <MemoryShell key={auth.session.user.id} userId={auth.session.user.id} /> : <Login />
}
