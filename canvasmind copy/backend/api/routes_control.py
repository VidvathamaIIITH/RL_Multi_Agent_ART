from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from api.routes_session import _session_manager, get_orchestrator
from schemas.session_schemas import InterventionRequest, RollbackRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["control"])


@router.post("/{session_id}/pause")
async def pause_session(session_id: str) -> Dict[str, str]:
    orch = get_orchestrator(session_id)
    await orch.handle_user_intervention({"action": "pause"})
    return {"status": "paused", "session_id": session_id}


@router.post("/{session_id}/resume")
async def resume_session(session_id: str) -> Dict[str, str]:
    orch = get_orchestrator(session_id)
    await orch.handle_user_intervention({"action": "resume"})
    return {"status": "resumed", "session_id": session_id}


@router.post("/{session_id}/intervene")
async def intervene(session_id: str, body: InterventionRequest) -> Dict[str, str]:
    orch = get_orchestrator(session_id)
    await orch.handle_user_intervention(
        {"action": "inject", "instruction": body.instruction, "target_agent": body.target_agent}
    )
    return {"status": "injected", "session_id": session_id}


@router.post("/{session_id}/freeze/{agent}")
async def freeze_agent(session_id: str, agent: str) -> Dict[str, str]:
    if agent not in ("agent_a", "agent_b"):
        raise HTTPException(status_code=400, detail="agent must be agent_a or agent_b")
    orch = get_orchestrator(session_id)
    await orch.handle_user_intervention({"action": "freeze_agent", "agent": agent})
    return {"status": "frozen", "agent": agent}


@router.post("/{session_id}/unfreeze/{agent}")
async def unfreeze_agent(session_id: str, agent: str) -> Dict[str, str]:
    if agent not in ("agent_a", "agent_b"):
        raise HTTPException(status_code=400, detail="agent must be agent_a or agent_b")
    orch = get_orchestrator(session_id)
    await orch.handle_user_intervention({"action": "unfreeze_agent", "agent": agent})
    return {"status": "unfrozen", "agent": agent}


@router.post("/{session_id}/rollback/{round_num}")
async def rollback_session(session_id: str, round_num: int) -> Dict[str, Any]:
    try:
        session = await _session_manager.rollback_to_round(session_id, round_num)
        return {"status": "rolled_back", "session_id": session_id, "round": round_num}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/finalize")
async def finalize_session(session_id: str) -> Dict[str, str]:
    orch = get_orchestrator(session_id)
    await orch.handle_user_intervention({"action": "finalize"})
    return {"status": "finalizing", "session_id": session_id}


@router.post("/{session_id}/reset")
async def reset_session(session_id: str) -> Dict[str, str]:
    orch = get_orchestrator(session_id)
    await orch.handle_user_intervention({"action": "cancel"})
    session = await _session_manager.get_session(session_id)
    session.messages.clear()
    session.critic_evaluations.clear()
    session.current_round = 0
    from schemas.session_schemas import SessionStatus, CanvasStateModel
    session.status = SessionStatus.INITIALIZING
    session.canvas_state = CanvasStateModel()
    await _session_manager.save_session(session)
    return {"status": "reset", "session_id": session_id}


@router.post("/{session_id}/regenerate_round")
async def regenerate_round(session_id: str) -> Dict[str, str]:
    try:
        session = await _session_manager.get_session(session_id)
        if session.current_round > 0:
            await _session_manager.rollback_to_round(session_id, session.current_round - 1)
        return {"status": "regenerating", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
