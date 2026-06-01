import React, { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { AgentInfo, AgentStatus } from '../../types/agent.types'
import type { AgentMessage as AgentMessageType } from '../../types/agent.types'
import { AgentHeader } from './AgentHeader'
import { AgentMessage } from './AgentMessage'
import { TypingIndicator } from '../shared/TypingIndicator'
import { useSessionStore } from '../../store/useSessionStore'
import { useAgentStore } from '../../store/useAgentStore'

interface Props {
  agent: AgentInfo
  messages: AgentMessageType[]
  status: AgentStatus
  isTyping: boolean
  streamingText: string
  onFreezeToggle?: () => void
}

export function AgentPanel({ agent, messages, status, isTyping, streamingText, onFreezeToggle }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, streamingText])

  const isFrozen = status === 'frozen'

  return (
    <div
      className="flex flex-col h-full relative"
      style={{
        backgroundColor: 'var(--bg-secondary)',
        border: `1px solid ${agent.borderColor}`,
        borderRadius: '12px',
        overflow: 'hidden',
      }}
    >
      {/* Frozen overlay */}
      {isFrozen && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40 backdrop-blur-sm rounded-xl">
          <div className="text-center">
            <div className="text-4xl mb-2">❄️</div>
            <p className="text-blue-300 font-bold">AGENT FROZEN</p>
            <p className="text-text-muted text-xs mt-1">This agent will not respond</p>
          </div>
        </div>
      )}

      <AgentHeader
        agent={agent}
        status={status}
        isTyping={isTyping}
        messageCount={messages.length}
        onFreezeToggle={onFreezeToggle}
      />

      {/* Messages list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-3 py-3 space-y-1"
      >
        <AnimatePresence initial={false}>
          {messages.length === 0 && !isTyping && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-text-muted text-xs text-center py-8"
            >
              {agent.displayName} is waiting for the session to start...
            </motion.p>
          )}
          {messages.map(msg => (
            <AgentMessage key={msg.id} message={msg} agent={agent} />
          ))}
          {isTyping && streamingText && (
            <AgentMessage
              key="streaming"
              message={{
                id: 'streaming',
                sender: agent.name,
                round: 0,
                intent: 'propose',
                artistic_goal: '...',
                region: null,
                palette: null,
                composition_notes: '',
                emotional_register: '',
                reasoning: '',
                next_action: '',
                critique: null,
                confidence_score: 0.5,
                raw_text: streamingText,
                timestamp: new Date().toISOString(),
                is_streaming: true,
                is_complete: false,
              }}
              agent={agent}
              isStreaming
              streamingText={streamingText}
            />
          )}
          {isTyping && !streamingText && (
            <div className="flex justify-start">
              <div
                className="rounded-xl px-3 py-2"
                style={{ backgroundColor: agent.bgColor, border: `1px solid ${agent.borderColor}` }}
              >
                <TypingIndicator color={agent.color} />
              </div>
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
