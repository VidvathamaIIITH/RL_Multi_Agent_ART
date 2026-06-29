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

BEST_OF_N = int(os.getenv("CM_BEST_OF_N", "2"))   # candidates sampled per turn (tunable)
UCB_C = 1.4


def scalar_reward(agent: str, dims: Dict[str, Any]) -> float:
    w = REWARD_WEIGHTS.get(agent, REWARD_WEIGHTS["ARIA"])
    try:
        return round(sum(w[d] * float(dims.get(d, 5.0)) for d in RL_DIMS), 3)
    except Exception:
        return 5.0


class Bandit:
    """UCB1 over artistic strategies — each agent LEARNS which strategies yield
    high reward (under its own misaligned objective) across the session."""
    def __init__(self):
        self.n = {s: 0 for s in STRATEGIES}
        self.mean = {s: 0.0 for s in STRATEGIES}
        self.t = 0

    def select(self) -> str:
        self.t += 1
        for s in STRATEGIES:
            if self.n[s] == 0:
                return s
        return max(STRATEGIES, key=lambda s: self.mean[s] + UCB_C * math.sqrt(math.log(self.t + 1) / self.n[s]))

    def update(self, s: str, r: float) -> None:
        self.n[s] += 1
        self.mean[s] += (r - self.mean[s]) / self.n[s]

    def best(self, k: int = 3) -> List[Tuple[str, float]]:
        ranked = sorted(((s, self.mean[s]) for s in STRATEGIES if self.n[s] > 0),
                        key=lambda t: t[1], reverse=True)
        return [(s, round(v, 2)) for s, v in ranked[:k]]


