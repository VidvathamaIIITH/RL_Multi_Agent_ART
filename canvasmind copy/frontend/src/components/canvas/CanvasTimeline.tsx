import React from 'react'
import { useCanvasStore } from '../../store/useCanvasStore'

export function CanvasTimeline() {
  const { snapshots, currentSnapshotRound, viewSnapshot } = useCanvasStore()

  if (snapshots.length === 0) {
    return (
      <div className="text-text-muted text-xs text-center py-2">
        No snapshots yet
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1 px-3 py-1.5 overflow-x-auto">
      {snapshots.map(snap => (
        <button
          key={snap.round}
          onClick={() => viewSnapshot(snap.round)}
          className={`
            flex-shrink-0 w-8 h-8 rounded-lg text-xs font-mono font-medium transition-all
            ${currentSnapshotRound === snap.round
              ? 'bg-accent-a text-white shadow-[0_0_10px_rgba(99,102,241,0.4)]'
              : 'bg-bg-tertiary text-text-muted hover:text-text-primary hover:bg-bg-card border border-border-primary'
            }
          `}
        >
          {snap.round}
        </button>
      ))}
    </div>
  )
}
