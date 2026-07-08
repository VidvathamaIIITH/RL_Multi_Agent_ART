import React, { useState } from 'react'
import { useQuadStore } from '../../store/useQuadStore'
import { stopQuadRun, closeQuadStream } from './quadRun'
import type { QuadStep } from '../../types/quad.types'

const page: React.CSSProperties = {
  minHeight: '100vh', background: '#000', color: '#fff', overflowY: 'auto',
  fontFamily: "'Inter',system-ui,sans-serif", padding: '40px 40px 40px',
}
const label: React.CSSProperties = {
  fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#6d6d6d',
}
const pill = (border = 'rgba(255,255,255,0.28)'): React.CSSProperties => ({
  border: `1px solid ${border}`, background: 'transparent', color: '#fff', borderRadius: 75,
  padding: '8px 16px', fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', cursor: 'pointer',
})
function cap(s: string): string { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s }

const SCORE_KEYS = ['compositional_coherence', 'style_fidelity', 'emotional_resonance', 'originality', 'collaboration_quality']
const SCORE_LABELS: Record<string, string> = {
  compositional_coherence: 'Compositional coherence', style_fidelity: 'Style fidelity',
  emotional_resonance: 'Emotional resonance', originality: 'Originality', collaboration_quality: 'Collaboration quality',
}

