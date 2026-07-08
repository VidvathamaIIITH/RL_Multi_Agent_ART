"""QuadCreativeOrchestrator — strict 4-agent sequential additive pipeline.

Runs in a worker thread and emits SSE-shaped event dicts onto a queue (and to an
optional external sink). All Azure calls use the raw REST pattern already proven
in the single-file launcher (``max_completion_tokens`` for gpt-5.2; gpt-image-1
generations/edits returning base64) — NOT the SDK provider — so it works on the
GPU VM without the SDK's parameter issues.
"""
from __future__ import annotations

import base64
import json
import os
import queue
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import requests

from agents.persona_agent import EXPERTISE_LEVELS, QUAD_PERSONAS, PersonaAgent, personas_catalog  # noqa: F401
from orchestration.art_history_rag import ArtHistoryRAG


# --------------------------------------------------------------------------- #
#  Raw Azure OpenAI REST helpers (env read lazily so import never fails)
# --------------------------------------------------------------------------- #
def _env(key: str) -> Optional[str]:
    return os.getenv(key)


def azure_chat_completion(messages: List[Dict[str, str]], max_completion_tokens: int = 1800, timeout: int = 180) -> str:
    endpoint = (_env("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
    url = (f"{endpoint}/openai/deployments/{_env('AZURE_OPENAI_DEPLOYMENT_GPTTEXT52')}"
           f"/chat/completions?api-version={_env('AZURE_OPENAI_API_VERSION')}")
    headers = {"api-key": _env("AZURE_OPENAI_API_KEY"), "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json={"messages": messages, "max_completion_tokens": max_completion_tokens}, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure chat failed HTTP {resp.status_code}: {resp.text[:400]}")
    content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("Azure returned an empty chat response.")
    return content.strip()


def azure_generate_image_b64(prompt: str, size: str = "1024x1024", timeout: int = 240) -> Optional[str]:
    dep = _env("AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1")
    if not dep:
        return None
    endpoint = (_env("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
    url = f"{endpoint}/openai/deployments/{dep}/images/generations?api-version={_env('AZURE_OPENAI_API_VERSION')}"
    headers = {"api-key": _env("AZURE_OPENAI_API_KEY"), "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json={"prompt": prompt[:3900], "size": size, "n": 1}, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure image generation failed HTTP {resp.status_code}: {resp.text[:300]}")
    return (resp.json().get("data") or [{}])[0].get("b64_json")


def azure_edit_image_b64(prompt: str, image_b64_list: List[str], size: str = "1024x1024", timeout: int = 300) -> Optional[str]:
    dep = _env("AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1")
    if not dep:
        return None
    endpoint = (_env("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
    url = f"{endpoint}/openai/deployments/{dep}/images/edits?api-version={_env('AZURE_OPENAI_API_VERSION')}"
    headers = {"api-key": _env("AZURE_OPENAI_API_KEY")}
    field = "image" if len(image_b64_list) == 1 else "image[]"
    files = [(field, (f"img{i}.png", base64.b64decode(b), "image/png")) for i, b in enumerate(image_b64_list)]
    resp = requests.post(url, headers=headers, files=files, data={"prompt": prompt[:3900], "size": size, "n": "1"}, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Azure image edit failed HTTP {resp.status_code}: {resp.text[:300]}")
    return (resp.json().get("data") or [{}])[0].get("b64_json")


def _extract_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    s, e = cleaned.find("{"), cleaned.rfind("}")
    if s == -1 or e == -1 or e <= s:
        raise ValueError("No JSON object found")
    return json.loads(cleaned[s:e + 1])


def _safe(d: Dict[str, Any], k: str, default: Any = "") -> Any:
    v = d.get(k, default)
    return default if v is None else v


def _as_dict(a: Any) -> Dict[str, Any]:
    if isinstance(a, dict):
        return a
    if hasattr(a, "model_dump"):
        return a.model_dump()
    if hasattr(a, "dict"):
        return a.dict()
    return {}


class QuadCreativeOrchestrator:
    def __init__(self, prompt: str, style: str, make_images: bool, rounds: int,
                 agents: List[Any], emit: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self.id = uuid.uuid4().hex
        self.prompt = prompt
        self.style = style
        self.rounds = max(1, min(int(rounds), 6))
        self.make_images = bool(make_images) and bool(_env("AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1"))
        self.rag = ArtHistoryRAG()
        padded = (list(agents) + [{}, {}, {}, {}])[:4]
        self.agents = [PersonaAgent(i, _as_dict(a), self.rag) for i, a in enumerate(padded)]
        self.stopped = False
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._external_emit = emit
        self.thread = threading.Thread(target=self.run, daemon=True)

    def emit(self, e: Dict[str, Any]) -> None:
        self.events.put(e)
        if self._external_emit:
            try:
                self._external_emit(e)
            except Exception:
                pass

    def start(self) -> None:
        self.thread.start()

    def _agent_turn(self, agent: PersonaAgent, ident: Dict[str, str], canvas_objects: str,
                    transcript: List[str], is_first: bool) -> Dict[str, Any]:
        system = agent.system_prompt(self.style)
        enrich = ("\nStylistic keywords to honour: " + ident["enrich"]) if ident["enrich"] else ""
        if is_first:
            task = ("The shared canvas is BLANK. Choose ONE strong primary element to BEGIN the painting, expressed "
                    "through your persona. Put it in 'new_object'.")
        else:
            task = (f"The shared canvas already contains: {canvas_objects}. ADD exactly ONE NEW, DISTINCT element that "
                    f"complements the whole AND expresses your persona. Do NOT restyle or repeat existing elements.")
        schema = ('Return ONLY valid JSON: {"sender":"' + agent.name + '","sees_on_canvas":"<already painted>",'
                  '"new_object":"<the SINGLE new object>","where":"<placement>","palette":["#hex"],'
                  '"reasoning":"<why it fits your persona and the whole>","confidence_score":0.0}')
        convo = ("\n\nCollaboration so far:\n" + "\n".join(transcript[-8:])) if transcript else ""
        user = (f"Shared brief: {self.prompt}\nStyle: {self.style or 'cohesive painterly'}{enrich}{convo}\n\n"
                f"Task: {task}\nStay fully in character. {schema}")
        raw = azure_chat_completion([{"role": "system", "content": system}, {"role": "user", "content": user}])
        try:
            data = _extract_json(raw)
        except Exception:
            data = {"sender": agent.name, "sees_on_canvas": canvas_objects or "blank canvas",
                    "new_object": (raw[:80] or "a new element"), "where": "the canvas",
                    "palette": [], "reasoning": raw[:300], "confidence_score": 0.7}
        data["sender"] = agent.name
        return data

    def _run_critic(self, canvas_objects: str, transcript: List[str]) -> Dict[str, Any]:
        system = ("You are JUDGE, a rigorous art critic. You do NOT edit the painting. You assess how well the four "
                  "agents collaborated in strict sequence, each building on the last, and summarise the result.")
        schema = ('Return ONLY JSON: {"scores":{"compositional_coherence":0.0,"style_fidelity":0.0,'
                  '"emotional_resonance":0.0,"originality":0.0,"collaboration_quality":0.0,"composite":0.0},'
                  '"reasoning":"...","highlights":["..."],"final_summary":"..."}')
        user = (f"Brief: {self.prompt}\nStyle: {self.style or 'cohesive painterly'}\n"
                f"Everything the four agents added to the single shared canvas, in order:\n" + "\n".join(transcript) +
                f"\n\nThe finished canvas contains: {canvas_objects}\nScore strictly 0-10; judge the SEQUENTIAL "
                f"COLLABORATION too. {schema}")
        raw = azure_chat_completion([{"role": "system", "content": system}, {"role": "user", "content": user}])
        try:
            return _extract_json(raw)
        except Exception:
            return {"scores": {"compositional_coherence": 7, "style_fidelity": 7, "emotional_resonance": 7,
                    "originality": 7, "collaboration_quality": 7, "composite": 7.0},
                    "reasoning": raw[:500], "highlights": [], "final_summary": "A sequential collaborative artwork."}

    def run(self) -> None:
        start = time.time()
        transcript: List[str] = []
        added: List[str] = []
        current: Optional[str] = None
        turn = 0
        total = self.rounds * 4
        idents = [a.identity(self.style) for a in self.agents]

        self.emit({"type": "session", "mode": "quad", "prompt": self.prompt, "style": self.style,
                   "images": self.make_images, "rounds": self.rounds, "total_turns": total,
                   "agents": [{"index": i, "name": self.agents[i].name, "persona_name": idents[i]["persona_name"],
                               "expertise": self.agents[i].expertise, "custom": bool(self.agents[i].custom_prompt)}
                              for i in range(4)]})
        stopped_early = False
        try:
            for rnd in range(1, self.rounds + 1):
                for idx in range(4):
                    if self.stopped:
                        stopped_early = True
                        break
                    agent = self.agents[idx]
                    ident = idents[idx]
                    turn += 1
                    is_first = (current is None and not added)
                    canvas_objects = ", ".join(added) if added else "blank canvas"
                    self.emit({"type": "turn", "turn": turn, "total": total, "round": rnd, "agent_idx": idx,
                               "name": agent.name, "persona_name": ident["persona_name"], "expertise": agent.expertise})
                    msg = self._agent_turn(agent, ident, canvas_objects, transcript, is_first)
                    new_object = str(_safe(msg, "new_object", "a new element")).strip() or "a new element"
                    self.emit({"type": "agent", "agent_idx": idx, "name": agent.name, "turn": turn, "round": rnd,
                               "persona_name": ident["persona_name"], "object": new_object, "message": msg})
                    transcript.append(f"R{rnd} - {agent.name} ({ident['persona_name']}) added '{new_object}' "
                                      f"({_safe(msg,'where','')}).")
                    added.append(new_object)

                    if self.make_images:
                        self.emit({"type": "image_pending", "turn": turn, "agent_idx": idx, "name": agent.name})
                        try:
                            if is_first:
                                gp = (f"A painting - {ident['image_style']}. The very BEGINNING of an artwork about: "
                                      f"{self.prompt}. The canvas currently contains ONLY one element: {new_object}. "
                                      f"Large empty unpainted areas, minimal. Overall style: {self.style or 'cohesive painterly'}.")
                                current = azure_generate_image_b64(gp)
                            else:
                                ep = (f"Add exactly ONE new element to this existing painting: {new_object} (placed at "
                                      f"{_safe(msg,'where','an empty area')}), rendered {ident['image_style']}. CRITICAL: "
                                      f"keep everything already present EXACTLY as it is; ONLY ADD the one new element. "
                                      f"Theme: {self.prompt}. Style: {self.style or 'cohesive painterly'}.")
                                current = azure_edit_image_b64(ep, [current])
                            if current:
                                self.emit({"type": "image", "turn": turn, "total": total, "round": rnd, "agent_idx": idx,
                                           "name": agent.name, "object": new_object,
                                           "label": f"R{rnd} - Agent {idx+1} ({ident['persona_name']}): {new_object}",
                                           "image": "data:image/png;base64," + current})
                        except Exception as exc:
                            self.emit({"type": "warning", "message": f"Turn {turn} ({agent.name}) image step failed: {exc}"})
                if stopped_early:
                    break

            if stopped_early:
                self.emit({"type": "warning", "message": "Stopped early by user - presenting the work so far"})

            # JUDGE — scores the sequential collaboration (no edits), like the ARIA/NEXUS critic.
            self.emit({"type": "turn", "turn": "JUDGE", "total": total, "agent_idx": None,
                       "name": "JUDGE", "persona_name": "Critic", "expertise": "-"})
            evaluation = self._run_critic(", ".join(added), transcript)
            self.emit({"type": "critic", "evaluation": evaluation})
            try:
                composite = float(evaluation.get("scores", {}).get("composite", 0.0))
            except Exception:
                composite = 0.0

            if self.make_images and current:
                self.emit({"type": "final", "label": "Final combined artwork (4-agent chain)",
                           "image": "data:image/png;base64," + current})
            self.emit({"type": "summary", "outcome": "Completed", "turns": turn, "objects": added,
                       "rounds": self.rounds, "composite": composite, "elapsed": round(time.time() - start, 1)})
        except Exception as exc:
            self.emit({"type": "error", "message": str(exc)})
        finally:
            self.emit({"type": "done"})
