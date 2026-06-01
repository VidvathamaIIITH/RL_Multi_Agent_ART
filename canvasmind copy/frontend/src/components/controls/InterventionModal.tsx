import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useUIStore } from '../../store/useUIStore'
import { useSession } from '../../hooks/useSession'
import { GlowButton } from '../shared/GlowButton'

export function InterventionModal() {
  const { isInterventionModalOpen, closeInterventionModal } = useUIStore()
  const { intervene } = useSession()
  const [instruction, setInstruction] = useState('')
  const [target, setTarget] = useState<'both' | 'agent_a' | 'agent_b'>('both')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!instruction.trim()) return
    setLoading(true)
    try {
      await intervene(instruction, target)
      setInstruction('')
      closeInterventionModal()
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      {isInterventionModalOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={closeInterventionModal}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            onClick={e => e.stopPropagation()}
            className="bg-bg-card border border-border-primary rounded-2xl p-6 w-full max-w-lg shadow-2xl"
          >
            <h2 className="text-text-primary font-semibold text-lg mb-1">User Intervention</h2>
            <p className="text-text-muted text-xs mb-4">
              Inject a directive into the creative dialogue (Ctrl+I)
            </p>

            <div className="flex gap-2 mb-3">
              {(['agent_a', 'both', 'agent_b'] as const).map(opt => (
                <button
                  key={opt}
                  onClick={() => setTarget(opt)}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
                    target === opt
                      ? opt === 'agent_a'
                        ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300'
                        : opt === 'agent_b'
                        ? 'bg-pink-500/20 border-pink-500/40 text-pink-300'
                        : 'bg-white/10 border-white/20 text-white'
                      : 'bg-transparent border-border-primary text-text-muted hover:text-text-secondary'
                  }`}
                >
                  {opt === 'agent_a' ? 'ARIA only' : opt === 'agent_b' ? 'NEXUS only' : 'Both agents'}
                </button>
              ))}
            </div>

            <textarea
              value={instruction}
              onChange={e => setInstruction(e.target.value)}
              placeholder="Type your directive, e.g. 'Focus more on negative space' or 'Shift to a warmer palette'..."
              className="w-full h-28 bg-bg-tertiary border border-border-primary rounded-xl px-3 py-2 text-sm text-text-primary placeholder:text-text-muted resize-none focus:outline-none focus:border-accent-a"
              autoFocus
              onKeyDown={e => {
                if (e.ctrlKey && e.key === 'Enter') handleSubmit()
                if (e.key === 'Escape') closeInterventionModal()
              }}
            />

            {instruction && (
              <div className="mt-2 px-3 py-2 bg-bg-tertiary rounded-lg border border-border-primary">
                <p className="text-text-muted text-xs mb-1">Preview:</p>
                <p className="text-text-secondary text-xs italic">
                  "[USER → {target === 'both' ? 'All agents' : target.replace('_', ' ').toUpperCase()}]: {instruction}"
                </p>
              </div>
            )}

            <div className="flex justify-end gap-2 mt-4">
              <GlowButton variant="ghost" onClick={closeInterventionModal}>Cancel</GlowButton>
              <GlowButton
                variant="primary"
                onClick={handleSubmit}
                disabled={!instruction.trim()}
                loading={loading}
              >
                Inject (Ctrl+Enter)
              </GlowButton>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
