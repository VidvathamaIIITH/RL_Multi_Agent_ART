import { create } from 'zustand'
import type { AgentMessage, AgentStatus } from '../types/agent.types'
import { apiService } from '../services/api.service'

interface AgentState {
  agentAMessages: AgentMessage[]
  agentBMessages: AgentMessage[]
  agentAStatus: AgentStatus
  agentBStatus: AgentStatus
  agentAStreamingText: string
  agentBStreamingText: string
  agentAIsTyping: boolean
  agentBIsTyping: boolean
  criticStreamingText: string
  criticIsTyping: boolean

  addMessage: (message: AgentMessage) => void
  appendToken: (agent: 'agent_a' | 'agent_b' | 'critic', token: string) => void
  finalizeStreaming: (agent: 'agent_a' | 'agent_b' | 'critic') => void
  setAgentStatus: (agent: 'agent_a' | 'agent_b', status: AgentStatus) => void
  setTyping: (agent: 'agent_a' | 'agent_b' | 'critic', typing: boolean) => void
  freezeAgent: (agent: 'agent_a' | 'agent_b', sessionId: string) => Promise<void>
  unfreezeAgent: (agent: 'agent_a' | 'agent_b', sessionId: string) => Promise<void>
  clearMessages: () => void
  initFromSession: (messages: AgentMessage[], aStatus: AgentStatus, bStatus: AgentStatus) => void
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agentAMessages: [],
  agentBMessages: [],
  agentAStatus: 'waiting',
  agentBStatus: 'waiting',
  agentAStreamingText: '',
  agentBStreamingText: '',
  agentAIsTyping: false,
  agentBIsTyping: false,
  criticStreamingText: '',
  criticIsTyping: false,

  addMessage: (message) => {
    if (message.sender === 'agent_a') {
      set(s => ({ agentAMessages: [...s.agentAMessages, message], agentAStreamingText: '' }))
    } else if (message.sender === 'agent_b') {
      set(s => ({ agentBMessages: [...s.agentBMessages, message], agentBStreamingText: '' }))
    }
  },

  appendToken: (agent, token) => {
    if (agent === 'agent_a') {
      set(s => ({ agentAStreamingText: s.agentAStreamingText + token }))
    } else if (agent === 'agent_b') {
      set(s => ({ agentBStreamingText: s.agentBStreamingText + token }))
    } else if (agent === 'critic') {
      set(s => ({ criticStreamingText: s.criticStreamingText + token }))
    }
  },

  finalizeStreaming: (agent) => {
    if (agent === 'agent_a') {
      set({ agentAStreamingText: '', agentAIsTyping: false })
    } else if (agent === 'agent_b') {
      set({ agentBStreamingText: '', agentBIsTyping: false })
    } else if (agent === 'critic') {
      set({ criticStreamingText: '', criticIsTyping: false })
    }
  },

  setAgentStatus: (agent, status) => {
    if (agent === 'agent_a') set({ agentAStatus: status })
    else set({ agentBStatus: status })
  },

  setTyping: (agent, typing) => {
    if (agent === 'agent_a') set({ agentAIsTyping: typing })
    else if (agent === 'agent_b') set({ agentBIsTyping: typing })
    else set({ criticIsTyping: typing })
  },

  freezeAgent: async (agent, sessionId) => {
    await apiService.post(`/api/sessions/${sessionId}/freeze/${agent}`, {})
  },

  unfreezeAgent: async (agent, sessionId) => {
    await apiService.post(`/api/sessions/${sessionId}/unfreeze/${agent}`, {})
  },

  clearMessages: () => set({
    agentAMessages: [],
    agentBMessages: [],
    agentAStreamingText: '',
    agentBStreamingText: '',
    criticStreamingText: '',
  }),

  initFromSession: (messages, aStatus, bStatus) => {
    const aMessages = messages.filter(m => m.sender === 'agent_a')
    const bMessages = messages.filter(m => m.sender === 'agent_b')
    set({
      agentAMessages: aMessages,
      agentBMessages: bMessages,
      agentAStatus: aStatus,
      agentBStatus: bStatus,
    })
  },
}))
