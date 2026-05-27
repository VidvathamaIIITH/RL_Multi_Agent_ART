import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useUIStore } from '../../store/useUIStore'
import { SessionControls } from '../controls/SessionControls'
import { FreezeAgentToggle } from '../controls/FreezeAgentToggle'

export function SidePanel() {
  const { isSidePanelExpanded, toggleSidePanel } = useUIStore()

  return (
    <div className="relative flex">
      <button
        onClick={toggleSidePanel}
        className="absolute -left-2 top-1/2 -translate-y-1/2 z-10 w-4 h-10 bg-bg-tertiary border border-border-primary rounded text-text-muted hover:text-text-primary flex items-center justify-center text-xs transition-colors"
        title="Toggle side panel (Ctrl+B)"
      >
        {isSidePanelExpanded ? '›' : '‹'}
      </button>

      <AnimatePresence>
        {isSidePanelExpanded && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 180, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden shrink-0"
          >
            <div
              className="w-44 h-full flex flex-col gap-4 px-3 py-4 border-l border-border-primary overflow-y-auto"
              style={{ backgroundColor: 'var(--bg-secondary)' }}
            >
              <SessionControls />
              <div className="border-t border-border-primary pt-3">
                <FreezeAgentToggle />
              </div>
              <div className="border-t border-border-primary pt-3">
                <p className="text-text-muted text-xs mb-1">Shortcuts:</p>
                <div className="space-y-0.5 text-xs text-text-muted font-mono">
                  <p>Ctrl+I — Intervene</p>
                  <p>Ctrl+E — Export</p>
                  <p>Ctrl+P — Pause/Resume</p>
                  <p>Ctrl+B — Toggle panel</p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
