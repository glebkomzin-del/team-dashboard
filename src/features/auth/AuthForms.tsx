import { useEffect, useRef, useState } from 'react'
import { resetPassword, signIn, signOut, updatePassword } from '@/auth'

function Feedback({ error, message }: { error: string; message?: string }) {
  const ref = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (error || message) ref.current?.focus() }, [error, message])
  if (!error && !message) return null
  return <p ref={ref} tabIndex={-1} role={error ? 'alert' : 'status'}>{error || message}</p>
}

export function Login({ expired = false, onSignedIn }: { expired?: boolean; onSignedIn?: () => void }) {
  const [reset, setReset] = useState(expired)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  return <main className="working-memory wm-login">
    <p className="wm-eyebrow" translate="no">MEETING OS</p>
    <h1>{reset ? 'Passwort zurücksetzen' : 'Dein Arbeitsgedächtnis'}</h1>
    <p className="wm-muted">{reset ? 'Du erhältst einen Link, mit dem du ein neues Passwort festlegen kannst.' : 'Melde dich mit deinem bestehenden Dashboard-Konto an.'}</p>
    {expired && <p className="wm-note">Dieser Wiederherstellungslink ist abgelaufen oder ungültig. Fordere bitte einen neuen an.</p>}
    <form className="wm-controls" onSubmit={async event => {
      event.preventDefault(); if (busy || sent) return
      setBusy(true); setError('')
      try {
        if (reset) { await resetPassword(email); setSent(true) }
        else { await signIn(email, password); setPassword(''); onSignedIn?.() }
      } catch {
        setError(reset ? 'Der Link konnte nicht angefordert werden. Bitte versuche es später erneut.' : 'Anmeldung fehlgeschlagen. Prüfe E-Mail und Passwort und versuche es erneut.')
      } finally { setBusy(false) }
    }}>
      <label>E-Mail<input type="email" spellCheck={false} name="email" autoComplete="username" required disabled={busy || sent} value={email} onChange={event => setEmail(event.target.value)} /></label>
      {!reset && <label>Passwort<input type="password" name="password" autoComplete="current-password" required disabled={busy} value={password} onChange={event => setPassword(event.target.value)} /></label>}
      <Feedback error={error} message={sent ? 'Falls ein Konto mit dieser E-Mail existiert, ist der Link unterwegs. Schau auch im Spam-Ordner nach.' : ''} />
      {!sent && <button type="submit" className="wm-button" disabled={busy}>{busy ? (reset ? 'Link wird angefordert…' : 'Anmeldung läuft…') : (reset ? 'Link anfordern' : 'Anmelden')}</button>}
    </form>
    <button type="button" className="wm-link" disabled={busy} onClick={() => { setReset(!reset); setError(''); setSent(false); setPassword('') }}>{reset ? 'Zur Anmeldung' : 'Passwort vergessen?'}</button>
  </main>
}

export function PasswordRecovery({ onComplete }: { onComplete: () => void }) {
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  return <main className="working-memory wm-login">
    <p className="wm-eyebrow" translate="no">MEETING OS</p><h1>Neues Passwort festlegen</h1>
    <p className="wm-muted">Verwende mindestens acht Zeichen. Dein Passwortmanager kann dir ein sicheres Passwort vorschlagen.</p>
    <form className="wm-controls" onSubmit={async event => {
      event.preventDefault(); if (busy || saved) return
      if (password !== confirmation) { setError('Die beiden Passwörter stimmen nicht überein.'); return }
      setBusy(true); setError('')
      try { await updatePassword(password); setPassword(''); setConfirmation(''); setSaved(true) }
      catch (cause) {
        const code = cause && typeof cause === 'object' && 'code' in cause ? cause.code : ''
        setError(code === 'same_password' ? 'Wähle bitte ein anderes Passwort als bisher.' : code === 'weak_password' ? 'Dieses Passwort ist zu schwach. Verwende ein längeres, einmaliges Passwort.' : 'Das Passwort konnte nicht gespeichert werden. Versuche es erneut oder fordere einen neuen Wiederherstellungslink an.')
      } finally { setBusy(false) }
    }}>
      {!saved && <><label>Neues Passwort<input name="new-password" type="password" autoComplete="new-password" minLength={8} required disabled={busy} value={password} onChange={event => setPassword(event.target.value)} /></label><label>Passwort wiederholen<input name="confirm-password" type="password" autoComplete="new-password" minLength={8} required disabled={busy} value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label></>}
      <Feedback error={error} message={saved ? 'Dein neues Passwort ist gespeichert.' : ''} />
      {!saved && <button type="submit" className="wm-button" disabled={busy}>{busy ? 'Passwort wird gespeichert…' : 'Passwort speichern'}</button>}
    </form>
    {saved ? <button type="button" className="wm-button" onClick={onComplete}>Zum Arbeitsstand</button> : <button type="button" className="wm-link" disabled={busy} onClick={async () => { setBusy(true); try { await signOut(); onComplete() } catch { setError('Abmelden fehlgeschlagen. Bitte erneut versuchen.') } finally { setBusy(false) } }}>Abbrechen und abmelden</button>}
  </main>
}
