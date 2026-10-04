import { useEffect } from 'react'

const IDLE_MS = 3000

export function useIdleCursor(active = true) {
  useEffect(() => {
    if (!active) {
      document.body.classList.remove('cursor-idle')
      return
    }
    let id
    const wake = () => {
      document.body.classList.remove('cursor-idle')
      clearTimeout(id)
      id = setTimeout(() => document.body.classList.add('cursor-idle'), IDLE_MS)
    }
    wake()
    window.addEventListener('mousemove', wake)
    window.addEventListener('keydown', wake)
    return () => {
      clearTimeout(id)
      window.removeEventListener('mousemove', wake)
      window.removeEventListener('keydown', wake)
    }
  }, [active])
}
