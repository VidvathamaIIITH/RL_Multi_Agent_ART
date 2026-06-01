import React from 'react'
import { useSession } from '../../hooks/useSession'
import { useUIStore } from '../../store/useUIStore'
import { GlowButton } from '../shared/GlowButton'

export function SessionControls() {
  const { session, pauseSession, resumeSession, finalizeSession, resetSession, isLoading } = useSession()
  const { openInterventionModal, openRollbackModal, openExportModal } = useUIStore()

  const status = session?.status

  return (
    <div className="flex flex-col gap-2">
      <p className="text-text-muted text-xs font-medium uppercase tracking-wider mb-1">Session</p>

      {status === 'running' && (
        <GlowButton variant="ghost" size="sm" onClick={pauseSession} loading={isLoading} className="w-full justify-center">
          ⏸ Pause
        </GlowButton>
      )}
      {status === 'paused' && (
        <GlowButton variant="success" size="sm" onClick={resumeSession} loading={isLoading} className="w-full justify-center">
          ▶ Resume
        </GlowButton>
      )}
      {(status === 'running' || status === 'paused') && (
        <GlowButton variant="primary" size="sm" onClick={finalizeSession} className="w-full justify-center">
          ✓ Finalize
        </GlowButton>
      )}

      <GlowButton
        variant="ghost"
        size="sm"
        onClick={openInterventionModal}
        disabled={!session || (status !== 'running' && status !== 'paused')}
        className="w-full justify-center"
        title="Ctrl+I"
      >
        ✏ Intervene
      </GlowButton>

      <GlowButton
        variant="ghost"
        size="sm"
        onClick={() => session && openRollbackModal(session.current_round)}
        disabled={!session || !session.current_round}
        className="w-full justify-center"
      >
        ↩ Rollback
      </GlowButton>

      <GlowButton
        variant="ghost"
        size="sm"
        onClick={openExportModal}
        disabled={!session}
        className="w-full justify-center"
        title="Ctrl+E"
      >
        ↓ Export
      </GlowButton>

      {session && (
        <GlowButton variant="danger" size="sm" onClick={resetSession} className="w-full justify-center mt-2">
          ⟳ Reset
        </GlowButton>
      )}
    </div>
  )
}
