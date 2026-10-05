import { Activity, ArrowLeft, Eye, EyeOff, Loader2, Lock, Mail, ShieldCheck } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'
import { api } from '../lib/api'

const EASE = [0.16, 1, 0.3, 1]

export const FIELD =
  'mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-slate-100 outline-none focus:border-brand-soft/60 focus:ring-2 focus:ring-brand-soft/20'
export const PRIMARY =
  'mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 font-medium text-white ring-1 ring-brand-soft/30 transition hover:bg-brand/80 disabled:opacity-60'

export function AuthCard({ onSubmit, subtitle, children }) {
  return (
    <div className="grid flex-1 place-items-center px-4">
      <motion.form
        onSubmit={onSubmit}
        className="w-full max-w-[420px] rounded-3xl border border-white/[0.08] bg-white/[0.03] p-8 backdrop-blur-xl"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: EASE }}
      >
        <div className="flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-2xl bg-brand text-brand-soft ring-1 ring-brand-soft/25">
            <Activity className="size-5" strokeWidth={2.25} />
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight">Dash Pulse</div>
            <div className="text-sm text-muted">{subtitle}</div>
          </div>
        </div>
        {children}
      </motion.form>
    </div>
  )
}

export function ErrorBox({ children }) {
  return (
    <div role="alert" className="mt-5 rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-sm text-bad">
      {children}
    </div>
  )
}

export default function LoginScreen({ onSignIn, notice = '' }) {
  const [forgot, setForgot] = useState(false)
  if (forgot) return <ForgotForm onBack={() => setForgot(false)} />
  return <SignInForm onSignIn={onSignIn} notice={notice} onForgot={() => setForgot(true)} />
}

function SignInForm({ onSignIn, notice, onForgot }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await onSignIn(username.trim(), password, remember)
    } catch (err) {
      setError(err.status ? err.message : 'Cannot reach the dashboard service. Try again shortly.')
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard onSubmit={submit} subtitle="Sign in to view the operations dashboard">
      {notice && (
        <div className="mt-6 rounded-xl border border-good/30 bg-good/10 px-4 py-3 text-sm text-good">{notice}</div>
      )}

      <label className="mt-8 block text-sm text-muted" htmlFor="username">
        Username
      </label>
      <input
        id="username"
        autoComplete="username"
        autoFocus
        required
        maxLength={150}
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        className={FIELD}
      />

      <label className="mt-5 block text-sm text-muted" htmlFor="password">
        Password
      </label>
      <div className="relative mt-2">
        <input
          id="password"
          type={reveal ? 'text' : 'password'}
          autoComplete="current-password"
          required
          maxLength={256}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-xl border border-white/10 bg-black/30 py-3 pr-12 pl-4 text-slate-100 outline-none focus:border-brand-soft/60 focus:ring-2 focus:ring-brand-soft/20"
        />
        <button
          type="button"
          onClick={() => setReveal((r) => !r)}
          aria-label={reveal ? 'Hide password' : 'Show password'}
          className="absolute inset-y-0 right-0 grid w-12 place-items-center text-muted hover:text-slate-200"
        >
          {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>

      <label className="mt-5 flex items-center gap-3 text-sm text-slate-300">
        <input
          type="checkbox"
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
          className="size-4 accent-[var(--color-brand-soft)]"
        />
        Keep this screen signed in for 30 days
      </label>

      {error && <ErrorBox>{error}</ErrorBox>}

      <button type="submit" disabled={busy} className={PRIMARY}>
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Lock className="size-4" />}
        {busy ? 'Signing in…' : 'Sign in'}
      </button>

      <button
        type="button"
        onClick={onForgot}
        className="mt-4 w-full text-center text-sm text-muted transition hover:text-slate-200"
      >
        Forgot password?
      </button>

      <div className="mt-6 flex items-center gap-2 text-xs text-muted">
        <ShieldCheck className="size-3.5 text-good" />
        Only use this on trusted screens. Accounts are issued by the operations team.
      </div>
    </AuthCard>
  )
}

function ForgotForm({ onBack }) {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api('/api/auth/forgot', { method: 'POST', body: { email: email.trim() } })
      setSent(true)
    } catch (err) {
      setError(err.status ? err.message : 'Cannot reach the dashboard service. Try again shortly.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard onSubmit={submit} subtitle="Reset your password">
      {sent ? (
        <div className="mt-8 rounded-xl border border-good/30 bg-good/10 px-4 py-3 text-sm leading-relaxed text-good">
          If that email belongs to an account, a link to choose a new password is on its way. It expires in 24 hours.
          Check your junk folder if it does not arrive in a few minutes.
        </div>
      ) : (
        <>
          <p className="mt-8 text-sm leading-relaxed text-muted">
            Enter the email address on your account and we will send you a link to choose a new password.
          </p>
          <label className="mt-5 block text-sm text-muted" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            autoFocus
            required
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={FIELD}
          />
          {error && <ErrorBox>{error}</ErrorBox>}
          <button type="submit" disabled={busy} className={PRIMARY}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Mail className="size-4" />}
            {busy ? 'Sending…' : 'Email me a link'}
          </button>
        </>
      )}
      <button
        type="button"
        onClick={onBack}
        className="mt-4 flex w-full items-center justify-center gap-2 text-sm text-muted transition hover:text-slate-200"
      >
        <ArrowLeft className="size-4" /> Back to sign in
      </button>
    </AuthCard>
  )
}
