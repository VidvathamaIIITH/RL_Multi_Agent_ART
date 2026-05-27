import pytest
from unittest.mock import AsyncMock, MagicMock

from websocket.ws_manager import WebSocketManager
from schemas.ws_events import WSEvent, WSEventType


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    manager = WebSocketManager()
    ws = AsyncMock()
    await manager.connect(ws, "session-1")
    assert "session-1" in manager.active_connections
    assert ws in manager.active_connections["session-1"]

    await manager.disconnect(ws, "session-1")
    assert "session-1" not in manager.active_connections


@pytest.mark.asyncio
async def test_broadcast_to_session():
    manager = WebSocketManager()
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    await manager.connect(ws1, "session-x")
    await manager.connect(ws2, "session-x")

    event = WSEvent(
        event_type=WSEventType.ROUND_STARTED,
        session_id="session-x",
        data={"round": 1},
    )
    await manager.broadcast_to_session("session-x", event)

    ws1.send_text.assert_called_once()
    ws2.send_text.assert_called_once()


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connection():
    manager = WebSocketManager()
    dead_ws = AsyncMock()
    dead_ws.send_text.side_effect = Exception("Connection closed")
    live_ws = AsyncMock()

    await manager.connect(dead_ws, "session-y")
    await manager.connect(live_ws, "session-y")

    event = WSEvent(
        event_type=WSEventType.HEALTH_PING,
        session_id="session-y",
        data={},
    )
    await manager.broadcast_to_session("session-y", event)

    assert dead_ws not in manager.active_connections.get("session-y", [])
    assert live_ws in manager.active_connections.get("session-y", [])
