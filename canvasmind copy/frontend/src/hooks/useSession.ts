import { useCallback } from 'react'
import { useSessionStore } from '../store/useSessionStore'
import { useAgentStore } from '../store/useAgentStore'
import { useCriticStore } from '../store/useCriticStore'
import { useCanvasStore } from '../store/useCanvasStore'
import { useUIStore } from '../store/useUIStore'
import { apiService } from '../services/api.service'

export function useSession() {
  const store = useSessionStore()
  const { addLogEntry } = useUIStore()

  const intervene = useCallback(async (instruction: string, targetAgent = 'both') => {
    const id = store.session?.session_id
    if (!id) return
    try {
      await apiService.post(`/api/sessions/${id}/intervene`, { instruction, target_agent: targetAgent })
      addLogEntry('info', `Intervention: ${instruction.slice(0, 60)}`)
    } catch (e) {
      addLogEntry('error', `Intervention failed: ${e}`)
    }
  }, [store.session?.session_id])

  const regenerateRound = useCallback(async () => {
    const id = store.session?.session_id
    if (!id) return
    try {
      await apiService.post(`/api/sessions/${id}/regenerate_round`, {})
      addLogEntry('info', 'Regenerating current round')
    } catch (e) {
      addLogEntry('error', `Regenerate failed: ${e}`)
    }
  }, [store.session?.session_id])

  return {
    session: store.session,
    isLoading: store.isLoading,
    error: store.error,
    createSession: store.createSession,
    startSession: store.startSession,
    loadSession: store.loadSession,
    pauseSession: store.pauseSession,
    resumeSession: store.resumeSession,
    finalizeSession: store.finalizeSession,
    rollbackToRound: store.rollbackToRound,
    resetSession: store.resetSession,
    intervene,
    regenerateRound,
  }
}
