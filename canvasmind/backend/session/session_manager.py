from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from schemas.agent_message import AgentMessage
from schemas.critic_evaluation import CriticEvaluation
from schemas.session_schemas import (
    CanvasStateModel,
    Session,
    SessionStatus,
    SessionSummary,
)

logger = logging.getLogger(__name__)
_STORAGE = Path(settings.session_storage_path)


class SessionManager:
    def __init__(self) -> None:
        _STORAGE.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return _STORAGE / f"{session_id}.json"

    async def create_session(self, prompt: str, config: Dict[str, Any]) -> Session:
        title = config.get("title") or f"Session: {prompt[:40]}..."
        max_rounds = int(config.get("max_rounds", settings.max_rounds))
        session = Session(
            title=title,
            user_prompt=prompt,
            max_rounds=max_rounds,
            canvas_state=CanvasStateModel(),
            metadata={"style_hint": config.get("style_hint", ""), "era_hint": config.get("era_hint", "")},
        )
        await self.save_session(session)
        return session

    async def get_session(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not path.exists():
            raise ValueError(f"Session {session_id} not found")
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, path.read_text, "utf-8")
        data = json.loads(text)
        return Session(**data)

    async def save_session(self, session: Session) -> None:
        session.updated_at = datetime.utcnow()
        path = self._path(session.session_id)
        tmp = path.with_suffix(".tmp")
        loop = asyncio.get_event_loop()
        payload = session.model_dump_json(indent=2)
        await loop.run_in_executor(None, lambda: tmp.write_text(payload, encoding="utf-8"))
        await loop.run_in_executor(None, tmp.replace, path)

    async def list_sessions(self) -> List[SessionSummary]:
        summaries = []
        for p in sorted(_STORAGE.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(None, p.read_text, "utf-8")
                data = json.loads(text)
                summaries.append(
                    SessionSummary(
                        session_id=data["session_id"],
                        title=data["title"],
                        user_prompt=data["user_prompt"],
                        status=SessionStatus(data["status"]),
                        current_round=data["current_round"],
                        max_rounds=data["max_rounds"],
                        convergence_score=data.get("convergence_score", 0.0),
                        created_at=datetime.fromisoformat(data["created_at"]),
                        updated_at=datetime.fromisoformat(data["updated_at"]),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to load session {p}: {e}")
        return summaries

    async def delete_session(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()

    async def rollback_to_round(self, session_id: str, round_num: int) -> Session:
        session = await self.get_session(session_id)
        session.messages = [m for m in session.messages if m.round <= round_num]
        session.critic_evaluations = [e for e in session.critic_evaluations if e.round <= round_num]
        session.current_round = round_num
        session.status = SessionStatus.PAUSED

        from canvas.canvas_manager import CanvasManager
        cm = CanvasManager()
        session.canvas_state = cm.rollback_to_round(session.canvas_state, round_num)

        await self.save_session(session)
        return session

    async def add_message(self, session_id: str, message: AgentMessage) -> None:
        session = await self.get_session(session_id)
        session.messages.append(message)
        await self.save_session(session)

    async def update_critic(self, session_id: str, evaluation: CriticEvaluation) -> None:
        session = await self.get_session(session_id)
        session.critic_evaluations.append(evaluation)
        if evaluation.scores.composite > 0:
            recent = session.critic_evaluations[-3:]
            session.convergence_score = sum(e.scores.composite for e in recent) / len(recent) / 10.0
        await self.save_session(session)

    async def record_intervention(self, session_id: str, intervention: Dict[str, Any]) -> None:
        session = await self.get_session(session_id)
        intervention["timestamp"] = datetime.utcnow().isoformat()
        session.user_interventions.append(intervention)
        await self.save_session(session)
