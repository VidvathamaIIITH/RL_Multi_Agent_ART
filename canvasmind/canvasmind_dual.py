#!/usr/bin/env python3
"""CanvasMind — DUAL pipeline: the two-agent ARIA/NEXUS ``Session`` (with the
inference-time RL layer). Split out of canvasmind_app.py; all shared
infrastructure comes from canvasmind_core."""
from __future__ import annotations
from canvasmind_core import *  # noqa: F401,F403  (config, Azure, storage, personas, memory, RL)


class Session:
    def __init__(self, prompt: str, style: str, make_images: bool, rounds: int,
                 aria_persona: str, nexus_persona: str, autonomy: float = 1.0, human_directive: str = ""):
        self.id = uuid.uuid4().hex
        self.prompt = prompt
        self.style = style
        self.rounds = max(1, min(int(rounds), 8))
        self.make_images = make_images and bool(AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1)
        self.personas = {"ARIA": aria_persona if aria_persona in AGENT_PERSONAS else PERSONA_KEYS[0],
                         "NEXUS": nexus_persona if nexus_persona in AGENT_PERSONAS else PERSONA_KEYS[1]}
        self.streams = {"ARIA": MemoryStream("ARIA"), "NEXUS": MemoryStream("NEXUS")}
        # RL / research layer state
        self.autonomy = max(0.0, min(1.0, float(autonomy)))   # 0 = human-led ... 1 = fully autonomous
        self.human_directive = (human_directive or "").strip()
        # Bandits persist across sessions (see get_bandit): one session gives an agent
        # only `rounds` pulls over 8 arms — far too few for UCB1 to learn anything.
        self.bandit = {"ARIA": get_bandit("ARIA"), "NEXUS": get_bandit("NEXUS")}
        self.reward_curve = {"ARIA": [], "NEXUS": []}
        self.empower = {"ARIA": [], "NEXUS": []}
        self.pareto: List[List[float]] = []
        # The Goodhart series is tagged by agent so its slope can be estimated WITHIN
        # agent: ARIA and NEXUS maximise different functionals of the same dimensions,
        # so a raw slope over the interleaved series tracks an alternating mixture.
        self.goodhart: Dict[str, List[Any]] = {"proxy": [], "independent": [], "agents": []}
        self.obj_records: List[Dict[str, Any]] = []
        # A marginal is only meaningful against the SAME agent's previous turn.
        self._prev_reward: Dict[str, Optional[float]] = {"ARIA": None, "NEXUS": None}
        self.stopped = False   # set True to halt the turns early; JUDGE then evaluates progress so far
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.recorder: Optional[SessionRecorder] = None
        self.session_number: Optional[int] = None
        try:
            self.recorder = SessionRecorder(self.id, "dual")
            self.session_number = self.recorder.number
        except Exception as exc:                     # storage must never block a run
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

    def _painter_turn(self, agent, other, persona_key, perceived, retrieved, transcript, is_first, now) -> Dict[str, Any]:
        summary = summary_description(agent, persona_key, self.streams[agent], now)
        msgs = build_painter_prompt(agent, persona_key, summary, self.prompt, self.style,
                                    perceived, retrieved, transcript, is_first, other)
        raw = azure_chat_completion(msgs, purpose="painter")
        try:
            data = extract_json_object(raw)
        except Exception:
            data = {"sender": agent, "sees_on_canvas": perceived or "blank canvas",
                    "new_object": (raw[:80] or "a new element"), "where": "the canvas",
                    "palette": [], "reasoning": raw[:300], "confidence_score": 0.7}
        data["sender"] = agent
        return data

    def _choose_action(self, agent, other, persona_key, perceived, full_objects,
                       retrieved, transcript, is_first, now):
        """Best-of-N policy + reward model: a UCB bandit picks a strategy, the agent
        samples N candidate additions pursuing it, the reward model scores each, and we
        select the argmax of this agent's (misaligned) weighted reward.

        `perceived` is what the persona can take in (bounded by vision_r) and drives
        the PROMPT; `full_objects` is the true canvas state and drives the REWARD."""
        t0 = time.time()
        strategy = self.bandit[agent].select()
        summary = summary_description(agent, persona_key, self.streams[agent], now)
        cands = generate_candidates(agent, persona_key, summary, self.prompt, self.style, perceived,
                                    retrieved, transcript, is_first, other, strategy, BEST_OF_N,
                                    self.autonomy, self.human_directive)
        if not cands:
            cands = [self._painter_turn(agent, other, persona_key, perceived, retrieved, transcript, is_first, now)]
        dims = score_candidate_rewards(cands, self.prompt, self.style, full_objects)
        scalars = [scalar_reward(agent, dims[i]) for i in range(len(cands))]
        best = max(range(len(cands)), key=lambda i: scalars[i])
        chosen, chosen_dims, chosen_reward = cands[best], dims[best], scalars[best]
        rejected = [{"object": str(cands[i].get("new_object", "")), "reward": scalars[i],
                     "reasoning": str(cands[i].get("reasoning", ""))}
                    for i in range(len(cands)) if i != best]
        self.bandit[agent].update(strategy, chosen_reward)
        emp = empowerment_from_rewards(scalars)
        self.empower[agent].append(emp)
        self.reward_curve[agent].append(chosen_reward)
        self.pareto.append([round(chosen_dims["compositional_coherence"], 2), round(chosen_dims["originality"], 2)])
        rl = {"reward": chosen_reward, "reward_dims": {k: round(chosen_dims[k], 1) for k in RL_DIMS},
              "strategy": strategy, "n_candidates": len(cands), "rejected": rejected,
              "empowerment": emp, "empowerment_informative": empowerment_is_informative(len(cands)),
              "resisted_human": bool(chosen.get("resisted_human")),
              "decided_at": _utcnow(), "decision_ms": round((time.time() - t0) * 1000, 1)}
        return chosen, chosen_dims, chosen_reward, rl, cands, scalars

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
        raw = probe_chat_completion([{"role": "system", "content": system},
                                     {"role": "user", "content": user}], purpose="judge")
        try:
            return extract_json_object(raw)
        except Exception:
            return {"scores": {"compositional_coherence": 7, "style_fidelity": 7, "emotional_resonance": 7,
                    "originality": 7, "collaboration_quality": 7, "composite": 7.0},
                    "reasoning": raw[:500], "highlights": [], "final_summary": "A collaborative artwork."}

    def _observe_and_maybe_reflect(self, agent, other, perceived, last_other, now) -> None:
        """Agent perceives as much of the canvas as vision_r allows, plus the other
        agent's latest move; stores them as memories and reflects if importance is high."""
        obs = [f"The shared canvas now shows: {perceived or 'a blank canvas'}."]
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
        set_recorder(self.recorder)          # the Azure wrappers log through this
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
                   "rounds": self.rounds, "total_turns": total,
                   "session_number": self.session_number,
                   "personas": {a: {"key": self.personas[a],
                                    "name": persona_spec(self.personas[a])["name"],
                                    "occupation": persona_spec(self.personas[a])["occupation"],
                                    "vision_r": persona_spec(self.personas[a])["vision_r"],
                                    "att_bandwidth": persona_spec(self.personas[a])["att_bandwidth"],
                                    "retention": persona_spec(self.personas[a])["retention"]}
                                for a in ("ARIA", "NEXUS")},
                   "best_of_n": BEST_OF_N,
                   "instruments_independent": instruments_are_independent(),
                   "embeddings": bool(AZURE_OPENAI_DEPLOYMENT_EMBED)})
        order = [("ARIA", "NEXUS"), ("NEXUS", "ARIA")]
        stopped_early = False
        evaluation: Dict[str, Any] = {}
        metrics: Dict[str, Any] = {}
        try:
            for rnd in range(1, self.rounds + 1):
                for agent, other in order:
                    if self.stopped:
                        stopped_early = True
                        break
                    turn += 1
                    now += 1
                    turn_t0 = time.time()
                    pkey = self.personas[agent]
                    pspec = persona_spec(pkey)
                    is_first = (current_b64 is None and not added)
                    full_objects = ", ".join(added) if added else "blank canvas"
                    perceived = perceived_canvas(added, pkey)     # bounded by vision_r
                    self.emit({"type": "turn", "turn": turn, "total": total,
                               "agent": agent, "persona": pkey, "persona_name": pspec["name"]})

                    # 1) PERCEIVE the canvas + the other agent's last move; REFLECT (learn).
                    self._observe_and_maybe_reflect(agent, other, perceived, last[other], now)

                    # 2) RETRIEVE memories relevant to the decision at hand.
                    query = (f"{self.prompt}. Current canvas: {perceived}. "
                             f"What single new object should {agent} add next?")
                    retrieved = [m["text"] for m in self.streams[agent].retrieve(
                        query, now, k=max(2, min(12, int(pspec.get("retention", RETRIEVE_K)))))]

                    # 3) ACT — best-of-N candidates + reward-model selection (inference-time RL).
                    msg, chosen_dims, chosen_reward, rl, cands, scalars = self._choose_action(
                        agent, other, pkey, perceived, full_objects, retrieved, transcript, is_first, now)
                    new_object = str(safe_get(msg, "new_object", "a new element")).strip() or "a new element"
                    # Goodhart monitor: optimized proxy reward vs. an independent quality probe,
                    # both computed on the FULL canvas, not the agent's bounded perception.
                    objs_after = ((full_objects + ", ") if full_objects != "blank canvas" else "") + new_object
                    indep = independent_quality(objs_after, self.prompt, self.style)
                    self.goodhart["proxy"].append(chosen_reward)
                    self.goodhart["independent"].append(indep)
                    self.goodhart["agents"].append(agent)
                    prev = self._prev_reward[agent]
                    marginal = None if prev is None else round(chosen_reward - prev, 3)
                    self._prev_reward[agent] = chosen_reward
                    self.obj_records.append({"turn": turn, "agent": agent, "object": new_object,
                                             "marginal": marginal, "reward": chosen_reward})
                    rl["proxy_reward"] = chosen_reward
                    rl["independent_quality"] = indep
                    rl["marginal_same_agent"] = marginal
                    self.emit({"type": "agent", "agent": agent, "persona": pkey,
                               "persona_name": pspec["name"], "turn": turn,
                               "object": new_object, "message": msg, "retrieved": retrieved[:4], "rl": rl})
                    if rl.get("resisted_human"):
                        self.emit({"type": "warning",
                                   "message": f"{agent} resisted the human directive (autonomy {self.autonomy:.2f})"})
                    transcript.append(f"Turn {turn} — {agent} added '{new_object}' ({safe_get(msg,'where','')}).")
                    added.append(new_object)
                    last[agent] = msg
                    # Reward-aware Reflexion: a low-reward turn triggers a learning reflection.
                    reflexion: List[str] = []
                    if chosen_reward < REFLEXION_REWARD_TRIGGER:
                        reflexion = reflect(self.streams[agent], agent, other, now)
                        if reflexion:
                            self.emit({"type": "reflection", "agent": agent, "insights": reflexion,
                                       "reason": "low reward (Reflexion)"})

                    # 4) PAINT — first turn generates; later turns ADD to the shared canvas.
                    image_file = None
                    if self.make_images:
                        self.emit({"type": "image_pending", "turn": turn, "agent": agent})
                        p = persona(agent, pkey)
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
                                if self.recorder is not None:
                                    image_file = self.recorder.save_image(current_b64, turn, agent, new_object)
                                self.emit({"type": "image", "turn": turn, "total": total, "agent": agent,
                                           "object": new_object, "label": f"{turn} · {agent} added: {new_object}",
                                           "image": "data:image/png;base64," + current_b64})
                        except Exception as exc:
                            self.emit({"type": "warning", "message": f"Turn {turn} ({agent}) image step failed: {exc}"})

                    # 5) STORE the agent's own action as a memory (scored for poignancy).
                    own = f"I, {agent}, added '{new_object}' ({safe_get(msg,'where','')}) building on {full_objects}."
                    self.streams[agent].add(own, "observation", now, score_importance(agent, [own])[0])

                    # 6) RECORD the complete turn.
                    if self.recorder is not None:
                        self.recorder.log_turn({
                            "turn": turn, "round": rnd, "agent": agent, "other": other,
                            "persona": pkey, "persona_name": pspec["name"],
                            "started_at": _utcnow(), "duration_ms": round((time.time() - turn_t0) * 1000, 1),
                            "brief": self.prompt, "style": self.style,
                            "canvas_before_full": full_objects,
                            "canvas_before_perceived": perceived,
                            "vision_r": pspec["vision_r"], "att_bandwidth": pspec["att_bandwidth"],
                            "retention": pspec["retention"],
                            "retrieved_memories": retrieved,
                            "strategy": rl["strategy"],
                            "candidates": [{"new_object": c.get("new_object"), "where": c.get("where"),
                                            "palette": c.get("palette"), "reasoning": c.get("reasoning"),
                                            "reward": scalars[i]} for i, c in enumerate(cands)],
                            "chosen": {"new_object": new_object, "where": safe_get(msg, "where", ""),
                                       "palette": msg.get("palette"), "sees_on_canvas": msg.get("sees_on_canvas"),
                                       "reasoning": safe_get(msg, "reasoning", ""),
                                       "confidence_score": msg.get("confidence_score")},
                            "reasoning": safe_get(msg, "reasoning", ""),
                            "reasoned_at": rl["decided_at"], "reasoning_ms": rl["decision_ms"],
                            "scores": {"reward": chosen_reward, "reward_dims": rl["reward_dims"],
                                       "independent_quality": indep, "marginal_same_agent": marginal,
                                       "empowerment": rl["empowerment"],
                                       "empowerment_informative": rl["empowerment_informative"]},
                            "reflexion_insights": reflexion,
                            "image_file": image_file,
                        })
                if stopped_early:
                    break

            if stopped_early:
                self.emit({"type": "warning",
                           "message": "Stopped early by user — JUDGE is evaluating the work completed so far"})

            # JUDGE — evaluates only; the final canvas is the accumulated result.
            self.emit({"type": "turn", "turn": "JUDGE", "total": total, "agent": "JUDGE", "persona": "-"})
            evaluation = self._run_critic(", ".join(added), transcript)
            self.emit({"type": "critic", "evaluation": evaluation})
            if self.make_images and current_b64:
                if self.recorder is not None:
                    self.recorder.save_final_image(current_b64)
                self.emit({"type": "final", "label": "Final combined artwork (both agents)",
                           "image": "data:image/png;base64," + current_b64})

            # ---- RESEARCH METRICS: Shapley credit · empowerment · Goodhart ----
            shapley = self._shapley_credit()
            gh = detect_goodhart(self.goodhart["proxy"], self.goodhart["independent"], self.goodhart["agents"])

            def _avg(xs):
                return round(sum(xs) / len(xs), 3) if xs else 0.0

            metrics = {
                "type": "metrics",
                "reward_model": "misaligned (ARIA→coherence, NEXUS→originality)",
                "best_of_n": BEST_OF_N, "autonomy": self.autonomy,
                "instruments_independent": instruments_are_independent(),
                "shapley": shapley["values"], "shapley_share": shapley["share"],
                "shapley_ci95": shapley["ci95"], "shapley_note": shapley["note"],
                "empowerment": {"ARIA": _avg(self.empower["ARIA"]), "NEXUS": _avg(self.empower["NEXUS"]),
                                "human": round(max(0.0, 1.0 - self.autonomy), 2),
                                "informative": empowerment_is_informative(BEST_OF_N)},
                "reward_curve": {"ARIA": [round(x, 2) for x in self.reward_curve["ARIA"]],
                                 "NEXUS": [round(x, 2) for x in self.reward_curve["NEXUS"]]},
                "pareto": self.pareto,
                "goodhart": {"proxy": [round(x, 2) for x in self.goodhart["proxy"]],
                             "independent": [round(x, 2) for x in self.goodhart["independent"]],
                             "agents": self.goodhart["agents"], **gh},
                "bandit": {"ARIA": self.bandit["ARIA"].best(3), "NEXUS": self.bandit["NEXUS"].best(3),
                           "pulls": {a: sum(self.bandit[a].pulls.values()) for a in ("ARIA", "NEXUS")},
                           "persisted": BANDIT_PERSIST},
                "objects": self.obj_records,
            }
            self.emit(metrics)
            _save_bandit_state()

            try:
                composite = float(evaluation.get("scores", {}).get("composite", 0.0))
            except Exception:
                composite = 0.0
            self.emit({"type": "summary", "outcome": "Stopped early" if stopped_early else "Completed",
                       "turns": turn, "objects": added, "composite": composite,
                       "session_number": self.session_number,
                       "memories": {a: len(self.streams[a].mem) for a in ("ARIA", "NEXUS")},
                       "elapsed": round(time.time() - start, 1)})
        except Exception as exc:
            self.emit({"type": "error", "message": str(exc)})
        finally:
            self._persist(evaluation, metrics, added, turn, stopped_early, start)
            self.emit({"type": "done"})
            set_recorder(None)

    def _shapley_credit(self) -> Dict[str, Any]:
        """Exact two-player Shapley value, with the uncertainty it is estimated under.

        phi_A = 1/2 [ v(A) + (v(AB) - v(B)) ],  v(empty) = 0.
        Efficiency (phi_A + phi_B = v(AB)) holds exactly for any v; precision does not,
        because v is an LLM estimate. We repeat the (batched) value query and report a
        95% interval, and we refuse to render a share when a value is negative."""
        try:
            aria_objs = [r["object"] for r in self.obj_records if r["agent"] == "ARIA"]
            nexus_objs = [r["object"] for r in self.obj_records if r["agent"] == "NEXUS"]
            all_objs = [r["object"] for r in self.obj_records]
            v = value_of_coalitions(aria_objs, nexus_objs, all_objs, self.prompt, self.style)
            vA, vB, vAB = v["vA"], v["vB"], v["vAB"]
            shap_A = round(0.5 * (vA + (vAB - vB)), 3)
            shap_B = round(0.5 * (vB + (vAB - vA)), 3)
            # Propagate the value-oracle spread into the credit estimate.
            sd = v.get("sd") or {}
            n = max(1, int(v.get("samples", 1)))
            se = 0.5 * math.sqrt(sum(float(sd.get(k, 0.0)) ** 2 for k in ("vA", "vB", "vAB")) / n)
            ci = round(1.96 * se, 3)
            tot = shap_A + shap_B
            if tot > 0 and shap_A >= 0 and shap_B >= 0:
                share = {"ARIA": round(100 * shap_A / tot, 1), "NEXUS": round(100 * shap_B / tot, 1)}
                note = (f"±{ci} on each value (n={n} samples of the value oracle). "
                        "A split this close to even is not evidence of asymmetric contribution.")
            else:
                share = {"ARIA": 50.0, "NEXUS": 50.0}
                note = ("The value oracle was not superadditive (a coalition scored below one of its "
                        "members), so a percentage split is not well defined; showing an even split.")
            return {"values": {"ARIA": shap_A, "NEXUS": shap_B}, "share": share,
                    "ci95": ci, "note": note, "coalition_values": {"vA": vA, "vB": vB, "vAB": vAB},
                    "efficiency_ok": abs((shap_A + shap_B) - vAB) < 1e-6}
        except Exception:
            return {"values": {"ARIA": 0.0, "NEXUS": 0.0}, "share": {"ARIA": 50.0, "NEXUS": 50.0},
                    "ci95": None, "note": "Shapley credit unavailable.", "coalition_values": {},
                    "efficiency_ok": False}

    def _persist(self, evaluation, metrics, added, turn, stopped_early, start) -> None:
        if self.recorder is None:
            return
        try:
            for a in ("ARIA", "NEXUS"):
                self.recorder.save_memory(a, self.streams[a])
            if evaluation:
                self.recorder.write_json("critic.json", evaluation)
            if metrics:
                self.recorder.write_json("metrics.json", {k: v for k, v in metrics.items() if k != "type"})
            self.recorder.write_json("summary.json", {
                "outcome": "Stopped early" if stopped_early else "Completed",
                "turns": turn, "objects": added,
                "composite": float((evaluation.get("scores") or {}).get("composite", 0.0) or 0.0),
                "elapsed_s": round(time.time() - start, 1)})
            self.recorder.finalize({
                "brief": self.prompt, "style": self.style, "rounds": self.rounds,
                "turns_completed": turn, "stopped_early": stopped_early,
                "personas": {a: self.personas[a] for a in ("ARIA", "NEXUS")},
                "autonomy": self.autonomy, "human_directive": self.human_directive,
                "best_of_n": BEST_OF_N, "objects": added,
                "text_deployment": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
                "probe_deployment": AZURE_OPENAI_DEPLOYMENT_PROBE or AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
                "image_deployment": AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1,
                "composite": float((evaluation.get("scores") or {}).get("composite", 0.0) or 0.0)})
        except Exception as exc:
            print(f"[CanvasMind] WARNING: could not finalize session store: {exc}")
