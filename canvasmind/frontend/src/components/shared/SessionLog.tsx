import React, { useEffect, useRef } from 'react'
import { useUIStore } from '../../store/useUIStore'
import type { LogEntry } from '../../types/ui.types'

const TYPE_STYLES: Record<LogEntry['type'], string> = {
  info: 'text-text-secondary',
  success: 'text-emerald-400',
  warning: 'text-amber-400',
  error: 'text-red-400',
  agent_a: 'text-indigo-400',
  agent_b: 'text-pink-400',
  critic: 'text-amber-300',
}

const TYPE_PREFIX: Record<LogEntry['type'], string> = {
  info: '○',
  success: '✓',
  warning: '⚠',
  error: '✗',
  agent_a: 'A',
  agent_b: 'B',
  critic: 'C',
}

export function SessionLog() {
  const { sessionLog } = useUIStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [sessionLog.length])

  return (
    <div className="h-full overflow-y-auto font-mono text-xs px-3 py-2 space-y-0.5">
      {sessionLog.length === 0 && (
        <p className="text-text-muted text-center py-4">Session log will appear here...</p>
      )}
      {sessionLog.map(entry => (
        <div key={entry.id} className="flex items-start gap-2 hover:bg-white/2 rounded px-1">
          <span className="text-text-muted text-xs shrink-0 w-20">
            {new Date(entry.timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <span className={`shrink-0 w-4 ${TYPE_STYLES[entry.type]}`}>{TYPE_PREFIX[entry.type]}</span>
          <span className={`${TYPE_STYLES[entry.type]} break-all`}>{entry.message}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
