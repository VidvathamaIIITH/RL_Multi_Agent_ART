"""Quad-Agent Pipeline API (modular backend).

Uses Server-Sent Events (same event shapes as the single-file launcher) so the
React view can consume it with a plain EventSource. Isolated from the existing
ARIA/NEXUS WebSocket routes.
"""
from __future__ import annotations

import asyncio
import json
import queue
from typing import Dict

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from agents.persona_agent import EXPERTISE_LEVELS, QUAD_PERSONAS, personas_catalog
from orchestration.quad_orchestrator import QuadCreativeOrchestrator
from schemas.quad_session import QuadAgentSessionCreate

router = APIRouter(prefix="/api/quad", tags=["quad"])

_QSESSIONS: Dict[str, QuadCreativeOrchestrator] = {}


@router.get("/personas")
async def quad_personas() -> Dict:
    return {"personas": personas_catalog(), "levels": EXPERTISE_LEVELS}


_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


@router.get("/hero-image")
async def quad_hero_image():
    """Serve the Quad-Agent hero image (assets/4_Agent_Art.png) for the React view."""
    for name in ("4_Agent_Art.png", "4_Agent_Art.jpg", "quad-hero.png", "quad_hero.png", "quad-hero.webp"):
        p = _ASSETS_DIR / name
        if p.exists():
            return FileResponse(str(p))
    return JSONResponse({"error": "no quad hero image"}, status_code=404)


@router.post("/start")
async def quad_start(request: Request):
    body = await request.json()
    try:
        payload = QuadAgentSessionCreate(**body)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"invalid payload: {exc}"}, status_code=400)
    if not payload.prompt.strip():
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    keys = list(QUAD_PERSONAS.keys())
    raw_agents = [a.model_dump() for a in payload.agents]
    agents = []
    for i in range(4):
        a = raw_agents[i] if i < len(raw_agents) else {}
        persona = a.get("persona") if a.get("persona") in QUAD_PERSONAS else keys[i % len(keys)]
        expertise = a.get("expertise") if a.get("expertise") in EXPERTISE_LEVELS else "intermediate"
        agents.append({"name": (a.get("name") or f"Agent {i+1}").strip(), "persona": persona,
                       "custom_prompt": (a.get("custom_prompt") or "").strip(), "expertise": expertise})

    orch = QuadCreativeOrchestrator(prompt=payload.prompt.strip(), style=payload.style.strip(),
                                    make_images=payload.images, rounds=payload.rounds, agents=agents)
    _QSESSIONS[orch.id] = orch
    orch.start()
    return {"session_id": orch.id}


@router.get("/stream/{session_id}")
async def quad_stream(session_id: str) -> StreamingResponse:
    orch = _QSESSIONS.get(session_id)
    if not orch:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'session not found'})}\n\n"]),
            media_type="text/event-stream")

    async def gen():
        while True:
            try:
                ev = await asyncio.to_thread(orch.events.get, True, 20)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") == "done":
                _QSESSIONS.pop(session_id, None)
                break

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/stop/{session_id}")
async def quad_stop(session_id: str):
    orch = _QSESSIONS.get(session_id)
    if not orch:
        return JSONResponse({"error": "session not found"}, status_code=404)
    orch.stopped = True
    return {"status": "stopping", "session_id": session_id}
