"""FastAPI application factory and lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from api.config import get_settings
from api.db.session import engine
from api.logging import configure_logging
from api.middleware import RequestIdMiddleware


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
    return app


app = create_app()
