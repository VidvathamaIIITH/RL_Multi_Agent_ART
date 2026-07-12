# CanvasMind — RL_Multi_Agent

**Two AI painters build one shared canvas, one object at a time, in the open —
under an inference-time reinforcement-learning layer — while a third agent judges
the result.** This document explains the entire system end to end, in detail,
with nothing skipped: what every component does, how a session flows turn by
turn, every mechanism in the RL layer, the four-agent variant, exactly what gets
saved to disk, every API endpoint and environment variable, the five bug fixes,
and how to run, deploy, and reproduce everything.

If you only read one section, read [3. How a dual session works, step by
step](#3-how-a-dual-session-works-step-by-step).

---

## Table of contents

1. [What this is](#1-what-this-is)
2. [Quick start](#2-quick-start)
3. [How a dual session works, step by step](#3-how-a-dual-session-works-step-by-step)
4. [The generative-agent substrate](#4-the-generative-agent-substrate)
5. [The inference-time RL layer](#5-the-inference-time-rl-layer)
6. [The five scoring instruments](#6-the-five-scoring-instruments)
7. [The Quad-Agent pipeline](#7-the-quad-agent-pipeline)
8. [Per-session storage](#8-per-session-storage)
9. [The five fixes (what was broken)](#9-the-five-fixes-what-was-broken)
10. [Architecture & why it is one file](#10-architecture--why-it-is-one-file)
11. [API reference](#11-api-reference)
12. [Configuration (every environment variable)](#12-configuration-every-environment-variable)
13. [The ablation study](#13-the-ablation-study)
14. [The research paper & slide decks](#14-the-research-paper--slide-decks)
15. [Repository map](#15-repository-map)
16. [Deploying on the Azure VM](#16-deploying-on-the-azure-vm)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. What this is

Most AI-art tools take a prompt and hand back a finished image; all the
decision-making is invisible. **CanvasMind makes the process visible.** Creation
is a turn-based negotiation between autonomous agents on a *single shared canvas*
that is passed back and forth. Each turn adds exactly **one** new object on top of
the previous image, so the painting visibly grows, and every intermediate state
is shown.

Three agents take part in the **dual** system:

| Agent | Role | Edits the canvas? |
|-------|------|-------------------|
| **ARIA** | Creative Director — opens the painting, adds bold structure | yes |
| **NEXUS** | Creative Challenger — inspects ARIA's work, adds complementary elements | yes |
| **JUDGE** | Critic — scores how well the two collaborated | **no** (evaluates only) |

On top of this sits an **inference-time reinforcement-learning layer**: no model
weights are ever trained: all "learning" happens *within* and *across* sessions
through search (best-of-N), a reward model, a bandit over artistic strategies,
and verbal self-correction. The two agents optimise *different* reward weightings
of the same five aesthetic dimensions — a deliberate misalignment that turns the
shared canvas into a general-sum game.

There is also a **Quad** system (four agents, strict sequence, **no** RL layer)
that acts as an architectural control.

Everything runs from **one Python file** (`canvasmind_app.py`, ~3,700 lines) that
serves both the browser UI and the backend API on a single port, streaming every
event live over Server-Sent Events (SSE) and calling Azure OpenAI over raw REST
(`gpt-5.2` for text, `gpt-image-1` for images).

There are **three byte-identical copies** of the runtime:
`./canvasmind_app.py` (the one you run locally), `canvasmind/canvasmind_app.py`,
and `RL_Multi_Agent_ART/canvasmind/canvasmind_app.py` (the VM bundle). Any edit to
one must be copied to the other two.

---

## 2. Quick start

### Prerequisites
- Python 3.10+ with `pip`
- Azure OpenAI access with a `gpt-5.2` (or equivalent) text deployment; a
  `gpt-image-1` image deployment is optional (without it you get the full text
  conversation but no pictures).

### Install
```bash
pip install fastapi uvicorn requests
```

### Set credentials
Either export them in your shell, or put them in `backend/.env` (the app reads the
shell **first**, then `backend/.env`, then `.env`):

```bash
export AZURE_OPENAI_API_KEY="your-key"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_API_VERSION="2025-04-01-preview"
export AZURE_OPENAI_DEPLOYMENT_GPTTEXT52="gpt-5.2"
export AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1="gpt-image-1"   # optional
```

### Run
```bash
python canvasmind_app.py --port 8000
```

Open <http://localhost:8000>. You'll see the *"Two minds. One canvas."* briefing
screen. Pick **AI Surprise** (the model invents a brief) or **Write My Own**, then
**Begin Session**. Watch ARIA and NEXUS alternate on the canvas; scroll down for
JUDGE's scoring and the research dashboard. **Stop & Judge** halts the turns early
and asks JUDGE to score whatever is finished. The **⧉ Quad Pipeline** button opens
the four-agent system.

Every session is automatically saved under `data/sessions/session_<N>/` (see
[§8](#8-per-session-storage)).

---

## 3. How a dual session works, step by step

A session runs on its own background thread and pushes events onto a queue that
the SSE endpoint drains to the browser. Let `R` = rounds (default 5, clamped to
`[1,8]`). The agents alternate for `2R` turns (ARIA on odd turns, NEXUS on even).

### 3.0 Briefing
The brief (`prompt`) and `style` come either from the user or from
`GET /api/inspire`, which asks the model to invent a striking brief + style,
loosely seeded by two random words from a 32-word list (`bioluminescent`,
`brutalist`, `ukiyo-e`, …).

### 3.1 The ten steps of one turn
Each turn, the acting agent (say NEXUS, with the other being ARIA) does the
following. Steps 3–6 and 8 are the **RL layer**; 1–2 and 10 are the
**generative-agent substrate**; 7 is a **diagnostic**.

1. **Perceive.** The agent observes as much of the current canvas as its persona's
   `vision_r` allows (the most recent objects; older ones are summarised as
   *"and N earlier elements you cannot take in at one glance"*), plus the other
   agent's last move. Each observation is scored 1–10 for **importance
   (poignancy)** by the model and stored as a memory.
2. **Retrieve.** The agent retrieves the top-`k` memories relevant to the decision
   (`k` = the persona's `retention`, clamped `[2,12]`). Relevance is
   `norm(recency) + norm(importance) + norm(relevance)` (see [§4](#4-the-generative-agent-substrate)).
3. **Explore (bandit).** A per-agent **UCB1 bandit** picks one of **8 artistic
   strategies** (establish a focal point, add atmospheric depth, introduce bold
   contrast, enrich fine detail, open expressive negative space, add a narrative
   element, unify the palette, heighten emotional tone). The strategy is injected
   into the proposal prompt.
4. **Propose (best-of-N).** In **one** model call the agent proposes `N` distinct
   candidate additions (default `N=4`), each a JSON object with `new_object`,
   `where`, `palette`, `sees_on_canvas`, `reasoning`, and `resisted_human`.
5. **Score (reward model).** In **one** batched model call, a reward model scores
   each candidate's prospective canvas on five dimensions
   (`compositional_coherence`, `style_fidelity`, `emotional_resonance`,
   `originality`, `clarity`), each 0–10.
6. **Commit.** The agent commits to the candidate that maximises **its own
   weighted reward** (ARIA weights coherence heavily; NEXUS weights originality —
   see [§5](#5-the-inference-time-rl-layer)). The rejected candidates and their
   rewards are streamed to the UI.
7. **Probe (Goodhart).** An **independent-quality** probe scores the resulting
   canvas for holistic merit while *ignoring* the optimised rubric. This runs on
   a separate instrument deployment when configured. Proxy reward and independent
   quality are logged for the Goodhart monitor.
8. **Reflect? (Reflexion).** If the committed reward is below `4.5`, the agent
   runs a reflection: it asks the model for 3 salient questions about its evolving
   approach, retrieves memories for each, and synthesises 3 cited insights, which
   are stored and injected into future prompts.
9. **Paint.** On the first turn the canvas is blank, so `images/generations`
   creates the first object. On every later turn `images/edits` uploads the
   current canvas and adds *only* the one new element ("keep everything already in
   the painting EXACTLY as it is"). The PNG (base64) is streamed inline as a
   `data:` URL and saved to disk.
10. **Store.** The agent stores its own action as a memory (scored for importance)
    so it — and, via the transcript, the other agent — can build on it.

### 3.2 Critique and metrics
After the last turn (or an early **Stop**):
- **JUDGE** scores the whole collaboration over five dimensions +
  `collaboration_quality` + a `composite`, with reasoning, highlights, and a
  one-sentence summary. JUDGE never edits — the final image *is* the accumulated
  canvas.
- The **research dashboard** metrics are computed and emitted in one `metrics`
  event: Shapley credit (with a confidence interval), empowerment, the Goodhart
  verdict, the coherence↔originality Pareto trace, per-agent reward curves, and
  the bandit's learned strategies.

### 3.3 The SSE event contract
Thirteen event types are streamed, in order:
`session` · `turn` · `agent` · `reflection` · `image_pending` · `image` ·
`critic` · `final` · `metrics` · `summary` · `warning` · `error` · `done`.
The browser switches on `type` to update the agent feeds, the filmstrip, the
large canvas, the critic panel, the dashboard, and the event log.

### 3.4 Compute cost
Per dual turn: 6 model calls (importance ×2, proposal, reward scoring,
independent probe, and one image call), plus 2 more if Reflexion fires. At the
end: JUDGE (1 call) + Shapley (3 batched value samples). A session with `R` rounds
costs `12R + 4` calls versus `8R + 1` for a plain painter — about **1.56×** at
`R=5`. Crucially, **best-of-N costs no extra calls**: proposal and scoring are
each one batched call regardless of `N`, so raising `N` only spends output tokens.

---

## 4. The generative-agent substrate

Modelled after Park et al., *Generative Agents* (UIST 2023).

### 4.1 The eight personas
Every agent slot (ARIA, NEXUS, and each Quad agent) is instantiated from one of
**eight personas**, written in the paper's seed-memory format. They span walks of
life so that *who an agent is* shapes *what it paints*:

| Key | Name | Age / occupation | `vision_r` | `att_bandwidth` | `retention` |
|-----|------|------------------|:---:|:---:|:---:|
| `isabella_rodriguez` | Isabella Rodriguez | 34, café owner | 8 | 8 | 8 |
| `klaus_mueller` | Klaus Mueller | 20, sociology researcher | 6 | 10 | 10 |
| `maya_okonkwo` | Maya Okonkwo | 41, marine biologist | 10 | 6 | 9 |
| `tomas_grieg` | Tomas Grieg | 67, retired shipwright & woodcarver | 9 | 5 | 7 |
| `priya_raghunathan` | Priya Raghunathan | 29, software engineer & astronomer | 7 | 9 | 10 |
| `amara_diallo` | Amara Diallo | 23, street muralist & organiser | 9 | 7 | 6 |
| `hiroshi_tanaka` | Hiroshi Tanaka | 58, jazz saxophonist & club owner | 7 | 10 | 8 |
| `elena_voss` | Elena Voss | 36, emergency-room nurse | 10 | 8 | 9 |

Each persona also carries `innate`, `learned`, `currently`, `lifestyle`,
`living_area`, `daily_plan_req`, a `voice`, and an `image_style`. The three
**cognitive parameters** are wired into behaviour:

- **`vision_r`** — how much of the accumulated canvas the agent perceives at once
  (bounds the prompt; the reward model and probes still see the whole canvas).
- **`att_bandwidth`** — how many recent transcript lines enter the prompt.
- **`retention`** — the retrieval budget `k`.

### 4.2 Memory stream
Each agent keeps a stream of natural-language memory objects. Each has an `id`,
`text`, `kind` (`observation` or `reflection`), `created` and `last_access`
times, and an `importance` score in `[1,10]` obtained by prompting the model for
poignancy (fallback 4).

### 4.3 Retrieval
For a query `q` at time `τ`, each memory `m` is scored by
`norm(γ^(τ − last_access)) + norm(importance/10) + norm(cos(q, m))`, with
`γ = 0.995` (`RECENCY_DECAY`) and each term min–max normalised across the stream.
Relevance uses embedding cosine if an embedding deployment is configured,
otherwise stop-worded term-frequency cosine. The top `k` are returned and their
`last_access` refreshed.

### 4.4 Reflection
When accumulated observation importance since the last reflection exceeds
`REFLECT_THRESHOLD = 10`, the agent reflects: 3 salient questions → top-4
retrieval per question → 3 cited insights stored with importance 6. The three most
recent reflections are injected into the agent's summary description every turn —
the main channel by which an agent changes within a session.

---

## 5. The inference-time RL layer

**No gradients, no training.** Everything is search + selection + exploration +
verbal correction at inference time. Five mechanisms:

### 5.1 Reward model
`score_candidate_rewards` rates all `N` prospective canvases on the five
`RL_DIMS` in one batched call, returning a 0–10 score per dimension per candidate.

### 5.2 Best-of-N
`generate_candidates` samples `N` distinct additions in one call
(`BEST_OF_N`, default **4**, env `CM_BEST_OF_N`); the agent commits to the argmax
of its own weighted reward. Both the proposal and the scoring are single batched
calls, so `N` is "free" in API calls.

### 5.3 Misaligned per-agent rewards
The scalar reward is a weighted sum over the five dimensions. **The weights differ
by agent**, deliberately:

| Dimension | ARIA weight | NEXUS weight |
|-----------|:---:|:---:|
| compositional_coherence | **0.40** | 0.10 |
| style_fidelity | 0.25 | 0.15 |
| emotional_resonance | 0.15 | 0.20 |
| originality | 0.10 | **0.45** |
| clarity | 0.10 | 0.10 |

ARIA is paid for coherence, NEXUS for originality. Both sum to 1 (so rewards stay
in `[0,10]`). Their weight vectors have cosine similarity 0.59 — a genuine
general-sum game on a shared canvas. This costs a little raw quality (the agents
sometimes disagree with the holistic optimum) but produces the *tension* the
interface exists to show.

### 5.4 UCB1 bandit over strategies
Each agent keeps its own bandit over the 8 strategies. It scores every arm by
`mean[s] + 1.4 · sqrt(ln(t+1)/n[s])` with:
- **optimistic initialisation** (each arm seeded at reward 10.0 with one
  pseudo-count) so the confidence bound is evaluated on *every* pull;
- **uniform random tie-breaking**;
- **cross-session persistence** — learned per-arm means are saved to
  `data/bandit_state.json` and reloaded, because one session gives an agent only
  `R ≤ 8` pulls over 8 arms, far too few to learn from alone.

(This is the repaired bandit; see [§9](#9-the-five-fixes-what-was-broken) for what
it replaced.)

### 5.5 Reward-aware Reflexion
A turn whose committed reward falls below `REFLEXION_REWARD_TRIGGER = 4.5` (env
`CM_REFLEXION_TRIGGER`) triggers a learning reflection, in the spirit of Shinn et
al.'s Reflexion.

### 5.6 Autonomy & directive resistance
The user sets an autonomy scalar `α ∈ [0,1]` and may give a directive. If
`α ≥ 0.66` the agent is told it *may resist* the directive (and set
`resisted_human`); otherwise it is told to honour it. Resistance surfaces as a
`warning` event. Note this is an instruction in a prompt, not an enforced
constraint.

---

## 6. The five scoring instruments

The system runs five distinct LLM-scored instruments. **Exactly one is a target
of optimisation** — which is what keeps JUDGE's composite from being circular:

| Instrument | Rubric | Optimised against? | In the action loop? |
|------------|--------|:---:|:---:|
| Reward model | 5 dims incl. **clarity** | **yes** | yes |
| Independent probe | holistic merit | no | no |
| JUDGE composite | 5 dims incl. **collaboration_quality** | no | no |
| Shapley value oracle | composite quality of a coalition | no | no (end only) |
| Importance | poignancy | no | yes |

Note the reward rubric and the JUDGE rubric differ in their fifth dimension
(`clarity` vs `collaboration_quality`). The independent probe, JUDGE, and the
Shapley oracle can be routed to a **separate** deployment
(`AZURE_OPENAI_DEPLOYMENT_PROBE`) so they are independent in *model*, not only in
*rubric*.

### The research-dashboard diagnostics
- **Empowerment** — normalised entropy of `softmax(reward/T)`, `T=2.0`, over the
  `N` candidates: how many good futures the agent's action channel commands. Only
  meaningful for `N ≥ 3` (the `metrics` event flags `informative`).
- **Goodhart monitor** — compares the optimised proxy-reward trend against the
  independent-quality trend, estimated *within agent*; declares reward hacking
  only when the divergence is statistically significant (≥ 2 standard errors) and
  the proxy is rising.
- **Shapley credit** — exact two-player value `φ_ARIA = ½[v(A) + (v(A∪B) − v(B))]`,
  where each coalition value `v(·)` is averaged over 3 batched samples; reported
  with a 95% interval, and withheld when a coalition value is non-superadditive.
- **Pareto trace** — the (coherence, originality) pair each committed turn lands
  on, tracing the frontier the two objectives negotiate.

---

## 7. The Quad-Agent pipeline

An isolated advanced view: **four** independently configured agents act in
**strict sequence** (1 → 2 → 3 → 4) per round, `R ∈ [1,6]`, producing `4R`
additive images. Each agent has:
- a **name**;
- an **artistic voice** — one of six presets: The Vanguard Minimalist, The
  Neo-Noir Cyberpunk, The Biomorphic Surrealist, The Baroque Traditionalist, The
  Kinetic Futurist, The Luminous Impressionist;
- an optional **Configure Custom Agent** free-text prompt that overrides the
  preset;
- a **persona identity** drawn from the same eight of [§4.1](#41-the-eight-personas).

A deterministic keyword router, **`ArtHistoryRAG`** (a 16-entry knowledge base of
movements/techniques), injects up to three stylistic clarifications when it
recognises a style in the brief or voice. Its interface is retriever-shaped so it
can later be swapped for a vector store.

**The Quad pipeline has no RL layer** — no bandit, best-of-N, reward model, memory
stream, or Shapley. It shares only the additive canvas, the JUDGE critic, and the
SSE contract. That makes it a clean architectural control: dual − quad = the RL
layer + the memory substrate.

---

## 8. Per-session storage

Every session — dual or quad — opens a numbered folder and records **everything**:
the prompt given, the reasoning, the time each reasoning was done, the raw API
responses, the scores, and all outputs. Set the root with `CM_DATA_DIR` (default
`./data/sessions`).

```
data/sessions/session_0007/
├── session.json                 # manifest: config, personas, timings, deployments, outcome
├── json/
│   ├── events.jsonl             # every streamed event, in order, wall-clock stamped
│   ├── llm_calls.jsonl          # EVERY Azure call: purpose, request, raw response, latency
│   ├── turns/
│   │   ├── turn_01_ARIA.json     # prompt, candidates+rewards, chosen, reasoning,
│   │   ├── turn_02_NEXUS.json     #   reasoned_at timestamp, retrieved memories,
│   │   └── …                       #   scores, independent_quality, image_file
│   ├── memory/
│   │   ├── aria.json             # ARIA's full memory stream at the end
│   │   └── nexus.json            # NEXUS's full memory stream
│   ├── critic.json              # JUDGE's full evaluation
│   ├── metrics.json             # Shapley / empowerment / Goodhart / bandit / Pareto
│   ├── summary.json             # outcome, turns, objects, composite, elapsed
│   ├── participant.json         # pre-session form (age / gender / art expertise)  [if submitted]
│   └── survey.json              # post-session survey (scale + Likert)             [if submitted]
└── images/
    ├── step_01_ARIA_a-lone-lighthouse.png
    ├── step_02_NEXUS_a-flock-of-gulls.png
    ├── …
    └── final.png                # the accumulated final canvas
```

How it works, precisely:
- A **`SessionRecorder`** opens the folder and allocates the smallest unused
  `session_<N>` under a lock (so two simultaneous starts can't collide).
- A **thread-local** pointer (`set_recorder`) means the raw Azure wrappers log
  every call *themselves* — so `llm_calls.jsonl` captures the prompt, the raw JSON
  response, the deployment, the latency, and a running elapsed time, with **no**
  change at the hundreds of call sites. (Each session runs on its own thread, so
  the thread-local is exactly the right scope.)
- Images are written as real PNG files; the base64 blob is stripped out of
  `events.jsonl`/`llm_calls.jsonl` (replaced with `<see images/>`) so the JSON
  stays readable.
- Recording is wrapped so it **can never break a run** — a storage error prints a
  warning and the session continues.

You can browse saved sessions via the API: `GET /api/sessions`,
`GET /api/sessions/{n}`, `GET /api/sessions/{n}/images/{file}`.

---

## 9. The five fixes (what was broken)

A formal audit of the RL layer (documented in the research paper) found four
non-obvious defects; a simulation ablation showed the *original* system delivered
essentially **no** net quality benefit over a plain painter. All are now fixed on
the default path, at no extra compute:

| # | Defect (original "v1") | Fix (shipped now) |
|---|------------------------|-------------------|
| 1 | **The UCB1 bandit was inert.** With 8 strategies and ≤ 8 pulls/session, the selector always returned the first un-pulled arm and *never evaluated the confidence bound* — a fixed round-robin, with no cross-session memory. | **Optimistic initialisation** (bound evaluated every pull), **random tie-breaking**, and **cross-session persistence** (`data/bandit_state.json`). The bandit now climbs to ~98% of the achievable ceiling within ~50 sessions. |
| 2 | **Empowerment was a one-bit statistic** at the old default `N=2` — a deterministic function of the single reward gap. | Default **`N=4`** (free in API calls), and a `informative` flag that is false whenever `N<3`. |
| 3 | **Shapley credit was read from a single noisy value query** (±16.7 pp at σ=1). | The three coalition values are **batched and averaged over 3 samples** (noise ÷ √3 → ±9.4 pp), with a 95% interval emitted and a share withheld when values are non-superadditive. |
| 4 | **The Goodhart monitor false-fired ~10%** on short runs and regressed an *alternating mixture* of two objectives. | Slopes estimated **within agent**; the monitor fires only when the divergence exceeds **2 standard errors** (false-positive rate ~5% at 10 turns, ~0.5% at 16). |
| 5 | **`vision_r` was declared but never read**, and all instruments shared one deployment. | `vision_r` now **bounds each agent's perception** of the canvas, and the probe/JUDGE/Shapley oracle route to a separate `AZURE_OPENAI_DEPLOYMENT_PROBE` when set. |

Fixed vs audited, measured by the ablation (simulation; see [§13](#13-the-ablation-study)):
the audited system was **−0.05** composite points vs a pre-RL painter; the fixed
system is **+1.66**, at the same compute — ~+0.6 from best-of-N and ~+1.1 from the
now-functional persistent bandit.

---

## 10. Architecture & why it is one file

```
Browser UI  ──POST /api/start──▶  canvasmind_app.py (FastAPI, one port)  ──chat/images──▶  Azure OpenAI
   ▲                                 · generative-agent substrate                            (raw REST)
   └────────  SSE event stream ──────┤ · inference-time RL layer                    gpt-5.2  (decisions,
                                      · Session (dual) / QuadSession (quad)                    reward model,
                                      · SessionRecorder (per-session store)                    probes, JUDGE)
                                                                                     gpt-image-1 (generate/edit)
```

Design decisions, and why:
- **One origin, relative paths.** The page calls `fetch('api/...')` relative to
  itself, so a reverse-proxy sub-path prefix (e.g. `/…/proxy/8000/`) is preserved
  — no 404s on assets, no CORS, no second port.
- **Raw REST, not the SDK.** Azure is called with `max_completion_tokens` and *no*
  custom temperature, which is what the `gpt-5.2` deployment requires.
- **SSE, not WebSocket.** One-directional streaming is enough (the browser only
  receives), traverses proxies cleanly, and sets `X-Accel-Buffering: no` so events
  aren't buffered.
- **One thread per session** pushing onto a queue; the SSE endpoint drains it.
- **Robust JSON.** Every model reply is parsed with fence-stripping extractors and
  a fallback, so one malformed reply never aborts a run.
- **Graceful image fallback.** Every image step is wrapped in try/except: a failed
  edit keeps the previous canvas and continues; with no image deployment at all,
  the agents still hold the full text conversation.

A modular reference backend (`canvasmind/backend/`, 45 Python modules) and a React
frontend also exist, but **the single file is the runtime** and the RL layer lives
only there.

---

## 11. API reference

| Method & path | Purpose |
|---------------|---------|
| `GET /` | The embedded single-page UI |
| `GET /api/health` | Model + capability probe (`images_enabled`, `personas`, …) |
| `GET /api/personas` | The 8 generative-agent persona specs |
| `GET /api/inspire` | AI invents a brief + style |
| `POST /api/start` | Start a dual session → `{session_id}` |
| `GET /api/stream/{id}` | SSE event stream for a session |
| `POST /api/stop/{id}` | Halt the turns; JUDGE then evaluates progress so far |
| `GET /api/quad/personas` | Quad artistic voices + the 8 identities |
| `POST /api/quad/start` | Start a quad session → `{session_id}` |
| `GET /api/sessions` | List all recorded sessions (newest first) |
| `GET /api/sessions/{n}` | One session's manifest + file index |
| `GET /api/sessions/{n}/images/{file}` | Fetch a saved image (path-traversal-safe) |
| `POST /api/sessions/{n}/participant` | Save the pre-session form |
| `POST /api/sessions/{n}/survey` | Save the post-session survey |
| `GET /assets/hero` | Dual hero image (`assets/hero.png`) |
| `GET /assets/quad-hero` | Quad hero image (`assets/4_Agent_Art.png`) |

`POST /api/start` body: `prompt` (required), `style`, `rounds` (1–8),
`images` (bool), `aria_persona`, `nexus_persona` (persona keys), `autonomy`
(0–1), `human_directive`.

`POST /api/quad/start` body: `prompt` (required), `style`, `rounds` (1–6),
`images`, and `agents` — a list of up to 4 objects
`{name, persona (voice key), custom_prompt, persona_id (identity key)}`.

---

## 12. Configuration (every environment variable)

**Azure (required unless noted):**

| Variable | Meaning |
|----------|---------|
| `AZURE_OPENAI_API_KEY` | API key |
| `AZURE_OPENAI_ENDPOINT` | `https://<resource>.openai.azure.com/` |
| `AZURE_OPENAI_API_VERSION` | e.g. `2025-04-01-preview` |
| `AZURE_OPENAI_DEPLOYMENT_GPTTEXT52` | text deployment (decisions, reward model) |
| `AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1` | *(optional)* image deployment; unset → text-only |
| `AZURE_OPENAI_DEPLOYMENT_EMBED` | *(optional)* embeddings → true cosine relevance |
| `AZURE_OPENAI_DEPLOYMENT_PROBE` | *(optional)* separate deployment for the probe / JUDGE / Shapley oracle |

**Tuning (all optional, with sensible defaults):**

| Variable | Default | Effect |
|----------|:---:|--------|
| `CM_BEST_OF_N` | 4 | Candidates sampled per turn (free in API calls) |
| `CM_BANDIT_PERSIST` | on | Persist learned bandit values across sessions |
| `CM_REFLEXION_TRIGGER` | 4.5 | Reward below which Reflexion fires |
| `CM_SHAPLEY_REPEATS` | 3 | Value-oracle samples averaged for Shapley |
| `CM_DATA_DIR` | `./data/sessions` | Where per-session folders are written |

Credentials are read from the **shell first**, then `backend/.env`, then `.env`
(shell values always win; `.env` never overrides an exported variable).

---

## 13. The ablation study

`ablation/run_ablation.py` answers *"what does each RL component actually
contribute?"* It **imports the real decision code** from `canvasmind_app.py`
(`Bandit`, `scalar_reward`, `empowerment_from_rewards`, the slope estimator,
`REWARD_WEIGHTS`) and replaces **only** the two Azure-backed oracles (the reward
model and the quality probes) with a calibrated stochastic reward environment
whose generative model is stated in the script and the paper.

```bash
pip install numpy
python ablation/run_ablation.py    # writes ablation/results/*.csv + summary.json
```

**These are simulation results, not live-system results, and are labelled as such
throughout.** No Azure calls are made. What the simulation buys is that every
selection rule, bandit update, empowerment value, Goodhart slope, and Shapley
value is computed by the *shipping code path* — so the ablation measures the real
algorithm under a controlled environment. It runs 4,000 seeded sessions per
configuration and compares the audited "v1" against the fixed "full" system, with
a bandit learning curve and a sweep over how much learnable structure the strategy
space has. Outputs land in `ablation/results/` (one CSV per experiment +
`summary.json`).

---

## 14. The research paper & slide decks

- **`paper/canvasmind_acl.tex`** — a full ACL-format technical paper: the system,
  a formal audit of four defects (with proofs), the five fixes, and the
  before/after ablation. It compiles with the official ACL style files if present,
  otherwise with a built-in ACL-layout emulation, on a bare TeX Live / Overleaf.
  See `paper/README.md`. All figures are TikZ (no external images).
- **`paper/custom.bib`** — 59 references.
- **`CanvasMind_Technical_Deck.pptx`** (17 slides) and
  **`CanvasMind_Technical_Deck_Full.pptx`** (42-slide appendix) — generated by
  `build_canvasmind_summary_deck.py` and `build_canvasmind_deck.py`.
- **`RL_Multi_Agent_ACL.tex` / `.pdf`** — an *earlier* paper describing the
  pre-RL system; kept for provenance, superseded by `paper/`.

---

## 15. Repository map

```
canvasmind_app.py                  ← THE runtime (single file; 3 identical copies)
canvasmind/canvasmind_app.py       ← copy (with the modular backend + React ref)
RL_Multi_Agent_ART/…/canvasmind_app.py  ← copy (VM bundle)
assets/hero.png, 4_Agent_Art.png   ← home-screen hero artwork
data/sessions/session_<N>/         ← per-session records (created at runtime)
data/bandit_state.json             ← persisted bandit learning (created at runtime)
ablation/run_ablation.py           ← the ablation harness
ablation/results/                  ← CSVs + summary.json (created by the harness)
paper/canvasmind_acl.tex           ← the ACL research paper
paper/custom.bib, paper/README.md
build_canvasmind_summary_deck.py   ← 17-slide deck generator
build_canvasmind_deck.py           ← 42-slide deck generator
canvasmind/backend/                ← modular reference backend (45 modules)
canvasmind/frontend/               ← React reference UI
canvasmind/README.md, RUN_ON_VM.md ← VM-oriented guides
```

Inside `canvasmind_app.py`, in order: the UTF-8 stdout guard and `.env` loader;
`validate_config`; the `SessionRecorder` + storage helpers; the raw-REST Azure
wrappers (`azure_chat_completion`, `probe_chat_completion`,
`azure_generate_image_b64`, `azure_edit_image_b64`, `azure_embed`); JSON
extractors; the persona system; the memory stream, retrieval, and reflection; the
RL layer (`RL_DIMS`, `REWARD_WEIGHTS`, `Bandit`, `generate_candidates`,
`score_candidate_rewards`, `independent_quality`, `value_of_coalitions`,
`empowerment_from_rewards`, `detect_goodhart`); the `Session` class; the Quad
system (`QUAD_PERSONAS`, `ArtHistoryRAG`, `QuadSession`); the FastAPI routes; and
the embedded single-page UI (`INDEX_HTML`).

---

## 16. Deploying on the Azure VM

The VM bundle is `RL_Multi_Agent_ART/canvasmind/`. In short:

```bash
cd RL_Multi_Agent_ART/canvasmind
export AZURE_OPENAI_API_KEY=...  AZURE_OPENAI_ENDPOINT=...   # (Section 2)
python canvasmind_app.py --port 8000
# or: ./launch.sh   (Linux)   /   .\launch.ps1   (Windows)
```

Open the reverse-proxy URL for **port 8000**:
`https://<host>/dev-workspaces/<WORKSPACE>/proxy/8000/`. Because the UI and
backend share one origin, the earlier proxy/CORS failures cannot occur. Use `tmux`
or a `systemd` unit to keep it running after disconnect. `RUN_ON_VM.md` has the
full step-by-step (including the React frontend on port 3000, if you prefer it).

Drop `assets/hero.png` and `assets/4_Agent_Art.png` next to the app for the hero
artwork; a cosmic gradient is used until then.

---

## 17. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `FATAL: Missing required environment variables` | Key/endpoint/version/text-deployment not set | Export them, or put them in `backend/.env` ([§2](#2-quick-start)) |
| `HTTP 401 … invalid subscription key` | Wrong key or endpoint | Re-copy from Azure Portal → Keys and Endpoint |
| Text runs but **no images** | No image deployment | Set `AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1` (optional; text-only otherwise) |
| Only image #1 appears | `gpt-image-1` rate limit / no `edits` endpoint | Wait; check quota. The app falls back to the last good canvas and continues |
| Blank page / 404 behind proxy | Opened the wrong port | Open the proxy for the port you launched (8000 for the single-file app) |
| Port 8000 already in use | A stale server | Kill the process holding the port and relaunch (Windows: `Get-NetTCPConnection -LocalPort 8000` then `Stop-Process`) |
| No `data/sessions/…` folder | `CM_DATA_DIR` unwritable | Storage failures print a warning and never stop a run; check the path/permissions |
| Banner `UnicodeEncodeError` on Windows | Console code page can't encode `═` | Pre-existing/cosmetic; run with `PYTHONIOENCODING=utf-8` if it bothers you |
| Ablation import error | `numpy` missing | `pip install numpy` |

---

*CanvasMind — RL_Multi_Agent. TCS Research Computational Creativity Platform.
Single-file runtime · FastAPI + SSE · Azure OpenAI (gpt-5.2 text, gpt-image-1
images).*
