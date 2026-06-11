# CanvasMind — Run Everything on the Azure VM (End-to-End)

This guide gets CanvasMind running **perfectly on the VM with zero mistakes**.
The whole product is now **2 Python files + 1 launcher**:

| File | What it is |
|---|---|
| **`launch.sh`** / `launch.ps1` | One-command launcher (sets up deps, starts the app) — **run this** |
| **`canvasmind_app.py`** ⭐ | The complete app: web UI + backend + 3-image co-creation, on **one port** |
| **`simulate_chat.py`** | Terminal-only demo (no browser) — agents printed to the console |

Both Python files call Azure **exactly the proven way**: raw REST with
`max_completion_tokens` (gpt-5.2 rejects `max_tokens`) and no custom temperature.
This is why they work where the old SDK-based app failed. **You do not need to
build or run the React frontend** — the single-file app *is* the frontend and
backend together.

> ✅ **Verified end-to-end.** The full pipeline was tested through the real HTTP
> server + SSE: `session → ARIA(partial image) → NEXUS(builds on it) →
> JUDGE(combines both) → 3 downloadable images → done`. Only the live Azure call
> needs your VM credentials.

---

## Table of Contents

1. [What the app does (the 3-image co-creation)](#1-what-the-app-does-the-3-image-co-creation)
2. [Why this fixes the VM proxy problems](#2-why-this-fixes-the-vm-proxy-problems)
3. [One-time VM setup](#3-one-time-vm-setup)
4. [Set your Azure credentials](#4-set-your-azure-credentials)
5. [Run it (one command)](#5-run-it-one-command)
6. [Open it in the browser (through the proxy)](#6-open-it-in-the-browser-through-the-proxy)
7. [Terminal-only option](#7-terminal-only-option)
8. [Keep it running after you log out](#8-keep-it-running-after-you-log-out)
9. [Troubleshooting every error](#9-troubleshooting-every-error)
10. [Optional — the original React frontend](#10-optional--the-original-react-frontend)
11. [Quick command reference](#11-quick-command-reference)

---

## 1. What the app does (the 3-image co-creation)

**Two ways to start a brief** (toggle at the top of the page):

- **✨ AI Surprise** *(default)* — click **"Surprise Me"** and the AI invents a
  striking, unexpected brief and style on its own. The chosen brief is shown in
  the UI, then the co-creation begins automatically.
- **✍️ Write my own** — switch to the manual prompt box, type your own brief and
  optional style, and click **Start Co-Creation**.

Either way, **ARIA and NEXUS then paint ONE shared canvas, step by step, taking
turns to add a single new object each turn** — true additive collaboration:

1. The canvas starts blank. **ARIA** adds the first object (e.g. a mountain
   range) → image displayed.
2. That exact canvas is handed to **NEXUS**, which looks at it and **adds one new
   object** on top (e.g. a forest), preserving everything already there → image displayed.
3. Back to **ARIA**, which adds another new object → displayed. …and so on.

This continues for **N back-and-forths** (default **5 → 10 turns → 10 images**).
**Every step is displayed** in a left-to-right filmstrip so you can watch the
painting grow object by object (exactly like the progressive reference frames).

- Each turn uses Azure's image-to-image *edits* endpoint with the instruction to
  **keep everything already painted and ADD only one new element** — so it is
  additive collaboration, not a full repaint/refinement.
- **JUDGE does NOT edit the artwork.** It only evaluates how well the two agents
  collaborated and **presents the final accumulated canvas** as the combined
  result (the last step already contains every contribution).

The **"⬇ Download all steps"** button saves every step image
(`canvasmind_step01_ARIA_<object>.png`, `…step02_NEXUS_<object>.png`, …).

---

## 2. Why this fixes the VM proxy problems

The earlier blank screen / 404 errors happened because the React app ran on a
**separate port (3000)** behind a sub-path reverse proxy, and Vite emitted
absolute asset paths. `canvasmind_app.py` removes that entire class of problems:

- **One port, one origin.** The UI is served by the backend itself — no
  cross-origin call, no separate frontend port, no CORS.
- **Relative paths + Server-Sent Events.** The page fetches `api/...` relative to
  itself, so the proxy prefix is always preserved — no 404s.
- **Correct Azure calls.** Uses `max_completion_tokens` and omits `temperature`,
  matching the gpt-5.2 requirements that broke the SDK provider.
- **Images stream as base64.** Generated server-side with `gpt-image-1` and sent
  inline — nothing for the browser to fetch cross-origin.

---

## 3. One-time VM setup

The launcher does this for you, but here it is explicitly. Open the VS Code
terminal connected to the VM:

```bash
cd ~/canvasmind        # or wherever the project lives, e.g. RL_Multi_Agent_ART/canvasmind
python3 --version      # Python 3.11 expected

python3 -m venv backend/venv
source backend/venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt    # installs requests, fastapi, uvicorn, ...
```

---

## 4. Set your Azure credentials

The app reads credentials from the **shell environment first**, then from
`backend/.env`. On the GPU VM the key and endpoint are usually already exported.
Confirm:

```bash
echo "$AZURE_OPENAI_API_KEY"      # should print your key
echo "$AZURE_OPENAI_ENDPOINT"     # should print https://<resource>.openai.azure.com/
```

If they are **empty**, export them (replace with your real values):

```bash
export AZURE_OPENAI_API_KEY="your-real-key"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
```

The deployment names and API version come from `backend/.env`, already set to:

```bash
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_DEPLOYMENT_GPTTEXT52=gpt-5.2
AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1=gpt-image-1
```

> **Image-to-image note:** NEXUS and JUDGE feed the previous image(s) into the
> next step using Azure's `images/edits` endpoint. If your `gpt-image-1`
> deployment only supports generation, the app **automatically falls back** to a
> fresh generation with a descriptive prompt — so you still get all 3 images.
> If `gpt-image-1` is not deployed at all, leave it blank and the app runs as a
> text-only dialogue.

---

## 5. Run it (one command)

```bash
cd ~/canvasmind          # or RL_Multi_Agent_ART/canvasmind
chmod +x launch.sh       # first time only
./launch.sh              # runs on port 8000
#   ./launch.sh 3000     # or any port already exposed by the proxy
```

The launcher checks credentials, ensures dependencies (creating a venv if
needed), then starts the app. You should see:

```
================================================================
  CanvasMind — Step-by-Step Collaborative Painting
================================================================
  Azure Endpoint  : https://your-resource.openai.azure.com/
  API Key         : ****abcd
  API Version     : 2025-04-01-preview
  Text Deployment : gpt-5.2
  Image Deployment: gpt-image-1
================================================================
  Open the app at:  http://localhost:8000/
INFO:     Uvicorn running on http://0.0.0.0:8000
```

If you see `FATAL: Missing required environment variables` instead, go back to
[Section 4](#4-set-your-azure-credentials).

> **Windows / local:** use `.\launch.ps1 -Port 8000` (or `python canvasmind_app.py --port 8000`).

---

## 6. Open it in the browser (through the proxy)

Everything is on **port 8000**, so open the proxy URL for **8000** (not 3000):

```
https://rniazure.tcsapps.com/dev-workspaces/RAMA-GPU-A100/proxy/8000/
```

Replace `RAMA-GPU-A100` with your workspace name. In the UI:

1. Pick a mode at the top:
   - **✨ AI Surprise** → click **"Surprise Me"** to let the AI invent a striking
     brief + style (shown in the UI, then it creates), **or**
   - **✍️ Write my own** → type your own brief + optional style, click **Start Co-Creation**.
2. Optionally set **Back-and-forths** (default 5 → 10 step images).
3. Watch the painting grow live:
   - The big **Shared Canvas** view updates to the latest step.
   - The **filmstrip** below fills with every turn's image, left to right.
   - **ARIA** (left feed) and **NEXUS** (right feed) each say what they see and
     the one new object they add, so the conversation is legible.
   - **JUDGE** scores the collaboration and the final canvas is marked **✓ FINAL**.
4. Click **⬇ Download all steps** to save every step image as a PNG.

The bottom strip is a live event log.

> **No port 8000 in the proxy list?** Run on a port that is already proxied:
> `./launch.sh 3000` and open `.../proxy/3000/`.

---

## 7. Terminal-only option

No browser needed — the whole conversation prints in the terminal:

```bash
cd ~/canvasmind && source backend/venv/bin/activate
python simulate_chat.py --prompt "A serene mountain lake at golden hour" --rounds 5
python simulate_chat.py --prompt "A cathedral interior" --rounds 6 --style "baroque chiaroscuro"
```

| Flag | Default | Meaning |
|---|---|---|
| `--prompt` | a cyberpunk forest brief | The creative brief |
| `--rounds` | `5` | Max rounds (1–20) |
| `--style` | empty | Optional style hint |

---

## 8. Keep it running after you log out

Under `tmux` (survives an SSH/VS Code disconnect):

```bash
sudo apt-get install -y tmux        # once
tmux new -s canvasmind
cd ~/canvasmind && ./launch.sh
# detach: Ctrl+B then D   ·   reattach: tmux attach -t canvasmind
```

Or as a permanent systemd service:

```bash
sudo tee /etc/systemd/system/canvasmind.service >/dev/null <<'EOF'
[Unit]
Description=CanvasMind Single-File App
After=network.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser/canvasmind
Environment="AZURE_OPENAI_API_KEY=your-real-key"
Environment="AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/"
ExecStart=/home/azureuser/canvasmind/backend/venv/bin/python /home/azureuser/canvasmind/canvasmind_app.py --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now canvasmind
sudo journalctl -u canvasmind -f      # live logs
```

---

## 9. Troubleshooting every error

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: Missing required environment variables` | Key/endpoint not exported and not in `.env` | `export AZURE_OPENAI_API_KEY=...` and `AZURE_OPENAI_ENDPOINT=...` (Section 4) |
| `HTTP 401 ... invalid subscription key` | Wrong key or endpoint | Re-copy from Azure Portal → Keys and Endpoint |
| `HTTP 404 ... DeploymentNotFound` | Wrong deployment name | Make `AZURE_OPENAI_DEPLOYMENT_GPTTEXT52` match the exact name in Azure AI Studio → Deployments |
| `unsupported parameter: max_tokens` | Old SDK provider, not this app | Use `canvasmind_app.py` / `simulate_chat.py` — they send `max_completion_tokens` |
| Image #2 / #3 falls back to a fresh image | `gpt-image-1` deployment has no `edits` capability | Expected — the app logs a warning and regenerates so you still get 3 images |
| Only image #1 appears | `gpt-image-1` slow or rate-limited | Wait; check Azure quota. Image steps are non-fatal and logged |
| No images at all, just text | `AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1` blank | Set the image deployment name in `backend/.env` |
| Browser shows blank / 404 on assets | You opened the **React (3000)** app | Use the single-file app on **port 8000** |
| `Blocked request ... host not allowed` (React only) | Vite host allowlist | Already fixed in `vite.config.ts` via `allowedHosts: ['rniazure.tcsapps.com']` |
| SSE stream stops early behind proxy | Proxy buffering | The app sets `X-Accel-Buffering: no`; if your proxy still buffers, use the terminal option (Section 7) |
| `ModuleNotFoundError: requests` | Deps not installed / venv not active | `./launch.sh` handles this, or `pip install -r backend/requirements.txt` in the venv |

---

## 10. Optional — the original React frontend

You do **not** need this for the VM demo. If you want the React UI on port 3000,
the config is already fixed for the proxy (`base: './'` +
`allowedHosts: ['rniazure.tcsapps.com']`):

```bash
cd ~/canvasmind/frontend
npm install
npm run build
npm run preview -- --host 0.0.0.0 --port 3000
# open https://<host>/.../proxy/3000/
```

The React app talks to the backend via `VITE_BACKEND_URL` in `frontend/.env`; for
full end-to-end you must also expose the backend through the proxy. Because that
wiring is fragile through a corporate proxy, **the single-file app is the
recommended path.**

---

## 11. Quick command reference

```bash
# One-command launch (sets up deps, starts the app on port 8000)
cd ~/canvasmind && ./launch.sh
#   → open https://<host>/dev-workspaces/<workspace>/proxy/8000/

# Check creds are present
echo "$AZURE_OPENAI_API_KEY"; echo "$AZURE_OPENAI_ENDPOINT"

# Run the app directly (venv active)
python ~/canvasmind/canvasmind_app.py --port 8000

# Terminal-only demo
python ~/canvasmind/simulate_chat.py --prompt "A neon koi pond" --rounds 5

# Health check
curl http://localhost:8000/api/health

# tmux (survives disconnect)
tmux new -s canvasmind     # start, then Ctrl+B then D
tmux attach -t canvasmind
```

---

*CanvasMind — TCS Research Computational Creativity Platform*
*Launcher: `launch.sh` · App: `canvasmind_app.py` · Terminal demo: `simulate_chat.py`*
*Azure: gpt-5.2 (text) + gpt-image-1 (image, with image-to-image edits) via REST · API version 2025-04-01-preview*
