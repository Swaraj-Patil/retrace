"""Tests for ``GET /v1/metrics/overview``."""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient

from tests.conftest import (
    EXPECTED_AVG_TOP_SIMILARITY,
    EXPECTED_BUCKETS,
    EXPECTED_CHUNKS_NEVER_CITED_RATE,
    EXPECTED_CITATION_COVERAGE,
    EXPECTED_RAG_TRACES,
    EXPECTED_TOTAL_TRACES,
    READ_TEST_BASE_TIME,
)

EXPECTED_AVG_RETRIEVAL_LATENCY_MS = 250


def _auth(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_metrics_returns_401_without_auth(client: AsyncClient) -> None:
    r = await client.get("/v1/metrics/overview")
    assert r.status_code == 401


async def test_metrics_against_seeded_dataset(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    r = await client.get("/v1/metrics/overview", headers=_auth(raw_key))
    assert r.status_code == 200, r.text
    m = r.json()

    assert m["total_traces"] == EXPECTED_TOTAL_TRACES
    assert m["rag_traces"] == EXPECTED_RAG_TRACES
    assert m["avg_retrieval_latency_ms"] == EXPECTED_AVG_RETRIEVAL_LATENCY_MS
    assert m["chunks_never_cited_rate"] == pytest.approx(
        EXPECTED_CHUNKS_NEVER_CITED_RATE, abs=1e-6
    )
    assert m["avg_top_similarity"] == pytest.approx(
        EXPECTED_AVG_TOP_SIMILARITY, abs=1e-4
    )
    assert m["citation_coverage"] == pytest.approx(EXPECTED_CITATION_COVERAGE, abs=1e-6)


async def test_score_distribution_includes_1_point_0_in_top_bucket(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    """The dataset includes a chunk with similarity_score = 1.0. The
    bucket label for that value must be "0.9-1.0", not a phantom
    "1.0-1.1" - the SQL clamps via least(..., 9)."""
    raw_key, _ = test_api_key
    r = await client.get("/v1/metrics/overview", headers=_auth(raw_key))
    m = r.json()

    by_bucket = {b["bucket"]: b["count"] for b in m["score_distribution"]}
    assert by_bucket == EXPECTED_BUCKETS
    assert "1.0-1.1" not in by_bucket
    # And the top bucket holds both 0.9 and 1.0:
    assert by_bucket["0.9-1.0"] == 2
    # Sum equals total chunks.
    assert sum(by_bucket.values()) == 12


async def test_traces_over_time_groups_by_date(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    r = await client.get("/v1/metrics/overview", headers=_auth(raw_key))
    m = r.json()

    # All 6 seeded traces share a single date (READ_TEST_BASE_TIME).
    expected_date = READ_TEST_BASE_TIME.date().isoformat()
    by_date = {p["date"]: p["count"] for p in m["traces_over_time"]}
    assert by_date == {expected_date: EXPECTED_TOTAL_TRACES}


async def test_empty_project_returns_numeric_zeros_not_nan(
    client: AsyncClient,
    seeded_read_dataset: None,
    second_test_api_key: tuple[str, UUID],
) -> None:
    """Regression guard for the NaN-from-empty-avg fix.

    The second project has only 2 traces, 1 retrieval, 1 chunk, and 0
    citations. The metrics endpoint must return finite numeric values
    (no NaN, no null, no 500) even when an aggregate is over zero rows.
    Explicit zero-value asserts on every avg/ratio so a future regression
    of the _safe_avg helper fails this test.
    """
    raw_key, _ = second_test_api_key
    r = await client.get("/v1/metrics/overview", headers=_auth(raw_key))
    assert r.status_code == 200, r.text
    m = r.json()

    # The second project has minimal data, but it does have rows.
    # All numeric fields must be valid floats/ints. Specifically:
    # - 0 citations -> chunks_never_cited_rate = 1.0 (single chunk, not cited)
    # - 0 RAG traces with citations -> citation_coverage = 0.0
    assert isinstance(m["total_traces"], int)
    assert isinstance(m["rag_traces"], int)
    assert isinstance(m["avg_retrieval_latency_ms"], int)
    assert isinstance(m["chunks_never_cited_rate"], float)
    assert isinstance(m["avg_top_similarity"], float)
    assert isinstance(m["citation_coverage"], float)
    # No NaN/inf leaking through.
    import math as _math

    assert _math.isfinite(m["chunks_never_cited_rate"])
    assert _math.isfinite(m["avg_top_similarity"])
    assert _math.isfinite(m["citation_coverage"])


async def test_truly_empty_project_zeros_everywhere(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
    second_test_api_key: tuple[str, UUID],
) -> None:
    """Hit the metrics endpoint with a time window that excludes every
    row in both projects. Every aggregate must come back as 0/0.0 and
    both arrays must be empty - the NaN/None regression guard for the
    truly-no-data path that today's _safe_avg fix addresses."""
    raw_key, _ = test_api_key
    far_future_from = "2099-01-01T00:00:00Z"
    far_future_to = "2099-12-31T23:59:59Z"
    r = await client.get(
        "/v1/metrics/overview",
        params={"from": far_future_from, "to": far_future_to},
        headers=_auth(raw_key),
    )
    assert r.status_code == 200, r.text
    m = r.json()

    assert m["total_traces"] == 0
    assert m["rag_traces"] == 0
    assert m["avg_retrieval_latency_ms"] == 0
    assert m["chunks_never_cited_rate"] == 0.0
    assert m["avg_top_similarity"] == 0.0
    assert m["citation_coverage"] == 0.0
    assert m["traces_over_time"] == []
    assert m["score_distribution"] == []


async def test_time_range_narrows_metrics(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    # First two RAG traces fall within minutes 0-5 of READ_TEST_BASE_TIME.
    # Their retrievals have latencies 100, 200 -> avg 150.
    from_ts = READ_TEST_BASE_TIME.isoformat()
    to_ts = READ_TEST_BASE_TIME.replace(minute=7).isoformat()

    r = await client.get(
        "/v1/metrics/overview",
        params={"from": from_ts, "to": to_ts},
        headers=_auth(raw_key),
    )
    assert r.status_code == 200
    m = r.json()

    assert m["total_traces"] == 2
    assert m["rag_traces"] == 2
    assert m["avg_retrieval_latency_ms"] == 150


async def test_metrics_project_scoping(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
    second_test_api_key: tuple[str, UUID],
) -> None:
    """First project's totals must not include second project's rows."""
    primary_key, _ = test_api_key
    second_key, _ = second_test_api_key

    r1 = await client.get("/v1/metrics/overview", headers=_auth(primary_key))
    r2 = await client.get("/v1/metrics/overview", headers=_auth(second_key))

    primary = r1.json()
    second = r2.json()

    assert primary["total_traces"] == EXPECTED_TOTAL_TRACES
    assert second["total_traces"] == 2
    assert primary["total_traces"] != second["total_traces"]
