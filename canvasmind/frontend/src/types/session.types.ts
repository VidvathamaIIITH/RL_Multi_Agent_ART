import type { AgentMessage, AgentStatus } from './agent.types'
import type { CriticEvaluation } from './critic.types'

export type SessionStatus =
  | 'initializing'
  | 'running'
  | 'paused'
  | 'converged'
  | 'completed'
  | 'error'
  | 'cancelled'

export interface CanvasOperation {
  id: string
  operation_type: string
  agent: string
  region: string
  description: string
  color_palette: string[]
  style_instructions: string
  semantic_intent: string
  round: number
  timestamp: string
}

export interface CanvasSnapshot {
  round: number
  image_base64: string | null
  operations: CanvasOperation[]
  region_map: Record<string, string>
  annotations: unknown[]
  artistic_intent_summary: string
  timestamp: string
}

export interface CanvasState {
  canvas_id: string
  width: number
  height: number
  current_round: number
  operations_history: CanvasOperation[]
  snapshots: CanvasSnapshot[]
  region_ownership: Record<string, string>
  contested_regions: string[]
  current_image_base64: string | null
  last_updated: string
}

export interface Session {
  session_id: string
  title: string
  user_prompt: string
  status: SessionStatus
  current_round: number
  max_rounds: number
  messages: AgentMessage[]
  critic_evaluations: CriticEvaluation[]
  canvas_state: CanvasState
  agent_a_status: AgentStatus
  agent_b_status: AgentStatus
  convergence_score: number
  user_interventions: unknown[]
  finalized_plan: string | null
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export interface SessionSummary {
  session_id: string
  title: string
  user_prompt: string
  status: SessionStatus
  current_round: number
  max_rounds: number
  convergence_score: number
  created_at: string
  updated_at: string
}

export interface SessionConfig {
  max_rounds: number
  style_hint?: string
  era_hint?: string
}

export interface CreateSessionPayload {
  prompt: string
  title?: string
  max_rounds: number
  style_hint?: string
  era_hint?: string
}
