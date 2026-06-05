# CanvasMind — Run Everything on the Azure VM (End-to-End)

This guide gets CanvasMind running **perfectly on the VM with zero mistakes**.
There are two ways to run it — pick one:

| Option | File | What you get | Best for |
|---|---|---|---|
| **A. Single-file web app** ⭐ | `canvasmind_app.py` | Full browser UI: agents talking live, canvas images, critic gauges — all on **one port** | The visual demo on the VM (no proxy 404s) |
| **B. Terminal simulation** | `simulate_chat.py` | The full conversation printed in the terminal (no browser at all) | Quickest proof it works / SSH-only |

Both call Azure **exactly the same proven way**: raw REST with
`max_completion_tokens` (gpt-5.2 rejects `max_tokens`) and no custom temperature.
This is why they work where the old SDK-based app failed.

> **The whole product is now just 2 Python files** — `canvasmind_app.py`
> (frontend + backend + images combined) and `simulate_chat.py` (terminal demo).
> You do **not** need to build or run the React frontend at all. (The React app
> is still here for reference — see the optional section at the end.)

---

## Table of Contents

1. [Why the single-file app fixes the VM problems](#1-why-the-single-file-app-fixes-the-vm-problems)
2. [One-time VM setup](#2-one-time-vm-setup)
3. [Set your Azure credentials](#3-set-your-azure-credentials)
4. [Option A — Run the single-file web app](#4-option-a--run-the-single-file-web-app)
5. [Open it in the browser (through the proxy)](#5-open-it-in-the-browser-through-the-proxy)
6. [Option B — Run the terminal simulation](#6-option-b--run-the-terminal-simulation)
7. [Keep it running after you log out](#7-keep-it-running-after-you-log-out)
8. [Troubleshooting every error](#8-troubleshooting-every-error)
9. [Optional — the original React frontend](#9-optional--the-original-react-frontend)
10. [Quick command reference](#10-quick-command-reference)

---

## 1. Why the single-file app fixes the VM problems

The earlier blank screen / 404 errors happened because the React app ran on a
**separate port (3000)** behind a sub-path reverse proxy, and Vite emitted
absolute asset paths. `canvasmind_app.py` removes that entire class of problems:

- **One port (8000), one origin.** The UI is served by the backend itself, so
  there is no cross-origin call, no separate frontend port, no CORS.
- **Relative paths + Server-Sent Events.** The page fetches `api/...` relative
  to itself, so the proxy prefix is always preserved — no 404s.
- **Correct Azure calls.** Uses `max_completion_tokens` and omits `temperature`,
  matching the gpt-5.2 deployment requirements that broke the SDK provider.
- **Images included.** Generates canvas images with `gpt-image-1` server-side
  and streams them to the browser as base64 — nothing for the browser to fetch
  cross-origin.

---

## 2. One-time VM setup

Open the VS Code terminal connected to the VM and run:

```bash
cd ~/canvasmind        # or wherever the project lives, e.g. RL_Multi_Agent_ART/canvasmind

# Python 3.11 (skip if already present)
python3 --version

# Create and activate a virtual environment
python3 -m venv backend/venv
source backend/venv/bin/activate

# Install dependencies (requests, fastapi, uvicorn are the ones the app needs)
pip install --upgrade pip
pip install -r backend/requirements.txt
```

That's all the setup. The single-file app needs only `requests`, `fastapi`, and
`uvicorn`, which are all in `requirements.txt`.

---

## 3. Set your Azure credentials

The app reads credentials from the **shell environment first**, then from
`backend/.env`. On the GPU VM the key and endpoint are usually already exported.
Confirm with:

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

> If `gpt-image-1` is not deployed in your resource, leave it blank — the app
> still runs, just without canvas images (untick "Generate images" in the UI).

---

## 4. Option A — Run the single-file web app

```bash
cd ~/canvasmind
source backend/venv/bin/activate
python canvasmind_app.py --port 8000
```

You should see:

```
================================================================
  CanvasMind — Single-File Full-Stack App
================================================================
  Azure Endpoint  : https://your-resource.openai.azure.com/
  API Key         : ****abcd
  API Version     : 2025-04-01-preview
  Text Deployment : gpt-5.2
  Image Deployment: gpt-image-1
================================================================
  Open the app at:  http://localhost:8000/
  Behind a proxy :  https://<host>/.../proxy/8000/

INFO:     Uvicorn running on http://0.0.0.0:8000
```

Leave it running. If you see the `FATAL: Missing required environment variables`
message instead, go back to [Section 3](#3-set-your-azure-credentials).

---

## 5. Open it in the browser (through the proxy)

Because everything is on **port 8000**, open the proxy URL for port 8000
(not 3000):

```
https://rniazure.tcsapps.com/dev-workspaces/RAMA-GPU-A100/proxy/8000/
```

Replace `RAMA-GPU-A100` with your workspace name. You'll see the CanvasMind UI:

1. Type a creative brief (or keep the default), set rounds, optionally a style hint.
2. Click **Start Session**.
3. Watch live:
   - **ARIA** (left) proposes the artistic direction.
   - **NEXUS** (right) challenges and refines it.
   - **JUDGE** (center, below the canvas) scores all 5 dimensions each round.
   - The **canvas image** for each round appears in the center (if `gpt-image-1` is enabled).
   - A green **CONVERGED** banner shows when the agents agree (composite ≥ 7.5).

The bottom strip is a live event log.

> **No port 8000 in the proxy list?** Ask for port 8000 to be exposed, or run on
> a port that is already proxied: `python canvasmind_app.py --port 3000` and open
> `.../proxy/3000/`.

---

## 6. Option B — Run the terminal simulation

No browser needed — the entire conversation prints in the terminal:

```bash
cd ~/canvasmind
source backend/venv/bin/activate

python simulate_chat.py --prompt "A serene mountain lake at golden hour" --rounds 5
python simulate_chat.py --prompt "A cathedral interior" --rounds 6 --style "baroque chiaroscuro"
```

| Flag | Default | Meaning |
|---|---|---|
| `--prompt` | a cyberpunk forest brief | The creative brief |
| `--rounds` | `5` | Max rounds (1–20) |
| `--style` | empty | Optional style hint |

---

## 7. Keep it running after you log out

So the app survives an SSH/VS Code disconnect, run it under `tmux`:

```bash
sudo apt-get install -y tmux        # once
tmux new -s canvasmind
cd ~/canvasmind && source backend/venv/bin/activate
python canvasmind_app.py --port 8000
# detach: press Ctrl+B then D
# reattach later: tmux attach -t canvasmind
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

## 8. Troubleshooting every error

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: Missing required environment variables` | Key/endpoint not exported and not in `.env` | `export AZURE_OPENAI_API_KEY=...` and `AZURE_OPENAI_ENDPOINT=...` (Section 3) |
| `HTTP 401 ... invalid subscription key` | Wrong key or endpoint | Re-copy from Azure Portal → Keys and Endpoint |
| `HTTP 404 ... DeploymentNotFound` | Wrong deployment name | Make `AZURE_OPENAI_DEPLOYMENT_GPTTEXT52` match the exact name in Azure AI Studio → Deployments |
| `unsupported parameter: max_tokens` | Old SDK provider, not this app | Use `canvasmind_app.py` / `simulate_chat.py` — they send `max_completion_tokens` |
| `temperature ... not supported` | Custom temperature on a reasoning model | These files send no temperature; you're set |
| Browser shows blank / 404 on assets | You opened the **React (3000)** app behind the proxy | Use the single-file app on **port 8000** instead |
| `Blocked request ... host not allowed` (React only) | Vite host allowlist | Already fixed in `vite.config.ts` via `allowedHosts: ['rniazure.tcsapps.com']` |
| Canvas image never appears | `gpt-image-1` not deployed or slow | Confirm the image deployment exists; or untick "Generate images" |
| SSE stream stops early behind proxy | Proxy buffering | The app sets `X-Accel-Buffering: no`; if your proxy still buffers, use Option B (terminal) |
| `ModuleNotFoundError: requests` | Deps not installed / venv not active | `source backend/venv/bin/activate && pip install -r backend/requirements.txt` |

---

## 9. Optional — the original React frontend

You do **not** need this for the VM demo, but if you want the full React UI on
port 3000, the config is already fixed for the proxy:

```bash
cd ~/canvasmind/frontend
npm install
npm run build
npm run preview -- --host 0.0.0.0 --port 3000
# open https://<host>/.../proxy/3000/
```

`vite.config.ts` already uses `base: './'` (relative paths) and
`allowedHosts: ['rniazure.tcsapps.com']`. The React app talks to the backend via
`VITE_BACKEND_URL` in `frontend/.env`; for full end-to-end you must also expose
the backend (port 8000) through the proxy and point those URLs at it. Because
that wiring is fragile through a corporate proxy, **the single-file app
(Option A) is the recommended path.**

---

## 10. Quick command reference

```bash
# Activate venv (every new shell)
source ~/canvasmind/backend/venv/bin/activate

# Check creds are present
echo "$AZURE_OPENAI_API_KEY"; echo "$AZURE_OPENAI_ENDPOINT"

# Run the full web app (one port, browser UI)
python ~/canvasmind/canvasmind_app.py --port 8000
#   → open https://<host>/dev-workspaces/<workspace>/proxy/8000/

# Run the terminal-only demo
python ~/canvasmind/simulate_chat.py --prompt "A neon koi pond" --rounds 5

# Health check
curl http://localhost:8000/api/health

# Run under tmux (survives disconnect)
tmux new -s canvasmind
#   ... start the app, then Ctrl+B then D to detach
tmux attach -t canvasmind
```

---

*CanvasMind — TCS Research Computational Creativity Platform*
*Single-file app: `canvasmind_app.py` · Terminal demo: `simulate_chat.py`*
*Azure: gpt-5.2 (text) + gpt-image-1 (image) via REST · API version 2025-04-01-preview*
