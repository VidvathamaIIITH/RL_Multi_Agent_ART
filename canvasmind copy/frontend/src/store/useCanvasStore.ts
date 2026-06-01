import { create } from 'zustand'
import type { CanvasState, CanvasOperation, CanvasSnapshot } from '../types/session.types'
import { apiService } from '../services/api.service'

interface CanvasStoreState {
  currentImage: string | null
  operations: CanvasOperation[]
  snapshots: CanvasSnapshot[]
  regionMap: Record<string, string>
  currentSnapshotRound: number
  isGeneratingImage: boolean
  canvasData: CanvasState | null

  updateCanvas: (canvas: CanvasState) => void
  viewSnapshot: (round: number) => void
  generateImage: (sessionId: string) => Promise<void>
  setCurrentImage: (base64: string | null) => void
  reset: () => void
}

export const useCanvasStore = create<CanvasStoreState>((set, get) => ({
  currentImage: null,
  operations: [],
  snapshots: [],
  regionMap: {},
  currentSnapshotRound: 0,
  isGeneratingImage: false,
  canvasData: null,

  updateCanvas: (canvas) => {
    set({
      canvasData: canvas,
      operations: canvas.operations_history,
      snapshots: canvas.snapshots,
      regionMap: canvas.region_ownership,
      currentImage: canvas.current_image_base64,
      currentSnapshotRound: canvas.current_round,
    })
  },

  viewSnapshot: (round) => {
    const { snapshots } = get()
    const snap = snapshots.find(s => s.round === round)
    if (snap) {
      set({
        currentSnapshotRound: round,
        currentImage: snap.image_base64,
        regionMap: snap.region_map,
        operations: snap.operations,
      })
    }
  },

  generateImage: async (sessionId) => {
    set({ isGeneratingImage: true })
    try {
      const result = await apiService.post<{ image_base64: string }>(
        `/api/sessions/${sessionId}/canvas/generate`,
        {}
      )
      set({ currentImage: result.image_base64, isGeneratingImage: false })
    } catch (e) {
      set({ isGeneratingImage: false })
      throw e
    }
  },

  setCurrentImage: (base64) => set({ currentImage: base64 }),

  reset: () => set({
    currentImage: null,
    operations: [],
    snapshots: [],
    regionMap: {},
    currentSnapshotRound: 0,
    isGeneratingImage: false,
    canvasData: null,
  }),
}))
