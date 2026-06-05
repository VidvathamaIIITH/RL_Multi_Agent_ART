#!/usr/bin/env bash
# ============================================================================
# CanvasMind — One-Command Launcher (frontend + backend, fully connected)
# ============================================================================
# This starts the complete application in a SINGLE process on a SINGLE port.
# The web UI (frontend) and the API + agents + image generation (backend) are
# served together, so they are always connected — no separate ports, no CORS,
# no proxy 404s.
#
# Usage:
#   ./launch.sh            # runs on port 8000
#   ./launch.sh 3000       # runs on a different port (e.g. one already proxied)
#
# Then open:
#   http://localhost:8000/                                  (local)
#   https://<host>/dev-workspaces/<workspace>/proxy/8000/   (behind the VM proxy)
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
PORT="${1:-8000}"

echo "==================================================================="
echo "  CanvasMind launcher  ·  port ${PORT}"
echo "==================================================================="

# 1) Make sure Azure credentials are available (exported, or in backend/.env).
if [ -z "${AZURE_OPENAI_API_KEY:-}" ]; then
  echo "  NOTE: AZURE_OPENAI_API_KEY is not exported in this shell."
  echo "        If backend/.env uses os.getenv placeholders, export them now:"
  echo '          export AZURE_OPENAI_API_KEY="your-key"'
  echo '          export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"'
  echo "        (The app will tell you clearly if they are missing.)"
fi

# 2) Ensure dependencies. Use whatever Python already has them; otherwise create
#    a virtual environment and install requirements once.
if python3 -c "import requests, fastapi, uvicorn" >/dev/null 2>&1; then
  echo "  Dependencies: already present"
  exec python3 canvasmind_app.py --port "$PORT"
fi

echo "  Dependencies: setting up virtual environment + installing..."
[ -d backend/venv ] || python3 -m venv backend/venv
# shellcheck disable=SC1091
source backend/venv/bin/activate
pip install -q --upgrade pip
pip install -q -r backend/requirements.txt
echo "  Dependencies: installed"

exec python canvasmind_app.py --port "$PORT"
