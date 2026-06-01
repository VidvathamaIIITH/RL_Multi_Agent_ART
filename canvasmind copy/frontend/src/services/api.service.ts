const BASE_URL = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_BACKEND_URL || 'http://localhost:8000'

class APIService {
  private baseUrl: string

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl
  }

  async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`)
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }))
      throw new Error(err.error || err.detail || `HTTP ${res.status}`)
    }
    return res.json()
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }))
      throw new Error(err.error || err.detail || `HTTP ${res.status}`)
    }
    return res.json()
  }

  async delete(path: string): Promise<void> {
    const res = await fetch(`${this.baseUrl}${path}`, { method: 'DELETE' })
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
  }

  async getBlob(path: string): Promise<Blob> {
    const res = await fetch(`${this.baseUrl}${path}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.blob()
  }

  async getText(path: string): Promise<string> {
    const res = await fetch(`${this.baseUrl}${path}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.text()
  }
}

export const apiService = new APIService(BASE_URL)
