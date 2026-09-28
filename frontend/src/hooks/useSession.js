import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'

const RETRY_MS = 10_000

async function fetchSession() {
  try {
    const s = await api('/api/auth/session')
    return { status: s.authenticated ? 'in' : 'out', username: s.username, isAdmin: Boolean(s.is_admin) }
  } catch {
    return { status: 'offline', username: null, isAdmin: false }
  }
}

export function useSession() {
  const [state, setState] = useState({ status: 'loading', username: null, isAdmin: false })

  useEffect(() => {
    if (state.status !== 'loading' && state.status !== 'offline') return
    let alive = true
    const id = setTimeout(
      () => fetchSession().then((next) => alive && setState(next)),
      state.status === 'offline' ? RETRY_MS : 0,
    )
    return () => {
      alive = false
      clearTimeout(id)
    }
  }, [state.status])

  const signIn = useCallback(async (username, password, remember) => {
    const s = await api('/api/auth/login', { method: 'POST', body: { username, password, remember } })
    setState({ status: 'in', username: s.username, isAdmin: Boolean(s.is_admin) })
  }, [])

  const signOut = useCallback(async () => {
    await api('/api/auth/logout', { method: 'POST', body: {} }).catch(() => {})
    setState(await fetchSession())
  }, [])

  const expired = useCallback(() => setState({ status: 'out', username: null, isAdmin: false }), [])

  return { ...state, signIn, signOut, expired }
}
