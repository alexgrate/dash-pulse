import { motion } from 'motion/react'
import { useEffect, useMemo, useState } from 'react'
import { NIGERIA } from '../lib/nigeria'

const LON_MIN = 2.5
const LAT_MAX = 14.0
const SCALE = 100
const X_FACTOR = Math.cos((9 * Math.PI) / 180)
const W = (14.9 - LON_MIN) * SCALE * X_FACTOR
const H = (LAT_MAX - 4.1) * SCALE

const project = (lon, lat) => [(lon - LON_MIN) * SCALE * X_FACTOR, (LAT_MAX - lat) * SCALE]

const OUTLINE = NIGERIA.map(
  (ring) =>
    ring.map(([lon, lat], i) => `${i ? 'L' : 'M'}${project(lon, lat).map((v) => v.toFixed(1))}`).join(' ') + 'Z',
).join(' ')

const PING_EVERY_MS = 450
const PING_LIFE_MS = 2200

export default function NigeriaMap({ points, cities }) {
  const max = Math.max(1, ...points.map((p) => p.count))
  const weighted = useMemo(() => points.flatMap((p) => Array(Math.min(p.recent * 3 + 1, 40)).fill(p)), [points])
  const [pings, setPings] = useState([])

  useEffect(() => {
    if (weighted.length === 0) return
    const id = setInterval(() => {
      const p = weighted[Math.floor(Math.random() * weighted.length)]
      const now = Date.now()
      setPings((list) => [
        ...list.filter((x) => now - x.born < PING_LIFE_MS),
        { id: `${now}-${p.lat}-${p.lon}`, born: now, ...p },
      ])
    }, PING_EVERY_MS)
    return () => clearInterval(id)
  }, [weighted])

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 size-full overflow-visible">
      <defs>
        <radialGradient id="dotGlow">
          <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.9" />
          <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="landFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.07" />
          <stop offset="100%" stopColor="var(--color-glow)" stopOpacity="0.04" />
        </linearGradient>
      </defs>

      <motion.path
        d={OUTLINE}
        fill="url(#landFill)"
        stroke="var(--color-accent)"
        strokeOpacity="0.55"
        strokeWidth="2.5"
        strokeLinejoin="round"
        style={{ filter: 'drop-shadow(0 0 10px rgba(96,165,250,0.45))' }}
        initial={{ pathLength: 0, fillOpacity: 0 }}
        animate={{ pathLength: 1, fillOpacity: 1 }}
        transition={{ duration: 2.2, ease: 'easeInOut' }}
      />

      {points.map((p, i) => {
        const [x, y] = project(p.lon, p.lat)
        const r = 4 + Math.sqrt(p.count / max) * 26
        return (
          <motion.circle
            key={`${p.lat}-${p.lon}`}
            cx={x}
            cy={y}
            r={r}
            fill="url(#dotGlow)"
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.8 + Math.min(i, 40) * 0.03 }}
            style={{ transformOrigin: `${x}px ${y}px` }}
          />
        )
      })}

      {pings.map((p) => {
        const [x, y] = project(p.lon, p.lat)
        return (
          <g key={p.id}>
            <motion.circle
              cx={x}
              cy={y}
              fill="none"
              stroke="var(--color-good)"
              strokeWidth="2"
              initial={{ r: 2, opacity: 0.9 }}
              animate={{ r: 38, opacity: 0 }}
              transition={{ duration: PING_LIFE_MS / 1000, ease: 'easeOut' }}
            />
            <motion.circle
              cx={x}
              cy={y}
              r={4}
              fill="var(--color-good)"
              initial={{ opacity: 1 }}
              animate={{ opacity: 0 }}
              transition={{ duration: 1.2 }}
            />
          </g>
        )
      })}

      {cities.slice(0, 5).map((c, i) => {
        const [x, y] = project(c.lon, c.lat)
        return (
          <motion.g
            key={c.city}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.6 + i * 0.15 }}
          >
            <circle cx={x} cy={y} r={4} fill="#e8ecf6" />
            <text x={x + 12} y={y + 6} fill="#e8ecf6" fontSize="26" fontWeight="600" fontFamily="var(--font-sans)">
              {c.city}
            </text>
          </motion.g>
        )
      })}
    </svg>
  )
}
