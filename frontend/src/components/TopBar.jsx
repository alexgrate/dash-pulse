import { Activity, Siren, WifiOff } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useClock } from '../hooks/useClock'
import { InsightIcon, TONES } from '../lib/insights'

const TZ = 'Africa/Lagos'

export default function TopBar({ offline, alert = false, insight = null }) {
  const now = useClock()
  const time = now.toLocaleTimeString('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const date = now.toLocaleDateString('en-GB', { timeZone: TZ, weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <header className="flex items-center justify-between gap-[2vw] px-[3vw] pt-[3vh]">
      <div className="flex shrink-0 items-center gap-3">
        <div className="grid size-[clamp(36px,2.6vw,56px)] place-items-center rounded-2xl bg-brand text-brand-soft ring-1 ring-brand-soft/25">
          <Activity className="size-1/2" strokeWidth={2.25} />
        </div>
        <div>
          <div className="text-[clamp(16px,1.3vw,28px)] font-semibold tracking-tight">Dash Pulse</div>
          <div className="text-[clamp(11px,0.8vw,16px)] text-muted">Operations · live</div>
        </div>
      </div>

      <div className="flex min-w-0 flex-1 justify-center">
        <AnimatePresence mode="wait">{insight && <InsightPill key={insight.id} insight={insight} />}</AnimatePresence>
      </div>

      <div className="flex shrink-0 items-center gap-[2vw]">
        {alert && (
          <span className="flex animate-pulse items-center gap-2 rounded-full bg-bad/15 px-3 py-1 text-[clamp(12px,0.9vw,18px)] font-semibold tracking-[0.15em] text-bad uppercase">
            <Siren className="size-[1.1em]" /> Alert
          </span>
        )}
        {offline ? (
          <span className="flex items-center gap-2 text-[clamp(12px,0.9vw,18px)] text-warn">
            <WifiOff className="size-[1.1em]" /> Reconnecting…
          </span>
        ) : (
          <span className="flex items-center gap-2 text-[clamp(12px,0.9vw,18px)] text-muted">
            <span className="relative flex size-2.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-good opacity-75" />
              <span className="relative inline-flex size-2.5 rounded-full bg-good" />
            </span>
            Live
          </span>
        )}
        <div className="text-right">
          <div className="tabular font-mono text-[clamp(18px,1.6vw,34px)]">{time}</div>
          <div className="text-[clamp(11px,0.8vw,16px)] text-muted">{date}</div>
        </div>
      </div>
    </header>
  )
}

function InsightPill({ insight }) {
  const tone = TONES[insight.severity] ?? TONES.info
  return (
    <motion.div
      className={`flex max-w-full items-center gap-3 rounded-full border ${tone.border} bg-brand/30 py-2 pr-5 pl-2 backdrop-blur-xl`}
      initial={{ opacity: 0, y: -12, filter: 'blur(6px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      exit={{ opacity: 0, y: 12, filter: 'blur(6px)' }}
      transition={{ duration: 0.6, delay: 0.5 }}
    >
      <span
        className={`grid size-[clamp(24px,1.8vw,38px)] shrink-0 place-items-center rounded-full ${tone.bg} ${tone.text}`}
      >
        <InsightIcon insight={insight} className="size-1/2" />
      </span>
      <span className="truncate text-[clamp(12px,1vw,21px)]">{insight.title}</span>
    </motion.div>
  )
}
