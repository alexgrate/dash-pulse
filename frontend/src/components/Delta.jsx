import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { change } from '../lib/format'

export default function Delta({ today, yesterday, invert = false, label = 'vs this time yesterday' }) {
  const c = change(today, yesterday)
  if (c == null) return null

  const up = c > 0.005
  const down = c < -0.005
  const good = invert ? down : up
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus
  const tone = !up && !down ? 'text-muted bg-white/5' : good ? 'text-good bg-good/10' : 'text-bad bg-bad/10'

  return (
    <span className="inline-flex items-center gap-2 text-[clamp(12px,0.95vw,20px)]">
      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-medium ${tone}`}>
        <Icon className="size-[1.1em]" strokeWidth={2.5} />
        <span className="tabular">{Math.abs(c * 100).toFixed(1)}%</span>
      </span>
      <span className="text-muted">{label}</span>
    </span>
  )
}
