"""Tests for ``GET /v1/traces`` list endpoint."""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient

from tests.conftest import (
    EXPECTED_RAG_TRACES,
    EXPECTED_TOTAL_TRACES,
    READ_TEST_BASE_TIME,
)


def _auth(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_list_returns_401_without_auth(client: AsyncClient) -> None:
    r = await client.get("/v1/traces")
    assert r.status_code == 401


async def test_list_returns_seeded_traces(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    r = await client.get("/v1/traces", headers=_auth(raw_key))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == EXPECTED_TOTAL_TRACES
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["traces"]) == EXPECTED_TOTAL_TRACES

    # Default ordering is by start_time DESC: the two plain traces (at
    # minutes 30 and 35) come before the RAG traces (at minutes 0-15).
    times = [t["start_time"] for t in body["traces"]]
    assert times == sorted(times, reverse=True)


async def test_list_aggregates_populated_per_trace(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    r = await client.get("/v1/traces", headers=_auth(raw_key))
    body = r.json()

    rag_items = [t for t in body["traces"] if t["has_retrieval"]]
    plain_items = [t for t in body["traces"] if not t["has_retrieval"]]

    assert len(rag_items) == EXPECTED_RAG_TRACES
    assert len(plain_items) == EXPECTED_TOTAL_TRACES - EXPECTED_RAG_TRACES

    # Each RAG trace has 3 chunks (one retrieval, top_k=3).
    assert all(t["chunk_count"] == 3 for t in rag_items)
    # Plain traces have no retrievals -> no chunks, no citations.
    assert all(t["chunk_count"] == 0 for t in plain_items)
    assert all(t["citation_count"] == 0 for t in plain_items)

    # Sum of citations across RAG traces matches the seed schedule.
    assert sum(t["citation_count"] for t in rag_items) == 4


async def test_pagination_respects_limit_and_offset(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key

    r = await client.get("/v1/traces?limit=2&offset=0", headers=_auth(raw_key))
    page1 = r.json()
    assert page1["total"] == EXPECTED_TOTAL_TRACES
    assert page1["limit"] == 2
    assert page1["offset"] == 0
    assert len(page1["traces"]) == 2

    r = await client.get("/v1/traces?limit=2&offset=2", headers=_auth(raw_key))
    page2 = r.json()
    assert page2["total"] == EXPECTED_TOTAL_TRACES
    assert page2["offset"] == 2
    assert len(page2["traces"]) == 2

    page1_ids = {t["trace_id"] for t in page1["traces"]}
    page2_ids = {t["trace_id"] for t in page2["traces"]}
    assert page1_ids.isdisjoint(page2_ids)


async def test_limit_validation_rejects_too_large(
    client: AsyncClient, test_api_key: tuple[str, UUID]
) -> None:
    raw_key, _ = test_api_key
    r = await client.get("/v1/traces?limit=999", headers=_auth(raw_key))
    assert r.status_code == 422


async def test_rag_only_filter(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    r = await client.get("/v1/traces?rag_only=true", headers=_auth(raw_key))
    body = r.json()
    assert body["total"] == EXPECTED_RAG_TRACES
    assert len(body["traces"]) == EXPECTED_RAG_TRACES
    assert all(t["has_retrieval"] for t in body["traces"])


async def test_rag_only_list_count_divergence_regression(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    """The list query and the count() query are built from the same filter
    builder, but they live in two SQL strings - if someone adds a CTE-
    backed filter to one without the other, ``total`` and the actual
    page rows would diverge. This test pages through all matching rows
    under ``rag_only=true`` and asserts the sum equals ``total``.
    """
    raw_key, _ = test_api_key

    # First request: get total.
    r = await client.get("/v1/traces?rag_only=true&limit=1", headers=_auth(raw_key))
    total = r.json()["total"]
    assert total == EXPECTED_RAG_TRACES

    # Now page through and count the actual rows. Must equal total.
    actual = 0
    seen_ids: set[str] = set()
    offset = 0
    while True:
        r = await client.get(
            f"/v1/traces?rag_only=true&limit=2&offset={offset}",
            headers=_auth(raw_key),
        )
        page = r.json()
        assert page["total"] == total, "total drifted between pages"
        if not page["traces"]:
            break
        actual += len(page["traces"])
        for t in page["traces"]:
            seen_ids.add(t["trace_id"])
        offset += 2
    assert actual == total
    assert len(seen_ids) == total


async def test_time_range_filter_narrows_results(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    # The 4 RAG traces start at minutes 0, 5, 10, 15 of READ_TEST_BASE_TIME.
    # Pick a window that includes only the first two.
    from_ts = READ_TEST_BASE_TIME.isoformat()
    to_ts = (READ_TEST_BASE_TIME.replace(minute=7)).isoformat()
    # httpx serializes query params, which escapes the +00:00 in ISO 8601
    # tz suffix to %2B00:00 (it would otherwise read as a literal space).
    r = await client.get(
        "/v1/traces",
        params={"from": from_ts, "to": to_ts},
        headers=_auth(raw_key),
    )
    body = r.json()
    assert body["total"] == 2
    assert len(body["traces"]) == 2


async def test_project_scoping_blocks_other_project_traces(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
    second_test_api_key: tuple[str, UUID],
) -> None:
    """First project's key must NOT see second project's traces, and
    vice versa. This is the security boundary."""
    primary_key, primary_pid = test_api_key
    second_key, second_pid = second_test_api_key

    r1 = await client.get("/v1/traces", headers=_auth(primary_key))
    primary_body = r1.json()
    assert primary_body["total"] == EXPECTED_TOTAL_TRACES

    r2 = await client.get("/v1/traces", headers=_auth(second_key))
    second_body = r2.json()
    # Second project was seeded with 2 traces by the fixture.
    assert second_body["total"] == 2

    primary_ids = {t["trace_id"] for t in primary_body["traces"]}
    second_ids = {t["trace_id"] for t in second_body["traces"]}
    assert primary_ids.isdisjoint(second_ids)
