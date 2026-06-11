# CanvasMind — Multi-Agent Collaborative AI Painting System

> TCS Research — Computational Creativity Platform

A production-ready desktop application where collaborative AI painting agents (ARIA and NEXUS) negotiate, debate, and converge on a unified artwork in real time, with live streaming text, score gauges, and a shared canvas.

---

## Architecture

```
canvasmind/
├── canvasmind_app.py ⭐ SINGLE-FILE APP — web UI + backend + 3-image co-creation
├── launch.sh / .ps1     One-command launcher (deps + start)
├── simulate_chat.py     Terminal-only demo (agents printed to the console)
├── RUN_ON_VM.md         End-to-end VM guide
├── backend/          FastAPI Python backend (modular multi-agent stack)
│   ├── agents/       ARIA (Director), NEXUS (Challenger), JUDGE (Critic)
│   ├── orchestration/  CreativeOrchestrator — session lifecycle brain
│   ├── canvas/       Shared canvas state and operations
│   ├── session/      Session management, memory compression
│   ├── providers/    AzureOpenAIProvider with retry/streaming
│   ├── websocket/    Real-time event emission
│   ├── persistence/  JSON storage + export service
│   ├── schemas/      Pydantic data models
│   ├── api/          REST endpoints
│   └── simulate_chat.py  (same terminal demo, backend copy)
└── frontend/         Electron + React + TypeScript desktop app
    ├── src/store/    Zustand state management (5 stores)
    ├── src/components/  Agent panels, canvas, critic, controls
    ├── src/services/ WebSocket + REST clients
    └── electron/     Main process + preload
```

> **Deploying to an Azure VM?** See [DEPLOYMENT.md](DEPLOYMENT.md) for the
> complete step-by-step guide: file transfer, virtual environment setup, the
> backend-only simulation, and running behind a reverse proxy.

---

## ⭐ Recommended: one-command launch (single-file app)

The fastest, most reliable way to run everything — frontend **and** backend in
one process on one port, with the **3-image co-creation pipeline**:

```bash
cd canvasmind          # or RL_Multi_Agent_ART/canvasmind
chmod +x launch.sh     # first time only
./launch.sh            # → http://localhost:8000/   (Windows: .\launch.ps1)
```

`launch.sh` checks credentials, installs dependencies if needed, and starts
[`canvasmind_app.py`](canvasmind_app.py). Open the app and choose how to begin:

- **✨ AI Surprise** — click **Surprise Me** and the AI invents a striking brief +
  style on its own (shown in the UI), then creates.
- **✍️ Write my own** — type your own brief and click **Start Co-Creation**.

Then ARIA and NEXUS paint **one shared canvas, step by step**, taking turns to
**add a single new object each turn** (additive collaboration, not refinement):

1. The canvas starts blank; **ARIA** adds the first object → displayed.
2. That canvas is handed to **NEXUS**, which **adds one new object** on top,
   keeping everything already there → displayed.
3. Back to ARIA, then NEXUS… for **N back-and-forths** (default **5 → 10 step
   images**), every step shown in a left-to-right filmstrip.
4. **JUDGE makes no edits** — it scores the collaboration and presents the final
   accumulated canvas as the combined result.

A **⬇ Download all steps** button saves every step image. This path avoids every
reverse-proxy / CORS / port issue — see [RUN_ON_VM.md](RUN_ON_VM.md) for the full
VM walkthrough.

> The single-file app calls Azure via raw REST with `max_completion_tokens` (no
> custom temperature), which is what `gpt-5.2` requires. The terminal-only demo
> `simulate_chat.py` works the same way.

---

