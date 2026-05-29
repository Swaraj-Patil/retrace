"""Per-request ID assignment plus structured access logging.

Generates a UUID (or reuses an inbound ``X-Request-Id`` header), binds it to
structlog contextvars so every log line inside the request carries it,
echoes it back on the response, and emits one ``http.request`` log line
per request with method, path, status, and latency_ms.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"

_logger = structlog.get_logger("retrace.api.request")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())

        # Also expose on request.state so exception handlers can include
        # it in error responses without re-parsing headers.
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            latency_ms = int((time.perf_counter() - start) * 1000)
            _logger.exception(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=500,
                latency_ms=latency_ms,
            )
            raise

        latency_ms = int((time.perf_counter() - start) * 1000)
        response.headers[REQUEST_ID_HEADER] = request_id
        _logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
        )
        return response
