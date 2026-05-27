import React from 'react'
import { useAgentStore } from '../../store/useAgentStore'
import { useSessionStore } from '../../store/useSessionStore'

export function FreezeAgentToggle() {
  const session = useSessionStore(s => s.session)
  const { freezeAgent, unfreezeAgent, agentAStatus, agentBStatus } = useAgentStore()

  if (!session) return null

  return (
    <div className="flex flex-col gap-2">
      <p className="text-text-muted text-xs font-medium uppercase tracking-wider mb-1">Agents</p>
      <button
        onClick={() => {
          if (agentAStatus === 'frozen') unfreezeAgent('agent_a', session.session_id)
          else freezeAgent('agent_a', session.session_id)
        }}
        className={`
          w-full py-1.5 rounded-lg text-xs font-medium transition-colors border
          ${agentAStatus === 'frozen'
            ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
            : 'bg-indigo-500/10 border-indigo-500/20 text-indigo-400 hover:bg-indigo-500/20'
          }
        `}
      >
        {agentAStatus === 'frozen' ? '❄ Unfreeze ARIA' : '❄ Freeze ARIA'}
      </button>
      <button
        onClick={() => {
          if (agentBStatus === 'frozen') unfreezeAgent('agent_b', session.session_id)
          else freezeAgent('agent_b', session.session_id)
        }}
        className={`
          w-full py-1.5 rounded-lg text-xs font-medium transition-colors border
          ${agentBStatus === 'frozen'
            ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
            : 'bg-pink-500/10 border-pink-500/20 text-pink-400 hover:bg-pink-500/20'
          }
        `}
      >
        {agentBStatus === 'frozen' ? '❄ Unfreeze NEXUS' : '❄ Freeze NEXUS'}
      </button>
    </div>
  )
}
