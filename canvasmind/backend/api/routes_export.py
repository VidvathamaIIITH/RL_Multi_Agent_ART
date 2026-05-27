from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from api.routes_session import _session_manager
from persistence.export_service import ExportService

router = APIRouter(prefix="/api/sessions", tags=["export"])
_export = ExportService()


@router.get("/{session_id}/export/json")
async def export_json(session_id: str) -> JSONResponse:
    try:
        session = await _session_manager.get_session(session_id)
        data = await _export.export_json(session)
        return JSONResponse(content=data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/export/markdown", response_class=PlainTextResponse)
async def export_markdown(session_id: str) -> str:
    try:
        session = await _session_manager.get_session(session_id)
        return await _export.export_markdown(session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/export/transcript", response_class=PlainTextResponse)
async def export_transcript(session_id: str) -> str:
    try:
        session = await _session_manager.get_session(session_id)
        return await _export.export_transcript(session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/export/canvas")
async def export_canvas(session_id: str) -> Response:
    try:
        session = await _session_manager.get_session(session_id)
        data = await _export.export_canvas_history(session)
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=canvas_{session_id}.zip"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/export/replay")
async def export_replay(session_id: str) -> JSONResponse:
    try:
        session = await _session_manager.get_session(session_id)
        data = await _export.export_replay(session)
        return JSONResponse(content=data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
