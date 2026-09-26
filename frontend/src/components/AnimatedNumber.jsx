import { animate, motion, useMotionValue, useTransform } from 'motion/react'
import { useEffect } from 'react'
import { num } from '../lib/format'

export default function AnimatedNumber({ value, format = num, className }) {
  const motionValue = useMotionValue(0)
  const text = useTransform(motionValue, (v) => format(v))

  useEffect(() => {
    const controls = animate(motionValue, value ?? 0, { duration: 1.8, ease: [0.16, 1, 0.3, 1] })
    return () => controls.stop()
  }, [value, motionValue])

  return <motion.span className={`tabular ${className ?? ''}`}>{text}</motion.span>
}
