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
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from api.clickhouse.client import get_client
from api.db.session import SessionLocal, engine
from api.dependencies.auth import ProjectContext, get_current_project
from api.main import app
from api.models import (
    ApiKey,
    Membership,
    MembershipRole,
    Org,
    Project,
    User,
    UserSession,
)
from api.security import (
    SESSION_TTL,
    generate_api_key,
    generate_session_token,
    hash_password,
)
from api.services.auth_rate_limit import reset_login_rate_limit

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


# Second project, used by read-API tests to verify that project_id scoping
# is a true security boundary - a key issued for project A must see zero
# rows from project B, not 403, not leakage. Distinct UUID5 namespace from
# the primary test project so the two never collide.
_TEST2_NS = uuid5(NAMESPACE_DNS, "tests.retrace.read-second")
_TEST2_ORG_ID = uuid5(_TEST2_NS, "org")
_TEST2_USER_ID = uuid5(_TEST2_NS, "user")
SECOND_TEST_PROJECT_ID = uuid5(_TEST2_NS, "project")


@pytest.fixture(scope="session")
def second_test_api_key() -> Iterator[tuple[str, UUID]]:
    """Parallel fixture to ``test_api_key`` for project-scoping tests."""
    raw_key = asyncio.run(_seed_second_test_rows())
    try:
        yield raw_key, SECOND_TEST_PROJECT_ID
    finally:
        asyncio.run(_teardown_second_test_rows())


async def _seed_second_test_rows() -> str:
    try:
        async with SessionLocal() as session:
            await session.execute(delete(Org).where(Org.id == _TEST2_ORG_ID))
            await session.execute(delete(User).where(User.id == _TEST2_USER_ID))
            await session.commit()

            org = Org(
                id=_TEST2_ORG_ID,
                name="Second Test Org",
                slug=f"test2-{_TEST2_ORG_ID.hex[:8]}",
            )
            user = User(
                id=_TEST2_USER_ID,
                email=f"test2-{_TEST2_USER_ID.hex[:8]}@retrace.test",
                name="Second Test User",
            )
            session.add_all([org, user])
            await session.flush()

            session.add_all(
                [
                    Membership(
                        org_id=_TEST2_ORG_ID,
                        user_id=_TEST2_USER_ID,
                        role=MembershipRole.OWNER,
                    ),
                    Project(
                        id=SECOND_TEST_PROJECT_ID,
                        org_id=_TEST2_ORG_ID,
                        name="Second Test Project",
                        slug=f"test2-{SECOND_TEST_PROJECT_ID.hex[:8]}",
                    ),
                ]
            )
            await session.flush()

            generated = generate_api_key()
            session.add(
                ApiKey(
                    project_id=SECOND_TEST_PROJECT_ID,
                    name="Second test key",
                    key_prefix=generated.prefix,
                    hashed_key=generated.hashed,
                )
            )
            await session.commit()
            return generated.raw
    finally:
        await engine.dispose()


async def _teardown_second_test_rows() -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(delete(Org).where(Org.id == _TEST2_ORG_ID))
            await session.execute(delete(User).where(User.id == _TEST2_USER_ID))
            await session.commit()
    finally:
        await engine.dispose()


# Session-auth fixtures
# ---------------------
# Two pre-seeded users with known passwords and active session tokens,
# each in their own org. Used by the auth/console/unified tests. The
# UUID5 namespace is independent of the api-key fixtures so the row
# sets never collide. The login rate-limit bucket is reset between
# tests (autouse) so a noisy test cannot lock out a quiet one.
_SESSION_TEST_NS = uuid5(NAMESPACE_DNS, "tests.retrace.session")
SESSION_USER_PASSWORD = "session-test-password-1234"

_SESSION_A_ORG_ID = uuid5(_SESSION_TEST_NS, "a-org")
_SESSION_A_USER_ID = uuid5(_SESSION_TEST_NS, "a-user")
SESSION_A_PROJECT_ID = uuid5(_SESSION_TEST_NS, "a-project")
SESSION_A_EMAIL = f"session-a-{_SESSION_A_USER_ID.hex[:8]}@retrace.test"

_SESSION_B_ORG_ID = uuid5(_SESSION_TEST_NS, "b-org")
_SESSION_B_USER_ID = uuid5(_SESSION_TEST_NS, "b-user")
SESSION_B_PROJECT_ID = uuid5(_SESSION_TEST_NS, "b-project")
SESSION_B_EMAIL = f"session-b-{_SESSION_B_USER_ID.hex[:8]}@retrace.test"


