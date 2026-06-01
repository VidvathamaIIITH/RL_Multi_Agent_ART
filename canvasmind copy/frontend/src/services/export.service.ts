import { apiService } from './api.service'

class ExportService {
  async downloadJSON(sessionId: string): Promise<void> {
    const data = await apiService.get<unknown>(`/api/sessions/${sessionId}/export/json`)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    this._download(blob, `canvasmind-${sessionId}-export.json`)
  }

  async downloadMarkdown(sessionId: string): Promise<void> {
    const text = await apiService.getText(`/api/sessions/${sessionId}/export/markdown`)
    const blob = new Blob([text], { type: 'text/markdown' })
    this._download(blob, `canvasmind-${sessionId}-report.md`)
  }

  async downloadTranscript(sessionId: string): Promise<void> {
    const text = await apiService.getText(`/api/sessions/${sessionId}/export/transcript`)
    const blob = new Blob([text], { type: 'text/plain' })
    this._download(blob, `canvasmind-${sessionId}-transcript.txt`)
  }

  async downloadCanvas(sessionId: string): Promise<void> {
    const blob = await apiService.getBlob(`/api/sessions/${sessionId}/export/canvas`)
    this._download(blob, `canvasmind-${sessionId}-canvas.zip`)
  }

  async downloadReplay(sessionId: string): Promise<void> {
    const data = await apiService.get<unknown>(`/api/sessions/${sessionId}/export/replay`)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    this._download(blob, `canvasmind-${sessionId}-replay.json`)
  }

  private _download(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }
}

export const exportService = new ExportService()
