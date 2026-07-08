import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { PromptInput } from './components/prompt/PromptInput'
import { AppLayout } from './components/layout/AppLayout'
import { TopBar } from './components/layout/TopBar'
import { useWebSocket } from './hooks/useWebSocket'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { useSessionStore } from './store/useSessionStore'
import { useUIStore } from './store/useUIStore'
import { useQuadStore } from './store/useQuadStore'
import { QuadConfigDashboard } from './components/quad/QuadConfigDashboard'
import { QuadLiveView } from './components/quad/QuadLiveView'
import { apiService } from './services/api.service'
import './styles/globals.css'
import './styles/animations.css'

type AppView = 'prompt' | 'session'

export default function App() {
  const [view, setView] = useState<AppView>('prompt')
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const { openLoadSessionModal } = useUIStore()
  const { setBackendHealthy, setAzureConnected } = useUIStore()
  const quadView = useQuadStore((s) => s.view)
  const openQuad = useQuadStore((s) => s.setView)

  // WebSocket connects when a session is active
  useWebSocket(activeSessionId)

  // Keyboard shortcuts
  useKeyboardShortcuts()

  // Health check on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        await apiService.get('/health')
        setBackendHealthy(true)
      } catch {
        setBackendHealthy(false)
      }
      try {
        const res = await apiService.get<{ status: string }>('/health/azure')
        setAzureConnected(res.status === 'connected')
      } catch {
        setAzureConnected(false)
      }
    }
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleSessionStarted = (sessionId: string) => {
    setActiveSessionId(sessionId)
    setView('session')
  }

  const handleHome = () => {
    setView('prompt')
    setActiveSessionId(null)
  }

  if (quadView === 'config') return <QuadConfigDashboard />
  if (quadView === 'live') return <QuadLiveView />

  return (
    <div className="h-screen flex flex-col overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {view === 'prompt' && (
        <button
          onClick={() => openQuad('config')}
          style={{
            position: 'fixed', top: 16, right: 16, zIndex: 60,
            border: '1px solid rgba(255,255,255,0.4)', background: 'rgba(0,0,0,0.45)', color: '#fff',
            borderRadius: 75, padding: '8px 16px', fontSize: 11, letterSpacing: '0.14em',
            textTransform: 'uppercase', cursor: 'pointer',
          }}
        >
          ⧉ Switch to Quad-Agent Pipeline
        </button>
      )}
      {view === 'session' && (
        <TopBar onHome={handleHome} onLoadSession={openLoadSessionModal} />
      )}

      <div className="flex-1 overflow-hidden min-h-0">
        <AnimatePresence mode="wait">
          {view === 'prompt' ? (
            <motion.div
              key="prompt"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full"
            >
              <PromptInput onSessionStarted={handleSessionStarted} />
            </motion.div>
          ) : (
            <motion.div
              key="session"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full"
            >
              <AppLayout />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
