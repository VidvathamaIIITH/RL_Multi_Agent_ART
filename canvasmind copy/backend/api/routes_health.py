from __future__ import annotations
import asyncio
import os
import time
from typing import Any, Dict

from fastapi import APIRouter
from openai import AzureOpenAI

from config import settings
from websocket.ws_manager import ws_manager

router = APIRouter(tags=["health"])
_START_TIME = time.time()


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "version": "1.0.0",
        "active_ws_sessions": len(ws_manager.active_connections),
    }


@router.get("/health/azure")
async def health_azure() -> Dict[str, Any]:
    try:
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
        loop = asyncio.get_event_loop()
        start = time.time()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=settings.deployment_text,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            ),
        )
        latency_ms = round((time.time() - start) * 1000)
        return {"status": "connected", "latency_ms": latency_ms, "deployment": settings.deployment_text}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/health/ws")
async def health_ws() -> Dict[str, Any]:
    return {
        "status": "running",
        "active_sessions": list(ws_manager.active_connections.keys()),
        "total_connections": sum(len(v) for v in ws_manager.active_connections.values()),
    }
