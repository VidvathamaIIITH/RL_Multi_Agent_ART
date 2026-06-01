import React, { useState } from 'react'
import { motion } from 'framer-motion'
import type { AgentMessage as AgentMessageType } from '../../types/agent.types'
import type { AgentInfo } from '../../types/agent.types'
import { IntentBadge } from './IntentBadge'

interface Props {
  message: AgentMessageType
  agent: AgentInfo
  isStreaming?: boolean
  streamingText?: string
}

export function AgentMessage({ message, agent, isStreaming, streamingText }: Props) {
  const [expanded, setExpanded] = useState(false)
  const displayText = isStreaming ? (streamingText || '') : message.raw_text

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="rounded-xl p-3 mb-2"
      style={{ backgroundColor: agent.bgColor, border: `1px solid ${agent.borderColor}` }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <IntentBadge intent={message.intent} />
          <span className="text-xs text-text-muted font-mono">R{message.round}</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Confidence bar */}
          <div className="flex items-center gap-1">
            <div className="w-12 h-1 bg-bg-tertiary rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${message.confidence_score * 100}%`, backgroundColor: agent.color }}
              />
            </div>
            <span className="text-xs text-text-muted font-mono">
              {Math.round(message.confidence_score * 100)}%
            </span>
          </div>
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-text-muted hover:text-text-secondary text-xs transition-colors"
          >
            {expanded ? '▲' : '▼'}
          </button>
        </div>
      </div>

      {/* Artistic goal */}
      <p className="text-sm font-medium" style={{ color: agent.color }}>
        {message.artistic_goal}
      </p>

      {/* Next action */}
      <p className="text-xs text-text-secondary mt-1">
        → {message.next_action}
      </p>

      {/* Streaming indicator */}
      {isStreaming && (
        <div className="mt-2 text-xs text-text-muted font-mono leading-relaxed max-h-20 overflow-hidden">
          {displayText.slice(-200)}
          <span className="animate-pulse">▋</span>
        </div>
      )}

      {/* Palette swatches */}
      {message.palette && message.palette.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2">
          {message.palette.map((hex, i) => (
            <div
              key={i}
              className="w-4 h-4 rounded-sm border border-white/10"
              style={{ backgroundColor: hex }}
              title={hex}
            />
          ))}
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="mt-3 space-y-2 border-t border-white/5 pt-3"
        >
          <Detail label="Composition" value={message.composition_notes} />
          <Detail label="Emotion" value={message.emotional_register} />
          <Detail label="Reasoning" value={message.reasoning} />
          {message.critique && <Detail label="Critique" value={message.critique} />}
          {message.region && (
            <div className="flex gap-2">
              <span className="text-text-muted text-xs w-20 shrink-0">Region:</span>
              <span className="text-xs font-mono text-text-secondary bg-bg-tertiary px-2 py-0.5 rounded">
                {message.region}
              </span>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="text-text-muted text-xs w-20 shrink-0">{label}:</span>
      <p className="text-xs text-text-secondary leading-relaxed">{value}</p>
    </div>
  )
}
