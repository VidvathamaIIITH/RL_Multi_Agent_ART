import React from 'react'
import { useUIStore } from '../../store/useUIStore'
import { GlowButton } from '../shared/GlowButton'
import { exportService } from '../../services/export.service'
import { useSessionStore } from '../../store/useSessionStore'

export function CanvasControls() {
  const { openRollbackModal } = useUIStore()
  const session = useSessionStore(s => s.session)

  const handleExportCanvas = async () => {
    if (!session) return
    try {
      await exportService.downloadCanvas(session.session_id)
    } catch (e) {
      console.error('Canvas export failed:', e)
    }
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-t border-border-primary">
      <GlowButton
        size="sm"
        variant="ghost"
        onClick={() => session && openRollbackModal(session.current_round)}
        disabled={!session || session.current_round === 0}
      >
        Rollback
      </GlowButton>
      <GlowButton size="sm" variant="ghost" onClick={handleExportCanvas} disabled={!session}>
        Export Canvas
      </GlowButton>
    </div>
  )
}
