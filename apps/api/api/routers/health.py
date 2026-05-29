"""Liveness and readiness endpoints.

``/health`` is a cheap liveness probe: 200 as long as the process is up.
``/ready`` runs a real round-trip against Postgres and ClickHouse in
parallel and returns 503 with a per-store breakdown if either fails.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.clickhouse.client import get_client
from api.db.session import SessionLocal

router = APIRouter(tags=["health"])

_logger = structlog.get_logger("retrace.api.health")


async def _check_postgres() -> None:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))


async def _check_clickhouse() -> None:
    client = get_client()
    await asyncio.to_thread(client.query, "SELECT 1")


async def _status_of(check: Callable[[], Awaitable[None]], name: str) -> str:
    try:
        await check()
    except Exception:
        _logger.exception("ready.check_failed", check=name)
        return "failed"
    return "ok"


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> JSONResponse:
    pg_status, ch_status = await asyncio.gather(
        _status_of(_check_postgres, "postgres"),
        _status_of(_check_clickhouse, "clickhouse"),
    )
    checks = {"postgres": pg_status, "clickhouse": ch_status}
    if pg_status == "ok" and ch_status == "ok":
        return JSONResponse(status_code=200, content={"status": "ready", "checks": checks})
    return JSONResponse(status_code=503, content={"error": "not_ready", "checks": checks})
