export interface CriticScore {
  compositional_coherence: number
  style_fidelity: number
  emotional_resonance: number
  originality: number
  clarity_of_next_action: number
  composite: number
}

export interface CriticEvaluation {
  id: string
  round: number
  scores: CriticScore
  reasoning: string
  contradictions_detected: string[]
  weak_ideas: string[]
  directive_agent_a: string
  directive_agent_b: string
  recommended_next_step: string
  convergence_signal: boolean
  timestamp: string
}

export const SCORE_DIMENSIONS: Array<{ key: keyof CriticScore; label: string }> = [
  { key: 'compositional_coherence', label: 'Composition' },
  { key: 'style_fidelity', label: 'Style' },
  { key: 'emotional_resonance', label: 'Emotion' },
  { key: 'originality', label: 'Originality' },
  { key: 'clarity_of_next_action', label: 'Clarity' },
]
