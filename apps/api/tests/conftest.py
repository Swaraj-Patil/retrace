"""Shared pytest fixtures for the API integration tests.

Tests run in-process against the real FastAPI app via httpx's
ASGITransport. Database calls in endpoints hit the same Postgres and
ClickHouse instances brought up by docker compose, so the local stack
needs to be running before pytest is invoked.

A small `/__test_protected__` route is mounted at import time so the
auth dependency can be exercised without depending on real `/v1/*`
endpoints. The route is added in the test process only - it is not
present when uvicorn is run for real.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Annotated
from uuid import NAMESPACE_DNS, UUID, uuid5

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from api.db.session import SessionLocal, engine
from api.dependencies.auth import ProjectContext, get_current_project
from api.main import app
from api.models import ApiKey, Membership, MembershipRole, Org, Project, User
from api.security import generate_api_key

PROTECTED_TEST_PATH = "/__test_protected__"


@app.get(PROTECTED_TEST_PATH)
async def _test_protected_route(
    ctx: Annotated[ProjectContext, Depends(get_current_project)],
) -> dict[str, str]:
    return {
        "project_id": str(ctx.project_id),
        "project_name": ctx.project_name,
        "org_id": str(ctx.org_id),
    }


# Deterministic UUIDs for the test fixture rows, in a namespace separate
# from the seed demo so the two never collide.
_TEST_NS = uuid5(NAMESPACE_DNS, "tests.retrace.dev")
_TEST_ORG_ID = uuid5(_TEST_NS, "org")
_TEST_USER_ID = uuid5(_TEST_NS, "user")
_TEST_PROJECT_ID = uuid5(_TEST_NS, "project")


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_between_tests() -> AsyncIterator[None]:
    """pytest-asyncio gives each test its own event loop. The async
    SQLAlchemy engine's pooled connections are bound to the loop they
    were opened on, so connections must be discarded between tests or
    the next test hits ``got Future attached to a different loop``.
    """
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Async HTTP client wired to the in-process app via ASGITransport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session")
def test_api_key() -> Iterator[tuple[str, UUID]]:
    """Dedicated test org/user/project/api_key, deterministic and isolated.

    Returns ``(raw_key, project_id)``. Tears down all five rows on
    session end. The cascade on the Org delete handles the membership,
    project, and api_key; the user is independent and removed
    explicitly.
    """
    raw_key = asyncio.run(_seed_test_rows())
    try:
        yield raw_key, _TEST_PROJECT_ID
    finally:
        asyncio.run(_teardown_test_rows())


async def _seed_test_rows() -> str:
    try:
        async with SessionLocal() as session:
            # Drop any leftover state from a previously aborted run before insert.
            await session.execute(delete(Org).where(Org.id == _TEST_ORG_ID))
            await session.execute(delete(User).where(User.id == _TEST_USER_ID))
            await session.commit()

            org = Org(
                id=_TEST_ORG_ID,
                name="Integration Test Org",
                slug=f"test-{_TEST_ORG_ID.hex[:8]}",
            )
            user = User(
                id=_TEST_USER_ID,
                email=f"test-{_TEST_USER_ID.hex[:8]}@retrace.test",
                name="Integration Test User",
            )
            session.add_all([org, user])
            await session.flush()

            membership = Membership(
                org_id=_TEST_ORG_ID,
                user_id=_TEST_USER_ID,
                role=MembershipRole.OWNER,
            )
            project = Project(
                id=_TEST_PROJECT_ID,
                org_id=_TEST_ORG_ID,
                name="Integration Test Project",
                slug=f"test-{_TEST_PROJECT_ID.hex[:8]}",
            )
            session.add_all([membership, project])
            await session.flush()

            generated = generate_api_key()
            session.add(
                ApiKey(
                    project_id=_TEST_PROJECT_ID,
                    name="Integration test key",
                    key_prefix=generated.prefix,
                    hashed_key=generated.hashed,
                )
            )
            await session.commit()
            return generated.raw
    finally:
        # The fixture runs inside its own asyncio.run loop; tests run in
        # separate loops. Dispose the engine here so pooled connections
        # from this loop do not leak into the test loops.
        await engine.dispose()


async def _teardown_test_rows() -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(delete(Org).where(Org.id == _TEST_ORG_ID))
            await session.execute(delete(User).where(User.id == _TEST_USER_ID))
            await session.commit()
    finally:
        await engine.dispose()
