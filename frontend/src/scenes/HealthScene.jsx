import { AlertTriangle, ScanFace, ShieldCheck } from 'lucide-react'
import { motion } from 'motion/react'
import AnimatedNumber from '../components/AnimatedNumber'
import { Eyebrow, Panel } from '../components/ui'
import { num, pct } from '../lib/format'

const PRODUCT_LABELS = {
  INTER: 'Transfers to other banks',
  INTRA: 'Transfers within Dash',
  'Data Bundle': 'Data',
  'Betting & Lottery': 'Betting',
  'Transport and Toll Payment': 'Transport & tolls',
}

const EASE = [0.16, 1, 0.3, 1]

const REASON_KINDS = {
  system: { color: 'var(--color-bad)', label: 'System' },
  account: { color: 'var(--color-warn)', label: 'Account hold' },
  customer: { color: 'var(--color-accent)', label: 'Customer' },
  unknown: { color: 'var(--color-muted)', label: 'Not recorded' },
  other: { color: 'var(--color-brand-soft)', label: 'Other' },
}

export default function HealthScene({ data }) {
  const { recent, baseline, reasons, products, liveness, alert, window_minutes: minutes } = data.health
  const enough = recent.settled >= (data.health.min_settled ?? 15)
  const rising =
    enough &&
    recent.failure_rate != null &&
    baseline.failure_rate != null &&
    recent.failure_rate > baseline.failure_rate * 1.2
  const top = Math.max(1, ...reasons.map((r) => r.today))

  return (
    <div className="grid h-full grid-cols-12 gap-[2vw]">
      <div className="col-span-4 flex flex-col gap-[2vw]">
        <Panel className="flex flex-1 flex-col justify-center">
          <div className="flex items-center gap-3">
            {alert || rising ? (
              <AlertTriangle className="size-[clamp(16px,1.3vw,28px)] text-bad" />
            ) : (
              <ShieldCheck className="size-[clamp(16px,1.3vw,28px)] text-good" />
            )}
            <Eyebrow>Failure rate · last {minutes} min</Eyebrow>
          </div>
          <AnimatedNumber
            value={recent.failure_rate ?? 0}
            format={(v) => (recent.failure_rate == null ? '—' : pct(v))}
            className={`mt-3 block text-[clamp(48px,6vw,130px)] leading-none font-semibold tracking-[-0.04em] ${
              alert || rising ? 'text-bad' : enough ? 'text-good' : 'text-muted'
            }`}
          />
          <div className="mt-4 text-[clamp(12px,0.95vw,20px)] text-muted">
            {enough ? (
              <>
                Normal is <span className="text-slate-200">{pct(baseline.failure_rate)}</span> · {num(recent.failed)}{' '}
                failed of {num(recent.settled)}
              </>
            ) : (
              <>
                Too few to judge: only {num(recent.settled)} transactions in the last {minutes} min. Normal is{' '}
                <span className="text-slate-200">{pct(baseline.failure_rate)}</span>.
              </>
            )}
          </div>
        </Panel>

        <Panel className="flex flex-1 flex-col justify-center" delay={0.15}>
          <div className="flex items-center gap-3">
            <ScanFace className="size-[clamp(16px,1.3vw,28px)] text-glow" />
            <Eyebrow>Face checks failing today</Eyebrow>
          </div>
          <AnimatedNumber
            value={liveness.failure_rate ?? 0}
            format={(v) => pct(v)}
            className="mt-3 block text-[clamp(40px,4.6vw,100px)] leading-none font-semibold tracking-[-0.04em]"
          />
          <div className="mt-4 text-[clamp(12px,0.95vw,20px)] text-muted">
            {num(liveness.failed)} low-score of {num(liveness.passed + liveness.failed)} liveness checks
          </div>
        </Panel>
      </div>

      <Panel className="col-span-4 flex flex-col" delay={0.1}>
        <Eyebrow>Why transactions fail</Eyebrow>
        <div className="mt-1 text-[clamp(16px,1.4vw,30px)] font-medium">Top reasons today</div>
        <div className="mt-[4vh] flex flex-1 flex-col justify-around">
          {reasons.length === 0 && <div className="text-muted">No failures yet today</div>}
          {reasons.map((r, i) => (
            <div key={r.reason}>
              <div className="mb-2 flex items-end justify-between gap-4">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-[clamp(13px,1.05vw,22px)]">{r.reason}</span>
                  <span
                    className="shrink-0 text-[clamp(9px,0.7vw,14px)] tracking-[0.15em] uppercase"
                    style={{ color: (REASON_KINDS[r.kind] ?? REASON_KINDS.other).color }}
                  >
                    {(REASON_KINDS[r.kind] ?? REASON_KINDS.other).label}
                  </span>
                </span>
                <span className="flex shrink-0 items-baseline gap-3">
                  {r.recent > 0 && (
                    <span className="rounded-full bg-bad/10 px-2 py-0.5 text-[clamp(10px,0.8vw,16px)] text-bad">
                      +{num(r.recent)} now
                    </span>
                  )}
                  <span className="tabular text-[clamp(16px,1.5vw,32px)] font-semibold">{num(r.today)}</span>
                </span>
              </div>
              <div className="h-[clamp(6px,0.7vh,10px)] overflow-hidden rounded-full bg-white/[0.05]">
                <motion.div
                  className="h-full rounded-full"
                  style={{
                    background: (REASON_KINDS[r.kind] ?? REASON_KINDS.other).color,
                    boxShadow: `0 0 14px ${(REASON_KINDS[r.kind] ?? REASON_KINDS.other).color}`,
                  }}
                  initial={{ width: 0 }}
                  animate={{ width: `${(r.today / top) * 100}%` }}
                  transition={{ duration: 1.3, delay: 0.3 + i * 0.1, ease: EASE }}
                />
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel className="col-span-4 flex flex-col" delay={0.2}>
        <Eyebrow>Product health</Eyebrow>
        <div className="mt-1 text-[clamp(16px,1.4vw,30px)] font-medium">Failed and reversed today</div>
        <div className="mt-[4vh] grid grid-cols-[1fr_auto_auto] content-around gap-x-[1.5vw] gap-y-[2.2vh] text-[clamp(12px,1vw,21px)]">
          <span className="text-[clamp(10px,0.75vw,15px)] tracking-[0.2em] text-muted uppercase">Product</span>
          <span className="text-right text-[clamp(10px,0.75vw,15px)] tracking-[0.2em] text-muted uppercase">
            Failed
          </span>
          <span className="text-right text-[clamp(10px,0.75vw,15px)] tracking-[0.2em] text-muted uppercase">
            Reversed
          </span>
          {products.map((p) => (
            <Row key={p.kind} product={p} />
          ))}
        </div>
      </Panel>
    </div>
  )
}

const MIN_FOR_COLOUR = 30

const toneFor = (rate, usual, count) => {
  if (rate == null || count < MIN_FOR_COLOUR) return 'text-slate-200'
  if (usual == null) return rate > 0.15 ? 'text-bad' : rate > 0.08 ? 'text-warn' : 'text-slate-200'
  if (rate - usual >= 0.08) return 'text-bad'
  if (rate - usual >= 0.04) return 'text-warn'
  return 'text-slate-200'
}

function Rate({ rate, usual, count }) {
  return (
    <span className={`tabular text-right font-medium ${toneFor(rate, usual, count)}`}>
      {pct(rate)}
      {usual != null && (
        <span className="block text-[clamp(9px,0.7vw,14px)] font-normal text-muted">usual {pct(usual)}</span>
      )}
    </span>
  )
}

function Row({ product: p }) {
  return (
    <>
      <span className="truncate">
        {PRODUCT_LABELS[p.kind] ?? p.kind}
        <span className="ml-2 text-muted">{num(p.count)}</span>
      </span>
      <Rate rate={p.failure_rate} usual={p.usual_failure_rate} count={p.count} />
      <Rate rate={p.reversal_rate} usual={p.usual_reversal_rate} count={p.count} />
    </>
  )
}
