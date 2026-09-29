import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const POLL_MS = 5_000

export const lagosMs = (iso) => (iso ? Date.parse(`${iso}+01:00`) : null)

export function useLive() {
  const [live, setLive] = useState(null)
  const [offset, setOffset] = useState(0)
  const [failing, setFailing] = useState(false)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const json = await api('/api/live')
        if (!alive) return
        setLive(json)
        setOffset(lagosMs(json.now) - Date.now())
        setFailing(false)
      } catch {
        if (alive) setFailing(true)
      }
    }
    load()
    const id = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  return { live, offset, failing }
}
