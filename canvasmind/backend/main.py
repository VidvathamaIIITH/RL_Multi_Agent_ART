from __future__ import annotations
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import validate_config, settings
from api.routes_session import router as session_router
from api.routes_control import router as control_router
from api.routes_export import router as export_router
from api.routes_health import router as health_router
from api.routes_quad import router as quad_router
from middleware.logging_middleware import LoggingMiddleware
from middleware.error_handlers import register_error_handlers
from websocket.ws_manager import ws_manager

validate_config()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CanvasMind API",
    description="Computational Creativity — Multi-Agent Collaborative AI Painting System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(session_router)
app.include_router(control_router)
app.include_router(export_router)
app.include_router(quad_router)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"WS message from {session_id}: {data[:100]}")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, session_id)
        logger.info(f"WS disconnected: {session_id}")


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("CanvasMind backend started")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("CanvasMind backend shutting down")
