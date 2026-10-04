import { motion } from 'motion/react'
import ChartHover, { TipNote, TipRow, TipTitle } from './ChartHover'

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

export default function HourlyChart({ today, yesterday, hourNow, typical = null, onPick }) {
  const complete = today.slice(0, hourNow)
  const scale = typical ? [...complete, ...typical.hourly_high] : [...complete, ...yesterday]
  const max = Math.max(1, ...scale) * 1.15
  const ghost = yesterday.map((v) => Math.min(v, max * 0.98))
  const band = typical && bandPath(typical.hourly_high, typical.hourly_low, max)
  const line = complete.length > 1 ? linePath(complete, max) : ''
  const area = line && `${line} L${x(complete.length - 1)},${H} L0,${H} Z`
  const last = complete.length - 1

  const weekday = typical?.weekday ?? 'day'

  const tip = (h) => {
    const label = `${String(h).padStart(2, '0')}:00–${String((h + 1) % 24).padStart(2, '0')}:00`
    const low = typical?.hourly_low?.[h]
    const high = typical?.hourly_high?.[h]
    const usual = typical?.hourly_median?.[h]
    const done = h < hourNow
    const value = today[h]
    let note
    let tone = 'text-slate-300'
    if (h > hourNow) note = 'This hour has not happened yet today.'
    else if (!done) note = `This hour is still in progress: ${value} so far.`
    else if (low == null) note = 'Not enough history yet to say what is normal.'
    else if (value < low) {
      note = `Quieter than a normal ${weekday} at this hour.`
      tone = 'text-warn'
    } else if (value > high) {
      note = `Busier than a normal ${weekday} at this hour.`
      tone = 'text-good'
    } else note = `Normal for a ${weekday} at this hour.`
    return (
      <>
        <TipTitle>{label}</TipTitle>
        {h <= hourNow && <TipRow label="Today" value={`${value} transactions`} color="var(--color-accent)" />}
        <TipRow label="Yesterday" value={`${yesterday[h]} transactions`} color="var(--color-muted)" />
        {low != null && (
          <TipRow
            label={`Normal ${weekday}`}
            value={`${Math.round(low)}–${Math.round(high)} (typically ${Math.round(usual)})`}
            color="var(--color-brand-soft)"
          />
        )}
        <TipNote tone={tone}>{note}</TipNote>
      </>
    )
  }

  const markers = (h) => [
    ...(h < hourNow ? [{ y: y(today[h], max) / H, color: 'var(--color-accent)' }] : []),
    { y: y(Math.min(yesterday[h], max * 0.98), max) / H, color: 'var(--color-muted)' },
  ]

  return (
    <ChartHover count={24} render={tip} markers={markers} onPick={onPick} className="size-full">
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
    </ChartHover>
  )
}
