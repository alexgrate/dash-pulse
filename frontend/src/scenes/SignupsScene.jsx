import { motion } from 'motion/react'
import ChartHover, { TipNote, TipRow, TipTitle } from '../components/ChartHover'
import { Eyebrow, Panel } from '../components/ui'
import { useExplore } from '../lib/explore'
import { num, pct } from '../lib/format'

const EASE = [0.16, 1, 0.3, 1]

const day = (iso, opts) => new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-GB', opts)

const LABELS = {
  day: (i) => day(i.start, { day: 'numeric', month: 'short' }),
  week: (i) => day(i.start, { day: 'numeric', month: 'short' }),
  month: (i) => day(i.start, { month: 'short', year: '2-digit' }),
}

const TITLES = {
  day: (i) => day(i.start, { weekday: 'long', day: 'numeric', month: 'long' }),
  week: (i) =>
    `${day(i.start, { day: 'numeric', month: 'short' })} – ${i.current ? 'today' : day(i.end, { day: 'numeric', month: 'short' })}`,
  month: (i) => day(i.start, { month: 'long', year: 'numeric' }),
}

const PERIOD = { day: 'day', week: 'week', month: 'month' }
const THIS = { day: 'today', week: 'this week', month: 'this month' }
const LAST = { day: 'yesterday', week: 'last week', month: 'last month' }

export default function SignupsScene({ data }) {
  const h = data.signup_history
  if (!h) return <div className="grid h-full place-items-center text-muted">Building the sign-up history…</div>
  return (
    <div className="grid h-full grid-cols-2 grid-rows-[minmax(0,1.1fr)_minmax(0,1fr)] gap-[1.6vw]">
      <History by="day" items={h.day} title="Day by day" span="last 30 days" className="col-span-2" delay={0} />
      <History by="week" items={h.week} title="Week by week" span="last 12 weeks" delay={0.15} />
      <History by="month" items={h.month} title="Month by month" span="last 12 months" delay={0.3} />
    </div>
  )
}

function History({ by, items, title, span, className = '', delay }) {
  const { enabled, open } = useExplore()
  const series = [...items].reverse()
  const max = Math.max(1, ...series.map((i) => i.signups))
  const latest = series.at(-1)
  const previous = series.at(-2)
  const labelEvery = Math.ceil(series.length / (by === 'day' ? 10 : 12))

  return (
    <Panel className={`flex min-h-0 flex-col ${className}`} delay={delay}>
      <div className="flex items-start justify-between gap-6">
        <div>
          <Eyebrow>
            {title} · {span}
          </Eyebrow>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="tabular text-[clamp(20px,2vw,42px)] leading-tight font-semibold">
              {num(latest?.signups)}
            </span>
            <span className="text-[clamp(11px,0.85vw,17px)] text-muted">
              sign-ups {THIS[by]}
              {latest?.current ? ' so far' : ''} · <span className="text-good">{num(latest?.opened)} opened</span>
              {previous && (
                <>
                  {' '}
                  · {LAST[by]} {num(previous.signups)}
                </>
              )}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 gap-4 text-[clamp(10px,0.75vw,15px)] text-muted">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-accent/35" /> Sign-ups
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-good" /> Accounts opened
          </span>
        </div>
      </div>

      <ChartHover
        count={series.length}
        className="mt-[1.5vh] min-h-0 flex-1"
        onPick={
          enabled
            ? (i) => open({ type: 'people', mode: 'signups', date: series[i].start, until: series[i].end })
            : undefined
        }
        render={(i) => {
          const p = series[i]
          return (
            <>
              <TipTitle>
                {TITLES[by](p)}
                {p.current ? ' (so far)' : ''}
              </TipTitle>
              <TipRow label="Sign-ups started" value={num(p.signups)} color="var(--color-accent)" />
              <TipRow label="Accounts opened" value={num(p.opened)} color="var(--color-good)" />
              <TipRow label="Finished" value={p.finished_share == null ? '—' : pct(p.finished_share, 0)} />
              <TipNote>
                Finished: of the people who started in this {PERIOD[by]}, how many have an account now.
                {enabled ? ' Click to see the people.' : ''}
              </TipNote>
            </>
          )
        }}
      >
        <div className="flex size-full items-end gap-[3px]">
          {series.map((p, i) => (
            <div key={p.start} className="flex h-full min-w-0 flex-1 flex-col justify-end">
              <div className="relative flex-1">
                <motion.div
                  className="absolute inset-x-0 bottom-0 rounded-t-[4px] bg-accent/35"
                  initial={{ height: 0 }}
                  animate={{ height: `${(p.signups / max) * 100}%` }}
                  transition={{ duration: 1, delay: delay + i * 0.015, ease: EASE }}
                />
                <motion.div
                  className="absolute inset-x-[18%] bottom-0 rounded-t-[3px] bg-good"
                  initial={{ height: 0 }}
                  animate={{ height: `${(p.opened / max) * 100}%` }}
                  transition={{ duration: 1, delay: delay + 0.2 + i * 0.015, ease: EASE }}
                />
              </div>
              <div className="mt-1.5 h-[1.3em] truncate text-center font-mono text-[clamp(9px,0.65vw,13px)] text-muted">
                {i % labelEvery === 0 || i === series.length - 1 ? LABELS[by](p) : ''}
              </div>
            </div>
          ))}
        </div>
      </ChartHover>
    </Panel>
  )
}
