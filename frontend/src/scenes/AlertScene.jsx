import { Siren } from 'lucide-react'
import { motion } from 'motion/react'
import AnimatedNumber from '../components/AnimatedNumber'
import { Eyebrow } from '../components/ui'
import { num, pct } from '../lib/format'

export default function AlertScene({ data }) {
  const alert = data.health.alert
  if (!alert) return null

  const cause = [...data.health.reasons].sort((a, b) => b.recent - a.recent)[0]

  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <div className="relative grid size-[clamp(80px,7vw,150px)] place-items-center">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="absolute inset-0 rounded-full border-2 border-bad"
            initial={{ scale: 0.6, opacity: 0.8 }}
            animate={{ scale: 2.4, opacity: 0 }}
            transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.8, ease: 'easeOut' }}
          />
        ))}
        <div className="grid size-full place-items-center rounded-full bg-bad/15 text-bad">
          <Siren className="size-1/2" strokeWidth={2} />
        </div>
      </div>

      <Eyebrow className="mt-[5vh]" tone="text-bad">
        Alert · last {alert.window_minutes} minutes
      </Eyebrow>
      <motion.h1
        className="mt-3 text-[clamp(32px,4vw,84px)] font-semibold tracking-tight"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.8 }}
      >
        {alert.title}
      </motion.h1>

      <div className="mt-[5vh] flex items-end gap-[5vw]">
        <Figure label="failing right now">
          <AnimatedNumber
            value={alert.failure_rate}
            format={(v) => pct(v)}
            className="text-[clamp(64px,9vw,200px)] leading-none font-semibold tracking-[-0.04em] text-bad"
          />
        </Figure>
        <Figure label="normal rate">
          <span className="text-[clamp(32px,3.6vw,80px)] leading-none font-semibold text-muted">
            {pct(alert.normal_rate)}
          </span>
        </Figure>
        <Figure label="failed transactions">
          <AnimatedNumber value={alert.failed} className="text-[clamp(32px,3.6vw,80px)] leading-none font-semibold" />
        </Figure>
      </div>

      {cause && cause.recent > 0 && (
        <div className="mt-[6vh] rounded-full border border-bad/30 bg-bad/10 px-6 py-3 text-[clamp(14px,1.2vw,26px)]">
          Main cause: <span className="font-semibold">{cause.reason}</span>
          <span className="text-muted">
            {' '}
            · {num(cause.recent)} in the last {alert.window_minutes} min
          </span>
        </div>
      )}
    </div>
  )
}

function Figure({ label, children }) {
  return (
    <div className="flex flex-col items-center gap-3">
      {children}
      <span className="text-[clamp(11px,0.9vw,18px)] tracking-[0.2em] text-muted uppercase">{label}</span>
    </div>
  )
}
