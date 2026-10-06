import type { AuthChangeEvent, Session } from '@supabase/supabase-js'
import { createClient } from '@supabase/supabase-js'

// Konfigurierbar über .env (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY);
// die Fallbacks halten den Build ohne .env lauffähig (Anon-Key ist öffentlich).
export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || 'https://lghwikeotbkmojyyjglz.supabase.co'
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM'

// Capture recovery intent before the auth client consumes the URL fragment.
const recoveryHash = new URLSearchParams(window.location.hash.slice(1))
export const recoveryRequested = new URLSearchParams(window.location.search).get('recovery') === '1' || recoveryHash.get('type') === 'recovery'
export const recoveryLinkFailed = recoveryHash.has('error') || recoveryHash.has('error_code')

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

export async function signIn(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
  if (error) throw error
  return data
}
export async function signOut() {
  const { error } = await supabase.auth.signOut({ scope: 'local' })
  if (error) throw error
}
export async function resetPassword(email: string) {
  const target = new URL(window.location.pathname === '/memory-next' ? '/memory-next' : '/', window.location.origin)
  target.searchParams.set('recovery', '1')
  const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: target.href })
  if (error) throw error
}
export async function updatePassword(password: string) {
  const { error } = await supabase.auth.updateUser({ password })
  if (error) throw error
}
export async function getSession() {
  const { data, error } = await supabase.auth.getSession()
  if (error) throw error
  return data.session
}
export function onAuthStateChange(callback: (session: Session | null, event: AuthChangeEvent) => void) {
  return supabase.auth.onAuthStateChange((event, session) => callback(session, event))
}
