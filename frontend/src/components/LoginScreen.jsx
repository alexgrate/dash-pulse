import { Activity, Eye, EyeOff, Loader2, Lock, ShieldCheck } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'

const EASE = [0.16, 1, 0.3, 1]

export default function LoginScreen({ onSignIn }) {
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
    <div className="grid flex-1 place-items-center px-4">
      <motion.form
        onSubmit={submit}
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
            <div className="text-sm text-muted">Sign in to view the operations dashboard</div>
          </div>
        </div>

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
          className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-slate-100 outline-none focus:border-brand-soft/60 focus:ring-2 focus:ring-brand-soft/20"
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

        {error && (
          <div role="alert" className="mt-5 rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-sm text-bad">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 font-medium text-white ring-1 ring-brand-soft/30 transition hover:bg-brand/80 disabled:opacity-60"
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Lock className="size-4" />}
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <div className="mt-6 flex items-center gap-2 text-xs text-muted">
          <ShieldCheck className="size-3.5 text-good" />
          Only use this on trusted screens. Accounts are issued by the operations team.
        </div>
      </motion.form>
    </div>
  )
}
