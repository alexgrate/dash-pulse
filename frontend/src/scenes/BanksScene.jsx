import { Landmark, ShieldCheck, Smartphone } from 'lucide-react'
import { motion } from 'motion/react'
import AnimatedNumber from '../components/AnimatedNumber'
import Drill from '../components/Drill'
import { Eyebrow, Panel } from '../components/ui'
import { list } from '../lib/explore'
import { naira, num, pct } from '../lib/format'
import { InsightIcon, topFor, TONES } from '../lib/insights'

const EASE = [0.16, 1, 0.3, 1]

const isFailingNow = (bank) => Boolean(bank.failing_now)

const MIN_FOR_COLOUR = 30

const rateTone = (rate, overall, settled) => {
  if (rate == null) return 'text-muted'
  if (settled < MIN_FOR_COLOUR) return 'text-slate-300'
  if (rate - overall >= 0.15) return 'text-bad'
  if (rate - overall >= 0.07) return 'text-warn'
  return 'text-slate-300'
}

export default function BanksScene({ data }) {
  const { items, total, bank_count: bankCount, recent_minutes: minutes } = data.banks
  const top = Math.max(1, ...items.map((b) => b.count))
  const overall = total.failure_rate ?? 0

  return (
    <div className="grid h-full grid-cols-12 grid-rows-[minmax(0,1fr)] gap-[2.5vw]">
      <Panel className="col-span-7 flex min-h-0 flex-col">
        <div className="flex items-start justify-between gap-4">
          <div>
            <Eyebrow>Where transfers go today</Eyebrow>
            <div className="mt-1 text-[clamp(16px,1.4vw,30px)] font-medium">Destination banks</div>
          </div>
          <div className="text-right text-[clamp(11px,0.9vw,18px)] text-muted">
            <span className="tabular text-slate-100">{num(total.count)}</span> transfers ·{' '}
            <span className="text-slate-100">{naira(total.value)}</span> to other banks · {num(bankCount)} banks
          </div>
        </div>

        <div className="mt-[2.5vh] grid grid-cols-[1fr_auto_auto] items-end gap-x-[1.6vw] pb-2 text-[clamp(10px,0.75vw,15px)] tracking-[0.2em] text-muted uppercase">
          <span>Bank</span>
          <span className="text-right">Value</span>
          <span className="w-[7ch] text-right">Failing</span>
        </div>

        <div className="flex min-h-0 flex-1 flex-col justify-around">
          {items.length === 0 && <div className="text-muted">No transfers to other banks yet today</div>}
          {items.map((bank, i) => (
            <Drill key={bank.key} to={list({ kinds: ['INTER'], bank: bank.bank })} className="-mx-2 px-2 py-1">
              <div className="grid grid-cols-[1fr_auto_auto] items-baseline gap-x-[1.6vw]">
                <span className="flex min-w-0 items-baseline gap-3">
                  <span className="truncate text-[clamp(13px,1.1vw,23px)]">{bank.bank}</span>
                  <span className="tabular text-[clamp(12px,0.95vw,20px)] text-muted">{num(bank.count)}</span>
                  {isFailingNow(bank) && (
                    <span className="flex items-center gap-1.5 rounded-full bg-bad/15 px-2 py-0.5 text-[clamp(10px,0.8vw,16px)] text-bad">
                      <span className="size-1.5 animate-ping rounded-full bg-bad" />
                      {pct(bank.recent.system_rate)} bank errors · {minutes} min
                    </span>
                  )}
                </span>
                <span className="tabular text-right text-[clamp(12px,0.95vw,20px)] text-muted">
                  {naira(bank.value)}
                </span>
                <span
                  className={`tabular w-[7ch] text-right text-[clamp(13px,1.05vw,22px)] font-medium ${rateTone(bank.failure_rate, overall, bank.settled)}`}
                >
                  {pct(bank.failure_rate)}
                </span>
              </div>
              <div className="mt-1.5 h-[clamp(5px,0.6vh,9px)] overflow-hidden rounded-full bg-white/[0.05]">
                <motion.div
                  className={`h-full rounded-full ${isFailingNow(bank) ? 'bg-bad' : 'bg-accent'}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${(bank.count / top) * 100}%` }}
                  transition={{ duration: 1.3, delay: 0.3 + i * 0.08, ease: EASE }}
                />
              </div>
            </Drill>
          ))}
        </div>
      </Panel>

      <div className="col-span-5 flex min-h-0 flex-col gap-[2.5vw]">
        <Devices devices={data.devices} />
        <BankHealth data={data} overall={overall} />
      </div>
    </div>
  )
}

