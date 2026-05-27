import React from 'react'
import { motion } from 'framer-motion'

interface Props { label: string; className?: string }

export function AnimatedBadge({ label, className = '' }: Props) {
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${className}`}
    >
      {label}
    </motion.span>
  )
}
