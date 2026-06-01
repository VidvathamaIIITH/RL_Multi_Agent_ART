import React from 'react'
import { useUIStore } from '../../store/useUIStore'
import { CanvasViewer } from './CanvasViewer'
import { CanvasTimeline } from './CanvasTimeline'
import { CanvasOverlay } from './CanvasOverlay'
import { CanvasControls } from './CanvasControls'
import type { ActiveTab } from '../../types/ui.types'

const TABS: { id: ActiveTab; label: string }[] = [
  { id: 'canvas', label: 'Canvas' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'operations', label: 'Operations' },
]

export function CanvasPanel() {
  const { activeTab, setActiveTab } = useUIStore()

  return (
    <div
      className="flex flex-col h-full panel-canvas rounded-xl overflow-hidden"
      style={{ backgroundColor: 'var(--bg-secondary)' }}
    >
      {/* Tabs */}
      <div className="flex border-b border-border-primary">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              px-4 py-2.5 text-xs font-medium transition-colors
              ${activeTab === tab.id
                ? 'text-text-primary border-b-2 border-accent-a'
                : 'text-text-muted hover:text-text-secondary'
              }
            `}
          >
            {tab.label}
          </button>
        ))}
        <div className="ml-auto px-3 py-2">
          <span className="text-text-muted text-xs">Shared Canvas</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {activeTab === 'canvas' && <CanvasViewer />}
        {activeTab === 'timeline' && (
          <div className="flex-1 overflow-y-auto p-3">
            <p className="text-text-secondary text-sm mb-3">Round Snapshots</p>
            <CanvasTimeline />
          </div>
        )}
        {activeTab === 'operations' && (
          <div className="flex-1 overflow-y-auto">
            <CanvasOverlay />
          </div>
        )}
      </div>

      <CanvasControls />
    </div>
  )
}