// Expandable per-turn card: object always shown, details on click.
function QuadStepCard({ step }: { step: QuadStep }): JSX.Element {
  const [open, setOpen] = useState(false)
  const palette = step.palette && step.palette.length ? step.palette.join(' · ') : ''
  const conf = step.confidence != null ? `${Math.round(step.confidence * 100)}%` : ''
  const row = (k: string, v?: string) =>
    v ? (
      <div key={k}>
        <p style={{ fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#4a4a4a', marginTop: 6 }}>{k}</p>
        <p style={{ fontSize: 11, color: '#8d8d8d', lineHeight: 1.4 }}>{v}</p>
      </div>
    ) : null
  return (
    <div style={{ borderLeft: '1px solid rgba(255,255,255,0.18)', paddingLeft: 10 }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', background: 'transparent', border: 'none', padding: 0, cursor: 'pointer' }}
      >
        <span style={{ fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#4a4a4a' }}>{`Turn ${step.turn} · adds`}</span>
        <span style={{ fontSize: 10, color: '#6d6d6d' }}>{open ? '▴' : '▾'}</span>
      </button>
      <p style={{ fontSize: 14, fontWeight: 300, lineHeight: 1.3, margin: '4px 0 2px' }}>{step.object}</p>
      {open && (
        <div style={{ marginTop: 6, borderTop: '1px dashed rgba(255,255,255,0.12)', paddingTop: 6 }}>
          {row('Sees on canvas', step.sees)}
          {row('Placed', step.where)}
          {row('Palette', palette)}
          {row('Why', step.reasoning)}
          {row('Confidence', conf)}
        </div>
      )}
    </div>
  )
}

export function QuadLiveView(): JSX.Element {
  const {
    meta, agents, feeds, steps, currentImage, activeAgentIndex, totalTurns, status, log,
    prompt, style, critic, setView, resetRun,
  } = useQuadStore()
  const [showBrief, setShowBrief] = useState(false)

  const panelMeta = (i: number) => {
    const m = meta[i]
    if (m) return { name: m.name, persona: m.persona_name, expertise: m.expertise }
    const a = agents[i]
    return { name: a?.name ?? `Agent ${i + 1}`, persona: a?.persona ?? '', expertise: a?.expertise ?? 'intermediate' }
  }
  const framed: QuadStep[] = steps.filter((s) => s.image)
  const composite = (() => {
    const c = critic?.scores?.composite
    if (typeof c === 'number') return c
    const vals = SCORE_KEYS.map((k) => critic?.scores?.[k] ?? 0)
    return vals.reduce((a, b) => a + b, 0) / (vals.length || 1)
  })()

  return (
    <div style={page}>
      {/* header: compact full-width clickable brief + controls */}
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        borderBottom: '1px solid rgba(255,255,255,0.12)', paddingBottom: 16, marginBottom: 22, gap: 24, flexWrap: 'wrap',
      }}>
        <div style={{ flex: 1, minWidth: 260, cursor: 'pointer' }} onClick={() => setShowBrief(true)} title="Click to read the full brief">
          <p style={{ ...label, marginBottom: 8, letterSpacing: '0.22em' }}>
            Quad Pipeline · Brief <span style={{ color: '#5a5a5a' }}>· click to expand</span>
          </p>
          <h2 style={{
            fontSize: 'clamp(15px,1.7vw,22px)', fontWeight: 300, lineHeight: 1.3, color: '#fff',
            display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          }}>{prompt || 'Untitled collaboration'}</h2>
          {style && <p style={{ fontSize: 12, letterSpacing: '0.06em', color: '#9a9a9a', marginTop: 8, textTransform: 'uppercase' }}>{style}</p>}
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 18, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <div style={{ textAlign: 'right' }}>
            <p style={{ ...label, marginBottom: 6 }}>Turn</p>
            <p style={{ fontSize: 40, fontWeight: 300, lineHeight: 1 }}>{String(steps.length).padStart(2, '0')} / {totalTurns}</p>
          </div>
          {status === 'running' && <button onClick={stopQuadRun} style={pill('rgba(255,255,255,0.45)')}>Stop ↦</button>}
          <button onClick={() => { closeQuadStream(); resetRun(); setView('config') }} style={pill()}>New config</button>
        </div>
      </div>

      {/* 4 agent panels with expandable cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 16, marginBottom: 28 }}>
        {[0, 1, 2, 3].map((i) => {
          const pm = panelMeta(i)
          const active = i === activeAgentIndex
          return (
            <div key={i} style={{
              border: `1px solid ${active ? 'rgba(255,255,255,0.55)' : 'rgba(255,255,255,0.14)'}`,
              borderRadius: 12, padding: 12, background: 'rgba(255,255,255,0.02)', minHeight: 120,
              display: 'flex', flexDirection: 'column', gap: 10,
              boxShadow: active ? '0 0 26px rgba(255,255,255,0.06)' : 'none',
            }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: 8 }}>
                <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.14em' }}>{pm.name}</span>
                <span style={{ fontSize: 10, color: '#9a9a9a' }}>{pm.persona}</span>
                <span style={{ marginLeft: 'auto', fontSize: 9, color: '#9a9a9a', border: '1px solid rgba(255,255,255,0.28)', borderRadius: 75, padding: '2px 8px' }}>{cap(pm.expertise)}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 260, overflowY: 'auto' }}>
                {feeds[i].map((st) => <QuadStepCard key={st.turn} step={st} />)}
              </div>
            </div>
          )
        })}
      </div>

      {/* canvas + filmstrip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.2fr) minmax(0,1fr)', gap: 28, alignItems: 'start' }}>
        <div style={{ position: 'relative', width: '100%', aspectRatio: '1 / 1', background: '#050505', border: '1px solid rgba(255,255,255,0.12)', overflow: 'hidden' }}>
          {currentImage
            ? <img src={currentImage} alt="quad canvas" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
            : <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span style={{ fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#3a3a3a' }}>awaiting first object</span>
              </div>}
        </div>
        <div>
          <p style={{ ...label, marginBottom: 10 }}>Filmstrip · {framed.length} steps</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, maxHeight: 340, overflowY: 'auto' }}>
            {framed.map((f) => (
              <div key={f.turn} title={f.label ?? `step ${f.turn}`} style={{ width: 64, height: 64, border: '1px solid rgba(255,255,255,0.16)', position: 'relative', overflow: 'hidden', background: '#050505' }}>
                <img src={f.image} alt={f.label ?? ''} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
                <span style={{ position: 'absolute', bottom: 3, left: 5, fontSize: 9, color: '#fff', mixBlendMode: 'difference' }}>{f.turn}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* JUDGE critique band */}
      {critic && (
        <div style={{ marginTop: 48, borderTop: '1px solid rgba(255,255,255,0.12)', paddingTop: 40 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'center', marginBottom: 36 }}>
            <span style={{ width: 10, height: 10, border: '1px solid #fff', borderRadius: '50%', display: 'inline-block' }} />
            <span style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.16em' }}>JUDGE</span>
            <span style={{ ...label }}>Critic · scores the sequential collaboration</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr)', gap: 56, maxWidth: 1120, margin: '0 auto', alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              {SCORE_KEYS.map((k) => {
                const v = Math.max(0, Math.min(10, Number(critic.scores?.[k] ?? 0)))
                return (
                  <div key={k}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16, marginBottom: 10 }}>
                      <span style={{ fontSize: 13, color: '#fff' }}>{SCORE_LABELS[k]}</span>
                      <span style={{ fontSize: 13, color: '#9a9a9a' }}>{Math.round(v * 10)}</span>
                    </div>
                    <div style={{ height: 1, background: 'rgba(255,255,255,0.12)', position: 'relative' }}>
                      <div style={{ position: 'absolute', left: 0, top: 0, height: 1, background: '#fff', width: `${v * 10}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
            <div>
              <p style={{ ...label, marginBottom: 8 }}>Composite</p>
              <p style={{ fontSize: 84, fontWeight: 300, lineHeight: 0.9, letterSpacing: '-0.03em', marginBottom: 22 }}>{(Math.max(0, Math.min(10, composite)) * 10).toFixed(1)}</p>
              {critic.reasoning && <p style={{ fontSize: 14, lineHeight: 1.55, color: '#9a9a9a', marginBottom: 16 }}>{critic.reasoning}</p>}
              {(critic.highlights ?? []).map((h, i) => (
                <p key={i} style={{ fontSize: 12, lineHeight: 1.5, color: '#6d6d6d', marginBottom: 6, paddingLeft: 14, position: 'relative' }}>
                  <span style={{ position: 'absolute', left: 0 }}>·</span>{h}
                </p>
              ))}
            </div>
          </div>
          {critic.final_summary && (
            <p style={{ maxWidth: 880, margin: '44px auto 0', textAlign: 'center', fontSize: 'clamp(20px,2.4vw,28px)', fontWeight: 300, lineHeight: 1.3 }}>
              {`“${critic.final_summary}”`}
            </p>
          )}
        </div>
      )}

      {/* event log */}
      <div style={{ marginTop: 36, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 18 }}>
        <p style={{ fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#4a4a4a', marginBottom: 12 }}>Event Stream</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, maxHeight: 150, overflowY: 'auto' }}>
          {log.slice(-40).map((l, i) => (
            <div key={i} style={{ display: 'flex', gap: 16, fontSize: 11, alignItems: 'baseline' }}>
              <span style={{ color: '#4a4a4a', textTransform: 'uppercase', letterSpacing: '0.14em', flex: '0 0 96px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.type}</span>
              <span style={{ flex: 1, minWidth: 0, color: '#9a9a9a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* full-brief modal */}
      {showBrief && (
        <div
          onClick={() => setShowBrief(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(0,0,0,0.82)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}
        >
          <div onClick={(e) => e.stopPropagation()} style={{ maxWidth: 760, width: '100%', maxHeight: '80vh', overflowY: 'auto', border: '1px solid rgba(255,255,255,0.16)', borderRadius: 16, background: '#0a0a0f', padding: 34 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
              <p style={{ fontSize: 11, letterSpacing: '0.24em', textTransform: 'uppercase', color: '#8d8d8d' }}>Full Brief</p>
              <button onClick={() => setShowBrief(false)} style={{ border: '1px solid rgba(255,255,255,0.28)', background: 'transparent', color: '#fff', borderRadius: '50%', width: 30, height: 30, cursor: 'pointer', fontSize: 15, lineHeight: 1 }}>×</button>
            </div>
            <h3 style={{ fontSize: 'clamp(22px,3vw,34px)', fontWeight: 300, lineHeight: 1.28, marginBottom: 16 }}>{prompt || 'Untitled collaboration'}</h3>
            {style && <p style={{ fontSize: 13, letterSpacing: '0.06em', textTransform: 'uppercase', color: '#9a9a9a' }}>{`Style — ${style}`}</p>}
          </div>
        </div>
      )}
    </div>
  )
}