class SessionUserFixture:
    """Bundle returned by the session-user fixtures.

    ``token`` is the raw ``rts_`` session token (Bearer-ready). The
    other fields are the row ids the fixture seeded, so individual
    tests can assert against them without re-querying.
    """

    def __init__(
        self,
        *,
        token: str,
        email: str,
        password: str,
        user_id: UUID,
        org_id: UUID,
        project_id: UUID,
    ) -> None:
        self.token = token
        self.email = email
        self.password = password
        self.user_id = user_id
        self.org_id = org_id
        self.project_id = project_id


@pytest.fixture(scope="session")
def session_user_fixture() -> Iterator[SessionUserFixture]:
    """Primary session user (A). Owner of one project in one org."""
    raw_token = asyncio.run(
        _seed_session_user(
            user_id=_SESSION_A_USER_ID,
            email=SESSION_A_EMAIL,
            org_id=_SESSION_A_ORG_ID,
            project_id=SESSION_A_PROJECT_ID,
            tag="a",
        )
    )
    try:
        yield SessionUserFixture(
            token=raw_token,
            email=SESSION_A_EMAIL,
            password=SESSION_USER_PASSWORD,
            user_id=_SESSION_A_USER_ID,
            org_id=_SESSION_A_ORG_ID,
            project_id=SESSION_A_PROJECT_ID,
        )
    finally:
        asyncio.run(_teardown_session_user(_SESSION_A_USER_ID, _SESSION_A_ORG_ID))


@pytest.fixture(scope="session")
def second_session_user_fixture() -> Iterator[SessionUserFixture]:
    """Secondary session user (B), in a different org. Used by
    cross-org tests as the foreign actor / foreign project."""
    raw_token = asyncio.run(
        _seed_session_user(
            user_id=_SESSION_B_USER_ID,
            email=SESSION_B_EMAIL,
            org_id=_SESSION_B_ORG_ID,
            project_id=SESSION_B_PROJECT_ID,
            tag="b",
        )
    )
    try:
        yield SessionUserFixture(
            token=raw_token,
            email=SESSION_B_EMAIL,
            password=SESSION_USER_PASSWORD,
            user_id=_SESSION_B_USER_ID,
            org_id=_SESSION_B_ORG_ID,
            project_id=SESSION_B_PROJECT_ID,
        )
    finally:
        asyncio.run(_teardown_session_user(_SESSION_B_USER_ID, _SESSION_B_ORG_ID))


