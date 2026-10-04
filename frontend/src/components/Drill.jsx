import { useExplore } from '../lib/explore'

export default function Drill({ to, className = '', children }) {
  const { enabled, open } = useExplore()
  if (!enabled || !to) return <div className={className}>{children}</div>
  const go = (e) => {
    e.stopPropagation()
    open(to)
  }
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={go}
      onKeyDown={(e) => (e.key === 'Enter' ? go(e) : null)}
      className={`${className} cursor-pointer rounded-xl ring-brand-soft/0 transition outline-none hover:bg-white/[0.04] hover:ring-2 hover:ring-brand-soft/40 focus-visible:ring-2 focus-visible:ring-brand-soft/60`}
    >
      {children}
    </div>
  )
}
