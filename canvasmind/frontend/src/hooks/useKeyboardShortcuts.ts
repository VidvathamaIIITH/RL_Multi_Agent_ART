import { useEffect } from 'react'
import { useUIStore } from '../store/useUIStore'
import { useSession } from './useSession'

export function useKeyboardShortcuts() {
  const { openInterventionModal, openExportModal, toggleSidePanel } = useUIStore()
  const { pauseSession, resumeSession, session } = useSession()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey) {
        switch (e.key.toLowerCase()) {
          case 'i':
            e.preventDefault()
            openInterventionModal()
            break
          case 'e':
            e.preventDefault()
            openExportModal()
            break
          case 'b':
            e.preventDefault()
            toggleSidePanel()
            break
          case 'p':
            e.preventDefault()
            if (session?.status === 'running') pauseSession()
            else if (session?.status === 'paused') resumeSession()
            break
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [session?.status])
}
