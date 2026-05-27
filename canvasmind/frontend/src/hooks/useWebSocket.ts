import { useEffect, useRef, useCallback } from 'react'
import { wsService } from '../services/websocket.service'
import type { WSEvent, WSEventType } from '../types/ws.types'
import { useAgentStore } from '../store/useAgentStore'
import { useCriticStore } from '../store/useCriticStore'
import { useCanvasStore } from '../store/useCanvasStore'
import { useSessionStore } from '../store/useSessionStore'
import { useUIStore } from '../store/useUIStore'
import type { AgentMessage } from '../types/agent.types'
import type { CriticEvaluation } from '../types/critic.types'
import type { CanvasState } from '../types/session.types'

export function useWebSocket(sessionId: string | null) {
  const connectedRef = useRef(false)
  const addMessage = useAgentStore(s => s.addMessage)
  const appendToken = useAgentStore(s => s.appendToken)
  const setTyping = useAgentStore(s => s.setTyping)
  const addEvaluation = useCriticStore(s => s.addEvaluation)
  const appendCriticToken = useCriticStore(s => s.appendCriticToken)
  const updateCanvas = useCanvasStore(s => s.updateCanvas)
  const updateFromWSEvent = useSessionStore(s => s.updateFromWSEvent)
  const { addLogEntry, setWsConnected } = useUIStore()

  useEffect(() => {
    if (!sessionId) return

    wsService.connect(sessionId)
    setWsConnected(false)

    const unsubs: Array<() => void> = []

    unsubs.push(wsService.on('__ws_connected__' as WSEventType, () => {
      setWsConnected(true)
      addLogEntry('success', 'WebSocket connected')
    }))

    unsubs.push(wsService.on('__ws_disconnected__' as WSEventType, () => {
      setWsConnected(false)
      addLogEntry('warning', 'WebSocket disconnected — reconnecting...')
    }))

    unsubs.push(wsService.on('session_started', (e: WSEvent) => {
      addLogEntry('info', `Session started: ${(e.data as { prompt: string }).prompt?.slice(0, 60)}`)
      updateFromWSEvent(e)
    }))

    unsubs.push(wsService.on('round_started', (e: WSEvent) => {
      addLogEntry('info', `Round ${e.round} started`)
      updateFromWSEvent(e)
    }))

    unsubs.push(wsService.on('agent_typing_start', (e: WSEvent) => {
      if (e.agent === 'agent_a') setTyping('agent_a', true)
      else if (e.agent === 'agent_b') setTyping('agent_b', true)
      else if (e.agent === 'critic') setTyping('critic', true)
    }))

    unsubs.push(wsService.on('agent_typing_end', (e: WSEvent) => {
      if (e.agent === 'agent_a') setTyping('agent_a', false)
      else if (e.agent === 'agent_b') setTyping('agent_b', false)
      else if (e.agent === 'critic') setTyping('critic', false)
    }))

    unsubs.push(wsService.on('agent_token', (e: WSEvent) => {
      const token = (e.data as { token: string }).token
      if (e.agent === 'agent_a') appendToken('agent_a', token)
      else if (e.agent === 'agent_b') appendToken('agent_b', token)
    }))

    unsubs.push(wsService.on('critic_token', (e: WSEvent) => {
      appendCriticToken((e.data as { token: string }).token)
    }))

    unsubs.push(wsService.on('agent_message_complete', (e: WSEvent) => {
      const msg = (e.data as { message: AgentMessage }).message
      addMessage(msg)
      addLogEntry(
        msg.sender === 'agent_a' ? 'agent_a' : 'agent_b',
        `[R${msg.round}] ${msg.sender} (${msg.intent}): ${msg.next_action?.slice(0, 80)}`
      )
    }))

    unsubs.push(wsService.on('critic_evaluation', (e: WSEvent) => {
      const ev = (e.data as { evaluation: CriticEvaluation }).evaluation
      addEvaluation(ev)
      addLogEntry('critic', `Critic R${ev.round}: ${ev.scores.composite?.toFixed(1)}/10 — ${ev.recommended_next_step?.slice(0, 80)}`)
    }))

    unsubs.push(wsService.on('canvas_updated', (e: WSEvent) => {
      updateCanvas((e.data as { canvas: CanvasState }).canvas)
    }))

    unsubs.push(wsService.on('round_complete', (e: WSEvent) => {
      addLogEntry('success', `Round ${e.round} complete`)
    }))

    unsubs.push(wsService.on('session_converged', (e: WSEvent) => {
      addLogEntry('success', `Session converged: ${(e.data as { reason: string }).reason}`)
      updateFromWSEvent(e)
    }))

    unsubs.push(wsService.on('session_complete', (e: WSEvent) => {
      addLogEntry('success', 'Session completed')
      updateFromWSEvent(e)
    }))

    unsubs.push(wsService.on('session_paused', (e: WSEvent) => {
      addLogEntry('warning', 'Session paused')
      updateFromWSEvent(e)
    }))

    unsubs.push(wsService.on('session_resumed', (e: WSEvent) => {
      addLogEntry('info', 'Session resumed')
      updateFromWSEvent(e)
    }))

    unsubs.push(wsService.on('agent_frozen', (e: WSEvent) => {
      addLogEntry('warning', `Agent ${e.agent} frozen`)
      updateFromWSEvent(e)
    }))

    unsubs.push(wsService.on('agent_unfrozen', (e: WSEvent) => {
      addLogEntry('info', `Agent ${e.agent} unfrozen`)
      updateFromWSEvent(e)
    }))

    unsubs.push(wsService.on('error', (e: WSEvent) => {
      addLogEntry('error', `Error: ${(e.data as { message: string }).message}`)
    }))

    return () => {
      unsubs.forEach(u => u())
      wsService.disconnect()
      setWsConnected(false)
    }
  }, [sessionId])
}
