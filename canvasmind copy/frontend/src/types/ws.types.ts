import type { AgentMessage } from './agent.types'
import type { CriticEvaluation } from './critic.types'

export type WSEventType =
  | 'session_started'
  | 'round_started'
  | 'agent_typing_start'
  | 'agent_typing_end'
  | 'agent_token'
  | 'agent_message_complete'
  | 'critic_evaluation'
  | 'critic_token'
  | 'canvas_updated'
  | 'round_complete'
  | 'session_paused'
  | 'session_resumed'
  | 'session_converged'
  | 'session_complete'
  | 'user_intervention'
  | 'agent_frozen'
  | 'agent_unfrozen'
  | 'error'
  | 'health_ping'

export interface WSEvent {
  event_type: WSEventType
  session_id: string
  round: number | null
  agent: string | null
  data: Record<string, unknown>
  timestamp: string
}

export interface TokenEventData { token: string }
export interface MessageCompleteEventData { message: AgentMessage }
export interface CriticEventData { evaluation: CriticEvaluation }
export interface CanvasUpdatedEventData { canvas: unknown }
export interface ErrorEventData { message: string; details: string }
export interface ConvergedEventData { reason: string; plan: string }
