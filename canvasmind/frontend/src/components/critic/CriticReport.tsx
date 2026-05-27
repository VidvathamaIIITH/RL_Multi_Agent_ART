import React, { useState } from 'react'
import { motion } from 'framer-motion'
import type { CriticEvaluation } from '../../types/critic.types'

interface Props { evaluation: CriticEvaluation }

export function CriticReport({ evaluation }: Props) {
  const [showDetails, setShowDetails] = useState(false)

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="text-xs space-y-2"
    >
      <p className="text-text-secondary leading-relaxed line-clamp-2">
        {evaluation.reasoning}
      </p>

      {evaluation.contradictions_detected.length > 0 && (
        <div>
          <p className="text-red-400 text-xs font-medium mb-1">Contradictions:</p>
          <ul className="space-y-0.5">
            {evaluation.contradictions_detected.map((c, i) => (
              <li key={i} className="text-text-muted pl-2 border-l border-red-400/30">⚠ {c}</li>
            ))}
          </ul>
        </div>
      )}

      <button
        onClick={() => setShowDetails(d => !d)}
        className="text-text-muted hover:text-text-secondary transition-colors"
      >
        {showDetails ? '▲ Less' : '▼ Directives'}
      </button>

      {showDetails && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          className="space-y-2 pt-2 border-t border-border-primary"
        >
          <div>
            <span className="text-indigo-400 font-medium">ARIA directive: </span>
            <span className="text-text-secondary">{evaluation.directive_agent_a}</span>
          </div>
          <div>
            <span className="text-pink-400 font-medium">NEXUS directive: </span>
            <span className="text-text-secondary">{evaluation.directive_agent_b}</span>
          </div>
          {evaluation.weak_ideas.length > 0 && (
            <div>
              <p className="text-amber-400 font-medium mb-1">Weak ideas:</p>
              {evaluation.weak_ideas.map((w, i) => (
                <p key={i} className="text-text-muted pl-2">• {w}</p>
              ))}
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  )
}
