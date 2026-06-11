"""Tests for the unified project-context resolver on the read endpoints.

``/v1/traces``, ``/v1/traces/{id}``, and ``/v1/metrics/overview`` now
accept either an API key or a user session. The api-key branch ignores
``?project_id=`` so the existing demo calls are byte-identical; the
session branch requires ``?project_id=`` (400 otherwise) and 404s on
cross-org access (no enumeration, even on the detail endpoint).
"""

from __future__ import annotations

from uuid import UUID

from httpx import AsyncClient

from tests.conftest import (
    EXPECTED_RAG_TRACES,
    EXPECTED_TOTAL_TRACES,
    SessionUserFixture,
)


# ---------------------------------------------------------------------------
# API-key branch (regression: must stay byte-identical to pre-swap)
# ---------------------------------------------------------------------------


async def test_api_key_no_project_id_returns_seeded_data(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    """The demo's existing call pattern (rt_ key, no ?project_id) returns
    the same totals it always did."""
    raw_key, _ = test_api_key
    headers = {"Authorization": f"Bearer {raw_key}"}

    traces = await client.get("/v1/traces", headers=headers)
    assert traces.status_code == 200
    assert traces.json()["total"] == EXPECTED_TOTAL_TRACES

    metrics = await client.get("/v1/metrics/overview", headers=headers)
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["total_traces"] == EXPECTED_TOTAL_TRACES
    assert body["rag_traces"] == EXPECTED_RAG_TRACES


async def test_api_key_branch_ignores_project_id_query_param(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
    second_test_api_key: tuple[str, UUID],
) -> None:
    """With an API key, ``?project_id`` is ignored: the response is
    scoped by the key, not by the query param. Verified by passing the
    *other* project's id - the caller still sees their own data."""
    raw_key, own_pid = test_api_key
    _, other_pid = second_test_api_key
    headers = {"Authorization": f"Bearer {raw_key}"}

    no_param = (await client.get("/v1/traces", headers=headers)).json()
    own_param = (
        await client.get(f"/v1/traces?project_id={own_pid}", headers=headers)
    ).json()
    other_param = (
        await client.get(f"/v1/traces?project_id={other_pid}", headers=headers)
    ).json()

    # All three return the api-key's own project totals - the query
    # param is silently ignored on this branch.
    assert no_param["total"] == own_param["total"] == other_param["total"]
    assert no_param["total"] == EXPECTED_TOTAL_TRACES


# ---------------------------------------------------------------------------
# Session branch: missing project_id -> 400 project_id_required
# ---------------------------------------------------------------------------


async def test_session_traces_list_without_project_id_returns_400(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    r = await client.get(
        "/v1/traces", headers={"Authorization": f"Bearer {session_user_fixture.token}"}
    )
    assert r.status_code == 400
    assert r.json() == {"error": "project_id_required"}


async def test_session_metrics_overview_without_project_id_returns_400(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    r = await client.get(
        "/v1/metrics/overview",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 400
    assert r.json() == {"error": "project_id_required"}


async def test_session_trace_detail_without_project_id_returns_400(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    """Auth dependency runs before the trace lookup, so a missing
    project_id 400s without leaking whether the trace exists."""
    raw_key, _ = test_api_key
    # Borrow a real trace id from the seeded dataset for realism.
    listed = await client.get(
        "/v1/traces?limit=1", headers={"Authorization": f"Bearer {raw_key}"}
    )
    trace_id = listed.json()["traces"][0]["trace_id"]

    r = await client.get(
        f"/v1/traces/{trace_id}",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 400
    assert r.json() == {"error": "project_id_required"}


# ---------------------------------------------------------------------------
# Session branch: own project_id -> 200 (even when empty)
# ---------------------------------------------------------------------------


async def test_session_with_own_project_id_returns_200_on_empty_project(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    """The session user's own project has no ingested data, but
    the read endpoints still return 200 with empty/zero results -
    auth and scoping work even on an empty project."""
    headers = {"Authorization": f"Bearer {session_user_fixture.token}"}
    pid = session_user_fixture.project_id

    traces = await client.get(f"/v1/traces?project_id={pid}", headers=headers)
    assert traces.status_code == 200
    assert traces.json()["total"] == 0
    assert traces.json()["traces"] == []

    metrics = await client.get(
        f"/v1/metrics/overview?project_id={pid}", headers=headers
    )
    assert metrics.status_code == 200
    assert metrics.json()["total_traces"] == 0


# ---------------------------------------------------------------------------
# Session branch: cross-org project_id -> 404 project_not_found
# ---------------------------------------------------------------------------


async def test_session_traces_list_with_foreign_project_id_returns_404(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
    test_api_key: tuple[str, UUID],
) -> None:
    _, foreign_pid = test_api_key
    r = await client.get(
        f"/v1/traces?project_id={foreign_pid}",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 404
    assert r.json() == {"error": "project_not_found"}


async def test_session_metrics_with_foreign_project_id_returns_404(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
    test_api_key: tuple[str, UUID],
) -> None:
    _, foreign_pid = test_api_key
    r = await client.get(
        f"/v1/metrics/overview?project_id={foreign_pid}",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 404
    assert r.json() == {"error": "project_not_found"}


async def test_session_trace_detail_with_foreign_project_id_returns_404_not_trace_404(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    """Critical no-enumeration property: even when the trace_id is a
    real, existing trace in the foreign project, the response is
    ``project_not_found`` (404), not ``trace_not_found``. A session
    caller cannot probe for valid trace ids across orgs."""
    raw_key, foreign_pid = test_api_key
    listed = await client.get(
        "/v1/traces?limit=1", headers={"Authorization": f"Bearer {raw_key}"}
    )
    real_trace_id = listed.json()["traces"][0]["trace_id"]

    r = await client.get(
        f"/v1/traces/{real_trace_id}?project_id={foreign_pid}",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 404
    assert r.json() == {"error": "project_not_found"}