function Devices({ devices }) {
  const total = devices.android + devices.ios + devices.other || 1
  const android = devices.android / total
  const ios = devices.ios / total
  return (
    <Panel className="flex flex-1 flex-col justify-center-safe" delay={0.15}>
      <div className="flex items-center gap-3">
        <Smartphone className="size-[clamp(16px,1.3vw,28px)] text-accent" />
        <Eyebrow>Devices used today</Eyebrow>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-[1.5vw]">
        <Share label="Android" users={devices.android} share={android} color="var(--color-good)" />
        <Share label="iOS" users={devices.ios} share={ios} color="var(--color-brand-soft)" />
      </div>
      <div className="mt-5 flex h-[clamp(8px,1vh,14px)] overflow-hidden rounded-full bg-white/[0.05]">
        <motion.div
          className="h-full"
          style={{ background: 'var(--color-good)' }}
          initial={{ width: 0 }}
          animate={{ width: `${android * 100}%` }}
          transition={{ duration: 1.3, delay: 0.4, ease: EASE }}
        />
        <motion.div
          className="h-full"
          style={{ background: 'var(--color-brand-soft)' }}
          initial={{ width: 0 }}
          animate={{ width: `${ios * 100}%` }}
          transition={{ duration: 1.3, delay: 0.55, ease: EASE }}
        />
      </div>
    </Panel>
  )
}

function Share({ label, users, share, color }) {
  return (
    <div>
      <div className="flex items-center gap-2 text-[clamp(12px,1vw,21px)] text-muted">
        <span className="size-2.5 rounded-full" style={{ background: color }} />
        {label}
      </div>
      <AnimatedNumber
        value={share}
        format={(v) => pct(v)}
        className="mt-1 block text-[clamp(36px,min(4vw,7vh),90px)] leading-none font-semibold tracking-[-0.03em]"
      />
      <div className="tabular mt-2 text-[clamp(11px,0.9vw,18px)] text-muted">{num(users)} people</div>
    </div>
  )
}

function BankHealth({ data, overall }) {
  const insight = topFor(data, 'banks')
  const problem = insight && (insight.severity === 'bad' || insight.severity === 'warn')
  const tone = TONES[problem ? insight.severity : 'good']
  return (
    <Panel className={`flex flex-1 flex-col justify-center-safe border ${tone.border}`} delay={0.25}>
      <div className="flex items-center gap-3">
        {problem ? (
          <InsightIcon insight={insight} className={`size-[clamp(16px,1.3vw,28px)] ${tone.text}`} />
        ) : (
          <ShieldCheck className="size-[clamp(16px,1.3vw,28px)] text-good" />
        )}
        <Eyebrow>Destination bank health</Eyebrow>
      </div>
      <div className="mt-3 text-[clamp(18px,1.7vw,36px)] leading-snug font-semibold">
        {problem ? insight.title : 'No bank is failing out of line'}
      </div>
      <div className="mt-2 text-[clamp(12px,0.95vw,20px)] text-muted">
        {problem ? (
          insight.detail
        ) : (
          <span className="flex items-center gap-2">
            <Landmark className="size-[1.1em]" />
            Transfers to other banks are failing at {pct(overall)} overall today, mostly customer-side. No bank is
            showing unusual bank-side errors.
          </span>
        )}
      </div>
    </Panel>
  )
}
