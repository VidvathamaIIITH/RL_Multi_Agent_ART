import React, { useRef, useState, useEffect } from 'react'
import { useCanvasStore } from '../../store/useCanvasStore'
import { useSessionStore } from '../../store/useSessionStore'
import { GlowButton } from '../shared/GlowButton'

const REGIONS_GRID = [
  ['top_left', 'top_center', 'top_right'],
  ['middle_left', 'center', 'middle_right'],
  ['bottom_left', 'bottom_center', 'bottom_right'],
]

const AGENT_COLORS: Record<string, string> = {
  agent_a: 'rgba(99,102,241,0.25)',
  agent_b: 'rgba(236,72,153,0.25)',
}

export function CanvasViewer() {
  const { currentImage, regionMap, isGeneratingImage } = useCanvasStore()
  const session = useSessionStore(s => s.session)
  const generateImage = useCanvasStore(s => s.generateImage)
  const [zoom, setZoom] = useState(1)
  const [showOverlay, setShowOverlay] = useState(true)

  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault()
      setZoom(z => Math.min(3, Math.max(0.5, z - e.deltaY * 0.001)))
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Controls */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-primary">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setZoom(z => Math.min(3, z + 0.25))}
            className="text-text-muted hover:text-text-primary text-xs px-2 py-1 border border-border-primary rounded"
          >+</button>
          <span className="text-text-muted text-xs font-mono">{Math.round(zoom * 100)}%</span>
          <button
            onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}
            className="text-text-muted hover:text-text-primary text-xs px-2 py-1 border border-border-primary rounded"
          >−</button>
          <button onClick={() => setZoom(1)} className="text-text-muted hover:text-text-primary text-xs px-2 py-1 border border-border-primary rounded">
            1:1
          </button>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-text-muted cursor-pointer">
            <input type="checkbox" checked={showOverlay} onChange={e => setShowOverlay(e.target.checked)} className="w-3 h-3" />
            Region overlay
          </label>
          {session && (
            <GlowButton
              onClick={() => generateImage(session.session_id)}
              loading={isGeneratingImage}
              size="sm"
              variant="ghost"
            >
              Generate Image
            </GlowButton>
          )}
        </div>
      </div>

      {/* Canvas area */}
      <div
        className="flex-1 overflow-auto flex items-center justify-center"
        onWheel={handleWheel}
        style={{ background: 'radial-gradient(ellipse at center, #1a1a28 0%, #0a0a0f 100%)' }}
      >
        <div
          style={{ transform: `scale(${zoom})`, transformOrigin: 'center', transition: 'transform 0.15s ease' }}
          className="relative"
        >
          {currentImage ? (
            <img
              src={`data:image/png;base64,${currentImage}`}
              alt="Canvas"
              className="max-w-[512px] max-h-[512px] rounded-lg"
            />
          ) : (
            <ASCIICanvas regionMap={regionMap} />
          )}

          {showOverlay && Object.keys(regionMap).length > 0 && !currentImage && (
            <RegionOverlay regionMap={regionMap} />
          )}
        </div>
      </div>
    </div>
  )
}

function ASCIICanvas({ regionMap }: { regionMap: Record<string, string> }) {
  return (
    <div
      className="grid grid-cols-3 gap-0.5 p-2 rounded-xl"
      style={{ width: 360, height: 360, backgroundColor: '#0d0d15', border: '1px solid #2a2a3a' }}
    >
      {REGIONS_GRID.flat().map(region => {
        const owner = regionMap[region]
        const bg = owner ? AGENT_COLORS[owner] || 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.02)'
        return (
          <div
            key={region}
            className="flex items-center justify-center rounded text-xs transition-all"
            style={{ backgroundColor: bg, border: '1px solid rgba(255,255,255,0.05)' }}
          >
            {owner ? (
              <span
                className="font-bold text-base"
                style={{ color: owner === 'agent_a' ? '#6366f1' : '#ec4899' }}
              >
                {owner === 'agent_a' ? 'A' : 'B'}
              </span>
            ) : (
              <span className="text-text-muted opacity-30">·</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function RegionOverlay({ regionMap }: { regionMap: Record<string, string> }) {
  return (
    <div className="absolute inset-0 grid grid-cols-3 pointer-events-none" style={{ gridTemplateRows: 'repeat(3, 1fr)' }}>
      {REGIONS_GRID.flat().map(region => {
        const owner = regionMap[region]
        if (!owner) return <div key={region} />
        return (
          <div
            key={region}
            className="flex items-end justify-start p-1"
            style={{ backgroundColor: AGENT_COLORS[owner] || 'transparent' }}
          >
            <span className="text-xs font-mono opacity-60" style={{ color: owner === 'agent_a' ? '#818cf8' : '#f472b6' }}>
              {region.replace('_', ' ')}
            </span>
          </div>
        )
      })}
    </div>
  )
}