## Quick Start (modular stack — advanced/alternative)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your Azure OpenAI credentials
```

Required environment variables:
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_VERSION` (e.g., `2025-04-01-preview`)
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_GPTTEXT52` — your text model deployment (e.g. `gpt-5.2`)
- `AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1` — your image model deployment (e.g. `gpt-image-1`)

> On the VM, `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT` are typically
> exported in the shell; `backend/.env` supplies the version and deployment names.

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend (web)

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### 4. Electron desktop

```bash
cd frontend
npm run electron:dev
```

### 5. Docker

```bash
cp .env.example .env  # fill in values
docker-compose up
```

### 6. Backend-only demo (no frontend, no ports, no proxy)

The most reliable way to see the agents talk — ideal for a remote VM or a quick
manager demo. Runs the full ARIA → NEXUS → JUDGE conversation in the terminal
using the real production classes.

```bash
cd backend
source venv/bin/activate          # or: pip install -r requirements.txt
# Ensure backend/.env has your real Azure credentials, then:
python simulate_chat.py --prompt "A serene mountain lake at golden hour" --rounds 5
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--prompt` | a cyberpunk forest brief | The creative brief the agents work on |
| `--rounds` | `5` | Max negotiation rounds (1–20) |
| `--style` | empty | Optional style hint (e.g. `baroque`, `neon noir`) |

Each round prints ARIA's proposal, NEXUS's challenge, and JUDGE's 5-dimension
scorecard with directives, then detects convergence and prints a score-trend
summary. No browser, WebSocket, or CORS involved.

---

## Running Behind a Reverse Proxy (Sub-Path URL)

If the frontend is served through a proxy at a sub-path, e.g.
`https://host/dev-workspaces/<name>/proxy/3000/`, a default Vite build 404s on
its assets (`main.tsx`, `@react-refresh`, `client`) because Vite uses absolute
paths from the domain root. The fix is already in `vite.config.ts` (production
builds use relative `base: './'`). Run one of:

```bash
# Recommended: production build + preview (relative paths survive the proxy)
cd frontend
npm run build
npm run preview -- --host 0.0.0.0 --port 3000

# Or live dev server — pass the exact proxy prefix:
VITE_BASE=/dev-workspaces/<your-workspace>/proxy/3000/ \
  npm run dev -- --host 0.0.0.0 --port 3000
```

The backend (port 8000) must also be reachable from your browser — either
proxied at `.../proxy/8000/` (set `VITE_BACKEND_URL`/`VITE_WS_URL` accordingly)
or via the VM's public IP. If full wiring is awkward through the proxy, use the
**backend-only demo** above. Full details in [DEPLOYMENT.md](DEPLOYMENT.md) §18.

---

## How It Works

1. User enters a creative prompt
2. System creates a session and launches `CreativeOrchestrator`
3. Each round:
   - **ARIA** (Agent A, Creative Director) proposes a vision
   - **NEXUS** (Agent B, Creative Challenger) responds, challenges or acknowledges
   - Mediation sub-rounds run if dispute detected
   - Canvas operations are extracted and applied
   - **JUDGE** (Critic) evaluates across 5 dimensions (0–10 each)
   - Convergence check: composite ≥ 7.5 + both agents agree
4. Live streaming text appears in agent panels via WebSocket
5. User can intervene, freeze agents, rollback, or force finalize at any time

---

## Session Control

| Action | Keyboard | Effect |
|--------|----------|--------|
| Intervene | Ctrl+I | Inject directive into dialogue |
| Export | Ctrl+E | Open export options |
| Pause/Resume | Ctrl+P | Pause or resume session |
| Toggle panel | Ctrl+B | Show/hide side panel |

---

## API Endpoints

```
POST   /api/sessions              Create session
POST   /api/sessions/{id}/start   Start orchestration
POST   /api/sessions/{id}/pause   Pause
POST   /api/sessions/{id}/resume  Resume
POST   /api/sessions/{id}/intervene  Inject directive
POST   /api/sessions/{id}/freeze/{agent}
POST   /api/sessions/{id}/rollback/{round}
POST   /api/sessions/{id}/finalize
GET    /api/sessions/{id}/export/json
GET    /api/sessions/{id}/export/markdown
GET    /api/sessions/{id}/export/canvas
WS     /ws/{session_id}           Real-time events
GET    /health                    Health check
GET    /health/azure              Azure connectivity test
```

---

## Academic Foundation

Implements the framework from "Computational Creativity: A Multi-Agent Framework for Collaborative Generative Art" (TCS Research):

- Formal inter-agent communication protocol with typed message schema
- Critic evaluation: Compositional Coherence, Style Fidelity, Emotional Resonance, Originality, Clarity of Next Action
- Convergence criteria: score threshold + explicit agent agreement + max rounds
- Canvas as shared structured state with region map, operation history, snapshots
- Session provenance: full audit trail of all agent messages, critic scores, user interventions

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, WebSockets |
| LLM | Azure OpenAI (GPT text + DALL-E image) |
| Frontend | React 18, TypeScript, Vite |
| State | Zustand |
| Animations | Framer Motion |
| Charts | Recharts |
| Styling | TailwindCSS |
| Desktop | Electron |
| Persistence | JSON files (SESSION_STORAGE_PATH) |
