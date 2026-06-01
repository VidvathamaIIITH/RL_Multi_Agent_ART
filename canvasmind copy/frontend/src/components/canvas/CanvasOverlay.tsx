import React from 'react'
import { useCanvasStore } from '../../store/useCanvasStore'

export function CanvasOverlay() {
  const { operations, regionMap } = useCanvasStore()
  if (operations.length === 0) return null

  const recent = operations.slice(-5)
  return (
    <div className="px-3 py-2 space-y-1">
      <p className="text-text-muted text-xs font-medium">Recent operations:</p>
      {recent.map(op => (
        <div key={op.id} className="flex items-center gap-2 text-xs">
          <span
            className="font-mono px-1.5 py-0.5 rounded text-xs"
            style={{
              backgroundColor: op.agent === 'agent_a' ? 'rgba(99,102,241,0.15)' : 'rgba(236,72,153,0.15)',
              color: op.agent === 'agent_a' ? '#818cf8' : '#f472b6',
            }}
          >
            {op.agent === 'agent_a' ? 'ARIA' : 'NEXUS'}
          </span>
          <span className="text-text-muted">{op.region}</span>
          <span className="text-text-secondary truncate">{op.description.slice(0, 60)}</span>
          {op.color_palette.slice(0, 3).map((c, i) => (
            <span key={i} className="w-3 h-3 rounded-sm inline-block border border-white/10" style={{ backgroundColor: c }} />
          ))}
        </div>
      ))}
    </div>
  )
}
