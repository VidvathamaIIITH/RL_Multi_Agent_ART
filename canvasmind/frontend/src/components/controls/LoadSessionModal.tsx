import React, { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useUIStore } from '../../store/useUIStore'
import { useSessionStore } from '../../store/useSessionStore'
import { GlowButton } from '../shared/GlowButton'
import type { SessionSummary } from '../../types/session.types'

const STATUS_COLORS: Record<string, string> = {
  running: '#10b981',
  paused: '#f59e0b',
  converged: '#6366f1',
  completed: '#8888aa',
  error: '#ef4444',
  initializing: '#3b82f6',
  cancelled: '#6b7280',
}

export function LoadSessionModal() {
  const { isLoadSessionModalOpen, closeLoadSessionModal } = useUIStore()
  const { sessions, listSessions, loadSession } = useSessionStore()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isLoadSessionModalOpen) listSessions()
  }, [isLoadSessionModalOpen])

  const handleLoad = async (id: string) => {
    setLoading(true)
    try {
      await loadSession(id)
      closeLoadSessionModal()
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      {isLoadSessionModalOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={closeLoadSessionModal}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            onClick={e => e.stopPropagation()}
            className="bg-bg-card border border-border-primary rounded-2xl p-6 w-full max-w-xl shadow-2xl"
          >
            <h2 className="text-text-primary font-semibold text-lg mb-4">Load Session</h2>

            {sessions.length === 0 ? (
              <p className="text-text-muted text-sm text-center py-8">No saved sessions found.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {sessions.map(s => (
                  <button
                    key={s.session_id}
                    onClick={() => handleLoad(s.session_id)}
                    disabled={loading}
                    className="w-full flex items-start gap-3 px-4 py-3 rounded-xl bg-bg-tertiary hover:bg-bg-card border border-border-primary hover:border-accent-a/30 transition-all text-left"
                  >
                    <span
                      className="mt-1 w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: STATUS_COLORS[s.status] || '#6b7280' }}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-text-primary text-sm font-medium truncate">{s.title}</p>
                      <p className="text-text-muted text-xs truncate">{s.user_prompt}</p>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs text-text-muted">R{s.current_round}/{s.max_rounds}</span>
                        <span className="text-xs text-text-muted">{(s.convergence_score * 100).toFixed(0)}% converged</span>
                        <span className="text-xs text-text-muted">{new Date(s.updated_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <span className="text-xs" style={{ color: STATUS_COLORS[s.status] }}>{s.status}</span>
                  </button>
                ))}
              </div>
            )}

            <div className="flex justify-end mt-4">
              <GlowButton variant="ghost" onClick={closeLoadSessionModal}>Close</GlowButton>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
