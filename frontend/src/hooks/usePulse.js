import { useEffect, useState } from 'react'
import { api, Unauthorized } from '../lib/api'

const POLL_MS = 20_000

export function usePulse(enabled, onUnauthorized) {
  const [data, setData] = useState(null)
  const [offline, setOffline] = useState(false)
  const [clockOffset, setClockOffset] = useState(0)

  useEffect(() => {
    if (!enabled) return
    let alive = true

    async function load() {
      try {
        const json = await api('/api/pulse')
        if (alive) {
          setData(json)
          setOffline(false)
          if (json.server_time) setClockOffset(Date.parse(`${json.server_time}+01:00`) - Date.now())
        }
      } catch (e) {
        if (!alive) return
        if (e instanceof Unauthorized) onUnauthorized()
        else setOffline(true)
      }
    }

    load()
    const id = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [enabled, onUnauthorized])

  return { data: enabled ? data : null, offline: offline || Boolean(data?.stale), clockOffset }
}
