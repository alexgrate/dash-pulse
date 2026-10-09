import { naira, num, pct } from '../lib/format'

export default function Ticker({ data }) {
  const t = data.transactions.today
  const alert = data.health?.alert
  const items = [
    ...(alert
      ? [
          `⚠ Failures at ${pct(alert.failure_rate)} in the last ${alert.window_minutes} min (normal ${pct(alert.normal_rate)})`,
        ]
      : []),
    ...(data.intelligence?.items ?? []).slice(0, 4).map((i) => i.title),
    `${num(t.count)} transactions today`,
    `${pct(t.success_rate)} success rate`,
    `${naira(t.value)} sent by customers`,
    `${num(t.failed)} failed · ${num(t.reversed)} reversed`,
    `${num(data.active_users.today)} active users`,
    `${num(data.new_accounts.today)} new accounts`,
    data.rewards.today.count
      ? `${num(data.rewards.today.count)} rewards paid · ${naira(data.rewards.today.value)}`
      : 'No reward payouts today',
  ]

  return (
    <footer className="overflow-hidden border-t border-white/[0.06] bg-black/30 py-[1.4vh] text-[clamp(12px,0.95vw,20px)] text-muted">
      <div className="flex w-max animate-marquee whitespace-nowrap">
        {[...items, ...items].map((text, i) => (
          <span key={i} className="flex items-center gap-[2.5vw] pr-[2.5vw]">
            {text}
            <span className="size-1.5 rounded-full bg-accent/60" />
          </span>
        ))}
      </div>
    </footer>
  )
}
