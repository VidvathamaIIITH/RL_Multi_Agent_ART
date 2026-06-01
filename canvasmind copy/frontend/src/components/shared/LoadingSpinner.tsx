import React from 'react'
import { motion } from 'framer-motion'

interface Props { size?: number; color?: string; label?: string }

export function LoadingSpinner({ size = 32, color = '#6366f1', label }: Props) {
  return (
    <div className="flex flex-col items-center gap-3">
      <svg width={size} height={size} viewBox="0 0 24 24">
        <motion.circle
          cx="12" cy="12" r="10"
          stroke={color}
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
          strokeDasharray="62.83"
          animate={{ strokeDashoffset: [62.83, 0, 62.83], rotate: [0, 360] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
        />
      </svg>
      {label && <span className="text-xs text-text-secondary">{label}</span>}
    </div>
  )
}
