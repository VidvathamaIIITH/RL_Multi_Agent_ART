import React from 'react'
import { useCriticStore } from '../../store/useCriticStore'
import { useAgentStore } from '../../store/useAgentStore'
import { ScoreGauge } from './ScoreGauge'
import { ScoreHistory } from './ScoreHistory'
import { NextActionCard } from './NextActionCard'
import { CriticReport } from './CriticReport'
import { TypingIndicator } from '../shared/TypingIndicator'
import { SCORE_DIMENSIONS } from '../../types/critic.types'

export function CriticPanel() {
  const { evaluations, latestEvaluation, criticIsTyping, criticStreamingText } = useCriticStore()

  return (
    <div
      className="flex flex-col h-full panel-critic rounded-xl overflow-hidden"
      style={{ backgroundColor: 'var(--bg-secondary)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-amber-500/20">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-500" />
          <span className="gradient-text-critic font-bold text-sm">JUDGE</span>
          <span className="text-text-muted text-xs">Critic Agent</span>
        </div>
        {criticIsTyping && (
          <div className="flex items-center gap-2">
            <TypingIndicator color="#f59e0b" />
            <span className="text-amber-400 text-xs">Evaluating...</span>
          </div>
        )}
        {latestEvaluation && (
          <span className="text-xs font-mono text-amber-400">
            R{latestEvaluation.round} | {latestEvaluation.scores.composite.toFixed(1)}/10
          </span>
        )}
      </div>

      <div className="flex-1 overflow-hidden grid grid-cols-3 divide-x divide-border-primary">
        {/* Score gauges */}
        <div className="p-3 flex flex-col gap-3 overflow-y-auto">
          {latestEvaluation ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                {SCORE_DIMENSIONS.map(dim => (
                  <ScoreGauge
                    key={dim.key}
                    score={latestEvaluation.scores[dim.key] as number}
                    label={dim.label}
                    size={64}
                  />
                ))}
              </div>
              <div className="flex items-center justify-center">
                <ScoreGauge
                  score={latestEvaluation.scores.composite}
                  label="COMPOSITE"
                  size={80}
                />
              </div>
            </>
          ) : (
            <div className="text-text-muted text-xs text-center py-4">
              Awaiting first evaluation...
            </div>
          )}
          <ScoreHistory evaluations={evaluations} />
        </div>

        {/* Reasoning & report */}
        <div className="p-3 overflow-y-auto">
          {criticIsTyping && criticStreamingText && (
            <div className="text-xs text-amber-300/70 font-mono leading-relaxed mb-3 max-h-32 overflow-hidden">
              {criticStreamingText.slice(-400)}
              <span className="animate-pulse">▋</span>
            </div>
          )}
          {latestEvaluation && !criticIsTyping && (
            <CriticReport evaluation={latestEvaluation} />
          )}
        </div>

        {/* Next action */}
        <div className="p-3 overflow-y-auto">
          {latestEvaluation && (
            <NextActionCard
              action={latestEvaluation.recommended_next_step}
              convergenceSignal={latestEvaluation.convergence_signal}
            />
          )}
        </div>
      </div>
    </div>
  )
}
