import React, { useEffect } from 'react'
import { useQuadStore } from '../../store/useQuadStore'
import { fetchPersonas, QUAD_HERO_URL } from '../../services/quad.service'
import { launchQuad } from './quadRun'
import { QuadAgentCard } from './QuadAgentCard'

const page: React.CSSProperties = {
  minHeight: '100vh', background: '#000', color: '#fff', overflowY: 'auto',
  fontFamily: "'Inter',system-ui,sans-serif", padding: '48px 40px 70px',
}
const label: React.CSSProperties = {
  fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#8d8d8d',
}
const lineInput: React.CSSProperties = {
  width: '100%', background: 'transparent', border: 'none',
  borderBottom: '1px solid rgba(255,255,255,0.22)', color: '#fff', fontSize: 16,
  padding: '8px 0 12px', outline: 'none',
}

export function QuadConfigDashboard(): JSX.Element {
  const { prompt, style, rounds, setPrompt, setStyle, setRounds, setPersonas, setView } =
    useQuadStore()

  useEffect(() => {
    let cancelled = false
    fetchPersonas()
      .then((r) => { if (!cancelled) setPersonas(r.personas, r.levels) })
      .catch(() => { /* fallback personas already in store */ })
    return () => { cancelled = true }
  }, [setPersonas])

  return (
    <div style={page}>
      {/* glowing hero image (4_Agent_Art.png), like the 2-agent home screen */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 0, backgroundImage: `url(${QUAD_HERO_URL})`, backgroundSize: 'cover', backgroundPosition: 'center' }} />
      <div style={{ position: 'fixed', inset: 0, zIndex: 0, background: 'linear-gradient(90deg, rgba(0,0,0,0.86) 0%, rgba(0,0,0,0.62) 55%, rgba(0,0,0,0.45) 100%), linear-gradient(0deg, rgba(0,0,0,0.7), rgba(0,0,0,0.25))' }} />
      <div style={{ position: 'relative', zIndex: 1 }}>
      <p style={{ fontSize: 11, letterSpacing: '0.3em', textTransform: 'uppercase', color: '#9a9a9a', marginBottom: 18 }}>
        Advanced · Quad-Agent Sequential Pipeline
      </p>
      <h1 style={{ fontSize: 'clamp(34px,6vw,68px)', fontWeight: 300, lineHeight: 1, marginBottom: 14 }}>
        Four minds, in sequence.
      </h1>
      <p style={{ fontSize: 15, color: '#cdcdcd', maxWidth: 640, lineHeight: 1.5, marginBottom: 8 }}>
        Four independently-configured persona agents each add one object per round, in strict order —
        pure additive co-creation, no JUDGE.
      </p>

      <div style={{
        display: 'grid', gridTemplateColumns: '2fr 1fr auto', gap: 26, alignItems: 'end',
        borderTop: '1px solid rgba(255,255,255,0.16)', paddingTop: 30, marginTop: 24,
      }}>
        <div>
          <label style={label}>Global Prompt</label>
          <input style={lineInput} value={prompt} placeholder="Describe the artwork the four agents build together…"
            onChange={(e) => setPrompt(e.target.value)} />
        </div>
        <div>
          <label style={label}>Style Hints</label>
          <input style={lineInput} value={style} placeholder="e.g. oceanic, stormy"
            onChange={(e) => setStyle(e.target.value)} />
        </div>
        <div>
          <label style={label}>Rounds</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
            <button onClick={() => setRounds(rounds - 1)} style={roundBtn}>−</button>
            <span style={{ fontSize: 34, fontWeight: 300, minWidth: 40, textAlign: 'center' }}>{rounds}</span>
            <button onClick={() => setRounds(rounds + 1)} style={roundBtn}>+</button>
          </div>
          <p style={{ fontSize: 11, color: '#8d8d8d', marginTop: 8 }}>{rounds * 4} step images · 4 agents × rounds</p>
        </div>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 18,
        margin: '30px 0 36px',
      }}>
        {[0, 1, 2, 3].map((i) => <QuadAgentCard key={i} index={i} />)}
      </div>

      <div style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={() => { void launchQuad() }} style={{
          background: '#fff', color: '#000', border: 'none', borderRadius: 75,
          padding: '15px 36px', fontSize: 13, fontWeight: 500, letterSpacing: '0.14em',
          textTransform: 'uppercase', cursor: 'pointer',
        }}>
          Launch Quad Session →
        </button>
        <button onClick={() => setView('off')} style={{
          background: 'transparent', color: '#9a9a9a', border: 'none', fontSize: 12,
          letterSpacing: '0.14em', textTransform: 'uppercase', cursor: 'pointer',
        }}>
          ← Back to ARIA · NEXUS
        </button>
      </div>
      </div>
    </div>
  )
}

const roundBtn: React.CSSProperties = {
  width: 34, height: 34, borderRadius: '50%', border: '1px solid rgba(255,255,255,0.28)',
  background: 'transparent', color: '#fff', fontSize: 18, cursor: 'pointer', lineHeight: 1,
}
