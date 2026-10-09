import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { motion } from 'motion/react'
import ChartHover, { TipNote, TipRow, TipTitle } from '../components/ChartHover'
import { Eyebrow, Panel } from '../components/ui'
import { list, useExplore } from '../lib/explore'
import { naira, num, pct } from '../lib/format'

const EASE = [0.16, 1, 0.3, 1]
const W = 1000
const H = 360
const PAD = 14

const avg7 = (values) =>
  values.map((_, i) => {
    const slice = values.slice(Math.max(0, i - 6), i + 1)
    return slice.reduce((a, b) => a + b, 0) / slice.length
  })

const path = (values, max, w = W, h = H, pad = PAD) =>
  values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * w
      const y = h - pad - ((v ?? 0) / max) * (h - pad * 2)
      return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

const shortDate = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

const isFlat = (value, points) => (points ? Math.abs(value) < 0.01 : Math.abs(value) < 0.05)

const direction = (value, points) =>
  isFlat(value, points) ? 'about the same as' : value > 0 ? 'higher than' : 'lower than'

function Change({ value, points = false, invert = false }) {
  if (value == null) return <span className="text-muted">—</span>
  const flat = isFlat(value, points)
  const up = value > 0
  const good = invert ? !up : up
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight
  const tone = flat ? 'text-muted' : good ? 'text-good' : 'text-bad'
  const text = points ? `${(Math.abs(value) * 100).toFixed(1)} pts` : pct(Math.abs(value), 0)
  return (
    <span className={`tabular inline-flex items-center gap-1 ${tone}`}>
      <Icon className="size-[1.1em]" strokeWidth={2.5} />
      {text}
    </span>
  )
}

const longDate = (iso) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

const median = (values) => {
  const v = values.filter((x) => x != null).sort((a, b) => a - b)
  if (!v.length) return null
  const m = Math.floor(v.length / 2)
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2
}

function explainDay(series, i, rewardsDate) {
  const d = series[i]
  const normal = median(series.slice(Math.max(0, i - 28), i).map((x) => x.transactions))
  const weekday = new Date(`${d.date}T12:00:00`).getDay()
  const notes = []
  if (d.date === rewardsDate)
    notes.push({ tone: 'text-warn', text: 'The last day any customer received a reward payout.' })
  if (normal && d.transactions >= normal * 1.6)
    notes.push({
      tone: 'text-good',
      text: `Unusually busy: about ${(d.transactions / normal).toFixed(1)}× a normal day in the 4 weeks before it.`,
    })
  else if (normal && d.transactions <= normal * 0.6)
    notes.push({
      tone: 'text-warn',
      text: `Unusually quiet: about ${pct(1 - d.transactions / normal, 0)} below a normal day in the 4 weeks before it.`,
    })
  if (d.failure_rate != null && d.settled >= 50 && d.failure_rate >= 0.25)
    notes.push({
      tone: 'text-bad',
      text: `High failure day: ${num(d.failed)} of ${num(d.settled)} transactions failed. Check the Health tab for reasons.`,
    })
  if (weekday === 0 || weekday === 6) notes.push({ tone: 'text-slate-300', text: 'Weekend: days are usually quieter.' })
  if (!notes.length) notes.push({ tone: 'text-slate-300', text: 'A normal day, in line with the weeks around it.' })
  return { normal, notes }
}

