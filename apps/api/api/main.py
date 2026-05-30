"""FastAPI application factory and lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.db.session import engine
from api.dependencies.auth import Unauthorized
from api.logging import configure_logging
from api.middleware import RequestIdMiddleware
from api.routers import health as health_router
from api.routers import ingest as ingest_router
from api.routers import metrics as metrics_router
from api.routers import projects as projects_router
from api.routers import traces as traces_router
from api.routers.traces import TraceNotFound
from api.services.ingest import (
    BatchTooLarge,
    PartialInsertFailure,
    UnresolvedReferences,
)

_logger = structlog.get_logger("retrace.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log = structlog.get_logger("retrace.api")
    log.info("api.startup")
    try:
        yield
    finally:
        await engine.dispose()
        log.info("api.shutdown")


def create_app() -> FastAPI:
    """Build and return the FastAPI app. Called once at module import time."""
    settings = get_settings()
    configure_logging(env=settings.api_env)

    app = FastAPI(
        title="Retrace API",
        version="0.0.1",
        description="RAG-native observability ingestion API.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router.router)
    app.include_router(ingest_router.router)
    app.include_router(projects_router.router)
    app.include_router(traces_router.router)
    app.include_router(metrics_router.router)

    @app.exception_handler(Unauthorized)
    async def _unauthorized_handler(_: Request, __: Unauthorized) -> JSONResponse:
        return JSONResponse(status_code=401, content={"error": "invalid_credentials"})

    @app.exception_handler(TraceNotFound)
    async def _trace_not_found_handler(_: Request, __: TraceNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "trace_not_found"})

    @app.exception_handler(BatchTooLarge)
    async def _batch_too_large_handler(_: Request, __: BatchTooLarge) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"error": "batch_too_large", "max_items": 1000},
        )

    @app.exception_handler(UnresolvedReferences)
    async def _unresolved_handler(_: Request, exc: UnresolvedReferences) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "unresolved_references",
                "missing": {
                    table: sorted(str(i) for i in ids) for table, ids in exc.missing.items()
                },
            },
        )

    @app.exception_handler(PartialInsertFailure)
    async def _partial_handler(request: Request, exc: PartialInsertFailure) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        _logger.error(
            "ingest.partial_insert_failure",
            inserted=exc.inserted,
            cause=repr(exc.__cause__) if exc.__cause__ else None,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "request_id": request_id},
        )

    return app


app = create_app()
