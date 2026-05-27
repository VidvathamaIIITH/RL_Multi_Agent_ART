import React from 'react'
import type { MessageIntent } from '../../types/agent.types'

interface Props { intent: MessageIntent }

export function IntentBadge({ intent }: Props) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono font-medium badge-${intent}`}>
      {intent}
    </span>
  )
}
