import React from 'react'
import { motion } from 'framer-motion'

interface Props { action: string; convergenceSignal: boolean }

export function NextActionCard({ action, convergenceSignal }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="rounded-lg p-3 border"
      style={{
        backgroundColor: convergenceSignal ? 'rgba(16,185,129,0.08)' : 'rgba(245,158,11,0.08)',
        borderColor: convergenceSignal ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)',
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-medium" style={{ color: convergenceSignal ? '#10b981' : '#f59e0b' }}>
          {convergenceSignal ? '✓ CONVERGENCE NEAR' : '→ NEXT ACTION'}
        </span>
      </div>
      <p className="text-xs text-text-secondary leading-relaxed">{action}</p>
    </motion.div>
  )
}
