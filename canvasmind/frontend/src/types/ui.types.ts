export interface GlowButtonProps {
  onClick?: () => void
  disabled?: boolean
  variant?: 'primary' | 'secondary' | 'danger' | 'success' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  children: React.ReactNode
  className?: string
  loading?: boolean
  title?: string
}

export interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
}

export type ActiveTab = 'canvas' | 'timeline' | 'operations'

export interface LogEntry {
  id: string
  timestamp: string
  type: 'info' | 'success' | 'warning' | 'error' | 'agent_a' | 'agent_b' | 'critic'
  message: string
}
