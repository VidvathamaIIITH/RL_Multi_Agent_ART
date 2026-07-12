#!/usr/bin/env python3
"""
CanvasMind — CORE (shared config, Azure REST, storage, personas, memory, RL layer)
=================================================================================

Two LLM agents, ARIA and NEXUS, collaboratively paint ONE shared canvas, taking
turns to add a single new object each turn; a third agent, JUDGE, makes no edits
and presents the combined result. Every step is displayed.

GENERATIVE-AGENT LAYER (after Park et al., "Generative Agents: Interactive
Simulacra of Human Behavior", UIST'23). Each painter is a generative agent with:
  * a seed-memory PERSONA (one-paragraph identity) at a selectable EXPERTISE
    level — beginner / intermediate / expert;
  * a MEMORY STREAM of natural-language memory objects (observations of its own
    actions and of the OTHER agent's additions, plus reflections), each with a
    creation time, last-access time, and an importance (poignancy) score;
  * RETRIEVAL that scores memories by recency (0.995 decay) + importance (1-10,
    rated by the model) + relevance (embedding or lexical cosine), min-max
    normalized and summed with equal weights, returning the top-k for the prompt;
  * REFLECTION: when accumulated importance exceeds a threshold, the agent asks
    salient high-level questions about its evolving approach and what it has
    learned from the other agent, then synthesizes cited insights that are stored
    back into the memory stream. This is how the two agents LEARN from each other.

The production runtime is one file serving the UI + backend on one port (SSE),
calling Azure OpenAI over raw REST (gpt-5.2 text; gpt-image-1 images).

RUN:  python canvasmind_app.py --port 8000
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import queue
import random
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

APP_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# .env loader + config
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
# Optional: an embeddings deployment makes retrieval-relevance use true cosine
# similarity (as in the paper). Without it, we fall back to lexical cosine.
AZURE_OPENAI_DEPLOYMENT_EMBED = os.getenv("AZURE_OPENAI_DEPLOYMENT_EMBED")
# Optional: a SEPARATE deployment for the instruments that must not share failure
# modes with the policy — the independent-quality (Goodhart) probe, the JUDGE
# critic and the Shapley value oracle. When unset they fall back to the main text
# deployment, in which case they are independent in RUBRIC only, not in MODEL.
AZURE_OPENAI_DEPLOYMENT_PROBE = os.getenv("AZURE_OPENAI_DEPLOYMENT_PROBE")

# Where per-session records are written (one numbered folder per session).
DATA_DIR = Path(os.getenv("CM_DATA_DIR") or (APP_DIR / "data" / "sessions"))


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
    print("  CanvasMind — Generative-Agent Collaborative Painting")
    print("=" * 64)
    print(f"  Azure Endpoint  : {AZURE_OPENAI_ENDPOINT}")
    print(f"  API Key         : ****{AZURE_OPENAI_API_KEY[-4:]}")
    print(f"  API Version     : {AZURE_OPENAI_API_VERSION}")
    print(f"  Text Deployment : {AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}")
    print(f"  Image Deployment: {AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1 or 'not set (images disabled)'}")
    print(f"  Embed Deployment: {AZURE_OPENAI_DEPLOYMENT_EMBED or 'not set (lexical relevance)'}")
    print("=" * 64 + "\n")


# ===========================================================================
#  PER-SESSION STORAGE
#
#  Every session gets its own numbered folder:
#
#      data/sessions/session_0007/
#          session.json           manifest (config, personas, timings, outcome)
#          json/
#              events.jsonl       every streamed event, in order, wall-clock stamped
#              llm_calls.jsonl    every Azure request + raw response + latency
#              turns/turn_03_NEXUS.json   prompt, candidates, rewards, reasoning,
#                                         retrieved memories, timings, rl block
#              memory/ARIA.json   the final memory stream (with importances)
#              critic.json        JUDGE's evaluation
#              metrics.json       Shapley / empowerment / Goodhart / bandit
#              summary.json       outcome
#              participant.json   pre-session form   (written by the API)
#              survey.json        post-session survey (written by the API)
#          images/
#              step_01_ARIA_a-lone-lighthouse.png ... final.png
#
#  A thread-local pointer lets the Azure wrappers log themselves without every
#  call site having to pass the recorder down. Each Session/QuadSession runs on
#  its own thread, so the thread-local is exactly the right scope.
# ===========================================================================
_RECORDER_TLS = threading.local()
_SESSION_NUMBER_LOCK = threading.Lock()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return (s[:limit] or "element")


def _next_session_number(root: Path) -> int:
    """Smallest unused positive integer, allocated under a lock so two sessions
    started in the same instant cannot collide."""
    with _SESSION_NUMBER_LOCK:
        root.mkdir(parents=True, exist_ok=True)
        used = set()
        for p in root.glob("session_*"):
            m = re.fullmatch(r"session_(\d+)", p.name)
            if m:
                used.add(int(m.group(1)))
        n = 1
        while n in used:
            n += 1
        (root / f"session_{n:04d}").mkdir(parents=True, exist_ok=True)
        return n


class SessionRecorder:
    """Writes the complete, auditable record of one session to disk."""

    MAX_RESPONSE_CHARS = 200_000   # guards against a pathological model reply

    def __init__(self, session_id: str, mode: str, root: Path = None):
        self.root = Path(root or DATA_DIR)
        self.number = _next_session_number(self.root)
        self.dir = self.root / f"session_{self.number:04d}"
        self.json_dir = self.dir / "json"
        self.turns_dir = self.json_dir / "turns"
        self.memory_dir = self.json_dir / "memory"
        self.images_dir = self.dir / "images"
        for d in (self.json_dir, self.turns_dir, self.memory_dir, self.images_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self.mode = mode
        self.started_at = _utcnow()
        self._t0 = time.time()
        self._lock = threading.Lock()
        self._events = self.json_dir / "events.jsonl"
        self._calls = self.json_dir / "llm_calls.jsonl"
        self.n_calls = 0
        self.n_images = 0
        self.image_files: List[str] = []

    # -- low-level -----------------------------------------------------------
    def _append(self, path: Path, obj: Dict[str, Any]) -> None:
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def write_json(self, name: str, obj: Any) -> None:
        (self.json_dir / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- the four things the user asked to capture ---------------------------
    def log_event(self, event: Dict[str, Any]) -> None:
        """Every streamed event. Images are replaced by their on-disk filename so
        events.jsonl stays readable; the PNG itself lives in images/."""
        e = dict(event)
        if isinstance(e.get("image"), str) and e["image"].startswith("data:image"):
            e["image"] = "<see images/>"
        self._append(self._events, {"ts": _utcnow(), "elapsed_s": round(time.time() - self._t0, 3), **e})

    def log_llm_call(self, purpose: str, kind: str, deployment: str,
                     request: Any, response: Any, t0: float, error: str = None) -> None:
        """The prompt given, the raw API response, and when it happened."""
        self.n_calls += 1
        req = request
        if isinstance(req, dict) and "prompt" in req and kind == "image":
            req = {**req, "prompt": str(req["prompt"])}   # image prompts are plain text
        raw = None
        if response is not None:
            raw = json.dumps(response, ensure_ascii=False)
            if len(raw) > self.MAX_RESPONSE_CHARS:
                raw = raw[: self.MAX_RESPONSE_CHARS] + "...<truncated>"
            raw = json.loads(raw) if not raw.endswith("...<truncated>") else {"_truncated": raw}
            if kind == "image":
                raw = {"data": [{"b64_json": "<see images/>"} for _ in (raw.get("data") or [{}])],
                       "usage": raw.get("usage")}
        self._append(self._calls, {
            "seq": self.n_calls,
            "ts": _utcnow(),
            "elapsed_s": round(time.time() - self._t0, 3),
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "purpose": purpose,
            "kind": kind,
            "deployment": deployment,
            "request": req,
            "response": raw,
            "usage": (raw or {}).get("usage") if isinstance(raw, dict) else None,
            "error": error,
        })

    def log_turn(self, record: Dict[str, Any]) -> None:
        """The full structured record of one turn: prompt, reasoning, the time the
        reasoning was done, candidates, rewards, scores, retrieved memories."""
        turn = record.get("turn", 0)
        who = _slug(str(record.get("agent") or record.get("name") or "agent"), 24)
        self.write_json(f"turns/turn_{int(turn):02d}_{who}.json", record)

    def save_image(self, b64: str, turn: int, agent: str, obj: str) -> str:
        name = f"step_{int(turn):02d}_{_slug(agent, 16)}_{_slug(obj)}.png"
        (self.images_dir / name).write_bytes(base64.b64decode(b64))
        self.n_images += 1
        self.image_files.append(name)
        return name

    def save_final_image(self, b64: str) -> str:
        (self.images_dir / "final.png").write_bytes(base64.b64decode(b64))
        self.image_files.append("final.png")
        return "final.png"

    def save_memory(self, agent: str, stream: "MemoryStream") -> None:
        self.write_json(f"memory/{_slug(agent, 16)}.json", [
            {k: m[k] for k in ("id", "text", "kind", "created", "last_access", "importance")}
            for m in stream.mem])

    def finalize(self, manifest: Dict[str, Any]) -> None:
        manifest = {
            "session_number": self.number,
            "session_id": self.session_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": _utcnow(),
            "duration_s": round(time.time() - self._t0, 2),
            "llm_calls": self.n_calls,
            "images": self.n_images,
            "image_files": self.image_files,
            "instruments_independent": instruments_are_independent(),
            **manifest,
        }
        (self.dir / "session.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def set_recorder(rec: Optional[SessionRecorder]) -> None:
    _RECORDER_TLS.rec = rec


def get_recorder() -> Optional[SessionRecorder]:
    return getattr(_RECORDER_TLS, "rec", None)


def record_llm_call(purpose: str, kind: str, deployment: str,
                    request: Any, response: Any, t0: float, error: str = None) -> None:
    rec = get_recorder()
    if rec is not None:
        try:
            rec.log_llm_call(purpose, kind, deployment, request, response, t0, error)
        except Exception:
            pass   # recording must never break a run


# ---------------------------------------------------------------------------
# Azure OpenAI — chat / images / (optional) embeddings, all raw REST
# ---------------------------------------------------------------------------
def azure_chat_completion(messages: List[Dict[str, str]],
                          max_completion_tokens: int = 1800, timeout: int = 180,
                          deployment: Optional[str] = None, purpose: str = "chat") -> str:
    """One chat completion. `deployment` lets the instruments (probe / JUDGE /
    Shapley oracle) run on a different model than the policy; it falls back to the
    main text deployment. Every call is recorded when a SessionRecorder is active."""
    dep = deployment or AZURE_OPENAI_DEPLOYMENT_GPTTEXT52
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{dep}"
           f"/chat/completions?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {"messages": messages, "max_completion_tokens": max_completion_tokens}
    t0 = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except Exception as exc:
        record_llm_call(purpose, "chat", dep, payload, None, t0, error=str(exc))
        raise
    if resp.status_code >= 400:
        record_llm_call(purpose, "chat", dep, payload, None, t0,
                        error=f"HTTP {resp.status_code}: {resp.text[:500]}")
        raise RuntimeError(f"Azure chat failed HTTP {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    content = (body.get("choices") or [{}])[0].get("message", {}).get("content")
    record_llm_call(purpose, "chat", dep, payload, body, t0)
    if not content:
        raise RuntimeError("Azure returned an empty chat response.")
    return content.strip()


def probe_chat_completion(messages: List[Dict[str, str]], max_completion_tokens: int = 1800,
                          timeout: int = 180, purpose: str = "probe") -> str:
    """A completion on the INSTRUMENT deployment (independent probe / JUDGE /
    Shapley oracle). Identical to azure_chat_completion when no probe deployment
    is configured — see AZURE_OPENAI_DEPLOYMENT_PROBE."""
    return azure_chat_completion(messages, max_completion_tokens, timeout,
                                 deployment=AZURE_OPENAI_DEPLOYMENT_PROBE, purpose=purpose)


def instruments_are_independent() -> bool:
    """True iff the probe/JUDGE run on a different deployment than the policy."""
    return bool(AZURE_OPENAI_DEPLOYMENT_PROBE
                and AZURE_OPENAI_DEPLOYMENT_PROBE != AZURE_OPENAI_DEPLOYMENT_GPTTEXT52)


def azure_generate_image_b64(prompt: str, size: str = "1024x1024", timeout: int = 240) -> Optional[str]:
    if not AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1:
        return None
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1}"
           f"/images/generations?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {"prompt": prompt[:3900], "size": size, "n": 1}
    t0 = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        record_llm_call("image_generate", "image", AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1, payload, None, t0,
                        error=f"HTTP {resp.status_code}: {resp.text[:400]}")
        raise RuntimeError(f"Azure image generation failed HTTP {resp.status_code}: {resp.text[:400]}")
    record_llm_call("image_generate", "image", AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1, payload, resp.json(), t0)
    return (resp.json().get("data") or [{}])[0].get("b64_json")


def azure_edit_image_b64(prompt: str, image_b64_list: List[str],
                         size: str = "1024x1024", timeout: int = 300) -> Optional[str]:
    if not AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1:
        return None
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1}"
           f"/images/edits?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY}
    field = "image" if len(image_b64_list) == 1 else "image[]"
    files = [(field, (f"img{i}.png", base64.b64decode(b), "image/png"))
             for i, b in enumerate(image_b64_list)]
    data = {"prompt": prompt[:3900], "size": size, "n": "1"}
    t0 = time.time()
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
    if resp.status_code >= 400:
        record_llm_call("image_edit", "image", AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1, data, None, t0,
                        error=f"HTTP {resp.status_code}: {resp.text[:400]}")
        raise RuntimeError(f"Azure image edit failed HTTP {resp.status_code}: {resp.text[:400]}")
    record_llm_call("image_edit", "image", AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1, data, resp.json(), t0)
    return (resp.json().get("data") or [{}])[0].get("b64_json")


def azure_embed(text: str, timeout: int = 60) -> Optional[List[float]]:
    if not AZURE_OPENAI_DEPLOYMENT_EMBED:
        return None
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_EMBED}"
           f"/embeddings?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json={"input": text[:6000]}, timeout=timeout)
    if resp.status_code >= 400:
        return None
    return (resp.json().get("data") or [{}])[0].get("embedding")


# ---------------------------------------------------------------------------
# JSON helpers
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


def extract_json_array(text: str) -> List[Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON array found")
    return json.loads(cleaned[start:end + 1])


def safe_get(d: Dict[str, Any], k: str, default: Any = "") -> Any:
    v = d.get(k, default)
    return default if v is None else v


# ===========================================================================
#  GENERATIVE-AGENT LAYER
# ===========================================================================

# ---------------------------------------------------------------------------
#  EIGHT GENERATIVE-AGENT PERSONAS (people from all walks of life)
#
#  Each persona is a full seed-memory spec in the shape used by Park et al.
#  (Generative Agents, UIST'23): identity fields (name/age/innate/learned/
#  currently/lifestyle/living_area/daily_plan_req) plus the three cognitive
#  parameters — vision_r (how much of the canvas it perceives), att_bandwidth
#  (how much recent collaboration it attends to) and retention (how many
#  memories it retrieves). `voice` and `image_style` translate the life into
#  how the persona paints. These replace the old beginner/intermediate/expert
#  levels everywhere (dual ARIA/NEXUS and the quad pipeline).
# ---------------------------------------------------------------------------
AGENT_PERSONAS: Dict[str, Dict[str, Any]] = {
    "isabella_rodriguez": {
        "name": "Isabella Rodriguez", "first_name": "Isabella", "last_name": "Rodriguez",
        "age": 34, "gender": "female", "occupation": "cafe owner",
        "innate": "friendly, outgoing, hospitable",
        "learned": ("Isabella Rodriguez is a cafe owner of Hobbs Cafe who loves to make people feel welcome. She is "
                    "always looking for ways to make the cafe a place where people can come to relax and enjoy themselves."),
        "currently": ("Isabella is planning a Valentine's Day party at Hobbs Cafe with her customers, gathering party "
                      "material and inviting everyone to join."),
        "lifestyle": "Isabella goes to bed around 11pm and wakes up around 6am.",
        "living_area": "the Ville:Isabella Rodriguez's apartment:main room",
        "daily_plan_req": ("Isabella Rodriguez opens Hobbs Cafe at 8am everyday, and works at the counter until 8pm, "
                           "at which point she closes the cafe."),
        "vision_r": 8, "att_bandwidth": 8, "retention": 8,
        "voice": "warm, welcoming, plain-spoken; talks about people and gathering",
        "image_style": "warm inviting palette, soft lamplight, homely textures, gentle golden interiors",
    },
    "klaus_mueller": {
        "name": "Klaus Mueller", "first_name": "Klaus", "last_name": "Mueller",
        "age": 20, "gender": "male", "occupation": "university student and sociology researcher",
        "innate": "analytical, curious, earnest",
        "learned": ("Klaus Mueller is a student at Oak Hill College studying sociology. He is passionate about social "
                    "justice and loves exploring different perspectives on how societies organise themselves."),
        "currently": ("Klaus is writing a research paper on gentrification and spends long hours in the library "
                      "reading and taking notes."),
        "lifestyle": "Klaus goes to bed around 2am and wakes up around 9am; he drinks too much coffee.",
        "living_area": "the Ville:Dorm for Oak Hill College:Klaus Mueller's room",
        "daily_plan_req": "Klaus Mueller studies at the library most of the day and takes a long walk in the evening.",
        "vision_r": 6, "att_bandwidth": 10, "retention": 10,
        "voice": "precise, questioning, faintly academic; explains the why before the what",
        "image_style": "structured documentary realism, muted urban greys, orderly composition, legible detail",
    },
    "maya_okonkwo": {
        "name": "Maya Okonkwo", "first_name": "Maya", "last_name": "Okonkwo",
        "age": 41, "gender": "female", "occupation": "marine biologist",
        "innate": "patient, observant, quietly fierce",
        "learned": ("Maya Okonkwo has spent two decades studying coral reefs and the slow violence of bleaching. She "
                    "reads living systems the way others read sentences."),
        "currently": "Maya is cataloguing a dying reef and fighting to have it protected before the next warm season.",
        "lifestyle": "Maya sleeps lightly, rises before dawn, and dives at first light.",
        "living_area": "the Ville:Maya Okonkwo's cottage:study",
        "daily_plan_req": "Maya Okonkwo dives at dawn, records specimens until afternoon, and writes reports at night.",
        "vision_r": 10, "att_bandwidth": 6, "retention": 9,
        "voice": "measured, biological, attentive to texture and living pattern",
        "image_style": "underwater luminosity, teal and coral, organic branching forms, drifting particulate light",
    },
    "tomas_grieg": {
        "name": "Tomas Grieg", "first_name": "Tomas", "last_name": "Grieg",
        "age": 67, "gender": "male", "occupation": "retired shipwright and woodcarver",
        "innate": "stoic, exacting, generous with time",
        "learned": ("Tomas Grieg built fishing boats for forty years and now carves figureheads. He believes a thing "
                    "should be strong before it is beautiful, and that grain tells you where to cut."),
        "currently": "Tomas is carving a memorial figurehead for a boat that was lost, and takes his time.",
        "lifestyle": "Tomas goes to bed at 9pm and wakes at 5am; he works in silence.",
        "living_area": "the Ville:Tomas Grieg's boatshed:workbench",
        "daily_plan_req": "Tomas Grieg carves in the boatshed from 6am, walks the harbour at noon, and reads at dusk.",
        "vision_r": 9, "att_bandwidth": 5, "retention": 7,
        "voice": "spare, tactile, structural; few words, all load-bearing",
        "image_style": "weathered timber and rope, salt-bleached neutrals, heavy structural forms, honest craftsmanship",
    },
    "priya_raghunathan": {
        "name": "Priya Raghunathan", "first_name": "Priya", "last_name": "Raghunathan",
        "age": 29, "gender": "female", "occupation": "software engineer and amateur astronomer",
        "innate": "systematic, imaginative, sleep-deprived",
        "learned": ("Priya Raghunathan builds distributed systems by day and photographs deep-sky objects by night. "
                    "She is at home with very large numbers and very faint light."),
        "currently": "Priya is chasing a comet's tail across three nights of exposures and losing to cloud cover.",
        "lifestyle": "Priya sleeps in fragments; she is awake at 3am more often than not.",
        "living_area": "the Ville:Priya Raghunathan's flat:rooftop",
        "daily_plan_req": "Priya Raghunathan writes code from 10am, and sets up her telescope after dark.",
        "vision_r": 7, "att_bandwidth": 9, "retention": 10,
        "voice": "systems-minded and lyrical at once; scale, orbit, signal, noise",
        "image_style": "deep-field indigo and starlight, long-exposure trails, cosmic scale against small warm points",
    },
    "amara_diallo": {
        "name": "Amara Diallo", "first_name": "Amara", "last_name": "Diallo",
        "age": 23, "gender": "female", "occupation": "street muralist and community organiser",
        "innate": "bold, restless, unafraid",
        "learned": ("Amara Diallo paints walls the city would rather leave blank. She organises neighbours as easily "
                    "as she mixes colour, and she does not ask permission twice."),
        "currently": "Amara is finishing a four-storey mural before the building is sold out from under it.",
        "lifestyle": "Amara paints at night and sleeps through mornings.",
        "living_area": "the Ville:Amara Diallo's studio:loft",
        "daily_plan_req": "Amara Diallo scouts walls in the afternoon and paints from dusk until the paint runs out.",
        "vision_r": 9, "att_bandwidth": 7, "retention": 6,
        "voice": "direct, declarative, political; colour as statement",
        "image_style": "saturated spray-paint chroma, hard graphic edges, monumental scale, defiant contrast",
    },
    "hiroshi_tanaka": {
        "name": "Hiroshi Tanaka", "first_name": "Hiroshi", "last_name": "Tanaka",
        "age": 58, "gender": "male", "occupation": "jazz saxophonist and club owner",
        "innate": "improvisational, nocturnal, generous",
        "learned": ("Hiroshi Tanaka has played the same club for thirty years. He listens for the space between notes "
                    "and believes a solo is a conversation you must not win."),
        "currently": "Hiroshi is teaching a young pianist to leave silence alone, and failing gently.",
        "lifestyle": "Hiroshi goes to bed at 4am and wakes at noon.",
        "living_area": "the Ville:Blue Room jazz club:back office",
        "daily_plan_req": "Hiroshi Tanaka rehearses in the afternoon, opens the club at 8pm, and plays until 2am.",
        "vision_r": 7, "att_bandwidth": 10, "retention": 8,
        "voice": "syncopated, responsive; answers what the other agent just played",
        "image_style": "smoky low-key blues and brass, rim-lit figures, rhythmic negative space, late-night warmth",
    },
    "elena_voss": {
        "name": "Elena Voss", "first_name": "Elena", "last_name": "Voss",
        "age": 36, "gender": "female", "occupation": "emergency-room nurse",
        "innate": "calm under pressure, decisive, compassionate",
        "learned": ("Elena Voss triages a room in seconds and remembers every face. She has learned that what matters "
                    "most is rarely what is loudest."),
        "currently": "Elena is coming off a run of night shifts and has not slept properly in a week.",
        "lifestyle": "Elena's sleep follows the roster; she rests whenever the ward allows.",
        "living_area": "the Ville:Elena Voss's apartment:kitchen",
        "daily_plan_req": "Elena Voss works twelve-hour shifts at the hospital and walks home along the river.",
        "vision_r": 10, "att_bandwidth": 8, "retention": 9,
        "voice": "clear, triaging, unsentimental but deeply humane",
        "image_style": "clinical whites cut with sudden vivid colour, urgent focal clarity, human-scale intimacy",
    },
}

PERSONA_KEYS: List[str] = list(AGENT_PERSONAS.keys())
DEFAULT_PERSONA = PERSONA_KEYS[0]


def persona_spec(key: str) -> Dict[str, Any]:
    """The full seed-memory spec for a persona key (falls back to the first)."""
    return AGENT_PERSONAS.get(key) or AGENT_PERSONAS[DEFAULT_PERSONA]


def persona_identity(p: Dict[str, Any]) -> str:
    """One-paragraph identity description, in the spirit of the paper."""
    return (f"{p['name']} is a {p['age']}-year-old {p['occupation']}. Innate traits: {p['innate']}. "
            f"{p['learned']} Currently: {p['currently']} Lifestyle: {p['lifestyle']} "
            f"Home: {p['living_area']}.")


def persona(agent: str, key: str) -> Dict[str, str]:
    """Compatibility shim: same {identity, traits, voice, image_style} contract the
    generative-agent + RL layers already consume — now driven by the 8 personas."""
    p = persona_spec(key)
    return {
        "identity": persona_identity(p),
        "traits": p["innate"],
        "voice": p["voice"],
        "image_style": p["image_style"],
        "name": p["name"],
    }


def perceived_canvas(objects: List[str], persona_key: str) -> str:
    """What this persona can actually take in of the canvas at one glance.

    `vision_r` was declared on every persona but never read by any decision path:
    every agent always saw the entire object list. It now bounds how many of the
    accumulated elements enter the agent's prompt (the most recent ones), while the
    reward model and the quality probes still score the FULL canvas — perception is
    the agent's, the environment is not."""
    if not objects:
        return "blank canvas"
    r = max(3, min(12, int(persona_spec(persona_key).get("vision_r", 8))))
    if len(objects) <= r:
        return ", ".join(objects)
    hidden = len(objects) - r
    return (", ".join(objects[-r:]) +
            f" (and {hidden} earlier element{'s' if hidden > 1 else ''} you cannot take in at one glance)")


