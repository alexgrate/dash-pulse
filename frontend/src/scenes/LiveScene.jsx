import { CheckCircle2, Clock3, HeartPulse, RotateCcw, XCircle } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import AnimatedNumber from '../components/AnimatedNumber'
import { Eyebrow, Panel } from '../components/ui'
import { useClock } from '../hooks/useClock'
import { lagosMs, useLive } from '../hooks/useLive'
import { naira, num, pct } from '../lib/format'

const EASE = [0.16, 1, 0.3, 1]

const OUTCOMES = {
  SUCCESS: { icon: CheckCircle2, tone: 'text-good', bar: 'var(--color-good)', label: 'Successful' },
  FAILED: { icon: XCircle, tone: 'text-bad', bar: 'var(--color-bad)', label: 'Failed' },
  REVERSED: { icon: RotateCcw, tone: 'text-warn', bar: 'var(--color-warn)', label: 'Reversed' },
  PENDING: { icon: Clock3, tone: 'text-muted', bar: 'var(--color-muted)', label: 'Pending' },
}

const HEART = {
  good: { tone: 'text-good', stroke: 'var(--color-good)', border: 'border-good/25' },
  warn: { tone: 'text-warn', stroke: 'var(--color-warn)', border: 'border-warn/40' },
  bad: { tone: 'text-bad', stroke: 'var(--color-bad)', border: 'border-bad/50' },
  idle: { tone: 'text-muted', stroke: 'var(--color-muted)', border: 'border-white/[0.06]' },
}

function ago(seconds) {
  if (seconds == null) return '—'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

function span(seconds) {
  if (seconds < 90) return `${Math.round(seconds)} seconds`
  return `${Math.round(seconds / 60)} minutes`
}

function heartbeat(silence, typicalPerHour) {
  if (silence == null) return { state: 'idle', note: 'Waiting for the first transaction…' }
  const gap = typicalPerHour ? 3600 / Math.max(typicalPerHour, 0.5) : null
  const warnAfter = Math.max(gap ? gap * 3 : 600, 300)
  const badAfter = Math.max(gap ? gap * 6 : 1200, 900)
  const usual = gap ? `usually one every ~${span(gap)} at this hour` : 'no typical pattern yet'
  if (silence >= badAfter)
    return { state: 'bad', note: `No transactions for ${span(silence)}, ${usual}. Check the app and channels.` }
  if (silence >= warnAfter) return { state: 'warn', note: `Quieter than usual, ${usual}.` }
  return { state: 'good', note: gap ? `Normal for this time of day, ${usual}.` : 'Transactions are flowing.' }
}

export default function LiveScene({ data }) {
  const { live, offset, failing } = useLive()
  const now = useClock().getTime() + offset
  const typicalPerHour = data.intelligence?.typical?.hourly_median?.[data.hour_now]
  const silence = live?.last_at ? (now - lagosMs(live.last_at)) / 1000 : null
  const beat = heartbeat(silence, typicalPerHour)
  const style = HEART[beat.state]

  return (
    <div className="grid h-full grid-cols-12 grid-rows-[minmax(0,1fr)] gap-[2.5vw]">
      <Panel className="relative col-span-7 flex min-h-0 flex-col overflow-hidden">
        <div className="flex items-start justify-between">
          <div>
            <Eyebrow>Transactions as they happen</Eyebrow>
            <div className="mt-1 text-[clamp(16px,1.4vw,30px)] font-medium">Live feed</div>
          </div>
          <span className="flex items-center gap-2 text-[clamp(11px,0.85vw,17px)] text-muted">
            <span className="relative flex size-2.5">
              <span
                className={`absolute inline-flex size-full rounded-full opacity-75 ${failing ? 'bg-warn' : 'animate-ping bg-good'}`}
              />
              <span className={`relative inline-flex size-2.5 rounded-full ${failing ? 'bg-warn' : 'bg-good'}`} />
            </span>
            {failing ? 'Reconnecting…' : 'Updates every 5 seconds'}
          </span>
        </div>

        <div className="relative mt-[2.5vh] min-h-0 flex-1 overflow-hidden">
          {!live && <div className="text-muted">Listening…</div>}
          <ul className="flex flex-col gap-[1vh]">
            <AnimatePresence initial={false}>
              {live?.feed.map((t) => (
                <FeedRow key={t.id} item={t} seconds={(now - lagosMs(t.at)) / 1000} />
              ))}
            </AnimatePresence>
          </ul>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-ink/90 to-transparent" />
        </div>
      </Panel>

      <div className="col-span-5 flex min-h-0 flex-col gap-[2.5vw]">
        <Panel className={`flex flex-1 flex-col justify-center border ${style.border}`} delay={0.15}>
          <div className="flex items-center gap-3">
            <HeartPulse className={`size-[clamp(16px,1.3vw,28px)] ${style.tone}`} />
            <Eyebrow>Last transaction</Eyebrow>
          </div>
          <div
            className={`tabular mt-3 text-[clamp(40px,min(4.6vw,8vh),100px)] leading-none font-semibold tracking-[-0.03em] ${style.tone}`}
          >
            {ago(silence)}
          </div>
          <Ecg stroke={style.stroke} flat={beat.state === 'bad'} />
          <div className="text-[clamp(12px,0.95vw,20px)] text-muted">{beat.note}</div>
        </Panel>

        <WindowPanel live={live} />
      </div>
    </div>
  )
}

function FeedRow({ item, seconds }) {
  const o = OUTCOMES[item.outcome] ?? OUTCOMES.PENDING
  const Icon = o.icon
  const fresh = seconds < 20
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: -28, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.7, ease: EASE }}
      className={`flex items-center gap-[1vw] rounded-2xl border px-[1.2vw] py-[1.1vh] transition-colors duration-[2000ms] ${
        fresh ? 'border-brand-soft/40 bg-brand/30' : 'border-white/[0.05] bg-white/[0.02]'
      }`}
    >
      <Icon className={`size-[clamp(18px,1.4vw,30px)] shrink-0 ${o.tone}`} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[clamp(13px,1.1vw,23px)]">
          {item.kind}
          {item.bank && <span className="text-muted"> → {item.bank}</span>}
        </div>
        {item.reason && <div className="truncate text-[clamp(11px,0.85vw,17px)] text-bad/80">{item.reason}</div>}
      </div>
      <div className="tabular shrink-0 text-right text-[clamp(14px,1.2vw,25px)] font-semibold">
        {naira(item.amount)}
      </div>
      <div className="tabular w-[8ch] shrink-0 text-right text-[clamp(11px,0.85vw,17px)] text-muted">
        {ago(seconds)}
      </div>
    </motion.li>
  )
}

