import React from 'react'
import { motion } from 'framer-motion'
import { AgentPanel } from '../agents/AgentPanel'
import { CanvasPanel } from '../canvas/CanvasPanel'
import { CriticPanel } from '../critic/CriticPanel'
import { SidePanel } from './SidePanel'
import { SessionLog } from '../shared/SessionLog'
import { InterventionModal } from '../controls/InterventionModal'
import { RollbackModal } from '../controls/RollbackModal'
import { ExportModal } from '../controls/ExportModal'
import { LoadSessionModal } from '../controls/LoadSessionModal'
import { useAgentStore } from '../../store/useAgentStore'
import { useSessionStore } from '../../store/useSessionStore'
import { AGENT_A_INFO, AGENT_B_INFO } from '../../types/agent.types'

export function AppLayout() {
  const {
    agentAMessages, agentBMessages,
    agentAStatus, agentBStatus,
    agentAIsTyping, agentBIsTyping,
    agentAStreamingText, agentBStreamingText,
    freezeAgent, unfreezeAgent,
  } = useAgentStore()
  const session = useSessionStore(s => s.session)

  const handleFreezeA = () => {
    if (!session) return
    if (agentAStatus === 'frozen') unfreezeAgent('agent_a', session.session_id)
    else freezeAgent('agent_a', session.session_id)
  }

  const handleFreezeB = () => {
    if (!session) return
    if (agentBStatus === 'frozen') unfreezeAgent('agent_b', session.session_id)
    else freezeAgent('agent_b', session.session_id)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Main 3-column + side panel */}
      <div className="flex flex-1 overflow-hidden min-h-0 pt-1">
        {/* Agent A panel */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="w-72 xl:w-80 shrink-0 p-2"
        >
          <AgentPanel
            agent={AGENT_A_INFO}
            messages={agentAMessages}
            status={agentAStatus}
            isTyping={agentAIsTyping}
            streamingText={agentAStreamingText}
            onFreezeToggle={handleFreezeA}
          />
        </motion.div>

        {/* Canvas panel — center, flex-1 */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="flex-1 min-w-0 p-2 flex flex-col gap-2"
        >
          <div className="flex-1 min-h-0">
            <CanvasPanel />
          </div>
          {/* Critic panel below canvas */}
          <div className="h-64 shrink-0">
            <CriticPanel />
          </div>
        </motion.div>

        {/* Agent B panel */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
          className="w-72 xl:w-80 shrink-0 p-2"
        >
          <AgentPanel
            agent={AGENT_B_INFO}
            messages={agentBMessages}
            status={agentBStatus}
            isTyping={agentBIsTyping}
            streamingText={agentBStreamingText}
            onFreezeToggle={handleFreezeB}
          />
        </motion.div>

        {/* Side panel */}
        <SidePanel />
      </div>

      {/* Session log — bottom strip */}
      <div
        className="h-28 shrink-0 border-t-2 border-border-primary"
        style={{ backgroundColor: 'var(--bg-secondary)' }}
      >
        <SessionLog />
      </div>

      {/* Modals */}
      <InterventionModal />
      <RollbackModal />
      <ExportModal />
      <LoadSessionModal />
    </div>
  )
}
