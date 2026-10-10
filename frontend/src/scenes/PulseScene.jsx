import AnimatedNumber from '../components/AnimatedNumber'
import Delta from '../components/Delta'
import HourlyChart from '../components/HourlyChart'
import { Target } from 'lucide-react'
import Drill from '../components/Drill'
import { Eyebrow, Panel } from '../components/ui'
import { list, useExplore } from '../lib/explore'
import { naira, num, pct } from '../lib/format'

export default function PulseScene({ data }) {
  const { today, yesterday } = data.transactions
  const users = data.active_users
  const { enabled, open } = useExplore()
  const forecast = data.intelligence?.forecast
  const typical = data.intelligence?.typical

  return (
    <div className="grid h-full grid-cols-12 grid-rows-[minmax(0,1fr)] gap-[2.5vw]">
      <div className="col-span-5 flex min-h-0 flex-col justify-center-safe gap-[2.5vh] overflow-hidden [@media(max-height:820px)]:gap-[1.6vh]">
        <Drill to={list()} className="-m-3 p-3">
          <Eyebrow>Transactions today</Eyebrow>
          <AnimatedNumber
            value={today.count}
            className="mt-2 block text-[clamp(44px,min(10vw,15vh),220px)] leading-[0.9] font-semibold tracking-[-0.04em] [@media(max-height:820px)]:text-[12vh]"
          />
          <div className="mt-[1.5vh]">
            {typical?.so_far_median ? (
              <Delta today={today.count} yesterday={typical.so_far_median} label={`vs a typical ${typical.weekday}`} />
            ) : (
              <Delta today={today.count} yesterday={yesterday.count} />
            )}
          </div>
          {forecast && (
            <div className="mt-[1.2vh] flex items-center gap-2 text-[clamp(12px,1vw,21px)] text-muted">
              <Target className="size-[1.1em] text-brand-soft" />
              On track for <span className="tabular font-semibold text-slate-100">~{num(forecast.projected)}</span>
              {typical && (
                <span>
                  · typical {typical.weekday} ~{num(forecast.typical_total)}
                </span>
              )}
            </div>
          )}
        </Drill>

        <div className="grid grid-cols-2 gap-[min(1vw,1.6vh)]">
          <Stat
            label="Money sent by customers"
            note="Money out plus within Dash. Money in is on the Live tab."
            delay={0.15}
            to={list({ status: 'SUCCESS' })}
          >
            <AnimatedNumber value={today.value} format={naira} />
            <Delta today={today.value} yesterday={yesterday.value} label="vs yesterday" />
          </Stat>
          <Stat label="Success rate" delay={0.25} to={list({ status: 'SUCCESS' })}>
            <AnimatedNumber
              value={today.success_rate ?? 0}
              format={(v) => (today.success_rate == null ? '—' : pct(v))}
              className={
                today.success_rate == null ? 'text-muted' : today.success_rate < 0.8 ? 'text-bad' : 'text-good'
              }
            />
            <span className="text-[clamp(12px,0.95vw,20px)] text-muted">yesterday {pct(yesterday.success_rate)}</span>
          </Stat>
          <Stat label="Failed" delay={0.35} to={list({ status: 'FAILED' })}>
            <AnimatedNumber value={today.failed} />
            <Delta today={today.failed} yesterday={yesterday.failed} invert label="vs yesterday" />
          </Stat>
          <Stat label="Active users" delay={0.45}>
            <AnimatedNumber value={users.today} />
            <Delta today={users.today} yesterday={users.yesterday} label="vs yesterday" />
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
            onPick={enabled ? (h) => h <= data.hour_now && open(list({ hour: h })) : undefined}
          />
        </div>
        <div className="text-[clamp(11px,0.85vw,17px)] text-muted">
          This hour so far: <span className="tabular text-slate-200">{num(data.hourly.today[data.hour_now])}</span>
        </div>
      </Panel>
    </div>
  )
}

function Stat({ label, note, delay, to, children }) {
  const [value, sub] = children
  return (
    <Panel delay={delay} className="!py-[min(1.6vw,2.6vh)]">
      <Drill to={to} className="-m-2 p-2">
        <Eyebrow>{label}</Eyebrow>
        {note && (
          <div className="mt-0.5 text-[clamp(10px,0.72vw,14px)] leading-snug text-muted/75 [@media(max-height:820px)]:hidden">
            {note}
          </div>
        )}
        <div className="mt-1 text-[clamp(20px,min(2.6vw,4.2vh),56px)] font-semibold tracking-tight">{value}</div>
        <div className="mt-1">{sub}</div>
      </Drill>
    </Panel>
  )
}
