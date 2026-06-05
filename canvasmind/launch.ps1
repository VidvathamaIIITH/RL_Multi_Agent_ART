# ============================================================================
# CanvasMind - One-Command Launcher (frontend + backend, fully connected)
# ============================================================================
# Starts the complete application in a SINGLE process on a SINGLE port. The web
# UI (frontend) and the API + agents + image generation (backend) are served
# together, so they are always connected - no separate ports, no CORS.
#
# Usage (PowerShell):
#   .\launch.ps1            # runs on port 8000
#   .\launch.ps1 -Port 3000 # runs on a different port
#
# Then open http://localhost:8000/ in your browser.
# ============================================================================
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==================================================================="
Write-Host "  CanvasMind launcher  -  port $Port"
Write-Host "==================================================================="

if (-not $env:AZURE_OPENAI_API_KEY) {
  Write-Host "  NOTE: AZURE_OPENAI_API_KEY is not set in this shell."
  Write-Host "        Export it (and the endpoint) if backend/.env uses placeholders:"
  Write-Host '          $env:AZURE_OPENAI_API_KEY="your-key"'
  Write-Host '          $env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"'
}

function Test-Deps {
  python -c "import requests, fastapi, uvicorn" 2>$null
  return ($LASTEXITCODE -eq 0)
}

if (Test-Deps) {
  Write-Host "  Dependencies: already present"
} else {
  Write-Host "  Dependencies: setting up virtual environment + installing..."
  if (-not (Test-Path backend\venv)) { python -m venv backend\venv }
  & backend\venv\Scripts\Activate.ps1
  pip install --upgrade pip | Out-Null
  pip install -r backend\requirements.txt
  Write-Host "  Dependencies: installed"
}

Write-Host "  Launching CanvasMind on http://localhost:$Port/ ..."
python canvasmind_app.py --port $Port