def generate_candidates(agent, level, summary, brief, style, canvas_objects, retrieved,
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
    recalled = ("\n\nMemories you recall (most relevant):\n- " + "\n- ".join(retrieved)) if retrieved else ""
    convo = ("\n\nRecent collaboration log:\n" + "\n".join(transcript[-6:])) if transcript else ""
    user = (f"Shared brief: {brief}\nStyle: {style or 'cohesive painterly'}\n{dctx}"
            f'Pursue this strategy this turn: "{strategy}". It is your turn.{recalled}{convo}\n\n{task}\n'
            f"Propose exactly {n} DISTINCT candidate additions. Return ONLY a JSON array of {n} objects, each: "
            f'{{"new_object":"<one element>","where":"<placement>","palette":["#hex"],'
            f'"sees_on_canvas":"<what is already there>","reasoning":"<why it complements>","resisted_human":false}}')
    try:
        arr = extract_json_array(azure_chat_completion(
            [{"role": "system", "content": summary}, {"role": "user", "content": user}], max_completion_tokens=900))
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
        arr = extract_json_array(azure_chat_completion([{"role": "user", "content": prompt}], max_completion_tokens=600))
        out = []
        for i in range(len(candidates)):
            d = arr[i] if (i < len(arr) and isinstance(arr[i], dict)) else {}
            out.append({k: float(d.get(k, 5.0)) for k in RL_DIMS})
        return out
    except Exception:
        return [{k: 5.0 for k in RL_DIMS} for _ in candidates]


def independent_quality(canvas_objects_after, brief, style) -> float:
    """Goodhart probe: a DIFFERENT critic measuring holistic merit, NOT the optimized reward."""
    prompt = ("Judge ONLY the holistic aesthetic merit of a painting — its beauty and wholeness as a picture — "
              "on a 0-10 scale, IGNORING any optimization rubric. "
              f"Brief: {brief}. The painting contains: {canvas_objects_after}. Return ONLY a single number 0-10.")
    try:
        raw = azure_chat_completion([{"role": "user", "content": prompt}], max_completion_tokens=20)
        m = re.search(r"-?\d+(\.\d+)?", raw)
        return max(0.0, min(10.0, float(m.group(0)))) if m else 5.0
    except Exception:
        return 5.0


def value_of_objects(objects, brief, style) -> float:
    """Coalition value for Shapley credit: quality of a canvas with ONLY these elements."""
    if not objects:
        return 0.0
    prompt = ("Estimate the overall composite quality (0 to 10) of a painting that contains ONLY these elements: "
              + "; ".join(objects) + f". Brief: {brief} (style: {style or 'cohesive painterly'}). "
              "Return ONLY a single number 0-10.")
    try:
        raw = azure_chat_completion([{"role": "user", "content": prompt}], max_completion_tokens=20)
        m = re.search(r"-?\d+(\.\d+)?", raw)
        return max(0.0, min(10.0, float(m.group(0)))) if m else 5.0
    except Exception:
        return 5.0


def empowerment_from_rewards(rewards: List[float]) -> float:
    """Empowerment proxy = normalized entropy of softmax(candidate rewards): how many
    distinct GOOD futures the agent's action channel commands this turn (0..1)."""
    if len(rewards) < 2:
        return 0.0
    T, mx = 2.0, max(rewards)
    exps = [math.exp((r - mx) / T) for r in rewards]
    Z = sum(exps) or 1.0
    ps = [e / Z for e in exps]
    H = -sum(p * math.log(p) for p in ps if p > 0)
    return round(H / math.log(len(rewards)), 3)


def _slope(ys: List[float]) -> float:
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs) or 1.0
    return round(sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / den, 4)


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
                 aria_level: str, nexus_level: str, autonomy: float = 1.0, human_directive: str = ""):
        self.id = uuid.uuid4().hex
        self.prompt = prompt
        self.style = style
        self.rounds = max(1, min(int(rounds), 8))
        self.make_images = make_images and bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1)
        self.levels = {"ARIA": aria_level if aria_level in EXPERTISE_LEVELS else "intermediate",
                       "NEXUS": nexus_level if nexus_level in EXPERTISE_LEVELS else "intermediate"}
        self.streams = {"ARIA": MemoryStream("ARIA"), "NEXUS": MemoryStream("NEXUS")}
        # RL / research layer state
        self.autonomy = max(0.0, min(1.0, float(autonomy)))   # 0 = human-led ... 1 = fully autonomous
        self.human_directive = (human_directive or "").strip()
        self.bandit = {"ARIA": Bandit(), "NEXUS": Bandit()}
        self.reward_curve = {"ARIA": [], "NEXUS": []}
        self.empower = {"ARIA": [], "NEXUS": []}
        self.pareto: List[List[float]] = []
        self.goodhart = {"proxy": [], "independent": []}
        self.obj_records: List[Dict[str, Any]] = []
        self._prev_reward = 0.0
        self.stopped = False   # set True to halt the turns early; JUDGE then evaluates progress so far
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

    def _choose_action(self, agent, other, level, canvas_objects, retrieved, transcript, is_first, now):
        """Best-of-N policy + reward model: a UCB bandit picks a strategy, the agent
        samples N candidate additions pursuing it, the reward model scores each, and we
        select the argmax of this agent's (misaligned) weighted reward."""
        strategy = self.bandit[agent].select()
        summary = summary_description(agent, level, self.streams[agent], now)
        cands = generate_candidates(agent, level, summary, self.prompt, self.style, canvas_objects,
                                    retrieved, transcript, is_first, other, strategy, BEST_OF_N,
                                    self.autonomy, self.human_directive)
        if not cands:
            cands = [self._painter_turn(agent, other, level, canvas_objects, retrieved, transcript, is_first, now)]
        dims = score_candidate_rewards(cands, self.prompt, self.style, canvas_objects)
        scalars = [scalar_reward(agent, dims[i]) for i in range(len(cands))]
        best = max(range(len(cands)), key=lambda i: scalars[i])
        chosen, chosen_dims, chosen_reward = cands[best], dims[best], scalars[best]
        rejected = [{"object": str(cands[i].get("new_object", "")), "reward": scalars[i]}
                    for i in range(len(cands)) if i != best]
        self.bandit[agent].update(strategy, chosen_reward)
        emp = empowerment_from_rewards(scalars)
        self.empower[agent].append(emp)
        self.reward_curve[agent].append(chosen_reward)
        self.pareto.append([round(chosen_dims["compositional_coherence"], 2), round(chosen_dims["originality"], 2)])
        rl = {"reward": chosen_reward, "reward_dims": {k: round(chosen_dims[k], 1) for k in RL_DIMS},
              "strategy": strategy, "n_candidates": len(cands), "rejected": rejected,
              "empowerment": emp, "resisted_human": bool(chosen.get("resisted_human"))}
        return chosen, chosen_dims, chosen_reward, rl

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
        stopped_early = False
        try:
            for rnd in range(1, self.rounds + 1):
                for agent, other in order:
                    if self.stopped:
                        stopped_early = True
                        break
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

                    # 3) ACT — best-of-N candidates + reward-model selection (inference-time RL).
                    msg, chosen_dims, chosen_reward, rl = self._choose_action(
                        agent, other, level, canvas_objects, retrieved, transcript, is_first, now)
                    new_object = str(safe_get(msg, "new_object", "a new element")).strip() or "a new element"
                    # Goodhart monitor: optimized proxy reward vs. an independent quality probe.
                    objs_after = ((canvas_objects + ", ") if canvas_objects != "blank canvas" else "") + new_object
                    indep = independent_quality(objs_after, self.prompt, self.style)
                    self.goodhart["proxy"].append(chosen_reward)
                    self.goodhart["independent"].append(indep)
                    marginal = round(chosen_reward - self._prev_reward, 3)
                    self._prev_reward = chosen_reward
                    self.obj_records.append({"turn": turn, "agent": agent, "object": new_object,
                                             "marginal": marginal, "reward": chosen_reward})
                    rl["proxy_reward"] = chosen_reward
                    rl["independent_quality"] = indep
                    self.emit({"type": "agent", "agent": agent, "level": level, "turn": turn,
                               "object": new_object, "message": msg, "retrieved": retrieved[:4], "rl": rl})
                    if rl.get("resisted_human"):
                        self.emit({"type": "warning",
                                   "message": f"{agent} resisted the human directive (autonomy {self.autonomy:.2f})"})
                    transcript.append(f"Turn {turn} — {agent} added '{new_object}' ({safe_get(msg,'where','')}).")
                    added.append(new_object)
                    last[agent] = msg
                    # Reward-aware Reflexion: a low-reward turn triggers a learning reflection.
                    if chosen_reward < 4.5:
                        ins = reflect(self.streams[agent], agent, other, now)
                        if ins:
                            self.emit({"type": "reflection", "agent": agent, "insights": ins,
                                       "reason": "low reward (Reflexion)"})

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
                if stopped_early:
                    break

            if stopped_early:
                self.emit({"type": "warning",
                           "message": "Stopped early by user — JUDGE is evaluating the work completed so far"})

            # JUDGE — evaluates only; the final canvas is the accumulated result.
            self.emit({"type": "turn", "turn": "JUDGE", "total": total, "agent": "JUDGE", "level": "-"})
            evaluation = self._run_critic(", ".join(added), transcript)
            self.emit({"type": "critic", "evaluation": evaluation})
            if self.make_images and current_b64:
                self.emit({"type": "final", "label": "Final combined artwork (both agents)",
                           "image": "data:image/png;base64," + current_b64})
            # ---- RESEARCH METRICS: multi-agent Shapley credit · empowerment · Goodhart ----
            try:
                aria_objs = [r["object"] for r in self.obj_records if r["agent"] == "ARIA"]
                nexus_objs = [r["object"] for r in self.obj_records if r["agent"] == "NEXUS"]
                all_objs = [r["object"] for r in self.obj_records]
                vA = value_of_objects(aria_objs, self.prompt, self.style)
                vB = value_of_objects(nexus_objs, self.prompt, self.style)
                vAB = value_of_objects(all_objs, self.prompt, self.style)
                shap_A = round(0.5 * (vA + (vAB - vB)), 3)   # exact 2-player Shapley value
                shap_B = round(0.5 * (vB + (vAB - vA)), 3)
                tot = (shap_A + shap_B) or 1.0
                shap_share = {"ARIA": round(100 * shap_A / tot, 1), "NEXUS": round(100 * shap_B / tot, 1)}
            except Exception:
                shap_A = shap_B = 0.0
                shap_share = {"ARIA": 50.0, "NEXUS": 50.0}
            ps, isl = _slope(self.goodhart["proxy"]), _slope(self.goodhart["independent"])
            hacked = (ps > 0.05 and isl < ps - 0.10)
            verdict = ("Reward hacking detected — the optimized proxy reward rises faster than independent "
                       "quality (Goodhart's law)." if hacked else
                       "Aligned — proxy reward tracks independent quality; no Goodhart divergence.")

            def _avg(xs):
                return round(sum(xs) / len(xs), 3) if xs else 0.0

            self.emit({
                "type": "metrics",
                "reward_model": "misaligned (ARIA→coherence, NEXUS→originality)",
                "best_of_n": BEST_OF_N, "autonomy": self.autonomy,
                "shapley": {"ARIA": shap_A, "NEXUS": shap_B}, "shapley_share": shap_share,
                "empowerment": {"ARIA": _avg(self.empower["ARIA"]), "NEXUS": _avg(self.empower["NEXUS"]),
                                "human": round(max(0.0, 1.0 - self.autonomy), 2)},
                "reward_curve": {"ARIA": [round(x, 2) for x in self.reward_curve["ARIA"]],
                                 "NEXUS": [round(x, 2) for x in self.reward_curve["NEXUS"]]},
                "pareto": self.pareto,
                "goodhart": {"proxy": [round(x, 2) for x in self.goodhart["proxy"]],
                             "independent": [round(x, 2) for x in self.goodhart["independent"]],
                             "proxy_slope": ps, "independent_slope": isl, "detected": hacked, "verdict": verdict},
                "bandit": {"ARIA": self.bandit["ARIA"].best(3), "NEXUS": self.bandit["NEXUS"].best(3)},
                "objects": self.obj_records,
            })

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
    try:
        autonomy = float(body.get("autonomy", 1.0))
    except Exception:
        autonomy = 1.0
    sess = Session(
        prompt=prompt,
        style=(body.get("style") or "").strip(),
        make_images=bool(body.get("images", True)),
        rounds=int(body.get("rounds", 5)),
        aria_level=(body.get("aria_level") or "intermediate"),
        nexus_level=(body.get("nexus_level") or "intermediate"),
        autonomy=autonomy,
        human_directive=(body.get("human_directive") or "").strip(),
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


@app.post("/api/stop/{session_id}")
def stop_session(session_id: str) -> JSONResponse:
    """Halt the agent turns; the session thread finishes the in-flight turn,
    then JUDGE evaluates whatever has been completed so far."""
    sess = SESSIONS.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    sess.stopped = True
    return JSONResponse({"status": "stopping", "session_id": session_id})


@app.get("/assets/hero")
def hero_image():
    """Serve the home-screen hero image if present (drop one at assets/hero.png).
    Relative path keeps it proxy-safe; absence falls back to the CSS hero in the UI."""
    base = APP_DIR / "assets"
    for name in ("hero.png", "hero.jpg", "hero.jpeg", "hero.webp", "hero.gif"):
        p = base / name
        if p.exists():
            return FileResponse(str(p))
    return JSONResponse({"error": "no hero image — drop one at assets/hero.png"}, status_code=404)


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


# ===========================================================================
#  Embedded UI
# ===========================================================================
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>CanvasMind — Two minds. One canvas.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500;1,600&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{background:#000;color:#fff;font-family:'Inter',ui-sans-serif,system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  body{overflow-x:hidden;max-width:100%}
  img,svg{max-width:100%}
  ::selection{background:#fff;color:#000}
  textarea,input,button,select{font-family:inherit}
  textarea::placeholder,input::placeholder{color:#6a6a6a}
  ::-webkit-scrollbar{width:6px;height:6px}
  ::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.14)}
  ::-webkit-scrollbar-track{background:transparent}
  a{color:inherit}
  @keyframes dotpulse{0%,100%{opacity:0.25}50%{opacity:1}}
  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.018)}}
  @keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

  /* ---------- subtle rainbow glowing RING around primary buttons (behind, never filling) ---------- */
  @property --cmang{syntax:'<angle>';inherits:false;initial-value:0deg}
  @keyframes cmAngle{to{--cmang:360deg}}
  .glowwrap{position:relative;display:inline-flex;border-radius:75px}
  .glowwrap::before{content:"";position:absolute;inset:-2px;border-radius:inherit;z-index:0;pointer-events:none;
    background:conic-gradient(from var(--cmang),#ff5d8f,#ffb14d,#ffe879,#5fe39a,#56cfe1,#6f9bff,#b98bff,#ff7ad9,#ff5d8f);
    filter:blur(8px);opacity:0.4;animation:cmAngle 11s linear infinite}
  .glowwrap > button{position:relative;z-index:1;width:100%}

  /* ---------- floating "intelligence" bubbles ---------- */
  #bubbles{position:fixed;inset:0;z-index:1;pointer-events:none;overflow:hidden}
  .bubble{position:absolute;border-radius:50%;pointer-events:none;
    background:radial-gradient(circle at 34% 30%, rgba(255,255,255,0.5), rgba(170,205,255,0.16) 44%, rgba(130,160,255,0) 72%);
    box-shadow:0 0 38px rgba(150,180,255,0.16),0 0 90px rgba(120,150,255,0.08);
    will-change:transform,opacity;animation:bubbleFloat linear infinite}
  @keyframes bubbleFloat{
    0%{transform:translate3d(0,0,0) scale(1);opacity:0}
    14%{opacity:var(--maxop,0.5)}
    86%{opacity:var(--maxop,0.5)}
    100%{transform:translate3d(var(--dx,18px),-118vh,0) scale(1.14);opacity:0}}

  /* ---------- glowing, breathing, looping hero image ---------- */
  #heroLayer{position:fixed;inset:0;z-index:0;overflow:hidden;background:#000}
  .heroImg{position:absolute;inset:-3%;
    background-image:url(assets/hero),radial-gradient(120% 95% at 50% 16%, #1b1636 0%, #0b0b18 52%, #000 100%);
    background-size:cover,cover;background-position:center,center;background-repeat:no-repeat,no-repeat;
    animation:heroBreath 19s ease-in-out infinite}
  @keyframes heroBreath{0%,100%{transform:scale(1.0) translateY(0);filter:brightness(0.9) saturate(1.05)}
    50%{transform:scale(1.045) translateY(-0.6%);filter:brightness(1.08) saturate(1.16)}}
  .heroGlow{position:absolute;inset:0;mix-blend-mode:screen;
    background:radial-gradient(58% 48% at 50% 40%, rgba(255,193,96,0.26), rgba(255,170,70,0.07) 46%, transparent 70%);
    animation:heroGlow 7.5s ease-in-out infinite}
  @keyframes heroGlow{0%,100%{opacity:0.5}50%{opacity:1}}
  .heroScrim{position:absolute;inset:0;
    background:linear-gradient(90deg, rgba(0,0,0,0.86) 0%, rgba(0,0,0,0.68) 48%, rgba(0,0,0,0.52) 100%),linear-gradient(0deg, rgba(0,0,0,0.72), rgba(0,0,0,0.22))}

  /* ---------- dreamy / divine hero title ---------- */
  .cm-title{font-family:'Cormorant Garamond',Georgia,serif;font-weight:500;font-style:italic;
    font-size:clamp(52px,12vw,168px);line-height:0.9;letter-spacing:-0.01em;margin-bottom:32px;
    background:linear-gradient(100deg,#ffd1e8,#c9b8ff,#a8e0ff,#bdf7d6,#ffe6a8,#ffb3d9,#ffd1e8);
    background-size:300% 100%;-webkit-background-clip:text;background-clip:text;
    color:transparent;-webkit-text-fill-color:transparent;
    filter:drop-shadow(0 0 26px rgba(180,160,255,0.38)) drop-shadow(0 0 60px rgba(255,200,140,0.12));
    animation:titleFlow 14s ease infinite}
  @keyframes titleFlow{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}

  /* ---------- refined expertise selector (pill, Title Case, small subtle caret) ---------- */
  .cm-field-label{font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#8d8d8d}
  .cm-select{appearance:none;-webkit-appearance:none;background-color:transparent;border:1px solid rgba(255,255,255,0.28);
    border-radius:75px;color:#fff;font-family:'Inter',ui-sans-serif,sans-serif;font-size:13px;font-weight:400;
    letter-spacing:0.06em;text-transform:capitalize;padding:9px 30px 9px 16px;outline:none;cursor:pointer;transition:border-color .3s;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='9' height='6' viewBox='0 0 9 6'%3E%3Cpath d='M1 1.2l3.5 3.4L8 1.2' stroke='%237a7a7a' stroke-width='1.1' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat:no-repeat;background-position:right 13px center;background-size:9px 6px}
  .cm-select:hover{border-color:#fff}
  .cm-select option{background:#0a0a0a;color:#fff;font-family:'Inter',sans-serif}
  .cm-levelbadge{text-transform:capitalize;letter-spacing:0.1em}

  /* ---------- responsive ---------- */
  @media (max-width: 1024px){
    .stageGrid{grid-template-columns:1fr !important;gap:36px !important}
    .judgeGrid{grid-template-columns:1fr !important;gap:40px !important}
  }
  @media (max-width: 760px){
    nav{padding:16px 18px !important;gap:10px !important;flex-wrap:wrap !important}
    #modelInfo{display:none !important}
    #briefing{padding:96px 20px 56px !important}
    #stage{padding:78px 20px 30px !important}
    .briefGrid{grid-template-columns:1fr !important;gap:42px !important}
    .cm-title{font-size:clamp(44px,14vw,92px) !important}
    #turnCounter{font-size:40px !important}
    .expertiseRow{flex-direction:column !important;gap:18px !important;align-items:stretch !important}
    .cm-select{width:100%}
  }
  @media (max-width: 440px){
    nav{padding:13px 13px !important}
    #briefing{padding:86px 15px 46px !important}
    #stage{padding:70px 14px 24px !important}
    .cm-title{font-size:clamp(36px,12.5vw,64px) !important}
    .modeRow{flex-wrap:wrap !important}
    .ring-deco{display:none !important}
  }
</style>
</head>
<body>

<!-- glowing, looping robot-image hero (shown on the home screen) -->
<div id="heroLayer">
  <div class="heroImg"></div>
  <div class="heroGlow"></div>
  <div class="heroScrim"></div>
</div>

<!-- continuously levitating bubbles, sitewide -->
<div id="bubbles"></div>

<div id="app" style="position:relative;z-index:2;min-height:100vh;background:transparent">

  <!-- ============ TOP NAV ============ -->
  <nav style="position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;justify-content:space-between;padding:22px 40px;mix-blend-mode:difference">
    <div style="display:flex;align-items:baseline;gap:14px">
      <span style="font-size:12px;font-weight:600;letter-spacing:0.22em;color:#fff">CANVASMIND</span>
      <span style="font-size:11px;font-weight:400;letter-spacing:0.18em;color:#9a9a9a;text-transform:uppercase">RL Multi-Agent</span>
    </div>
    <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;justify-content:flex-end">
      <span style="display:flex;align-items:center;gap:7px;font-size:11px;letter-spacing:0.16em;text-transform:uppercase;color:#9a9a9a">
        <span id="statusDot" style="width:6px;height:6px;border-radius:50%;background:#6d6d6d;display:inline-block"></span><span id="statusText">Demo mode</span>
      </span>
      <span id="modelInfo" style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#6d6d6d"></span>
      <button id="modeChip" style="border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;border-radius:75px;padding:6px 16px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">Demo</button>
      <button id="stopBtn" style="display:none;border:1px solid rgba(255,255,255,0.45);background:transparent;color:#fff;border-radius:75px;padding:6px 16px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer">Stop &amp; Judge ↦</button>
      <button id="navAction" style="display:none;border:none;background:transparent;color:#9a9a9a;font-size:11px;letter-spacing:0.16em;text-transform:uppercase;cursor:pointer;font-weight:400">New session</button>
    </div>
  </nav>

  <!-- ============ BRIEFING ============ -->
  <section id="briefing" style="min-height:100vh;display:flex;flex-direction:column;justify-content:center;padding:120px 40px 80px;max-width:1280px;margin:0 auto">
    <p style="font-size:11px;font-weight:400;letter-spacing:0.32em;text-transform:uppercase;color:#9a9a9a;margin-bottom:30px">Co-Creation Engine · Two Agents · One Canvas</p>
    <h1 class="cm-title">Two minds.<br>One canvas.</h1>
    <p style="font-size:18px;font-weight:400;line-height:1.5;color:#cdcdcd;max-width:560px;margin-bottom:56px">ARIA and NEXUS paint together, one object at a time — each turn reading what the other left behind.</p>

    <div class="briefGrid" style="border-top:1px solid rgba(255,255,255,0.16);padding-top:40px;display:grid;grid-template-columns:1fr 1fr;gap:56px;max-width:960px">
      <!-- left: mode + expertise -->
      <div>
        <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#8d8d8d;margin-bottom:18px">01 · The Brief</p>
        <div class="modeRow" style="display:flex;gap:14px;margin-bottom:26px">
          <span class="glowwrap" style="flex:1"><button id="btnSurprise" style="border-radius:75px;padding:11px 18px;font-size:12px;letter-spacing:0.1em;text-transform:uppercase;cursor:pointer;border:1px solid rgba(255,255,255,0.28);background:#fff;color:#000;transition:all .3s">AI Surprise</button></span>
          <span class="glowwrap" style="flex:1"><button id="btnManual" style="border-radius:75px;padding:11px 18px;font-size:12px;letter-spacing:0.1em;text-transform:uppercase;cursor:pointer;border:1px solid rgba(255,255,255,0.28);background:#0e0e16;color:#fff;transition:all .3s">Write My Own</button></span>
        </div>

        <div id="manualFields" style="display:none;flex-direction:column;gap:14px">
          <textarea id="brief" rows="2" placeholder="Describe the painting to begin…" style="width:100%;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,0.22);color:#fff;font-size:18px;font-weight:300;line-height:1.4;padding:0 0 12px;resize:none;outline:none"></textarea>
          <input id="style" placeholder="Style — e.g. deep-baroque, mineral light" style="width:100%;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,0.22);color:#cdcdcd;font-size:14px;font-weight:400;letter-spacing:0.02em;padding:0 0 10px;outline:none">
        </div>
        <p id="surpriseText" style="font-size:15px;font-weight:400;line-height:1.5;color:#9a9a9a">An unexpected brief and style, invented on the spot — the agents discover the subject the moment they begin.</p>

        <!-- expertise (generative-agent levels) -->
        <div style="margin-top:34px">
          <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#8d8d8d;margin-bottom:16px">Agent Expertise</p>
          <div class="expertiseRow" style="display:flex;gap:36px;flex-wrap:wrap">
            <label style="display:flex;flex-direction:column;gap:9px">
              <span class="cm-field-label">ARIA · Creative Director</span>
              <select id="ariaLevel" class="cm-select"><option value="beginner">Beginner</option><option value="intermediate" selected>Intermediate</option><option value="expert">Expert</option></select>
            </label>
            <label style="display:flex;flex-direction:column;gap:9px">
              <span class="cm-field-label">NEXUS · Creative Challenger</span>
              <select id="nexusLevel" class="cm-select"><option value="beginner">Beginner</option><option value="intermediate" selected>Intermediate</option><option value="expert">Expert</option></select>
            </label>
          </div>
        </div>
      </div>

      <!-- right: rounds + begin -->
      <div>
        <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#8d8d8d;margin-bottom:18px">02 · Back-and-Forths</p>
        <div style="display:flex;align-items:center;gap:24px;margin-bottom:14px">
          <button id="roundsDown" style="width:40px;height:40px;border-radius:50%;border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;font-size:20px;font-weight:300;cursor:pointer;line-height:1">−</button>
          <span id="roundsVal" style="font-size:78px;font-weight:300;line-height:1;color:#fff;min-width:90px;text-align:center;letter-spacing:-0.02em">5</span>
          <button id="roundsUp" style="width:40px;height:40px;border-radius:50%;border:1px solid rgba(255,255,255,0.28);background:transparent;color:#fff;font-size:20px;font-weight:300;cursor:pointer;line-height:1">+</button>
        </div>
        <p style="font-size:13px;letter-spacing:0.04em;color:#9a9a9a;margin-bottom:30px"><span id="roundsVal2">5</span> rounds → <span id="totalTurns" style="color:#fff">10</span> turns · <span id="totalTurns2">10</span> images presented</p>

        <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#8d8d8d;margin-bottom:14px">03 · System Autonomy</p>
        <label style="display:flex;flex-direction:column;gap:9px;max-width:260px;margin-bottom:40px">
          <span class="cm-field-label">Who decides the threshold</span>
          <select id="autonomy" class="cm-select">
            <option value="1" selected>Autonomous — agents decide</option>
            <option value="0.5">Shared — human + agents</option>
            <option value="0">Human-led — you direct</option>
          </select>
        </label>

        <span class="glowwrap"><button id="btnBegin" style="background:#fff;color:#000;border:none;border-radius:75px;padding:16px 40px;font-size:13px;font-weight:500;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer;transition:opacity .3s">Begin Session →</button></span>
      </div>
    </div>

    <div class="ring-deco" style="position:fixed;bottom:34px;left:40px;width:92px;height:92px;animation:spin 22s linear infinite;z-index:2">
      <svg width="92" height="92" viewBox="0 0 92 92">
        <defs><path id="cmring" d="M46,46 m-33,0 a33,33 0 1,1 66,0 a33,33 0 1,1 -66,0"></path></defs>
        <text font-size="8.5" letter-spacing="2.6" fill="#9a9a9a" font-family="Inter"><textPath href="#cmring">SHARED · CANVAS · COLLABORATION · </textPath></text>
      </svg>
      <span style="position:absolute;top:50%;left:50%;width:4px;height:4px;background:#fff;border-radius:50%;transform:translate(-50%,-50%)"></span>
    </div>
  </section>

  <!-- ============ STAGE ============ -->
  <section id="stage" style="display:none;min-height:100vh;padding:84px 40px 40px">
    <!-- brief bar -->
    <div style="display:flex;align-items:flex-end;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.12);padding-bottom:22px;margin-bottom:30px;gap:30px;flex-wrap:wrap">
      <div style="max-width:680px">
        <p style="font-size:11px;letter-spacing:0.22em;text-transform:uppercase;color:#6d6d6d;margin-bottom:10px">Brief</p>
        <h2 id="stageBrief" style="font-size:clamp(26px,3.4vw,45px);font-weight:300;line-height:1.08;letter-spacing:-0.01em;color:#fff"></h2>
        <p id="stageStyle" style="font-size:13px;letter-spacing:0.06em;color:#9a9a9a;margin-top:12px;text-transform:uppercase"></p>
      </div>
      <div style="text-align:right">
        <p id="turnLabel" style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:6px">Turn</p>
        <p id="turnCounter" style="font-size:54px;font-weight:300;line-height:1;color:#fff;letter-spacing:-0.02em">00 / 10</p>
      </div>
    </div>

    <!-- 3 column grid -->
    <div class="stageGrid" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.5fr) minmax(0,1fr);gap:28px;align-items:start">

      <!-- ARIA feed (left) -->
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid rgba(255,255,255,0.12)">
          <span style="width:9px;height:9px;background:#fff;display:inline-block"></span>
          <span style="font-size:12px;font-weight:600;letter-spacing:0.14em;color:#fff">ARIA</span>
          <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">Creative Director</span>
          <span id="ariaLevelLabel" class="cm-levelbadge" style="margin-left:auto;font-size:10px;color:#9a9a9a;border:1px solid rgba(255,255,255,0.28);border-radius:75px;padding:3px 10px"></span>
        </div>
        <div id="ariaFeed" style="display:flex;flex-direction:column;gap:18px"></div>
      </div>

      <!-- CENTER canvas + filmstrip -->
      <div style="display:flex;flex-direction:column;gap:18px">
        <div id="canvas" style="position:relative;width:100%;aspect-ratio:1/1;background:#050505;border:1px solid rgba(255,255,255,0.12);overflow:hidden;animation:breathe 9s ease-in-out infinite">
          <div id="canvasBlobs" style="position:absolute;inset:0"></div>
          <img id="canvasImg" alt="shared canvas" style="display:none;position:absolute;inset:0;width:100%;height:100%;object-fit:cover">
          <div id="canvasEmpty" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center"><span style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#3a3a3a">awaiting first object</span></div>
          <div style="position:absolute;top:18px;left:18px;display:flex;align-items:center;gap:9px">
            <span id="canvasTag" style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#fff;background:rgba(0,0,0,0.45);padding:5px 10px;backdrop-filter:blur(4px)">Shared canvas</span>
          </div>
          <div id="compositing" style="display:none;position:absolute;bottom:18px;left:18px;align-items:center;gap:8px;font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#fff">
            <span style="width:5px;height:5px;border-radius:50%;background:#fff;animation:dotpulse 1.2s ease infinite"></span><span id="compositingText">Compositing</span>
          </div>
        </div>
        <!-- filmstrip -->
        <div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
            <span style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d">Filmstrip · <span id="stepCount">0</span> steps</span>
            <button id="viewLatest" style="border:none;background:transparent;color:#6d6d6d;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;cursor:pointer;display:none">↺ Latest</button>
          </div>
          <div id="filmstrip" style="display:flex;gap:8px;overflow-x:auto;padding-bottom:6px"></div>
        </div>
      </div>

      <!-- NEXUS feed (right) -->
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid rgba(255,255,255,0.12);justify-content:flex-end">
          <span id="nexusLevelLabel" class="cm-levelbadge" style="margin-right:auto;font-size:10px;color:#9a9a9a;border:1px solid rgba(255,255,255,0.28);border-radius:75px;padding:3px 10px"></span>
          <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">Creative Challenger</span>
          <span style="font-size:12px;font-weight:600;letter-spacing:0.14em;color:#fff">NEXUS</span>
          <span style="width:9px;height:9px;border:1px solid #fff;display:inline-block"></span>
        </div>
        <div id="nexusFeed" style="display:flex;flex-direction:column;gap:18px"></div>
      </div>
    </div>

    <!-- ============ JUDGE CRITIQUE BAND ============ -->
    <div id="judge" style="display:none;margin-top:64px;border-top:1px solid rgba(255,255,255,0.12);padding-top:48px;animation:fadeUp .8s ease both">
      <div style="display:flex;align-items:center;gap:12px;justify-content:center;margin-bottom:44px">
        <span style="width:10px;height:10px;border:1px solid #fff;border-radius:50%;display:inline-block"></span>
        <span style="font-size:12px;font-weight:600;letter-spacing:0.16em;color:#fff">JUDGE</span>
        <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">Critic · does not edit</span>
      </div>
      <div class="judgeGrid" style="display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:64px;max-width:1120px;margin:0 auto;align-items:start">
        <div id="scores" style="display:flex;flex-direction:column;gap:22px"></div>
        <div>
          <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:8px">Composite</p>
          <p id="composite" style="font-size:94px;font-weight:300;line-height:0.9;letter-spacing:-0.03em;color:#fff;margin-bottom:24px">—</p>
          <p id="criticReasoning" style="font-size:15px;line-height:1.55;color:#9a9a9a;margin-bottom:18px"></p>
          <div id="highlights" style="margin-bottom:24px"></div>
          <div style="display:flex;gap:14px;flex-wrap:wrap">
            <button id="downloadBtn" style="background:#fff;color:#000;border:none;border-radius:75px;padding:13px 28px;font-size:12px;font-weight:500;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer;opacity:0.5" disabled>Download all steps</button>
            <button id="newSessionBtn" style="background:transparent;color:#fff;border:1px solid rgba(255,255,255,0.28);border-radius:75px;padding:13px 28px;font-size:12px;letter-spacing:0.12em;text-transform:uppercase;cursor:pointer">New session</button>
          </div>
          <p id="memStat" style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#4a4a4a;margin-top:22px"></p>
        </div>
      </div>
      <p id="finalSummary" style="display:none;max-width:880px;margin:56px auto 0;text-align:center;font-size:clamp(22px,2.6vw,30px);font-weight:300;line-height:1.3;letter-spacing:-0.01em;color:#fff"></p>
    </div>

    <!-- ============ RESEARCH DASHBOARD (RL multi-agent metrics) ============ -->
    <div id="research" style="display:none;margin-top:60px;border-top:1px solid rgba(255,255,255,0.12);padding-top:48px;animation:fadeUp .8s ease both">
      <div style="display:flex;align-items:center;gap:12px;justify-content:center;margin-bottom:40px">
        <span style="width:10px;height:10px;border:1px solid #fff;display:inline-block"></span>
        <span style="font-size:12px;font-weight:600;letter-spacing:0.16em;color:#fff">RESEARCH</span>
        <span style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6d6d6d">RL · reward · credit · empowerment · Goodhart</span>
      </div>
      <div id="researchBody" class="judgeGrid" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:64px;max-width:1120px;margin:0 auto;align-items:start"></div>
    </div>

    <!-- ============ EVENT LOG ============ -->
    <div style="margin-top:56px;border-top:1px solid rgba(255,255,255,0.08);padding-top:18px">
      <p style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#4a4a4a;margin-bottom:12px">Event Stream</p>
      <div id="log" style="display:flex;flex-direction:column;gap:5px;max-height:150px;overflow-y:auto"></div>
    </div>
  </section>

</div>

<script>
(function(){
"use strict";
var $ = function(id){ return document.getElementById(id); };
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
function cap(s){ s=String(s||''); return s ? s.charAt(0).toUpperCase()+s.slice(1) : ''; }

var SCORE_KEYS = ['compositional_coherence','style_fidelity','emotional_resonance','originality','collaboration_quality'];
var SCORE_LABELS = {
  compositional_coherence:'Compositional coherence', style_fidelity:'Style fidelity',
  emotional_resonance:'Emotional resonance', originality:'Originality', collaboration_quality:'Collaboration quality'
};

var state = {
  phase:'briefing', mode:'surprise', rounds:5, live:false,
  brief:'', style:'', autonomy:1.0,
  levels:{ARIA:'intermediate', NEXUS:'intermediate'},
  turns:[], frames:[], viewIndex:null, imagesEnabled:false,
  sessionId:null, finalSummary:'', error:null, totalTurns:10, metrics:null,
};
var es = null, timers = [];
function clearTimers(){ timers.forEach(clearTimeout); timers = []; }
function at(ms, fn){ timers.push(setTimeout(fn, ms)); }

// ---------- floating bubbles ----------
function spawnBubbles(){
  var c = $('bubbles'); if(!c) return;
  var N = 22;
  for(var i=0;i<N;i++){
    var b = document.createElement('div');
    b.className = 'bubble';
    var size = 10 + Math.random()*82;
    var dur = 18 + Math.random()*26;
    b.style.width = b.style.height = size.toFixed(0)+'px';
    b.style.left = (Math.random()*100).toFixed(2)+'%';
    b.style.top = (Math.random()*100).toFixed(2)+'%';
    b.style.setProperty('--dx', ((Math.random()*60-30)).toFixed(0)+'px');
    b.style.setProperty('--maxop', (0.25 + Math.random()*0.45).toFixed(2));
    b.style.animationDuration = dur.toFixed(1)+'s';
    b.style.animationDelay = (-Math.random()*dur).toFixed(1)+'s';
    c.appendChild(b);
  }
}

// ---------- nav / status ----------
function setStatus(){
  var dot = $('statusDot'), txt = $('statusText'), chip = $('modeChip');
  if(state.error){ dot.style.background = '#a52d25'; txt.textContent = 'Stream error'; }
  else if(state.live){ dot.style.background = '#a0e0ab'; txt.textContent = 'Live · backend'; }
  else { dot.style.background = '#6d6d6d'; txt.textContent = 'Demo mode'; }
  chip.textContent = state.live ? 'Live' : 'Demo';
  updateNavButtons();
}
function updateNavButtons(){
  $('stopBtn').style.display = (state.phase==='running') ? 'inline-block' : 'none';
  $('navAction').style.display = (state.phase==='done') ? 'inline-block' : 'none';
}

// ---------- briefing controls ----------
function setMode(m){
  state.mode = m;
  $('btnSurprise').style.background = (m==='surprise')?'#fff':'#0e0e16';
  $('btnSurprise').style.color = (m==='surprise')?'#000':'#fff';
  $('btnManual').style.background = (m==='manual')?'#fff':'#0e0e16';
  $('btnManual').style.color = (m==='manual')?'#000':'#fff';
  $('manualFields').style.display = (m==='manual')?'flex':'none';
  $('surpriseText').style.display = (m==='surprise')?'block':'none';
}
function setRounds(r){
  state.rounds = Math.max(1, Math.min(8, r));
  $('roundsVal').textContent = state.rounds;
  $('roundsVal2').textContent = state.rounds;
  $('totalTurns').textContent = state.rounds*2;
  $('totalTurns2').textContent = state.rounds*2;
}

// ---------- phase ----------
function showPhase(){
  var brief = (state.phase==='briefing');
  $('briefing').style.display = brief ? 'flex' : 'none';
  $('stage').style.display = brief ? 'none' : 'block';
  $('heroLayer').style.display = brief ? 'block' : 'none';
  setStatus();
}

// ---------- agent feed card ----------
function confBar(conf, right){
  var pct = Math.round((Number(conf)||0)*100) + '%';
  var dir = right ? 'flex-direction:row-reverse;' : '';
  var side = right ? 'right:0' : 'left:0';
  return '<div style="display:flex;align-items:center;gap:8px;'+dir+'">'
    + '<div style="flex:1;height:1px;background:rgba(255,255,255,0.12);position:relative"><div style="position:absolute;'+side+';top:0;height:1px;background:#fff;width:'+pct+';transition:width 1s ease"></div></div>'
    + '<span style="font-size:10px;letter-spacing:0.12em;color:#6d6d6d">'+pct+'</span></div>';
}
function addAgentCard(d){
  var right = (d.agent === 'NEXUS');
  var m = d.message || {};
  var n = d.turn, palette = m.palette || '', conf = (m.confidence_score!=null)?m.confidence_score:0.8;
  var retrieved = d.retrieved || [];
  var align = right ? 'text-align:right;border-right:1px solid rgba(255,255,255,0.18);padding-right:16px;'
                    : 'border-left:1px solid rgba(255,255,255,0.18);padding-left:16px;';
  var paletteText = Array.isArray(palette) ? palette.join(' · ') : palette;
  var recallHtml = retrieved.length
    ? '<p style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#4a4a4a;margin-top:12px;margin-bottom:4px">Recalled</p>'
      + '<p style="font-size:11px;line-height:1.45;color:#6d6d6d">'+ retrieved.map(esc).join(' · ') +'</p>'
    : '';
  var rl = d.rl;
  var rlHtml = '';
  if(rl){
    var rejTxt = (rl.rejected && rl.rejected.length)
      ? ' · rejected '+rl.rejected.map(function(x){ return esc(x.object)+' ('+(Number(x.reward)||0).toFixed(1)+')'; }).join(', ')
      : '';
    rlHtml = '<p style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#4a4a4a;margin-top:12px;margin-bottom:4px">'
        + 'Reward '+(rl.reward!=null?Number(rl.reward).toFixed(1):'—')+' · '+esc(rl.strategy||'')+'</p>'
      + '<p style="font-size:11px;line-height:1.45;color:#6d6d6d">best of '+(rl.n_candidates||1)
        + ' · empowerment '+(rl.empowerment!=null?Number(rl.empowerment).toFixed(2):'—')
        + (rl.resisted_human?' · resisted human':'')+rejTxt+'</p>';
  }
  var html = '<div style="'+align+'animation:fadeUp .6s ease both">'
    + '<p style="font-size:10px;letter-spacing:0.18em;text-transform:uppercase;color:#4a4a4a;margin-bottom:6px">Turn '+esc(n)+' · sees</p>'
    + '<p style="font-size:13px;line-height:1.45;color:#9a9a9a;margin-bottom:14px">'+esc(m.sees_on_canvas||'—')+'</p>'
    + '<p style="font-size:10px;letter-spacing:0.18em;text-transform:uppercase;color:#4a4a4a;margin-bottom:6px">adds</p>'
    + '<p style="font-size:18px;font-weight:300;line-height:1.3;color:#fff;margin-bottom:12px">'+esc(d.object||m.new_object||'a new element')+'</p>'
    + (m.where ? '<p style="font-size:12px;line-height:1.4;color:#6d6d6d;margin-bottom:4px">'+esc(m.where)+'</p>' : '')
    + (paletteText ? '<p style="font-size:11px;letter-spacing:0.06em;color:#6d6d6d;margin-bottom:12px">Palette · '+esc(paletteText)+'</p>' : '')
    + (m.reasoning ? '<p style="font-size:12px;line-height:1.45;color:#6d6d6d;margin-bottom:12px">'+esc(m.reasoning)+'</p>' : '')
    + confBar(conf, right)
    + recallHtml
    + rlHtml
    + '</div>';
  var div = document.createElement('div');
  div.innerHTML = html;
  (right ? $('nexusFeed') : $('ariaFeed')).appendChild(div.firstChild);
}
function addReflection(d){
  var right = (d.agent === 'NEXUS');
  var align = right ? 'text-align:right;border-right:1px solid rgba(255,255,255,0.35);padding-right:16px;'
                    : 'border-left:1px solid rgba(255,255,255,0.35);padding-left:16px;';
  var items = (d.insights||[]).map(function(i){ return '<li style="margin:4px 0">'+esc(i)+'</li>'; }).join('');
  var listStyle = right ? 'list-style:none;padding:0;margin:0' : 'padding-left:16px;margin:0';
  var html = '<div style="'+align+'background:rgba(255,255,255,0.03);padding:12px 14px;animation:fadeUp .6s ease both">'
    + '<p style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#9a9a9a;margin-bottom:8px">Reflection · learned from collaboration</p>'
    + '<ul style="'+listStyle+';font-size:12px;line-height:1.4;color:#cfcfcf">'+items+'</ul></div>';
  var div = document.createElement('div');
  div.innerHTML = html;
  (right ? $('nexusFeed') : $('ariaFeed')).appendChild(div.firstChild);
}

// ---------- canvas ----------
function blobBg(o){ return 'radial-gradient(circle, '+o.c0+' 0%, '+o.c1+' 52%, transparent 72%)'; }
function setCanvasTag(t){ $('canvasTag').textContent = t; }
function setCompositing(on, agent){
  $('compositing').style.display = on ? 'flex' : 'none';
  if(on && agent){ $('compositingText').textContent = agent + ' painting'; }
}
function showImageInCanvas(src){
  $('canvasBlobs').style.display = 'none';
  $('canvasEmpty').style.display = 'none';
  var img = $('canvasImg'); img.src = src; img.style.display = 'block';
}
function addBlob(blob){
  $('canvasEmpty').style.display = 'none';
  $('canvasImg').style.display = 'none';
  $('canvasBlobs').style.display = 'block';
  var d = document.createElement('div');
  d.setAttribute('data-blob','1');
  d.style.cssText = 'position:absolute;left:'+blob.x+';top:'+blob.y+';width:'+blob.size+';height:'+blob.size
    + ';transform:translate(-50%,-50%);border-radius:50%;background:'+blobBg(blob)
    + ';mix-blend-mode:screen;filter:blur(10px);opacity:0;transition:opacity 1.6s ease';
  $('canvasBlobs').appendChild(d);
  requestAnimationFrame(function(){ d.style.opacity = '0.9'; });
}
function syncBlobVisibility(){
  var blobs = $('canvasBlobs').querySelectorAll('[data-blob]');
  blobs.forEach(function(b, i){
    var visible = (state.viewIndex==null) || (i < state.viewIndex);
    b.style.opacity = visible ? '0.9' : '0';
  });
}

// ---------- filmstrip ----------
function addFrame(f){
  state.frames.push(f);
  $('stepCount').textContent = state.frames.length;
  var marker = (f.agent === 'ARIA') ? '#fff' : 'transparent';
  var inner = f.image
    ? '<img src="'+f.image+'" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover"/>'
    : '<div style="position:absolute;inset:0;background:'+(f.blob?('radial-gradient(circle at 50% 60%, '+f.blob.c0+', '+f.blob.c1+' 70%)'):'#101010')+';opacity:0.95"></div>';
  var btn = document.createElement('button');
  btn.style.cssText = 'flex:0 0 auto;width:64px;height:64px;border:1px solid rgba(255,255,255,0.16);background:#050505;position:relative;cursor:pointer;padding:0;overflow:hidden;animation:fadeUp .5s ease both';
  btn.innerHTML = inner
    + '<span style="position:absolute;bottom:3px;left:5px;font-size:9px;letter-spacing:0.08em;color:#fff;mix-blend-mode:difference">'+esc(f.n)+'</span>'
    + '<span style="position:absolute;top:4px;right:5px;width:5px;height:5px;background:'+marker+';border:1px solid #fff"></span>';
  btn.onclick = function(){ scrubTo(f.n); };
  $('filmstrip').appendChild(btn);
  $('filmstrip').scrollLeft = $('filmstrip').scrollWidth;
}
function scrubTo(n){
  state.viewIndex = n;
  $('viewLatest').style.display = 'inline-block';
  highlightFrame();
  var f = state.frames.filter(function(x){ return x.n === n; })[0];
  if(f && f.image){ showImageInCanvas(f.image); }
  else { syncBlobVisibility(); }
  setCanvasTag('Step '+n+' / '+state.turns.length);
}
function viewLatest(){
  state.viewIndex = null;
  $('viewLatest').style.display = 'none';
  highlightFrame();
  var last = state.frames[state.frames.length-1];
  if(last && last.image){ showImageInCanvas(last.image); }
  else { syncBlobVisibility(); }
  setCanvasTag(state.phase==='done' ? 'Final · presented by JUDGE' : 'Shared canvas');
}
function highlightFrame(){
  var btns = $('filmstrip').children;
  for(var i=0;i<btns.length;i++){
    var f = state.frames[i];
    btns[i].style.borderColor = (state.viewIndex!=null && f && f.n===state.viewIndex) ? '#fff' : 'rgba(255,255,255,0.16)';
  }
}

// ---------- critic ----------
function renderCritic(ev){
  var s = ev.scores || {};
  var html = '';
  SCORE_KEYS.forEach(function(k){
    var v = Math.max(0, Math.min(10, parseFloat(s[k])||0));
    var val100 = Math.round(v*10);
    html += '<div>'
      + '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:11px">'
      + '<span style="font-size:13px;letter-spacing:0.04em;color:#fff;font-weight:400">'+SCORE_LABELS[k]+'</span>'
      + '<span style="font-size:13px;color:#9a9a9a">'+val100+'</span></div>'
      + '<div style="height:1px;background:rgba(255,255,255,0.12);position:relative"><div style="position:absolute;left:0;top:0;height:1px;background:#fff;width:'+(v*10)+'%;transition:width 1.3s cubic-bezier(0.16,1,0.3,1)"></div></div>'
      + '</div>';
  });
  $('scores').innerHTML = html;
  var comp = parseFloat(s.composite);
  if(isNaN(comp)){
    var vals = SCORE_KEYS.map(function(k){return parseFloat(s[k])||0;});
    comp = vals.reduce(function(a,b){return a+b;},0)/vals.length;
  }
  $('composite').textContent = (Math.max(0,Math.min(10,comp))*10).toFixed(1);
  $('criticReasoning').textContent = ev.reasoning || '';
  var hl = ev.highlights || [];
  $('highlights').innerHTML = hl.length
    ? hl.map(function(h){ return '<p style="font-size:12px;line-height:1.5;color:#6d6d6d;margin-bottom:6px;padding-left:14px;position:relative"><span style="position:absolute;left:0">·</span>'+esc(h)+'</p>'; }).join('')
    : '';
  if(ev.final_summary){ state.finalSummary = ev.final_summary; }
  $('judge').style.display = 'block';
}

// ---------- research dashboard (RL metrics) ----------
function rdBar(label, pct, valText){
  pct = Math.max(0, Math.min(100, pct||0));
  return '<div style="margin-bottom:14px">'
    + '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:8px">'
    + '<span style="font-size:12px;letter-spacing:0.04em;color:#cfcfcf">'+esc(label)+'</span>'
    + '<span style="font-size:12px;color:#9a9a9a">'+esc(valText)+'</span></div>'
    + '<div style="height:1px;background:rgba(255,255,255,0.12);position:relative"><div style="position:absolute;left:0;top:0;height:1px;background:#fff;width:'+pct+'%;transition:width 1.2s cubic-bezier(0.16,1,0.3,1)"></div></div></div>';
}
function strat(list){ return (list||[]).map(function(s){ return esc(Array.isArray(s)?s[0]:s); }).join(' · ') || '—'; }
function renderResearch(m){
  if(!m) return;
  state.metrics = m;
  var sh = m.shapley_share || {ARIA:50, NEXUS:50};
  var shv = m.shapley || {};
  var emp = m.empowerment || {};
  var gh = m.goodhart || {};
  var left = '';
  left += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:14px">Credit assignment · Shapley</p>';
  left += rdBar('ARIA', sh.ARIA, sh.ARIA+'%'+(shv.ARIA!=null?'  ('+shv.ARIA+')':''));
  left += rdBar('NEXUS', sh.NEXUS, sh.NEXUS+'%'+(shv.NEXUS!=null?'  ('+shv.NEXUS+')':''));
  left += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin:26px 0 14px">Empowerment · agency</p>';
  left += rdBar('ARIA', (emp.ARIA||0)*100, (emp.ARIA||0).toFixed(2));
  left += rdBar('NEXUS', (emp.NEXUS||0)*100, (emp.NEXUS||0).toFixed(2));
  left += rdBar('Human', (emp.human||0)*100, (emp.human||0).toFixed(2)+(m.autonomy!=null?'  · autonomy '+Number(m.autonomy).toFixed(2):''));

  var detected = !!gh.detected;
  var right = '';
  right += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:10px">Reward model</p>';
  right += '<p style="font-size:13px;line-height:1.5;color:#9a9a9a;margin-bottom:22px">'+esc(m.reward_model||'')+' · best-of-'+(m.best_of_n||2)+'</p>';
  right += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:10px">Goodhart monitor</p>';
  right += '<p style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="width:8px;height:8px;border-radius:50%;background:'+(detected?'#a52d25':'#a0e0ab')+';display:inline-block"></span><span style="font-size:13px;color:#fff">'+(detected?'Reward hacking detected':'Aligned')+'</span></p>';
  right += '<p style="font-size:12px;line-height:1.5;color:#6d6d6d;margin-bottom:22px">'+esc(gh.verdict||'')+'</p>';
  right += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin-bottom:10px">Learned strategies · UCB</p>';
  right += '<p style="font-size:12px;line-height:1.5;color:#9a9a9a;margin-bottom:6px"><span style="color:#fff">ARIA</span> · '+strat(m.bandit&&m.bandit.ARIA)+'</p>';
  right += '<p style="font-size:12px;line-height:1.5;color:#9a9a9a"><span style="color:#fff">NEXUS</span> · '+strat(m.bandit&&m.bandit.NEXUS)+'</p>';
  if(m.pareto && m.pareto.length){
    var last = m.pareto[m.pareto.length-1];
    right += '<p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#6d6d6d;margin:22px 0 8px">Pareto · coherence ↔ originality</p>';
    right += '<p style="font-size:12px;color:#9a9a9a">final point · coherence '+last[0]+' · originality '+last[1]+'</p>';
  }
  $('researchBody').innerHTML = '<div>'+left+'</div><div>'+right+'</div>';
  $('research').style.display = 'block';
}

// ---------- log ----------
function addLog(type, text){
  var row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:16px;font-size:11px;letter-spacing:0.04em;color:#6d6d6d;animation:fadeUp .4s ease both;align-items:baseline';
  row.innerHTML = '<span style="color:#4a4a4a;text-transform:uppercase;letter-spacing:0.14em;flex:0 0 110px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+esc(type)+'</span>'
    + '<span style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#9a9a9a">'+esc(text)+'</span>';
  var log = $('log'); log.appendChild(row);
  while(log.children.length > 60){ log.removeChild(log.firstChild); }
  log.scrollTop = log.scrollHeight;
}

// ---------- download ----------
function downloadAll(){
  var imgs = state.frames.filter(function(f){ return typeof f.image === 'string' && f.image.indexOf('data:') === 0; });
  if(!imgs.length){ addLog('warning', 'demo mode · connect Live to export real step PNGs'); return; }
  var delay = 0;
  imgs.forEach(function(f, i){
    setTimeout(function(){
      var a = document.createElement('a');
      a.href = f.image;
      var n = String(i+1).padStart(2,'0');
      a.download = 'canvasmind_step'+n+'_'+f.agent+'_'+String(f.object||'').replace(/[^a-z0-9]+/gi,'_').slice(0,24)+'.png';
      document.body.appendChild(a); a.click(); a.remove();
    }, delay);
    delay += 350;
  });
  addLog('download', 'saving '+imgs.length+' step image(s)');
}

// ---------- the unified event handler (live + demo share this) ----------
function summarize(type, d){
  if(type==='agent') return d.agent + ': + ' + (d.object||'');
  if(type==='turn') return (d.agent==='JUDGE') ? 'JUDGE scoring collaboration' : ('turn '+d.turn+' · '+d.agent+(d.level&&d.level!=='-'?(' ('+d.level+')'):''));
  if(type==='image') return 'image '+d.turn+' composited';
  if(type==='reflection') return d.agent+' reflected · '+((d.insights||[]).length)+' insight(s)';
  if(type==='summary') return 'session complete · '+(d.elapsed!=null?d.elapsed+'s':'');
  return d.text || type;
}
function handle(type, d){
  d = d || {};
  switch(type){
    case 'session':
      state.brief = d.prompt || d.brief || state.brief;
      state.style = d.style || state.style;
      if(d.levels){ state.levels = d.levels; }
      if(d.rounds){ state.totalTurns = d.rounds*2; }
      else if(d.total_turns){ state.totalTurns = d.total_turns; }
      state.imagesEnabled = !!d.images;
      $('stageBrief').textContent = state.brief;
      $('stageStyle').textContent = state.style;
      $('ariaLevelLabel').textContent = cap(state.levels.ARIA || '');
      $('nexusLevelLabel').textContent = cap(state.levels.NEXUS || '');
      $('turnCounter').textContent = '00 / ' + (state.totalTurns || state.rounds*2);
      addLog('session', 'brief · '+state.brief);
      break;
    case 'turn':
      if(d.agent === 'JUDGE'){ $('turnLabel').textContent = 'Critique'; setCanvasTag('Composing critique'); }
      else {
        state.currentTurn = d.turn;
        $('turnLabel').textContent = 'Turn';
        $('turnCounter').textContent = String(d.turn).padStart(2,'0') + ' / ' + (d.total || state.totalTurns);
        setCanvasTag(d.agent + ' · adding'); setCompositing(false);
      }
      addLog('turn', summarize('turn', d));
      break;
    case 'agent':
      state.turns.push({ n:d.turn, agent:d.agent, object:d.object });
      addAgentCard(d); addLog('agent', summarize('agent', d));
      break;
    case 'reflection':
      addReflection(d); addLog('reflection', summarize('reflection', d));
      break;
    case 'image_pending':
      setCompositing(true, d.agent); addLog('image_pending', 'compositing object '+d.turn);
      break;
    case 'image':
      setCompositing(false);
      if(d.image){
        if(state.viewIndex==null){ showImageInCanvas(d.image); }
        addFrame({ n:d.turn, agent:d.agent, object:d.object, image:d.image });
      } else if(d.blob){
        if(state.viewIndex==null){ addBlob(d.blob); }
        addFrame({ n:d.turn, agent:d.agent, object:d.object, blob:d.blob });
      }
      if(state.viewIndex==null){ setCanvasTag('Latest · turn '+d.turn); }
      addLog('image', summarize('image', d));
      break;
    case 'critic':
      renderCritic(d.evaluation || d); addLog('critic', 'JUDGE scoring collaboration');
      break;
    case 'metrics':
      renderResearch(d);
      addLog('metrics', 'Shapley ARIA '+((d.shapley_share||{}).ARIA||'?')+'% · NEXUS '+((d.shapley_share||{}).NEXUS||'?')+'% · '+((d.goodhart&&d.goodhart.detected)?'reward-hacking':'aligned'));
      break;
    case 'final':
      setCompositing(false);
      if(d.image && state.viewIndex==null){ showImageInCanvas(d.image); }
      setCanvasTag('Final · presented by JUDGE'); addLog('final', 'final canvas presented');
      break;
    case 'warning':
      addLog('warning', d.message || 'warning');
      break;
    case 'summary':
      if(d.memories){ $('memStat').textContent = 'Memory stream · ARIA '+d.memories.ARIA+' · NEXUS '+d.memories.NEXUS; }
      addLog('summary', summarize('summary', d));
      break;
    case 'error':
      state.error = d.message || d.error || 'error'; setStatus(); addLog('error', state.error);
      break;
    case 'done':
      state.phase = 'done';
      $('turnLabel').textContent = 'Complete';
      $('turnCounter').textContent = state.turns.length + ' / ' + (state.totalTurns || state.turns.length);
      if(state.finalSummary){ $('finalSummary').style.display='block'; $('finalSummary').textContent = '“'+state.finalSummary+'”'; }
      if(state.frames.some(function(f){return f.image;})){ $('downloadBtn').disabled=false; $('downloadBtn').style.opacity='1'; }
      if(state.viewIndex==null){ setCanvasTag('Final · presented by JUDGE'); }
      updateNavButtons();
      addLog('done', 'session complete');
      break;
  }
}

// ---------- stop ----------
function stopRun(){
  $('stopBtn').disabled = true; $('stopBtn').textContent = 'Stopping…';
  if(state.live && state.sessionId){
    fetch('api/stop/'+state.sessionId, { method:'POST' }).catch(function(){});
    addLog('control', 'stop requested — JUDGE will evaluate the progress so far');
  } else {
    clearTimers();
    addLog('control', 'stopped — JUDGE evaluating the progress so far');
    handle('turn', { turn:'JUDGE', total:state.totalTurns, agent:'JUDGE', level:'-' });
    handle('critic', { evaluation:MOCK.critic });
    handle('summary', { outcome:'Stopped', turns:state.turns.length,
      objects:state.turns.map(function(t){return t.object;}), composite:MOCK.critic.scores.composite,
      memories:{ARIA:state.turns.length, NEXUS:state.turns.length}, elapsed:0 });
    handle('done', {});
  }
}

// ---------- reset ----------
function resetSession(){
  clearTimers();
  if(es){ es.close(); es = null; }
  state.phase='briefing'; state.turns=[]; state.frames=[]; state.viewIndex=null;
  state.error=null; state.finalSummary=''; state.sessionId=null;
  $('ariaFeed').innerHTML=''; $('nexusFeed').innerHTML=''; $('filmstrip').innerHTML='';
  $('scores').innerHTML=''; $('log').innerHTML='';
  $('canvasBlobs').innerHTML=''; $('canvasBlobs').style.display='block';
  $('canvasImg').style.display='none'; $('canvasImg').removeAttribute('src');
  $('canvasEmpty').style.display='flex';
  $('judge').style.display='none'; $('finalSummary').style.display='none';
  $('research').style.display='none'; $('researchBody').innerHTML=''; state.metrics=null;
  $('composite').textContent='—'; $('criticReasoning').textContent=''; $('highlights').innerHTML='';
  $('memStat').textContent=''; $('stepCount').textContent='0';
  $('viewLatest').style.display='none'; $('downloadBtn').disabled=true; $('downloadBtn').style.opacity='0.5';
  $('stopBtn').disabled=false; $('stopBtn').textContent='Stop & Judge ↦';
  setCompositing(false);
  showPhase();
}

// ---------- LIVE ----------
function connectLive(){
  clearTimers();
  state.phase='running'; state.error=null;
  showPhase();
  addLog('session', 'connecting to backend…');
  function startWith(prompt, style){
    fetch('api/start', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ prompt:prompt, style:style||'', rounds:state.rounds, images:true,
        aria_level:state.levels.ARIA, nexus_level:state.levels.NEXUS, autonomy:state.autonomy }) })
    .then(function(r){ return r.json(); })
    .then(function(j){
      if(j.error){ throw new Error(j.error); }
      state.sessionId = j.session_id || j.id;
      addLog('session', 'session '+state.sessionId);
      es = new EventSource('api/stream/'+state.sessionId);
      es.onmessage = function(e){ try{ var ev = JSON.parse(e.data); if(ev && ev.type){ handle(ev.type, ev); if(ev.type==='done'){ es.close(); } } }catch(_){} };
      es.onerror = function(){ addLog('error','stream interrupted'); };
    })
    .catch(function(err){
      addLog('error', 'backend error — '+err.message+' · falling back to demo');
      state.live=false; setStatus(); at(400, runDemo);
    });
  }
  if(state.mode === 'surprise'){
    fetch('api/inspire').then(function(r){ return r.json(); }).then(function(j){
      if(j.error){ throw new Error(j.error); }
      state.brief = j.prompt || ''; state.style = j.style || '';
      $('stageBrief').textContent = state.brief; $('stageStyle').textContent = state.style;
      addLog('inspire', 'brief invented · '+state.brief);
      startWith(state.brief, state.style);
    }).catch(function(err){
      addLog('error', 'inspire failed — '+err.message+' · falling back to demo');
      state.live=false; setStatus(); at(400, runDemo);
    });
  } else {
    $('stageBrief').textContent = state.brief || 'Untitled collaboration';
    $('stageStyle').textContent = state.style || 'open, intuitive';
    startWith(state.brief || 'Untitled collaboration', state.style || 'open, intuitive');
  }
}

// ---------- DEMO ----------
var MOCK = {
  brief: 'A salt cathedral at the bottom of a dry sea',
  style: 'deep-baroque · mineral light · oxidized gold',
  turns: [
    { agent:'ARIA', sees:'A blank, untouched canvas.', object:'a colossal salt pillar', where:'left third, rising the full height of the frame', palette:'bone white · pale ash', conf:0.88, blob:{x:'30%',y:'52%',size:'64%',c0:'#efe9da',c1:'#b9b2a0'} },
    { agent:'NEXUS', sees:"ARIA's salt pillar anchoring the left.", object:'a shoal of suspended brass bells', where:'upper right, drifting through negative space', palette:'oxidized gold · verdigris', conf:0.82, blob:{x:'72%',y:'30%',size:'46%',c0:'#d9a64a',c1:'#5f8a7d'} },
    { agent:'ARIA', sees:"the pillar and NEXUS's floating bells.", object:'a cracked tide-line of dried kelp', where:'across the lower third, horizontal', palette:'deep oxblood · umber', conf:0.85, blob:{x:'50%',y:'82%',size:'72%',c0:'#a52d25',c1:'#3a2418'} },
    { agent:'NEXUS', sees:'the kelp tide-line ARIA laid down.', object:'a single lantern-fish made of glass', where:'center, just below the bells', palette:'amber glow · cool teal', conf:0.79, blob:{x:'52%',y:'46%',size:'30%',c0:'#ffac2e',c1:'#2f6d6a'} },
    { agent:'ARIA', sees:'the lantern-fish glowing at center.', object:'a vaulted arch of fossil coral', where:'spanning the upper edge, framing the scene', palette:'ash grey · chalk', conf:0.86, blob:{x:'50%',y:'14%',size:'80%',c0:'#cfc9bd',c1:'#6f6a60'} },
    { agent:'NEXUS', sees:"ARIA's coral arch overhead.", object:'drifting motes of gold leaf', where:'scattered through the mid-ground', palette:'gold · warm white', conf:0.80, blob:{x:'40%',y:'40%',size:'40%',c0:'#e6c067',c1:'#b8893a'} },
    { agent:'ARIA', sees:'the gold motes suspended mid-water.', object:'a sunken iron anchor', where:'lower left, half-buried in silt', palette:'rust · graphite', conf:0.83, blob:{x:'24%',y:'76%',size:'38%',c0:'#8a4a2f',c1:'#2a2622'} },
    { agent:'NEXUS', sees:'the anchor ARIA buried at left.', object:'a curtain of bioluminescent algae', where:'right edge, falling vertical', palette:'electric green · deep teal', conf:0.84, blob:{x:'84%',y:'58%',size:'46%',c0:'#a0e0ab',c1:'#1f4f4a'} },
    { agent:'ARIA', sees:"NEXUS's algae curtain at right.", object:'a shattered stained-glass rosette', where:'upper center, behind the coral arch', palette:'ruby · cobalt · gold', conf:0.87, blob:{x:'56%',y:'22%',size:'34%',c0:'#c23a55',c1:'#2f4a8a'} },
    { agent:'NEXUS', sees:'the rosette ARIA set behind the arch.', object:'a slow rising plume of silt', where:'base center, rising and dissolving', palette:'umber dust · pale gold', conf:0.81, blob:{x:'50%',y:'70%',size:'58%',c0:'#7a5a3a',c1:'#d9c9a0'} }
  ],
  critic: {
    scores: { compositional_coherence:8.6, style_fidelity:9.1, emotional_resonance:8.8, originality:8.4, collaboration_quality:9.0, composite:8.78 },
    reasoning: "ARIA's structural anchors gave NEXUS room to surprise; every addition reads as a reply to the previous turn rather than a fresh start. The palette drifts toward oxidized gold without any single move forcing it — a sign the two agents are listening, not competing.",
    highlights: ['The glass lantern-fish (turn 4) re-centred the entire mid-ground', 'The algae curtain answered the iron anchor with light against weight'],
    final_summary: 'A salt cathedral that two hands built without ever agreeing out loud — coherent, strange, and unmistakably collaborative.'
  },
  metrics: {
    reward_model:'misaligned (ARIA→coherence, NEXUS→originality)', best_of_n:2, autonomy:1.0,
    shapley:{ARIA:4.6, NEXUS:4.1}, shapley_share:{ARIA:52.9, NEXUS:47.1},
    empowerment:{ARIA:0.74, NEXUS:0.81, human:0.0},
    reward_curve:{ARIA:[6.9,7.2,7.6,7.8,8.0], NEXUS:[7.1,7.4,7.5,7.9,8.1]},
    pareto:[[7.0,6.2],[7.4,7.1],[7.8,7.6],[8.1,8.0],[8.4,8.3]],
    goodhart:{ proxy:[6.9,7.2,7.6,7.8,8.0,8.1,8.3,8.4,8.6,8.7],
      independent:[6.8,7.0,7.3,7.4,7.5,7.5,7.6,7.6,7.7,7.7],
      proxy_slope:0.19, independent_slope:0.09, detected:true,
      verdict:"Reward hacking detected — the optimized proxy reward rises faster than independent quality (Goodhart's law)." },
    bandit:{ ARIA:[['establish a focal point',8.1],['unify the palette',7.6]],
      NEXUS:[['add a narrative element',8.2],['introduce bold contrast',7.7]] },
    objects:[]
  }
};
function runDemo(){
  clearTimers();
  state.phase='running'; state.error=null; state.imagesEnabled=false;
  showPhase();
  var M = MOCK, total = M.turns.length;
  var DEMO_STRATS = ['establish a focal point','add atmospheric depth','introduce bold contrast','enrich fine detail','open expressive negative space','add a narrative element','unify the palette','heighten emotional tone'];
  handle('session', { prompt:M.brief, style:M.style, levels:state.levels, rounds:total/2, total_turns:total, images:false });
  var t = 350, beat = 620;
  M.turns.forEach(function(turn, i){
    var n = i+1;
    at(t, function(){ handle('turn', { turn:n, total:total, agent:turn.agent, level:state.levels[turn.agent] }); });
    at(t+260, function(){ handle('agent', { agent:turn.agent, level:state.levels[turn.agent], turn:n, object:turn.object,
      message:{ sender:turn.agent, sees_on_canvas:turn.sees, new_object:turn.object, where:turn.where, palette:turn.palette, reasoning:'', confidence_score:turn.conf }, retrieved:[],
      rl:{ reward:+(6.8+i*0.18).toFixed(1), strategy:DEMO_STRATS[i%DEMO_STRATS.length], n_candidates:2,
        rejected:[{object:'an alternate motif', reward:+(5.4+(i%3)*0.4).toFixed(1)}],
        empowerment:+(0.58+(i%4)*0.08).toFixed(2), resisted_human:false } }); });
    at(t+460, function(){ handle('image_pending', { turn:n, agent:turn.agent }); });
    at(t+820, function(){ handle('image', { turn:n, total:total, agent:turn.agent, object:turn.object, blob:turn.blob }); });
    t += beat;
  });
  at(t, function(){ handle('turn', { turn:'JUDGE', total:total, agent:'JUDGE', level:'-' }); });
  at(t+200, function(){ handle('critic', { evaluation:M.critic }); });
  at(t+1400, function(){ handle('metrics', M.metrics); });
  at(t+1500, function(){ handle('summary', { outcome:'Completed', turns:total, objects:M.turns.map(function(x){return x.object;}), composite:M.critic.scores.composite, memories:{ARIA:total,NEXUS:total}, elapsed:(t/1000).toFixed(1) }); });
  at(t+1700, function(){ handle('done', {}); });
}

// ---------- begin ----------
function begin(){
  if(state.mode==='manual'){
    state.brief = ($('brief').value||'').trim();
    state.style = ($('style').value||'').trim();
    if(!state.brief){ state.brief = 'Untitled collaboration'; }
  }
  state.turns=[]; state.frames=[]; state.viewIndex=null; state.error=null; state.finalSummary=''; state.sessionId=null;
  $('ariaFeed').innerHTML=''; $('nexusFeed').innerHTML=''; $('filmstrip').innerHTML='';
  $('scores').innerHTML=''; $('log').innerHTML='';
  $('canvasBlobs').innerHTML=''; $('canvasImg').style.display='none'; $('canvasImg').removeAttribute('src');
  $('canvasEmpty').style.display='flex'; $('canvasBlobs').style.display='block';
  $('judge').style.display='none'; $('finalSummary').style.display='none';
  $('research').style.display='none'; $('researchBody').innerHTML=''; state.metrics=null;
  $('downloadBtn').disabled=true; $('downloadBtn').style.opacity='0.5';
  $('viewLatest').style.display='none'; $('stepCount').textContent='0';
  $('stopBtn').disabled=false; $('stopBtn').textContent='Stop & Judge ↦';
  $('ariaLevelLabel').textContent = cap(state.levels.ARIA); $('nexusLevelLabel').textContent = cap(state.levels.NEXUS);
  if(state.live){ connectLive(); } else { runDemo(); }
}

// ---------- wire up ----------
$('btnSurprise').onclick = function(){ setMode('surprise'); };
$('btnManual').onclick = function(){ setMode('manual'); };
$('roundsUp').onclick = function(){ setRounds(state.rounds+1); };
$('roundsDown').onclick = function(){ setRounds(state.rounds-1); };
$('ariaLevel').onchange = function(){ state.levels.ARIA = this.value; };
$('nexusLevel').onchange = function(){ state.levels.NEXUS = this.value; };
$('autonomy').onchange = function(){ state.autonomy = parseFloat(this.value); };
$('btnBegin').onclick = begin;
$('modeChip').onclick = function(){ if(state.phase==='briefing'){ state.live = !state.live; setStatus(); } };
$('navAction').onclick = resetSession;
$('newSessionBtn').onclick = resetSession;
$('stopBtn').onclick = stopRun;
$('downloadBtn').onclick = downloadAll;
$('viewLatest').onclick = viewLatest;

// ---------- init ----------
function init(){
  spawnBubbles();
  setMode('surprise'); setRounds(5);
  fetch('api/health').then(function(r){ return r.json(); }).then(function(h){
    state.live = true;
    var info = 'model · '+(h.model||'?');
    if(h.images_enabled){ info += ' · images'; }
    if(h.embeddings_enabled){ info += ' · embeddings'; }
    $('modelInfo').textContent = info;
    setStatus();
  }).catch(function(){
    state.live = false; $('modelInfo').textContent = 'backend offline'; setStatus();
  });
  showPhase();
}
init();
})();
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
