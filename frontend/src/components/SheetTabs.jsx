import { ExternalLink, RotateCw } from 'lucide-react'
import { useState } from 'react'

export const SHEETS = [
  { id: 'pulse', label: 'Pulse' },
  { id: 'loans', label: 'Loans', url: 'https://loandashboard.dash-mfb.com/' },
  { id: 'cx', label: 'CX', url: 'https://cxdashboard.dash-mfb.com/' },
]

export default function SheetTabs({ active, onPick }) {
  return (
    <nav className="flex shrink-0 items-stretch gap-1 border-t border-white/10 bg-[#070a12] px-[2vw] text-[clamp(11px,0.8vw,15px)]">
      {SHEETS.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onPick(s.id)}
          className={`rounded-b-lg px-[1.2vw] py-[0.9vh] font-medium transition ${
            s.id === active
              ? 'bg-white/[0.07] text-slate-100 shadow-[inset_0_2px_0_var(--color-brand-soft)]'
              : 'text-muted hover:bg-white/[0.03] hover:text-slate-200'
          }`}
        >
          {s.label}
        </button>
      ))}
    </nav>
  )
}

export function SheetFrame({ sheet, visible }) {
  const [round, setRound] = useState(0)
  const action =
    'flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-slate-300 hover:bg-white/5 hover:text-slate-100'
  return (
    <div className={visible ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}>
      <div className="flex shrink-0 items-center gap-3 border-b border-white/10 bg-[#070a12] px-[2vw] py-1.5 text-[clamp(11px,0.75vw,14px)] text-muted">
        <span className="min-w-0 flex-1 truncate">
          Blank page after signing in with OCI? Open it in a new tab, sign in there once, then come back and press
          Reload.
        </span>
        <a href={sheet.url} target="_blank" rel="noopener noreferrer" className={action}>
          <ExternalLink className="size-3.5" />
          Open in new tab
        </a>
        <button type="button" onClick={() => setRound((r) => r + 1)} className={action}>
          <RotateCw className="size-3.5" />
          Reload
        </button>
      </div>
      <iframe
        key={round}
        title={sheet.label}
        src={sheet.url}
        referrerPolicy="strict-origin-when-cross-origin"
        className="min-h-0 w-full flex-1 border-0 bg-white"
      />
    </div>
  )
}
