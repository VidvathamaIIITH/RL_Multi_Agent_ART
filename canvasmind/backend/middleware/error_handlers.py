from __future__ import annotations
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})
