import { motion } from 'motion/react'

const W = 1000
const H = 400
const PAD = 12
const x = (hour) => (hour / 23) * W
const y = (value, max) => H - PAD - (value / max) * (H - PAD * 2)

function linePath(values, max) {
  return values.map((v, h) => `${h ? 'L' : 'M'}${x(h).toFixed(1)},${y(v, max).toFixed(1)}`).join(' ')
}

function bandPath(high, low, max) {
  const top = high.map((v, h) => `${h ? 'L' : 'M'}${x(h).toFixed(1)},${y(v, max).toFixed(1)}`).join(' ')
  const bottom = low
    .map((v, h) => [h, v])
    .reverse()
    .map(([h, v]) => `L${x(h).toFixed(1)},${y(v, max).toFixed(1)}`)
    .join(' ')
  return `${top} ${bottom} Z`
}

export default function HourlyChart({ today, yesterday, hourNow, typical = null }) {
  const complete = today.slice(0, hourNow)
  const scale = typical ? [...complete, ...typical.hourly_high] : [...complete, ...yesterday]
  const max = Math.max(1, ...scale) * 1.15
  const ghost = yesterday.map((v) => Math.min(v, max * 0.98))
  const band = typical && bandPath(typical.hourly_high, typical.hourly_low, max)
  const line = complete.length > 1 ? linePath(complete, max) : ''
  const area = line && `${line} L${x(complete.length - 1)},${H} L0,${H} Z`
  const last = complete.length - 1

  return (
    <div className="relative size-full">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="size-full overflow-visible">
        <defs>
          <linearGradient id="todayFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1="0"
            x2={W}
            y1={H * f}
            y2={H * f}
            stroke="var(--color-line)"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {band && (
          <motion.path
            d={band}
            fill="var(--color-brand-soft)"
            fillOpacity="0.1"
            stroke="var(--color-brand-soft)"
            strokeOpacity="0.25"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1.2 }}
          />
        )}

        <motion.path
          d={linePath(ghost, max)}
          fill="none"
          stroke="var(--color-muted)"
          strokeOpacity="0.55"
          strokeWidth="2"
          strokeDasharray="5 7"
          vectorEffect="non-scaling-stroke"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1.2, delay: 0.3 }}
        />

        {area && (
          <motion.path
            d={area}
            fill="url(#todayFill)"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1.2, delay: 1.2 }}
          />
        )}
        {line && (
          <motion.path
            d={line}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ filter: 'drop-shadow(0 0 8px var(--color-accent))' }}
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.8, ease: 'easeInOut', delay: 0.4 }}
          />
        )}
      </svg>

      {last >= 1 && (
        <motion.span
          className="absolute size-3 -translate-x-1/2 -translate-y-1/2"
          style={{ left: `${(x(last) / W) * 100}%`, top: `${(y(complete[last], max) / H) * 100}%` }}
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 2.1 }}
        >
          <span className="absolute inset-0 animate-ping rounded-full bg-accent opacity-60" />
          <span className="absolute inset-0 rounded-full bg-accent" />
        </motion.span>
      )}

      <div className="absolute inset-x-0 -bottom-7 flex justify-between font-mono text-[clamp(10px,0.75vw,15px)] text-muted">
        {['00:00', '06:00', '12:00', '18:00', '23:00'].map((t) => (
          <span key={t}>{t}</span>
        ))}
      </div>
    </div>
  )
}
