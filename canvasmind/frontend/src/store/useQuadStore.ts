import { create } from 'zustand'
import type {
  Expertise, Persona, QuadAgentConfig, QuadAgentMeta, QuadStep, QuadCritic,
} from '../types/quad.types'

export type QuadView = 'off' | 'config' | 'live'
export type QuadStatus = 'idle' | 'running' | 'done' | 'error'

const FALLBACK_PERSONAS: Persona[] = [
  { key: 'vanguard_minimalist', name: 'The Vanguard Minimalist' },
  { key: 'neo_noir_cyberpunk', name: 'The Neo-Noir Cyberpunk' },
  { key: 'biomorphic_surrealist', name: 'The Biomorphic Surrealist' },
  { key: 'baroque_traditionalist', name: 'The Baroque Traditionalist' },
  { key: 'kinetic_futurist', name: 'The Kinetic Futurist' },
  { key: 'luminous_impressionist', name: 'The Luminous Impressionist' },
]

function defaultAgents(personas: Persona[]): QuadAgentConfig[] {
  return [0, 1, 2, 3].map((i) => ({
    name: `Agent ${i + 1}`,
    persona: personas[i % personas.length]?.key ?? 'vanguard_minimalist',
    customPrompt: '',
    useCustom: false,
    expertise: 'intermediate' as Expertise,
  }))
}

interface QuadState {
  view: QuadView
  personas: Persona[]
  levels: Expertise[]

  // global config
  prompt: string
  style: string
  rounds: number
  agents: QuadAgentConfig[]

  // live run
  status: QuadStatus
  sessionId: string | null
  meta: QuadAgentMeta[]
  activeAgentIndex: number
  round: number
  totalTurns: number
  steps: QuadStep[]              // full step history
  feeds: QuadStep[][]           // per-agent [0..3]
  currentImage: string | null
  critic: QuadCritic | null
  log: { type: string; text: string }[]

  // actions
  setView: (v: QuadView) => void
  setPersonas: (p: Persona[], levels?: Expertise[]) => void
  setPrompt: (v: string) => void
  setStyle: (v: string) => void
  setRounds: (n: number) => void
  updateAgent: (i: number, patch: Partial<QuadAgentConfig>) => void
  toggleCustom: (i: number) => void
  beginRun: () => void
  startFromSession: (meta: QuadAgentMeta[], totalTurns: number) => void
  setActive: (i: number) => void
  setRound: (r: number) => void
  pushStep: (step: QuadStep) => void
  setImageForTurn: (turn: number, image: string) => void
  setCurrentImage: (img: string | null) => void
  setCritic: (c: QuadCritic) => void
  addLog: (type: string, text: string) => void
  setStatus: (s: QuadStatus) => void
  setSessionId: (id: string | null) => void
  resetRun: () => void
}

export const useQuadStore = create<QuadState>((set) => ({
  view: 'off',
  personas: FALLBACK_PERSONAS,
  levels: ['beginner', 'intermediate', 'expert'],

  prompt: '',
  style: '',
  rounds: 1,
  agents: defaultAgents(FALLBACK_PERSONAS),

  status: 'idle',
  sessionId: null,
  meta: [],
  activeAgentIndex: -1,
  round: 0,
  totalTurns: 4,
  steps: [],
  feeds: [[], [], [], []],
  currentImage: null,
  critic: null,
  log: [],

  setView: (v) => set({ view: v }),
  setPersonas: (p, levels) =>
    set((s) => ({
      personas: p.length ? p : s.personas,
      levels: levels && levels.length ? levels : s.levels,
      agents: s.agents.map((a, i) =>
        a.persona ? a : { ...a, persona: (p[i % p.length]?.key ?? a.persona) }),
    })),
  setPrompt: (v) => set({ prompt: v }),
  setStyle: (v) => set({ style: v }),
  setRounds: (n) => set({ rounds: Math.max(1, Math.min(6, Math.round(n) || 1)) }),
  updateAgent: (i, patch) =>
    set((s) => ({ agents: s.agents.map((a, idx) => (idx === i ? { ...a, ...patch } : a)) })),
  toggleCustom: (i) =>
    set((s) => ({ agents: s.agents.map((a, idx) => (idx === i ? { ...a, useCustom: !a.useCustom } : a)) })),

  beginRun: () =>
    set({
      view: 'live', status: 'running', sessionId: null, meta: [], activeAgentIndex: -1,
      round: 0, steps: [], feeds: [[], [], [], []], currentImage: null, critic: null, log: [],
      totalTurns: 4,
    }),
  startFromSession: (meta, totalTurns) => set({ meta, totalTurns }),
  setActive: (i) => set({ activeAgentIndex: i }),
  setRound: (r) => set({ round: r }),
  pushStep: (step) =>
    set((s) => {
      const feeds = s.feeds.map((f) => f.slice())
      if (step.agentIdx >= 0 && step.agentIdx < 4) feeds[step.agentIdx].push(step)
      return { steps: [...s.steps, step], feeds }
    }),
  setImageForTurn: (turn, image) =>
    set((s) => ({
      steps: s.steps.map((st) => (st.turn === turn ? { ...st, image } : st)),
      currentImage: image,
    })),
  setCurrentImage: (img) => set({ currentImage: img }),
  setCritic: (c) => set({ critic: c }),
  addLog: (type, text) => set((s) => ({ log: [...s.log.slice(-80), { type, text }] })),
  setStatus: (status) => set({ status }),
  setSessionId: (id) => set({ sessionId: id }),
  resetRun: () =>
    set({
      status: 'idle', sessionId: null, meta: [], activeAgentIndex: -1, round: 0,
      steps: [], feeds: [[], [], [], []], currentImage: null, critic: null, log: [],
    }),
}))