function Ecg({ stroke, flat }) {
  const path = flat
    ? 'M0,30 L400,30'
    : 'M0,30 L60,30 L75,30 L85,8 L95,52 L105,30 L200,30 L215,30 L225,12 L235,48 L245,30 L400,30'
  return (
    <div className="my-[2vh] h-[clamp(36px,5vh,70px)] overflow-hidden">
      <svg viewBox="0 0 400 60" preserveAspectRatio="none" className="size-full">
        <motion.path
          d={path}
          fill="none"
          stroke={stroke}
          strokeWidth="2.5"
          strokeLinejoin="round"
          style={{ filter: `drop-shadow(0 0 6px ${stroke})` }}
          initial={{ pathLength: 0, opacity: 0.2 }}
          animate={{ pathLength: [0, 1, 1], opacity: [1, 1, 0.15] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
        />
      </svg>
    </div>
  )
}

function WindowPanel({ live }) {
  const w = live?.window
  const total = w?.count || 0
  const parts = ['SUCCESS', 'FAILED', 'REVERSED', 'PENDING'].map((k) => ({
    key: k,
    ...OUTCOMES[k],
    n: w ? w[k.toLowerCase()] : 0,
  }))
  return (
    <Panel className="flex flex-1 flex-col justify-center" delay={0.25}>
      <Eyebrow>Last {live?.window_minutes ?? 15} minutes</Eyebrow>
      <div className="mt-2 flex items-baseline gap-3">
        <AnimatedNumber
          value={total}
          className="text-[clamp(36px,min(4vw,7vh),90px)] leading-none font-semibold tracking-[-0.03em]"
        />
        <span className="text-[clamp(12px,0.95vw,20px)] text-muted">transactions</span>
      </div>
      <div className="mt-[2vh] flex h-[clamp(8px,1vh,14px)] overflow-hidden rounded-full bg-white/[0.05]">
        {parts.map((p) =>
          p.n ? (
            <motion.div
              key={p.key}
              className="h-full"
              style={{ background: p.bar }}
              initial={{ width: 0 }}
              animate={{ width: `${(p.n / total) * 100}%` }}
              transition={{ duration: 1, ease: EASE }}
            />
          ) : null,
        )}
      </div>
      <div className="mt-[2vh] grid grid-cols-2 gap-x-[1.5vw] gap-y-[1vh] text-[clamp(12px,0.95vw,20px)]">
        {parts.map((p) => (
          <div key={p.key} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-muted">
              <span className="size-2.5 rounded-full" style={{ background: p.bar }} />
              {p.label}
            </span>
            <span className="tabular">
              {num(p.n)}
              <span className="ml-2 text-muted">{total ? pct(p.n / total, 0) : ''}</span>
            </span>
          </div>
        ))}
      </div>
    </Panel>
  )
}
