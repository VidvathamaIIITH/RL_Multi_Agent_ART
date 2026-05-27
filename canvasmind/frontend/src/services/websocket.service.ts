import type { WSEvent, WSEventType } from '../types/ws.types'

const WS_BASE = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_WS_URL || 'ws://localhost:8000'

type Handler = (event: WSEvent) => void

class WebSocketService {
  private ws: WebSocket | null = null
  private sessionId: string | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private handlers: Map<WSEventType | '__all__', Handler[]> = new Map()
  private manualClose = false

  connect(sessionId: string): void {
    this.sessionId = sessionId
    this.manualClose = false
    this._connect()
  }

  private _connect(): void {
    if (!this.sessionId) return
    const url = `${WS_BASE}/ws/${this.sessionId}`
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this.reconnectAttempts = 0
      this._dispatch({ event_type: '__ws_connected__' as WSEventType, session_id: this.sessionId!, round: null, agent: null, data: {}, timestamp: new Date().toISOString() })
    }

    this.ws.onmessage = (e) => {
      try {
        const event: WSEvent = JSON.parse(e.data)
        this._dispatch(event)
      } catch (err) {
        console.error('WS parse error:', err)
      }
    }

    this.ws.onerror = (e) => {
      console.error('WS error:', e)
    }

    this.ws.onclose = () => {
      this._dispatch({ event_type: '__ws_disconnected__' as WSEventType, session_id: this.sessionId!, round: null, agent: null, data: {}, timestamp: new Date().toISOString() })
      if (!this.manualClose) {
        this._scheduleReconnect()
      }
    }
  }

  on(eventType: WSEventType | '__all__', handler: Handler): () => void {
    const existing = this.handlers.get(eventType) || []
    this.handlers.set(eventType, [...existing, handler])
    return () => {
      const current = this.handlers.get(eventType) || []
      this.handlers.set(eventType, current.filter(h => h !== handler))
    }
  }

  disconnect(): void {
    this.manualClose = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
    this.sessionId = null
  }

  private _dispatch(event: WSEvent): void {
    const specific = this.handlers.get(event.event_type) || []
    const all = this.handlers.get('__all__') || []
    ;[...specific, ...all].forEach(h => {
      try { h(event) } catch (e) { console.error('WS handler error:', e) }
    })
  }

  private _scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('WS max reconnect attempts reached')
      return
    }
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 16000)
    this.reconnectAttempts++
    console.log(`WS reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`)
    this.reconnectTimer = setTimeout(() => this._connect(), delay)
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

export const wsService = new WebSocketService()
