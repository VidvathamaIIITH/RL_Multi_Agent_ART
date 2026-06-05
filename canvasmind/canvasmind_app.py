#!/usr/bin/env python3
"""
CanvasMind — Single-File Full-Stack Application
===============================================

EVERYTHING in one file: the backend (Azure OpenAI REST calls), the multi-agent
orchestration (ARIA + NEXUS + JUDGE), live image generation (gpt-image-1), AND
the complete web UI (served as one HTML page from the same port).

Why one file + one port?
  - No separate Vite frontend, so NO reverse-proxy 404s, NO CORS, NO WebSocket
    handshake problems. The browser loads the UI and streams events from the
    SAME origin using Server-Sent Events (works perfectly behind the TCS proxy).
  - Calls Azure exactly like the proven simulate_chat.py: raw REST with
    `max_completion_tokens` (gpt-5.2 rejects `max_tokens`) and no custom
    temperature. This is why it "just works" where the SDK-based app failed.

RUN IT (one command):

    python canvasmind_app.py
    python canvasmind_app.py --port 8000

Then open the app in the browser:
    Local : http://localhost:8000/
    VM/proxy: https://<host>/dev-workspaces/<workspace>/proxy/8000/

CREDENTIALS:
  Reads from environment first (the VM usually exports AZURE_OPENAI_API_KEY and
  AZURE_OPENAI_ENDPOINT), then fills the rest from backend/.env. Required:
    AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT_GPTTEXT52
  Optional (enables live canvas images):
    AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

# ---------------------------------------------------------------------------
# UTF-8 terminal safety (Windows consoles default to cp1252)
# ---------------------------------------------------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

APP_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Minimal .env loader — never crashes on malformed lines, never overrides a
# value already exported in the shell (so the VM's exported creds win).
# ---------------------------------------------------------------------------
def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and "os.getenv" not in value:
            os.environ.setdefault(key, value)


# Load from common locations so it works whether you run from canvasmind/ or backend/.
for candidate in (APP_DIR / "backend" / ".env", APP_DIR / ".env"):
    load_env_file(candidate)

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT_GPTTEXT52 = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPTTEXT52")
AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1 = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1")


def validate_config() -> None:
    required = {
        "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
        "AZURE_OPENAI_DEPLOYMENT_GPTTEXT52": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print("\n[CanvasMind] FATAL: Missing required environment variables:")
        for k in missing:
            print(f"  - {k}")
        print("\nExport them in your shell or set them in backend/.env, then re-run.\n")
        sys.exit(1)
    if not AZURE_OPENAI_ENDPOINT.startswith("https://"):
        print("[CanvasMind] FATAL: AZURE_OPENAI_ENDPOINT must start with https://")
        sys.exit(1)

    print("\n" + "=" * 64)
    print("  CanvasMind — Single-File Full-Stack App")
    print("=" * 64)
    print(f"  Azure Endpoint  : {AZURE_OPENAI_ENDPOINT}")
    print(f"  API Key         : ****{AZURE_OPENAI_API_KEY[-4:]}")
    print(f"  API Version     : {AZURE_OPENAI_API_VERSION}")
    print(f"  Text Deployment : {AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}")
    print(f"  Image Deployment: {AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1 or 'not set (images disabled)'}")
    print("=" * 64 + "\n")


# ---------------------------------------------------------------------------
# Azure OpenAI — raw REST (matches the proven simulate_chat.py exactly)
# ---------------------------------------------------------------------------
def azure_chat_completion(messages: List[Dict[str, str]],
                          max_completion_tokens: int = 1800,
                          timeout: int = 180) -> str:
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}"
           f"/chat/completions?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    # NOTE: gpt-5.2 requires max_completion_tokens, NOT max_tokens, and rejects
    # a custom temperature. Keep the payload minimal.
    payload = {"messages": messages, "max_completion_tokens": max_completion_tokens}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure chat failed HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("Azure returned an empty chat response.")
    return content.strip()


def azure_generate_image(prompt: str, size: str = "1024x1024", timeout: int = 180) -> Optional[str]:
    """Returns a data: URL (base64 PNG) or None if image generation is unavailable."""
    if not AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1:
        return None
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1}"
           f"/images/generations?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {"prompt": prompt[:3900], "size": size, "n": 1}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure image failed HTTP {resp.status_code}: {resp.text[:400]}")
    item = (resp.json().get("data") or [{}])[0]
    if item.get("b64_json"):
        return "data:image/png;base64," + item["b64_json"]
    if item.get("url"):
        return item["url"]
    return None


# ---------------------------------------------------------------------------
# JSON extraction + agent / critic prompts (verbatim from the working sim)
# ---------------------------------------------------------------------------
def extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return json.loads(cleaned[start:end + 1])


def safe_get(d: Dict[str, Any], k: str, default: Any = "") -> Any:
    v = d.get(k, default)
    return default if v is None else v


AGENT_JSON_SCHEMA = """
Return only valid JSON with this structure:
{
  "sender": "ARIA or NEXUS",
  "intent": "propose | critique | refine | converge",
  "confidence_score": 0.0,
  "artistic_goal": "...",
  "palette": ["#hex", "#hex"],
  "region": "...",
  "composition_notes": "...",
  "emotional_register": "...",
  "reasoning": "...",
  "critique": "...",
  "next_action": "..."
}
"""

CRITIC_JSON_SCHEMA = """
Return only valid JSON with this structure:
{
  "round": 1,
  "scores": {
    "compositional_coherence": 0.0,
    "style_fidelity": 0.0,
    "emotional_resonance": 0.0,
    "originality": 0.0,
    "clarity_of_next_action": 0.0,
    "composite": 0.0
  },
  "reasoning": "...",
  "contradictions_detected": ["..."],
  "weak_ideas": ["..."],
  "directive_agent_a": "...",
  "directive_agent_b": "...",
  "recommended_next_step": "...",
  "convergence_signal": false
}
"""


def build_agent_messages(agent_name, prompt, style_hint, round_number,
                         transcript, canvas_description, critic_feedback):
    if agent_name == "ARIA":
        personality = ("You are ARIA, the Creative Director. You are decisive, visual, "
                       "composition-focused, and skilled at turning vague ideas into a coherent artwork plan.")
    else:
        personality = ("You are NEXUS, the Creative Challenger. You question weak ideas, "
                       "increase originality, add conceptual tension, and improve the plan without derailing it.")
    user_content = f"""
