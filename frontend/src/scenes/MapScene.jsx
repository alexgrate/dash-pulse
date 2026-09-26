import { MapPin } from 'lucide-react'
import { motion } from 'motion/react'
import AnimatedNumber from '../components/AnimatedNumber'
import NigeriaMap from '../components/NigeriaMap'
import { Eyebrow, Panel } from '../components/ui'
import { num } from '../lib/format'

const EASE = [0.16, 1, 0.3, 1]

export default function MapScene({ data }) {
  const { points, cities, located, city_count: cityCount, recent_minutes: minutes } = data.geography
  const top = Math.max(1, ...cities.map((c) => c.count))

  return (
    <div className="grid h-full grid-cols-12 grid-rows-[minmax(0,1fr)] gap-[2.5vw]">
      <Panel className="col-span-7 flex flex-col">
        <div className="flex items-start justify-between">
          <div>
            <Eyebrow>Where Nigeria is banking today</Eyebrow>
            <div className="mt-1 text-[clamp(16px,1.4vw,30px)] font-medium">Live transaction map</div>
          </div>
          <span className="flex items-center gap-2 text-[clamp(11px,0.85vw,17px)] text-muted">
            <span className="size-2.5 rounded-full bg-good" /> Last {minutes} min
          </span>
        </div>
        <div className="relative mt-[2vh] min-h-0 flex-1">
          {points.length ? (
            <NigeriaMap points={points} cities={cities} />
          ) : (
            <div className="grid h-full place-items-center text-muted">No located transactions yet today</div>
          )}
        </div>
      </Panel>

      <div className="col-span-5 flex min-h-0 flex-col gap-[2.5vw]">
        <Panel delay={0.15}>
          <div className="flex items-center gap-3">
            <MapPin className="size-[clamp(16px,1.3vw,28px)] text-accent" />
            <Eyebrow>Transactions with a location</Eyebrow>
          </div>
          <AnimatedNumber
            value={located}
            className="mt-3 block text-[clamp(40px,4.6vw,100px)] leading-none font-semibold tracking-[-0.04em]"
          />
          <div className="mt-3 text-[clamp(12px,0.95vw,20px)] text-muted">
            across <span className="text-slate-200">{num(cityCount)}</span> {cityCount === 1 ? 'city' : 'cities'} today
          </div>
        </Panel>

        <Panel className="flex min-h-0 flex-1 flex-col" delay={0.25}>
          <Eyebrow>Top cities today</Eyebrow>
          <div className="mt-[3vh] flex flex-1 flex-col justify-around">
            {cities.slice(0, 5).map((c, i) => (
              <div key={c.city}>
                <div className="mb-2 flex items-end justify-between">
                  <span className="text-[clamp(13px,1.1vw,23px)]">{c.city}</span>
                  <span className="flex items-baseline gap-3">
                    {c.recent > 0 && (
                      <span className="rounded-full bg-good/10 px-2 py-0.5 text-[clamp(10px,0.8vw,16px)] text-good">
                        +{num(c.recent)}
                      </span>
                    )}
                    <span className="tabular text-[clamp(16px,1.5vw,32px)] font-semibold">{num(c.count)}</span>
                  </span>
                </div>
                <div className="h-[clamp(5px,0.6vh,9px)] overflow-hidden rounded-full bg-white/[0.05]">
                  <motion.div
                    className="h-full rounded-full bg-accent"
                    style={{ boxShadow: '0 0 14px var(--color-accent)' }}
                    initial={{ width: 0 }}
                    animate={{ width: `${(c.count / top) * 100}%` }}
                    transition={{ duration: 1.3, delay: 0.4 + i * 0.1, ease: EASE }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}
