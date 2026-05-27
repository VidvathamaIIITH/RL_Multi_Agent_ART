import { create } from 'zustand'
import type { Session, SessionSummary, CreateSessionPayload } from '../types/session.types'
import type { WSEvent } from '../types/ws.types'
import { apiService } from '../services/api.service'

interface SessionState {
  session: Session | null
  sessions: SessionSummary[]
  isLoading: boolean
  error: string | null
  lastApiLatency: number | null

  createSession: (payload: CreateSessionPayload) => Promise<Session>
  startSession: (sessionId: string) => Promise<void>
  loadSession: (sessionId: string) => Promise<void>
  listSessions: () => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>
  pauseSession: () => Promise<void>
  resumeSession: () => Promise<void>
  finalizeSession: () => Promise<void>
  rollbackToRound: (round: number) => Promise<void>
  resetSession: () => Promise<void>
  updateFromWSEvent: (event: WSEvent) => void
  setSession: (session: Session) => void
  clearError: () => void
}

export const useSessionStore = create<SessionState>((set, get) => ({
  session: null,
  sessions: [],
  isLoading: false,
  error: null,
  lastApiLatency: null,

  createSession: async (payload) => {
    set({ isLoading: true, error: null })
    const start = Date.now()
    try {
      const session = await apiService.post<Session>('/api/sessions', payload)
      set({ session, isLoading: false, lastApiLatency: Date.now() - start })
      return session
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      set({ error: msg, isLoading: false })
      throw e
    }
  },

  startSession: async (sessionId) => {
    await apiService.post(`/api/sessions/${sessionId}/start`, {})
  },

  loadSession: async (sessionId) => {
    set({ isLoading: true, error: null })
    try {
      const session = await apiService.get<Session>(`/api/sessions/${sessionId}`)
      set({ session, isLoading: false })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      set({ error: msg, isLoading: false })
    }
  },

  listSessions: async () => {
    try {
      const sessions = await apiService.get<SessionSummary[]>('/api/sessions')
      set({ sessions })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      set({ error: msg })
    }
  },

  deleteSession: async (sessionId) => {
    await apiService.delete(`/api/sessions/${sessionId}`)
    set(state => ({ sessions: state.sessions.filter(s => s.session_id !== sessionId) }))
  },

  pauseSession: async () => {
    const id = get().session?.session_id
    if (!id) return
    await apiService.post(`/api/sessions/${id}/pause`, {})
  },

  resumeSession: async () => {
    const id = get().session?.session_id
    if (!id) return
    await apiService.post(`/api/sessions/${id}/resume`, {})
  },

  finalizeSession: async () => {
    const id = get().session?.session_id
    if (!id) return
    await apiService.post(`/api/sessions/${id}/finalize`, {})
  },

  rollbackToRound: async (round) => {
    const id = get().session?.session_id
    if (!id) return
    const session = await apiService.post<Session>(`/api/sessions/${id}/rollback/${round}`, {})
    set({ session })
  },

  resetSession: async () => {
    const id = get().session?.session_id
    if (!id) return
    await apiService.post(`/api/sessions/${id}/reset`, {})
  },

  updateFromWSEvent: (event) => {
    const { session } = get()
    if (!session) return

    switch (event.event_type) {
      case 'session_started':
        set(s => ({ session: s.session ? { ...s.session, status: 'running' } : null }))
        break
      case 'session_paused':
        set(s => ({ session: s.session ? { ...s.session, status: 'paused' } : null }))
        break
      case 'session_resumed':
        set(s => ({ session: s.session ? { ...s.session, status: 'running' } : null }))
        break
      case 'session_converged':
        set(s => ({
          session: s.session
            ? { ...s.session, status: 'converged', finalized_plan: (event.data as { plan: string }).plan }
            : null,
        }))
        break
      case 'session_complete':
        set(s => ({ session: s.session ? { ...s.session, status: 'completed' } : null }))
        break
      case 'round_started':
        set(s => ({
          session: s.session && event.round != null
            ? { ...s.session, current_round: event.round! }
            : s.session,
        }))
        break
      case 'agent_frozen':
        if (event.agent === 'agent_a') {
          set(s => ({ session: s.session ? { ...s.session, agent_a_status: 'frozen' } : null }))
        } else {
          set(s => ({ session: s.session ? { ...s.session, agent_b_status: 'frozen' } : null }))
        }
        break
      case 'agent_unfrozen':
        if (event.agent === 'agent_a') {
          set(s => ({ session: s.session ? { ...s.session, agent_a_status: 'active' } : null }))
        } else {
          set(s => ({ session: s.session ? { ...s.session, agent_b_status: 'active' } : null }))
        }
        break
    }
  },

  setSession: (session) => set({ session }),
  clearError: () => set({ error: null }),
}))
