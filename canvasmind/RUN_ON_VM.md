# CanvasMind — Run Everything on the Azure VM (End-to-End)

This guide gets CanvasMind running **perfectly on the VM with zero mistakes**, including the **brand new cinematic monochrome design** that has been applied to the React frontend.

The system consists of two parts running in tandem:
1. **The Backend (Port 8000)**: A Python FastAPI server that connects to Azure OpenAI, manages the agents (ARIA, NEXUS, JUDGE), and handles image generation.
2. **The Frontend (Port 3000)**: A stunning, cinematic React frontend that provides a real-time, side-by-side view of the agents co-creating on a shared canvas.

---

## Table of Contents

1. [One-time VM setup](#1-one-time-vm-setup)
2. [Set your Azure credentials (CRITICAL)](#2-set-your-azure-credentials-critical)
3. [Start the Backend Server](#3-start-the-backend-server)
4. [Start the Cinematic Frontend](#4-start-the-cinematic-frontend)
5. [Open it in the browser (through the proxy)](#5-open-it-in-the-browser-through-the-proxy)
6. [The agents & the RL research layer](#6-the-agents--the-rl-research-layer)
7. [Troubleshooting every error](#7-troubleshooting-every-error)

---

## 1. One-time VM setup

If you haven't already, you need to set up the dependencies for both the frontend and the backend. Open the VS Code terminal connected to the VM:

### Backend Setup:
```bash
cd ~/canvasmind        # or wherever the project lives
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### Frontend Setup:
```bash
cd ~/canvasmind/frontend
npm install
```

---

## 2. Set your Azure credentials (CRITICAL)

The backend requires Azure OpenAI credentials to power ARIA, NEXUS, and JUDGE. 
It reads credentials from the **shell environment first**, then from `backend/.env`.

Check if they are set:
```bash
echo "$AZURE_OPENAI_API_KEY"      # should print your key
echo "$AZURE_OPENAI_ENDPOINT"     # should print https://<resource>.openai.azure.com/
```

If they are **empty**, you MUST export them (replace with your real values):
```bash
export AZURE_OPENAI_API_KEY="your-real-key"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
```

> **Note on Models:** The backend defaults to `gpt-5.2` for text and `gpt-image-1` for images. If your image model lacks the 'edits' endpoint, the app gracefully falls back to generating fresh images each turn so you still get a visual output.

---

## 3. Start the Backend Server

The backend provides the intelligence for the app. Keep this running in one terminal window.

```bash
cd ~/canvasmind
./launch.sh
# Alternatively on Windows: .\launch.ps1
```

You should see:
```text
INFO:     Uvicorn running on http://0.0.0.0:8000
```
*(If you see `FATAL: Missing required environment variables`, go back to step 2).*

---

## 4. Start the Cinematic Frontend

Open a **second terminal window** (do not close the backend!). We will start the newly redesigned React frontend.

```bash
cd ~/canvasmind/frontend
npm run dev
```

You should see Vite launch on `http://localhost:3000/`. This frontend connects automatically to the backend on port 8000.

---

## 5. Open it in the browser (through the proxy)

Since you are running both servers on the VM, you must access the **Frontend (Port 3000)** through the Azure VM reverse proxy.

Open this URL in your browser:
```text
https://rniazure.tcsapps.com/dev-workspaces/RAMA-GPU-A100/proxy/3000/
```
*(Replace `RAMA-GPU-A100` with your actual workspace name).*

### How to use it:
1. You will be greeted by the cinematic **"Two minds. One canvas."** briefing screen.
2. Select **"AI Surprise"** to have a brief generated for you, or **"Write My Own"** to enter a custom prompt.
3. Click **"Begin Session →"**.
4. The UI will transition to the Stage. You will see ARIA on the left, NEXUS on the right, and the Canvas in the center. Watch as they take turns adding objects to the painting!
5. Scroll down to see the **JUDGE** band score the collaboration when the round finishes.

---

## 6. The agents & the RL research layer

CanvasMind's painters are **generative agents** (after Park et al., *Generative Agents*, UIST'23) wrapped in an **inference-time reinforcement-learning** layer. On the briefing screen you control two new things:

- **Agent Expertise** — set ARIA and NEXUS each to **Beginner / Intermediate / Expert**. This changes their persona, vocabulary, technique, and rendering sophistication, and they can be **mixed** (e.g. ARIA Expert + NEXUS Beginner).
- **System Autonomy** — **Autonomous / Shared / Human-led**; this sets the human's share of agency (and, with a directive, whether the agents may *resist* it).

During a session each agent **remembers** what it and its partner did, **retrieves** relevant memories (recency + importance + relevance), and **reflects** to learn from the collaboration. On top of that runs the RL layer:

- **Reward model + best-of-N** — each turn the agent samples *N* candidate additions and the critic-as-reward-model scores them; the agent acts on the best (tune with `export CM_BEST_OF_N=2`). Each agent card shows the chosen **reward**, the **strategy**, and the **rejected** candidates.
- **Misaligned rewards + UCB bandit** — ARIA is rewarded mostly for *coherence*, NEXUS mostly for *originality* (a general-sum game); a bandit lets each agent **learn** which strategies pay off.
- **Reward-aware Reflexion** — a low-reward turn triggers a learning reflection.
- **Research Dashboard** (appears below JUDGE when the run finishes): **Shapley credit** assignment (accountability — who is responsible for the result), an **empowerment** agency metric for ARIA / NEXUS / human, a **Goodhart reward-hacking monitor** (optimized proxy vs. independent quality), the **Pareto** trace (coherence ↔ originality), and the bandit's learned strategies.

> **Compute note:** the RL layer makes several model calls per turn (candidate sampling, reward scoring, an independent-quality probe, plus Shapley value calls at the end), so a live run is heavier than before. Lower it with `export CM_BEST_OF_N=1` or fewer rounds. **Demo Mode** (the chip in the top nav, or automatic when the backend is offline) shows the entire UI — including the Research Dashboard — instantly with zero API calls.

---

## 7. Troubleshooting every error

| Symptom | Cause | Fix |
|---|---|---|
| **Frontend says "Demo Mode" / Backend disconnected** | Frontend can't reach the backend API | Ensure the backend is running on port 8000. Check if `VITE_BACKEND_URL` in `frontend/.env` correctly points to port 8000. |
| **FATAL: Missing required environment variables** | Key/endpoint not exported | `export AZURE_OPENAI_API_KEY=...` and `AZURE_OPENAI_ENDPOINT=...` (Section 2) |
| **HTTP 401 ... invalid subscription key** | Wrong key or endpoint | Re-copy from Azure Portal → Keys and Endpoint |
| **Only image #1 appears** | Azure `gpt-image-1` quota limit | The image generation is being rate-limited. Wait a minute; check Azure quota. |
| **Browser shows blank / 404** | You opened the proxy for port 8000 | You must open the proxy for **3000** (`.../proxy/3000/`) to see the React frontend. |
| **ModuleNotFoundError: requests** | Backend dependencies missing | Run `pip install -r backend/requirements.txt` in the active virtual environment. |

---

*CanvasMind — TCS Research Computational Creativity Platform*
*Frontend: React + Vite (Port 3000) · Backend: FastAPI (Port 8000)*
