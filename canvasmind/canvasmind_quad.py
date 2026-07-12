#!/usr/bin/env python3
"""CanvasMind — QUAD pipeline: four independently-configured persona agents in
strict sequence (``QuadSession``) plus ``ArtHistoryRAG``. No RL layer. Split out
of canvasmind_app.py; shared infrastructure comes from canvasmind_core."""
from __future__ import annotations
from canvasmind_core import *  # noqa: F401,F403


# ===========================================================================
#  QUAD-AGENT SEQUENTIAL PIPELINE  (advanced view — isolated from ARIA/NEXUS)
# ===========================================================================
# Four independently-configurable persona agents each add one object, in strict
# sequence, per round. No JUDGE — pure additive co-creation. Reuses the same
# Azure REST calls, the SESSIONS registry, the /api/stream SSE and /api/stop.

QUAD_PERSONAS: Dict[str, Dict[str, Any]] = {
    "vanguard_minimalist": {
        "name": "The Vanguard Minimalist",
        "blurb": "Negative space, geometric simplicity, raw restraint.",
        "identity": ("a Vanguard Minimalist: you revere negative space, geometric clarity and raw restraint; you add "
                     "the fewest, most deliberate marks; you strip away rather than embellish and trust emptiness to "
                     "carry meaning."),
        "image_style": "stark minimalist composition, vast negative space, precise geometry, muted monochrome palette",
        "keywords": ["minimalism", "negative space", "geometric", "bauhaus"],
    },
    "neo_noir_cyberpunk": {
        "name": "The Neo-Noir Cyberpunk",
        "blurb": "High-contrast neon, rainy streets, dystopian industry.",
        "identity": ("a Neo-Noir Cyberpunk: you are obsessed with high-contrast neon, rain-slicked streetscapes, "
                     "holographic signage and dystopian industrial texture; you add glowing, gritty, electric elements."),
        "image_style": "neo-noir cyberpunk, high-contrast neon glow, rain reflections, wet asphalt, dystopian industrial detail",
        "keywords": ["cyberpunk", "neon", "noir", "glitch"],
    },
    "biomorphic_surrealist": {
        "name": "The Biomorphic Surrealist",
        "blurb": "Organic, fluid, dream-like, uncanny melting forms.",
        "identity": ("a Biomorphic Surrealist: you introduce organic, fluid, dream-like elements and uncanny melting "
                     "structures; your additions feel grown rather than built, unsettling and strangely alive."),
        "image_style": "biomorphic surrealism, fluid organic melting forms, dreamlike uncanny detail, soft iridescence",
        "keywords": ["surrealism", "biomorphic", "organic", "dreamlike"],
    },
    "baroque_traditionalist": {
        "name": "The Baroque Traditionalist",
        "blurb": "Deep chiaroscuro, classical symmetry, ornate gold.",
        "identity": ("a Baroque Traditionalist: you demand deep chiaroscuro, classical symmetry, ornate gold detailing "
                     "and dramatic directional lighting; your additions are richly modelled and theatrically lit."),
        "image_style": "baroque oil painting, deep chiaroscuro, dramatic single-source light, ornate gilded detail, classical symmetry",
        "keywords": ["baroque", "chiaroscuro", "classical", "gold"],
    },
    "kinetic_futurist": {
        "name": "The Kinetic Futurist",
        "blurb": "Motion vectors, speed lines, fractured energy.",
        "identity": ("a Kinetic Futurist: you emphasise sharp motion vectors, speed lines, chaotic energy and fractured "
                     "perspectives; your additions imply violent movement and dynamism frozen mid-flight."),
        "image_style": "futurist dynamism, sharp motion vectors, speed lines, fractured multi-perspective, energetic diagonals",
        "keywords": ["futurism", "kinetic", "motion", "fractured"],
    },
    "luminous_impressionist": {
        "name": "The Luminous Impressionist",
        "blurb": "Broken colour, shimmering light, soft atmosphere.",
        "identity": ("a Luminous Impressionist: you build with broken colour and shimmering light; you add soft "
                     "atmospheric passages of dappled, vibrating hue that dissolve hard edges into air."),
        "image_style": "impressionist broken colour, dappled shimmering light, soft atmospheric edges, plein-air luminosity",
        "keywords": ["impressionism", "broken colour", "light", "atmosphere"],
    },
}


def quad_persona_modifier(persona_key: str) -> str:
    """Layers the chosen human persona (who the agent IS) onto its artistic voice."""
    p = persona_spec(persona_key)
    return (f"You are also {p['name']}, a {p['age']}-year-old {p['occupation']}. Innate traits: {p['innate']}. "
            f"{p['learned']} Currently: {p['currently']} Speak in this voice: {p['voice']}. Your life and trade "
            f"must be legible in the single element you add.")