export default function TrendsScene({ data }) {
  const { enabled, open } = useExplore()
  const t = data.trends
  if (!t?.series?.length) {
    return <div className="grid h-full place-items-center text-muted">Building the 90-day picture…</div>
  }
  const series = t.series
  const daily = series.map((d) => d.transactions)
  const smooth = avg7(daily)
  const max = Math.max(1, ...daily) * 1.1
  const s = t.summary.transactions
  const rewardsDate = data.rewards?.last_paid_at?.slice(0, 10)
  const rewardsIndex = series.findIndex((d) => d.date === rewardsDate)
  const area = `${path(daily, max)} L${W},${H} L0,${H} Z`

  return (
    <div className="grid h-full grid-cols-12 grid-rows-[minmax(0,1fr)] gap-[2.5vw]">
      <Panel className="col-span-8 flex min-h-0 flex-col">
        <div className="flex items-start justify-between gap-6">
          <div>
            <Eyebrow>Transactions per day · last {t.days} days</Eyebrow>
            <div className="mt-1 text-[clamp(16px,1.4vw,30px)] font-medium">Where we're heading</div>
            <p className="mt-1 max-w-[46ch] text-[clamp(11px,0.85vw,17px)] leading-snug text-muted">
              How many transactions customers make each day, over the last {t.days} days. Hover over any day to see its
              details.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-[2vw] text-right">
              {[
                ['This week', s.this_week, null],
                ['Last week', s.last_week, s.vs_last_week],
                ['4 weeks ago', s.month_ago, s.vs_month_ago],
              ].map(([label, value, change]) => (
                <div key={label}>
                  <div className="text-[clamp(9px,0.7vw,14px)] tracking-[0.18em] text-muted uppercase">{label}</div>
                  <div className="tabular mt-1 text-[clamp(18px,1.7vw,36px)] font-semibold">
                    {num(value)}
                    <span className="ml-1 text-[clamp(10px,0.75vw,15px)] font-normal text-muted">/day</span>
                  </div>
                  {change != null && (
                    <div className="text-[clamp(11px,0.85vw,17px)] text-muted">
                      this week is <Change value={change} />{' '}
                      {isFlat(change) ? 'the same' : change > 0 ? 'higher' : 'lower'}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p className="max-w-[48ch] text-right text-[clamp(10px,0.75vw,15px)] leading-snug text-muted/80">
              Each week is shown as its typical day: the middle day of that week, so one unusually busy or quiet day
              does not skew it.
            </p>
          </div>
        </div>

        <div className="relative mt-[3vh] min-h-0 flex-1 pb-7">
          <ChartHover
            count={series.length}
            className="size-full"
            onPick={enabled ? (i) => open(list({ date: series[i].date })) : undefined}
            markers={(i) => [
              { y: (H - PAD - (smooth[i] / max) * (H - PAD * 2)) / H, color: 'var(--color-brand-soft)' },
              { y: (H - PAD - (daily[i] / max) * (H - PAD * 2)) / H, color: 'var(--color-accent)' },
            ]}
            render={(i) => {
              const d = series[i]
              const { normal, notes } = explainDay(series, i, rewardsDate)
              return (
                <>
                  <TipTitle>{longDate(d.date)}</TipTitle>
                  <TipRow label="Transactions" value={num(d.transactions)} color="var(--color-accent)" />
                  <TipRow label="7-day average" value={`${num(smooth[i])} a day`} color="var(--color-brand-soft)" />
                  {normal != null && <TipRow label="Normal day before it" value={num(normal)} />}
                  <TipRow label="Money moved" value={naira(d.value)} />
                  <TipRow
                    label="Failed"
                    value={d.failure_rate == null ? '—' : `${num(d.failed)} (${pct(d.failure_rate, 0)})`}
                  />
                  <TipRow label="Sign-ups · accounts" value={`${num(d.signups)} · ${num(d.accounts)}`} />
                  {notes.map((n) => (
                    <TipNote key={n.text} tone={n.tone}>
                      {n.text}
                    </TipNote>
                  ))}
                </>
              )
            }}
          >
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="size-full overflow-visible">
              <defs>
                <linearGradient id="trendFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.28" />
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
              <motion.path
                d={area}
                fill="url(#trendFill)"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 1.2, delay: 0.8 }}
              />
              <motion.path
                d={path(daily, max)}
                fill="none"
                stroke="var(--color-accent)"
                strokeOpacity="0.45"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 1, delay: 0.3 }}
              />
              <motion.path
                d={path(smooth, max)}
                fill="none"
                stroke="var(--color-brand-soft)"
                strokeWidth="3.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ filter: 'drop-shadow(0 0 8px var(--color-brand-soft))' }}
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 2, ease: 'easeInOut', delay: 0.4 }}
              />
            </svg>
          </ChartHover>

          {rewardsIndex >= 0 && (
            <motion.div
              className="absolute top-0 bottom-7 border-l border-dashed border-warn/60"
              style={{ left: `${(rewardsIndex / (series.length - 1)) * 100}%` }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2 }}
            >
              <span
                className={`absolute top-0 ${rewardsIndex / (series.length - 1) > 0.7 ? 'right-2' : 'left-2'} rounded-full bg-warn/15 px-2 py-0.5 text-[clamp(10px,0.75vw,15px)] whitespace-nowrap text-warn`}
              >
                Rewards last paid · {shortDate(rewardsDate)}
              </span>
            </motion.div>
          )}

          <div className="absolute inset-x-0 bottom-0 flex justify-between font-mono text-[clamp(10px,0.75vw,15px)] text-muted">
            {[0, 0.25, 0.5, 0.75, 1].map((f) => {
              const d = series[Math.round(f * (series.length - 1))]
              return <span key={f}>{shortDate(d.date)}</span>
            })}
          </div>
        </div>

        <div className="mt-2 flex gap-6 text-[clamp(11px,0.85vw,17px)] text-muted">
          <span className="flex items-center gap-2">
            <span className="h-[3px] w-6 rounded-full bg-brand-soft" /> Bright line: 7-day average, smooths out daily
            ups and downs
          </span>
          <span className="flex items-center gap-2">
            <span className="h-[2px] w-6 rounded-full bg-accent/50" /> Faint line: the actual count each day
          </span>
        </div>
      </Panel>

      <div className="col-span-4 grid min-h-0 grid-rows-4 gap-[1.2vw]">
        <Metric
          label="Value moved"
          field="value"
          series={series}
          summary={t.summary.value}
          format={naira}
          delay={0.15}
        />
        <Metric
          label="Sign-ups"
          field="signups"
          series={series}
          summary={t.summary.signups}
          format={num}
          delay={0.25}
        />
        <Metric
          label="New accounts"
          field="accounts"
          series={series}
          summary={t.summary.accounts}
          format={num}
          delay={0.35}
        />
        <Metric
          label="Failure rate"
          field="failure_rate"
          series={series}
          summary={t.summary.failure_rate}
          format={(v) => pct(v, 1)}
          points
          invert
          delay={0.45}
        />
      </div>
    </div>
  )
}

