import { useEffect, useState } from 'react'
export interface Preferences { startPage: 'uebersicht' | 'todos' | 'team'; taskView: 'list' | 'week'; density: 'compact' | 'comfortable' }
export const defaults: Preferences = { startPage: 'uebersicht', taskView: 'list', density: 'compact' }
const key = 'mos_preferences_v1'
export function readPreferences(): Preferences {
  try { const value = JSON.parse(localStorage.getItem(key) || '{}'); return {
    startPage: ['uebersicht', 'todos', 'team'].includes(value.startPage) ? value.startPage : defaults.startPage,
    taskView: ['list', 'week'].includes(value.taskView) ? value.taskView : defaults.taskView,
    density: ['compact', 'comfortable'].includes(value.density) ? value.density : defaults.density,
  } } catch { return defaults }
}
export function savePreferences(value: Preferences) { localStorage.setItem(key, JSON.stringify(value)); window.dispatchEvent(new Event('mos-preferences')) }
export function usePreferences() {
  const [preferences, setPreferences] = useState(readPreferences)
  useEffect(() => { const update = () => setPreferences(readPreferences()); window.addEventListener('mos-preferences', update); window.addEventListener('storage', update); return () => { window.removeEventListener('mos-preferences', update); window.removeEventListener('storage', update) } }, [])
  return preferences
}
