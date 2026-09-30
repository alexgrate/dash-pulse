import { useEffect, useRef, useState } from 'react'

function useHold(active) {
  useEffect(() => {
    if (!active) return
    window.dispatchEvent(new CustomEvent('pulse-hold', { detail: true }))
    return () => window.dispatchEvent(new CustomEvent('pulse-hold', { detail: false }))
  }, [active])
}

export default function ChartHover({ count, render, markers, className = '', children }) {
  const ref = useRef(null)
  const [index, setIndex] = useState(null)
  const [flip, setFlip] = useState(false)
  useHold(index != null)

  function move(e) {
    const box = ref.current.getBoundingClientRect()
    const f = Math.min(Math.max((e.clientX - box.left) / box.width, 0), 1)
    setIndex(Math.round(f * (count - 1)))
    setFlip(e.clientX > window.innerWidth / 2)
  }

  const f = index == null ? 0 : index / Math.max(count - 1, 1)
  const content = index == null ? null : render(index)

  return (
    <div ref={ref} className={`relative ${className}`} onMouseMove={move} onMouseLeave={() => setIndex(null)}>
      {children}
      {index != null && (
        <>
          <div className="pointer-events-none absolute inset-y-0 w-px bg-white/30" style={{ left: `${f * 100}%` }} />
          {(markers?.(index) ?? []).map((m, i) =>
            m.y == null ? null : (
              <span
                key={i}
                className="pointer-events-none absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-ink"
                style={{ left: `${f * 100}%`, top: `${m.y * 100}%`, background: m.color }}
              />
            ),
          )}
          {content && (
            <div
              className="pointer-events-none absolute top-2 z-30 w-max max-w-[min(360px,80vw)] rounded-2xl border border-white/10 bg-[#0b0f1a]/95 px-4 py-3 text-[clamp(12px,0.85vw,16px)] shadow-2xl backdrop-blur-xl"
              style={{
                left: `${f * 100}%`,
                transform: flip ? 'translateX(calc(-100% - 14px))' : 'translateX(14px)',
              }}
            >
              {content}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function TipTitle({ children }) {
  return <div className="font-semibold text-slate-100">{children}</div>
}

export function TipRow({ label, value, color }) {
  return (
    <div className="mt-1 flex items-center justify-between gap-6">
      <span className="flex items-center gap-2 text-muted">
        {color && <span className="size-2 rounded-full" style={{ background: color }} />}
        {label}
      </span>
      <span className="tabular text-slate-100">{value}</span>
    </div>
  )
}

export function TipNote({ tone = 'text-slate-300', children }) {
  return <div className={`mt-2 border-t border-white/10 pt-2 leading-snug ${tone}`}>{children}</div>
}
