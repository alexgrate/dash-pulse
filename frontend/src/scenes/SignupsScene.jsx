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

const short = (n) => (n >= 10000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : num(n))

const people = (p) => ({ type: 'people', mode: 'signups', date: p.start, until: p.end })

export default function SignupsScene({ data }) {
  const h = data.signup_history
  const { allowed, openNow } = useExplore()
  if (!h) return <div className="grid h-full place-items-center text-muted">Building the sign-up history…</div>
  const pick = allowed ? (p) => openNow(people(p)) : undefined
  const cards = [
    ['Today', h.day[0], 'so far'],
    ['Yesterday', h.day[1]],
    ['This week', h.week[0], 'so far'],
    ['Last week', h.week[1]],
    ['This month', h.month[0], 'so far'],
    ['Last month', h.month[1]],
  ]
  return (
    <div className="flex h-full flex-col gap-[1.2vw]">
      <div className="grid shrink-0 grid-cols-6 gap-[1vw]">
        {cards.map(([label, p, note], i) => (
          <Summary key={label} label={label} note={note} period={p} onPick={pick} delay={i * 0.05} />
        ))}
      </div>
      <History by="day" items={h.day} title="Day by day" span="last 30 days" onPick={pick} delay={0.3} />
      <div className="grid min-h-0 flex-1 grid-cols-2 gap-[1.2vw]">
        <History by="week" items={h.week} title="Week by week" span="last 12 weeks" onPick={pick} delay={0.4} />
        <History by="month" items={h.month} title="Month by month" span="last 12 months" onPick={pick} delay={0.5} />
      </div>
    </div>
  )
}

function Summary({ label, note, period, onPick, delay }) {
  if (!period) return <Panel delay={delay} />
  const body = (
    <>
      <div className="flex items-baseline justify-between gap-2">
        <Eyebrow>{label}</Eyebrow>
        {note && <span className="text-[clamp(9px,0.65vw,13px)] text-brand-soft">{note}</span>}
      </div>
      <div className="tabular mt-1 text-[clamp(22px,2.2vw,46px)] leading-none font-semibold">{num(period.signups)}</div>
      <div className="mt-1 text-[clamp(10px,0.8vw,16px)] leading-snug text-muted">
        sign-ups · <span className="text-good">{num(period.opened)} opened</span>
        {period.finished_share != null && <> · {pct(period.finished_share, 0)} finished</>}
      </div>
    </>
  )
  return (
    <Panel className="!py-[min(1.2vw,1.8vh)]" delay={delay}>
      {onPick ? (
        <button
          type="button"
          onClick={() => onPick(period)}
          className="-m-2 block w-[calc(100%+1rem)] cursor-pointer rounded-xl p-2 text-left transition hover:bg-white/[0.05] hover:ring-2 hover:ring-brand-soft/40"
        >
          {body}
        </button>
      ) : (
        body
      )}
    </Panel>
  )
}

function History({ by, items, title, span, onPick, delay }) {
  const series = [...items].reverse()
  const max = Math.max(1, ...series.map((i) => Math.max(i.signups, i.opened)))
  const labelEvery = by === 'day' ? 2 : 1

  return (
    <Panel className="flex min-h-0 flex-1 flex-col !py-[min(1.2vw,1.8vh)]" delay={delay}>
      <div className="flex items-center justify-between gap-6">
        <Eyebrow>
          {title} · {span}
        </Eyebrow>
        <div className="flex shrink-0 items-center gap-4 text-[clamp(10px,0.75vw,15px)] text-muted">
          {onPick && by === 'day' && <span className="text-brand-soft">Click any card or bar to see the people</span>}
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
        className="mt-[1vh] min-h-0 flex-1"
        onPick={onPick ? (i) => onPick(series[i]) : undefined}
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
                {onPick ? ' Click to see the people.' : ''}
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
                  className={`absolute inset-x-0 bottom-0 rounded-t-[4px] ${p.current ? 'bg-accent/55' : 'bg-accent/35'}`}
                  initial={{ height: 0 }}
                  animate={{ height: `${Math.max((p.signups / max) * 82, 0.6)}%` }}
                  transition={{ duration: 1, delay: delay + i * 0.015, ease: EASE }}
                />
                <motion.div
                  className="absolute inset-x-[18%] bottom-0 rounded-t-[3px] bg-good"
                  initial={{ height: 0 }}
                  animate={{ height: `${(p.opened / max) * 82}%` }}
                  transition={{ duration: 1, delay: delay + 0.2 + i * 0.015, ease: EASE }}
                />
                <motion.div
                  className="tabular absolute inset-x-0 pb-0.5 text-center text-[clamp(9px,0.68vw,14px)] leading-none whitespace-nowrap text-slate-200"
                  initial={{ bottom: 0, opacity: 0 }}
                  animate={{ bottom: `${(Math.max(p.signups, p.opened) / max) * 82}%`, opacity: 1 }}
                  transition={{ duration: 1, delay: delay + i * 0.015, ease: EASE }}
                >
                  {short(p.signups)}
                </motion.div>
              </div>
              <div className="tabular mt-1 truncate text-center text-[clamp(8px,0.62vw,13px)] leading-none text-good">
                {short(p.opened)}
              </div>
              <div className="mt-1 h-[1.2em] truncate text-center font-mono text-[clamp(8px,0.6vw,12px)] text-muted">
                {i % labelEvery === 0 || i === series.length - 1 ? LABELS[by](p) : ''}
              </div>
            </div>
          ))}
        </div>
      </ChartHover>
    </Panel>
  )
}
