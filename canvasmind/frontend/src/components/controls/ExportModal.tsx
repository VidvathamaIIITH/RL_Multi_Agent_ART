import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useUIStore } from '../../store/useUIStore'
import { useSession } from '../../hooks/useSession'
import { GlowButton } from '../shared/GlowButton'
import { exportService } from '../../services/export.service'

const EXPORTS = [
  { id: 'json', label: 'Full JSON', desc: 'Complete session data', icon: '{}' },
  { id: 'markdown', label: 'Markdown Report', desc: 'Human-readable report with scores', icon: '📄' },
  { id: 'transcript', label: 'Transcript', desc: 'Agent dialogue only', icon: '💬' },
  { id: 'canvas', label: 'Canvas ZIP', desc: 'All snapshots + metadata', icon: '🎨' },
  { id: 'replay', label: 'Replay JSON', desc: 'Re-playable event stream', icon: '▶' },
] as const

type ExportId = (typeof EXPORTS)[number]['id']

export function ExportModal() {
  const { isExportModalOpen, closeExportModal } = useUIStore()
  const { session } = useSession()
  const [loading, setLoading] = useState<ExportId | null>(null)

  const handle = async (id: ExportId) => {
    if (!session) return
    setLoading(id)
    try {
      if (id === 'json') await exportService.downloadJSON(session.session_id)
      else if (id === 'markdown') await exportService.downloadMarkdown(session.session_id)
      else if (id === 'transcript') await exportService.downloadTranscript(session.session_id)
      else if (id === 'canvas') await exportService.downloadCanvas(session.session_id)
      else if (id === 'replay') await exportService.downloadReplay(session.session_id)
    } catch (e) {
      console.error('Export failed:', e)
    } finally {
      setLoading(null)
    }
  }

  return (
    <AnimatePresence>
      {isExportModalOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={closeExportModal}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            onClick={e => e.stopPropagation()}
            className="bg-bg-card border border-border-primary rounded-2xl p-6 w-full max-w-md shadow-2xl"
          >
            <h2 className="text-text-primary font-semibold text-lg mb-4">Export Session</h2>

            <div className="space-y-2">
              {EXPORTS.map(exp => (
                <button
                  key={exp.id}
                  onClick={() => handle(exp.id)}
                  disabled={loading === exp.id || !session}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-xl bg-bg-tertiary hover:bg-bg-card border border-border-primary hover:border-accent-a/30 transition-all disabled:opacity-40 text-left"
                >
                  <span className="text-xl">{exp.icon}</span>
                  <div className="flex-1">
                    <p className="text-text-primary text-sm font-medium">{exp.label}</p>
                    <p className="text-text-muted text-xs">{exp.desc}</p>
                  </div>
                  {loading === exp.id && (
                    <svg className="animate-spin w-4 h-4 text-accent-a" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  )}
                </button>
              ))}
            </div>

            <div className="flex justify-end mt-4">
              <GlowButton variant="ghost" onClick={closeExportModal}>Close</GlowButton>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
