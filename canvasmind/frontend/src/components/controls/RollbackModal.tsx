import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useUIStore } from '../../store/useUIStore'
import { useSession } from '../../hooks/useSession'
import { GlowButton } from '../shared/GlowButton'

export function RollbackModal() {
  const { isRollbackModalOpen, selectedRoundForRollback, closeRollbackModal } = useUIStore()
  const { rollbackToRound, session } = useSession()
  const [loading, setLoading] = useState(false)
  const [targetRound, setTargetRound] = useState<number>(selectedRoundForRollback || 1)

  const maxRound = session?.current_round || 1

  const handleRollback = async () => {
    setLoading(true)
    try {
      await rollbackToRound(targetRound)
      closeRollbackModal()
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      {isRollbackModalOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={closeRollbackModal}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            onClick={e => e.stopPropagation()}
            className="bg-bg-card border border-border-primary rounded-2xl p-6 w-full max-w-sm shadow-2xl"
          >
            <h2 className="text-text-primary font-semibold text-lg mb-1">Rollback Session</h2>
            <p className="text-amber-400 text-xs mb-4">
              This will discard all rounds after the selected round. This cannot be undone.
            </p>

            <div className="mb-4">
              <label className="text-text-secondary text-sm block mb-2">
                Rollback to end of round:
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0}
                  max={maxRound}
                  value={targetRound}
                  onChange={e => setTargetRound(Number(e.target.value))}
                  className="flex-1"
                />
                <span className="text-text-primary font-mono text-lg w-8 text-center">{targetRound}</span>
              </div>
            </div>

            <p className="text-text-muted text-xs mb-4">
              Rounds {targetRound + 1}–{maxRound} will be removed.
            </p>

            <div className="flex justify-end gap-2">
              <GlowButton variant="ghost" onClick={closeRollbackModal}>Cancel</GlowButton>
              <GlowButton variant="danger" onClick={handleRollback} loading={loading}>
                Rollback to R{targetRound}
              </GlowButton>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
