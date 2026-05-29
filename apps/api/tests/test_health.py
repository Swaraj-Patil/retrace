"""Tests for /health and /ready."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from api.routers import health as health_router


async def test_health_returns_ok(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_ready_returns_200_when_stores_reachable(client: AsyncClient) -> None:
    r = await client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"postgres": "ok", "clickhouse": "ok"}


async def test_ready_returns_503_when_postgres_check_raises(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom() -> None:
        raise RuntimeError("simulated postgres outage")

    monkeypatch.setattr(health_router, "_check_postgres", boom)

    r = await client.get("/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["error"] == "not_ready"
    assert body["checks"]["postgres"] == "failed"
    assert body["checks"]["clickhouse"] == "ok"
