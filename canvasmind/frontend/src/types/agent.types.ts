export type MessageIntent =
  | 'propose'
  | 'refine'
  | 'disagree'
  | 'acknowledge'
  | 'challenge'
  | 'yield'
  | 'finalize'

export type AgentName = 'agent_a' | 'agent_b' | 'critic' | 'user'

export type AgentStatus = 'active' | 'frozen' | 'waiting' | 'typing'

export interface AgentMessage {
  id: string
  sender: AgentName
  round: number
  intent: MessageIntent
  artistic_goal: string
  region: string | null
  palette: string[] | null
  composition_notes: string
  emotional_register: string
  reasoning: string
  next_action: string
  critique: string | null
  confidence_score: number
  raw_text: string
  timestamp: string
  is_streaming: boolean
  is_complete: boolean
}

export interface AgentInfo {
  name: AgentName
  displayName: string
  fullName: string
  color: string
  bgColor: string
  borderColor: string
  glowColor: string
  role: string
}

export const AGENT_A_INFO: AgentInfo = {
  name: 'agent_a',
  displayName: 'ARIA',
  fullName: 'Artistic Reasoning and Imagination Agent',
  color: '#6366f1',
  bgColor: 'rgba(99,102,241,0.08)',
  borderColor: 'rgba(99,102,241,0.3)',
  glowColor: 'rgba(99,102,241,0.2)',
  role: 'Creative Director',
}

export const AGENT_B_INFO: AgentInfo = {
  name: 'agent_b',
  displayName: 'NEXUS',
  fullName: 'Nuanced Examination and Cross-referencing Utility System',
  color: '#ec4899',
  bgColor: 'rgba(236,72,153,0.08)',
  borderColor: 'rgba(236,72,153,0.3)',
  glowColor: 'rgba(236,72,153,0.2)',
  role: 'Creative Challenger',
}

export const CRITIC_INFO: AgentInfo = {
  name: 'critic',
  displayName: 'JUDGE',
  fullName: 'Joint Unified Directive for Generative Evaluation',
  color: '#f59e0b',
  bgColor: 'rgba(245,158,11,0.08)',
  borderColor: 'rgba(245,158,11,0.3)',
  glowColor: 'rgba(245,158,11,0.2)',
  role: 'Critic',
}