Creative brief:
{prompt}

Style hint:
{style_hint or "none"}

Current round:
{round_number}

Current canvas description:
{canvas_description}

Critic feedback for you:
{critic_feedback or "none yet"}

Conversation so far:
{chr(10).join(transcript[-8:]) if transcript else "none yet"}

Task:
As {agent_name}, produce the next structured contribution to the artwork discussion.
Be concrete, visual, and useful. Do not be generic.

{AGENT_JSON_SCHEMA}
"""
    return [{"role": "system", "content": personality},
            {"role": "user", "content": user_content}]


def build_critic_messages(prompt, style_hint, round_number, transcript, canvas_description):
    system = ("You are JUDGE, a rigorous visual-art critic. You evaluate ARIA and NEXUS, "
              "score their current plan, identify contradictions, and decide whether the agents have converged.")
    user_content = f"""
Creative brief:
{prompt}

Style hint:
{style_hint or "none"}

Round:
{round_number}

Current canvas description:
{canvas_description}

Conversation to evaluate:
{chr(10).join(transcript[-10:])}

Instructions:
Score strictly from 0 to 10.
Set convergence_signal to true only if the plan is coherent, actionable, visually unified, and composite >= 7.5.

{CRITIC_JSON_SCHEMA}
"""
    return [{"role": "system", "content": system},
            {"role": "user", "content": user_content}]


def readable_agent_message(msg: Dict[str, Any]) -> str:
    parts = [f"{safe_get(msg, 'sender', 'Agent')} intent={safe_get(msg, 'intent', '?')}: {safe_get(msg, 'artistic_goal')}"]
    if safe_get(msg, "composition_notes"):
        parts.append(f"Composition: {safe_get(msg, 'composition_notes')}")
    palette = safe_get(msg, "palette", [])
    if isinstance(palette, list) and palette:
        parts.append(f"Palette: {', '.join(map(str, palette[:6]))}")
    if safe_get(msg, "critique"):
        parts.append(f"Critique: {safe_get(msg, 'critique')}")
    if safe_get(msg, "next_action"):
        parts.append(f"Next: {safe_get(msg, 'next_action')}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Session orchestration — runs in a background thread, streams events via queue
# ---------------------------------------------------------------------------
SESSIONS: Dict[str, "Session"] = {}


class Session:
    def __init__(self, prompt: str, rounds: int, style: str, make_images: bool):
        self.id = uuid.uuid4().hex
        self.prompt = prompt
        self.rounds = max(1, min(rounds, 20))
        self.style = style
        self.make_images = make_images and bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1)
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def emit(self, event: Dict[str, Any]) -> None:
        self.events.put(event)

    def start(self) -> None:
        self.thread.start()

    def _run_agent(self, agent_name, role, prompt, style, rnd, transcript, canvas_desc, feedback):
        raw = azure_chat_completion(build_agent_messages(
            agent_name, prompt, style, rnd, transcript, canvas_desc, feedback))
        try:
            data = extract_json_object(raw)
        except Exception:
            data = {
                "sender": agent_name,
                "intent": "propose" if agent_name == "ARIA" else "critique",
                "confidence_score": 0.7,
                "artistic_goal": raw[:700],
                "palette": [], "region": "whole canvas",
                "composition_notes": "Model returned unstructured text; using as proposal.",
                "emotional_register": "evocative", "reasoning": raw[:900],
                "critique": "", "next_action": "Continue refining in the next turn.",
            }
        data["sender"] = agent_name
        return data

    def _run_critic(self, prompt, style, rnd, transcript, canvas_desc):
        raw = azure_chat_completion(build_critic_messages(prompt, style, rnd, transcript, canvas_desc))
        try:
            data = extract_json_object(raw)
        except Exception:
            data = {
                "round": rnd,
                "scores": {"compositional_coherence": 6.0, "style_fidelity": 6.0,
                           "emotional_resonance": 6.0, "originality": 6.0,
                           "clarity_of_next_action": 6.0, "composite": 6.0},
                "reasoning": raw[:900], "contradictions_detected": [],
                "weak_ideas": ["Critic returned unstructured text; continue refining."],
                "directive_agent_a": "Clarify composition and focal hierarchy.",
                "directive_agent_b": "Challenge the weakest visual idea and add specificity.",
                "recommended_next_step": "Continue another round.", "convergence_signal": False,
            }
        data["round"] = rnd
        return data

    def _run(self) -> None:
        start = time.time()
        transcript: List[str] = [f"USER BRIEF: {self.prompt}"]
        canvas_desc = "Blank canvas. No operations yet."
        feedback_a = feedback_b = None
        composite_history: List[float] = []
        converged = False

        self.emit({"type": "session", "prompt": self.prompt, "rounds": self.rounds,
                   "style": self.style, "model": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
                   "images": self.make_images})
        try:
            for rnd in range(1, self.rounds + 1):
                self.emit({"type": "round", "round": rnd})

                aria = self._run_agent("ARIA", "Creative Director", self.prompt, self.style,
                                        rnd, transcript, canvas_desc, feedback_a)
                self.emit({"type": "agent", "agent": "ARIA", "role": "Creative Director", "message": aria})
                transcript.append(readable_agent_message(aria))
                canvas_desc = (f"Round {rnd} ARIA direction: {safe_get(aria, 'artistic_goal')}. "
                               f"{safe_get(aria, 'composition_notes')} "
                               f"Emotional register: {safe_get(aria, 'emotional_register')}.")

                nexus = self._run_agent("NEXUS", "Creative Challenger", self.prompt, self.style,
                                         rnd, transcript, canvas_desc, feedback_b)
                self.emit({"type": "agent", "agent": "NEXUS", "role": "Creative Challenger", "message": nexus})
                transcript.append(readable_agent_message(nexus))

                evaluation = self._run_critic(self.prompt, self.style, rnd, transcript, canvas_desc)
                self.emit({"type": "critic", "evaluation": evaluation})

                scores = evaluation.get("scores", {})
                try:
                    composite = float(scores.get("composite", 0.0))
                except Exception:
                    composite = 0.0
                composite_history.append(composite)
                feedback_a = str(safe_get(evaluation, "directive_agent_a", ""))
                feedback_b = str(safe_get(evaluation, "directive_agent_b", ""))

                # Live canvas image for this round (non-fatal if it fails).
                if self.make_images:
                    self.emit({"type": "canvas_pending", "round": rnd})
                    try:
                        img_prompt = (f"{self.prompt}. Style: {self.style or 'expressive'}. "
                                      f"{safe_get(aria, 'artistic_goal')}. "
                                      f"{safe_get(aria, 'composition_notes')}. "
                                      f"Palette: {', '.join(map(str, safe_get(aria, 'palette', [])[:6]))}. "
                                      f"Mood: {safe_get(aria, 'emotional_register')}.")
                        image = azure_generate_image(img_prompt)
                        if image:
                            self.emit({"type": "canvas", "round": rnd, "image": image})
                    except Exception as exc:
                        self.emit({"type": "warning", "message": f"Image generation failed in round {rnd}: {exc}"})

                if bool(safe_get(evaluation, "convergence_signal", False)) and composite >= 7.5:
                    converged = True
                    self.emit({"type": "converged", "round": rnd, "composite": composite})
                    break

            self.emit({
                "type": "summary",
                "outcome": "Converged" if converged else "Max rounds reached",
                "rounds": len(composite_history),
                "trend": composite_history,
                "final": composite_history[-1] if composite_history else 0.0,
                "elapsed": round(time.time() - start, 1),
            })
        except Exception as exc:
            self.emit({"type": "error", "message": str(exc)})
        finally:
            self.emit({"type": "done"})


# ---------------------------------------------------------------------------
# FastAPI app — serves the UI and streams session events (SSE)
# ---------------------------------------------------------------------------
app = FastAPI(title="CanvasMind Single-File App")


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({
        "status": "healthy",
        "model": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
        "images_enabled": bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1),
    })


@app.post("/api/start")
async def start(request: Request) -> JSONResponse:
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)
    rounds = int(body.get("rounds", 5))
    style = (body.get("style") or "").strip()
    make_images = bool(body.get("images", True))
    sess = Session(prompt, rounds, style, make_images)
    SESSIONS[sess.id] = sess
    sess.start()
    return JSONResponse({"session_id": sess.id})


@app.get("/api/stream/{session_id}")
async def stream(session_id: str) -> StreamingResponse:
    sess = SESSIONS.get(session_id)
    if not sess:
        return StreamingResponse(iter([f"data: {json.dumps({'type': 'error', 'message': 'session not found'})}\n\n"]),
                                 media_type="text/event-stream")

    import asyncio

    async def gen():
        while True:
            try:
                event = await asyncio.to_thread(sess.events.get, True, 20)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "done":
                SESSIONS.pop(session_id, None)
                break

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # disable proxy buffering so SSE streams live
    })


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


# ---------------------------------------------------------------------------
# Embedded single-page UI (vanilla JS, relative paths, SSE — proxy-safe)
# ---------------------------------------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>CanvasMind — Multi-Agent Creative AI</title>
<style>
  :root{
    --bg:#0a0a12; --bg2:#12121e; --card:#171727; --border:#262638;
    --txt:#e6e6f0; --muted:#8888a8; --aria:#22d3ee; --nexus:#d946ef;
    --judge:#f59e0b; --green:#22c55e; --red:#ef4444;
  }
  *{box-sizing:border-box;}
  body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--txt);height:100vh;overflow:hidden;display:flex;flex-direction:column;}
  header{display:flex;align-items:center;gap:16px;padding:10px 18px;background:var(--bg2);border-bottom:2px solid var(--border);flex-shrink:0;}
  header h1{font-size:18px;margin:0;font-weight:700;background:linear-gradient(90deg,var(--aria),var(--nexus));-webkit-background-clip:text;background-clip:text;color:transparent;}
  header .sub{font-size:11px;color:var(--muted);}
  header .status{margin-left:auto;font-size:12px;color:var(--muted);display:flex;gap:14px;align-items:center;}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;background:var(--muted);}
  .dot.ok{background:var(--green);} .dot.run{background:var(--judge);animation:pulse 1s infinite;}
  @keyframes pulse{50%{opacity:.3;}}
  .promptbar{display:flex;gap:10px;padding:12px 18px;background:var(--bg2);border-bottom:1px solid var(--border);flex-shrink:0;align-items:center;flex-wrap:wrap;}
  .promptbar input[type=text]{flex:1;min-width:220px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--txt);font-size:14px;}
  .promptbar input[type=number]{width:64px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:9px;color:var(--txt);}
  .promptbar label{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px;}
  button{background:linear-gradient(90deg,var(--aria),var(--nexus));color:#08080f;border:none;border-radius:8px;padding:9px 18px;font-weight:700;font-size:14px;cursor:pointer;}
  button:disabled{opacity:.5;cursor:not-allowed;}
  main{flex:1;display:grid;grid-template-columns:1fr 1.3fr 1fr;gap:10px;padding:10px;overflow:hidden;min-height:0;}
  .col{background:var(--bg2);border:1px solid var(--border);border-radius:12px;display:flex;flex-direction:column;overflow:hidden;min-height:0;}
  .col.aria{border-color:rgba(34,211,238,.35);}
  .col.nexus{border-color:rgba(217,70,239,.35);}
  .colhead{padding:10px 14px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px;display:flex;align-items:center;gap:8px;flex-shrink:0;}
  .colhead .role{font-size:11px;color:var(--muted);font-weight:400;}
  .feed{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;}
  .msg{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.45;animation:fade .25s ease;}
  @keyframes fade{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}
  .msg .tag{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.5px;padding:2px 8px;border-radius:99px;margin-bottom:6px;}
  .aria .tag{background:rgba(34,211,238,.15);color:var(--aria);}
  .nexus .tag{background:rgba(217,70,239,.15);color:var(--nexus);}
  .msg .goal{font-weight:600;margin-bottom:6px;}
  .msg .field{margin:4px 0;}
  .msg .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.4px;}
  .swatches{display:flex;gap:5px;margin:5px 0;flex-wrap:wrap;}
  .sw{width:18px;height:18px;border-radius:4px;border:1px solid #0006;}
  .next{color:var(--green);}
  .crit{color:var(--red);}
  .canvaswrap{flex:1;display:flex;align-items:center;justify-content:center;padding:14px;overflow:hidden;background:radial-gradient(circle at 50% 40%,#16162a,#0a0a12);}
  .canvaswrap img{max-width:100%;max-height:100%;border-radius:10px;box-shadow:0 8px 40px #000a;animation:fade .4s ease;}
  .canvasplaceholder{color:var(--muted);font-size:13px;text-align:center;}
  .spinner{width:34px;height:34px;border:3px solid var(--border);border-top-color:var(--aria);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 10px;}
  @keyframes spin{to{transform:rotate(360deg);}}
  .critic{flex-shrink:0;border-top:2px solid var(--border);background:var(--bg2);padding:12px 14px;max-height:46%;overflow-y:auto;}
  .critic h3{margin:0 0 8px;color:var(--judge);font-size:13px;}
  .bar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px;}
  .bar .lbl{width:170px;color:var(--muted);}
  .bar .track{flex:1;height:9px;background:var(--bg);border-radius:5px;overflow:hidden;}
  .bar .fill{height:100%;border-radius:5px;transition:width .5s ease;}
  .bar .val{width:34px;text-align:right;font-variant-numeric:tabular-nums;}
  .directive{font-size:12px;margin:5px 0;}
  .directive .who{font-weight:600;}
  .log{flex-shrink:0;height:90px;overflow-y:auto;background:#07070d;border-top:1px solid var(--border);font-family:'Consolas',monospace;font-size:11px;padding:8px 14px;color:var(--muted);}
  .log div{padding:1px 0;}
  .center{display:flex;flex-direction:column;min-height:0;}
  .converged-banner{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.4);border-radius:8px;padding:8px 12px;margin:8px 12px;font-weight:700;font-size:13px;text-align:center;}
</style>
</head>
<body>
<header>
  <div>
    <h1>CanvasMind</h1>
    <div class="sub">TCS Research — Multi-Agent Creative AI</div>
  </div>
  <div class="status">
    <span id="modelInfo"></span>
    <span><span class="dot" id="stateDot"></span><span id="stateText">idle</span></span>
  </div>
</header>

<div class="promptbar">
  <input type="text" id="prompt" placeholder="Describe the artwork for the agents to create..." value="A serene mountain lake at golden hour"/>
  <input type="text" id="style" placeholder="style hint (optional)" style="max-width:180px"/>
  <label>Rounds <input type="number" id="rounds" value="5" min="1" max="20"/></label>
  <label><input type="checkbox" id="images" checked/> Generate images</label>
  <button id="startBtn">Start Session</button>
</div>

<main>
  <div class="col aria">
    <div class="colhead" style="color:var(--aria)">● ARIA <span class="role">Creative Director</span></div>
    <div class="feed" id="ariaFeed"></div>
  </div>

  <div class="col center">
    <div class="colhead">🎨 Shared Canvas <span class="role" id="roundLabel"></span></div>
    <div id="convergedBanner"></div>
    <div class="canvaswrap" id="canvasWrap">
      <div class="canvasplaceholder">The canvas will appear here as the agents create.</div>
    </div>
    <div class="critic" id="criticPanel">
      <h3>⚖️ JUDGE — Critic Agent</h3>
      <div id="criticBody" style="color:var(--muted);font-size:12px;">Awaiting first evaluation…</div>
    </div>
  </div>

  <div class="col nexus">
    <div class="colhead" style="color:var(--nexus)">● NEXUS <span class="role">Creative Challenger</span></div>
    <div class="feed" id="nexusFeed"></div>
  </div>
</main>

<div class="log" id="log"></div>

<script>
const $ = id => document.getElementById(id);
let evtSource = null;

function log(msg){
  const d = document.createElement('div');
  const t = new Date().toLocaleTimeString();
  d.textContent = `${t}  ${msg}`;
  $('log').appendChild(d);
  $('log').scrollTop = $('log').scrollHeight;
}

function setState(text, cls){
  $('stateText').textContent = text;
  $('stateDot').className = 'dot ' + (cls||'');
}

function esc(s){ return String(s==null?'':s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function agentCard(agent, m){
  const cls = agent.toLowerCase();
  const palette = Array.isArray(m.palette) ? m.palette : [];
  const sw = palette.slice(0,8).map(c=>`<span class="sw" style="background:${esc(c)}" title="${esc(c)}"></span>`).join('');
  const conf = Math.round((parseFloat(m.confidence_score)||0)*100);
  return `<div class="msg ${cls}">
    <span class="tag">${esc(m.intent||'')} · ${conf}%</span>
    <div class="goal">${esc(m.artistic_goal)}</div>
    ${sw?`<div class="swatches">${sw}</div>`:''}
    ${m.composition_notes?`<div class="field"><span class="k">Composition</span><br>${esc(m.composition_notes)}</div>`:''}
    ${m.emotional_register?`<div class="field"><span class="k">Mood</span> ${esc(m.emotional_register)}</div>`:''}
    ${m.reasoning?`<div class="field"><span class="k">Reasoning</span><br>${esc(m.reasoning)}</div>`:''}
    ${m.critique?`<div class="field crit"><span class="k">Critique</span><br>${esc(m.critique)}</div>`:''}
    ${m.next_action?`<div class="field next"><span class="k">Next action →</span><br>${esc(m.next_action)}</div>`:''}
  </div>`;
}

function renderCritic(ev){
  const s = ev.scores||{};
  const dims = [
    ['Compositional Coherence','compositional_coherence'],
    ['Style Fidelity','style_fidelity'],
    ['Emotional Resonance','emotional_resonance'],
    ['Originality','originality'],
    ['Clarity of Next Action','clarity_of_next_action'],
    ['COMPOSITE','composite'],
  ];
  const color = v => v>=7.5?'var(--green)':(v>=5?'var(--judge)':'var(--red)');
  let html = '';
  for(const [label,key] of dims){
    const v = Math.max(0,Math.min(10, parseFloat(s[key])||0));
    html += `<div class="bar"><span class="lbl">${label}</span>
      <span class="track"><span class="fill" style="width:${v*10}%;background:${color(v)}"></span></span>
      <span class="val" style="color:${color(v)}">${v.toFixed(1)}</span></div>`;
  }
  if(ev.reasoning) html += `<div class="directive" style="margin-top:8px;color:var(--txt)">${esc(ev.reasoning)}</div>`;
  if(ev.directive_agent_a) html += `<div class="directive"><span class="who" style="color:var(--aria)">→ ARIA:</span> ${esc(ev.directive_agent_a)}</div>`;
  if(ev.directive_agent_b) html += `<div class="directive"><span class="who" style="color:var(--nexus)">→ NEXUS:</span> ${esc(ev.directive_agent_b)}</div>`;
  if(ev.recommended_next_step) html += `<div class="directive next">★ ${esc(ev.recommended_next_step)}</div>`;
  $('criticBody').innerHTML = html;
}

async function init(){
  try{
    const r = await fetch('api/health');
    const h = await r.json();
    $('modelInfo').textContent = `model: ${h.model}` + (h.images_enabled?' · images on':' · images off');
    setState('ready','ok');
  }catch(e){ setState('backend unreachable','');}
}

$('startBtn').onclick = async () => {
  const prompt = $('prompt').value.trim();
  if(!prompt){ alert('Enter a prompt first'); return; }
  // reset
  $('ariaFeed').innerHTML=''; $('nexusFeed').innerHTML='';
  $('criticBody').innerHTML='Awaiting first evaluation…';
  $('canvasWrap').innerHTML='<div class="canvasplaceholder">The canvas will appear here as the agents create.</div>';
  $('convergedBanner').innerHTML=''; $('roundLabel').textContent='';
  if(evtSource) evtSource.close();
  $('startBtn').disabled = true;
  setState('starting…','run');

  let res;
  try{
    res = await fetch('api/start', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, rounds: parseInt($('rounds').value)||5, style: $('style').value.trim(), images: $('images').checked})});
  }catch(e){ setState('failed to start','');$('startBtn').disabled=false; return; }
  const {session_id, error} = await res.json();
  if(error){ alert(error); setState('error','');$('startBtn').disabled=false; return; }

  log('Session '+session_id+' started');
  setState('running','run');
  evtSource = new EventSource('api/stream/'+session_id);

  evtSource.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    switch(ev.type){
      case 'session':
        log(`Brief: "${ev.prompt}" · up to ${ev.rounds} rounds · model ${ev.model}`);
        break;
      case 'round':
        $('roundLabel').textContent = `Round ${ev.round}`;
        log('── Round '+ev.round+' ──');
        break;
      case 'agent': {
        const feed = ev.agent==='ARIA' ? $('ariaFeed') : $('nexusFeed');
        feed.insertAdjacentHTML('beforeend', agentCard(ev.agent, ev.message));
        feed.scrollTop = feed.scrollHeight;
        log(ev.agent+' responded ('+(ev.message.intent||'')+')');
        break;
      }
      case 'critic':
        renderCritic(ev.evaluation);
        log('JUDGE scored round '+ev.evaluation.round+' · composite '+((ev.evaluation.scores||{}).composite||'?'));
        break;
      case 'canvas_pending':
        $('canvasWrap').innerHTML='<div class="canvasplaceholder"><div class="spinner"></div>Generating canvas image…</div>';
        break;
      case 'canvas':
        $('canvasWrap').innerHTML = `<img src="${ev.image}" alt="canvas round ${ev.round}"/>`;
        log('Canvas image rendered for round '+ev.round);
        break;
      case 'converged':
        $('convergedBanner').innerHTML = `<div class="converged-banner">✓ CONVERGED in round ${ev.round} · composite ${ev.composite.toFixed(1)}/10</div>`;
        log('CONVERGED · composite '+ev.composite.toFixed(1));
        break;
      case 'warning':
        log('⚠ '+ev.message);
        break;
      case 'summary':
        log(`Summary: ${ev.outcome} · ${ev.rounds} rounds · final ${ev.final.toFixed?ev.final.toFixed(1):ev.final} · ${ev.elapsed}s`);
        setState(ev.outcome,'ok');
        break;
      case 'error':
        log('ERROR: '+ev.message);
        alert('Error: '+ev.message);
        setState('error','');
        break;
      case 'done':
        evtSource.close();
        $('startBtn').disabled=false;
        break;
    }
  };
  evtSource.onerror = () => { log('stream closed'); $('startBtn').disabled=false; };
};

init();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="CanvasMind single-file full-stack app.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("BACKEND_PORT", "8000")))
    args = parser.parse_args()

    validate_config()
    print(f"  Open the app at:  http://localhost:{args.port}/")
    print(f"  Behind a proxy :  https://<host>/.../proxy/{args.port}/\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
