import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { useSession } from '../../hooks/useSession'
import { useWebSocket } from '../../hooks/useWebSocket'
import { GlowButton } from '../shared/GlowButton'
import { useAgentStore } from '../../store/useAgentStore'
import { useCriticStore } from '../../store/useCriticStore'
import { useCanvasStore } from '../../store/useCanvasStore'

const EXAMPLES = [
  'Paint a cat in Da Vinci style',
  'Create a surreal cyberpunk forest at dusk',
  'Generate a melancholic impressionist portrait',
  'Design an abstract expressionist seascape',
  'Compose a baroque still life with modern elements',
]

interface Props { onSessionStarted: (sessionId: string) => void }

export function PromptInput({ onSessionStarted }: Props) {
  const [prompt, setPrompt] = useState('')
  const [maxRounds, setMaxRounds] = useState(10)
  const [styleHint, setStyleHint] = useState('')
  const { createSession, startSession, isLoading, error } = useSession()
  const clearMessages = useAgentStore(s => s.clearMessages)
  const resetCritic = useCriticStore(s => s.reset)
  const resetCanvas = useCanvasStore(s => s.reset)

  const handleStart = async () => {
    if (!prompt.trim()) return
    clearMessages()
    resetCritic()
    resetCanvas()
    try {
      const session = await createSession({ prompt, max_rounds: maxRounds, style_hint: styleHint })
      await startSession(session.session_id)
      onSessionStarted(session.session_id)
    } catch (e) {
      console.error('Session start failed:', e)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-2xl"
      >
        <div className="text-center mb-10">
          <h1 className="text-5xl font-bold gradient-text-a mb-3" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
            CanvasMind
          </h1>
          <p className="text-text-secondary">
            Multi-Agent Collaborative AI Painting System
          </p>
          <p className="text-text-muted text-xs mt-1">
            TCS Research — Computational Creativity Platform
          </p>
        </div>

        <div className="bg-bg-card rounded-2xl p-6 border border-border-primary shadow-2xl">
          <label className="block text-text-secondary text-sm font-medium mb-2">
            Creative Prompt
          </label>
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="Describe what you want the agents to paint..."
            className="w-full h-24 bg-bg-tertiary border border-border-primary rounded-xl px-4 py-3 text-text-primary placeholder:text-text-muted resize-none focus:outline-none focus:border-accent-a text-sm transition-colors"
            onKeyDown={e => { if (e.ctrlKey && e.key === 'Enter') handleStart() }}
          />

          <div className="mt-3">
            <p className="text-text-muted text-xs mb-2">Examples:</p>
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map(ex => (
                <button
                  key={ex}
                  onClick={() => setPrompt(ex)}
                  className="text-xs px-3 py-1 rounded-full bg-bg-tertiary border border-border-primary text-text-muted hover:text-text-secondary hover:border-accent-a/30 transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mt-4">
            <div>
              <label className="text-text-muted text-xs block mb-1">Max Rounds: {maxRounds}</label>
              <input
                type="range"
                min={1} max={20}
                value={maxRounds}
                onChange={e => setMaxRounds(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="text-text-muted text-xs block mb-1">Style Hint (optional)</label>
              <input
                type="text"
                value={styleHint}
                onChange={e => setStyleHint(e.target.value)}
                placeholder="e.g. Baroque, Minimalist..."
                className="w-full bg-bg-tertiary border border-border-primary rounded-lg px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-a"
              />
            </div>
          </div>

          {error && (
            <div className="mt-3 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-xs">
              {error}
            </div>
          )}

          <GlowButton
            variant="primary"
            size="lg"
            onClick={handleStart}
            disabled={!prompt.trim()}
            loading={isLoading}
            className="w-full justify-center mt-4"
          >
            Start Multi-Agent Session (Ctrl+Enter)
          </GlowButton>
        </div>
      </motion.div>
    </div>
  )
}
