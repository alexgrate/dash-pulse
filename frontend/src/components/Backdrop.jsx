import { AnimatePresence, motion } from 'motion/react'

const BLOBS = [
  {
    color: 'var(--color-accent)',
    opacity: 0.12,
    className: '-left-[15%] -top-[30%] size-[60vw]',
    x: ['0%', '12%', '0%'],
    y: ['0%', '8%', '0%'],
    seconds: 30,
  },
  {
    color: 'var(--color-brand)',
    opacity: 0.55,
    className: '-right-[20%] top-[10%] size-[55vw]',
    x: ['0%', '-10%', '0%'],
    y: ['0%', '12%', '0%'],
    seconds: 38,
  },
  {
    color: 'var(--color-good)',
    opacity: 0.1,
    className: 'left-[25%] -bottom-[45%] size-[50vw]',
    x: ['0%', '8%', '0%'],
    y: ['0%', '-10%', '0%'],
    seconds: 46,
  },
]

export default function Backdrop({ alert = false }) {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <AnimatePresence>
        {alert && (
          <motion.div
            key="alert"
            className="absolute inset-0"
            style={{ background: 'radial-gradient(ellipse at 50% 40%, var(--color-bad), transparent 70%)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: [0.08, 0.2, 0.08] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
          />
        )}
      </AnimatePresence>
      {BLOBS.map((b, i) => (
        <motion.div
          key={i}
          className={`absolute rounded-full blur-[120px] ${b.className}`}
          style={{ background: b.color, opacity: b.opacity }}
          animate={{ x: b.x, y: b.y }}
          transition={{ duration: b.seconds, repeat: Infinity, ease: 'easeInOut' }}
        />
      ))}
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            'linear-gradient(var(--color-line) 1px, transparent 1px), linear-gradient(90deg, var(--color-line) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          maskImage: 'radial-gradient(ellipse at center, black 20%, transparent 75%)',
        }}
      />
    </div>
  )
}
