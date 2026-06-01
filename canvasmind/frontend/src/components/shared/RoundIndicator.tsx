import React from 'react'
import { motion } from 'framer-motion'

interface Props { current: number; max: number }

export function RoundIndicator({ current, max }: Props) {
  const pct = max > 0 ? (current / max) * 100 : 0
  return (
    <div className="flex items-center gap-3">
      <span className="text-text-secondary text-xs font-mono">Round</span>
      <div className="flex items-center gap-2">
        <span className="text-text-primary font-bold text-sm font-mono">{current}</span>
        <span className="text-text-muted text-xs">/</span>
        <span className="text-text-secondary text-xs font-mono">{max}</span>
      </div>
      <div className="w-24 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <motion.div
          className="h-full bg-gradient-to-r from-accent-a to-accent-b rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
    </div>
  )
}