const ABOUT = {
  value: 'Money customers successfully moved on a typical day this week.',
  signups: 'People who started opening an account, on a typical day this week.',
  accounts: 'Accounts actually opened, on a typical day this week.',
  failure_rate: 'Out of every 100 transactions this week, how many failed. Lower is better.',
}

const EXPLAIN = {
  value:
    'Total money in successful transactions. Bigger transfers can raise it even when there are fewer transactions.',
  signups: 'People who started signing up in the app that day, whether or not they finished.',
  accounts: 'Sign-ups that ended with an account actually opened that day.',
  failure_rate: 'Share of finished transactions that failed. Lower is better; the Health tab shows why they failed.',
}

function Metric({ label, field, series, summary, format, points = false, invert = false, delay }) {
  const values = avg7(series.map((d) => d[field] ?? 0))
  const max = Math.max(1e-9, ...values) * 1.1
  return (
    <Panel className="flex min-h-0 items-center gap-[1.2vw] !py-[1.4vh]" delay={delay}>
      <div className="min-w-0 flex-1">
        <Eyebrow>{label}</Eyebrow>
        <p className="mt-0.5 line-clamp-2 text-[clamp(10px,0.75vw,15px)] leading-snug text-muted/80">{ABOUT[field]}</p>
        <div className="tabular mt-1 text-[clamp(18px,1.6vw,34px)] leading-tight font-semibold">
          {format(summary.this_week)}
          {!points && <span className="ml-1 text-[clamp(10px,0.75vw,15px)] font-normal text-muted">a day</span>}
        </div>
        <div className="text-[clamp(11px,0.85vw,17px)] text-muted">
          {summary.vs_month_ago == null ? (
            summary.this_week == null ? (
              'No transactions yet this week'
            ) : (
              'Nothing from 4 weeks ago to compare with'
            )
          ) : (
            <>
              <Change value={summary.vs_month_ago} points={points} invert={invert} />{' '}
              {direction(summary.vs_month_ago, points)} 4 weeks ago
              {summary.month_ago != null && <span className="text-muted/70"> (was {format(summary.month_ago)})</span>}
            </>
          )}
        </div>
      </div>
      <div className="flex h-[78%] w-[42%] shrink-0 flex-col">
        <ChartHover
          count={series.length}
          className="min-h-0 w-full flex-1"
          markers={(i) => [{ y: (60 - 4 - (values[i] / max) * 52) / 60, color: 'var(--color-brand-soft)' }]}
          render={(i) => (
            <>
              <TipTitle>
                {label} · {longDate(series[i].date)}
              </TipTitle>
              <TipRow label="That day" value={series[i][field] == null ? '—' : format(series[i][field])} />
              <TipRow label="7-day average" value={format(values[i])} color="var(--color-brand-soft)" />
              <TipNote>{EXPLAIN[field]}</TipNote>
            </>
          )}
        >
          <svg viewBox="0 0 200 60" preserveAspectRatio="none" className="size-full overflow-visible">
            <motion.path
              d={path(values, max, 200, 60, 4)}
              fill="none"
              stroke="var(--color-brand-soft)"
              strokeWidth="2"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1.6, delay: delay + 0.3, ease: EASE }}
            />
          </svg>
        </ChartHover>
        <div className="mt-1 text-right text-[clamp(9px,0.65vw,13px)] text-muted/70">
          Last {series.length} days · 7-day average
        </div>
      </div>
    </Panel>
  )
}
