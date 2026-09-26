import { motion } from 'motion/react'

export function Eyebrow({ children, className = '', tone = 'text-muted' }) {
  return (
    <div className={`text-[clamp(11px,0.85vw,16px)] font-medium tracking-[0.22em] uppercase ${tone} ${className}`}>
      {children}
    </div>
  )
}

export function Panel({ children, className = '', delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}
      className={`rounded-3xl border border-white/[0.06] bg-white/[0.025] p-[1.6vw] backdrop-blur-xl ${className}`}
    >
      {children}
    </motion.div>
  )
}
