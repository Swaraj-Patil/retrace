"""Shared pytest fixtures for the API integration tests.

Tests run in-process against the real FastAPI app via httpx's
ASGITransport. Database calls in endpoints hit the same Postgres and
ClickHouse instances brought up by docker compose, so the local stack
needs to be running before pytest is invoked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Async HTTP client wired to the in-process app via ASGITransport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
