import { ArrowLeftRight, Dices, Gift, Receipt, Smartphone, UserPlus } from 'lucide-react'
import { motion } from 'motion/react'
import AnimatedNumber from '../components/AnimatedNumber'
import Delta from '../components/Delta'
import { Eyebrow, Panel } from '../components/ui'
import { naira, num } from '../lib/format'
import { versus } from '../lib/insights'

const GROUP_STYLE = {
  Transfers: { icon: ArrowLeftRight, color: 'var(--color-accent)' },
  'Airtime & Data': { icon: Smartphone, color: 'var(--color-glow)' },
  Betting: { icon: Dices, color: 'var(--color-warn)' },
  Bills: { icon: Receipt, color: 'var(--color-good)' },
}

const lastPaid = (iso) =>
  new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export default function FlowScene({ data }) {
  const total = data.mix.reduce((sum, g) => sum + g.count, 0) || 1

  return (
    <div className="grid h-full grid-cols-12 gap-[2.5vw]">
      <Panel className="col-span-7 flex flex-col">
        <Eyebrow>What customers are doing today</Eyebrow>
        <div className="mt-1 text-[clamp(16px,1.4vw,30px)] font-medium">Transaction mix</div>

        <div className="mt-[5vh] flex flex-1 flex-col justify-around">
          {data.mix.map((g, i) => {
            const style = GROUP_STYLE[g.group] ?? GROUP_STYLE.Bills
            const Icon = style.icon
            const share = g.count / total
            return (
              <div key={g.group}>
                <div className="mb-3 flex items-end justify-between">
                  <div className="flex items-center gap-3 text-[clamp(14px,1.25vw,26px)]">
                    <Icon className="size-[1.1em]" style={{ color: style.color }} />
                    {g.group}
                  </div>
                  <div className="flex items-baseline gap-4">
                    <span className="text-[clamp(12px,0.95vw,20px)] text-muted">{naira(g.value)}</span>
                    <AnimatedNumber value={g.count} className="text-[clamp(20px,1.9vw,40px)] font-semibold" />
                  </div>
                </div>
                <div className="h-[clamp(8px,0.9vh,14px)] overflow-hidden rounded-full bg-white/[0.05]">
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: style.color, boxShadow: `0 0 18px ${style.color}` }}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.max(share * 100, 0.8)}%` }}
                    transition={{ duration: 1.4, delay: 0.3 + i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </Panel>

      <div className="col-span-5 flex flex-col gap-[2.5vw]">
        <BigCard
          icon={UserPlus}
          label="New accounts opened"
          value={data.new_accounts.today}
          {...versus(data, 'accounts_so_far', data.new_accounts.yesterday)}
          delay={0.2}
        />
        <BigCard
          icon={Gift}
          label="Rewards paid out"
          value={data.rewards.today.count}
          yesterday={data.rewards.yesterday.count}
          extra={
            data.rewards.today.count || !data.rewards.last_paid_at
              ? `${naira(data.rewards.today.value)} paid today`
              : `Last payout ${lastPaid(data.rewards.last_paid_at)}`
          }
          delay={0.35}
        />
      </div>
    </div>
  )
}

function BigCard({ icon: Icon, label, value, yesterday, compareLabel, extra, delay }) {
  return (
    <Panel className="flex flex-1 flex-col justify-center" delay={delay}>
      <div className="flex items-center gap-3">
        <Icon className="size-[clamp(16px,1.3vw,28px)] text-accent" />
        <Eyebrow>{label}</Eyebrow>
      </div>
      <AnimatedNumber
        value={value}
        format={num}
        className="mt-3 block text-[clamp(48px,6vw,130px)] leading-none font-semibold tracking-[-0.04em]"
      />
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <Delta today={value} yesterday={yesterday} label={compareLabel} />
        {extra && <span className="text-[clamp(12px,0.95vw,20px)] text-muted">{extra}</span>}
      </div>
    </Panel>
  )
}
