import AnimatedNumber from '../components/AnimatedNumber'
import Delta from '../components/Delta'
import HourlyChart from '../components/HourlyChart'
import { Target } from 'lucide-react'
import { Eyebrow, Panel } from '../components/ui'
import { naira, num, pct } from '../lib/format'

export default function PulseScene({ data }) {
  const { today, yesterday } = data.transactions
  const users = data.active_users
  const forecast = data.intelligence?.forecast
  const typical = data.intelligence?.typical

  return (
    <div className="grid h-full grid-cols-12 gap-[2.5vw]">
      <div className="col-span-5 flex flex-col justify-center gap-[5vh]">
        <div>
          <Eyebrow>Transactions today</Eyebrow>
          <AnimatedNumber
            value={today.count}
            className="mt-2 block text-[clamp(64px,10vw,220px)] leading-[0.9] font-semibold tracking-[-0.04em]"
          />
          <div className="mt-5">
            <Delta today={today.count} yesterday={yesterday.count} />
          </div>
          {forecast && (
            <div className="mt-4 flex items-center gap-2 text-[clamp(12px,1vw,21px)] text-muted">
              <Target className="size-[1.1em] text-brand-soft" />
              On track for <span className="tabular font-semibold text-slate-100">~{num(forecast.projected)}</span>
              {typical && (
                <span>
                  · typical {typical.weekday} ~{num(forecast.typical_total)}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-[1.2vw]">
          <Stat label="Value moved" delay={0.15}>
            <AnimatedNumber value={today.value} format={naira} />
            <Delta today={today.value} yesterday={yesterday.value} label="" />
          </Stat>
          <Stat label="Success rate" delay={0.25}>
            <AnimatedNumber
              value={today.success_rate ?? 0}
              format={(v) => (today.success_rate == null ? '—' : pct(v))}
              className={
                today.success_rate == null ? 'text-muted' : today.success_rate < 0.8 ? 'text-bad' : 'text-good'
              }
            />
            <span className="text-[clamp(12px,0.95vw,20px)] text-muted">yesterday {pct(yesterday.success_rate)}</span>
          </Stat>
          <Stat label="Failed" delay={0.35}>
            <AnimatedNumber value={today.failed} />
            <Delta today={today.failed} yesterday={yesterday.failed} invert label="" />
          </Stat>
          <Stat label="Active users" delay={0.45}>
            <AnimatedNumber value={users.today} />
            <Delta today={users.today} yesterday={users.yesterday} label="" />
          </Stat>
        </div>
      </div>

      <Panel className="col-span-7 flex flex-col" delay={0.2}>
        <div className="flex items-start justify-between">
          <div>
            <Eyebrow>Hourly activity</Eyebrow>
            <div className="mt-1 text-[clamp(16px,1.4vw,30px)] font-medium">
              {typical ? `Today vs a typical ${typical.weekday}` : 'Today vs yesterday'}
            </div>
          </div>
          <div className="flex gap-5 text-[clamp(11px,0.85vw,17px)] text-muted">
            <span className="flex items-center gap-2">
              <span className="h-[3px] w-6 rounded-full bg-accent" /> Today
            </span>
            <span className="flex items-center gap-2">
              <span className="w-6 border-t-2 border-dashed border-muted/60" /> Yesterday
            </span>
            {typical && (
              <span className="flex items-center gap-2">
                <span className="h-3 w-6 rounded-sm border border-brand-soft/40 bg-brand-soft/15" /> Usual range
              </span>
            )}
          </div>
        </div>
        <div className="mt-[4vh] min-h-0 flex-1 pb-8">
          <HourlyChart
            today={data.hourly.today}
            yesterday={data.hourly.yesterday}
            hourNow={data.hour_now}
            typical={typical}
          />
        </div>
        <div className="text-[clamp(11px,0.85vw,17px)] text-muted">
          This hour so far: <span className="tabular text-slate-200">{num(data.hourly.today[data.hour_now])}</span>
        </div>
      </Panel>
    </div>
  )
}

function Stat({ label, delay, children }) {
  const [value, sub] = children
  return (
    <Panel delay={delay}>
      <Eyebrow>{label}</Eyebrow>
      <div className="mt-2 text-[clamp(24px,2.6vw,56px)] font-semibold tracking-tight">{value}</div>
      <div className="mt-1">{sub}</div>
    </Panel>
  )
}
