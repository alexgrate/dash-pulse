import { Clock, Percent, UserPlus } from 'lucide-react'
import { motion } from 'motion/react'
import AnimatedNumber from '../components/AnimatedNumber'
import Delta from '../components/Delta'
import { Eyebrow, Panel } from '../components/ui'
import { num, pct } from '../lib/format'
import { versus } from '../lib/insights'

const EASE = [0.16, 1, 0.3, 1]

const duration = (minutes) => {
  if (minutes == null) return '—'
  if (minutes < 90) return `${minutes} min`
  if (minutes < 60 * 48) return `${(minutes / 60).toFixed(1)} h`
  return `${(minutes / 1440).toFixed(1)} days`
}

const short = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : num(n))

export default function FunnelScene({ data }) {
  const f = data.funnel
  const first = f.stages[0]?.count || 1
  const worstLoss = Math.max(...f.stages.map((s) => s.lost))
  const stuckTop = Math.max(1, ...f.stuck.map((s) => s.count))

  return (
    <div className="grid h-full grid-cols-12 grid-rows-[auto_1fr] gap-[2vw]">
      <Kpi className="col-span-4" icon={UserPlus} label="Sign-ups today" delay={0}>
        <AnimatedNumber value={f.signups.today} />
        <Delta
          today={f.signups.today}
          yesterday={versus(data, 'signups_so_far', f.signups.yesterday).yesterday}
          label={versus(data, 'signups_so_far', f.signups.yesterday).compareLabel}
        />
      </Kpi>
      <Kpi className="col-span-4" icon={Percent} label={`Sign-up to account · ${f.days} days`} delay={0.1}>
        <AnimatedNumber value={f.conversion} format={(v) => (f.stages[0]?.count ? pct(v) : '—')} />
        <span className="text-[clamp(12px,0.95vw,20px)] text-muted">
          {num(f.stages.at(-1)?.count)} of {num(f.stages[0]?.count)} sign-ups
        </span>
      </Kpi>
      <Kpi className="col-span-4" icon={Clock} label="Typical time to open an account" delay={0.2}>
        <span>{duration(f.median_minutes_to_account)}</span>
        <span className="text-[clamp(12px,0.95vw,20px)] text-muted">median, from sign-up</span>
      </Kpi>

      <Panel className="col-span-8 flex flex-col" delay={0.25}>
        <Eyebrow>Onboarding funnel · last {f.days} days</Eyebrow>
        <div className="mt-[3vh] grid min-h-0 flex-1 grid-cols-6 gap-[1vw]">
          {f.stages.map((s, i) => (
            <div key={s.key} className="flex min-h-0 flex-col">
              <div className="tabular text-[clamp(16px,1.6vw,34px)] font-semibold">{short(s.count)}</div>
              <div className="text-[clamp(11px,0.85vw,17px)] text-muted">{pct(s.share, 0)}</div>
              <div className="relative mt-3 min-h-0 flex-1 overflow-hidden rounded-2xl bg-white/[0.03]">
                <motion.div
                  className="absolute inset-x-0 bottom-0 rounded-2xl"
                  style={{
                    background: 'linear-gradient(to top, var(--color-accent), var(--color-glow))',
                    boxShadow: '0 0 30px rgba(96,165,250,0.35)',
                  }}
                  initial={{ height: 0 }}
                  animate={{ height: `${Math.max((s.count / first) * 100, 2)}%` }}
                  transition={{ duration: 1.4, delay: 0.4 + i * 0.12, ease: EASE }}
                />
              </div>
              <div className="mt-3 min-h-[2.6em] text-[clamp(11px,0.9vw,18px)] leading-tight">{s.label}</div>
              <div
                className={`mt-1 h-[1.4em] text-[clamp(11px,0.85vw,17px)] ${
                  s.lost === worstLoss && s.lost > 0 ? 'font-semibold text-bad' : 'text-muted'
                }`}
              >
                {s.lost > 0 && `−${short(s.lost)} drop`}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel className="col-span-4 flex flex-col" delay={0.35}>
        <Eyebrow>Where people get stuck</Eyebrow>
        <div className="mt-[3vh] flex flex-1 flex-col justify-around">
          {f.stuck.map((s, i) => (
            <div key={s.phase}>
              <div className="mb-2 flex items-end justify-between gap-4">
                <span className="min-w-0">
                  <span className="block truncate text-[clamp(12px,1vw,21px)]">{s.label}</span>
                  <span className="block truncate font-mono text-[clamp(9px,0.65vw,13px)] text-muted">{s.phase}</span>
                </span>
                <span className="tabular text-[clamp(15px,1.4vw,30px)] font-semibold">{num(s.count)}</span>
              </div>
              <div className="h-[clamp(5px,0.6vh,9px)] overflow-hidden rounded-full bg-white/[0.05]">
                <motion.div
                  className={`h-full rounded-full ${i === 0 ? 'bg-bad' : 'bg-warn'}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${(s.count / stuckTop) * 100}%` }}
                  transition={{ duration: 1.3, delay: 0.5 + i * 0.1, ease: EASE }}
                />
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

function Kpi({ icon: Icon, label, delay, className, children }) {
  const [value, sub] = children
  return (
    <Panel className={className} delay={delay}>
      <div className="flex items-center gap-3">
        <Icon className="size-[clamp(16px,1.3vw,28px)] text-accent" />
        <Eyebrow>{label}</Eyebrow>
      </div>
      <div className="mt-2 text-[clamp(32px,3.4vw,72px)] leading-none font-semibold tracking-[-0.03em]">{value}</div>
      <div className="mt-3">{sub}</div>
    </Panel>
  )
}
