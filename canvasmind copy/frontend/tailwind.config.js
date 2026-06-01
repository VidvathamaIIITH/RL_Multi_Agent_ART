/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0a0a0f',
        'bg-secondary': '#111118',
        'bg-tertiary': '#1a1a24',
        'bg-card': '#16161f',
        'border-primary': '#2a2a3a',
        'border-glow': '#4a4aff',
        'accent-a': '#6366f1',
        'accent-b': '#ec4899',
        'accent-critic': '#f59e0b',
        'accent-success': '#10b981',
        'text-primary': '#f0f0ff',
        'text-secondary': '#8888aa',
        'text-muted': '#444466',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow-a': 'glowA 2s ease-in-out infinite alternate',
        'glow-b': 'glowB 2s ease-in-out infinite alternate',
        'typing': 'typing 1s steps(1) infinite',
        'score-fill': 'scoreFill 0.8s ease-out forwards',
      },
      keyframes: {
        glowA: {
          '0%': { boxShadow: '0 0 10px rgba(99,102,241,0.2)' },
          '100%': { boxShadow: '0 0 25px rgba(99,102,241,0.5)' },
        },
        glowB: {
          '0%': { boxShadow: '0 0 10px rgba(236,72,153,0.2)' },
          '100%': { boxShadow: '0 0 25px rgba(236,72,153,0.5)' },
        },
        typing: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
      },
    },
  },
  plugins: [],
}
