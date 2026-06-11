# CanvasMind — Complete Deployment Guide
### Azure VM Setup · File-by-File Reference · End-to-End Run Instructions

---

> ## ⭐ Fastest path (read this first)
> The recommended way to run CanvasMind on the VM is the **single-file app** with
> the **one-command launcher** — no React build, no separate ports, no proxy 404s:
> ```bash
> cd ~/canvasmind && ./launch.sh      # → open .../proxy/8000/
> ```
> It runs the **3-image co-creation pipeline** (ARIA paints a partial image →
> NEXUS builds on it → JUDGE combines both into a final artwork, with a
> *Download all 3 images* button). Full walkthrough: **[RUN_ON_VM.md](RUN_ON_VM.md)**
> and [Section 19](#19-single-file-app--one-command-launcher-recommended) below.
> The detailed modular-stack instructions (Sections 4–14) remain for reference.

---

## Table of Contents

1. [What Is CanvasMind](#1-what-is-canvasmind)
2. [Full Project File Reference](#2-full-project-file-reference)
3. [How the System Works End-to-End](#3-how-the-system-works-end-to-end)
4. [Transferring Files to the Azure VM via VS Code](#4-transferring-files-to-the-azure-vm-via-vs-code)
5. [Azure VM Creation](#5-azure-vm-creation)
6. [Install System Prerequisites on the VM](#6-install-system-prerequisites-on-the-vm)
7. [Set Up Python Virtual Environment](#7-set-up-python-virtual-environment)
8. [Create the .env File](#8-create-the-env-file)
9. [Run Backend Tests to Verify Setup](#9-run-backend-tests-to-verify-setup)
10. [Build the Frontend](#10-build-the-frontend)
11. [Start the Application](#11-start-the-application)
12. [Open Azure Firewall Ports](#12-open-azure-firewall-ports)
13. [Verify Everything Is Running](#13-verify-everything-is-running)
14. [Run as Permanent Background Services](#14-run-as-permanent-background-services)
15. [Troubleshooting Every Possible Error](#15-troubleshooting-every-possible-error)
16. [Quick Command Reference](#16-quick-command-reference)
17. [Backend-Only Agent Simulation (No Frontend Needed)](#17-backend-only-agent-simulation-no-frontend-needed)
18. [Running the Frontend Behind a Reverse Proxy (Sub-Path URL)](#18-running-the-frontend-behind-a-reverse-proxy-sub-path-url)
19. [Single-File App & One-Command Launcher (Recommended)](#19-single-file-app--one-command-launcher-recommended)

---

## 1. What Is CanvasMind

CanvasMind is a **computational creativity research platform** where three AI agents collaborate in real time to produce artwork, negotiate creative decisions, and converge on a unified final design.

### The Three Agents

| Agent | Internal Name | Personality | What It Does |
|---|---|---|---|
| **ARIA** | Creative Director | Visionary | Proposes the overall artistic vision, composition, colour palette, emotional tone |
| **NEXUS** | Creative Challenger | Devil's advocate | Critiques ARIA's proposals, suggests alternatives, pushes creative limits |
| **JUDGE** | Critic | Impartial evaluator | Scores every round across 5 dimensions, detects convergence, guides both agents |

### Architecture at a Glance

```
┌──────────────────────────────────────────────────────────────────────┐
│                         AZURE VM                                      │
│                                                                        │
│   ┌────────────────────────┐       ┌──────────────────────────────┐  │
│   │  FRONTEND — React/Vite │◄─────►│  BACKEND — Python / FastAPI  │  │
│   │  Port 3000             │  WS + │  Port 8000                   │  │
│   │                        │  REST │                              │  │
│   │  • Session dashboard   │       │  • REST API (4 routers)      │  │
│   │  • Live agent chat     │       │  • WebSocket streaming       │  │
│   │  • Canvas viewer       │       │  • AI orchestration          │  │
│   │  • Critic score gauges │       │  • Session persistence       │  │
│   │  • User controls       │       │  • Azure OpenAI calls        │  │
│   └────────────────────────┘       └──────────────┬───────────────┘  │
│                                                    │                   │
└────────────────────────────────────────────────────┼───────────────────┘
                                                     │  HTTPS
                                                     ▼
                                    ┌──────────────────────────────┐
                                    │     AZURE OpenAI SERVICE     │
                                    │  GPT-4o  → agents + critic   │
                                    │  GPT-Image-1 → canvas images │
                                    └──────────────────────────────┘
```

**Security rule (never broken):** Azure credentials live only in `backend/.env`. The frontend never sees them. The browser only ever talks to your own server on localhost or your VM's IP.

---

## 2. Full Project File Reference

This section explains **every single file** in the project so you can explain it precisely.

### Root Layout

```
canvasmind/
├── backend/          Python FastAPI server — all AI logic lives here
├── frontend/         React + TypeScript app — the UI
├── README.md         Quick-start overview
├── DEPLOYMENT.md     This file
```

---

### Backend Files

#### `backend/simulate_chat.py`
A standalone, backend-only script that runs the **entire** ARIA → NEXUS → JUDGE
conversation in the terminal — no frontend, no proxy, no ports. It reuses the
real agent and provider classes, so the dialogue is identical to the full app.
This is the most reliable way to demo CanvasMind on a remote VM. See
[Section 17](#17-backend-only-agent-simulation-no-frontend-needed) for full usage.

#### `backend/main.py`
The application entry point. Does four things in order:
1. Calls `validate_config()` — if any Azure credential is missing, the app exits immediately with a clear error listing what is missing. The server will never start without valid credentials.
2. Creates the FastAPI app object with CORS middleware (allows the frontend to talk to it) and a logging middleware.
3. Registers all four API routers (`/health`, `/api/sessions`, `/api/control`, `/api/export`).
4. Defines the WebSocket endpoint at `/ws/{session_id}` — this is the live streaming channel each browser tab connects to.

#### `backend/config.py`
Reads all environment variables from `.env` and validates them at startup.
- `REQUIRED_VARS` — the 5 Azure credentials that must be present.
- `OPTIONAL_DEFAULTS` — server port, max rounds, storage path (all have sensible defaults).
- `validate_config()` — called by `main.py` at import time. Prints a startup banner showing the endpoint and masked API key (last 4 chars only). Creates the session storage directory if it doesn't exist.
- `Settings` class — a plain Python class holding all config values as typed attributes, imported everywhere else via `from config import settings`.

#### `backend/requirements.txt`
All Python package dependencies with pinned versions:
```
fastapi==0.111.0          Web framework
uvicorn[standard]==0.30.1 ASGI server (runs FastAPI)
websockets==12.0          WebSocket protocol
python-dotenv==1.0.1      Reads .env files
pydantic==2.7.1           Data validation and serialisation
pydantic-settings==2.3.1  Settings management with Pydantic
openai==1.35.7            Azure OpenAI Python SDK
httpx==0.27.0             Async HTTP client
aiofiles==23.2.1          Async file I/O
python-multipart==0.0.9   File upload support
pytest==8.2.2             Test runner
pytest-asyncio==0.23.7    Async test support
anyio==4.4.0              Async I/O compatibility layer
```

#### `backend/pytest.ini`
Configures the test runner:
```ini
[pytest]
asyncio_mode = auto    ← makes all async test functions run automatically
pythonpath = .         ← adds backend/ to Python path so imports resolve
```

---

### `backend/schemas/` — Data Models

Every piece of data that flows through the system is defined here as a Pydantic model. Pydantic automatically validates types, ranges, and required fields. If an AI returns malformed JSON that doesn't match these shapes, it is caught and repaired before it can cause a crash.

#### `backend/schemas/agent_message.py`
Defines what an agent's response looks like.

`MessageIntent` enum — the 7 possible conversational moves an agent can make:
- `PROPOSE` — suggesting a new idea
- `REFINE` — improving the current shared idea
- `DISAGREE` — rejecting the other agent's direction
- `ACKNOWLEDGE` — accepting what the other agent said
- `CHALLENGE` — pushing back with a counter-argument
- `YIELD` — conceding a point
- `FINALIZE` — declaring the work complete

`AgentMessage` fields:
| Field | Type | Meaning |
|---|---|---|
| `id` | UUID string | Unique ID for this message |
| `sender` | string | `"ARIA"` or `"NEXUS"` |
| `round` | int | Which round this was generated in |
| `intent` | MessageIntent | One of the 7 intents above |
| `artistic_goal` | string | What the agent wants to achieve artistically |
| `region` | string (optional) | Which canvas region this concerns |
| `palette` | list of strings | Colour names/hex codes proposed |
| `composition_notes` | string | How elements should be arranged |
| `emotional_register` | string | The mood/emotion the agent targets |
| `reasoning` | string | Why the agent is making this move |
| `next_action` | string | Concrete instruction for what to paint next |
| `critique` | string (optional) | Assessment of the other agent's last move |
| `confidence_score` | float 0–1 | How confident the agent is |
| `is_streaming` | bool | True while tokens are still arriving |
| `is_complete` | bool | True once the full message has been received |

#### `backend/schemas/critic_evaluation.py`
Defines the Judge's evaluation of each round.

`CriticScore` fields (all scored 0–10):
| Field | What It Measures |
|---|---|
| `compositional_coherence` | Do the elements form a balanced, unified composition? |
| `style_fidelity` | Does it match the user's requested style/era? |
| `emotional_resonance` | Does it evoke the intended feeling? |
| `originality` | Is it genuinely creative, not derivative? |
| `clarity_of_next_action` | Is the next step clearly actionable? |
| `composite` (computed) | Automatic average of the 5 scores above |

`CriticEvaluation` fields:
- `scores` — the `CriticScore` object above
- `reasoning` — paragraph explaining the scores
- `contradictions_detected` — list of specific disagreements between agents
- `weak_ideas` — elements the critic thinks need improvement
- `directive_agent_a` — specific instruction to ARIA for next round
- `directive_agent_b` — specific instruction to NEXUS for next round
- `recommended_next_step` — the one most important thing to do
- `convergence_signal` — `True` if the critic thinks the agents have agreed enough

#### `backend/schemas/canvas_operation.py`
Defines a single painting action on the canvas.

`OperationType` enum:
- `paint_region` — apply colour/texture to a grid region
- `add_element` — place a visual element (tree, figure, shape)
- `modify_palette` — change the colour scheme
- `add_texture` — apply surface texture
- `adjust_composition` — rebalance the layout
- `add_annotation` — attach a text note to a region

`CanvasRegion` enum — the 3×3 grid:
```
top_left    | top_center    | top_right
center_left | center        | center_right
bottom_left | bottom_center | bottom_right
                                          + full_canvas
```

#### `backend/schemas/session_schemas.py`
The core data structures for a session.

`SessionStatus` enum — lifecycle states:
`initializing → running → paused → converged / completed / error / cancelled`

`AgentStatus` enum: `active / frozen / waiting / typing`

`CanvasSnapshot` — a saved copy of the canvas at a specific round (used for rollback).

`CanvasStateModel` — tracks the full canvas: current image (base64), all operations history, per-region ownership, contested regions, all snapshots.

`Session` — the master object for an entire session. Contains everything: the user's prompt, status, all messages from both agents, all critic evaluations, the canvas state, agent statuses, convergence score, user interventions, and the finalized plan.

`CreateSessionRequest` — what the frontend sends to create a new session: `prompt`, `title`, `max_rounds`, `style_hint`, `era_hint`.

`InterventionRequest` — what the frontend sends when the user injects a message: `instruction` and `target_agent` (`"aria"`, `"nexus"`, or `"both"`).

`RollbackRequest` — what the frontend sends to revert: `round` number.

#### `backend/schemas/ws_events.py`
Defines all 19 real-time WebSocket events.

`WSEventType` enum:
| Event | When It Fires |
|---|---|
| `session_started` | Orchestrator begins the first round |
| `round_started` | A new round begins |
| `agent_typing_start` | An agent starts generating |
| `agent_typing_end` | Agent generation finished |
| `agent_token` | A single streamed token from an agent |
| `agent_message_complete` | Full agent message ready |
| `critic_evaluation` | Judge has scored the round |
| `critic_token` | Streamed token from the critic |
| `canvas_updated` | New canvas image is ready |
| `round_complete` | Round fully done |
| `session_paused` | User paused |
| `session_resumed` | User resumed |
| `session_converged` | Composite score ≥ 7.5 — done |
| `session_complete` | Session finalised |
| `user_intervention` | User injected an instruction |
| `agent_frozen` | User froze an agent |
| `agent_unfrozen` | User unfroze an agent |
| `error` | Something went wrong |
| `health_ping` | Keep-alive heartbeat |

---

### `backend/providers/` — Azure OpenAI Interface

#### `backend/providers/base_provider.py`
Abstract base class that defines the interface every AI provider must implement. Ensures the system can be swapped to a different provider (OpenAI direct, Anthropic, etc.) without changing the orchestration code.

#### `backend/providers/azure_openai_provider.py`
The only file that ever calls Azure OpenAI. Contains every safeguard:

**Lazy client initialisation** — the Azure client is NOT created at import time (doing so would crash immediately if credentials are missing). It is created on the first actual API call via `_get_client()`:
```python
_client: AzureOpenAI | None = None

def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        _client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
    return _client
```

**Retry with exponential backoff** — every API call goes through `_retry_with_backoff()`. On `RateLimitError`, `APITimeoutError`, or `APIConnectionError` it waits 1s, then 2s, then 4s (plus random jitter) before giving up after 3 attempts.

**30-second timeout** — every API call is wrapped in `asyncio.wait_for(..., timeout=30.0)` so a hanging request never blocks the entire session indefinitely.

**JSON repair** — LLMs sometimes return malformed JSON (markdown fences, trailing commas, truncated responses). `_repair_json()` strips fences, fixes common issues, and finds the last valid closing bracket/brace.

**Key methods:**
- `stream_chat_completion()` — streams text tokens from GPT-4o, yielding each token as it arrives
- `create_agent_response()` — generates a full `AgentMessage` from an agent's system prompt + conversation history
- `generate_critic_evaluation()` — generates a full `CriticEvaluation` from both agents' messages
- `summarize_history()` — compresses long conversation histories to keep context windows manageable
- `generate_canvas_directive()` — creates a text description of what to paint
- `generate_image()` — calls DALL-E / GPT-Image-1 to produce the actual canvas image as base64

---

### `backend/agents/` — The Three AI Agents

#### `backend/agents/base_agent.py`
Abstract base defining the interface all agents share: `generate_message()` which takes the session history and returns an `AgentMessage`.

#### `backend/agents/creative_director.py`
ARIA — the Creative Director. Her system prompt positions her as a visionary artist focused on the overall emotional and compositional narrative. She leads with bold proposals and is instructed to be decisive but open to refinement.

#### `backend/agents/creative_challenger.py`
NEXUS — the Creative Challenger. His system prompt positions him as a critical thinker who never accepts the first idea. He is instructed to always find at least one thing to push back on and propose an alternative, but to converge gracefully once a clear direction emerges.

#### `backend/agents/critic_agent.py`
JUDGE — the Critic. His system prompt instructs him to be impartial, score on all 5 dimensions with detailed reasoning, always give specific actionable directives to each agent, and set `convergence_signal = True` only when he genuinely believes the artistic direction is strong and agreed upon.

---

### `backend/orchestration/` — Session Lifecycle Management

#### `backend/orchestration/orchestrator.py`
The master controller. `CreativeOrchestrator` manages the complete lifecycle of one session.

Key methods:
- `run_session()` — the main async loop. Runs rounds until convergence, max rounds reached, or user cancels. Sets session status throughout.
- `run_single_round()` — one complete round: Agent A speaks → Agent B speaks → (optional mediation) → Critic evaluates → Canvas updates → Convergence check.
- `run_agent_turn()` — gets one agent's response. Handles streaming token-by-token to the frontend via WebSocket, updates agent status (typing/active/waiting), and saves the message.
- `run_mediation()` — if both agents strongly disagree (`DISAGREE` intents), triggers up to 2 mediation sub-rounds to help them find common ground before the critic scores.
- `run_critic()` — asks JUDGE to evaluate the round, broadcasts scores, updates convergence score.
- `check_convergence()` — composite logic: `convergence_signal` from critic + composite score ≥ 7.5 + both agents have yielded/acknowledged = converged.
- `handle_user_intervention()` — injects the user's instruction into both agents' context and broadcasts the intervention event.

#### `backend/orchestration/convergence.py`
Pure function `check_convergence()` that takes the latest `CriticEvaluation` and the session's history and returns `(converged: bool, reason: str)`. Keeps convergence logic isolated and testable.

#### `backend/orchestration/turn_manager.py`
Decides which agent speaks next. Handles frozen agents (if ARIA is frozen, NEXUS goes twice; if both are frozen, the session must be paused).

---

### `backend/session/` — Session Persistence

#### `backend/session/session_manager.py`
Saves and loads sessions as JSON files on disk. Key design decisions:

**Atomic writes** — never writes directly to the final file. Writes to a `.tmp` file first, then renames it. This means a crash during a write never leaves a corrupted session file — you either have the old version or the new version, never a half-written one.

**Async I/O** — all file reads/writes use `asyncio.get_event_loop().run_in_executor()` so they never block the WebSocket event loop.

Key methods:
- `create_session()` — creates a new `Session` object and saves it
- `get_session()` — loads a session from disk by ID
- `save_session()` — atomic write of updated session
- `list_sessions()` — returns all sessions as `SessionSummary` objects (lightweight, no message history)
- `delete_session()` — removes the JSON file
- `rollback_to_round()` — restores the canvas state from a saved snapshot, truncates message history to that round
- `add_message()` — appends an agent message and saves
- `update_critic()` — appends a critic evaluation and saves
- `record_intervention()` — logs a user intervention and saves

#### `backend/session/memory_manager.py`
When a session runs for many rounds, the conversation history passed to each Azure OpenAI call can become very long (and expensive). `MemoryManager` compresses histories that exceed 20 messages by calling the AI to produce a summary, then replacing the old messages with the summary. The agents retain context without the token cost.

---

### `backend/websocket/` — Real-Time Streaming

#### `backend/websocket/ws_manager.py`
`WebSocketManager` — a singleton (one instance shared by the entire app, imported as `ws_manager`). Maintains a dictionary mapping `session_id → list of active WebSocket connections`. Multiple browser tabs can connect to the same session and all receive the same events.

Key methods:
- `connect()` — accepts a new WebSocket and adds it to the session's connection list
- `disconnect()` — removes a WebSocket cleanly
- `broadcast_to_session()` — sends a `WSEvent` to every connected client for a session. Automatically detects and cleans up dead connections (clients that disconnected without notice).
- `send_token()` — convenience method for streaming individual text tokens

#### `backend/websocket/event_emitter.py`
A helper class that wraps `ws_manager` and provides named methods for every event type. Used by the orchestrator so it never constructs raw `WSEvent` objects directly — all event creation is centralised here.

---

### `backend/canvas/` — Canvas Management

#### `backend/canvas/canvas_state.py`
Tracks the logical state of the canvas: which agent owns which region, which regions are contested, the current image bytes, and the history of all operations.

#### `backend/canvas/canvas_manager.py`
Applies `CanvasOperation` objects to the canvas state, takes new snapshots at the end of each round, and handles rollback by restoring from a snapshot.

#### `backend/canvas/canvas_renderer.py`
Calls `generate_image()` on the Azure provider, passing a composed description of the current artistic intent. Receives the image as a base64 string and stores it on the `CanvasStateModel`.

---

### `backend/api/` — REST API Endpoints

#### `backend/api/routes_session.py`
| Method | Path | What It Does |
|---|---|---|
| `POST` | `/api/sessions` | Creates a new session. Body: `CreateSessionRequest` |
| `GET` | `/api/sessions` | Lists all sessions as summaries |
| `GET` | `/api/sessions/{id}` | Gets full session detail |
| `DELETE` | `/api/sessions/{id}` | Deletes a session |

#### `backend/api/routes_control.py`
| Method | Path | What It Does |
|---|---|---|
| `POST` | `/api/sessions/{id}/start` | Starts the orchestration loop in a background task |
| `POST` | `/api/sessions/{id}/pause` | Signals the orchestrator to pause after current round |
| `POST` | `/api/sessions/{id}/resume` | Resumes a paused session |
| `POST` | `/api/sessions/{id}/intervene` | Injects user instruction. Body: `InterventionRequest` |
| `POST` | `/api/sessions/{id}/rollback` | Rolls back canvas to a previous round. Body: `RollbackRequest` |
| `POST` | `/api/sessions/{id}/freeze/{agent}` | Freezes `aria` or `nexus` |
| `POST` | `/api/sessions/{id}/unfreeze/{agent}` | Unfreezes an agent |
| `POST` | `/api/sessions/{id}/finalize` | Forces convergence and ends the session |

#### `backend/api/routes_export.py`
| Method | Path | What It Does |
|---|---|---|
| `GET` | `/api/sessions/{id}/export/json` | Downloads full session as JSON |
| `GET` | `/api/sessions/{id}/export/canvas` | Downloads the final canvas image |
| `GET` | `/api/sessions/{id}/export/transcript` | Downloads the full agent conversation as text |

#### `backend/api/routes_health.py`
| Method | Path | What It Does |
|---|---|---|
| `GET` | `/health` | Returns `{"status":"healthy","azure_connected":true}`. Used to verify the app and Azure connection are alive |

---

### `backend/middleware/`

#### `backend/middleware/logging_middleware.py`
Logs every incoming HTTP request with method, path, and response time. Useful for debugging.

#### `backend/middleware/error_handlers.py`
Registers global exception handlers so unhandled errors return a clean JSON `{"error": "..."}` response instead of a 500 HTML page.

---

### `backend/persistence/`

#### `backend/persistence/storage.py`
Low-level file I/O helpers used by `session_manager.py`.

#### `backend/persistence/export_service.py`
Generates the export files (JSON bundle, canvas image, transcript) from a `Session` object.

---

### `backend/tests/` — Test Suite

All 16 tests pass with no Azure credentials required. They test the logic, not the live API.

#### `backend/tests/test_schemas.py` (5 tests)
- Creates `AgentMessage`, `CriticEvaluation`, `CanvasOperation`, `Session` objects
- Verifies field validation (scores out of range raise errors)
- Verifies `CriticScore.composite` computes correctly
- Verifies `WSEvent` serialises correctly

#### `backend/tests/test_orchestrator.py` (5 tests)
- Session creation and initial state
- Convergence detection logic (score threshold, signal combination)
- Rollback restores correct snapshot
- Mediation triggers correctly on double DISAGREE
- User intervention injects into context

#### `backend/tests/test_azure_provider.py` (3 tests)
- JSON repair correctly handles markdown fences, trailing commas, truncated JSON
- Retry logic waits correct intervals and gives up after 3 attempts
- Lazy client init: importing the provider does not crash without credentials

#### `backend/tests/test_websocket.py` (3 tests)
- WebSocket manager accepts connections and tracks them
- Broadcast reaches all connected clients for a session
- Dead client cleanup removes broken connections without crashing live ones

---

### Frontend Files

#### `frontend/src/main.tsx`
The React entry point. Mounts `<App />` into the `#root` div of `index.html`.

#### `frontend/src/App.tsx`
Root component. Establishes the WebSocket connection on mount, registers all event handlers that update Zustand stores, and renders `<AppLayout />`.

#### `frontend/src/services/api.service.ts`
A thin HTTP client wrapping `fetch`. Provides `get<T>()`, `post<T>()`, `delete()`, `getBlob()`, `getText()` methods that all point to `VITE_BACKEND_URL` (defaulting to `http://localhost:8000`). All REST calls to the backend go through this service. Never calls Azure OpenAI directly.

#### `frontend/src/services/websocket.service.ts`
Manages the WebSocket connection to the backend. Features:
- Auto-reconnect with exponential backoff (up to 5 attempts, max 16-second delay)
- Event subscription system: `wsService.on('agent_token', handler)` — returns an unsubscribe function
- `manualClose` flag to distinguish intentional disconnects from network failures

---

### `frontend/src/store/` — State Management (Zustand)

Zustand is a minimal state management library. Each store is a plain object with state fields and action functions. Components subscribe to just the slices they need.

#### `useSessionStore.ts`
Holds: `sessionId`, `status`, `currentRound`, `maxRounds`, `convergenceScore`, `title`, `userPrompt`, `finalisedPlan`
Actions: `setSession`, `updateStatus`, `incrementRound`, `setConvergenceScore`, `setFinalisedPlan`, `resetSession`

#### `useAgentStore.ts`
Holds: `ariaMessages[]`, `nexusMessages[]`, `ariaStatus`, `nexusStatus`, `currentStreamingMessage`
Actions: `addMessage`, `setAgentStatus`, `startStreaming`, `appendToken`, `completeStreaming`

#### `useCanvasStore.ts`
Holds: `currentImageBase64`, `operationsHistory[]`, `snapshots[]`, `contestedRegions[]`
Actions: `updateCanvas`, `addOperation`, `addSnapshot`, `setContestedRegions`

#### `useCriticStore.ts`
Holds: `evaluations[]`, `latestEvaluation`, `convergenceHistory[]`
Actions: `addEvaluation`, `setLatestEvaluation`

#### `useUIStore.ts`
Holds: all modal open/close states, `activeTab`, `isSidePanelExpanded`, `sessionLog[]`, `wsConnected`, `backendHealthy`, `azureConnected`
Actions: all open/close functions, `addLogEntry`, `setWsConnected`, `setBackendHealthy`, `clearLog`

---

### `frontend/src/types/` — TypeScript Type Definitions

These mirror the backend Pydantic schemas exactly so the frontend has full type safety.

- `agent.types.ts` — `AgentMessage`, `MessageIntent`, `AgentStatus`
- `session.types.ts` — `Session`, `SessionStatus`, `CanvasState`, `CanvasSnapshot`
- `critic.types.ts` — `CriticEvaluation`, `CriticScore`
- `ws.types.ts` — `WSEvent`, `WSEventType` (all 19 event types)
- `ui.types.ts` — `ActiveTab`, `LogEntry`

---

### `frontend/src/components/` — UI Components

#### Layout
- `AppLayout.tsx` — master layout: top bar + side panel + main content area
- `TopBar.tsx` — session title, status badge, WebSocket indicator, Azure connection indicator
- `SidePanel.tsx` — collapsible panel containing SessionLog
- `StatusIndicator.tsx` — green/yellow/red dot showing connection and health state

#### Canvas
- `CanvasPanel.tsx` — container component for the canvas section
- `CanvasViewer.tsx` — displays the current canvas image with a 3×3 grid overlay
- `CanvasOverlay.tsx` — SVG layer on top of the canvas showing region ownership (which agent owns which area, contested regions in orange)
- `CanvasTimeline.tsx` — horizontal scrollable strip of canvas thumbnails at each round — click any to view that round's canvas
- `CanvasControls.tsx` — zoom, fullscreen, download buttons

#### Agents
- `AgentPanel.tsx` — scrolling feed of both agents' messages, alternating left/right
- `AgentMessage.tsx` — a single message card showing intent badge, artistic goal, reasoning, next action, confidence bar
- `AgentHeader.tsx` — agent avatar, name, status (typing animation when streaming)
- `IntentBadge.tsx` — coloured pill showing the intent (PROPOSE = blue, DISAGREE = red, FINALIZE = green, etc.)

#### Critic
- `CriticPanel.tsx` — container for the judge's panel
- `CriticReport.tsx` — full evaluation card: scores + reasoning + directives
- `ScoreGauge.tsx` — animated arc gauge showing a score from 0–10 with colour gradient (red → amber → green)
- `ScoreHistory.tsx` — Recharts line chart showing how each score changes round by round
- `NextActionCard.tsx` — prominent card showing `recommended_next_step`

#### Controls
- `SessionControls.tsx` — the main action bar: Start / Pause / Resume / Finalize / Rollback / Intervene / Export buttons
- `FreezeAgentToggle.tsx` — toggle switches to freeze/unfreeze ARIA or NEXUS
- `InterventionModal.tsx` — dialog for typing an instruction to inject
- `RollbackModal.tsx` — dialog for choosing which round to roll back to
- `ExportModal.tsx` — dialog showing export options (JSON / canvas image / transcript)
- `LoadSessionModal.tsx` — dialog listing existing sessions to load

#### Prompt
- `PromptInput.tsx` — the initial prompt entry form shown when no session is active

#### Shared
- `GlowButton.tsx` — styled button with glow animation on hover
- `TypingIndicator.tsx` — three-dot animated indicator shown when an agent is generating
- `RoundIndicator.tsx` — displays `Round 3 / 10` with a progress arc
- `ConvergenceMeter.tsx` — large animated gauge showing the overall convergence score
- `SessionLog.tsx` — scrolling list of timestamped log entries from `useUIStore.sessionLog`
- `LoadingSpinner.tsx` — simple spinner for async states
- `AnimatedBadge.tsx` — pill badge with entrance animation

---

### `frontend/package.json`
Node.js project manifest. Key fields:
- `"type": "module"` — tells Node to treat `.js` files as ES modules (required for Vite + PostCSS)
- `"main": "dist-electron/main.js"` — Electron entry point for desktop app mode
- `scripts.build` — `tsc && vite build` — TypeScript check then production bundle
- `scripts.dev` — `vite` — start dev server with hot reload
- `scripts.electron:dev` — runs Vite and Electron concurrently for desktop development

---

## 3. How the System Works End-to-End

```
User opens browser → types a prompt → clicks "Start Session"
         │
         ▼
Frontend: POST /api/sessions          { prompt, title, max_rounds }
Backend:  Creates Session object, saves to ./data/sessions/{uuid}.json
Frontend: receives Session with session_id
         │
         ▼
Frontend: POST /api/sessions/{id}/start
Backend:  Spawns background task → CreativeOrchestrator.run_session()
Frontend: Opens WebSocket ws://.../ws/{session_id}
         │
         ▼ ROUND LOOP (repeats up to max_rounds times)
         │
         ├─ Emit: round_started
         │
         ├─ ARIA's turn:
         │    Emit: agent_typing_start (ARIA)
         │    Call Azure GPT-4o with streaming=True
         │    Each token → Emit: agent_token  ← frontend shows typing in real time
         │    Emit: agent_message_complete (full AgentMessage)
         │    Save message to session file
         │
         ├─ NEXUS's turn:
         │    Same as ARIA above
         │
         ├─ (Optional) Mediation sub-rounds if both agents sent DISAGREE
         │
         ├─ JUDGE evaluates:
         │    Call Azure GPT-4o with both messages as context
         │    Emit: critic_evaluation (CriticEvaluation with all 5 scores)
         │    Save evaluation to session file
         │
         ├─ Canvas update:
         │    Generate paint directive from artistic intent
         │    Call Azure GPT-Image-1 → new canvas image (base64)
         │    Emit: canvas_updated
         │    Save canvas snapshot to session file
         │
         ├─ Check convergence:
         │    composite_score ≥ 7.5 AND convergence_signal == True → CONVERGED
         │    Emit: session_converged → loop ends
         │
         └─ Otherwise → next round
         │
         ▼
User can intervene at any time:
  POST /api/sessions/{id}/pause        → sets _paused flag, loop stops after current round
  POST /api/sessions/{id}/intervene    → injects instruction, Emit: user_intervention
  POST /api/sessions/{id}/rollback     → restores canvas snapshot, truncates history
  POST /api/sessions/{id}/freeze/aria  → removes ARIA from turn rotation
  POST /api/sessions/{id}/finalize     → forces convergence immediately
         │
         ▼
Session ends → POST /api/sessions/{id}/export/json
Frontend downloads complete session bundle
```

---

## 4. Transferring Files to the Azure VM via VS Code

Since you have VS Code on the VM, this is the simplest transfer method.

### Method A — VS Code Remote SSH (Recommended)

This lets you work directly on the VM from your local VS Code.

**On your local machine:**

1. Install the **Remote - SSH** extension in VS Code:
   - Open VS Code → Extensions (`Ctrl+Shift+X`) → search `Remote - SSH` → Install

2. Press `F1` → type `Remote-SSH: Connect to Host` → `+ Add New SSH Host`

3. Enter:
   ```
   ssh -i C:\Users\vidva\Downloads\your-key.pem azureuser@<YOUR_VM_PUBLIC_IP>
   ```

4. Press `F1` → `Remote-SSH: Connect to Host` → select your VM

5. VS Code reopens connected to the VM. You now see the VM's filesystem in the Explorer panel.

6. Open the VS Code Explorer (`Ctrl+Shift+E`) → right-click → **Upload files** or simply **drag and drop** your `canvasmind` folder from Windows Explorer into the VS Code Explorer panel.

The files are now on the VM at `/home/azureuser/canvasmind/`.

---

### Method B — Copy with SCP from the VS Code Integrated Terminal

1. On your **local** machine, open VS Code
2. Open the integrated terminal (`Ctrl+`` `)
3. Run:
```bash
scp -r -i "C:\Users\vidva\Downloads\your-key.pem" \
  "C:\Users\vidva\Downloads\Perfect_Chatbot\canvasmind" \
  azureuser@<YOUR_VM_IP>:~/
```

This copies the entire `canvasmind` folder to `/home/azureuser/canvasmind/` on the VM.

---

### What NOT to Transfer (Exclude These)

These folders are large, auto-generated, and must NOT be copied — they will be rebuilt on the VM:

| Folder | Why Exclude | Rebuilt By |
|---|---|---|
| `frontend/node_modules/` | 300MB+ of packages | `npm install` |
| `frontend/dist/` | Compiled frontend | `npm run build` |
| `backend/venv/` | Python virtual environment | `pip install -r requirements.txt` |
| `backend/__pycache__/` | Python bytecode cache | Python auto-generates |
| `backend/data/` | Session data files | Created at runtime |
| `backend/.env` | Your secret credentials | You create this on the VM |

**How to zip cleanly before transferring (run in PowerShell on your local machine):**

```powershell
# This creates a clean zip at C:\Users\vidva\Downloads\canvasmind_clean.zip
# that excludes all the large/generated folders

$source  = "C:\Users\vidva\Downloads\Perfect_Chatbot\canvasmind"
$archive = "C:\Users\vidva\Downloads\canvasmind_clean.zip"

if (Test-Path $archive) { Remove-Item $archive }

# Copy to a temp folder, strip unwanted dirs, zip
$tmp = "C:\Users\vidva\Downloads\canvasmind_tmp"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Copy-Item $source $tmp -Recurse

$exclude = @("node_modules","__pycache__",".pytest_cache","dist",
             "dist-electron","release","venv","data",".env",".git")
foreach ($dir in $exclude) {
    Get-ChildItem $tmp -Filter $dir -Recurse -Directory |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem $tmp -Filter $dir -Recurse -File |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

Add-Type -Assembly "System.IO.Compression.FileSystem"
[System.IO.Compression.ZipFile]::CreateFromDirectory($tmp, $archive)
Remove-Item $tmp -Recurse -Force
Write-Host "Clean zip ready: $archive"
```

Then drag `canvasmind_clean.zip` into VS Code Explorer on the VM and unzip it in the VS Code terminal:
```bash
cd ~
unzip canvasmind_clean.zip
```

---

## 5. Azure VM Creation

### Recommended Specifications

| Setting | Value |
|---|---|
| Image | **Ubuntu Server 22.04 LTS** |
| Size | **Standard B2s** (2 vCPU, 4 GB) minimum — **B4ms** (4 vCPU, 16 GB) for demos |
| Region | Same region as your Azure OpenAI resource (reduces latency) |
| Authentication | SSH public key |
| Username | `azureuser` |
| Public inbound port | SSH (22) — add others after creation |
| OS Disk | Standard SSD 30 GB |

### After the VM Is Created — Open Required Ports

Go to: **Azure Portal → Your VM → Networking → Add inbound port rule**

| Priority | Name | Port | Protocol |
|---|---|---|---|
| 310 | Allow-Backend | **8000** | TCP |
| 320 | Allow-Frontend | **3000** | TCP |

---

## 6. Install System Prerequisites on the VM

Open the VS Code integrated terminal connected to the VM (`Ctrl+`` `) and run each block.

### Step 1 — Update the system

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

### Step 2 — Install Python 3.11

```bash
sudo apt-get install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip
```

Verify:
```bash
python3.11 --version
# Must print: Python 3.11.x
```

### Step 3 — Install Node.js 20 and npm

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

Verify:
```bash
node --version    # Must print: v20.x.x
npm --version     # Must print: 10.x.x
```

### Step 4 — Install utilities

```bash
sudo apt-get install -y unzip curl git build-essential tmux
```

---

## 7. Set Up Python Virtual Environment

Run all commands from the VS Code terminal.

```bash
# Navigate to the backend folder
cd ~/canvasmind/backend

# Create the virtual environment using Python 3.11 specifically
python3.11 -m venv venv

# Activate it — you MUST do this every time you open a new terminal
source venv/bin/activate

# Your terminal prompt should now start with (venv)

# Upgrade pip to latest (prevents install failures)
pip install --upgrade pip setuptools wheel

# Install all dependencies
pip install -r requirements.txt
```

Verify all packages installed:
```bash
pip list | grep -E "fastapi|uvicorn|pydantic|openai|websockets"
```

Expected:
```
fastapi            0.111.0
openai             1.35.7
pydantic           2.7.1
pydantic-settings  2.3.1
uvicorn            0.30.1
websockets         12.0
```

---

## 8. Create the .env File

This is the most critical step. The app will not start without it.

In the VS Code terminal:

```bash
cd ~/canvasmind/backend
nano .env
```

Paste this template and fill in your actual values:

```bash
# ─────────────────────────────────────────────────────────────
# CanvasMind — Azure OpenAI Credentials
# Find these in: Azure Portal → Your OpenAI Resource → Keys and Endpoint
# ─────────────────────────────────────────────────────────────

AZURE_OPENAI_API_KEY=paste_your_key_1_here
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE-NAME.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01

# These are your deployment names from Azure AI Studio → Deployments
AZURE_OPENAI_DEPLOYMENT_GPTTEXT52=your_gpt4o_deployment_name
AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1=your_dalle3_deployment_name

# ─────────────────────────────────────────────────────────────
# Optional — leave as-is unless you have a reason to change
# ─────────────────────────────────────────────────────────────
BACKEND_PORT=8000
WS_PORT=8001
FRONTEND_PORT=3000
MAX_ROUNDS=10
SESSION_TIMEOUT=300
LOG_LEVEL=INFO
SESSION_STORAGE_PATH=./data/sessions
```

**Save:** `Ctrl+X` → `Y` → `Enter`

**Secure the file** (only your user can read it):
```bash
chmod 600 .env
```

**Create the data directory:**
```bash
mkdir -p ~/canvasmind/backend/data/sessions
```

### Where to Find Your Azure Values

| Variable | Location in Azure Portal |
|---|---|
| `AZURE_OPENAI_API_KEY` | Portal → Your OpenAI Resource → **Keys and Endpoint** → Key 1 |
| `AZURE_OPENAI_ENDPOINT` | Portal → Your OpenAI Resource → **Keys and Endpoint** → Endpoint URL |
| `AZURE_OPENAI_API_VERSION` | Use `2024-02-01` (works with all current models) |
| `AZURE_OPENAI_DEPLOYMENT_GPTTEXT52` | **Azure AI Studio** → Deployments → your GPT-4o deployment → Deployment name |
| `AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1` | **Azure AI Studio** → Deployments → your DALL-E 3 or GPT-Image-1 deployment → Deployment name |

---

## 9. Run Backend Tests to Verify Setup

Run this before starting the server. If all 16 pass, everything is configured correctly.

```bash
cd ~/canvasmind/backend
source venv/bin/activate

python -m pytest tests/test_schemas.py tests/test_orchestrator.py \
       tests/test_azure_provider.py tests/test_websocket.py -v
```

### Expected Output

```
tests/test_schemas.py::test_agent_message_creation PASSED
tests/test_schemas.py::test_critic_evaluation_composite_score PASSED
tests/test_schemas.py::test_canvas_operation_creation PASSED
tests/test_schemas.py::test_session_status_enum PASSED
tests/test_schemas.py::test_ws_event_creation PASSED
tests/test_orchestrator.py::test_session_creation PASSED
tests/test_orchestrator.py::test_convergence_detection PASSED
tests/test_orchestrator.py::test_session_rollback PASSED
tests/test_orchestrator.py::test_mediation_trigger PASSED
tests/test_orchestrator.py::test_user_intervention PASSED
tests/test_azure_provider.py::test_json_repair PASSED
tests/test_azure_provider.py::test_retry_logic PASSED
tests/test_azure_provider.py::test_lazy_client_init PASSED
tests/test_websocket.py::test_ws_connection PASSED
tests/test_websocket.py::test_ws_broadcast PASSED
tests/test_websocket.py::test_dead_client_cleanup PASSED

======= 16 passed in X.XXs =======
```

If any test fails, see [Section 15 — Troubleshooting](#15-troubleshooting-every-possible-error).

---

## 10. Build the Frontend

```bash
cd ~/canvasmind/frontend

# Install all Node.js packages (~300MB, takes 1–3 minutes)
npm install

# Set backend URL (if your VM has a public IP and you're accessing from another machine)
# Create a .env file for the frontend:
cat > .env << 'EOF'
VITE_BACKEND_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
EOF
# If accessing from outside the VM, replace localhost with your VM's public IP:
# VITE_BACKEND_URL=http://<YOUR_VM_PUBLIC_IP>:8000
# VITE_WS_URL=ws://<YOUR_VM_PUBLIC_IP>:8000

# Build the production bundle
npm run build
```

### Expected Build Output

```
vite v5.4.21 building for production...
✓ 1242 modules transformed.
dist/index.html                  0.78 kB
dist/assets/index-*.css         22.73 kB
dist/assets/index-*.js         697.64 kB
✓ built in ~9s
```

The `dist/` folder is the production frontend ready to serve.

---

## 11. Start the Application

You need two processes running simultaneously. Use VS Code's split terminal feature:

**Split the terminal:** Click the split terminal button in VS Code's terminal panel (or press `Ctrl+Shift+5`)

### Terminal 1 — Backend

```bash
cd ~/canvasmind/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

You should see the startup banner:
```
════════════════════════════════════════════════════════════
  CanvasMind — Multi-Agent Creative AI Painting System
════════════════════════════════════════════════════════════
  Azure Endpoint  : https://your-resource.openai.azure.com/
  API Key         : ****ab12
  API Version     : 2024-02-01
  Text Deployment : your-text-deployment
  Image Deployment: your-image-deployment
  Backend Port    : 8000
════════════════════════════════════════════════════════════

INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

**If you see this → backend is running perfectly.**

If you see `[FATAL] Missing required environment variables` → go back to [Section 8](#8-create-the-env-file) and fill in your `.env`.

### Terminal 2 — Frontend

```bash
cd ~/canvasmind/frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

You should see:
```
  VITE v5.4.21  ready in 312 ms

  ➜  Local:   http://localhost:3000/
  ➜  Network: http://0.0.0.0:3000/
```

---

## 12. Open Azure Firewall Ports

In **Azure Portal → Your VM → Networking → Inbound port rules → Add inbound port rule**:

### Rule 1 — Backend API
- Source: Any
- Source port ranges: *
- Destination: Any
- Destination port ranges: **8000**
- Protocol: TCP
- Action: Allow
- Priority: 310
- Name: Allow-CanvasMind-Backend

### Rule 2 — Frontend
- Destination port ranges: **3000**
- Priority: 320
- Name: Allow-CanvasMind-Frontend

---

## 13. Verify Everything Is Running

### From inside the VM (VS Code terminal)

```bash
# Test backend health
curl http://localhost:8000/health
```
Expected: `{"status":"healthy","azure_connected":true,"version":"1.0.0"}`

```bash
# Test API docs are up
curl -s http://localhost:8000/docs | grep -c "CanvasMind"
```
Expected: a number greater than 0

```bash
# Check both ports are listening
sudo ss -tlnp | grep -E "8000|3000"
```

### From your local machine browser

Open these URLs (replace with your VM's public IP):

| URL | What You Should See |
|---|---|
| `http://<VM_IP>:3000` | CanvasMind React frontend — dark theme UI with prompt input |
| `http://<VM_IP>:8000/docs` | FastAPI Swagger UI — all API endpoints listed and testable |
| `http://<VM_IP>:8000/health` | `{"status":"healthy","azure_connected":true}` |

### Create a Test Session via the Swagger UI

1. Go to `http://<VM_IP>:8000/docs`
2. Click `POST /api/sessions` → `Try it out`
3. Paste this body:
```json
{
  "prompt": "A serene mountain lake at golden hour",
  "title": "Test Session",
  "max_rounds": 3
}
```
4. Click `Execute`
5. Expected: `201 Created` with a full `Session` JSON object including a `session_id`

This confirms the backend, Pydantic schemas, and session persistence all work.

---

## 14. Run as Permanent Background Services

These systemd services make the app start automatically on VM reboot and keep running if a terminal closes.

### Create backend service

```bash
sudo nano /etc/systemd/system/canvasmind-backend.service
```

Paste:
```ini
[Unit]
Description=CanvasMind Backend API
After=network.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser/canvasmind/backend
Environment="PATH=/home/azureuser/canvasmind/backend/venv/bin"
EnvironmentFile=/home/azureuser/canvasmind/backend/.env
ExecStart=/home/azureuser/canvasmind/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Save: `Ctrl+X → Y → Enter`

### Create frontend service

```bash
sudo nano /etc/systemd/system/canvasmind-frontend.service
```

Paste:
```ini
[Unit]
Description=CanvasMind Frontend
After=network.target canvasmind-backend.service

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser/canvasmind/frontend
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0 --port 3000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Enable and start both services

```bash
sudo systemctl daemon-reload
sudo systemctl enable canvasmind-backend canvasmind-frontend
sudo systemctl start canvasmind-backend canvasmind-frontend
```

### Check status

```bash
sudo systemctl status canvasmind-backend
sudo systemctl status canvasmind-frontend
```

Both should show `Active: active (running)`.

### View live logs

```bash
# Backend logs
sudo journalctl -u canvasmind-backend -f

# Frontend logs
sudo journalctl -u canvasmind-frontend -f
```

---

## 15. Troubleshooting Every Possible Error

### Backend won't start

| Error Message | Cause | Fix |
|---|---|---|
| `[FATAL] Missing required environment variables` | `.env` file missing or incomplete | Create `.env` in `backend/` with all 5 Azure vars |
| `ModuleNotFoundError: No module named 'fastapi'` | Virtual environment not activated | Run `source venv/bin/activate` |
| `ModuleNotFoundError: No module named 'fastapi'` (even with venv active) | Dependencies not installed | Run `pip install -r requirements.txt` |
| `Address already in use — port 8000` | Another process is using port 8000 | Run `sudo fuser -k 8000/tcp` then retry |
| `python3.11: command not found` | Python 3.11 not installed | Re-run Section 6 Step 2 |
| `Permission denied: ./data/sessions` | Directory doesn't exist or wrong owner | Run `mkdir -p ~/canvasmind/backend/data/sessions` |

### Azure OpenAI errors

| Error | Cause | Fix |
|---|---|---|
| `openai.AuthenticationError: 401` | Wrong API key | Check `AZURE_OPENAI_API_KEY` in `.env` — copy again from Azure Portal |
| `openai.NotFoundError: 404` | Wrong deployment name | Check deployment names in **Azure AI Studio → Deployments** — names are case-sensitive |
| `openai.BadRequestError: 400` | Wrong endpoint format | Endpoint must end with `/` e.g. `https://name.openai.azure.com/` |
| `openai.RateLimitError: 429` | Too many requests | The retry logic handles this automatically — if it keeps happening, check your Azure quota |
| `openai.APIConnectionError` | Network unreachable | Check Azure NSG allows outbound HTTPS; check VM internet connectivity |

### Frontend errors

| Error | Cause | Fix |
|---|---|---|
| `npm: command not found` | Node.js not installed | Re-run Section 6 Step 3 |
| `EACCES: permission denied node_modules` | npm permissions issue | Run `sudo chown -R azureuser:azureuser ~/canvasmind/frontend` |
| TypeScript errors during `npm run build` | Type errors in source | Run `npx tsc --noEmit` to see details |
| Blank white page in browser | Backend unreachable or wrong URL | Check `VITE_BACKEND_URL` in `frontend/.env` matches your VM IP |
| WebSocket connection fails | Port 8000 blocked | Add inbound rule for port 8000 in Azure Portal → VM → Networking |

### Port and network issues

| Symptom | Fix |
|---|---|
| `Connection refused` on port 8000 from outside | Add NSG inbound rule for port 8000 (Section 12) |
| `Connection refused` on port 3000 from outside | Add NSG inbound rule for port 3000 (Section 12) |
| `curl: (7) Failed to connect` from inside VM | Service not running; check `sudo systemctl status canvasmind-backend` |
| Health endpoint returns `azure_connected: false` | Azure credentials valid but Azure API unreachable — check Azure service status |

### Tests fail

| Test Failure | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` on any test | Wrong working directory | Must run `pytest` from `~/canvasmind/backend/` with venv active |
| `asyncio: no running event loop` | pytest-asyncio not configured | Verify `pytest.ini` exists in `backend/` with `asyncio_mode = auto` |
| `ImportError: cannot import name 'ConfigDict'` | Pydantic version too old | Run `pip install pydantic==2.7.1` |

---

## 16. Quick Command Reference

```bash
# ── Activate Python environment (run first in every new terminal) ──
source ~/canvasmind/backend/venv/bin/activate

# ── Start backend (manual) ──
cd ~/canvasmind/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# ── Start frontend (manual) ──
cd ~/canvasmind/frontend
npm run dev -- --host 0.0.0.0 --port 3000

# ── Run all backend tests ──
cd ~/canvasmind/backend
python -m pytest tests/test_schemas.py tests/test_orchestrator.py \
       tests/test_azure_provider.py tests/test_websocket.py -v

# ── Test backend health ──
curl http://localhost:8000/health

# ── Check what is listening on key ports ──
sudo ss -tlnp | grep -E "8000|3000"

# ── Restart both systemd services ──
sudo systemctl restart canvasmind-backend canvasmind-frontend

# ── View live backend logs ──
sudo journalctl -u canvasmind-backend -f

# ── View live frontend logs ──
sudo journalctl -u canvasmind-frontend -f

# ── Check service status ──
sudo systemctl status canvasmind-backend
sudo systemctl status canvasmind-frontend

# ── Stop both services ──
sudo systemctl stop canvasmind-backend canvasmind-frontend

# ── Kill whatever is using port 8000 ──
sudo fuser -k 8000/tcp

# ── See backend process ──
ps aux | grep uvicorn

# ── Check .env is present and readable ──
ls -la ~/canvasmind/backend/.env

# ── Re-run frontend build after code changes ──
cd ~/canvasmind/frontend && npm run build

# ── Update frontend .env for external access ──
echo "VITE_BACKEND_URL=http://<YOUR_VM_IP>:8000" > ~/canvasmind/frontend/.env
echo "VITE_WS_URL=ws://<YOUR_VM_IP>:8000" >> ~/canvasmind/frontend/.env
npm run build
```

---

## Final Checklist Before Going Live

Run through this list in order. Every item must be checked.

- [ ] All project files are on the VM at `~/canvasmind/`
- [ ] `node_modules/`, `venv/`, `__pycache__/`, `dist/` are NOT in the transferred files (they are built on VM)
- [ ] Python 3.11 installed: `python3.11 --version` prints `3.11.x`
- [ ] Node.js 20 installed: `node --version` prints `v20.x.x`
- [ ] Virtual environment created at `backend/venv/`
- [ ] Virtual environment activated: prompt shows `(venv)`
- [ ] All pip packages installed: `pip list` shows fastapi, openai, pydantic, uvicorn
- [ ] `.env` file created at `backend/.env` with all 5 Azure variables filled
- [ ] `.env` permissions set: `ls -la backend/.env` shows `-rw-------`
- [ ] `data/sessions/` directory exists: `ls ~/canvasmind/backend/data/`
- [ ] All 16 tests pass: `python -m pytest tests/ -v` shows `16 passed`
- [ ] Frontend npm packages installed: `node_modules/` exists in `frontend/`
- [ ] Frontend built successfully: `dist/` exists in `frontend/`
- [ ] Backend starts and shows startup banner: `uvicorn main:app --host 0.0.0.0 --port 8000`
- [ ] Health check passes: `curl http://localhost:8000/health` returns `{"status":"healthy",...}`
- [ ] Azure port 8000 open in NSG
- [ ] Azure port 3000 open in NSG
- [ ] Browser can reach frontend at `http://<VM_IP>:3000`
- [ ] Browser can reach API docs at `http://<VM_IP>:8000/docs`

---

## 17. Backend-Only Agent Simulation (No Frontend Needed)

This is the **most reliable way to demo CanvasMind on a remote VM**. It runs the
entire three-agent conversation (ARIA → NEXUS → JUDGE) directly in the terminal
with their real personalities. There is **no frontend, no proxy, no ports, no
WebSocket, no CORS** — so none of the browser/proxy issues can ever affect it.
It only needs Azure credentials in `backend/.env` and internet access.

Use this when:
- You want to show your manager the agents actually talking and converging.
- The frontend is blocked by a corporate reverse proxy (see Section 18).
- You want to confirm your Azure credentials and deployments work end-to-end.

### The file: `backend/simulate_chat.py`

It reuses the **real production classes** — `AzureOpenAIProvider`,
`CreativeDirector` (ARIA), `CreativeChallenger` (NEXUS), `CriticAgent` (JUDGE) —
so the dialogue is identical to what the full app produces. Nothing is mocked.

What it does each round:
1. **ARIA** (Creative Director) proposes a concrete artistic direction.
2. **NEXUS** (Creative Challenger) challenges a weakness or proposes a richer alternative.
3. **JUDGE** (Critic) scores the round on all 5 dimensions, lists contradictions
   and weak ideas, and gives a specific directive to each agent.
4. Convergence is checked (composite ≥ 7.5 **and** the critic's convergence signal).
   When reached, the session ends and prints a summary with the full score trend.

### How to run it on the VM

```bash
cd ~/canvasmind/backend
source venv/bin/activate

# Make sure backend/.env has your REAL Azure credentials (see Section 8).

# Default run (5 rounds, a built-in cyberpunk prompt):
python simulate_chat.py

# Custom creative brief and round count:
python simulate_chat.py --prompt "A serene mountain lake at golden hour" --rounds 5

# With an optional style hint:
python simulate_chat.py --prompt "A cathedral interior" --rounds 6 --style "baroque chiaroscuro"
```

### Command-line options

| Flag | Default | Meaning |
|---|---|---|
| `--prompt` | a cyberpunk forest brief | The creative brief the agents collaborate on |
| `--rounds` | `5` | Maximum negotiation rounds (clamped to 1–20) |
| `--style` | empty | Optional style hint (e.g. `impressionist`, `neon noir`) |

### What you will see

```
══════════════════════════════════════════════════════════════
  CanvasMind — Multi-Agent Creative AI Painting System
  Azure Endpoint  : https://your-resource.openai.azure.com/
  API Key         : ****ab12
  ...
══════════════════════════════════════════════════════════════

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ROUND 1 / 5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ARIA is composing ....
┌─ ARIA (Creative Director)   intent=propose · confidence=85%
│ Artistic goal: ...
│ Palette: #1a2b3c  #d4af37 ...
│ Composition: ...
│ Next action → ...
└────────────────────────────────────────────────────────────

  NEXUS is examining ....
┌─ NEXUS (Creative Challenger)   intent=challenge · confidence=78%
│ Critique: ...
│ Next action → ...
└────────────────────────────────────────────────────────────

╔═ JUDGE (Critic Agent) — Round 1
║  Compositional Coherence  ███████░░░ 7.0
║  Style Fidelity           ████████░░ 8.0
║  ...
║  COMPOSITE                ███████░░░ 7.4
║  → Directive for ARIA: ...
║  → Directive for NEXUS: ...
╚════════════════════════════════════════════════════════════
```

### Troubleshooting the simulation

| Symptom | Cause | Fix |
|---|---|---|
| `[CanvasMind] FATAL: Missing required environment variables` | `.env` not filled in | Add all 5 Azure values to `backend/.env` (Section 8) |
| `Error code: 401 ... invalid subscription key` | Wrong API key or endpoint | Re-copy `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT` from the Azure Portal |
| `Error code: 404` | Wrong deployment name | Check `AZURE_OPENAI_DEPLOYMENT_GPTTEXT52` matches your Azure AI Studio deployment exactly |
| `UnicodeEncodeError` on Windows | cp1252 console | The script forces UTF-8 automatically; if you copied an older version, re-pull this file |
| Agents fail but no crash | Network/Azure issue | Each agent failure is caught and reported per-round; check VM outbound HTTPS |

---

## 18. Running the Frontend Behind a Reverse Proxy (Sub-Path URL)

Many corporate / cloud dev environments expose the VM through a reverse proxy at
a **sub-path**, for example:

```
https://rniazure.tcsapps.com/dev-workspaces/RAMA-GPU-A100/proxy/3000/
```

### The problem

By default, Vite writes asset links as **absolute paths from the domain root**
(`/src/main.tsx`, `/@vite/client`, `/@react-refresh`). Behind a sub-path proxy
the browser then requests `https://host/src/main.tsx` — which **drops the
`/dev-workspaces/.../proxy/3000/` prefix** — and the proxy returns **404**. The
page loads blank with console errors like:

```
Failed to load resource: 404  main.tsx
Failed to load resource: 404  @react-refresh
Failed to load resource: 404  client
```

(The `copy-paste-disable.js` 404 is injected by the proxy itself, not by us — ignore it.)

### The fix (already applied in `vite.config.ts`)

The config now uses **relative asset paths** for production builds
(`base: './'`), which preserve the proxy prefix automatically. Two ways to run:

**Option A — Production build + preview (recommended, most reliable):**

```bash
cd ~/canvasmind/frontend
npm run build
npm run preview -- --host 0.0.0.0 --port 3000
```

Because the build uses `base: './'`, every asset is requested relative to the
current page, so the proxy prefix is preserved and there are no 404s. There is
also no HMR WebSocket to misbehave behind the proxy.

**Option B — Live dev server behind the proxy:**

Pass the exact proxy prefix so Vite prepends it to every asset URL:

```bash
cd ~/canvasmind/frontend
VITE_BASE=/dev-workspaces/RAMA-GPU-A100/proxy/3000/ \
  npm run dev -- --host 0.0.0.0 --port 3000
```

Replace `RAMA-GPU-A100` with your actual workspace name from the URL. If
hot-reload doesn't connect through the proxy, the page still loads fully — just
refresh the browser manually after code changes.

### Important: the backend must also be reachable

When the frontend runs in your browser via the proxy, `localhost:8000` refers to
**your laptop**, not the VM. For the full UI to talk to the backend you must
either:
- expose the backend through the **same proxy** at `.../proxy/8000/` and set
  `VITE_BACKEND_URL` / `VITE_WS_URL` in `frontend/.env` to that proxied URL, **or**
- access the VM by its **public IP** with ports 8000 and 3000 open (Section 12).

If the proxy makes full end-to-end frontend wiring difficult, use the
**backend-only simulation (Section 17)** for your demo — it sidesteps all of this.

### Proxy fix summary table

| Layer | Symptom | Fix |
|---|---|---|
| Frontend assets | Blank page, 404 on `main.tsx`/`client` | Build with `base: './'` (done) → use `npm run build` + `npm run preview` |
| Dev server | 404s with `npm run dev` | Set `VITE_BASE=/dev-workspaces/<name>/proxy/3000/` |
| HMR WebSocket | Hot reload won't connect | Harmless — refresh manually; config already sets `wss`/`clientPort 443` when `VITE_BASE` is set |
| Backend API | UI loads but calls fail | Proxy port 8000 too, or use public IP; set `VITE_BACKEND_URL`/`VITE_WS_URL` |
| Anything proxy-related | Too complex to wire | Use the backend-only simulation (Section 17) |

---

## 19. Single-File App & One-Command Launcher (Recommended)

This is the simplest, most reliable way to run the whole product on the VM. The
**single-file app** (`canvasmind_app.py`) serves the web UI **and** the backend
together on **one port**, so there is no separate React build, no second port, no
CORS, and no reverse-proxy 404s. It is the recommended path for the VM.

### Why it works where the modular stack failed

- **Correct Azure calls.** It calls Azure via **raw REST** with
  `max_completion_tokens` and **no custom temperature** — exactly what the
  `gpt-5.2` deployment requires. (The older `backend/providers` SDK path sent
  `max_tokens`/`temperature`, which `gpt-5.2` rejects.)
- **One origin.** The browser fetches `api/...` relative to the page and streams
  events over Server-Sent Events, so the proxy prefix is always preserved.

### Two ways to start a brief

At the top of the page a toggle offers two modes:

- **✨ AI Surprise** *(default)* — **Surprise Me** calls `GET /api/inspire`, where
  the AI invents a striking, unexpected brief + style on its own (nudged by random
  seeds for variety). The chosen brief is shown in the UI, then co-creation starts.
- **✍️ Write my own** — the manual prompt box, where the user types their own
  brief + optional style and clicks **Start Co-Creation**.

### The 3-image co-creation pipeline

Whichever mode picks the brief, each agent then produces an image that builds on
the previous one:

1. **ARIA — Creative Director** decides the direction and paints a **partial,
   unfinished underpainting** (image #1) via `images/generations`.
2. **NEXUS — Creative Challenger** is shown ARIA's image, decides what to **add**,
   and generates a painting that **builds on image #1** (image #2) via the
   image-to-image `images/edits` endpoint.
3. **JUDGE — Critic** scores the work on 5 dimensions, then **combines both
   paintings** into one finished artwork (image #3) via a multi-image `images/edits`
   call.

All three appear in their own panels, with a **⬇ Download all 3 images** button.

> **Image-to-image fallback:** if your `gpt-image-1` deployment doesn't support
> the `edits` endpoint, the app automatically falls back to a fresh generation
> with a descriptive prompt, so you always get all three images. If `gpt-image-1`
> isn't deployed at all, the app runs as a text-only dialogue.

### Run it (one command)

```bash
cd ~/canvasmind          # or RL_Multi_Agent_ART/canvasmind
chmod +x launch.sh       # first time only
./launch.sh              # port 8000  ·  ./launch.sh 3000 for a different port
```

`launch.sh` verifies credentials, installs dependencies (creating a venv if
needed), and starts the app. On Windows use `.\launch.ps1 -Port 8000`, or run the
app directly with `python canvasmind_app.py --port 8000`.

Then open the proxy URL for **port 8000**:

```
https://rniazure.tcsapps.com/dev-workspaces/<your-workspace>/proxy/8000/
```

Type a brief → **Start Co-Creation** → watch the three images build on each other
→ **Download all 3 images**.

### Credentials

The app reads `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT` from the **shell
environment first** (usually already exported on the GPU VM), then from
`backend/.env`, which supplies the version and deployment names:

```bash
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_DEPLOYMENT_GPTTEXT52=gpt-5.2
AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1=gpt-image-1
```

### Verified end-to-end

The full flow was tested through the real HTTP server + SSE (Azure calls stubbed):

```
session → stage(ARIA) → agent(ARIA) → image(1·partial)
        → stage(NEXUS) → agent(NEXUS) → image(2·builds on ARIA)
        → stage(JUDGE) → critic → image(3·final combined)
        → summary → done          ·  3 valid downloadable PNGs
```

For the complete VM walkthrough (setup, tmux/systemd, troubleshooting), see
**[RUN_ON_VM.md](RUN_ON_VM.md)**.

---

*CanvasMind — TCS Research Computational Creativity Platform*
*Recommended: `launch.sh` → `canvasmind_app.py` (single-file app, 3-image co-creation)*
*Backend: Python 3.11 / FastAPI 0.111 / Pydantic 2.7 / Azure OpenAI (gpt-5.2 + gpt-image-1) via REST*
*Frontend: single-file UI (SSE) · React 18.3 / TypeScript 5.4 / Vite 5.3 stack retained for reference*