async def _seed_session_user(
    *,
    user_id: UUID,
    email: str,
    org_id: UUID,
    project_id: UUID,
    tag: str,
) -> str:
    try:
        async with SessionLocal() as session:
            # Drop any leftover state from a previously aborted run.
            await session.execute(delete(Org).where(Org.id == org_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()

            org = Org(
                id=org_id,
                name=f"Session Test Org {tag.upper()}",
                slug=f"session-{tag}-{org_id.hex[:8]}",
            )
            user = User(
                id=user_id,
                email=email,
                name=f"Session Test User {tag.upper()}",
                hashed_password=hash_password(SESSION_USER_PASSWORD),
            )
            session.add_all([org, user])
            await session.flush()

            session.add_all(
                [
                    Membership(
                        org_id=org_id, user_id=user_id, role=MembershipRole.OWNER
                    ),
                    Project(
                        id=project_id,
                        org_id=org_id,
                        name=f"Session Test Project {tag.upper()}",
                        slug=f"session-{tag}-{project_id.hex[:8]}",
                    ),
                ]
            )
            await session.flush()

            token = generate_session_token()
            expires_at = datetime.now(UTC) + SESSION_TTL
            session.add(
                UserSession(
                    user_id=user_id,
                    token_prefix=token.prefix,
                    hashed_token=token.hashed,
                    expires_at=expires_at,
                )
            )
            await session.commit()
            return token.raw
    finally:
        await engine.dispose()


async def _teardown_session_user(user_id: UUID, org_id: UUID) -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(delete(Org).where(Org.id == org_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_login_rate_limit_between_tests() -> Iterator[None]:
    """Login rate-limit is in-memory and per-process. Reset it between
    tests so a noisy test (e.g., the 6th-attempt 429 case) cannot
    affect later tests that happen to use the same (ip, email) bucket.
    """
    reset_login_rate_limit()
    yield
    reset_login_rate_limit()


# Deterministic read-test dataset
# -------------------------------
# Hand-picked counts and values so every read-API metric has an exact
# expected value, including the 1.0 similarity-score edge case for
# score_distribution bucketing.
#
# Primary project rows:
#   - 6 traces (4 RAG + 2 plain)
#   - 4 retrievals, latencies 100/200/300/400 -> avg 250
#   - 12 chunks, 3 per retrieval (ranks 0/1/2)
#   - 4 citations: 2 on trace 1, 1 on trace 2, 1 on trace 3, 0 on trace 4
#     -> citation_coverage = 3 / 4 = 0.75
#   - chunks_never_cited_rate = (12 - 4) / 12 = 8/12 (~0.6667)
#   - rank-0 scores: 1.0, 0.9, 0.6, 0.5 -> avg_top_similarity = 0.75
#     The 1.0 must land in the "0.9-1.0" bucket, not a phantom "1.0-1.1".
#
# Second project: 2 small unrelated rows so cross-project tests are
# strict (not vacuous against an empty project).
READ_TEST_BASE_TIME = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)

# Rank-0 similarity scores chosen so avg = 0.75 and 1.0 hits the edge.
_RANK0_SCORES = [1.0, 0.9, 0.6, 0.5]
# All 12 scores (4 retrievals x 3 chunks each). Bucket-rich for the
# distribution test.
_ALL_SCORES = [
    [1.0, 0.85, 0.7],   # retrieval 1 (RAG trace 1)
    [0.9, 0.65, 0.45],  # retrieval 2 (RAG trace 2)
    [0.6, 0.55, 0.5],   # retrieval 3 (RAG trace 3)
    [0.5, 0.4, 0.3],    # retrieval 4 (RAG trace 4)
]
# Citation counts per RAG trace (matches indexing of _ALL_SCORES).
_CITATIONS_PER_RAG_TRACE = [2, 1, 1, 0]

EXPECTED_TOTAL_TRACES = 6
EXPECTED_RAG_TRACES = 4
EXPECTED_AVG_RETRIEVAL_LATENCY_MS = 250
EXPECTED_AVG_TOP_SIMILARITY = sum(_RANK0_SCORES) / len(_RANK0_SCORES)  # 0.75
EXPECTED_CITATION_COVERAGE = 3 / 4  # 0.75
EXPECTED_CHUNKS_NEVER_CITED_RATE = (12 - sum(_CITATIONS_PER_RAG_TRACE)) / 12
EXPECTED_BUCKETS = {
    # Computed by hand from _ALL_SCORES; locked here so the bucketing
    # math is part of the test contract.
    "0.3-0.4": 1,
    "0.4-0.5": 2,
    "0.5-0.6": 3,
    "0.6-0.7": 2,
    "0.7-0.8": 1,
    "0.8-0.9": 1,
    "0.9-1.0": 2,
}


@pytest.fixture(scope="session")
def seeded_read_dataset(
    test_api_key: tuple[str, UUID],
    second_test_api_key: tuple[str, UUID],
) -> Iterator[None]:
    """Wipe + insert the deterministic read-test dataset under both projects.

    Session-scoped: runs once, before the first read test. Per-test
    cleanup is intentionally absent; the dataset is read-only as far
    as the tests are concerned.
    """
    _, primary_pid = test_api_key
    _, second_pid = second_test_api_key
    _wipe_clickhouse_for(primary_pid)
    _wipe_clickhouse_for(second_pid)
    _insert_primary_dataset(primary_pid)
    _insert_second_dataset(second_pid)
    try:
        yield
    finally:
        _wipe_clickhouse_for(primary_pid)
        _wipe_clickhouse_for(second_pid)


_RAG_TABLES = ("traces", "retrievals", "retrieved_chunks", "citations")


def _wipe_clickhouse_for(project_id: UUID) -> None:
    ch = get_client()
    for table in _RAG_TABLES:
        ch.command(
            f"ALTER TABLE {table} DELETE WHERE project_id = %(pid)s",
            parameters={"pid": str(project_id)},
            settings={"mutations_sync": 2},
        )


def _insert_primary_dataset(project_id: UUID) -> None:
    ch = get_client()
    base = READ_TEST_BASE_TIME

    traces: list[dict] = []
    retrievals: list[dict] = []
    chunks: list[dict] = []
    citations: list[dict] = []

    # Track ids for citation cross-references.
    rag_trace_ids: list[UUID] = []
    rag_retrieval_ids: list[UUID] = []
    chunk_ids_by_retrieval: list[list[UUID]] = []

    for i, scores in enumerate(_ALL_SCORES):
        when = base + timedelta(minutes=i * 5)
        trace_id = uuid4()
        rag_trace_ids.append(trace_id)
        traces.append(
            {
                "trace_id": trace_id,
                "span_id": uuid4(),
                "parent_span_id": None,
                "project_id": project_id,
                "start_time": when,
                "end_time": when + timedelta(milliseconds=200),
                "latency_ms": 200,
                "model": "gpt-4o",
                "tokens_in": 300 + i * 100,
                "tokens_out": 50 + i * 10,
                "status": "OK",
                "attributes": json.dumps({"kind": "rag.qa", "test_index": i}),
            }
        )

        retrieval_id = uuid4()
        rag_retrieval_ids.append(retrieval_id)
        retrievals.append(
            {
                "retrieval_id": retrieval_id,
                "trace_id": trace_id,
                "span_id": uuid4(),
                "project_id": project_id,
                "query": f"test query {i}",
                "embedding_model": "text-embedding-3-small",
                "top_k": 3,
                "latency_ms": (i + 1) * 100,  # 100, 200, 300, 400
                "timestamp": when,
            }
        )

        cids: list[UUID] = []
        for rank, score in enumerate(scores):
            cid = uuid4()
            cids.append(cid)
            chunks.append(
                {
                    "chunk_id": cid,
                    "retrieval_id": retrieval_id,
                    "project_id": project_id,
                    "rank": rank,
                    "similarity_score": score,
                    "content": f"chunk content t{i} r{rank}",
                    "source_doc_id": f"doc-{i}-{rank}",
                    "doc_metadata": json.dumps({"page": rank + 1}),
                    "timestamp": when,
                }
            )
        chunk_ids_by_retrieval.append(cids)

        # Citations: first N chunks of this trace, per the schedule.
        n_citations = _CITATIONS_PER_RAG_TRACE[i]
        cursor = 0
        for j in range(n_citations):
            citations.append(
                {
                    "citation_id": uuid4(),
                    "trace_id": trace_id,
                    "chunk_id": cids[j],
                    "project_id": project_id,
                    "response_span_start": cursor,
                    "response_span_end": cursor + 40,
                    "timestamp": when,
                }
            )
            cursor += 50

    # 2 plain (non-RAG) traces.
    for i in range(2):
        when = base + timedelta(minutes=30 + i * 5)
        traces.append(
            {
                "trace_id": uuid4(),
                "span_id": uuid4(),
                "parent_span_id": None,
                "project_id": project_id,
                "start_time": when,
                "end_time": when + timedelta(milliseconds=150),
                "latency_ms": 150,
                "model": "gpt-4o-mini",
                "tokens_in": 100,
                "tokens_out": 30,
                "status": "OK",
                "attributes": json.dumps({"kind": "llm.chat"}),
            }
        )

    _insert(ch, "traces", traces)
    _insert(ch, "retrievals", retrievals)
    _insert(ch, "retrieved_chunks", chunks)
    _insert(ch, "citations", citations)


def _insert_second_dataset(project_id: UUID) -> None:
    """Two rows under the second project. Scoping tests assert these do
    not leak into queries by the first project's key."""
    ch = get_client()
    base = READ_TEST_BASE_TIME

    trace_id = uuid4()
    other_trace_id = uuid4()
    retrieval_id = uuid4()
    chunk_id = uuid4()

    ch.insert(
        "traces",
        [
            [
                trace_id,
                uuid4(),
                None,
                project_id,
                base,
                base + timedelta(milliseconds=100),
                100,
                "gpt-4o",
                10,
                5,
                "OK",
                json.dumps({"kind": "second.project.rag"}),
            ],
            [
                other_trace_id,
                uuid4(),
                None,
                project_id,
                base + timedelta(minutes=1),
                base + timedelta(minutes=1, milliseconds=80),
                80,
                "gpt-4o",
                20,
                10,
                "OK",
                json.dumps({"kind": "second.project.plain"}),
            ],
        ],
        column_names=[
            "trace_id",
            "span_id",
            "parent_span_id",
            "project_id",
            "start_time",
            "end_time",
            "latency_ms",
            "model",
            "tokens_in",
            "tokens_out",
            "status",
            "attributes",
        ],
    )
    ch.insert(
        "retrievals",
        [
            [
                retrieval_id,
                trace_id,
                uuid4(),
                project_id,
                "second project query",
                "text-embedding-3-small",
                1,
                42,
                base,
            ]
        ],
        column_names=[
            "retrieval_id",
            "trace_id",
            "span_id",
            "project_id",
            "query",
            "embedding_model",
            "top_k",
            "latency_ms",
            "timestamp",
        ],
    )
    ch.insert(
        "retrieved_chunks",
        [
            [
                chunk_id,
                retrieval_id,
                project_id,
                0,
                0.99,
                "second project chunk",
                "doc-second",
                json.dumps({}),
                base,
            ]
        ],
        column_names=[
            "chunk_id",
            "retrieval_id",
            "project_id",
            "rank",
            "similarity_score",
            "content",
            "source_doc_id",
            "doc_metadata",
            "timestamp",
        ],
    )


def _insert(ch, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    data = [[row[col] for col in columns] for row in rows]
    ch.insert(table, data, column_names=columns)