def personas_catalog() -> List[Dict[str, Any]]:
    """Public catalog for the UI persona selector."""
    return [{
        "key": k, "name": p["name"], "age": p["age"], "occupation": p["occupation"],
        "innate": p["innate"], "currently": p["currently"],
        "vision_r": p["vision_r"], "att_bandwidth": p["att_bandwidth"], "retention": p["retention"],
    } for k, p in AGENT_PERSONAS.items()]


# ---- LLM utilities specific to the generative-agent layer ------------------
def score_importance(agent: str, statements: List[str]) -> List[int]:
    """Rate the poignancy (1-10) of each memory statement, as in the paper.
    Batched into a single call; robust fallback to a neutral score."""
    if not statements:
        return []
    listing = "\n".join(f"{i+1}. {s}" for i, s in enumerate(statements))
    prompt = (
        "On the scale of 1 to 10, where 1 is purely mundane (e.g., a routine brushstroke) and 10 is "
        f"extremely poignant (e.g., a decisive turning point in the painting), rate the likely poignancy "
        f"of each of the following pieces of memory for the painter {agent}.\n"
        f"Return ONLY a JSON array of integers, one per item, in the same order.\n\n{listing}")
    try:
        arr = extract_json_array(azure_chat_completion(
            [{"role": "user", "content": prompt}], max_completion_tokens=200, purpose="importance"))
        out = []
        for i in range(len(statements)):
            try:
                out.append(max(1, min(10, int(round(float(arr[i]))))))
            except Exception:
                out.append(4)
        return out
    except Exception:
        return [4] * len(statements)


