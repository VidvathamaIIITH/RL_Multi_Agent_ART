import React from 'react'
import { useQuadStore } from '../../store/useQuadStore'
import type { Expertise } from '../../types/quad.types'

const card: React.CSSProperties = {
  border: '1px solid rgba(255,255,255,0.16)', borderRadius: 14, padding: 18,
  background: 'rgba(255,255,255,0.02)', display: 'flex', flexDirection: 'column', gap: 12,
}
const label: React.CSSProperties = {
  fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#8d8d8d',
}
const input: React.CSSProperties = {
  width: '100%', background: 'transparent', border: 'none',
  borderBottom: '1px solid rgba(255,255,255,0.2)', color: '#fff', fontSize: 15,
  fontWeight: 300, padding: '0 0 8px', outline: 'none',
}
const select: React.CSSProperties = {
  width: '100%', background: '#0a0a0a', border: '1px solid rgba(255,255,255,0.28)',
  borderRadius: 75, color: '#fff', fontSize: 13, padding: '9px 16px', outline: 'none',
}
const textarea: React.CSSProperties = {
  width: '100%', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.16)',
  borderRadius: 10, color: '#fff', fontSize: 13, lineHeight: 1.45, padding: 10, outline: 'none',
  resize: 'vertical', minHeight: 70,
}

function cap(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

export function QuadAgentCard({ index }: { index: number }): JSX.Element {
  const agent = useQuadStore((s) => s.agents[index])
  const personas = useQuadStore((s) => s.personas)
  const levels = useQuadStore((s) => s.levels)
  const updateAgent = useQuadStore((s) => s.updateAgent)
  const toggleCustom = useQuadStore((s) => s.toggleCustom)

  return (
    <div style={card}>
      <div style={{ ...label, letterSpacing: '0.24em' }}>{`Agent 0${index + 1}`}</div>
      <input
        style={input}
        value={agent.name}
        placeholder="Agent name"
        onChange={(e) => updateAgent(index, { name: e.target.value })}
      />
      <label style={label}>Persona Preset</label>
      <select
        style={select}
        value={agent.persona}
        onChange={(e) => updateAgent(index, { persona: e.target.value })}
      >
        {personas.map((p) => (
          <option key={p.key} value={p.key}>{p.name}</option>
        ))}
      </select>

      <button
        onClick={() => toggleCustom(index)}
        style={{
          alignSelf: 'flex-start', background: agent.useCustom ? '#fff' : 'transparent',
          color: agent.useCustom ? '#000' : '#cdcdcd', border: '1px solid rgba(255,255,255,0.24)',
          borderRadius: 75, padding: '5px 12px', fontSize: 10, letterSpacing: '0.12em',
          textTransform: 'uppercase', cursor: 'pointer',
        }}
      >
        Configure Custom Agent
      </button>
      {agent.useCustom && (
        <textarea
          style={textarea}
          value={agent.customPrompt}
          placeholder="Raw bespoke persona prompt (overrides the preset)"
          onChange={(e) => updateAgent(index, { customPrompt: e.target.value })}
        />
      )}

      <label style={label}>Expertise</label>
      <select
        style={select}
        value={agent.expertise}
        onChange={(e) => updateAgent(index, { expertise: e.target.value as Expertise })}
      >
        {levels.map((l) => (
          <option key={l} value={l}>{cap(l)}</option>
        ))}
      </select>
    </div>
  )
}
