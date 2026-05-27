import React from 'react'
import { useUIStore } from '../../store/useUIStore'

interface DotProps { active: boolean; color?: string; label: string; pulsing?: boolean }

function Dot({ active, color = '#10b981', label, pulsing }: DotProps) {
  return (
    <div className="flex items-center gap-1.5" title={label}>
      <span
        className={`w-2 h-2 rounded-full transition-colors ${pulsing && active ? 'animate-pulse' : ''}`}
        style={{ backgroundColor: active ? color : '#444466' }}
      />
      <span className="text-xs text-text-muted hidden sm:block">{label}</span>
    </div>
  )
}

export function StatusIndicator() {
  const { wsConnected, backendHealthy, azureConnected } = useUIStore()

  return (
    <div className="flex items-center gap-3">
      <Dot active={backendHealthy} label="API" color="#10b981" />
      <Dot active={wsConnected} label="WS" color="#6366f1" pulsing />
      <Dot active={azureConnected} label="Azure" color="#f59e0b" />
    </div>
  )
}
