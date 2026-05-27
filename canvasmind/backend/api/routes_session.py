from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException

from orchestration.orchestrator import CreativeOrchestrator
from canvas.canvas_manager import CanvasManager
from providers.azure_openai_provider import AzureOpenAIProvider
from schemas.session_schemas import (
    CreateSessionRequest,
    Session,
    SessionSummary,
)
from session.session_manager import SessionManager
from websocket.ws_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_session_manager = SessionManager()
_provider = AzureOpenAIProvider()
_canvas_manager = CanvasManager()
_active_orchestrators: Dict[str, CreativeOrchestrator] = {}


@router.post("", response_model=Session)
async def create_session(body: CreateSessionRequest) -> Session:
    config = {
        "title": body.title,
        "max_rounds": body.max_rounds,
        "style_hint": body.style_hint or "",
        "era_hint": body.era_hint or "",
    }
    session = await _session_manager.create_session(body.prompt, config)
    return session


@router.get("", response_model=List[SessionSummary])
async def list_sessions() -> List[SessionSummary]:
    return await _session_manager.list_sessions()


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str) -> Session:
    try:
        return await _session_manager.get_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> Dict[str, str]:
    try:
        await _session_manager.delete_session(session_id)
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/start")
async def start_session(session_id: str, background_tasks: BackgroundTasks) -> Dict[str, str]:
    try:
        session = await _session_manager.get_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if session_id in _active_orchestrators:
        raise HTTPException(status_code=409, detail="Session already running")

    orchestrator = CreativeOrchestrator(
        session=session,
        provider=_provider,
        ws_manager=ws_manager,
        session_manager=_session_manager,
        canvas_manager=_canvas_manager,
    )
    _active_orchestrators[session_id] = orchestrator
    background_tasks.add_task(_run_and_cleanup, orchestrator, session_id)
    return {"status": "started", "session_id": session_id}


async def _run_and_cleanup(orchestrator: CreativeOrchestrator, session_id: str) -> None:
    try:
        await orchestrator.run_session()
    finally:
        _active_orchestrators.pop(session_id, None)


def get_orchestrator(session_id: str) -> CreativeOrchestrator:
    orch = _active_orchestrators.get(session_id)
    if not orch:
        raise HTTPException(status_code=404, detail="No active orchestrator for this session")
    return orch
