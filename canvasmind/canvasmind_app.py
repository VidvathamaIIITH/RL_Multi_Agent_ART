#!/usr/bin/env python3
"""
CanvasMind — Single-File Full-Stack App (Step-by-Step Collaborative Painting)
=============================================================================

EVERYTHING in one file: the backend (Azure OpenAI REST calls), the multi-agent
orchestration, live image generation (gpt-image-1), AND the complete web UI.

COLLABORATIVE PIPELINE (the heart of the app):
  - ONE shared canvas is passed back and forth between ARIA and NEXUS.
  - On each turn an agent looks at the current painting and ADDS exactly ONE NEW
    object/element on top of it (image-to-image edit that preserves everything
    already there — this is additive collaboration, NOT a full repaint/refine).
  - This happens for N back-and-forths (default 5 → 10 turns → 10 images), and
    EVERY intermediate image is displayed in a step-by-step filmstrip.
  - JUDGE does NOT edit the artwork. It only evaluates and presents the final
    accumulated canvas (the combination of both agents' contributions).

TWO WAYS TO START A BRIEF:
  - ✨ AI Surprise: the AI invents a striking brief + style on its own.
  - ✍️ Write my own: the user types their own brief.

Why one file + one port? No separate frontend → no proxy 404s, no CORS. Calls
Azure via raw REST with `max_completion_tokens` (gpt-5.2 rejects `max_tokens`)
and no custom temperature.

RUN IT:  python canvasmind_app.py --port 8000
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import random
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
# Minimal .env loader — never crashes, never overrides shell-exported values.
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
    print("  CanvasMind — Step-by-Step Collaborative Painting")
    print("=" * 64)
    print(f"  Azure Endpoint  : {AZURE_OPENAI_ENDPOINT}")
    print(f"  API Key         : ****{AZURE_OPENAI_API_KEY[-4:]}")
    print(f"  API Version     : {AZURE_OPENAI_API_VERSION}")
    print(f"  Text Deployment : {AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}")
    print(f"  Image Deployment: {AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1 or 'not set (images disabled)'}")
    print("=" * 64 + "\n")


# ---------------------------------------------------------------------------
# Azure OpenAI — chat (REST, matches the proven simulate_chat.py)
# ---------------------------------------------------------------------------
def azure_chat_completion(messages: List[Dict[str, str]],
                          max_completion_tokens: int = 1800,
                          timeout: int = 180) -> str:
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}"
           f"/chat/completions?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {"messages": messages, "max_completion_tokens": max_completion_tokens}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure chat failed HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("Azure returned an empty chat response.")
    return content.strip()


# ---------------------------------------------------------------------------
# Azure OpenAI — images.
#   generations : create the very first object on a fresh canvas
#   edits       : ADD one new object to the existing shared canvas (preserving it)
# Both return a raw base64 PNG string (or None if images are disabled).
# ---------------------------------------------------------------------------
def azure_generate_image_b64(prompt: str, size: str = "1024x1024", timeout: int = 240) -> Optional[str]:
    if not AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1:
        return None
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1}"
           f"/images/generations?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {"prompt": prompt[:3900], "size": size, "n": 1}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure image generation failed HTTP {resp.status_code}: {resp.text[:400]}")
    item = (resp.json().get("data") or [{}])[0]
    return item.get("b64_json")


def azure_edit_image_b64(prompt: str, image_b64_list: List[str],
                         size: str = "1024x1024", timeout: int = 300) -> Optional[str]:
    """Edit/extend existing image(s) (base64 PNG) with a prompt — used to ADD one object."""
    if not AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1:
        return None
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1}"
           f"/images/edits?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY}  # no Content-Type: requests sets the multipart boundary
    field = "image" if len(image_b64_list) == 1 else "image[]"
    files = [(field, (f"img{i}.png", base64.b64decode(b), "image/png"))
             for i, b in enumerate(image_b64_list)]
    data = {"prompt": prompt[:3900], "size": size, "n": "1"}
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure image edit failed HTTP {resp.status_code}: {resp.text[:400]}")
    item = (resp.json().get("data") or [{}])[0]
    return item.get("b64_json")


# ---------------------------------------------------------------------------
# JSON extraction + agent / critic prompts
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


# The agent must name the SINGLE new object it adds, and acknowledge what is
# already on the canvas — so the back-and-forth reads like a real conversation.
AGENT_JSON_SCHEMA = """
Return only valid JSON with this structure:
{
  "sender": "ARIA or NEXUS",
  "sees_on_canvas": "<what is already painted (name the other agent's last addition)>",
  "new_object": "<the SINGLE new object/element you are adding this turn>",
  "where": "<where on the canvas you place it, e.g. lower-left foreground>",
  "palette": ["#hex", "#hex"],
  "reasoning": "<why this addition complements what is already there>",
  "confidence_score": 0.0
}
"""

CRITIC_JSON_SCHEMA = """
Return only valid JSON with this structure:
{
  "scores": {
    "compositional_coherence": 0.0,
    "style_fidelity": 0.0,
    "emotional_resonance": 0.0,
    "originality": 0.0,
    "collaboration_quality": 0.0,
    "composite": 0.0
  },
  "reasoning": "<assess how well the two agents collaborated, building on each other>",
  "highlights": ["<the strongest contributions>"],
  "final_summary": "<one sentence describing the finished combined artwork>"
}
"""


def build_agent_messages(agent_name, other_name, prompt, style_hint, canvas_objects, transcript, is_first):
    if agent_name == "ARIA":
        personality = ("You are ARIA, the Creative Director. You are decisive and visual, and you "
                       "collaborate by adding bold structural elements to a shared painting.")
    else:
        personality = ("You are NEXUS, the Creative Challenger. You collaborate by adding inventive, "
                       "unexpected elements that build on and enrich what is already on the shared canvas.")

    if is_first:
        task = ("The shared canvas is BLANK. Choose ONE strong primary element to BEGIN the painting "
                "(e.g. a mountain range, a horizon line, a central figure). Put it in 'new_object'. "
                "Keep it to a single element — this is just the first object on the canvas.")
    else:
        task = (f"The shared canvas ALREADY CONTAINS: {canvas_objects}. "
                f"{other_name} just took a turn. Look at what is already painted and ADD exactly ONE "
                f"NEW, DISTINCT object/element that complements it. This is ADDITIVE collaboration — do "
                f"NOT refine, restyle, or repeat existing elements; introduce something genuinely new. "
                f"Name what you see in 'sees_on_canvas' and the single new thing in 'new_object'.")

    user_content = f"""
