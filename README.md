# 🎨 Computational Creativity Chatbot

> **Two AI agents negotiate and collaborate to create a stroke-based art piece on a shared virtual canvas, powered by OpenAI's API with 2 separate API keys.**

This project implements a multi-agent system inspired by the Computational Creativity research paper. Two AI painting agents — an **Impressionist** and a **Cubist** — take turns proposing, debating, and refining brushstrokes on a shared canvas over 10 rounds. A **Critic Agent** evaluates each round and steers the collaboration toward better art. Each painting agent uses its own separate OpenAI API key.

---

## 📑 Table of Contents

- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Architecture Overview](#-architecture-overview)
- [How the Agents Work](#-how-the-agents-work)
- [The Communication Protocol](#-the-communication-protocol)
- [The Shared Canvas](#-the-shared-canvas)
- [The Critic Agent](#-the-critic-agent)
- [Dispute Resolution & Mediation](#-dispute-resolution--mediation)
- [Configuration & Customization](#-configuration--customization)
- [File-by-File Code Walkthrough](#-file-by-file-code-walkthrough)
- [Output & Transcripts](#-output--transcripts)
- [Troubleshooting](#-troubleshooting)
- [Example Output](#-example-output)

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** installed on your system
- **Two OpenAI API keys** (get them at [platform.openai.com/api-keys](https://platform.openai.com/api-keys))

### Step 1 — Navigate to the project folder

```
cd C:\Users\vidva\Downloads\AntiGravity_Chatbot
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs three packages:

| Package | Version | Purpose |
|---------|---------|---------|
| `openai` | ≥ 1.30.0 | OpenAI Python SDK for API calls |
| `python-dotenv` | ≥ 1.0.0 | Loads API keys from the `.env` file |
| `colorama` | ≥ 0.4.6 | Enables colored terminal output on Windows |

### Step 3 — Add your two OpenAI API keys

Open the `.env` file in any text editor and paste your two keys:

```env
OPENAI_API_KEY_AGENT_A=sk-your-first-key-here
OPENAI_API_KEY_AGENT_B=sk-your-second-key-here
```

> ⚠️ **Important:** Do NOT add quotes around the keys. Paste them directly after the `=` sign.

**Which key goes where:**

| Environment Variable | Used By | Why Separate? |
|---------------------|---------|---------------|
| `OPENAI_API_KEY_AGENT_A` | Agent A (Impressionist painter) | Own rate limit bucket |
| `OPENAI_API_KEY_AGENT_B` | Agent B (Cubist painter) + Critic Agent | Own rate limit bucket |

### Step 4 — Run the chatbot

```bash
python main.py
```

This runs **10 rounds** of collaborative painting with the default theme *"A surreal underwater cityscape at twilight"*.

**Optional flags:**

```bash
python main.py --rounds 5                          # Only 5 rounds
python main.py --theme "A burning forest at dawn"   # Custom theme
python main.py -n 3 -t "Abstract jazz"              # Short form flags
```

---

## 📁 Project Structure

```
AntiGravity_Chatbot/
│
├── main.py              # Entry point — runs the session loop, CLI, pretty-printing
├── agents.py            # PaintingAgent and CriticAgent classes (OpenAI API calls)
├── protocol.py          # Message schemas (AgentMessage, CriticEvaluation) + JSON parsing
├── canvas.py            # SharedCanvas — tracks regions, strokes, ownership
├── config.py            # All settings: rounds, model, theme, agent personas
│
├── .env                 # YOUR API KEYS GO HERE (not committed to git)
├── .env.example         # Template showing what .env should look like
├── requirements.txt     # Python dependencies
├── .gitignore           # Keeps .env and __pycache__ out of git
│
├── logs/                # Auto-created — JSON transcripts saved here after each run
│   └── session_YYYYMMDD_HHMMSS.json
│
└── computational_creativity (1).pdf   # The research paper this project implements
```

---

## 🏗️ Architecture Overview

```
                    ┌─────────────────────────────────┐
                    │          main.py                 │
                    │     (Session Orchestrator)       │
                    │                                  │
                    │  Runs the 10-round loop:         │
                    │  1. Agent A proposes              │
                    │  2. Agent B responds              │
                    │  3. Mediation (if dispute)        │
                    │  4. Apply strokes to canvas       │
                    │  5. Critic evaluates              │
                    └──────────┬───────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
   ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
   │   PaintingAgent   │ │ PaintingAgent│ │   CriticAgent    │
   │    (Agent A)      │ │  (Agent B)   │ │                  │
   │                   │ │              │ │  Scores 4 axes   │
   │  Impressionist    │ │  Cubist      │ │  (0-10 each)     │
   │  Expert           │ │  Intermediate│ │  + directives    │
   │                   │ │              │ │                  │
   │  API Key 1        │ │  API Key 2   │ │  API Key 2       │
   └────────┬──────────┘ └──────┬───────┘ └────────┬─────────┘
            │                   │                   │
            │   agents.py       │                   │
            │  (OpenAI API)     │                   │
            └───────────────────┘                   │
                      │                              │
              ┌───────▼──────────┐                   │
              │  protocol.py     │◄──────────────────┘
              │                  │
              │  AgentMessage    │   JSON schema for
              │  CriticEvaluation│   structured comms
              │  JSON parsing    │
              └───────┬──────────┘
                      │
              ┌───────▼──────────┐
              │  canvas.py       │
              │                  │
              │  SharedCanvas    │   5 regions, stroke
              │  Region tracking │   history, ownership
              │  Stroke history  │
              └──────────────────┘
```

### Data Flow Per Round

```
config.py ──► main.py ──► Agent A ──► (OpenAI Key 1) ──► JSON proposal
                │                                              │
                │              ┌────────────────────────────────┘
                │              ▼
                ├──► Agent B ──► (OpenAI Key 2) ──► JSON response
                │                                        │
                │         ┌──────────────────────────────┘
                │         ▼
                ├──► canvas.py ◄── applies both agents' strokes
                │         │
                │         ▼
                └──► Critic ──► (OpenAI Key 2) ──► JSON evaluation
                          │
                          ▼
                    Feedback fed into Round N+1
```

---

## 🤖 How the Agents Work

### Agent A — The Impressionist (Expert)

| Trait | Value | Effect |
|-------|-------|--------|
| **Style** | Impressionist | Loose brushwork, emphasis on light and atmosphere |
| **Skill Level** | Expert | Confident, sophisticated proposals |
| **Boldness** | 80% | Makes strong, boundary-pushing creative choices |
| **Deference** | 20% | Rarely backs down from proposals |
| **Whimsy** | 90% | Loves unexpected, playful choices |

Agent A always proposes first each round. It favors ephemeral moments of light and color — think Monet, Renoir, Sisley.

### Agent B — The Cubist (Intermediate)

| Trait | Value | Effect |
|-------|-------|--------|
| **Style** | Cubist (Picasso-inspired) | Geometric forms, multiple viewpoints |
| **Skill Level** | Intermediate | Learning, building confidence |
| **Boldness** | 30% | Cautious, measured proposals |
| **Deference** | 70% | Tends to accommodate Agent A |
| **Whimsy** | 30% | Methodical and structured |

Agent B responds to Agent A's proposal. It adds geometric interpretation — think Picasso, Braque, Léger.

### How They Communicate

Each agent produces a **structured JSON message** every turn. The LLM is called with:
- **JSON mode** enabled (`response_format={"type": "json_object"}`)
- **Temperature 0.9** for high creativity
- **Max 800 tokens** per response
- **Rolling window** of the last 20 messages for conversation memory

---

## 📝 The Communication Protocol

All agent messages follow this exact JSON schema (from Section 4.2 of the paper):

```json
{
  "sender": "agent_a",
  "round": 3,
  "intent": "propose",
  "theme": "Bioluminescent jellyfish illuminating coral towers",
  "region": "center",
  "style_note": "Loose wet-on-wet technique with dissolved edges",
  "mark_ops": [
    "sweeping arc of cadmium yellow across the horizon",
    "stippled dots of cerulean blue for light refractions",
    "dragged palette knife streak of viridian through coral"
  ],
  "open_question": "Should we let the jellyfish tendrils extend into your geometry?",
  "emotion_tag": "wonder"
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `sender` | string | `"agent_a"` or `"agent_b"` (auto-set by system) |
| `round` | int | Current round number (auto-set by system) |
| `intent` | string | One of: `propose`, `acknowledge`, `dispute`, `yield` |
| `theme` | string | Agent's thematic direction for this turn |
| `region` | string | Canvas zone: `top-left`, `top-right`, `center`, `bottom-left`, `bottom-right` |
| `style_note` | string | HOW the agent will paint — specific to their style |
| `mark_ops` | list[string] | 2–4 vivid, specific painting operations (the actual "strokes") |
| `open_question` | string \| null | A creative question to push dialogue forward |
| `emotion_tag` | string | Dominant emotion: `wonder`, `tension`, `serenity`, `melancholy`, `joy`, `chaos`, etc. |

### Intent Types

| Intent | Who Uses It | What It Means |
|--------|------------|---------------|
| `propose` | Agent A (round start) | "Here's what I want to paint this round" |
| `acknowledge` | Agent B | "I accept your proposal and add my own contribution" |
| `dispute` | Agent B | "I disagree — here's why and my alternative" |
| `yield` | Agent B | "I defer entirely to your vision this round" |

### JSON Parsing Safety

The `protocol.py` file has **3 fallback strategies** to extract JSON from LLM responses:

1. **Markdown code block** — strips `` ```json `` wrappers
2. **Direct parse** — tries `json.loads()` on the raw text
3. **Brace extraction** — finds the outermost `{ ... }` in the text

If all 3 fail, the raw text is wrapped as a `style_note` with safe defaults — the session never crashes.

---

## 🖼️ The Shared Canvas

The canvas is a virtual structure with **5 regions**:

```
┌─────────────┬─────────────┐
│  top-left   │  top-right  │
├─────────────┼─────────────┤
│             │             │
│          center           │
│             │             │
├─────────────┼─────────────┤
│ bottom-left │ bottom-right│
└─────────────┴─────────────┘
```

### Region Ownership

| Status | Meaning |
|--------|---------|
| `free` | No agent has painted here yet |
| `owned` | One agent has claimed this region |
| `contested` | Both agents have painted in the same region |

### What the Canvas Tracks

1. **Region map** — who owns each zone
2. **Stroke history** — every `mark_op` with round number, agent, region, and emotion
3. **Semantic annotations** — style intent and theme per contribution
4. **Negotiation record** — complete dialogue between agents

Each round, the canvas provides a text summary to both agents showing:
- Region ownership map
- Last 12 stroke operations
- Last 8 semantic annotations

---

## 📋 The Critic Agent

After each round, the Critic evaluates the canvas on **4 dimensions** (from Section 3.4):

| Dimension | What It Measures |
|-----------|-----------------|
| **Compositional Coherence** (0-10) | Does the work cohere as a unified composition? |
| **Stylistic Dialogue** (0-10) | Is there productive stylistic interaction? |
| **Thematic Depth** (0-10) | Does the piece communicate a discernible theme? |
| **Technical Execution** (0-10) | Are strokes faithful to each agent's declared style? |

The Critic also provides:
- **Directive for Agent A** — specific, actionable suggestion
- **Directive for Agent B** — specific, actionable suggestion
- **Overall Commentary** — 2-3 sentences about the artwork's development

The Critic uses **temperature 0.7** (more analytical than creative) and **max 600 tokens**.

Its feedback is fed into the **next round** for both painting agents, creating an iterative improvement loop.

---

## ⚡ Dispute Resolution & Mediation

When Agent B responds with `intent: "dispute"`, the system enters a **mediation loop**:

```
Normal Round:
  Agent A → PROPOSE
  Agent B → ACKNOWLEDGE or YIELD
  ✓ Done

Disputed Round:
  Agent A → PROPOSE
  Agent B → DISPUTE ❌
    ↓
  ⚡ MEDIATION (up to 2 extra turns):
    Agent A → responds to dispute
    Agent B → responds to Agent A
    If B acknowledges/yields → ✓ Resolved
    If still disputing → one more turn
    If limit reached → proceed with last proposals
```

This creates a dynamic where Agent A (bold, 80% boldness) may push hard on creative choices, and Agent B (deferential, 70% deference) may occasionally push back when the proposal conflicts with its Cubist sensibilities.

---

## ⚙️ Configuration & Customization

All settings live in `config.py`. Here's what you can change:

### Main Controls

| Setting | Default | Location |
|---------|---------|----------|
| `NUM_ROUNDS` | `10` | `config.py` line 12 |
| `MODEL_NAME` | `"gpt-4o-mini"` | `config.py` line 13 |
| `THEME` | `"A surreal underwater cityscape at twilight"` | `config.py` line 14 |

### Agent Personas

You can modify any agent's personality by editing their config dict:

```python
AGENT_A_CONFIG = {
    "name": "Agent A",
    "style": "Impressionist",          # Change artistic style
    "skill_level": "Expert",           # Expert, Intermediate, Beginner
    "personality": {
        "boldness": 0.8,               # 0.0 = timid, 1.0 = aggressive
        "deference": 0.2,              # 0.0 = stubborn, 1.0 = always yields
        "whimsy": 0.9,                 # 0.0 = methodical, 1.0 = chaotic
    },
    "description": "...",              # Free-text persona description
}
```

### Alternative OpenAI Models

| Model | Speed | Quality | Cost |
|-------|-------|---------|------|
| `gpt-4o-mini` | ⚡ Fast | Good | Cheapest |
| `gpt-4o` | 🐢 Slower | Excellent | Moderate |
| `gpt-4.1-mini` | ⚡ Fast | Great | Cheap |
| `gpt-4.1` | 🐢 Slower | Excellent | Higher |

Change the model in `config.py` line 13:

```python
MODEL_NAME = "gpt-4o"  # Switch to the most powerful model
```

---

## 📂 File-by-File Code Walkthrough

### `main.py` — Session Orchestrator (~465 lines)

The entry point and main loop. Responsibilities:

1. **Windows compatibility** (lines 19-28) — Fixes console encoding for emoji and enables ANSI colors via colorama
2. **Environment loading** (lines 31-34) — `load_dotenv()` runs BEFORE importing agent modules, ensuring API keys are available when `OpenAI()` clients are created
3. **Pretty printers** (lines 69-161) — Colorful ANSI terminal output:
   - `print_header()` — Session banner with config summary
   - `print_agent_message()` — Color-coded agent output (cyan = A, magenta = B)
   - `print_critic_evaluation()` — Score bars (█/░) and directives
   - `print_mediation()` — Dispute mediation messages
4. **`print_final_decision()`** — End-of-session summary showing both agents' final contributions, the critic's verdict, and canvas ownership
5. **`run_session()`** — The core loop:
   - Validates both API keys are present
   - Creates Agent A (Key 1), Agent B (Key 2), Critic (Key 2), Canvas
   - Runs N rounds of propose → respond → mediate → apply → evaluate
   - Prints score progression and saves JSON transcript
6. **CLI** — Argparse with `--rounds/-n` and `--theme/-t`

### `agents.py` — Agent Classes (~270 lines)

Two agent classes that call the OpenAI API:

1. **`_call_openai()`** — API call wrapper with retry logic:
   - `AuthenticationError` → fails immediately with clear error message
   - `RateLimitError` → exponential backoff (2s, 4s, 8s)
   - `APIError` → linear retry (1s between attempts)
   - Max 3 retries for transient errors
2. **`PaintingAgent`** — Creative painting agent:
   - `__init__()` — Takes `api_key` parameter, creates `OpenAI(api_key=...)` client, builds system prompt from persona config
   - `_build_system_prompt()` — Constructs detailed system prompt with persona traits, theme, JSON schema, and creative rules
   - `generate_message()` — Builds user prompt with canvas state + partner's message + critic feedback, calls OpenAI, parses response into `AgentMessage`
3. **`CriticAgent`** — Evaluative agent:
   - `__init__()` — Takes `api_key` parameter, has its own system prompt focused on evaluation
   - `evaluate()` — Takes canvas state + both agents' messages, returns scored `CriticEvaluation`

### `protocol.py` — Message Schemas (209 lines)

Defines the structured data types and JSON parsing:

1. **`AgentMessage`** (dataclass) — Fields: sender, round, intent, theme, region, style_note, mark_ops, open_question, emotion_tag
   - `to_dict()` / `to_json()` — Serialization
   - `from_dict()` — Deserialization (ignores unknown keys)
   - `validate()` — Returns list of validation errors
2. **`CriticEvaluation`** (dataclass) — Fields: round, 4 scores (0-10), directives for each agent, commentary
   - `average_score` property — Mean of all 4 scores
3. **`_extract_json()`** — 3-strategy JSON extractor (markdown block → direct parse → brace extraction)
4. **`parse_agent_response()`** — Validates and normalizes agent JSON into `AgentMessage`
5. **`parse_critic_response()`** — Validates and normalizes critic JSON into `CriticEvaluation`, clamps scores to 0-10

### `canvas.py` — Shared Canvas (125 lines)

Manages the virtual canvas state:

1. **`CanvasRegion`** (dataclass) — name, owner, status (free/owned/contested)
2. **`SharedCanvas`** class:
   - `apply_operations()` — Applies an agent's strokes: updates region ownership, logs operations, records annotations
   - `get_state_summary()` — Builds text summary for agent context (region map, last 12 ops, last 8 annotations)
   - `get_full_log()` — Exports complete state for JSON transcript

### `config.py` — Configuration (84 lines)

All tunable parameters in one file:
- `NUM_ROUNDS`, `MODEL_NAME`, `THEME`
- `AGENT_A_CONFIG` — Impressionist persona (boldness 0.8, deference 0.2, whimsy 0.9)
- `AGENT_B_CONFIG` — Cubist persona (boldness 0.3, deference 0.7, whimsy 0.3)
- `CRITIC_CONFIG` — Evaluator description
- `CANVAS_REGIONS` — 5 canvas zones

---

## 📊 Output & Transcripts

### Terminal Output

Each round displays:

1. **Round header** — `◆ ROUND 3 of 10`
2. **Agent A's message** — Color-coded proposal with intent, strokes, emotion, and question
3. **Agent B's message** — Color-coded response
4. **Mediation** (if dispute) — Back-and-forth until resolved
5. **Critic evaluation** — Score bars, directives, and commentary

At the end of all 10 rounds:
- **Score Progression** — Visual bar chart showing improvement across rounds
- **Final Art Piece Decision** — Both agents' final strokes and the critic's verdict
- **Canvas Region Ownership** — Who controls each zone

### JSON Transcript

After every session, a detailed JSON file is saved to `logs/`:

```
logs/session_20260522_124839.json
```

The transcript contains:
- Theme, model, agent configs
- Start and finish timestamps
- Every round's exchanges (proposals, responses, mediation)
- Every critic evaluation with scores
- Final canvas state (regions, stroke history, annotations, negotiation record)

---

## 🔧 Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `ERROR: Missing OpenAI API key(s)!` | Keys not in `.env` | Open `.env`, paste both `sk-...` keys |
| `AUTHENTICATION FAILED: Your OpenAI API key is invalid` | Wrong or expired key | Get new keys at [platform.openai.com](https://platform.openai.com/api-keys) |
| `⏳ Rate limited — waiting Xs...` | Too many API calls | Automatic — system retries with exponential backoff |
| `ModuleNotFoundError: No module named 'openai'` | Dependencies not installed | Run `pip install -r requirements.txt` |
| Garbled emoji/unicode on Windows | Console encoding issue | Auto-fixed by code; or try `chcp 65001` in terminal |
| `Max retries exceeded` | API persistently failing | Wait 60 seconds and try again |

---

## 🎭 Example Output

Here's what a single round looks like in the terminal:

```
════════════════════════════════════════════════════════════
  ◆  ROUND 1 of 10
════════════════════════════════════════════════════════════

  Agent A is composing a proposal...
  🎨 Agent A (Impressionist, Expert)
    Intent: [PROPOSE]
    ┌─────────────────────────────────────────────────────
    │ Theme:    Twilight glow filtering through submerged coral spires
    │ Region:   top-left
    │ Style:    Wet-on-wet washes with light bleeding through edges
    │ Emotion:  wonder
    │ Operations:
    │   • Broad wash of violet-amber gradient across the upper sky-water
    │   • Feathered strokes of rose madder catching the last light
    │   • Flickering dabs of zinc white as bioluminescent sparks
    │ Question: How should we handle the transition where water meets sky?
    └─────────────────────────────────────────────────────

  Agent B is considering the proposal...
  🎭 Agent B (Cubist (Picasso-inspired), Intermediate)
    Intent: [ACKNOWLEDGE]
    ┌─────────────────────────────────────────────────────
    │ Theme:    Geometric coral towers refracting twilight
    │ Region:   bottom-left
    │ Style:    Angular planes with fragmented light facets
    │ Emotion:  serenity
    │ Operations:
    │   • Tessellated triangles of deep ultramarine for the ocean floor
    │   • Sharp-edged parallelograms of coral pink rising vertically
    │   • Overlapping transparent planes where your light touches my geometry
    │ Question: Can we create a gradient from your soft edges to my hard geometry?
    └─────────────────────────────────────────────────────

  Critic is evaluating the canvas...
  📋 CRITIC EVALUATION — Round 1
    ┌─────────────────────────────────────────────────────
    │ Compositional Coherence: █████░░░░░ 5/10
    │ Stylistic Dialogue:      ██████░░░░ 6/10
    │ Thematic Depth:          █████░░░░░ 5/10
    │ Technical Execution:     ██████░░░░ 6/10
    │ ─────────────────────────────────────────────
    │ Average: 5.5/10
    │
    │ → Agent A: Push the bioluminescence further — let light sources
    │            create focal points that draw the eye downward.
    │ → Agent B: Your geometry is strong but consider how Agent A's
    │            light sources could cast shadows on your angular forms.
    │
    │ A promising start with clear stylistic differentiation.
    │ The agents need to find more points of visual intersection.
    └─────────────────────────────────────────────────────
```

---

## 📄 License

This project is for educational and research purposes, implementing concepts from the included computational creativity paper.

---

## 🙏 Credits

- **Research Paper**: `computational_creativity (1).pdf` (included in project)
- **AI Model**: OpenAI `gpt-4o-mini` (default, configurable)
- **API**: [OpenAI Platform](https://platform.openai.com/)
