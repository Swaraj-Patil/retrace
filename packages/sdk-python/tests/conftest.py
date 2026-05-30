"""Shared fixtures for SDK tests.

Every test that touches SDK module-level state runs with a clean slate:
config wiped, runtime stopped. Without this the runtime thread spawned
by one test leaks into the next.

``sdk_test_api_key`` is a session-scoped fixture mirroring the API
suite's ``test_api_key`` pattern. The two suites use distinct UUID5
namespaces (``tests.retrace.sdk`` vs ``tests.retrace.dev``) so their
seeded rows are guaranteed disjoint and can coexist.

The fixture is duplicated here rather than imported across the tests/
boundary - cross-dir test imports got messy with our two ``tests/``
namespace-package dirs in commit 1.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import NAMESPACE_DNS, UUID, uuid5

import pytest

import retrace
from retrace import _config, _runtime
from retrace._context import current_trace_id


@pytest.fixture(autouse=True)
def reset_sdk_state() -> Iterator[None]:
    retrace._reset_for_tests()
    _config.reset_for_tests()
    _runtime.reset_for_tests()
    # Sync tests share the pytest thread's contextvars Context; clear the
    # trace_id so each test starts with no current trace.
    current_trace_id.set(None)
    yield
    retrace._reset_for_tests()
    _config.reset_for_tests()
    _runtime.reset_for_tests()
    current_trace_id.set(None)


# Deterministic UUIDs for the SDK integration-test fixture rows. The
# namespace is distinct from the API suite's so the two suites never
# touch each other's data.
_SDK_TEST_NS = uuid5(NAMESPACE_DNS, "tests.retrace.sdk")
_SDK_TEST_ORG_ID = uuid5(_SDK_TEST_NS, "org")
_SDK_TEST_USER_ID = uuid5(_SDK_TEST_NS, "user")
SDK_TEST_PROJECT_ID = uuid5(_SDK_TEST_NS, "project")


@pytest.fixture(scope="session")
def sdk_test_api_key() -> Iterator[tuple[str, UUID]]:
    """Dedicated SDK test org/user/project/api_key. Deterministic, isolated.

    Returns ``(raw_key, project_id)``. Tear-down drops the Org (cascading
    Membership, Project, ApiKey) and the User. Engine is disposed in
    finally so pooled connections from this fixture's loop don't leak.
    """
    raw_key = asyncio.run(_seed_sdk_test_rows())
    try:
        yield raw_key, SDK_TEST_PROJECT_ID
    finally:
        asyncio.run(_teardown_sdk_test_rows())


async def _seed_sdk_test_rows() -> str:
    # Imported lazily so the SDK unit-test suite doesn't pay the cost of
    # touching the API package when the integration test isn't requested.
    from sqlalchemy import delete

    from api.db.session import SessionLocal, engine
    from api.models import ApiKey, Membership, MembershipRole, Org, Project, User
    from api.security import generate_api_key

    try:
        async with SessionLocal() as session:
            # Drop any leftovers from a previously aborted run.
            await session.execute(delete(Org).where(Org.id == _SDK_TEST_ORG_ID))
            await session.execute(delete(User).where(User.id == _SDK_TEST_USER_ID))
            await session.commit()

            org = Org(
                id=_SDK_TEST_ORG_ID,
                name="SDK Integration Test Org",
                slug=f"sdk-test-{_SDK_TEST_ORG_ID.hex[:8]}",
            )
            user = User(
                id=_SDK_TEST_USER_ID,
                email=f"sdk-test-{_SDK_TEST_USER_ID.hex[:8]}@retrace.test",
                name="SDK Integration Test User",
            )
            session.add_all([org, user])
            await session.flush()

            membership = Membership(
                org_id=_SDK_TEST_ORG_ID,
                user_id=_SDK_TEST_USER_ID,
                role=MembershipRole.OWNER,
            )
            project = Project(
                id=SDK_TEST_PROJECT_ID,
                org_id=_SDK_TEST_ORG_ID,
                name="SDK Integration Test Project",
                slug=f"sdk-test-{SDK_TEST_PROJECT_ID.hex[:8]}",
            )
            session.add_all([membership, project])
            await session.flush()

            generated = generate_api_key()
            session.add(
                ApiKey(
                    project_id=SDK_TEST_PROJECT_ID,
                    name="SDK integration test key",
                    key_prefix=generated.prefix,
                    hashed_key=generated.hashed,
                )
            )
            await session.commit()
            return generated.raw
    finally:
        await engine.dispose()


async def _teardown_sdk_test_rows() -> None:
    from sqlalchemy import delete

    from api.db.session import SessionLocal, engine
    from api.models import Org, User

    try:
        async with SessionLocal() as session:
            await session.execute(delete(Org).where(Org.id == _SDK_TEST_ORG_ID))
            await session.execute(delete(User).where(User.id == _SDK_TEST_USER_ID))
            await session.commit()
    finally:
        await engine.dispose()
