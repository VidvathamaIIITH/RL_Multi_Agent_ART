import { create } from 'zustand'
import type { CriticEvaluation } from '../types/critic.types'

interface CriticState {
  evaluations: CriticEvaluation[]
  latestEvaluation: CriticEvaluation | null
  criticStreamingText: string
  criticIsTyping: boolean

  addEvaluation: (evaluation: CriticEvaluation) => void
  appendCriticToken: (token: string) => void
  finalizeCriticStreaming: () => void
  initFromSession: (evaluations: CriticEvaluation[]) => void
  reset: () => void
}

export const useCriticStore = create<CriticState>((set) => ({
  evaluations: [],
  latestEvaluation: null,
  criticStreamingText: '',
  criticIsTyping: false,

  addEvaluation: (evaluation) =>
    set(s => ({
      evaluations: [...s.evaluations, evaluation],
      latestEvaluation: evaluation,
      criticStreamingText: '',
      criticIsTyping: false,
    })),

  appendCriticToken: (token) =>
    set(s => ({
      criticStreamingText: s.criticStreamingText + token,
      criticIsTyping: true,
    })),

  finalizeCriticStreaming: () =>
    set({ criticStreamingText: '', criticIsTyping: false }),

  initFromSession: (evaluations) =>
    set({
      evaluations,
      latestEvaluation: evaluations.length > 0 ? evaluations[evaluations.length - 1] : null,
    }),

  reset: () => set({ evaluations: [], latestEvaluation: null, criticStreamingText: '', criticIsTyping: false }),
}))