class ArtHistoryRAG:
    """Lean keyword-matching context router (no external vector store). When an
    agent's persona/brief mentions a known style or technique, it injects precise
    stylistic keywords to enrich the prompt. The interface mirrors a retriever so
    it can later be swapped for a true embedding vector store."""

    KB: Dict[str, str] = {
        "chiaroscuro": "strong light-dark modelling, a single dramatic light source, deep velvety shadow",
        "baroque": "theatrical movement, ornate gilded ornament, rich tenebrism, classical grandeur",
        "surrealism": "dream logic, impossible juxtapositions, uncanny scale, melting organic form",
        "biomorphic": "curved organic contours, cell-like structures, forms that appear grown not built",
        "cyberpunk": "neon signage, holographic haze, rain-wet reflection, dense industrial decay",
        "neon": "saturated emissive colour, glowing rim light, bloom and reflection on wet surfaces",
        "noir": "hard shadows, low-key lighting, silhouetted figures, moody high contrast",
        "minimalism": "extreme reduction, generous negative space, precise geometry, restrained palette",
        "bauhaus": "primary colours, clean geometry, functional balance, sans-serif rigor",
        "futurism": "dynamic diagonals, motion blur, repeated forms implying speed, fractured planes",
        "impressionism": "broken brushwork, dappled light, vibrating complementary colour, soft edges",
        "ukiyo-e": "flat colour planes, bold contour lines, woodblock texture, asymmetric composition",
        "art nouveau": "sinuous whiplash curves, botanical motifs, decorative linear rhythm",
        "brutalism": "raw concrete mass, monolithic geometry, stark shadow, heavy monumental weight",
        "vaporwave": "pastel neon gradients, retro-digital glitch, marble-and-chrome kitsch",
        "gothic": "pointed arches, spectral gloom, intricate tracery, vertical aspiration",
    }

    def enrich(self, text: str, max_hits: int = 3) -> str:
        low = (text or "").lower()
        hits: List[str] = []
        for key, val in self.KB.items():
            if key in low and val not in hits:
                hits.append(val)
            if len(hits) >= max_hits:
                break
        return "; ".join(hits)


