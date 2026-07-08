// Bridges the Quad SSE stream to the Zustand store (kept out of components so
// the EventSource survives re-renders and can be closed from either view).
import { useQuadStore } from '../../store/useQuadStore'
import { startQuad, stopQuad, streamQuad, toStartPayload } from '../../services/quad.service'
import type { QuadEvent } from '../../types/quad.types'

let activeStream: EventSource | null = null

function handleEvent(ev: QuadEvent): void {
  const s = useQuadStore.getState()
  switch (ev.type) {
    case 'session':
      s.startFromSession(ev.agents ?? [], ev.total_turns ?? s.totalTurns)
      s.addLog('session', `brief · ${ev.prompt ?? ''}`)
      break
    case 'turn':
      if (typeof ev.agent_idx === 'number') s.setActive(ev.agent_idx)
      if (typeof ev.round === 'number') s.setRound(ev.round)
      s.addLog('turn', `R${ev.round ?? ''} · ${ev.name ?? ''} (${ev.persona_name ?? ''})`)
      break
    case 'agent':
      s.pushStep({
        turn: ev.turn ?? 0,
        agentIdx: ev.agent_idx ?? 0,
        name: ev.name ?? '',
        personaName: ev.persona_name,
        object: ev.object ?? ev.message?.new_object ?? 'a new element',
        sees: ev.message?.sees_on_canvas,
        where: ev.message?.where,
        reasoning: ev.message?.reasoning,
        palette: ev.message?.palette,
        confidence: ev.message?.confidence_score,
      })
      s.addLog('agent', `${ev.name ?? ''}: + ${ev.object ?? ''}`)
      break
    case 'image':
      if (ev.image && typeof ev.turn === 'number') s.setImageForTurn(ev.turn, ev.image)
      s.addLog('image', `image ${ev.turn ?? ''} · ${ev.label ?? ''}`)
      break
    case 'critic':
      if (ev.evaluation) s.setCritic(ev.evaluation)
      s.addLog('critic', 'JUDGE scored the collaboration')
      break
    case 'final':
      if (ev.image) s.setCurrentImage(ev.image)
      s.addLog('final', 'final canvas presented')
      break
    case 'warning':
      s.addLog('warning', String(ev.message ?? 'warning'))
      break
    case 'summary':
      s.addLog('summary', `complete · ${ev.turns ?? ''} turns · ${ev.elapsed ?? ''}s`)
      break
    case 'error':
      s.setStatus('error')
      s.addLog('error', String(ev.message ?? 'error'))
      break
    case 'done':
      s.setStatus('done')
      s.setActive(-1)
      closeQuadStream()
      s.addLog('done', 'session complete')
      break
    default:
      break
  }
}

export async function launchQuad(): Promise<void> {
  const s = useQuadStore.getState()
  s.beginRun()
  const payload = toStartPayload(
    s.prompt.trim() || 'A lighthouse at the edge of the world',
    s.style.trim(),
    s.rounds,
    s.agents,
  )
  try {
    const res = await startQuad(payload)
    if (res.error || !res.session_id) {
      s.setStatus('error')
      s.addLog('error', res.error ?? 'failed to start')
      return
    }
    s.setSessionId(res.session_id)
    s.addLog('session', `session ${res.session_id}`)
    activeStream = streamQuad(res.session_id, handleEvent)
    activeStream.onerror = () => s.addLog('error', 'stream interrupted')
  } catch (err) {
    s.setStatus('error')
    s.addLog('error', `backend error — ${(err as Error).message}`)
  }
}

export function stopQuadRun(): void {
  const s = useQuadStore.getState()
  if (s.sessionId) {
    void stopQuad(s.sessionId)
    s.addLog('control', 'stop requested — presenting work so far')
  }
}

export function closeQuadStream(): void {
  if (activeStream) {
    activeStream.close()
    activeStream = null
  }
}
