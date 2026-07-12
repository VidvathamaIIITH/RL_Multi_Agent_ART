#!/usr/bin/env python3
"""CanvasMind — application entry point (FastAPI routes + server).

The system is split into five files, all in this directory:
    canvasmind_core.py  config, Azure REST, per-session storage, personas,
                        memory stream + reflection, and the RL layer (shared)
    canvasmind_dual.py  the two-agent ARIA/NEXUS Session
    canvasmind_quad.py  the four-agent QuadSession + ArtHistoryRAG
    canvasmind_ui.py    the embedded single-page UI (INDEX_HTML)
    canvasmind_app.py   this file: the HTTP/SSE routes and main()

Everything still runs on ONE port from ONE process, exactly as before.
Run:  python canvasmind_app.py --port 8000
"""
from __future__ import annotations
from canvasmind_core import *                       # noqa: F401,F403
from canvasmind_dual import Session
from canvasmind_quad import QuadSession, QUAD_PERSONAS
from canvasmind_ui import INDEX_HTML


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
        "personas": PERSONA_KEYS,
    })


@app.get("/api/personas")
def list_personas() -> JSONResponse:
    """The 8 generative-agent personas offered to every agent slot (dual + quad)."""
    return JSONResponse({"personas": personas_catalog()})


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
        aria_persona=(body.get("aria_persona") or PERSONA_KEYS[0]),
        nexus_persona=(body.get("nexus_persona") or PERSONA_KEYS[1]),
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
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_completion_tokens=400, purpose="inspire"))
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


def _session_dir(number: int) -> Path:
    return DATA_DIR / f"session_{int(number):04d}"


@app.get("/api/sessions")
def list_sessions() -> JSONResponse:
    """Every recorded session, newest first."""
    out: List[Dict[str, Any]] = []
    if DATA_DIR.exists():
        for d in sorted(DATA_DIR.glob("session_*"), reverse=True):
            manifest = d / "session.json"
            if manifest.exists():
                try:
                    out.append(json.loads(manifest.read_text(encoding="utf-8")))
                    continue
                except Exception:
                    pass
            m = re.fullmatch(r"session_(\d+)", d.name)
            if m:
                out.append({"session_number": int(m.group(1)), "status": "in progress or incomplete"})
    return JSONResponse({"sessions": out, "root": str(DATA_DIR)})


@app.get("/api/sessions/{number}")
def get_session(number: int) -> JSONResponse:
    d = _session_dir(number)
    if not d.exists():
        return JSONResponse({"error": f"session {number} not found"}, status_code=404)
    manifest = d / "session.json"
    body: Dict[str, Any] = {"session_number": number, "path": str(d)}
    if manifest.exists():
        try:
            body.update(json.loads(manifest.read_text(encoding="utf-8")))
        except Exception:
            pass
    body["json_files"] = sorted(p.relative_to(d).as_posix() for p in (d / "json").rglob("*.json*"))
    body["images"] = sorted(p.name for p in (d / "images").glob("*.png"))
    return JSONResponse(body)


@app.get("/api/sessions/{number}/images/{filename}")
def get_session_image(number: int, filename: str):
    p = (_session_dir(number) / "images" / filename).resolve()
    root = (_session_dir(number) / "images").resolve()
    if root not in p.parents or not p.exists():   # no path traversal
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(p))


@app.post("/api/sessions/{number}/participant")
async def save_participant(number: int, request: Request) -> JSONResponse:
    """Pre-session form (age / gender / art expertise), stored with the session."""
    d = _session_dir(number)
    if not d.exists():
        return JSONResponse({"error": f"session {number} not found"}, status_code=404)
    body = await request.json()
    (d / "json" / "participant.json").write_text(
        json.dumps({"recorded_at": _utcnow(), **body}, ensure_ascii=False, indent=2), encoding="utf-8")
    return JSONResponse({"status": "saved", "session_number": number})


@app.post("/api/sessions/{number}/survey")
async def save_survey(number: int, request: Request) -> JSONResponse:
    """Post-session experience survey, stored with the session."""
    d = _session_dir(number)
    if not d.exists():
        return JSONResponse({"error": f"session {number} not found"}, status_code=404)
    body = await request.json()
    (d / "json" / "survey.json").write_text(
        json.dumps({"recorded_at": _utcnow(), **body}, ensure_ascii=False, indent=2), encoding="utf-8")
    return JSONResponse({"status": "saved", "session_number": number})


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


@app.get("/assets/quad-hero")
def quad_hero_image():
    """Serve the Quad-Agent hero image (drop one at assets/4_Agent_Art.png)."""
    base = APP_DIR / "assets"
    for name in ("4_Agent_Art.png", "4_Agent_Art.jpg", "quad-hero.png", "quad_hero.png", "quad-hero.jpg", "quad-hero.webp"):
        p = base / name
        if p.exists():
            return FileResponse(str(p))
    return JSONResponse({"error": "no quad hero image — drop one at assets/4_Agent_Art.png"}, status_code=404)


@app.get("/api/quad/personas")
def quad_personas() -> JSONResponse:
    return JSONResponse({
        # artistic voices (how the agent paints) — key kept as `personas` for backwards compatibility
        "personas": [{"key": k, "name": v["name"], "blurb": v["blurb"]} for k, v in QUAD_PERSONAS.items()],
        "voices": [{"key": k, "name": v["name"], "blurb": v["blurb"]} for k, v in QUAD_PERSONAS.items()],
        # the 8 generative-agent identities (who the agent is)
        "identities": personas_catalog(),
    })


@app.post("/api/quad/start")
async def quad_start(request: Request) -> JSONResponse:
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)
    persona_keys = list(QUAD_PERSONAS.keys())
    agents_in = body.get("agents") or []
    agents: List[Dict[str, Any]] = []
    for i in range(4):
        a = agents_in[i] if i < len(agents_in) and isinstance(agents_in[i], dict) else {}
        voice = a.get("persona") if a.get("persona") in QUAD_PERSONAS else persona_keys[i % len(persona_keys)]
        pid = a.get("persona_id") if a.get("persona_id") in AGENT_PERSONAS else PERSONA_KEYS[i % len(PERSONA_KEYS)]
        agents.append({"name": (a.get("name") or f"Agent {i+1}").strip(),
                       "persona": voice,                 # artistic voice
                       "custom_prompt": (a.get("custom_prompt") or "").strip(),
                       "persona_id": pid})               # generative-agent identity
    sess = QuadSession(prompt=prompt, style=(body.get("style") or "").strip(),
                       make_images=bool(body.get("images", True)), rounds=int(body.get("rounds", 1)),
                       agents=agents)
    SESSIONS[sess.id] = sess
    sess.start()
    return JSONResponse({"session_id": sess.id})


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


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
