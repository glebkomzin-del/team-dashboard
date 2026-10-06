import { useEffect, useState } from 'react'
import { readPreferences } from './preferences'
import type { Snapshot, Work } from './types'

export type Page = 'uebersicht' | 'einstellungen' | 'todos' | 'team' | 'wissen' | 'pruefen' | 'archiv' | 'fragen' | 'betrieb'
export interface Member { id: string; name: string; active: boolean; aliases: string[] }
export interface PlanningEvent { command_id: string; actor_id: string; event_date: string; action: string; reason: string; patch: Record<string, unknown> }
export interface PlannedWork extends Work {
  origin?: 'manual'; scheduled_date?: string | null; priority?: 'low' | 'normal' | 'high'
  estimate_minutes?: number | null; note?: string; planning_history?: PlanningEvent[]
}
export interface PlannedSnapshot extends Snapshot { planner?: { supported: boolean; team: Member[] } }
export const statusNames = { open: 'Offen', waiting: 'Blockiert', done: 'Erledigt', cancelled: 'Entfallen', dismissed: 'Verworfen' }
export const priorityNames = { low: 'Niedrig', normal: 'Normal', high: 'Hoch' }
export const pageNames: Record<Page, string> = { uebersicht: 'Übersicht', einstellungen: 'Einstellungen', todos: 'Meine Todos', team: 'Mein Team', wissen: 'Themen & Wissen', pruefen: 'Prüfungen', archiv: 'Meetings', fragen: 'Notizen fragen', betrieb: 'Verarbeitung' }
export function localDay(d = new Date()) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
export function addDays(day: string, n: number) { const d = new Date(`${day}T12:00:00`); d.setDate(d.getDate() + n); return localDay(d) }
export function monday(day: string) { const d = new Date(`${day}T12:00:00`); return addDays(day, -((d.getDay() + 6) % 7)) }
export function isoDate(day: string | null | undefined): string | null { if (!day || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return null; const d = new Date(`${day}T12:00:00Z`); return !Number.isNaN(d.valueOf()) && d.toISOString().startsWith(day) ? day : null }
export function dueDate(work: PlannedWork) { return isoDate(work.due_date) || isoDate(work.due_text) }
export function personal(owner: string | null) { return ['gleb', 'gleb komzin', 'komzin gleb'].includes((owner || '').toLowerCase().replace(/[^a-z]+/g, ' ').trim()) }
export function memberFor(owner: string | null, team: Member[]) { const key = (owner || '').toLocaleLowerCase('de').trim(); return team.find(m => [m.name, ...m.aliases].some(n => n.toLocaleLowerCase('de').trim() === key)) }
export function allWork(data: PlannedSnapshot): PlannedWork[] { return ([...data.personal, ...data.waiting_dependencies, ...data.waiting, ...data.completed, ...(data.cancelled || [])] as PlannedWork[]).map(work => ({ ...work, last_changed: [work.last_changed, ...(work.planning_history || []).map(e => e.event_date)].sort().at(-1)! })) }
export function completedOn(work: PlannedWork) {
  const events = [...work.history, ...(work.planning_history || [])]
  return events.filter(e => e.action === 'done' || e.patch?.status === 'done').map(e => e.event_date).sort().at(-1)
}
export function route() {
  const [raw, query = ''] = window.location.hash.slice(1).split('?')
  const params = new URLSearchParams(query)
  if (raw === 'betrieb') {
    params.set('section', 'verarbeitung')
    return { page: 'einstellungen' as Page, params }
  }
  return { page: (Object.hasOwn(pageNames, raw) ? raw : raw === 'arbeitsstand' ? 'todos' : readPreferences().startPage) as Page, params }
}
const scrollPositions: Partial<Record<Page, number>> = {}
export function rememberScroll(page: Page) { scrollPositions[page] = window.scrollY }
export function rememberedScroll(page: Page) { return scrollPositions[page] || 0 }
export function navigate(page: Page, params = new URLSearchParams(), replace = false) {
  rememberScroll(route().page)
  const query = params.toString(); const url = `${window.location.pathname}${window.location.search}#${page}${query ? `?${query}` : ''}`
  window.history[replace ? 'replaceState' : 'pushState']({ ...window.history.state, workspace: true }, '', url)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
export function useRoute() {
  const [location, setLocation] = useState(route)
  useEffect(() => {
    const update = () => setLocation(route())
    window.addEventListener('hashchange', update)
    window.addEventListener('popstate', update)
    if (window.location.hash.slice(1).split('?')[0] === 'betrieb') navigate('einstellungen', route().params, true)
    return () => { window.removeEventListener('hashchange', update); window.removeEventListener('popstate', update) }
  }, [])
  return location
}