Shared artwork brief:
{prompt}

Style:
{style_hint or "cohesive painterly"}

Conversation so far (who added what):
{chr(10).join(transcript[-8:]) if transcript else "nothing yet"}

Your task as {agent_name}:
{task}
Be concrete and visual. {AGENT_JSON_SCHEMA}
"""
    return [{"role": "system", "content": personality},
            {"role": "user", "content": user_content}]


def build_critic_messages(prompt, style_hint, canvas_objects, transcript):
    system = ("You are JUDGE, a rigorous art critic. You do NOT edit the painting. You only assess how "
              "well ARIA and NEXUS collaborated to build one combined artwork, and summarise the result.")
    user_content = f"""
Brief:
{prompt}

Style:
{style_hint or "cohesive painterly"}

Everything the two agents added to the single shared canvas, in order:
{chr(10).join(transcript)}

The finished canvas contains: {canvas_objects}

Score strictly 0-10. Judge the COLLABORATION (did they build on each other?) as well as the art.
{CRITIC_JSON_SCHEMA}
"""
    return [{"role": "system", "content": system},
            {"role": "user", "content": user_content}]


# ---------------------------------------------------------------------------
# Eclectic seeds so each "Surprise Me" brief is different and striking.
# ---------------------------------------------------------------------------
INSPIRE_SEEDS = [
    "bioluminescent", "brutalist", "baroque", "vaporwave", "Art Nouveau", "ukiyo-e",
    "surrealist", "cyberpunk", "Afrofuturist", "deep-sea", "celestial", "folkloric",
    "post-apocalyptic", "glitch", "Renaissance", "minimalist", "dreamlike", "mythological",
    "botanical", "cosmic", "noir", "psychedelic", "steampunk", "stained-glass",
    "infrared", "papercraft", "fresco", "neon", "monsoon", "desert", "arctic", "volcanic",
]


# ---------------------------------------------------------------------------
# Session orchestration — the step-by-step collaborative painting loop
# ---------------------------------------------------------------------------
SESSIONS: Dict[str, "Session"] = {}


class Session:
    def __init__(self, prompt: str, style: str, make_images: bool, rounds: int = 5):
        self.id = uuid.uuid4().hex
        self.prompt = prompt
        self.style = style
        self.rounds = max(1, min(int(rounds), 8))   # number of back-and-forths
        self.make_images = make_images and bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1)
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def emit(self, event: Dict[str, Any]) -> None:
        self.events.put(event)

    def start(self) -> None:
        self.thread.start()

    def _agent_turn(self, agent_name, other_name, canvas_objects, transcript, is_first) -> Dict[str, Any]:
        raw = azure_chat_completion(build_agent_messages(
            agent_name, other_name, self.prompt, self.style, canvas_objects, transcript, is_first))
        try:
            data = extract_json_object(raw)
        except Exception:
            data = {"sender": agent_name, "sees_on_canvas": canvas_objects or "blank canvas",
                    "new_object": raw[:120] or "a new element", "where": "the canvas",
                    "palette": [], "reasoning": raw[:400], "confidence_score": 0.7}
        data["sender"] = agent_name
        return data

    def _run_critic(self, canvas_objects, transcript) -> Dict[str, Any]:
        raw = azure_chat_completion(build_critic_messages(self.prompt, self.style, canvas_objects, transcript))
        try:
            return extract_json_object(raw)
        except Exception:
            return {"scores": {"compositional_coherence": 7.0, "style_fidelity": 7.0,
                    "emotional_resonance": 7.0, "originality": 7.0,
                    "collaboration_quality": 7.0, "composite": 7.0},
                    "reasoning": raw[:600], "highlights": [],
                    "final_summary": "The agents collaboratively built one combined artwork."}

    def _run(self) -> None:
        start = time.time()
        transcript: List[str] = []
        added_objects: List[str] = []
        current_b64: Optional[str] = None
        turn = 0
        total_turns = self.rounds * 2

        self.emit({"type": "session", "prompt": self.prompt, "style": self.style,
                   "model": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52, "images": self.make_images,
                   "rounds": self.rounds, "total_turns": total_turns})

        order = [("ARIA", "Creative Director", "NEXUS"),
                 ("NEXUS", "Creative Challenger", "ARIA")]
        try:
            for rnd in range(1, self.rounds + 1):
                for name, role, other in order:
                    turn += 1
                    is_first = (current_b64 is None and not added_objects)
                    canvas_objects = ", ".join(added_objects) if added_objects else "blank canvas"

                    self.emit({"type": "turn", "turn": turn, "total": total_turns,
                               "agent": name, "role": role})
                    msg = self._agent_turn(name, other, canvas_objects, transcript, is_first)
                    new_object = str(safe_get(msg, "new_object", "a new element")).strip() or "a new element"

                    self.emit({"type": "agent", "agent": name, "role": role, "turn": turn,
                               "object": new_object, "message": msg})
                    transcript.append(
                        f"Turn {turn} — {name} added '{new_object}' "
                        f"({safe_get(msg, 'where', '')}). Saw: {safe_get(msg, 'sees_on_canvas', '')}.")
                    added_objects.append(new_object)

                    # ---- Image: first turn generates; later turns ADD to the shared canvas ----
                    if self.make_images:
                        self.emit({"type": "image_pending", "turn": turn, "agent": name})
                        try:
                            if is_first:
                                p = (f"A painting in {self.style or 'painterly'} style — the very BEGINNING "
                                     f"of an artwork about: {self.prompt}. The canvas currently contains ONLY "
                                     f"ONE element: {new_object}. Large areas of empty unpainted canvas, "
                                     f"minimal, just the first object blocked in.")
                                current_b64 = azure_generate_image_b64(p)
                            else:
                                p = (f"Add exactly ONE new element to this existing painting: {new_object} "
                                     f"(placed at {safe_get(msg, 'where', 'an appropriate empty area')}). "
                                     f"CRITICAL: keep everything already in the painting EXACTLY as it is — do "
                                     f"not change, restyle, refine, or repaint the existing objects, composition, "
                                     f"or colours. ONLY ADD the one new element so the painting grows step by step. "
                                     f"Theme: {self.prompt}. Style: {self.style or 'cohesive painterly'}.")
                                current_b64 = azure_edit_image_b64(p, [current_b64])
                            if current_b64:
                                self.emit({"type": "image", "turn": turn, "total": total_turns,
                                           "agent": name, "object": new_object,
                                           "label": f"{turn} · {name} added: {new_object}",
                                           "image": "data:image/png;base64," + current_b64})
                        except Exception as exc:
                            self.emit({"type": "warning",
                                       "message": f"Turn {turn} ({name}) image step failed: {exc}"})

            # ---- JUDGE: evaluates only, does NOT edit. Final = the accumulated canvas. ----
            self.emit({"type": "turn", "turn": "JUDGE", "total": total_turns,
                       "agent": "JUDGE", "role": "Critic"})
            evaluation = self._run_critic(", ".join(added_objects), transcript)
            self.emit({"type": "critic", "evaluation": evaluation})

            if self.make_images and current_b64:
                # No edit — present the final combined canvas exactly as the agents built it.
                self.emit({"type": "final", "label": "Final combined artwork (both agents)",
                           "image": "data:image/png;base64," + current_b64})

            composite = 0.0
            try:
                composite = float(evaluation.get("scores", {}).get("composite", 0.0))
            except Exception:
                composite = 0.0

            self.emit({"type": "summary", "outcome": "Completed",
                       "turns": turn, "objects": added_objects, "composite": composite,
                       "elapsed": round(time.time() - start, 1)})
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
    style = (body.get("style") or "").strip()
    rounds = int(body.get("rounds", 5))
    make_images = bool(body.get("images", True))
    sess = Session(prompt, style, make_images, rounds)
    SESSIONS[sess.id] = sess
    sess.start()
    return JSONResponse({"session_id": sess.id})


@app.get("/api/inspire")
def inspire() -> JSONResponse:
    """The AI invents a striking, unexpected art brief + style on its own."""
    s1, s2 = random.sample(INSPIRE_SEEDS, 2)
    system = ("You are a bold, imaginative art-brief generator for a painting studio. "
              "You invent striking, unexpected, vivid concepts that are a joy to paint.")
    user = (
        f"Invent ONE original, surprising, visually rich art brief and a matching artistic style. "
        f"Loosely draw on '{s1}' and '{s2}', but feel free to go somewhere completely unexpected. "
        f"Be specific and evocative about subject, setting, mood, and light. Keep the brief to 1-2 sentences.\n\n"
        f'Return ONLY JSON: {{"prompt": "<the brief>", "style": "<a short style descriptor>"}}')
    try:
        raw = azure_chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_completion_tokens=400)
        data = extract_json_object(raw)
        prompt = str(data.get("prompt", "")).strip()
        style = str(data.get("style", "")).strip()
        if not prompt:
            raise ValueError("empty brief")
        return JSONResponse({"prompt": prompt, "style": style})
    except Exception as exc:
        return JSONResponse({"error": f"Could not invent a brief: {exc}"}, status_code=500)


@app.get("/api/stream/{session_id}")
async def stream(session_id: str) -> StreamingResponse:
    sess = SESSIONS.get(session_id)
    if not sess:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'session not found'})}\n\n"]),
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
        "X-Accel-Buffering": "no",
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
<title>CanvasMind — Collaborative Multi-Agent Painting</title>
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
  .promptbar input[type=text]{flex:1;min-width:200px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--txt);font-size:14px;}
  .promptbar input[type=number]{width:60px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:9px;color:var(--txt);}
  .promptbar label{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px;}
  button{background:linear-gradient(90deg,var(--aria),var(--nexus));color:#08080f;border:none;border-radius:8px;padding:9px 18px;font-weight:700;font-size:14px;cursor:pointer;}
  button.ghost{background:transparent;border:1px solid var(--border);color:var(--txt);}
  button:disabled{opacity:.4;cursor:not-allowed;}
  .modes{display:flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;}
  .mode{background:transparent;color:var(--muted);border:none;border-radius:0;padding:8px 14px;font-weight:600;font-size:13px;}
  .mode.active{background:linear-gradient(90deg,var(--aria),var(--nexus));color:#08080f;}
  .panel{display:flex;gap:10px;align-items:center;flex:1;flex-wrap:wrap;}
  .panel.hidden,.brief.hidden{display:none;}
  .brief{flex:1;min-width:200px;background:var(--card);border:1px solid var(--judge);border-radius:8px;padding:8px 12px;font-size:13px;animation:fade .25s ease;}
  .brief .bk{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--judge);font-weight:700;margin-right:5px;}
  .brief .bk2{color:var(--nexus);margin-left:10px;}
  main{flex:1;display:grid;grid-template-columns:1fr 1.7fr 1fr;gap:10px;padding:10px;overflow:hidden;min-height:0;}
  .col{background:var(--bg2);border:1px solid var(--border);border-radius:12px;display:flex;flex-direction:column;overflow:hidden;min-height:0;}
  .col.aria{border-color:rgba(34,211,238,.35);} .col.nexus{border-color:rgba(217,70,239,.35);}
  .colhead{padding:10px 14px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px;display:flex;align-items:center;gap:8px;flex-shrink:0;}
  .colhead .role{font-size:11px;color:var(--muted);font-weight:400;}
  .feed{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;}
  .msg{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.45;animation:fade .25s ease;}
  @keyframes fade{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}
  .msg .tag{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.5px;padding:2px 8px;border-radius:99px;margin-bottom:6px;}
  .aria .tag{background:rgba(34,211,238,.15);color:var(--aria);}
  .nexus .tag{background:rgba(217,70,239,.15);color:var(--nexus);}
  .msg .adds{font-weight:700;margin-bottom:4px;}
  .msg .field{margin:4px 0;} .msg .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.4px;}
  .swatches{display:flex;gap:5px;margin:5px 0;flex-wrap:wrap;} .sw{width:16px;height:16px;border-radius:4px;border:1px solid #0006;}
  .center{display:flex;flex-direction:column;min-height:0;}
  .current{flex:1;display:flex;align-items:center;justify-content:center;padding:10px;overflow:hidden;background:radial-gradient(circle at 50% 40%,#16162a,#0a0a12);position:relative;}
  .current img{max-width:100%;max-height:100%;border-radius:10px;box-shadow:0 8px 40px #000a;animation:fade .35s ease;}
  .current .ph{color:var(--muted);font-size:13px;text-align:center;}
  .current .finalbadge{position:absolute;top:12px;right:14px;background:var(--green);color:#06140b;font-weight:800;font-size:11px;padding:4px 10px;border-radius:99px;letter-spacing:.5px;display:none;}
  .spinner{width:34px;height:34px;border:3px solid var(--border);border-top-color:var(--aria);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 8px;}
  @keyframes spin{to{transform:rotate(360deg);}}
  /* step-by-step filmstrip */
  .strip{flex-shrink:0;height:132px;display:flex;gap:8px;overflow-x:auto;overflow-y:hidden;padding:8px 10px;border-top:1px solid var(--border);background:var(--bg);}
  .frame{flex:0 0 auto;width:150px;display:flex;flex-direction:column;gap:4px;animation:fade .3s ease;}
  .frame img{width:150px;height:88px;object-fit:cover;border-radius:6px;border:1px solid var(--border);}
  .frame.aria img{border-color:var(--aria);} .frame.nexus img{border-color:var(--nexus);}
  .frame .cap{font-size:10px;color:var(--muted);line-height:1.2;}
  .frame .cap b{color:var(--txt);}
  .critic{flex-shrink:0;border-top:2px solid var(--border);background:var(--bg2);padding:10px 14px;max-height:30%;overflow-y:auto;}
  .critic h3{margin:0 0 8px;color:var(--judge);font-size:13px;}
  .bar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px;}
  .bar .lbl{width:175px;color:var(--muted);}
  .bar .track{flex:1;height:9px;background:var(--bg);border-radius:5px;overflow:hidden;}
  .bar .fill{height:100%;border-radius:5px;transition:width .5s ease;}
  .bar .val{width:34px;text-align:right;}
  .directive{font-size:12px;margin:5px 0;}
  .log{flex-shrink:0;height:80px;overflow-y:auto;background:#07070d;border-top:1px solid var(--border);font-family:'Consolas',monospace;font-size:11px;padding:8px 14px;color:var(--muted);}
  .log div{padding:1px 0;}
</style>
</head>
<body>
<header>
  <div>
    <h1>CanvasMind</h1>
    <div class="sub">TCS Research — Collaborative Multi-Agent Painting (step by step)</div>
  </div>
  <div class="status">
    <span id="modelInfo"></span>
    <span><span class="dot" id="stateDot"></span><span id="stateText">idle</span></span>
  </div>
</header>

<div class="promptbar">
  <div class="modes">
    <button id="modeAi" class="mode active" title="Let the AI invent a striking brief">✨ AI Surprise</button>
    <button id="modeManual" class="mode" title="Write your own prompt">✍️ Write my own</button>
  </div>

  <div id="aiPanel" class="panel">
    <button id="surpriseBtn">✨ Surprise Me — invent a brief &amp; create</button>
    <div id="briefCard" class="brief hidden"></div>
  </div>

  <div id="manualPanel" class="panel hidden">
    <input type="text" id="prompt" placeholder="Describe the artwork for the agents to paint together..." value="A serene mountain lake at golden hour"/>
    <input type="text" id="style" placeholder="style hint (optional)" style="max-width:170px"/>
    <button id="startBtn">Start Co-Creation</button>
  </div>

  <label title="How many back-and-forth exchanges (each = 1 ARIA turn + 1 NEXUS turn = 2 images)">
    Back-and-forths <input type="number" id="rounds" value="5" min="3" max="8"/>
  </label>
  <button id="downloadBtn" class="ghost" disabled>⬇ Download all steps</button>
</div>

<main>
  <div class="col aria">
    <div class="colhead" style="color:var(--aria)">● ARIA <span class="role">Creative Director — adds bold elements</span></div>
    <div class="feed" id="ariaFeed"></div>
  </div>

  <div class="col center">
    <div class="colhead">🎨 Shared Canvas <span class="role" id="turnLabel"></span></div>
    <div class="current" id="currentWrap">
      <span class="finalbadge" id="finalBadge">✓ FINAL</span>
      <div class="ph">The shared canvas evolves here — one new object per turn.</div>
    </div>
    <div class="strip" id="strip"></div>
    <div class="critic" id="criticPanel">
      <h3>⚖️ JUDGE — Critic (presents the combined result, no edits)</h3>
      <div id="criticBody" style="color:var(--muted);font-size:12px;">Awaiting the finished collaboration…</div>
    </div>
  </div>

  <div class="col nexus">
    <div class="colhead" style="color:var(--nexus)">● NEXUS <span class="role">Creative Challenger — adds new objects</span></div>
    <div class="feed" id="nexusFeed"></div>
  </div>
</main>

<div class="log" id="log"></div>

<script>
const $ = id => document.getElementById(id);
let evtSource = null;
let frames = [];          // {turn, agent, object, dataurl}

function log(msg){
  const d = document.createElement('div');
  d.textContent = `${new Date().toLocaleTimeString()}  ${msg}`;
  $('log').appendChild(d); $('log').scrollTop = $('log').scrollHeight;
}
function setState(text, cls){ $('stateText').textContent = text; $('stateDot').className = 'dot ' + (cls||''); }
function esc(s){ return String(s==null?'':s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function agentCard(agent, m, turn){
  const cls = agent.toLowerCase();
  const palette = Array.isArray(m.palette) ? m.palette : [];
  const sw = palette.slice(0,8).map(c=>`<span class="sw" style="background:${esc(c)}" title="${esc(c)}"></span>`).join('');
  return `<div class="msg ${cls}">
    <span class="tag">turn ${turn} · adds 1 object</span>
    <div class="adds">＋ ${esc(m.new_object)}</div>
    ${m.where?`<div class="field"><span class="k">Placed</span> ${esc(m.where)}</div>`:''}
    ${m.sees_on_canvas?`<div class="field"><span class="k">Sees on canvas</span><br>${esc(m.sees_on_canvas)}</div>`:''}
    ${sw?`<div class="swatches">${sw}</div>`:''}
    ${m.reasoning?`<div class="field"><span class="k">Why</span><br>${esc(m.reasoning)}</div>`:''}
  </div>`;
}

function renderCritic(ev){
  const s = ev.scores||{};
  const dims = [
    ['Compositional Coherence','compositional_coherence'],['Style Fidelity','style_fidelity'],
    ['Emotional Resonance','emotional_resonance'],['Originality','originality'],
    ['Collaboration Quality','collaboration_quality'],['COMPOSITE','composite']];
  const color = v => v>=7.5?'var(--green)':(v>=5?'var(--judge)':'var(--red)');
  let html = '';
  for(const [label,key] of dims){
    const v = Math.max(0,Math.min(10, parseFloat(s[key])||0));
    html += `<div class="bar"><span class="lbl">${label}</span>
      <span class="track"><span class="fill" style="width:${v*10}%;background:${color(v)}"></span></span>
      <span class="val" style="color:${color(v)}">${v.toFixed(1)}</span></div>`;
  }
  if(ev.reasoning) html += `<div class="directive" style="margin-top:8px;color:var(--txt)">${esc(ev.reasoning)}</div>`;
  if(ev.final_summary) html += `<div class="directive" style="color:var(--green)">★ ${esc(ev.final_summary)}</div>`;
  $('criticBody').innerHTML = html;
}

async function init(){
  try{
    const h = await (await fetch('api/health')).json();
    $('modelInfo').textContent = `model: ${h.model}` + (h.images_enabled?' · images on':' · images OFF');
    setState('ready','ok');
  }catch(e){ setState('backend unreachable',''); }
}

function downloadAll(){
  let delay = 0;
  frames.forEach((f, i) => {
    setTimeout(()=>{
      const a = document.createElement('a');
      a.href = f.dataurl;
      const n = String(i+1).padStart(2,'0');
      a.download = `canvasmind_step${n}_${f.agent}_${(f.object||'').replace(/[^a-z0-9]+/gi,'_').slice(0,24)}.png`;
      document.body.appendChild(a); a.click(); a.remove();
    }, delay);
    delay += 350;
  });
  log('Downloading '+frames.length+' step image(s)…');
}
$('downloadBtn').onclick = downloadAll;

function showMode(mode){
  const ai = (mode === 'ai');
  $('aiPanel').classList.toggle('hidden', !ai);
  $('manualPanel').classList.toggle('hidden', ai);
  $('modeAi').classList.toggle('active', ai);
  $('modeManual').classList.toggle('active', !ai);
}
$('modeAi').onclick = () => showMode('ai');
$('modeManual').onclick = () => showMode('manual');

function setBusy(b){ $('startBtn').disabled=b; $('surpriseBtn').disabled=b; }

async function startSession(prompt, style){
  if(!prompt){ alert('Enter (or generate) a prompt first'); return; }
  $('ariaFeed').innerHTML=''; $('nexusFeed').innerHTML='';
  $('strip').innerHTML=''; frames=[];
  $('criticBody').innerHTML='Awaiting the finished collaboration…'; $('turnLabel').textContent='';
  $('finalBadge').style.display='none'; $('downloadBtn').disabled=true;
  $('currentWrap').querySelector('.ph')?.remove();
  $('currentWrap').innerHTML='<span class="finalbadge" id="finalBadge">✓ FINAL</span><div class="ph">Starting…</div>';
  if(evtSource) evtSource.close();
  setBusy(true); setState('starting…','run');

  let res;
  try{
    res = await fetch('api/start', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, style: style||'', rounds: parseInt($('rounds').value)||5, images:true})});
  }catch(e){ setState('failed to start',''); setBusy(false); return; }
  const {session_id, error} = await res.json();
  if(error){ alert(error); setState('error',''); setBusy(false); return; }

  log('Session '+session_id+' started'); setState('running','run');
  evtSource = new EventSource('api/stream/'+session_id);

  evtSource.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    switch(ev.type){
      case 'session':
        log(`Brief: "${ev.prompt}" · ${ev.rounds} back-and-forths → ${ev.total_turns} images · model ${ev.model}`
            + (ev.images?'':' · IMAGES DISABLED')); break;
      case 'turn':
        $('turnLabel').textContent = (ev.agent==='JUDGE')
          ? 'JUDGE combining…'
          : `Turn ${ev.turn}/${ev.total} · ${ev.agent} adding an object`;
        break;
      case 'agent': {
        const feed = ev.agent==='ARIA' ? $('ariaFeed') : $('nexusFeed');
        feed.insertAdjacentHTML('beforeend', agentCard(ev.agent, ev.message, ev.turn));
        feed.scrollTop = feed.scrollHeight;
        log(`Turn ${ev.turn}: ${ev.agent} adds “${ev.object}”`); break;
      }
      case 'image_pending':
        $('currentWrap').querySelector('.ph')?.remove();
        $('currentWrap').insertAdjacentHTML('beforeend','<div class="ph phgen"><div class="spinner"></div>'+ev.agent+' is painting…</div>');
        break;
      case 'image': {
        document.querySelectorAll('.phgen').forEach(n=>n.remove());
        // big current view = latest
        const badge = '<span class="finalbadge" id="finalBadge">✓ FINAL</span>';
        $('currentWrap').innerHTML = badge + `<img src="${ev.image}" alt="${esc(ev.label)}"/>`;
        // append to filmstrip
        frames.push({turn:ev.turn, agent:ev.agent, object:ev.object, dataurl:ev.image});
        const cls = ev.agent.toLowerCase();
        $('strip').insertAdjacentHTML('beforeend',
          `<div class="frame ${cls}"><img src="${ev.image}"/><div class="cap"><b>${ev.turn} · ${esc(ev.agent)}</b><br>＋ ${esc(ev.object)}</div></div>`);
        $('strip').scrollLeft = $('strip').scrollWidth;
        $('downloadBtn').disabled = false;
        log(`  ↳ image ${frames.length} shown (${ev.agent} added “${ev.object}”)`); break;
      }
      case 'critic': renderCritic(ev.evaluation); log('JUDGE assessed the collaboration'); break;
      case 'final':
        document.querySelectorAll('.phgen').forEach(n=>n.remove());
        $('currentWrap').innerHTML = '<span class="finalbadge" style="display:block">✓ FINAL</span>' + `<img src="${ev.image}" alt="final"/>`;
        log('Final combined artwork ready'); break;
      case 'warning': log('⚠ '+ev.message); break;
      case 'summary':
        log(`Done: ${ev.turns} turns · ${ev.objects.length} objects · composite ${ev.composite?ev.composite.toFixed(1):'-'} · ${ev.elapsed}s`);
        setState('completed','ok'); break;
      case 'error': log('ERROR: '+ev.message); alert('Error: '+ev.message); setState('error',''); break;
      case 'done': evtSource.close(); setBusy(false); break;
    }
  };
  evtSource.onerror = () => { log('stream closed'); setBusy(false); };
}

$('startBtn').onclick = () => startSession($('prompt').value.trim(), $('style').value.trim());

$('surpriseBtn').onclick = async () => {
  setBusy(true); setState('inventing a brief…','run');
  $('briefCard').classList.add('hidden');
  try{
    const data = await (await fetch('api/inspire')).json();
    if(data.error) throw new Error(data.error);
    $('prompt').value = data.prompt || '';
    $('style').value = data.style || '';
    $('briefCard').innerHTML =
      `<span class="bk">AI brief</span>${esc(data.prompt)}` +
      (data.style ? `<span class="bk bk2">style</span>${esc(data.style)}` : '');
    $('briefCard').classList.remove('hidden');
    log('✨ AI invented a brief: '+data.prompt + (data.style?(' · style: '+data.style):''));
    await startSession(data.prompt, data.style || '');
  }catch(e){
    setBusy(false); setState('error','');
    log('Surprise failed: '+e.message); alert('Could not invent a brief: '+e.message);
  }
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