class QuadSession:
    """Sequential 4-agent additive orchestrator. Compatible with the SESSIONS
    registry, /api/stream (SSE) and /api/stop, exactly like Session."""

    def __init__(self, prompt: str, style: str, make_images: bool, rounds: int,
                 agents: List[Dict[str, Any]]):
        self.id = uuid.uuid4().hex
        self.prompt = prompt
        self.style = style
        self.rounds = max(1, min(int(rounds), 6))
        self.make_images = make_images and bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1)
        self.agents = (list(agents) + [{}, {}, {}, {}])[:4]
        self.rag = ArtHistoryRAG()
        self.stopped = False
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.recorder: Optional[SessionRecorder] = None
        self.session_number: Optional[int] = None
        try:
            self.recorder = SessionRecorder(self.id, "quad")
            self.session_number = self.recorder.number
        except Exception as exc:
            print(f"[CanvasMind] WARNING: session store unavailable: {exc}")
        self.thread = threading.Thread(target=self._run, daemon=True)

    def emit(self, e: Dict[str, Any]) -> None:
        if self.recorder is not None:
            try:
                self.recorder.log_event(e)
            except Exception:
                pass
        self.events.put(e)

    def start(self) -> None:
        self.thread.start()

    def _identity(self, cfg: Dict[str, Any]) -> Dict[str, str]:
        custom = (cfg.get("custom_prompt") or "").strip()
        if custom:
            return {"identity": custom, "persona_name": (cfg.get("name") or "Custom Agent"),
                    "image_style": "in the artist's own described style",
                    "enrich": self.rag.enrich(custom + " " + self.style)}
        p = QUAD_PERSONAS.get(cfg.get("persona") or "") or list(QUAD_PERSONAS.values())[0]
        return {"identity": p["identity"], "persona_name": p["name"], "image_style": p["image_style"],
                "enrich": self.rag.enrich(" ".join([p["identity"]] + p.get("keywords", []) + [self.style]))}

    def _agent_turn(self, cfg, idx, ident, canvas_objects, transcript, is_first) -> Dict[str, Any]:
        name = cfg.get("name") or f"Agent {idx+1}"
        system = (f"You are {name}, {ident['identity']} {quad_persona_modifier(cfg.get('persona_id'))} "
                  f"You collaborate on ONE shared canvas, adding a single new object per turn and preserving all "
                  f"existing work.")
        enrich = ("\nStylistic keywords to honour: " + ident["enrich"]) if ident["enrich"] else ""
        if is_first:
            task = ("The shared canvas is BLANK. Choose ONE strong primary element to BEGIN the painting, expressed "
                    "through your persona. Put it in 'new_object'.")
        else:
            task = (f"The shared canvas already contains: {canvas_objects}. Look at what the previous agents added and "
                    f"ADD exactly ONE NEW, DISTINCT element that both complements the whole AND expresses your persona. "
                    f"Do NOT restyle or repeat existing elements.")
        schema = ('Return ONLY valid JSON: {"sender":"' + name + '","sees_on_canvas":"<what is already painted>",'
                  '"new_object":"<the SINGLE new object you add>","where":"<placement>","palette":["#hex"],'
                  '"reasoning":"<why this fits your persona and the whole>","confidence_score":0.0}')
        convo = ("\n\nCollaboration so far:\n" + "\n".join(transcript[-8:])) if transcript else ""
        user = (f"Shared brief: {self.prompt}\nStyle: {self.style or 'cohesive painterly'}{enrich}{convo}\n\n"
                f"Task: {task}\nStay fully in character. {schema}")
        raw = azure_chat_completion([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                    purpose="quad_agent")
        try:
            data = extract_json_object(raw)
        except Exception:
            data = {"sender": name, "sees_on_canvas": canvas_objects or "blank canvas",
                    "new_object": (raw[:80] or "a new element"), "where": "the canvas",
                    "palette": [], "reasoning": raw[:300], "confidence_score": 0.7}
        data["sender"] = name
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
        raw = probe_chat_completion([{"role": "system", "content": system},
                                     {"role": "user", "content": user}], purpose="judge")
        try:
            return extract_json_object(raw)
        except Exception:
            return {"scores": {"compositional_coherence": 7, "style_fidelity": 7, "emotional_resonance": 7,
                    "originality": 7, "collaboration_quality": 7, "composite": 7.0},
                    "reasoning": raw[:500], "highlights": [], "final_summary": "A sequential collaborative artwork."}

    def _run(self) -> None:
        set_recorder(self.recorder)          # the Azure wrappers log through this
        start = time.time()
        transcript: List[str] = []
        added: List[str] = []
        current_b64: Optional[str] = None
        turn = 0
        total = self.rounds * 4
        idents = [self._identity(c) for c in self.agents]

        self.emit({"type": "session", "mode": "quad", "prompt": self.prompt, "style": self.style,
                   "model": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52, "images": self.make_images,
                   "rounds": self.rounds, "total_turns": total,
                   "session_number": self.session_number,
                   "agents": [{"index": i, "name": (self.agents[i].get("name") or f"Agent {i+1}"),
                               "persona_name": idents[i]["persona_name"],
                               "persona_id": (self.agents[i].get("persona_id") or DEFAULT_PERSONA),
                               "persona_person": persona_spec(self.agents[i].get("persona_id") or DEFAULT_PERSONA)["name"],
                               "custom": bool((self.agents[i].get("custom_prompt") or "").strip())}
                              for i in range(4)]})
        stopped_early = False
        evaluation: Dict[str, Any] = {}
        try:
            for rnd in range(1, self.rounds + 1):
                for idx in range(4):
                    if self.stopped:
                        stopped_early = True
                        break
                    cfg = self.agents[idx]
                    ident = idents[idx]
                    name = cfg.get("name") or f"Agent {idx+1}"
                    turn += 1
                    turn_t0 = time.time()
                    is_first = (current_b64 is None and not added)
                    canvas_objects = ", ".join(added) if added else "blank canvas"
                    self.emit({"type": "turn", "turn": turn, "total": total, "round": rnd,
                               "agent_idx": idx, "name": name, "persona_name": ident["persona_name"],
                               "persona_person": persona_spec(cfg.get("persona_id") or DEFAULT_PERSONA)["name"]})
                    msg = self._agent_turn(cfg, idx, ident, canvas_objects, transcript, is_first)
                    reasoned_at = _utcnow()
                    new_object = str(safe_get(msg, "new_object", "a new element")).strip() or "a new element"
                    self.emit({"type": "agent", "agent_idx": idx, "name": name, "turn": turn, "round": rnd,
                               "persona_name": ident["persona_name"], "object": new_object, "message": msg})
                    transcript.append(f"R{rnd} - {name} ({ident['persona_name']}) added '{new_object}' "
                                      f"({safe_get(msg,'where','')}).")
                    added.append(new_object)

                    image_file = None
                    if self.make_images:
                        self.emit({"type": "image_pending", "turn": turn, "agent_idx": idx, "name": name})
                        try:
                            if is_first:
                                gp = (f"A painting - {ident['image_style']}. The very BEGINNING of an artwork about: "
                                      f"{self.prompt}. The canvas currently contains ONLY one element: {new_object}. "
                                      f"Large empty unpainted areas, minimal, just the first object blocked in. "
                                      f"Overall style: {self.style or 'cohesive painterly'}.")
                                current_b64 = azure_generate_image_b64(gp)
                            else:
                                ep = (f"Add exactly ONE new element to this existing painting: {new_object} "
                                      f"(placed at {safe_get(msg,'where','an appropriate empty area')}), rendered "
                                      f"{ident['image_style']}. CRITICAL: keep everything already in the painting EXACTLY "
                                      f"as it is - do not change, restyle, refine, or repaint existing objects, "
                                      f"composition, or colours. ONLY ADD the one new element. Theme: {self.prompt}. "
                                      f"Overall style: {self.style or 'cohesive painterly'}.")
                                current_b64 = azure_edit_image_b64(ep, [current_b64])
                            if current_b64:
                                if self.recorder is not None:
                                    image_file = self.recorder.save_image(current_b64, turn, name, new_object)
                                label = f"R{rnd} - Agent {idx+1} ({ident['persona_name']}): {new_object}"
                                self.emit({"type": "image", "turn": turn, "total": total, "round": rnd,
                                           "agent_idx": idx, "name": name, "object": new_object, "label": label,
                                           "image": "data:image/png;base64," + current_b64})
                        except Exception as exc:
                            self.emit({"type": "warning",
                                       "message": f"Turn {turn} ({name}) image step failed: {exc}"})

                    if self.recorder is not None:
                        self.recorder.log_turn({
                            "turn": turn, "round": rnd, "agent_idx": idx, "name": name,
                            "agent": name, "persona_voice": ident["persona_name"],
                            "persona_id": cfg.get("persona_id"),
                            "custom_prompt": cfg.get("custom_prompt") or None,
                            "rag_keywords": ident.get("enrich") or None,
                            "started_at": _utcnow(), "duration_ms": round((time.time() - turn_t0) * 1000, 1),
                            "brief": self.prompt, "style": self.style,
                            "canvas_before": canvas_objects,
                            "chosen": {"new_object": new_object, "where": safe_get(msg, "where", ""),
                                       "palette": msg.get("palette"), "sees_on_canvas": msg.get("sees_on_canvas"),
                                       "reasoning": safe_get(msg, "reasoning", ""),
                                       "confidence_score": msg.get("confidence_score")},
                            "reasoning": safe_get(msg, "reasoning", ""), "reasoned_at": reasoned_at,
                            "image_file": image_file,
                        })
                if stopped_early:
                    break

            if stopped_early:
                self.emit({"type": "warning", "message": "Stopped early by user - presenting the work so far"})

            # JUDGE — scores the sequential collaboration (no edits), like the ARIA/NEXUS critic.
            self.emit({"type": "turn", "turn": "JUDGE", "total": total, "agent_idx": None,
                       "name": "JUDGE", "persona_name": "Critic", "persona_person": "-"})
            evaluation = self._run_critic(", ".join(added), transcript)
            self.emit({"type": "critic", "evaluation": evaluation})
            try:
                composite = float(evaluation.get("scores", {}).get("composite", 0.0))
            except Exception:
                composite = 0.0

            if self.make_images and current_b64:
                if self.recorder is not None:
                    self.recorder.save_final_image(current_b64)
                self.emit({"type": "final", "label": "Final combined artwork (4-agent chain)",
                           "image": "data:image/png;base64," + current_b64})
            self.emit({"type": "summary", "outcome": "Stopped early" if stopped_early else "Completed",
                       "turns": turn, "objects": added, "session_number": self.session_number,
                       "rounds": self.rounds, "composite": composite, "elapsed": round(time.time() - start, 1)})
        except Exception as exc:
            self.emit({"type": "error", "message": str(exc)})
        finally:
            self._persist(evaluation, added, turn, stopped_early, start)
            self.emit({"type": "done"})
            set_recorder(None)

    def _persist(self, evaluation, added, turn, stopped_early, start) -> None:
        if self.recorder is None:
            return
        try:
            if evaluation:
                self.recorder.write_json("critic.json", evaluation)
            self.recorder.write_json("summary.json", {
                "outcome": "Stopped early" if stopped_early else "Completed",
                "turns": turn, "objects": added,
                "composite": float((evaluation.get("scores") or {}).get("composite", 0.0) or 0.0),
                "elapsed_s": round(time.time() - start, 1)})
            self.recorder.finalize({
                "brief": self.prompt, "style": self.style, "rounds": self.rounds,
                "turns_completed": turn, "stopped_early": stopped_early,
                "agents": [{"name": a.get("name"), "voice": a.get("persona"),
                            "persona_id": a.get("persona_id"),
                            "custom": bool((a.get("custom_prompt") or "").strip())} for a in self.agents],
                "objects": added,
                "text_deployment": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
                "probe_deployment": AZURE_OPENAI_DEPLOYMENT_PROBE or AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
                "image_deployment": AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1,
                "composite": float((evaluation.get("scores") or {}).get("composite", 0.0) or 0.0)})
        except Exception as exc:
            print(f"[CanvasMind] WARNING: could not finalize session store: {exc}")
