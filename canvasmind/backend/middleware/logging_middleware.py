from __future__ import annotations
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        response = await call_next(request)
        elapsed = round((time.time() - start) * 1000)
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({elapsed}ms)"
        )
        return response
