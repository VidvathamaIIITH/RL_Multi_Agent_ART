// SSE + REST client for the Quad-Agent Pipeline (modular backend at /api/quad/*).
import type { QuadAgentConfig, QuadEvent, Persona, Expertise } from '../types/quad.types'

const BASE_URL =
  (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_BACKEND_URL ||
  'http://localhost:8000'

export const QUAD_HERO_URL = `${BASE_URL}/api/quad/hero-image`

export interface PersonasResponse {
  personas: Persona[]
  levels: Expertise[]
}

export async function fetchPersonas(): Promise<PersonasResponse> {
  const res = await fetch(`${BASE_URL}/api/quad/personas`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<PersonasResponse>
}

export interface StartQuadPayload {
  prompt: string
  style: string
  rounds: number
  images: boolean
  agents: {
    name: string
    persona: string
    custom_prompt: string
    expertise: string
  }[]
}

export function toStartPayload(
  prompt: string,
  style: string,
  rounds: number,
  agents: QuadAgentConfig[],
): StartQuadPayload {
  return {
    prompt,
    style,
    rounds,
    images: true,
    agents: agents.map((a) => ({
      name: a.name,
      persona: a.persona,
      custom_prompt: a.useCustom ? a.customPrompt : '',
      expertise: a.expertise,
    })),
  }
}

export async function startQuad(payload: StartQuadPayload): Promise<{ session_id?: string; error?: string }> {
  const res = await fetch(`${BASE_URL}/api/quad/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return res.json()
}

export async function stopQuad(sessionId: string): Promise<void> {
  try {
    await fetch(`${BASE_URL}/api/quad/stop/${sessionId}`, { method: 'POST' })
  } catch {
    /* non-fatal */
  }
}

export function streamQuad(sessionId: string, onEvent: (ev: QuadEvent) => void): EventSource {
  const es = new EventSource(`${BASE_URL}/api/quad/stream/${sessionId}`)
  es.onmessage = (e: MessageEvent<string>) => {
    try {
      const data = JSON.parse(e.data) as QuadEvent
      if (data && data.type) onEvent(data)
    } catch {
      /* ignore keep-alives / partials */
    }
  }
  return es
}
