import { Eye, EyeOff, KeyRound, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { AuthCard, ErrorBox, FIELD, PRIMARY } from './LoginScreen'

export function readSetupLink() {
  const match = window.location.hash.match(/^#\/set-password\/([^/]+)\/([^/]+)$/)
  return match ? { uid: match[1], token: match[2] } : null
}

export default function SetPasswordScreen({ link, onDone }) {
  const [state, setState] = useState({ status: 'checking', username: '' })
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/auth/check-link', { method: 'POST', body: link })
      .then((r) => setState({ status: r.valid ? 'ready' : 'invalid', username: r.username ?? '' }))
      .catch(() => setState({ status: 'offline', username: '' }))
  }, [link])

  async function submit(e) {
    e.preventDefault()
    if (busy) return
    if (password !== confirm) {
      setError('The two passwords do not match.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const r = await api('/api/auth/set-password', { method: 'POST', body: { ...link, password } })
      onDone(`Password saved. Sign in as ${r.username}.`)
    } catch (err) {
      setError(err.status ? err.message : 'Cannot reach the dashboard service. Try again shortly.')
    } finally {
      setBusy(false)
    }
  }

  if (state.status !== 'ready') {
    const message = {
      checking: 'Checking your link…',
      invalid: 'This link has expired or was already used. Go back and choose “Forgot password?” to get a new one.',
      offline: 'Cannot reach the dashboard service. Try again shortly.',
    }[state.status]
    return (
      <AuthCard onSubmit={(e) => e.preventDefault()} subtitle="Set your password">
        {state.status === 'checking' ? (
          <p className="mt-8 text-sm text-muted">{message}</p>
        ) : (
          <ErrorBox>{message}</ErrorBox>
        )}
        <button type="button" onClick={() => onDone('')} className={PRIMARY}>
          Go to sign in
        </button>
      </AuthCard>
    )
  }

  return (
    <AuthCard onSubmit={submit} subtitle="Set your password">
      <p className="mt-8 text-sm leading-relaxed text-muted">
        Choose a password for <span className="font-medium text-slate-100">{state.username}</span>. Use at least 12
        characters, and avoid common words or anything like your username.
      </p>
      <input type="text" autoComplete="username" value={state.username} readOnly hidden />

      <label className="mt-5 block text-sm text-muted" htmlFor="new-password">
        New password
      </label>
      <div className="relative">
        <input
          id="new-password"
          type={reveal ? 'text' : 'password'}
          autoComplete="new-password"
          autoFocus
          required
          minLength={12}
          maxLength={256}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={`${FIELD} pr-12`}
        />
        <button
          type="button"
          onClick={() => setReveal((r) => !r)}
          aria-label={reveal ? 'Hide password' : 'Show password'}
          className="absolute inset-y-0 right-0 mt-2 grid w-12 place-items-center text-muted hover:text-slate-200"
        >
          {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>

      <label className="mt-5 block text-sm text-muted" htmlFor="confirm-password">
        Type it again
      </label>
      <input
        id="confirm-password"
        type={reveal ? 'text' : 'password'}
        autoComplete="new-password"
        required
        maxLength={256}
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        className={FIELD}
      />

      {error && <ErrorBox>{error}</ErrorBox>}

      <button type="submit" disabled={busy} className={PRIMARY}>
        {busy ? <Loader2 className="size-4 animate-spin" /> : <KeyRound className="size-4" />}
        {busy ? 'Saving…' : 'Save password'}
      </button>
    </AuthCard>
  )
}
