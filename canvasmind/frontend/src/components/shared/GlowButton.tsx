import React from 'react'
import { motion } from 'framer-motion'
import type { GlowButtonProps } from '../../types/ui.types'

const VARIANTS = {
  primary: 'bg-accent-a hover:bg-indigo-500 text-white border border-indigo-500/30 hover:shadow-[0_0_20px_rgba(99,102,241,0.4)]',
  secondary: 'bg-accent-b hover:bg-pink-500 text-white border border-pink-500/30 hover:shadow-[0_0_20px_rgba(236,72,153,0.4)]',
  danger: 'bg-red-600 hover:bg-red-500 text-white border border-red-500/30 hover:shadow-[0_0_20px_rgba(239,68,68,0.4)]',
  success: 'bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-500/30 hover:shadow-[0_0_20px_rgba(16,185,129,0.4)]',
  ghost: 'bg-transparent hover:bg-white/5 text-text-secondary hover:text-text-primary border border-border-primary',
}

const SIZES = {
  sm: 'px-3 py-1.5 text-xs rounded-md',
  md: 'px-4 py-2 text-sm rounded-lg',
  lg: 'px-6 py-3 text-base rounded-xl',
}

export function GlowButton({ onClick, disabled, variant = 'primary', size = 'md', children, className = '', loading, title }: GlowButtonProps) {
  return (
    <motion.button
      whileHover={{ scale: disabled ? 1 : 1.02 }}
      whileTap={{ scale: disabled ? 1 : 0.97 }}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      className={`
        inline-flex items-center gap-2 font-medium transition-all duration-200
        disabled:opacity-40 disabled:cursor-not-allowed
        ${VARIANTS[variant]} ${SIZES[size]} ${className}
      `}
    >
      {loading && (
        <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </motion.button>
  )
}
