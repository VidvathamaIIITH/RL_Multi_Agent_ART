from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Dict, List

from fastapi import WebSocket

from schemas.ws_events import WSEvent, WSEventType

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        self.active_connections.setdefault(session_id, []).append(websocket)
        logger.info(f"WS connected: session={session_id}, total={len(self.active_connections[session_id])}")

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        connections = self.active_connections.get(session_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active_connections.pop(session_id, None)
        logger.info(f"WS disconnected: session={session_id}")

    async def broadcast_to_session(self, session_id: str, event: WSEvent) -> None:
        connections = self.active_connections.get(session_id, [])
        if not connections:
            return
        payload = event.model_dump_json()
        dead: List[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.warning(f"WS send failed: {exc}")
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws, session_id)

    async def send_token(self, session_id: str, agent: str, token: str, round: int) -> None:
        event = WSEvent(
            event_type=WSEventType.AGENT_TOKEN,
            session_id=session_id,
            round=round,
            agent=agent,
            data={"token": token},
        )
        await self.broadcast_to_session(session_id, event)

    async def send_event(
        self, session_id: str, event_type: WSEventType, data: dict, round: int = None, agent: str = None
    ) -> None:
        event = WSEvent(
            event_type=event_type,
            session_id=session_id,
            round=round,
            agent=agent,
            data=data,
        )
        await self.broadcast_to_session(session_id, event)


ws_manager = WebSocketManager()
