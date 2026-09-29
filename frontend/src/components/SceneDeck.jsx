import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'

const EASE = [0.16, 1, 0.3, 1]

export default function SceneDeck({ scenes, data, interrupt = false, onSceneChange }) {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [held, setHeld] = useState(false)
  const [lastInterrupt, setLastInterrupt] = useState(interrupt)

  if (interrupt !== lastInterrupt) {
    setLastInterrupt(interrupt)
    setIndex(0)
  }

  const current = index % scenes.length
  const scene = scenes[current]
  const Scene = scene.Component

  useEffect(() => {
    onSceneChange?.(scene.id)
  }, [scene.id, onSceneChange])

  useEffect(() => {
    const onHold = (e) => setHeld(Boolean(e.detail))
    window.addEventListener('pulse-hold', onHold)
    return () => window.removeEventListener('pulse-hold', onHold)
  }, [])

  useEffect(() => {
    if (paused || held) return
    const id = setTimeout(() => setIndex((current + 1) % scenes.length), scene.seconds * 1000)
    return () => clearTimeout(id)
  }, [current, paused, held, scene.seconds, scenes.length])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight') setIndex((i) => (i + 1) % scenes.length)
      if (e.key === 'ArrowLeft') setIndex((i) => (i - 1 + scenes.length) % scenes.length)
      if (e.key === ' ') setPaused((p) => !p)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [scenes.length])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <SceneRail scenes={scenes} index={current} paused={paused || held} />
      <div className="relative min-h-0 flex-1">
        <AnimatePresence mode="wait">
          <motion.section
            key={scene.id}
            className="absolute inset-0 px-[3vw] pt-[2vh] pb-[3vh]"
            initial={{ opacity: 0, y: 40, filter: 'blur(14px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -40, filter: 'blur(14px)' }}
            transition={{ duration: 0.9, ease: EASE }}
          >
            <Scene data={data} />
          </motion.section>
        </AnimatePresence>
      </div>
    </div>
  )
}

function SceneRail({ scenes, index, paused }) {
  return (
    <div className="flex gap-3 px-[3vw] pt-[3vh]">
      {scenes.map((s, i) => (
        <div key={s.id} className="flex-1">
          <div
            className={`mb-2 text-[clamp(10px,0.75vw,15px)] font-medium tracking-[0.22em] uppercase transition-colors duration-700 ${
              s.id === 'alert' ? 'text-bad' : i === index ? 'text-slate-100' : 'text-muted/50'
            }`}
          >
            {s.title}
          </div>
          <div className="h-[3px] overflow-hidden rounded-full bg-white/10">
            {i < index && <div className="h-full w-full bg-white/30" />}
            {i === index &&
              (paused ? (
                <div className="h-full w-full bg-warn" />
              ) : (
                <motion.div
                  key={`${s.id}-${index}`}
                  className={`h-full ${s.id === 'alert' ? 'bg-bad' : 'bg-accent'}`}
                  initial={{ width: '0%' }}
                  animate={{ width: '100%' }}
                  transition={{ duration: s.seconds, ease: 'linear' }}
                />
              ))}
          </div>
        </div>
      ))}
    </div>
  )
}
