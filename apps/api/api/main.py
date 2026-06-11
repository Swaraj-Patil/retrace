"""FastAPI application factory and lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.db.session import engine
from api.dependencies.auth import (
    ProjectIdRequired,
    ProjectNotFound,
    Unauthorized,
)
from api.logging import configure_logging
from api.middleware import RequestIdMiddleware
from api.routers import auth as auth_router
from api.routers import console as console_router
from api.routers import health as health_router
from api.routers import ingest as ingest_router
from api.routers import metrics as metrics_router
from api.routers import projects as projects_router
from api.routers import traces as traces_router
from api.routers.traces import TraceNotFound
from api.services.auth import EmailAlreadyRegistered, OrgSlugCollision
from api.services.auth_rate_limit import RateLimited
from api.services.console import (
    ApiKeyNotFound,
    CannotDetermineOrg,
    ProjectSlugTaken,
)
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
    app.include_router(auth_router.router)
    app.include_router(console_router.router)
    app.include_router(ingest_router.router)
    app.include_router(projects_router.router)
    app.include_router(traces_router.router)
    app.include_router(metrics_router.router)

    @app.exception_handler(Unauthorized)
    async def _unauthorized_handler(_: Request, __: Unauthorized) -> JSONResponse:
        return JSONResponse(status_code=401, content={"error": "invalid_credentials"})

    @app.exception_handler(ProjectIdRequired)
    async def _project_id_required_handler(
        _: Request, __: ProjectIdRequired
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "project_id_required"})

    @app.exception_handler(ProjectNotFound)
    async def _project_not_found_handler(
        _: Request, __: ProjectNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "project_not_found"})

    @app.exception_handler(EmailAlreadyRegistered)
    async def _email_taken_handler(
        _: Request, __: EmailAlreadyRegistered
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "email_already_registered"})

    @app.exception_handler(OrgSlugCollision)
    async def _slug_collision_handler(
        request: Request, _: OrgSlugCollision
    ) -> JSONResponse:
        # Five retries with fresh random suffixes should never exhaust;
        # if they do something is very wrong (e.g., the DB rejecting
        # every insert for an unrelated reason). Log + 500.
        request_id = getattr(request.state, "request_id", "unknown")
        _logger.error("auth.org_slug_collision_exhausted")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "request_id": request_id},
        )

    @app.exception_handler(RateLimited)
    async def _rate_limited_handler(_: Request, __: RateLimited) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited"},
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(ProjectSlugTaken)
    async def _slug_taken_handler(_: Request, __: ProjectSlugTaken) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "project_slug_taken"})

    @app.exception_handler(CannotDetermineOrg)
    async def _cannot_determine_org_handler(
        _: Request, __: CannotDetermineOrg
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "cannot_determine_org"})

    @app.exception_handler(ApiKeyNotFound)
    async def _api_key_not_found_handler(
        _: Request, __: ApiKeyNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "api_key_not_found"})

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
