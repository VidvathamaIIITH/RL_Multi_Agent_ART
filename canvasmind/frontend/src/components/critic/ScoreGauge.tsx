import React from 'react'
import { motion } from 'framer-motion'

interface Props { score: number; label: string; size?: number }

function scoreColor(score: number): string {
  if (score < 4) return '#ef4444'
  if (score < 6) return '#f59e0b'
  if (score < 8) return '#6366f1'
  return '#10b981'
}

export function ScoreGauge({ score, label, size = 72 }: Props) {
  const r = (size / 2) - 6
  const circumference = 2 * Math.PI * r
  const pct = Math.min(score / 10, 1)
  const offset = circumference * (1 - pct)
  const color = scoreColor(score)

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={size / 2} cy={size / 2} r={r}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="4"
          />
          <motion.circle
            cx={size / 2} cy={size / 2} r={r}
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ filter: `drop-shadow(0 0 6px ${color}80)` }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <motion.span
            className="text-sm font-bold font-mono"
            style={{ color }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
          >
            {score.toFixed(1)}
          </motion.span>
        </div>
      </div>
      <span className="text-xs text-text-secondary text-center">{label}</span>
    </div>
  )
}
