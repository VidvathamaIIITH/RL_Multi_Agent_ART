import React, { useState } from 'react'
import { useSessionStore } from '../../store/useSessionStore'
import { RoundIndicator } from '../shared/RoundIndicator'
import { ConvergenceMeter } from '../shared/ConvergenceMeter'
import { StatusIndicator } from './StatusIndicator'
import { useUIStore } from '../../store/useUIStore'

const STATUS_PILL: Record<string, { label: string; color: string }> = {
  initializing: { label: 'Initializing', color: '#3b82f6' },
  running: { label: 'Running', color: '#10b981' },
  paused: { label: 'Paused', color: '#f59e0b' },
  converged: { label: 'Converged!', color: '#a855f7' },
  completed: { label: 'Completed', color: '#8888aa' },
  error: { label: 'Error', color: '#ef4444' },
  cancelled: { label: 'Cancelled', color: '#6b7280' },
}

interface Props { onHome: () => void; onLoadSession: () => void }

export function TopBar({ onHome, onLoadSession }: Props) {
  const session = useSessionStore(s => s.session)
  const { lastApiLatency } = useSessionStore()
  const { openLoadSessionModal } = useUIStore()
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')

  const status = session?.status
  const pill = status ? STATUS_PILL[status] : null

  return (
    <div
      className="flex items-center justify-between px-5 py-2.5 border-b-2 border-border-primary shrink-0 h-12"
      style={{ backgroundColor: 'var(--bg-secondary)' }}
    >
      {/* Left: Brand + session info */}
      <div className="flex items-center gap-4">
        <button
          onClick={onHome}
          className="text-sm font-bold gradient-text-a"
          style={{ fontFamily: 'Space Grotesk, sans-serif' }}
        >
          CanvasMind
        </button>

        {session && (
          <>
            <span className="text-text-muted text-xs">|</span>
            {isEditingTitle ? (
              <input
                value={titleDraft}
                onChange={e => setTitleDraft(e.target.value)}
                onBlur={() => setIsEditingTitle(false)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === 'Escape') setIsEditingTitle(false) }}
                autoFocus
                className="bg-bg-tertiary border border-accent-a/40 rounded px-2 py-0.5 text-sm text-text-primary focus:outline-none"
              />
            ) : (
              <span
                className="text-text-primary text-sm cursor-pointer hover:text-text-secondary truncate max-w-xs"
                onDoubleClick={() => { setTitleDraft(session.title); setIsEditingTitle(true) }}
                title="Double-click to edit"
              >
                {session.title}
              </span>
            )}

            <RoundIndicator current={session.current_round} max={session.max_rounds} />

            {pill && (
              <span
                className="px-2.5 py-0.5 rounded-full text-xs font-medium"
                style={{
                  color: pill.color,
                  backgroundColor: `${pill.color}18`,
                  border: `1px solid ${pill.color}40`,
                }}
              >
                {pill.label}
              </span>
            )}

            <ConvergenceMeter score={session.convergence_score} />
          </>
        )}
      </div>

      {/* Right: latency + status dots + actions */}
      <div className="flex items-center gap-4">
        {lastApiLatency && (
          <span className="text-text-muted text-xs font-mono">{lastApiLatency}ms</span>
        )}

        <StatusIndicator />

        <button
          onClick={openLoadSessionModal}
          className="text-xs text-text-muted hover:text-text-secondary border border-border-primary rounded px-2.5 py-1 transition-colors"
        >
          Load Session
        </button>
      </div>
    </div>
  )
}
