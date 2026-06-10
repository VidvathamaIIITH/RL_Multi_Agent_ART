#!/usr/bin/env python3
"""
CanvasMind — Single-File Full-Stack Application (3-Image Co-Creation)
====================================================================

EVERYTHING in one file: the backend (Azure OpenAI REST calls), the multi-agent
orchestration (ARIA + NEXUS + JUDGE), live image generation (gpt-image-1), AND
the complete web UI (served from the same port).

CO-CREATION IMAGE PIPELINE (this is the heart of the app):
  1. ARIA  decides a direction and generates a PARTIAL painting (image #1).
  2. NEXUS  is shown ARIA's partial image, decides what to add, and generates a
     new painting that BUILDS ON image #1  ->  image #2 (image-to-image edit).
  3. JUDGE  is given BOTH images, reasons further, and COMBINES them into a
     single finished artwork  ->  image #3 (multi-image edit).
All three images are displayed, and a "Download all 3 images" button saves them.

Why one file + one port?
  - No separate Vite frontend, so NO reverse-proxy 404s, NO CORS, NO WebSocket
    handshake problems. The browser streams events from the SAME origin via SSE.
  - Calls Azure exactly like the proven simulate_chat.py: raw REST with
    `max_completion_tokens` (gpt-5.2 rejects `max_tokens`) and no temperature.

RUN IT (one command):
    python canvasmind_app.py --port 8000

Then open:
    Local : http://localhost:8000/
    Proxy : https://<host>/dev-workspaces/<workspace>/proxy/8000/
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    print("  CanvasMind — Single-File App (3-Image Co-Creation)")
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
# Azure OpenAI — images. Two modes:
#   generations : create a brand-new image from a text prompt (ARIA, image #1)
#   edits       : transform/combine EXISTING image(s) with a prompt
#                 (NEXUS builds on #1 -> #2 ; JUDGE combines #1+#2 -> #3)
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
    """Edit/compose one or more existing images (passed as base64 PNG) with a prompt."""
    if not AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1:
        return None
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1}"
           f"/images/edits?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY}  # no Content-Type: requests sets the multipart boundary
    # Single image -> field name "image"; multiple -> "image[]" (mirrors the OpenAI SDK).
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


def build_agent_messages(agent_name, prompt, style_hint, transcript, canvas_description, extra_task):
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

Current canvas description:
{canvas_description}

Conversation so far:
{chr(10).join(transcript[-8:]) if transcript else "none yet"}

Task:
As {agent_name}, produce the next structured contribution to the artwork.
{extra_task}
Be concrete, visual, and useful. Do not be generic.

{AGENT_JSON_SCHEMA}
"""
    return [{"role": "system", "content": personality},
            {"role": "user", "content": user_content}]


