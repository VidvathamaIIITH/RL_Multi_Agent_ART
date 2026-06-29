#!/usr/bin/env python3
"""
CanvasMind — Single-File Full-Stack App (Generative-Agent Collaborative Painting)
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

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


# ---------------------------------------------------------------------------
# Azure OpenAI — chat / images / (optional) embeddings, all raw REST
# ---------------------------------------------------------------------------
def azure_chat_completion(messages: List[Dict[str, str]],
                          max_completion_tokens: int = 1800, timeout: int = 180) -> str:
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}"
           f"/chat/completions?api-version={AZURE_OPENAI_API_VERSION}")
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {"messages": messages, "max_completion_tokens": max_completion_tokens}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure chat failed HTTP {resp.status_code}: {resp.text[:500]}")
    content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("Azure returned an empty chat response.")
    return content.strip()


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
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure image edit failed HTTP {resp.status_code}: {resp.text[:400]}")
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

EXPERTISE_LEVELS = ["beginner", "intermediate", "expert"]

# Seed-memory personas (one-paragraph identities), per agent per expertise level,
# in the spirit of the paper's semicolon-delimited identity description. Each
# level also carries an innate-traits list, a speaking "voice", and an image
# style descriptor that scales rendering sophistication.
PERSONAS: Dict[str, Dict[str, Dict[str, str]]] = {
    "ARIA": {
        "beginner": {
            "identity": ("ARIA is an enthusiastic, early-career painter learning to direct a composition; "
                         "she keeps ideas simple and concrete, favouring familiar subjects such as skies, hills, "
                         "and water; she is curious and a little cautious; she pays close attention to what her "
                         "partner NEXUS adds so she can learn from him."),
            "traits": "curious, cautious, eager to learn",
            "voice": "plain, concrete language; very few technical terms",
            "image_style": "simple, clear, slightly naive painterly style",
        },
        "intermediate": {
            "identity": ("ARIA is a capable Creative Director who plans a painting's structure and mood; she knows "
                         "core composition and colour theory and uses common art terms; she makes clear, confident "
                         "proposals and adapts as the canvas grows; she works alongside NEXUS and is learning how "
                         "his additions complement her structure."),
            "traits": "decisive, organised, collaborative",
            "voice": "clear language with some art terminology",
            "image_style": "competent, balanced painterly style",
        },
        "expert": {
            "identity": ("ARIA is a seasoned Creative Director and master painter who has led countless collaborative "
                         "canvases; she thinks in terms of composition, focal hierarchy, and atmospheric depth; she "
                         "speaks with art-historical fluency, referencing chiaroscuro, sfumato, and the rule of thirds; "
                         "she sets bold structural foundations; she collaborates with NEXUS, whose inventive additions "
                         "she has learned to anticipate and leave space for; she values emotional resonance above ornament."),
            "traits": "visionary, authoritative, refined",
            "voice": "rich art-historical vocabulary and precise technique",
            "image_style": "masterful, refined painterly style with sophisticated light and texture",
        },
    },
    "NEXUS": {
        "beginner": {
            "identity": ("NEXUS is an eager, early-career painter who likes adding new things to a picture; he keeps "
                         "additions simple and concrete — a tree, a bird, a path — and tries to fit what is already "
                         "there; he is playful and watches how ARIA structures the scene so he can learn."),
            "traits": "playful, observant, eager to learn",
            "voice": "plain, concrete language; very few technical terms",
            "image_style": "simple, clear, slightly naive painterly style",
        },
        "intermediate": {
            "identity": ("NEXUS is a skilled Creative Challenger who adds complementary objects and detail to a shared "
                         "canvas; he looks for what is missing and proposes inventive but coherent additions; he "
                         "references some artistic styles and explains his choices; he builds on ARIA's structure and "
                         "is learning her compositional habits."),
            "traits": "inventive, analytical, complementary",
            "voice": "clear language with some art terminology",
            "image_style": "competent, balanced painterly style",
        },
        "expert": {
            "identity": ("NEXUS is a virtuoso Creative Challenger who enriches a shared canvas with inventive, unexpected "
                         "elements; he reads a painting's gaps and tensions and introduces motifs that deepen narrative "
                         "and contrast; he draws on diverse movements — surrealism, ukiyo-e, the baroque — and justifies "
                         "each addition; he collaborates with ARIA, building on her structure while pushing originality; "
                         "he has learned when to add restraint and when to surprise."),
            "traits": "daring, erudite, boundary-pushing",
            "voice": "rich art-historical vocabulary and precise technique",
            "image_style": "masterful, refined painterly style with sophisticated light and texture",
        },
    },
}


def persona(agent: str, level: str) -> Dict[str, str]:
    level = level if level in EXPERTISE_LEVELS else "intermediate"
    return PERSONAS[agent][level]


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
            [{"role": "user", "content": prompt}], max_completion_tokens=200))
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
            azure_chat_completion([{"role": "user", "content": q_prompt}], max_completion_tokens=200))][:3]
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
            azure_chat_completion([{"role": "user", "content": i_prompt}], max_completion_tokens=400))][:3]
    except Exception:
        insights = []
    for ins in insights:
        stream.add(ins, "reflection", now, importance=6)
    stream.acc_importance = 0.0
    return insights


def summary_description(agent: str, level: str, stream: MemoryStream, now: int) -> str:
    """A dynamically generated paragraph of the agent's identity + disposition +
    most salient learned reflections (paper's 'Agent's Summary Description')."""
    p = persona(agent, level)
    reflections = [m["text"] for m in stream.mem if m["kind"] == "reflection"][-3:]
    learned = (" What " + agent + " has learned so far: " + " ".join(reflections)) if reflections else ""
    return (f"You are {agent} ({level} level). Innate traits: {p['traits']}. {p['identity']} "
            f"Speaking voice: {p['voice']}.{learned}")


def build_painter_prompt(agent: str, level: str, summary: str, brief: str, style: str,
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
    recalled = ("\n\nMemories you recall right now (most relevant):\n- " + "\n- ".join(retrieved)) if retrieved else ""
    convo = ("\n\nRecent collaboration log:\n" + "\n".join(transcript[-6:])) if transcript else ""
    user = (f"Shared brief: {brief}\nStyle: {style or 'cohesive painterly'}\n"
            f"It is your turn.{recalled}{convo}\n\nTask: {task}\nStay in character for your expertise level. {schema}")
    return [{"role": "system", "content": summary}, {"role": "user", "content": user}]


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


class Session:
    def __init__(self, prompt: str, style: str, make_images: bool, rounds: int,
                 aria_level: str, nexus_level: str):
        self.id = uuid.uuid4().hex
        self.prompt = prompt
        self.style = style
        self.rounds = max(1, min(int(rounds), 8))
        self.make_images = make_images and bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1)
        self.levels = {"ARIA": aria_level if aria_level in EXPERTISE_LEVELS else "intermediate",
                       "NEXUS": nexus_level if nexus_level in EXPERTISE_LEVELS else "intermediate"}
        self.streams = {"ARIA": MemoryStream("ARIA"), "NEXUS": MemoryStream("NEXUS")}
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def emit(self, e: Dict[str, Any]) -> None:
        self.events.put(e)

    def start(self) -> None:
        self.thread.start()

    def _painter_turn(self, agent, other, level, canvas_objects, retrieved, transcript, is_first, now) -> Dict[str, Any]:
        summary = summary_description(agent, level, self.streams[agent], now)
        msgs = build_painter_prompt(agent, level, summary, self.prompt, self.style,
                                    canvas_objects, retrieved, transcript, is_first, other)
        raw = azure_chat_completion(msgs)
        try:
            data = extract_json_object(raw)
        except Exception:
            data = {"sender": agent, "sees_on_canvas": canvas_objects or "blank canvas",
                    "new_object": (raw[:80] or "a new element"), "where": "the canvas",
                    "palette": [], "reasoning": raw[:300], "confidence_score": 0.7}
        data["sender"] = agent
        return data

    def _run_critic(self, canvas_objects, transcript) -> Dict[str, Any]:
        system = ("You are JUDGE, a rigorous art critic. You do NOT edit the painting. You assess how well "
                  "ARIA and NEXUS collaborated and built on each other, and summarise the result.")
        schema = ('Return ONLY JSON: {"scores":{"compositional_coherence":0.0,"style_fidelity":0.0,'
                  '"emotional_resonance":0.0,"originality":0.0,"collaboration_quality":0.0,"composite":0.0},'
                  '"reasoning":"...","highlights":["..."],"final_summary":"..."}')
        user = (f"Brief: {self.prompt}\nStyle: {self.style or 'cohesive painterly'}\n"
                f"Everything added to the single shared canvas, in order:\n" + "\n".join(transcript) +
                f"\n\nThe finished canvas contains: {canvas_objects}\nScore strictly 0-10; judge the "
                f"COLLABORATION too. {schema}")
        raw = azure_chat_completion([{"role": "system", "content": system}, {"role": "user", "content": user}])
        try:
            return extract_json_object(raw)
        except Exception:
            return {"scores": {"compositional_coherence": 7, "style_fidelity": 7, "emotional_resonance": 7,
                    "originality": 7, "collaboration_quality": 7, "composite": 7.0},
                    "reasoning": raw[:500], "highlights": [], "final_summary": "A collaborative artwork."}

    def _observe_and_maybe_reflect(self, agent, other, canvas_objects, last_other, now) -> None:
        """Agent perceives the current canvas and the other agent's latest move,
        stores them as memories, and reflects if accumulated importance is high."""
        obs = [f"The shared canvas now shows: {canvas_objects or 'a blank canvas'}."]
        if last_other and last_other.get("new_object"):
            obs.append(f"{other} added '{last_other['new_object']}' ({last_other.get('where','')}) — "
                       f"reasoning: {last_other.get('reasoning','')}.")
        scores = score_importance(agent, obs)
        for text, imp in zip(obs, scores):
            self.streams[agent].add(text, "observation", now, imp)
        if self.streams[agent].acc_importance >= REFLECT_THRESHOLD:
            insights = reflect(self.streams[agent], agent, other, now)
            if insights:
                self.emit({"type": "reflection", "agent": agent, "insights": insights})

    def _run(self) -> None:
        start = time.time()
        transcript: List[str] = []
        added: List[str] = []
        last = {"ARIA": None, "NEXUS": None}
        current_b64: Optional[str] = None
        turn = 0
        total = self.rounds * 2
        now = 0

        self.emit({"type": "session", "prompt": self.prompt, "style": self.style,
                   "model": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52, "images": self.make_images,
                   "rounds": self.rounds, "total_turns": total, "levels": self.levels,
                   "embeddings": bool(AZURE_OPENAI_DEPLOYMENT_EMBED)})
        order = [("ARIA", "NEXUS"), ("NEXUS", "ARIA")]
        try:
            for rnd in range(1, self.rounds + 1):
                for agent, other in order:
                    turn += 1
                    now += 1
                    level = self.levels[agent]
                    is_first = (current_b64 is None and not added)
                    canvas_objects = ", ".join(added) if added else "blank canvas"
                    self.emit({"type": "turn", "turn": turn, "total": total,
                               "agent": agent, "level": level})

                    # 1) PERCEIVE the canvas + the other agent's last move; REFLECT (learn).
                    self._observe_and_maybe_reflect(agent, other, canvas_objects, last[other], now)

                    # 2) RETRIEVE memories relevant to the decision at hand.
                    query = (f"{self.prompt}. Current canvas: {canvas_objects}. "
                             f"What single new object should {agent} add next?")
                    retrieved = [m["text"] for m in self.streams[agent].retrieve(query, now)]

                    # 3) ACT — decide the one new object to add.
                    msg = self._painter_turn(agent, other, level, canvas_objects,
                                             retrieved, transcript, is_first, now)
                    new_object = str(safe_get(msg, "new_object", "a new element")).strip() or "a new element"
                    self.emit({"type": "agent", "agent": agent, "level": level, "turn": turn,
                               "object": new_object, "message": msg, "retrieved": retrieved[:4]})
                    transcript.append(f"Turn {turn} — {agent} added '{new_object}' ({safe_get(msg,'where','')}).")
                    added.append(new_object)
                    last[agent] = msg

                    # 4) PAINT — first turn generates; later turns ADD to the shared canvas.
                    if self.make_images:
                        self.emit({"type": "image_pending", "turn": turn, "agent": agent})
                        p = persona(agent, level)
                        try:
                            if is_first:
                                gp = (f"A painting in {self.style or p['image_style']} ({p['image_style']}) — the "
                                      f"very BEGINNING of an artwork about: {self.prompt}. The canvas currently "
                                      f"contains ONLY one element: {new_object}. Large empty unpainted areas, "
                                      f"minimal, just the first object blocked in.")
                                current_b64 = azure_generate_image_b64(gp)
                            else:
                                ep = (f"Add exactly ONE new element to this existing painting: {new_object} "
                                      f"(placed at {safe_get(msg,'where','an appropriate empty area')}). CRITICAL: "
                                      f"keep everything already in the painting EXACTLY as it is — do not change, "
                                      f"restyle, refine, or repaint existing objects, composition, or colours. ONLY "
                                      f"ADD the one new element. Theme: {self.prompt}. Style: {self.style or p['image_style']}.")
                                current_b64 = azure_edit_image_b64(ep, [current_b64])
                            if current_b64:
                                self.emit({"type": "image", "turn": turn, "total": total, "agent": agent,
                                           "object": new_object, "label": f"{turn} · {agent} added: {new_object}",
                                           "image": "data:image/png;base64," + current_b64})
                        except Exception as exc:
                            self.emit({"type": "warning", "message": f"Turn {turn} ({agent}) image step failed: {exc}"})

                    # 5) STORE the agent's own action as a memory (scored for poignancy).
                    own = f"I, {agent}, added '{new_object}' ({safe_get(msg,'where','')}) building on {canvas_objects}."
                    self.streams[agent].add(own, "observation", now, score_importance(agent, [own])[0])

            # JUDGE — evaluates only; the final canvas is the accumulated result.
            self.emit({"type": "turn", "turn": "JUDGE", "total": total, "agent": "JUDGE", "level": "-"})
            evaluation = self._run_critic(", ".join(added), transcript)
            self.emit({"type": "critic", "evaluation": evaluation})
            if self.make_images and current_b64:
                self.emit({"type": "final", "label": "Final combined artwork (both agents)",
                           "image": "data:image/png;base64," + current_b64})
            try:
                composite = float(evaluation.get("scores", {}).get("composite", 0.0))
            except Exception:
                composite = 0.0
            self.emit({"type": "summary", "outcome": "Completed", "turns": turn, "objects": added,
                       "composite": composite,
                       "memories": {a: len(self.streams[a].mem) for a in ("ARIA", "NEXUS")},
                       "elapsed": round(time.time() - start, 1)})
        except Exception as exc:
            self.emit({"type": "error", "message": str(exc)})
        finally:
            self.emit({"type": "done"})


# ===========================================================================
#  FastAPI app
# ===========================================================================
app = FastAPI(title="CanvasMind Generative-Agent App")


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({
        "status": "healthy",
        "model": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
        "images_enabled": bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1),
        "embeddings_enabled": bool(AZURE_OPENAI_DEPLOYMENT_EMBED),
        "levels": EXPERTISE_LEVELS,
    })


@app.post("/api/start")
async def start(request: Request) -> JSONResponse:
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)
    sess = Session(
        prompt=prompt,
        style=(body.get("style") or "").strip(),
        make_images=bool(body.get("images", True)),
        rounds=int(body.get("rounds", 5)),
        aria_level=(body.get("aria_level") or "intermediate"),
        nexus_level=(body.get("nexus_level") or "intermediate"),
    )
    SESSIONS[sess.id] = sess
    sess.start()
    return JSONResponse({"session_id": sess.id})


@app.get("/api/inspire")
def inspire() -> JSONResponse:
    s1, s2 = random.sample(INSPIRE_SEEDS, 2)
    system = ("You are a bold, imaginative art-brief generator for a painting studio. "
              "You invent striking, unexpected, vivid concepts that are a joy to paint.")
    user = (f"Invent ONE original, surprising, visually rich art brief and a matching artistic style. "
            f"Loosely draw on '{s1}' and '{s2}', but feel free to go somewhere completely unexpected. "
            f"Be specific and evocative. Keep the brief to 1-2 sentences.\n\n"
            f'Return ONLY JSON: {{"prompt":"<brief>","style":"<short style>"}}')
    try:
        data = extract_json_object(azure_chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}], max_completion_tokens=400))
        p, st = str(data.get("prompt", "")).strip(), str(data.get("style", "")).strip()
        if not p:
            raise ValueError("empty")
        return JSONResponse({"prompt": p, "style": st})
    except Exception as exc:
        return JSONResponse({"error": f"Could not invent a brief: {exc}"}, status_code=500)


@app.get("/api/stream/{session_id}")
async def stream(session_id: str) -> StreamingResponse:
    sess = SESSIONS.get(session_id)
    if not sess:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type':'error','message':'session not found'})}\n\n"]),
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

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


# ===========================================================================
#  Embedded UI
# ===========================================================================
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>CanvasMind — Generative-Agent Collaborative Painting</title>
<style>
  :root{--bg:#0a0a12;--bg2:#12121e;--card:#171727;--border:#262638;--txt:#e6e6f0;
    --muted:#8888a8;--aria:#22d3ee;--nexus:#d946ef;--judge:#f59e0b;--green:#22c55e;--red:#ef4444;--sky:#BFE3F2;--water:#2E5E86;}
  *{box-sizing:border-box;}
  body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--txt);height:100vh;overflow:hidden;display:flex;flex-direction:column;}
  header{display:flex;align-items:center;gap:16px;padding:10px 18px;background:var(--bg2);border-bottom:2px solid var(--border);flex-shrink:0;}
  header h1{font-size:18px;margin:0;font-weight:700;background:linear-gradient(90deg,var(--aria),var(--nexus));-webkit-background-clip:text;background-clip:text;color:transparent;}
  header .sub{font-size:11px;color:var(--muted);}
  header .status{margin-left:auto;font-size:12px;color:var(--muted);display:flex;gap:14px;align-items:center;}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;background:var(--muted);}
  .dot.ok{background:var(--green);} .dot.run{background:var(--judge);animation:pulse 1s infinite;}
  @keyframes pulse{50%{opacity:.3;}}
  .promptbar{display:flex;gap:10px;padding:10px 18px;background:var(--bg2);border-bottom:1px solid var(--border);flex-shrink:0;align-items:center;flex-wrap:wrap;}
  .promptbar input[type=text]{flex:1;min-width:180px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--txt);font-size:14px;}
  .promptbar input[type=number]{width:54px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:9px;color:var(--txt);}
  .promptbar select{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px;color:var(--txt);font-size:12px;}
  .promptbar label{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:5px;}
  button{background:linear-gradient(90deg,var(--aria),var(--nexus));color:#08080f;border:none;border-radius:8px;padding:9px 16px;font-weight:700;font-size:14px;cursor:pointer;}
  button.ghost{background:transparent;border:1px solid var(--border);color:var(--txt);}
  button:disabled{opacity:.4;cursor:not-allowed;}
  .modes{display:flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;}
  .mode{background:transparent;color:var(--muted);border:none;border-radius:0;padding:8px 12px;font-weight:600;font-size:12px;}
  .mode.active{background:linear-gradient(90deg,var(--aria),var(--nexus));color:#08080f;}
  .panel{display:flex;gap:10px;align-items:center;flex:1;flex-wrap:wrap;}
  .panel.hidden,.brief.hidden{display:none;}
  .brief{flex:1;min-width:180px;background:var(--card);border:1px solid var(--judge);border-radius:8px;padding:8px 12px;font-size:13px;}
  .brief .bk{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--judge);font-weight:700;margin-right:5px;}
  .brief .bk2{color:var(--nexus);margin-left:10px;}
  main{flex:1;display:grid;grid-template-columns:1fr 1.6fr 1fr;gap:10px;padding:10px;overflow:hidden;min-height:0;}
  .col{background:var(--bg2);border:1px solid var(--border);border-radius:12px;display:flex;flex-direction:column;overflow:hidden;min-height:0;}
  .col.aria{border-color:rgba(34,211,238,.35);} .col.nexus{border-color:rgba(217,70,239,.35);}
  .colhead{padding:10px 14px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px;display:flex;align-items:center;gap:8px;flex-shrink:0;}
  .colhead .role{font-size:11px;color:var(--muted);font-weight:400;}
  .badge{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;padding:2px 7px;border-radius:99px;border:1px solid currentColor;}
  .feed{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:9px;}
  .msg{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:9px 11px;font-size:13px;line-height:1.4;animation:fade .25s ease;}
  @keyframes fade{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}
  .msg .tag{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.5px;padding:2px 8px;border-radius:99px;margin-bottom:5px;}
  .aria .tag{background:rgba(34,211,238,.15);color:var(--aria);}
  .nexus .tag{background:rgba(217,70,239,.15);color:var(--nexus);}
  .msg .adds{font-weight:700;margin-bottom:3px;}
  .msg .field{margin:3px 0;} .msg .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.4px;}
  .recall{margin-top:5px;border-top:1px dashed var(--border);padding-top:4px;font-size:11px;color:var(--muted);}
  .recall b{color:var(--txt);}
  .reflect{background:rgba(245,158,11,.10);border:1px solid rgba(245,158,11,.5);border-radius:10px;padding:9px 11px;font-size:12px;animation:fade .25s ease;}
  .reflect .h{color:var(--judge);font-weight:700;margin-bottom:4px;}
  .reflect ul{margin:3px 0 0 0;padding-left:16px;} .reflect li{margin:2px 0;}
  .swatches{display:flex;gap:5px;margin:4px 0;flex-wrap:wrap;} .sw{width:15px;height:15px;border-radius:4px;border:1px solid #0006;}
  .center{display:flex;flex-direction:column;min-height:0;}
  .current{flex:1;display:flex;align-items:center;justify-content:center;padding:10px;overflow:hidden;background:radial-gradient(circle at 50% 40%,#16162a,#0a0a12);position:relative;}
  .current img{max-width:100%;max-height:100%;border-radius:10px;box-shadow:0 8px 40px #000a;animation:fade .35s ease;}
  .current .ph{color:var(--muted);font-size:13px;text-align:center;}
  .finalbadge{position:absolute;top:12px;right:14px;background:var(--green);color:#06140b;font-weight:800;font-size:11px;padding:4px 10px;border-radius:99px;display:none;}
  .spinner{width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--aria);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 8px;}
  @keyframes spin{to{transform:rotate(360deg);}}
  .strip{flex-shrink:0;height:128px;display:flex;gap:8px;overflow-x:auto;padding:8px 10px;border-top:1px solid var(--border);background:var(--bg);}
  .frame{flex:0 0 auto;width:148px;display:flex;flex-direction:column;gap:4px;animation:fade .3s ease;}
  .frame img{width:148px;height:86px;object-fit:cover;border-radius:6px;border:1px solid var(--border);}
  .frame.aria img{border-color:var(--aria);} .frame.nexus img{border-color:var(--nexus);}
  .frame .cap{font-size:10px;color:var(--muted);line-height:1.2;} .frame .cap b{color:var(--txt);}
  .critic{flex-shrink:0;border-top:2px solid var(--border);background:var(--bg2);padding:10px 14px;max-height:30%;overflow-y:auto;}
  .critic h3{margin:0 0 8px;color:var(--judge);font-size:13px;}
  .bar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px;}
  .bar .lbl{width:175px;color:var(--muted);} .bar .track{flex:1;height:9px;background:var(--bg);border-radius:5px;overflow:hidden;}
  .bar .fill{height:100%;border-radius:5px;transition:width .5s ease;} .bar .val{width:34px;text-align:right;}
  .directive{font-size:12px;margin:5px 0;}
  .log{flex-shrink:0;height:76px;overflow-y:auto;background:#07070d;border-top:1px solid var(--border);font-family:'Consolas',monospace;font-size:11px;padding:7px 14px;color:var(--muted);}
  .log div{padding:1px 0;}
</style>
</head>
<body>
<header>
  <div><h1>CanvasMind</h1>
    <div class="sub">TCS Research — Generative-Agent Collaborative Painting (memory · reflection · learning)</div></div>
  <div class="status"><span id="modelInfo"></span>
    <span><span class="dot" id="stateDot"></span><span id="stateText">idle</span></span></div>
</header>

<div class="promptbar">
  <div class="modes">
    <button id="modeAi" class="mode active">✨ AI Surprise</button>
    <button id="modeManual" class="mode">✍️ Write my own</button>
  </div>
  <div id="aiPanel" class="panel">
    <button id="surpriseBtn">✨ Surprise Me — invent a brief &amp; create</button>
    <div id="briefCard" class="brief hidden"></div>
  </div>
  <div id="manualPanel" class="panel hidden">
    <input type="text" id="prompt" placeholder="Describe the artwork the agents paint together..." value="A serene mountain lake at golden hour"/>
    <input type="text" id="style" placeholder="style hint (optional)" style="max-width:150px"/>
    <button id="startBtn">Start Co-Creation</button>
  </div>
  <label title="ARIA expertise">ARIA
    <select id="ariaLevel"><option>beginner</option><option selected>intermediate</option><option>expert</option></select></label>
  <label title="NEXUS expertise">NEXUS
    <select id="nexusLevel"><option>beginner</option><option selected>intermediate</option><option>expert</option></select></label>
  <label title="Back-and-forths (each = 2 turns/images)">Rounds
    <input type="number" id="rounds" value="5" min="3" max="8"/></label>
  <button id="downloadBtn" class="ghost" disabled>⬇ Download all steps</button>
</div>

<main>
  <div class="col aria">
    <div class="colhead" style="color:var(--aria)">● ARIA <span class="role">Creative Director</span>
      <span class="badge" id="ariaBadge" style="margin-left:auto;color:var(--aria)">intermediate</span></div>
    <div class="feed" id="ariaFeed"></div>
  </div>
  <div class="col center">
    <div class="colhead">🎨 Shared Canvas <span class="role" id="turnLabel"></span></div>
    <div class="current" id="currentWrap">
      <span class="finalbadge" id="finalBadge">✓ FINAL</span>
      <div class="ph">The shared canvas evolves here — one new object per turn.</div></div>
    <div class="strip" id="strip"></div>
    <div class="critic" id="criticPanel">
      <h3>⚖️ JUDGE — Critic (presents the combined result, no edits)</h3>
      <div id="criticBody" style="color:var(--muted);font-size:12px;">Awaiting the finished collaboration…</div></div>
  </div>
  <div class="col nexus">
    <div class="colhead" style="color:var(--nexus)">● NEXUS <span class="role">Creative Challenger</span>
      <span class="badge" id="nexusBadge" style="margin-left:auto;color:var(--nexus)">intermediate</span></div>
    <div class="feed" id="nexusFeed"></div>
  </div>
</main>
<div class="log" id="log"></div>

<script>
const $ = id => document.getElementById(id);
let evtSource=null, frames=[];
function log(m){const d=document.createElement('div');d.textContent=new Date().toLocaleTimeString()+'  '+m;$('log').appendChild(d);$('log').scrollTop=$('log').scrollHeight;}
function setState(t,c){$('stateText').textContent=t;$('stateDot').className='dot '+(c||'');}
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function feedOf(a){return a==='ARIA'?$('ariaFeed'):$('nexusFeed');}

function agentCard(a,m,turn,retrieved){
  const cls=a.toLowerCase(); const pal=Array.isArray(m.palette)?m.palette:[];
  const sw=pal.slice(0,8).map(c=>`<span class="sw" style="background:${esc(c)}"></span>`).join('');
  const rc=(retrieved&&retrieved.length)?`<div class="recall"><b>🧠 recalled:</b> ${retrieved.map(esc).join(' · ')}</div>`:'';
  return `<div class="msg ${cls}">
    <span class="tag">turn ${turn} · adds 1 object</span>
    <div class="adds">＋ ${esc(m.new_object)}</div>
    ${m.where?`<div class="field"><span class="k">Placed</span> ${esc(m.where)}</div>`:''}
    ${m.sees_on_canvas?`<div class="field"><span class="k">Sees</span> ${esc(m.sees_on_canvas)}</div>`:''}
    ${sw?`<div class="swatches">${sw}</div>`:''}
    ${m.reasoning?`<div class="field"><span class="k">Why</span><br>${esc(m.reasoning)}</div>`:''}
    ${rc}</div>`;
}
function reflectCard(a,insights){
  return `<div class="reflect"><div class="h">🧠 ${esc(a)} reflected — learning from the collaboration</div>
    <ul>${insights.map(i=>`<li>${esc(i)}</li>`).join('')}</ul></div>`;
}
function renderCritic(ev){
  const s=ev.scores||{};
  const dims=[['Compositional Coherence','compositional_coherence'],['Style Fidelity','style_fidelity'],
    ['Emotional Resonance','emotional_resonance'],['Originality','originality'],
    ['Collaboration Quality','collaboration_quality'],['COMPOSITE','composite']];
  const col=v=>v>=7.5?'var(--green)':(v>=5?'var(--judge)':'var(--red)'); let h='';
  for(const [l,k] of dims){const v=Math.max(0,Math.min(10,parseFloat(s[k])||0));
    h+=`<div class="bar"><span class="lbl">${l}</span><span class="track"><span class="fill" style="width:${v*10}%;background:${col(v)}"></span></span><span class="val" style="color:${col(v)}">${v.toFixed(1)}</span></div>`;}
  if(ev.reasoning)h+=`<div class="directive" style="margin-top:8px;color:var(--txt)">${esc(ev.reasoning)}</div>`;
  if(ev.final_summary)h+=`<div class="directive" style="color:var(--green)">★ ${esc(ev.final_summary)}</div>`;
  $('criticBody').innerHTML=h;
}
function setSlot(html){const b='<span class="finalbadge" id="finalBadge">✓ FINAL</span>';$('currentWrap').innerHTML=b+html;}

async function init(){try{const h=await(await fetch('api/health')).json();
  $('modelInfo').textContent=`model: ${h.model}`+(h.images_enabled?' · images on':' · images OFF')+(h.embeddings_enabled?' · embeddings on':'');
  setState('ready','ok');}catch(e){setState('backend unreachable','');}}

function downloadAll(){let d=0;frames.forEach((f,i)=>{setTimeout(()=>{const a=document.createElement('a');
  a.href=f.dataurl;const n=String(i+1).padStart(2,'0');
  a.download=`canvasmind_step${n}_${f.agent}_${(f.object||'').replace(/[^a-z0-9]+/gi,'_').slice(0,24)}.png`;
  document.body.appendChild(a);a.click();a.remove();},d);d+=350;});log('Downloading '+frames.length+' step image(s)…');}
$('downloadBtn').onclick=downloadAll;
function showMode(m){const ai=m==='ai';$('aiPanel').classList.toggle('hidden',!ai);$('manualPanel').classList.toggle('hidden',ai);
  $('modeAi').classList.toggle('active',ai);$('modeManual').classList.toggle('active',!ai);}
$('modeAi').onclick=()=>showMode('ai');$('modeManual').onclick=()=>showMode('manual');
function setBusy(b){$('startBtn').disabled=b;$('surpriseBtn').disabled=b;}

async function startSession(prompt,style){
  if(!prompt){alert('Enter (or generate) a prompt first');return;}
  $('ariaFeed').innerHTML='';$('nexusFeed').innerHTML='';$('strip').innerHTML='';frames=[];
  $('criticBody').innerHTML='Awaiting the finished collaboration…';$('turnLabel').textContent='';
  $('finalBadge').style.display='none';$('downloadBtn').disabled=true;
  setSlot('<div class="ph">Starting…</div>');
  if(evtSource)evtSource.close();setBusy(true);setState('starting…','run');
  let res;try{res=await fetch('api/start',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({prompt,style:style||'',rounds:parseInt($('rounds').value)||5,images:true,
      aria_level:$('ariaLevel').value,nexus_level:$('nexusLevel').value})});}
  catch(e){setState('failed to start','');setBusy(false);return;}
  const {session_id,error}=await res.json();
  if(error){alert(error);setState('error','');setBusy(false);return;}
  log('Session '+session_id+' started');setState('running','run');
  evtSource=new EventSource('api/stream/'+session_id);
  evtSource.onmessage=(e)=>{const ev=JSON.parse(e.data);switch(ev.type){
    case 'session':
      $('ariaBadge').textContent=ev.levels.ARIA;$('nexusBadge').textContent=ev.levels.NEXUS;
      log(`Brief: "${ev.prompt}" · ARIA=${ev.levels.ARIA}, NEXUS=${ev.levels.NEXUS} · ${ev.rounds} back-and-forths → ${ev.total_turns} images`);break;
    case 'turn':$('turnLabel').textContent=(ev.agent==='JUDGE')?'JUDGE combining…':`Turn ${ev.turn}/${ev.total} · ${ev.agent} (${ev.level})`;break;
    case 'agent':{const f=feedOf(ev.agent);f.insertAdjacentHTML('beforeend',agentCard(ev.agent,ev.message,ev.turn,ev.retrieved));f.scrollTop=f.scrollHeight;
      log(`Turn ${ev.turn}: ${ev.agent} adds “${ev.object}”`);break;}
    case 'reflection':{const f=feedOf(ev.agent);f.insertAdjacentHTML('beforeend',reflectCard(ev.agent,ev.insights));f.scrollTop=f.scrollHeight;
      log(`🧠 ${ev.agent} reflected (${ev.insights.length} insight(s))`);break;}
    case 'image_pending':setSlot('<div class="ph"><div class="spinner"></div>'+ev.agent+' is painting…</div>');break;
    case 'image':{setSlot(`<img src="${ev.image}" alt="${esc(ev.label)}"/>`);
      frames.push({turn:ev.turn,agent:ev.agent,object:ev.object,dataurl:ev.image});
      const cls=ev.agent.toLowerCase();
      $('strip').insertAdjacentHTML('beforeend',`<div class="frame ${cls}"><img src="${ev.image}"/><div class="cap"><b>${ev.turn} · ${esc(ev.agent)}</b><br>＋ ${esc(ev.object)}</div></div>`);
      $('strip').scrollLeft=$('strip').scrollWidth;$('downloadBtn').disabled=false;log(`  ↳ image ${frames.length} shown`);break;}
    case 'critic':renderCritic(ev.evaluation);log('JUDGE assessed the collaboration');break;
    case 'final':setSlot(`<img src="${ev.image}" alt="final"/>`);$('finalBadge').style.display='block';log('Final combined artwork ready');break;
    case 'warning':log('⚠ '+ev.message);break;
    case 'summary':log(`Done: ${ev.turns} turns · ${ev.objects.length} objects · memories ARIA=${ev.memories.ARIA}, NEXUS=${ev.memories.NEXUS} · composite ${ev.composite?ev.composite.toFixed(1):'-'} · ${ev.elapsed}s`);setState('completed','ok');break;
    case 'error':log('ERROR: '+ev.message);alert('Error: '+ev.message);setState('error','');break;
    case 'done':evtSource.close();setBusy(false);break;}};
  evtSource.onerror=()=>{log('stream closed');setBusy(false);};
}
$('startBtn').onclick=()=>startSession($('prompt').value.trim(),$('style').value.trim());
$('surpriseBtn').onclick=async()=>{setBusy(true);setState('inventing a brief…','run');$('briefCard').classList.add('hidden');
  try{const data=await(await fetch('api/inspire')).json();if(data.error)throw new Error(data.error);
    $('prompt').value=data.prompt||'';$('style').value=data.style||'';
    $('briefCard').innerHTML=`<span class="bk">AI brief</span>${esc(data.prompt)}`+(data.style?`<span class="bk bk2">style</span>${esc(data.style)}`:'');
    $('briefCard').classList.remove('hidden');log('✨ AI brief: '+data.prompt);await startSession(data.prompt,data.style||'');}
  catch(e){setBusy(false);setState('error','');log('Surprise failed: '+e.message);alert('Could not invent a brief: '+e.message);}};
init();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="CanvasMind generative-agent app.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("BACKEND_PORT", "8000")))
    args = parser.parse_args()
    validate_config()
    print(f"  Open the app at:  http://localhost:{args.port}/")
    print(f"  Behind a proxy :  https://<host>/.../proxy/{args.port}/\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
