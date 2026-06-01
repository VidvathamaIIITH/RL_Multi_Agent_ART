import React from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import type { CriticEvaluation } from '../../types/critic.types'

interface Props { evaluations: CriticEvaluation[] }

export function ScoreHistory({ evaluations }: Props) {
  const data = evaluations.map(ev => ({
    round: `R${ev.round}`,
    composite: Number(ev.scores.composite.toFixed(2)),
    composition: ev.scores.compositional_coherence,
    style: ev.scores.style_fidelity,
    emotion: ev.scores.emotional_resonance,
  }))

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-text-muted text-xs">
        Score history will appear here
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={80}>
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
        <XAxis dataKey="round" tick={{ fontSize: 10, fill: '#8888aa' }} />
        <YAxis domain={[0, 10]} tick={{ fontSize: 10, fill: '#8888aa' }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#16161f', border: '1px solid #2a2a3a', borderRadius: '8px', fontSize: 11 }}
          labelStyle={{ color: '#f0f0ff' }}
        />
        <ReferenceLine y={7.5} stroke="#10b981" strokeDasharray="3 3" strokeOpacity={0.5} />
        <Line type="monotone" dataKey="composite" stroke="#f59e0b" strokeWidth={2} dot={false} name="Composite" />
        <Line type="monotone" dataKey="composition" stroke="#6366f1" strokeWidth={1} dot={false} strokeOpacity={0.6} name="Composition" />
        <Line type="monotone" dataKey="style" stroke="#ec4899" strokeWidth={1} dot={false} strokeOpacity={0.6} name="Style" />
      </LineChart>
    </ResponsiveContainer>
  )
}
