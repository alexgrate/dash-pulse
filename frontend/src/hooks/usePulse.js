import { useEffect, useState } from 'react'

const POLL_MS = 20_000

export function usePulse() {
  const [data, setData] = useState(null)
  const [offline, setOffline] = useState(false)
  const [clockOffset, setClockOffset] = useState(0)

  useEffect(() => {
    let alive = true

    async function load() {
      try {
        const res = await fetch('/api/pulse')
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = await res.json()
        if (alive) {
          setData(json)
          setOffline(false)
          if (json.server_time) setClockOffset(Date.parse(`${json.server_time}+01:00`) - Date.now())
        }
      } catch {
        if (alive) setOffline(true)
      }
    }

    load()
    const id = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  return { data, offline: offline || Boolean(data?.stale), clockOffset }
}
