from __future__ import annotations
from typing import Any, Dict, Optional

from schemas.agent_message import AgentMessage
from schemas.critic_evaluation import CriticEvaluation
from schemas.ws_events import WSEventType
from websocket.ws_manager import WebSocketManager


class EventEmitter:
    def __init__(self, ws_manager: WebSocketManager, session_id: str) -> None:
        self._ws = ws_manager
        self._session_id = session_id

    async def session_started(self, prompt: str) -> None:
        await self._ws.send_event(self._session_id, WSEventType.SESSION_STARTED, {"prompt": prompt})

    async def round_started(self, round_num: int) -> None:
        await self._ws.send_event(self._session_id, WSEventType.ROUND_STARTED, {"round": round_num}, round=round_num)

    async def agent_typing_start(self, agent: str, round_num: int) -> None:
        await self._ws.send_event(self._session_id, WSEventType.AGENT_TYPING_START, {}, round=round_num, agent=agent)

    async def agent_typing_end(self, agent: str, round_num: int) -> None:
        await self._ws.send_event(self._session_id, WSEventType.AGENT_TYPING_END, {}, round=round_num, agent=agent)

    async def agent_token(self, agent: str, token: str, round_num: int) -> None:
        await self._ws.send_token(self._session_id, agent, token, round_num)

    async def agent_message_complete(self, message: AgentMessage) -> None:
        await self._ws.send_event(
            self._session_id,
            WSEventType.AGENT_MESSAGE_COMPLETE,
            {"message": message.model_dump()},
            round=message.round,
            agent=message.sender,
        )

    async def critic_token(self, token: str, round_num: int) -> None:
        await self._ws.send_event(
            self._session_id, WSEventType.CRITIC_TOKEN, {"token": token}, round=round_num, agent="critic"
        )

    async def critic_evaluation(self, evaluation: CriticEvaluation) -> None:
        await self._ws.send_event(
            self._session_id,
            WSEventType.CRITIC_EVALUATION,
            {"evaluation": evaluation.model_dump()},
            round=evaluation.round,
            agent="critic",
        )

    async def canvas_updated(self, canvas_data: Dict[str, Any]) -> None:
        await self._ws.send_event(self._session_id, WSEventType.CANVAS_UPDATED, {"canvas": canvas_data})

    async def round_complete(self, round_num: int, summary: str) -> None:
        await self._ws.send_event(
            self._session_id, WSEventType.ROUND_COMPLETE, {"round": round_num, "summary": summary}, round=round_num
        )

    async def session_paused(self) -> None:
        await self._ws.send_event(self._session_id, WSEventType.SESSION_PAUSED, {})

    async def session_resumed(self) -> None:
        await self._ws.send_event(self._session_id, WSEventType.SESSION_RESUMED, {})

    async def session_converged(self, reason: str, plan: str) -> None:
        await self._ws.send_event(
            self._session_id, WSEventType.SESSION_CONVERGED, {"reason": reason, "plan": plan}
        )

    async def session_complete(self) -> None:
        await self._ws.send_event(self._session_id, WSEventType.SESSION_COMPLETE, {})

    async def agent_frozen(self, agent: str) -> None:
        await self._ws.send_event(self._session_id, WSEventType.AGENT_FROZEN, {"agent": agent}, agent=agent)

    async def agent_unfrozen(self, agent: str) -> None:
        await self._ws.send_event(self._session_id, WSEventType.AGENT_UNFROZEN, {"agent": agent}, agent=agent)

    async def error(self, message: str, details: str = "") -> None:
        await self._ws.send_event(self._session_id, WSEventType.ERROR, {"message": message, "details": details})

    async def health_ping(self) -> None:
        await self._ws.send_event(self._session_id, WSEventType.HEALTH_PING, {})