def build_critic_messages(prompt, style_hint, transcript, canvas_description):
    system = ("You are JUDGE, a rigorous visual-art critic and final compositor. You evaluate ARIA "
              "and NEXUS, then decide how to merge their two paintings into one finished artwork.")
    user_content = f"""
Creative brief:
{prompt}

Style hint:
{style_hint or "none"}

Current canvas description:
{canvas_description}

Conversation to evaluate (ARIA's partial painting, then NEXUS's additions):
{chr(10).join(transcript[-10:])}

Instructions:
Score strictly from 0 to 10. In "recommended_next_step", describe specifically how the two
paintings should be combined into one unified, finished artwork (composition, palette, lighting).
Set convergence_signal to true if the combined direction is coherent and composite >= 7.5.

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
# Session orchestration — the 3-image co-creation pipeline (background thread)
# ---------------------------------------------------------------------------
SESSIONS: Dict[str, "Session"] = {}


class Session:
    def __init__(self, prompt: str, style: str, make_images: bool):
        self.id = uuid.uuid4().hex
        self.prompt = prompt
        self.style = style
        self.make_images = make_images and bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1)
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def emit(self, event: Dict[str, Any]) -> None:
        self.events.put(event)

    def start(self) -> None:
        self.thread.start()

    # -- text agents -------------------------------------------------------
    def _run_agent(self, agent_name, prompt, style, transcript, canvas_desc, extra_task) -> Dict[str, Any]:
        raw = azure_chat_completion(build_agent_messages(
            agent_name, prompt, style, transcript, canvas_desc, extra_task))
        try:
            data = extract_json_object(raw)
        except Exception:
            data = {
                "sender": agent_name,
                "intent": "propose" if agent_name == "ARIA" else "critique",
                "confidence_score": 0.7, "artistic_goal": raw[:700], "palette": [],
                "region": "whole canvas",
                "composition_notes": "Model returned unstructured text; using as proposal.",
                "emotional_register": "evocative", "reasoning": raw[:900],
                "critique": "", "next_action": "Continue developing the artwork.",
            }
        data["sender"] = agent_name
        return data

    def _run_critic(self, prompt, style, transcript, canvas_desc) -> Dict[str, Any]:
        raw = azure_chat_completion(build_critic_messages(prompt, style, transcript, canvas_desc))
        try:
            data = extract_json_object(raw)
        except Exception:
            data = {
                "round": 1,
                "scores": {"compositional_coherence": 6.0, "style_fidelity": 6.0,
                           "emotional_resonance": 6.0, "originality": 6.0,
                           "clarity_of_next_action": 6.0, "composite": 6.0},
                "reasoning": raw[:900], "contradictions_detected": [],
                "weak_ideas": ["Critic returned unstructured text."],
                "directive_agent_a": "Clarify composition.", "directive_agent_b": "Add specificity.",
                "recommended_next_step": "Merge both paintings into one unified, finished artwork.",
                "convergence_signal": False,
            }
        data["round"] = 1
        return data

    # -- image helpers -----------------------------------------------------
    def _emit_image(self, stage: str, label: str, b64: str) -> None:
        self.emit({"type": "image", "stage": stage, "label": label,
                   "image": "data:image/png;base64," + b64})

    def _palette_str(self, msg: Dict[str, Any]) -> str:
        pal = safe_get(msg, "palette", [])
        return ", ".join(map(str, pal[:6])) if isinstance(pal, list) else ""

    # -- main pipeline -----------------------------------------------------
    def _run(self) -> None:
        start = time.time()
        transcript: List[str] = [f"USER BRIEF: {self.prompt}"]
        style = self.style
        img_aria_b64: Optional[str] = None
        img_nexus_b64: Optional[str] = None
        composite = 0.0
        converged = False

        self.emit({"type": "session", "prompt": self.prompt, "style": style,
                   "model": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52, "images": self.make_images})
        try:
            # ============================ STAGE 1 · ARIA ============================
            self.emit({"type": "stage", "stage": "aria", "label": "ARIA — partial painting"})
            aria = self._run_agent(
                "ARIA", self.prompt, style, transcript,
                "Blank canvas. No operations yet.",
                "Define the core vision and the FIRST layer only — this will be a PARTIAL, "
                "unfinished underpainting that NEXUS will build on. Leave room for additions.")
            self.emit({"type": "agent", "agent": "ARIA", "role": "Creative Director", "message": aria})
            transcript.append(readable_agent_message(aria))
            canvas_desc = (f"ARIA's partial underpainting: {safe_get(aria, 'artistic_goal')}. "
                           f"{safe_get(aria, 'composition_notes')} "
                           f"Mood: {safe_get(aria, 'emotional_register')}.")

            if self.make_images:
                self.emit({"type": "image_pending", "stage": "aria"})
                try:
                    aria_prompt = (
                        f"{self.prompt}. Style: {style or 'expressive painterly'}. "
                        f"{safe_get(aria, 'artistic_goal')}. {safe_get(aria, 'composition_notes')}. "
                        f"Palette: {self._palette_str(aria)}. Mood: {safe_get(aria, 'emotional_register')}. "
                        f"IMPORTANT: render this as a PARTIALLY COMPLETED painting — an early "
                        f"underpainting with blocked-in shapes and loose unfinished areas, deliberately "
                        f"leaving empty space and room for more elements to be added later.")
                    img_aria_b64 = azure_generate_image_b64(aria_prompt)
                    if img_aria_b64:
                        self._emit_image("aria", "1 · ARIA — partial painting", img_aria_b64)
                except Exception as exc:
                    self.emit({"type": "warning", "message": f"ARIA image failed: {exc}"})

            # ============================ STAGE 2 · NEXUS ===========================
            self.emit({"type": "stage", "stage": "nexus", "label": "NEXUS — builds on ARIA"})
            nexus = self._run_agent(
                "NEXUS", self.prompt, style, transcript,
                canvas_desc + " (You are shown ARIA's partial painting and must extend it.)",
                "ARIA has produced a PARTIAL painting. Decide what to ADD next to develop it further "
                "without discarding what exists — new elements, depth, contrast, or detail.")
            self.emit({"type": "agent", "agent": "NEXUS", "role": "Creative Challenger", "message": nexus})
            transcript.append(readable_agent_message(nexus))

            if self.make_images and img_aria_b64:
                self.emit({"type": "image_pending", "stage": "nexus"})
                edit_prompt = (
                    f"Continue and build upon this partially completed painting. Theme: {self.prompt}. "
                    f"Keep the existing composition and palette, and ADD: {safe_get(nexus, 'artistic_goal')}. "
                    f"{safe_get(nexus, 'next_action')} {safe_get(nexus, 'composition_notes')}. "
                    f"Style: {style or 'cohesive painterly'}. Develop it further but keep it harmonious.")
                try:
                    img_nexus_b64 = azure_edit_image_b64(edit_prompt, [img_aria_b64])
                except Exception as exc:
                    self.emit({"type": "warning", "message": f"NEXUS image-edit failed, falling back: {exc}"})
                    try:
                        img_nexus_b64 = azure_generate_image_b64(
                            f"{self.prompt}. Style: {style}. Building on ARIA's underpainting. "
                            f"Add: {safe_get(nexus, 'artistic_goal')}. {safe_get(nexus, 'composition_notes')}.")
                    except Exception as exc2:
                        self.emit({"type": "warning", "message": f"NEXUS fallback image failed: {exc2}"})
                if img_nexus_b64:
                    self._emit_image("nexus", "2 · NEXUS — builds on ARIA", img_nexus_b64)

            # ============================ STAGE 3 · JUDGE ===========================
            self.emit({"type": "stage", "stage": "judge", "label": "JUDGE — final combined artwork"})
            evaluation = self._run_critic(self.prompt, style, transcript, canvas_desc)
            self.emit({"type": "critic", "evaluation": evaluation})
            try:
                composite = float(evaluation.get("scores", {}).get("composite", 0.0))
            except Exception:
                composite = 0.0
            converged = bool(safe_get(evaluation, "convergence_signal", False)) and composite >= 7.5

            if self.make_images and img_aria_b64 and img_nexus_b64:
                self.emit({"type": "image_pending", "stage": "judge"})
                combine_prompt = (
                    f"Combine and harmonize the TWO provided paintings into a SINGLE finished, unified "
                    f"artwork. Theme: {self.prompt}. Style: {style or 'cohesive painterly'}. "
                    f"{safe_get(evaluation, 'recommended_next_step')}. Resolve contradictions, balance the "
                    f"composition, unify palette and lighting, and complete all unfinished areas into a "
                    f"polished final piece.")
                try:
                    img_judge_b64 = azure_edit_image_b64(combine_prompt, [img_aria_b64, img_nexus_b64])
                except Exception as exc:
                    self.emit({"type": "warning", "message": f"JUDGE combine-edit failed, falling back: {exc}"})
                    try:
                        img_judge_b64 = azure_generate_image_b64(
                            f"A single finished, unified artwork combining the prior directions. "
                            f"{self.prompt}. Style: {style}. {safe_get(evaluation, 'recommended_next_step')}.")
                    except Exception as exc2:
                        img_judge_b64 = None
                        self.emit({"type": "warning", "message": f"JUDGE fallback image failed: {exc2}"})
                if img_judge_b64:
                    self._emit_image("judge", "3 · JUDGE — final combined artwork", img_judge_b64)

            self.emit({
                "type": "summary",
                "outcome": "Converged" if converged else "Completed",
                "composite": composite,
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
    style = (body.get("style") or "").strip()
    make_images = bool(body.get("images", True))
    sess = Session(prompt, style, make_images)
    SESSIONS[sess.id] = sess
    sess.start()
    return JSONResponse({"session_id": sess.id})


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
  button{background:linear-gradient(90deg,var(--aria),var(--nexus));color:#08080f;border:none;border-radius:8px;padding:9px 18px;font-weight:700;font-size:14px;cursor:pointer;}
  button.ghost{background:transparent;border:1px solid var(--border);color:var(--txt);}
  button:disabled{opacity:.4;cursor:not-allowed;}
  main{flex:1;display:grid;grid-template-columns:1fr 1.5fr 1fr;gap:10px;padding:10px;overflow:hidden;min-height:0;}
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
  .next{color:var(--green);} .crit{color:var(--red);}
  .center{display:flex;flex-direction:column;min-height:0;}
  .gallery{flex:1;display:grid;grid-template-rows:1fr 1fr 1fr;gap:8px;padding:10px;overflow-y:auto;}
  .slot{position:relative;background:radial-gradient(circle at 50% 40%,#16162a,#0a0a12);border:1px solid var(--border);border-radius:10px;display:flex;align-items:center;justify-content:center;overflow:hidden;min-height:120px;}
  .slot.aria{border-color:rgba(34,211,238,.4);}
  .slot.nexus{border-color:rgba(217,70,239,.4);}
  .slot.judge{border-color:rgba(245,158,11,.5);}
  .slot img{max-width:100%;max-height:100%;border-radius:8px;animation:fade .4s ease;}
  .slot .label{position:absolute;top:6px;left:8px;font-size:11px;font-weight:700;background:#0009;padding:3px 8px;border-radius:6px;}
  .slot.aria .label{color:var(--aria);} .slot.nexus .label{color:var(--nexus);} .slot.judge .label{color:var(--judge);}
  .ph{color:var(--muted);font-size:12px;text-align:center;padding:0 10px;}
  .spinner{width:30px;height:30px;border:3px solid var(--border);border-top-color:var(--aria);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 8px;}
  @keyframes spin{to{transform:rotate(360deg);}}
  .critic{flex-shrink:0;border-top:2px solid var(--border);background:var(--bg2);padding:10px 14px;max-height:34%;overflow-y:auto;}
  .critic h3{margin:0 0 8px;color:var(--judge);font-size:13px;}
  .bar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px;}
  .bar .lbl{width:170px;color:var(--muted);}
  .bar .track{flex:1;height:9px;background:var(--bg);border-radius:5px;overflow:hidden;}
  .bar .fill{height:100%;border-radius:5px;transition:width .5s ease;}
  .bar .val{width:34px;text-align:right;font-variant-numeric:tabular-nums;}
  .directive{font-size:12px;margin:5px 0;} .directive .who{font-weight:600;}
  .log{flex-shrink:0;height:84px;overflow-y:auto;background:#07070d;border-top:1px solid var(--border);font-family:'Consolas',monospace;font-size:11px;padding:8px 14px;color:var(--muted);}
  .log div{padding:1px 0;}
</style>
</head>
<body>
<header>
  <div>
    <h1>CanvasMind</h1>
    <div class="sub">TCS Research — Multi-Agent Creative AI · 3-image co-creation</div>
  </div>
  <div class="status">
    <span id="modelInfo"></span>
    <span><span class="dot" id="stateDot"></span><span id="stateText">idle</span></span>
  </div>
</header>

<div class="promptbar">
  <input type="text" id="prompt" placeholder="Describe the artwork for the agents to create..." value="A serene mountain lake at golden hour"/>
  <input type="text" id="style" placeholder="style hint (optional)" style="max-width:180px"/>
  <button id="startBtn">Start Co-Creation</button>
  <button id="downloadBtn" class="ghost" disabled>⬇ Download all 3 images</button>
</div>

<main>
  <div class="col aria">
    <div class="colhead" style="color:var(--aria)">● ARIA <span class="role">Creative Director — paints the first partial layer</span></div>
    <div class="feed" id="ariaFeed"></div>
  </div>

  <div class="col center">
    <div class="colhead">🎨 Three-Stage Canvas <span class="role" id="stageLabel"></span></div>
    <div class="gallery">
      <div class="slot aria" id="slotAria"><span class="label">1 · ARIA — partial</span><div class="ph">ARIA's partial painting will appear here.</div></div>
      <div class="slot nexus" id="slotNexus"><span class="label">2 · NEXUS — builds on ARIA</span><div class="ph">NEXUS extends ARIA's image here.</div></div>
      <div class="slot judge" id="slotJudge"><span class="label">3 · JUDGE — final combined</span><div class="ph">JUDGE merges both into the final artwork here.</div></div>
    </div>
    <div class="critic" id="criticPanel">
      <h3>⚖️ JUDGE — Critic & Compositor</h3>
      <div id="criticBody" style="color:var(--muted);font-size:12px;">Awaiting evaluation…</div>
    </div>
  </div>

  <div class="col nexus">
    <div class="colhead" style="color:var(--nexus)">● NEXUS <span class="role">Creative Challenger — adds to the painting</span></div>
    <div class="feed" id="nexusFeed"></div>
  </div>
</main>

<div class="log" id="log"></div>

<script>
const $ = id => document.getElementById(id);
let evtSource = null;
const images = { aria:null, nexus:null, judge:null };

function log(msg){
  const d = document.createElement('div');
  d.textContent = `${new Date().toLocaleTimeString()}  ${msg}`;
  $('log').appendChild(d); $('log').scrollTop = $('log').scrollHeight;
}
function setState(text, cls){ $('stateText').textContent = text; $('stateDot').className = 'dot ' + (cls||''); }
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
    ['Compositional Coherence','compositional_coherence'],['Style Fidelity','style_fidelity'],
    ['Emotional Resonance','emotional_resonance'],['Originality','originality'],
    ['Clarity of Next Action','clarity_of_next_action'],['COMPOSITE','composite']];
  const color = v => v>=7.5?'var(--green)':(v>=5?'var(--judge)':'var(--red)');
  let html = '';
  for(const [label,key] of dims){
    const v = Math.max(0,Math.min(10, parseFloat(s[key])||0));
    html += `<div class="bar"><span class="lbl">${label}</span>
      <span class="track"><span class="fill" style="width:${v*10}%;background:${color(v)}"></span></span>
      <span class="val" style="color:${color(v)}">${v.toFixed(1)}</span></div>`;
  }
  if(ev.reasoning) html += `<div class="directive" style="margin-top:8px;color:var(--txt)">${esc(ev.reasoning)}</div>`;
  if(ev.recommended_next_step) html += `<div class="directive next">★ How to combine: ${esc(ev.recommended_next_step)}</div>`;
  $('criticBody').innerHTML = html;
}

function setSlot(stage, html){
  const slot = $('slot'+stage.charAt(0).toUpperCase()+stage.slice(1));
  const label = slot.querySelector('.label').outerHTML;
  slot.innerHTML = label + html;
}

async function init(){
  try{
    const h = await (await fetch('api/health')).json();
    $('modelInfo').textContent = `model: ${h.model}` + (h.images_enabled?' · images on':' · images OFF');
    setState('ready','ok');
  }catch(e){ setState('backend unreachable',''); }
}

function downloadAll(){
  const order = [['aria','1_ARIA_partial'],['nexus','2_NEXUS_addition'],['judge','3_JUDGE_final']];
  let delay = 0;
  for(const [stage,name] of order){
    if(!images[stage]) continue;
    setTimeout(()=>{
      const a = document.createElement('a');
      a.href = images[stage];
      a.download = `canvasmind_${name}.png`;
      document.body.appendChild(a); a.click(); a.remove();
    }, delay);
    delay += 400; // stagger so the browser allows all downloads
  }
  log('Downloading '+order.filter(o=>images[o[0]]).length+' image(s)…');
}
$('downloadBtn').onclick = downloadAll;

$('startBtn').onclick = async () => {
  const prompt = $('prompt').value.trim();
  if(!prompt){ alert('Enter a prompt first'); return; }
  $('ariaFeed').innerHTML=''; $('nexusFeed').innerHTML='';
  $('criticBody').innerHTML='Awaiting evaluation…'; $('stageLabel').textContent='';
  images.aria=images.nexus=images.judge=null; $('downloadBtn').disabled=true;
  setSlot('aria','<div class="ph">ARIA\'s partial painting will appear here.</div>');
  setSlot('nexus','<div class="ph">NEXUS extends ARIA\'s image here.</div>');
  setSlot('judge','<div class="ph">JUDGE merges both into the final artwork here.</div>');
  if(evtSource) evtSource.close();
  $('startBtn').disabled = true; setState('starting…','run');

  let res;
  try{
    res = await fetch('api/start', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, style: $('style').value.trim(), images:true})});
  }catch(e){ setState('failed to start','');$('startBtn').disabled=false; return; }
  const {session_id, error} = await res.json();
  if(error){ alert(error); setState('error','');$('startBtn').disabled=false; return; }

  log('Session '+session_id+' started'); setState('running','run');
  evtSource = new EventSource('api/stream/'+session_id);

  evtSource.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    switch(ev.type){
      case 'session': log(`Brief: "${ev.prompt}" · model ${ev.model}` + (ev.images?'':' · IMAGES DISABLED (no image deployment)')); break;
      case 'stage': $('stageLabel').textContent = ev.label; log('▶ '+ev.label); break;
      case 'agent': {
        const feed = ev.agent==='ARIA' ? $('ariaFeed') : $('nexusFeed');
        feed.insertAdjacentHTML('beforeend', agentCard(ev.agent, ev.message));
        feed.scrollTop = feed.scrollHeight; log(ev.agent+' responded'); break;
      }
      case 'critic': renderCritic(ev.evaluation); log('JUDGE evaluated · composite '+((ev.evaluation.scores||{}).composite||'?')); break;
      case 'image_pending': setSlot(ev.stage, '<div class="ph"><div class="spinner"></div>Generating image…</div>'); break;
      case 'image':
        images[ev.stage] = ev.image;
        setSlot(ev.stage, `<img src="${ev.image}" alt="${esc(ev.label)}"/>`);
        $('downloadBtn').disabled = false;
        log('Image ready: '+ev.label); break;
      case 'warning': log('⚠ '+ev.message); break;
      case 'summary':
        log(`Done: ${ev.outcome} · composite ${ev.composite?ev.composite.toFixed(1):'-'} · ${ev.elapsed}s`);
        setState(ev.outcome,'ok'); break;
      case 'error': log('ERROR: '+ev.message); alert('Error: '+ev.message); setState('error',''); break;
      case 'done': evtSource.close(); $('startBtn').disabled=false; break;
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
