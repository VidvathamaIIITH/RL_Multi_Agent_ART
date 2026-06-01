import React from 'react'
import type { AgentInfo } from '../../types/agent.types'
import type { AgentStatus } from '../../types/agent.types'
import { TypingIndicator } from '../shared/TypingIndicator'

interface Props {
  agent: AgentInfo
  status: AgentStatus
  isTyping: boolean
  messageCount: number
  onFreezeToggle?: () => void
}

const STATUS_BADGE: Record<AgentStatus, { label: string; color: string }> = {
  active: { label: 'ACTIVE', color: '#10b981' },
  frozen: { label: 'FROZEN', color: '#6b7280' },
  waiting: { label: 'WAITING', color: '#f59e0b' },
  typing: { label: 'TYPING', color: '#6366f1' },
}

export function AgentHeader({ agent, status, isTyping, messageCount, onFreezeToggle }: Props) {
  const badge = STATUS_BADGE[isTyping ? 'typing' : status]

  return (
    <div
      className="flex items-center justify-between px-4 py-3 border-b"
      style={{ borderColor: agent.borderColor }}
    >
      <div className="flex items-center gap-3">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold"
          style={{ backgroundColor: agent.bgColor, color: agent.color }}
        >
          {agent.displayName[0]}
        </div>
        <div>
          <p className="font-semibold text-sm" style={{ color: agent.color }}>
            {agent.displayName}
          </p>
          <p className="text-text-muted text-xs">{agent.role}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {isTyping && <TypingIndicator color={agent.color} />}
        <span
          className="text-xs font-mono px-2 py-0.5 rounded-full"
          style={{ color: badge.color, backgroundColor: `${badge.color}18`, border: `1px solid ${badge.color}40` }}
        >
          {badge.label}
        </span>
        <span className="text-text-muted text-xs">{messageCount} msgs</span>
        {onFreezeToggle && (
          <button
            onClick={onFreezeToggle}
            title={status === 'frozen' ? 'Unfreeze agent' : 'Freeze agent'}
            className="text-xs text-text-muted hover:text-text-primary transition-colors px-2 py-1 rounded border border-border-primary hover:border-text-muted"
          >
            {status === 'frozen' ? '❄ Frozen' : '❄'}
          </button>
        )}
      </div>
    </div>
  )
}
