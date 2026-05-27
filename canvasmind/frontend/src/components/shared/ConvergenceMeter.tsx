import React from 'react'
import { motion } from 'framer-motion'

interface Props { score: number }

function getColor(score: number): string {
  if (score < 0.4) return '#ef4444'
  if (score < 0.65) return '#f59e0b'
  if (score < 0.85) return '#6366f1'
  return '#10b981'
}

export function ConvergenceMeter({ score }: Props) {
  const pct = Math.min(score * 100, 100)
  const color = getColor(score)
  const avg = (score * 10).toFixed(1)

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted whitespace-nowrap">Convergence</span>
      <div className="relative w-28 h-2 bg-bg-tertiary rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      </div>
      <span className="text-xs font-mono" style={{ color }}>{avg}/10</span>
    </div>
  )
}
