import { create } from 'zustand'
import type { ActiveTab, LogEntry } from '../types/ui.types'

function makeId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

interface UIState {
  isInterventionModalOpen: boolean
  isRollbackModalOpen: boolean
  isExportModalOpen: boolean
  isLoadSessionModalOpen: boolean
  selectedRoundForRollback: number | null
  activeTab: ActiveTab
  isSidePanelExpanded: boolean
  sessionLog: LogEntry[]
  wsConnected: boolean
  backendHealthy: boolean
  azureConnected: boolean

  openInterventionModal: () => void
  closeInterventionModal: () => void
  openRollbackModal: (round: number) => void
  closeRollbackModal: () => void
  openExportModal: () => void
  closeExportModal: () => void
  openLoadSessionModal: () => void
  closeLoadSessionModal: () => void
  setActiveTab: (tab: ActiveTab) => void
  toggleSidePanel: () => void
  addLogEntry: (type: LogEntry['type'], message: string) => void
  setWsConnected: (connected: boolean) => void
  setBackendHealthy: (healthy: boolean) => void
  setAzureConnected: (connected: boolean) => void
  clearLog: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  isInterventionModalOpen: false,
  isRollbackModalOpen: false,
  isExportModalOpen: false,
  isLoadSessionModalOpen: false,
  selectedRoundForRollback: null,
  activeTab: 'canvas',
  isSidePanelExpanded: true,
  sessionLog: [],
  wsConnected: false,
  backendHealthy: false,
  azureConnected: false,

  openInterventionModal: () => set({ isInterventionModalOpen: true }),
  closeInterventionModal: () => set({ isInterventionModalOpen: false }),
  openRollbackModal: (round) => set({ isRollbackModalOpen: true, selectedRoundForRollback: round }),
  closeRollbackModal: () => set({ isRollbackModalOpen: false, selectedRoundForRollback: null }),
  openExportModal: () => set({ isExportModalOpen: true }),
  closeExportModal: () => set({ isExportModalOpen: false }),
  openLoadSessionModal: () => set({ isLoadSessionModalOpen: true }),
  closeLoadSessionModal: () => set({ isLoadSessionModalOpen: false }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  toggleSidePanel: () => set(s => ({ isSidePanelExpanded: !s.isSidePanelExpanded })),

  addLogEntry: (type, message) =>
    set(s => ({
      sessionLog: [
        ...s.sessionLog.slice(-200),
        {
          id: makeId(),
          timestamp: new Date().toISOString(),
          type,
          message,
        },
      ],
    })),

  setWsConnected: (connected) => set({ wsConnected: connected }),
  setBackendHealthy: (healthy) => set({ backendHealthy: healthy }),
  setAzureConnected: (connected) => set({ azureConnected: connected }),
  clearLog: () => set({ sessionLog: [] }),
}))
