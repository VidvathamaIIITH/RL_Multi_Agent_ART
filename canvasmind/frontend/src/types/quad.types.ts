// Types for the Quad-Agent Sequential Pipeline (advanced view).

export type Expertise = 'beginner' | 'intermediate' | 'expert'

export interface Persona {
  key: string
  name: string
  blurb?: string
}

export interface QuadAgentConfig {
  name: string
  persona: string          // preset key (ignored when useCustom + customPrompt)
  customPrompt: string
  useCustom: boolean
  expertise: Expertise
}

export interface QuadAgentMeta {
  index: number
  name: string
  persona_name: string
  expertise: string
  custom?: boolean
}

export interface QuadStep {
  turn: number
  agentIdx: number
  name: string
  personaName?: string
  object: string
  sees?: string
  where?: string
  reasoning?: string
  palette?: string[]
  confidence?: number
  image?: string
  label?: string
}

export interface QuadCritic {
  scores?: Record<string, number>
  reasoning?: string
  highlights?: string[]
  final_summary?: string
}

// SSE event as emitted by the backend (single-file and modular share this shape).
export interface QuadEvent {
  type: string
  turn?: number
  total?: number
  round?: number
  agent_idx?: number
  name?: string
  persona_name?: string
  expertise?: string
  object?: string
  image?: string
  label?: string
  message?: {
    sees_on_canvas?: string
    new_object?: string
    where?: string
    palette?: string[]
    reasoning?: string
    confidence_score?: number
  }
  agents?: QuadAgentMeta[]
  evaluation?: QuadCritic
  prompt?: string
  style?: string
  rounds?: number
  total_turns?: number
  images?: boolean
  elapsed?: number
  message_text?: string
  [key: string]: unknown
}
