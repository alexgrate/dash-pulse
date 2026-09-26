import { Sparkles } from 'lucide-react'
import { motion } from 'motion/react'
import { Eyebrow } from '../components/ui'
import { InsightIcon, itemsOf, TONES } from '../lib/insights'

const EASE = [0.16, 1, 0.3, 1]

export default function BriefingScene({ data }) {
  const items = itemsOf(data)
  const [lead, ...rest] = items
  const intel = data.intelligence
  const attention = items.filter((i) => i.severity === 'warn' || i.severity === 'bad').length

  if (!lead) {
    return (
      <div className="grid h-full place-items-center text-[clamp(16px,1.4vw,30px)] text-muted">
        Building today’s picture…
      </div>
    )
  }

  const leadTone = TONES[lead.severity] ?? TONES.info

  return (
    <div className="flex h-full flex-col gap-[3vh]">
      <div className="flex items-end justify-between gap-[3vw]">
        <div className="flex items-center gap-3">
          <Sparkles className="size-[clamp(16px,1.3vw,28px)] text-brand-soft" />
          <Eyebrow tone="text-brand-soft">What you need to know right now</Eyebrow>
        </div>
        <div className="text-right text-[clamp(11px,0.9vw,18px)] text-muted">
          {`Watching ${intel.signals} signals against the last ${intel.typical?.days ?? 4} ${intel.typical?.weekday ?? 'day'}s · `}
          <span className={attention ? 'text-warn' : 'text-good'}>
            {attention ? `${attention} need${attention === 1 ? 's' : ''} attention` : 'all clear'}
          </span>
        </div>
      </div>

      <motion.div
        className={`relative overflow-hidden rounded-3xl border ${leadTone.border} bg-gradient-to-br from-brand/45 via-white/[0.02] to-transparent p-[2.2vw]`}
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.9, ease: EASE }}
      >
        <div className="flex items-start gap-[1.6vw]">
          <div
            className={`grid size-[clamp(48px,4.2vw,90px)] shrink-0 place-items-center rounded-2xl ${leadTone.bg} ${leadTone.text}`}
          >
            <InsightIcon insight={lead} className="size-1/2" />
          </div>
          <div className="min-w-0">
            <div className="text-[clamp(28px,3.4vw,72px)] leading-[1.05] font-semibold tracking-[-0.02em]">
              {lead.title}
            </div>
            <div className="mt-3 max-w-[70ch] text-[clamp(14px,1.3vw,28px)] text-slate-300">{lead.detail}</div>
          </div>
        </div>
      </motion.div>

      <div className="grid min-h-0 flex-1 grid-cols-3 grid-rows-2 gap-[1.4vw]">
        {rest.slice(0, 6).map((item, i) => {
          const tone = TONES[item.severity] ?? TONES.info
          return (
            <motion.div
              key={item.id}
              className="relative flex min-h-0 flex-col overflow-hidden rounded-3xl border border-white/[0.06] bg-white/[0.025] p-[1.4vw] backdrop-blur-xl"
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.25 + i * 0.1, ease: EASE }}
            >
              <span className={`absolute inset-y-0 left-0 w-1 ${tone.bar}`} />
              <div className="flex items-center gap-3">
                <div
                  className={`grid size-[clamp(28px,2.2vw,46px)] place-items-center rounded-xl ${tone.bg} ${tone.text}`}
                >
                  <InsightIcon insight={item} className="size-1/2" />
                </div>
                <span className="text-[clamp(10px,0.75vw,15px)] tracking-[0.2em] text-muted uppercase">
                  {SCENE_NAMES[item.scene] ?? item.scene}
                </span>
              </div>
              <div className="mt-3 text-[clamp(15px,1.35vw,28px)] leading-snug font-semibold">{item.title}</div>
              <div className="mt-2 line-clamp-3 text-[clamp(12px,0.95vw,20px)] text-muted">{item.detail}</div>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}

const SCENE_NAMES = {
  pulse: 'Pulse',
  flow: 'Money & people',
  map: 'Map',
  funnel: 'Onboarding',
  health: 'Health',
}