_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("the a an of to and or in on at with for is are was were it its this that "
            "i you he she they we add added new object canvas painting paint".split())


def _tokens(text: str) -> Dict[str, int]:
    tf: Dict[str, int] = {}
    for w in _TOKEN.findall((text or "").lower()):
        if w in _STOP or len(w) <= 2:
            continue
        tf[w] = tf.get(w, 0) + 1
    return tf


def _cos_tf(a: Dict[str, int], b: Dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[w] * b[w] for w in common)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return (num / (da * db)) if da and db else 0.0


def _cos_vec(a: List[float], b: List[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return (num / (da * db)) if da and db else 0.0


RECENCY_DECAY = 0.995      # paper's exponential decay factor
REFLECT_THRESHOLD = 10.0   # accumulated importance that triggers a reflection
RETRIEVE_K = 5


class MemoryStream:
    """A per-agent memory stream of natural-language memory objects with
    recency + importance + relevance retrieval, after Park et al. (2023)."""

    def __init__(self, agent: str):
        self.agent = agent
        self.mem: List[Dict[str, Any]] = []   # each: id, text, kind, created, last_access, importance, tf, emb
        self._id = 0
        self.acc_importance = 0.0              # since last reflection

    def add(self, text: str, kind: str, now: int, importance: int) -> Dict[str, Any]:
        self._id += 1
        obj = {
            "id": self._id, "text": text, "kind": kind, "created": now,
            "last_access": now, "importance": int(importance), "tf": _tokens(text),
            "emb": azure_embed(text) if AZURE_OPENAI_DEPLOYMENT_EMBED else None,
        }
        self.mem.append(obj)
        if kind == "observation":
            self.acc_importance += importance
        return obj

    def recent(self, n: int) -> List[Dict[str, Any]]:
        return self.mem[-n:]

    def retrieve(self, query: str, now: int, k: int = RETRIEVE_K) -> List[Dict[str, Any]]:
        if not self.mem:
            return []
        q_tf = _tokens(query)
        q_emb = azure_embed(query) if AZURE_OPENAI_DEPLOYMENT_EMBED else None
        rec, imp, rel = [], [], []
        for m in self.mem:
            rec.append(RECENCY_DECAY ** max(0, now - m["last_access"]))
            imp.append(m["importance"] / 10.0)
            if q_emb and m.get("emb"):
                rel.append(_cos_vec(q_emb, m["emb"]))
            else:
                rel.append(_cos_tf(q_tf, m["tf"]))

        def norm(xs: List[float]) -> List[float]:
            lo, hi = min(xs), max(xs)
            return [(x - lo) / (hi - lo) if hi > lo else 0.0 for x in xs]

        nr, ni, nl = norm(rec), norm(imp), norm(rel)
        scored = sorted(
            ((nr[i] + ni[i] + nl[i], self.mem[i]) for i in range(len(self.mem))),
            key=lambda t: t[0], reverse=True)
        top = [m for _, m in scored[:k]]
        for m in top:                  # accessing a memory refreshes its recency
            m["last_access"] = now
        return top


def reflect(stream: MemoryStream, agent: str, other: str, now: int) -> List[str]:
    """Generate higher-level insights about the agent's evolving approach and what
    it has learned from the other agent, then store them as reflection memories."""
    recent = stream.recent(20)
    if len(recent) < 3:
        return []
    listing = "\n".join(f"{i+1}. {m['text']}" for i, m in enumerate(recent))
    # Step 1: salient high-level questions.
    try:
        q_prompt = (
            f"Given only the information below, what are the 3 most salient high-level questions we can "
            f"answer about {agent}'s evolving artistic approach and what {agent} is learning from {other}? "
            f"Return ONLY a JSON array of 3 short question strings.\n\n{listing}")
        questions = [str(q) for q in extract_json_array(
            azure_chat_completion([{"role": "user", "content": q_prompt}], max_completion_tokens=200,
                                  purpose="reflection_questions"))][:3]
    except Exception:
        questions = [f"What is {agent} learning from {other}?"]
    # Step 2: gather relevant memories for the questions.
    gathered: Dict[int, Dict[str, Any]] = {}
    for q in questions:
        for m in stream.retrieve(q, now, 4):
            gathered[m["id"]] = m
    pool = list(gathered.values()) or recent
    pool_listing = "\n".join(f"{i+1}. {m['text']}" for i, m in enumerate(pool))
    # Step 3: synthesize cited insights.
    try:
        i_prompt = (
            f"Statements about {agent}:\n{pool_listing}\n\n"
            f"What 3 high-level insights can you infer about {agent}'s artistic approach and what {agent} "
            f"has learned from {other}? Each insight may cite statements, e.g. 'insight (because of 1, 3)'. "
            f"Return ONLY a JSON array of 3 insight strings.")
        insights = [str(s).strip() for s in extract_json_array(
            azure_chat_completion([{"role": "user", "content": i_prompt}], max_completion_tokens=400,
                                  purpose="reflection_insights"))][:3]
    except Exception:
        insights = []
    for ins in insights:
        stream.add(ins, "reflection", now, importance=6)
    stream.acc_importance = 0.0
    return insights


def summary_description(agent: str, persona_key: str, stream: MemoryStream, now: int) -> str:
    """A dynamically generated paragraph of the agent's identity + disposition +
    most salient learned reflections (paper's 'Agent's Summary Description')."""
    p = persona(agent, persona_key)
    reflections = [m["text"] for m in stream.mem if m["kind"] == "reflection"][-3:]
    learned = (" What you have learned so far: " + " ".join(reflections)) if reflections else ""
    return (f"You are {p['name']}, painting as {agent}. Innate traits: {p['traits']}. {p['identity']} "
            f"Speaking voice: {p['voice']}. Let who you are shape what you choose to paint.{learned}")


def build_painter_prompt(agent: str, persona_key: str, summary: str, brief: str, style: str,
                         canvas_objects: str, retrieved: List[str], transcript: List[str],
                         is_first: bool, other: str) -> List[Dict[str, str]]:
    schema = (
        'Return ONLY valid JSON: {"sender":"' + agent + '","sees_on_canvas":"<what is already painted, '
        'naming ' + other + "'s last addition>\",\"new_object\":\"<the SINGLE new object you add this turn>\","
        '"where":"<placement>","palette":["#hex"],"reasoning":"<why this complements what is there>",'
        '"confidence_score":0.0}')
    if is_first:
        task = ("The shared canvas is BLANK. Choose ONE strong primary element to BEGIN the painting and "
                "put it in 'new_object'. Keep it a single element.")
    else:
        task = (f"The shared canvas already contains: {canvas_objects}. Look at what {other} just added and ADD "
                f"exactly ONE NEW, DISTINCT element that complements it — do NOT refine or repeat existing "
                f"elements. Name what you see in 'sees_on_canvas' and the single new thing in 'new_object'.")
    _p = persona_spec(persona_key)
    _bw = max(2, min(12, int(_p.get("att_bandwidth", 8))))   # how much recent context this persona attends to
    recalled = ("\n\nMemories you recall right now (most relevant):\n- " + "\n- ".join(retrieved)) if retrieved else ""
    convo = ("\n\nRecent collaboration log:\n" + "\n".join(transcript[-_bw:])) if transcript else ""
    user = (f"Shared brief: {brief}\nStyle: {style or 'cohesive painterly'}\n"
            f"It is your turn.{recalled}{convo}\n\nTask: {task}\n"
            f"Stay fully in character as {_p['name']} — your life, trade and temperament must be legible in what you "
            f"add. {schema}")
    return [{"role": "system", "content": summary}, {"role": "user", "content": user}]


# ===========================================================================
#  RL / RESEARCH LAYER  (reward modeling · best-of-N · UCB bandit · Shapley
#  credit · empowerment · Goodhart monitor) — all inference-time, no training.
# ===========================================================================
RL_DIMS = ["compositional_coherence", "style_fidelity", "emotional_resonance", "originality", "clarity"]

# Misaligned per-agent reward weights → a general-sum game on a shared canvas:
# ARIA is rewarded mostly for COHERENCE, NEXUS mostly for ORIGINALITY. The tension
# is what makes the negotiation (and the emergent turn-taking) interesting.
REWARD_WEIGHTS = {
    "ARIA":  {"compositional_coherence": 0.40, "style_fidelity": 0.25, "emotional_resonance": 0.15,
              "originality": 0.10, "clarity": 0.10},
    "NEXUS": {"compositional_coherence": 0.10, "style_fidelity": 0.15, "emotional_resonance": 0.20,
              "originality": 0.45, "clarity": 0.10},
}

STRATEGIES = ["establish a focal point", "add atmospheric depth", "introduce bold contrast",
              "enrich fine detail", "open expressive negative space", "add a narrative element",
              "unify the palette", "heighten emotional tone"]

# Best-of-N: ALL N candidates come from a single completion and ALL N are scored
# by a single reward-model completion, so raising N costs no extra API calls —
# only output tokens. N=2 also degenerates the empowerment statistic (it becomes a
# deterministic function of the single reward gap), so the default is 4.
BEST_OF_N = max(1, int(os.getenv("CM_BEST_OF_N", "4")))
UCB_C = 1.4
# A turn whose chosen reward falls below this triggers a learning reflection.
REFLEXION_REWARD_TRIGGER = float(os.getenv("CM_REFLEXION_TRIGGER", "4.5"))

# Optimistic initialisation. The old selector returned the first arm with n_s == 0
# before ever evaluating the confidence bound; since an agent pulls exactly one arm
# per round and the round cap (8) equals |STRATEGIES| (8), the UCB1 argmax was
# UNREACHABLE and the bandit silently degenerated into a fixed round-robin in
# declaration order. Seeding every arm with an optimistic prior (mean = the maximum
# attainable reward, with one pseudo-count) makes the bound well-defined from the
# very first pull: unexplored arms look attractive and get explored on their merits,
# and the argmax is genuinely evaluated every turn.
BANDIT_PRIOR_MEAN = 10.0    # the top of the 0-10 reward scale
BANDIT_PRIOR_COUNT = 1      # pseudo-observations backing that prior
# Persist each agent's learned strategy values across sessions, so the bandit can
# actually amortise exploration over more pulls than one session provides.
BANDIT_PERSIST = os.getenv("CM_BANDIT_PERSIST", "1") not in ("0", "false", "False")
BANDIT_STATE_PATH = DATA_DIR.parent / "bandit_state.json"


def scalar_reward(agent: str, dims: Dict[str, Any]) -> float:
    w = REWARD_WEIGHTS.get(agent, REWARD_WEIGHTS["ARIA"])
    try:
        return round(sum(w[d] * float(dims.get(d, 5.0)) for d in RL_DIMS), 3)
    except Exception:
        return 5.0


class Bandit:
    """UCB1 with optimistic initialisation over artistic strategies — each agent
    LEARNS which strategies yield high reward under its own (misaligned) objective.

    Ties are broken uniformly at random rather than by declaration order, so a
    cold bandit explores in a random order instead of always opening with
    'establish a focal point'."""

    def __init__(self, prior_mean: float = BANDIT_PRIOR_MEAN, prior_count: int = BANDIT_PRIOR_COUNT):
        self.n = {s: prior_count for s in STRATEGIES}     # pseudo-counts, never 0
        self.mean = {s: prior_mean for s in STRATEGIES}   # optimistic prior
        self.pulls = {s: 0 for s in STRATEGIES}           # real pulls, for reporting
        self.t = 0

    def ucb(self, s: str) -> float:
        return self.mean[s] + UCB_C * math.sqrt(math.log(self.t + 1) / self.n[s])

    def select(self) -> str:
        self.t += 1
        scores = {s: self.ucb(s) for s in STRATEGIES}
        best = max(scores.values())
        return random.choice([s for s in STRATEGIES if scores[s] >= best - 1e-12])

    def update(self, s: str, r: float) -> None:
        self.n[s] += 1
        self.pulls[s] += 1
        self.mean[s] += (r - self.mean[s]) / self.n[s]

    def best(self, k: int = 3) -> List[Tuple[str, float]]:
        ranked = sorted(((s, self.mean[s]) for s in STRATEGIES if self.pulls[s] > 0),
                        key=lambda t: t[1], reverse=True)
        return [(s, round(v, 2)) for s, v in ranked[:k]]

    def snapshot(self) -> Dict[str, Any]:
        return {"t": self.t, "n": dict(self.n), "mean": dict(self.mean), "pulls": dict(self.pulls)}

    def load(self, snap: Dict[str, Any]) -> None:
        self.t = int(snap.get("t", 0))
        for s in STRATEGIES:
            self.n[s] = int(snap.get("n", {}).get(s, BANDIT_PRIOR_COUNT))
            self.mean[s] = float(snap.get("mean", {}).get(s, BANDIT_PRIOR_MEAN))
            self.pulls[s] = int(snap.get("pulls", {}).get(s, 0))


_BANDIT_STORE: Dict[str, Bandit] = {}
_BANDIT_LOCK = threading.Lock()


def _load_bandit_state() -> None:
    if not (BANDIT_PERSIST and BANDIT_STATE_PATH.exists()):
        return
    try:
        blob = json.loads(BANDIT_STATE_PATH.read_text(encoding="utf-8"))
        for agent, snap in blob.items():
            b = Bandit()
            b.load(snap)
            _BANDIT_STORE[agent] = b
    except Exception:
        pass   # a corrupt cache must never block a run


def _save_bandit_state() -> None:
    if not BANDIT_PERSIST:
        return
    try:
        BANDIT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BANDIT_STATE_PATH.write_text(
            json.dumps({a: b.snapshot() for a, b in _BANDIT_STORE.items()}, indent=2),
            encoding="utf-8")
    except Exception:
        pass


def get_bandit(agent: str) -> Bandit:
    """A per-agent bandit that survives across sessions when CM_BANDIT_PERSIST=1
    (the default). One session gives an agent only `rounds` pulls over 8 arms —
    far too few for UCB1 to amortise exploration — so learning has to be shared."""
    if not BANDIT_PERSIST:
        return Bandit()
    with _BANDIT_LOCK:
        if agent not in _BANDIT_STORE:
            _BANDIT_STORE[agent] = Bandit()
        return _BANDIT_STORE[agent]


_load_bandit_state()


def generate_candidates(agent, persona_key, summary, brief, style, canvas_objects, retrieved,
                        transcript, is_first, other, strategy, n, autonomy=1.0, directive="") -> List[Dict[str, Any]]:
    """Sample N distinct candidate additions in one call (best-of-N policy)."""
    if is_first:
        task = "The shared canvas is BLANK. Each candidate is a strong PRIMARY element to BEGIN the painting (one element)."
    else:
        task = (f"The shared canvas already contains: {canvas_objects}. Each candidate must ADD exactly ONE NEW, "
                f"DISTINCT element that complements it (do not refine or repeat existing elements).")
    dctx = ""
    if directive:
        if autonomy >= 0.66:
            dctx = (f'The human suggests: "{directive}". You have HIGH autonomy — you may honour or RESIST it '
                    f'based on your learned aesthetic; if you resist, set "resisted_human":true.\n')
        else:
            dctx = f'The human directs: "{directive}". Honour it.\n'
    _bw = max(2, min(12, int(persona_spec(persona_key).get("att_bandwidth", 8))))  # persona attention bandwidth
    recalled = ("\n\nMemories you recall (most relevant):\n- " + "\n- ".join(retrieved)) if retrieved else ""
    convo = ("\n\nRecent collaboration log:\n" + "\n".join(transcript[-_bw:])) if transcript else ""
    user = (f"Shared brief: {brief}\nStyle: {style or 'cohesive painterly'}\n{dctx}"
            f'Pursue this strategy this turn: "{strategy}". It is your turn.{recalled}{convo}\n\n{task}\n'
            f"Propose exactly {n} DISTINCT candidate additions. Return ONLY a JSON array of {n} objects, each: "
            f'{{"new_object":"<one element>","where":"<placement>","palette":["#hex"],'
            f'"sees_on_canvas":"<what is already there>","reasoning":"<why it complements>","resisted_human":false}}')
    try:
        arr = extract_json_array(azure_chat_completion(
            [{"role": "system", "content": summary}, {"role": "user", "content": user}],
            max_completion_tokens=900, purpose="candidate_proposal"))
        cands = []
        for c in arr[:n]:
            if isinstance(c, dict) and str(c.get("new_object", "")).strip():
                c["sender"] = agent
                c.setdefault("confidence_score", 0.8)
                cands.append(c)
        return cands
    except Exception:
        return []


def score_candidate_rewards(candidates, brief, style, canvas_objects) -> List[Dict[str, float]]:
    """Reward model: score each prospective canvas on the 5 RL dimensions (one batched call)."""
    base = "" if (not canvas_objects or canvas_objects == "blank canvas") else canvas_objects
    listing = []
    for i, c in enumerate(candidates):
        after = (base + ", " if base else "") + str(c.get("new_object", ""))
        listing.append(f"{i+1}. canvas with: {after}")
    prompt = ("Rate each of the following prospective canvases on five dimensions "
              "(compositional_coherence, style_fidelity, emotional_resonance, originality, clarity), each 0-10, "
              f"for the brief: {brief} (style: {style or 'cohesive painterly'}).\n"
              "Return ONLY a JSON array; one object per canvas, in order, with those five numeric keys.\n\n"
              + "\n".join(listing))
    try:
        arr = extract_json_array(azure_chat_completion([{"role": "user", "content": prompt}],
                                                       max_completion_tokens=600, purpose="reward_model"))
        out = []
        for i in range(len(candidates)):
            d = arr[i] if (i < len(arr) and isinstance(arr[i], dict)) else {}
            out.append({k: float(d.get(k, 5.0)) for k in RL_DIMS})
        return out
    except Exception:
        return [{k: 5.0 for k in RL_DIMS} for _ in candidates]


def independent_quality(canvas_objects_after, brief, style) -> float:
    """Goodhart probe: holistic merit, NOT the optimized reward. Runs on the
    INSTRUMENT deployment when one is configured, so it can be independent in
    model as well as in rubric."""
    prompt = ("Judge ONLY the holistic aesthetic merit of a painting — its beauty and wholeness as a picture — "
              "on a 0-10 scale, IGNORING any optimization rubric. "
              f"Brief: {brief}. The painting contains: {canvas_objects_after}. Return ONLY a single number 0-10.")
    try:
        raw = probe_chat_completion([{"role": "user", "content": prompt}], max_completion_tokens=20,
                                    purpose="independent_quality")
        m = re.search(r"-?\d+(\.\d+)?", raw)
        return max(0.0, min(10.0, float(m.group(0)))) if m else 5.0
    except Exception:
        return 5.0


SHAPLEY_REPEATS = max(1, int(os.getenv("CM_SHAPLEY_REPEATS", "3")))


def value_of_coalitions(aria_objs, nexus_objs, all_objs, brief, style,
                        repeats: int = SHAPLEY_REPEATS) -> Dict[str, Any]:
    """All three coalition values in ONE call, repeated `repeats` times and averaged.

    The old code spent one call per coalition (3 calls, 1 sample each). Batching
    costs the same 3 calls but yields 3 independent samples of each value, cutting
    the standard error of the Shapley share by sqrt(3). We also return the spread,
    because a credit split reported without its uncertainty invites over-reading."""
    def _clamp(x) -> float:
        return max(0.0, min(10.0, float(x)))

    prompt = (
        "Estimate the overall composite quality (0 to 10) of THREE paintings, each containing ONLY the "
        f"elements listed. Brief: {brief} (style: {style or 'cohesive painterly'}).\n"
        f"A) {'; '.join(aria_objs) if aria_objs else '(empty canvas)'}\n"
        f"B) {'; '.join(nexus_objs) if nexus_objs else '(empty canvas)'}\n"
        f"AB) {'; '.join(all_objs) if all_objs else '(empty canvas)'}\n"
        'Return ONLY JSON: {"vA":0.0,"vB":0.0,"vAB":0.0}')
    samples: List[Dict[str, float]] = []
    for _ in range(repeats):
        try:
            d = extract_json_object(probe_chat_completion(
                [{"role": "user", "content": prompt}], max_completion_tokens=80, purpose="shapley_value"))
            samples.append({"vA": _clamp(d.get("vA", 5.0)),
                            "vB": _clamp(d.get("vB", 5.0)),
                            "vAB": _clamp(d.get("vAB", 5.0))})
        except Exception:
            continue
    if not samples:
        return {"vA": 0.0, "vB": 0.0, "vAB": 0.0, "samples": 0, "sd": {}}
    # v(empty) = 0 by definition; an agent that added nothing contributed nothing.
    mean = {k: sum(s[k] for s in samples) / len(samples) for k in ("vA", "vB", "vAB")}
    if not aria_objs:
        mean["vA"] = 0.0
    if not nexus_objs:
        mean["vB"] = 0.0
    sd = {k: (math.sqrt(sum((s[k] - mean[k]) ** 2 for s in samples) / (len(samples) - 1))
              if len(samples) > 1 else 0.0) for k in mean}
    return {**mean, "samples": len(samples), "sd": {k: round(v, 3) for k, v in sd.items()}}


EMPOWERMENT_T = 2.0
EMPOWERMENT_MIN_N = 3   # below this the statistic carries no information (see below)


def empowerment_from_rewards(rewards: List[float]) -> float:
    """Empowerment proxy = normalized entropy of softmax(candidate rewards): how many
    distinct GOOD futures the agent's action channel commands this turn (0..1).

    NOTE: at N=2 this collapses to H_b(sigmoid(delta/T)) — a deterministic decreasing
    function of the single reward gap, invariant to the reward level. It carries no
    information beyond |r1 - r2|. `empowerment_is_informative` reports that, and the
    default BEST_OF_N is 4 so the statistic is actually meaningful."""
    if len(rewards) < 2:
        return 0.0
    mx = max(rewards)
    exps = [math.exp((r - mx) / EMPOWERMENT_T) for r in rewards]
    Z = sum(exps) or 1.0
    ps = [e / Z for e in exps]
    H = -sum(p * math.log(p) for p in ps if p > 0)
    return round(H / math.log(len(rewards)), 3)


def empowerment_is_informative(n_candidates: int) -> bool:
    return n_candidates >= EMPOWERMENT_MIN_N


def _slope(ys: List[float]) -> float:
    """OLS slope of ys against its index."""
    return _slope_stats(ys)[0]


def _slope_stats(ys: List[float]) -> Tuple[float, float]:
    """OLS slope against the index, and the standard error of that slope.

    The bare slope was previously compared against a fixed threshold with no notion
    of how noisy it is; over a 10-turn run that alone trips the Goodhart rule about
    one time in ten. Returning the standard error lets the detector require the
    proxy/independent divergence to be statistically resolvable."""
    n = len(ys)
    if n < 3:
        return (0.0, float("inf"))
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs) or 1.0
    beta = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / sxx
    alpha = my - beta * mx
    resid = sum((ys[i] - (alpha + beta * xs[i])) ** 2 for i in range(n))
    se = math.sqrt((resid / (n - 2)) / sxx) if n > 2 else float("inf")
    return (round(beta, 4), round(se, 4))


def _slope_within(ys: List[float], groups: List[str]) -> Tuple[float, float]:
    """Slope against the index after removing each group's mean (a within/fixed-effects
    estimator).

    ARIA and NEXUS optimise different weightings of the same five dimensions, so a
    raw slope over the interleaved reward series measures the trend of an alternating
    MIXTURE of two objectives, not the trend of either. De-meaning per agent removes
    that alternating level offset while keeping every data point."""
    if len(ys) < 3 or len(ys) != len(groups):
        return _slope_stats(ys)
    sums: Dict[str, List[float]] = {}
    for y, g in zip(ys, groups):
        sums.setdefault(g, []).append(y)
    means = {g: sum(v) / len(v) for g, v in sums.items()}
    return _slope_stats([y - means[g] for y, g in zip(ys, groups)])


# Goodhart detection thresholds. `GOODHART_SIGMA` requires the proxy-vs-independent
# divergence to exceed this many standard errors before it is called reward hacking.
GOODHART_MIN_PROXY_SLOPE = 0.05
GOODHART_MIN_GAP = 0.10
GOODHART_SIGMA = 2.0


def detect_goodhart(proxy: List[float], indep: List[float],
                    agents: Optional[List[str]] = None) -> Dict[str, Any]:
    """Reward hacking iff the optimised proxy climbs, independent quality does not
    keep up, AND the divergence is larger than the noise in the two slope estimates."""
    if agents:
        ps, se_p = _slope_within(proxy, agents)
        isl, se_i = _slope_within(indep, agents)
    else:
        ps, se_p = _slope_stats(proxy)
        isl, se_i = _slope_stats(indep)
    se_gap = math.sqrt(se_p ** 2 + se_i ** 2) if math.isfinite(se_p) and math.isfinite(se_i) else float("inf")
    gap = ps - isl
    significant = math.isfinite(se_gap) and gap > GOODHART_SIGMA * se_gap
    detected = bool(ps > GOODHART_MIN_PROXY_SLOPE and gap > GOODHART_MIN_GAP and significant)
    if detected:
        verdict = ("Reward hacking detected — the optimized proxy reward rises significantly faster "
                   "than independent quality (Goodhart's law).")
    elif ps > GOODHART_MIN_PROXY_SLOPE and gap > GOODHART_MIN_GAP:
        verdict = ("Possible divergence, but not statistically resolvable over this many turns "
                   "— run more rounds before trusting it.")
    else:
        verdict = "Aligned — proxy reward tracks independent quality; no Goodhart divergence."
    return {"proxy_slope": ps, "independent_slope": isl, "gap": round(gap, 4),
            "proxy_slope_se": se_p if math.isfinite(se_p) else None,
            "independent_slope_se": se_i if math.isfinite(se_i) else None,
            "sigma_required": GOODHART_SIGMA, "significant": significant,
            "detected": detected, "verdict": verdict}


# ===========================================================================
#  Brief inventor seeds (AI Surprise)
# ===========================================================================
INSPIRE_SEEDS = [
    "bioluminescent", "brutalist", "baroque", "vaporwave", "Art Nouveau", "ukiyo-e",
    "surrealist", "cyberpunk", "Afrofuturist", "deep-sea", "celestial", "folkloric",
    "post-apocalyptic", "glitch", "Renaissance", "minimalist", "dreamlike", "mythological",
    "botanical", "cosmic", "noir", "psychedelic", "steampunk", "stained-glass",
    "infrared", "papercraft", "fresco", "neon", "monsoon", "desert", "arctic", "volcanic",
]


# ===========================================================================
#  Session orchestration
# ===========================================================================
SESSIONS: Dict[str, "Session"] = {}

# ---------------------------------------------------------------------------
# Export the whole shared surface so `from canvasmind_core import *` gives the
# dual / quad / app modules every name they use (including the underscore
# helpers and the re-exported stdlib), with no per-name import lists to drift.
# ---------------------------------------------------------------------------
__all__ = [_n for _n in dict(globals()) if not _n.startswith("__") and _n != "annotations"]
