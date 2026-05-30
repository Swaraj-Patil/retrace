"""Tests for ``GET /v1/traces/{trace_id}`` detail endpoint."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from httpx import AsyncClient

from api.clickhouse.client import get_client


def _auth(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


def _first_rag_trace_id_for_project(project_id: UUID) -> UUID:
    """Pick any seeded RAG trace id under the given project. The fixture
    inserted four; tests don't care which one as long as it is RAG."""
    rows = get_client().query(
        "SELECT t.trace_id FROM traces t "
        "WHERE t.project_id = %(pid)s "
        "AND t.trace_id IN (SELECT DISTINCT trace_id FROM retrievals WHERE project_id = %(pid)s) "
        "LIMIT 1",
        parameters={"pid": str(project_id)},
    ).result_rows
    assert rows, "fixture should have seeded at least one RAG trace"
    return UUID(str(rows[0][0]))


def _first_plain_trace_id_for_project(project_id: UUID) -> UUID:
    rows = get_client().query(
        "SELECT t.trace_id FROM traces t "
        "WHERE t.project_id = %(pid)s "
        "AND t.trace_id NOT IN (SELECT DISTINCT trace_id FROM retrievals WHERE project_id = %(pid)s) "
        "LIMIT 1",
        parameters={"pid": str(project_id)},
    ).result_rows
    assert rows, "fixture should have seeded at least one plain trace"
    return UUID(str(rows[0][0]))


async def test_detail_returns_401_without_auth(client: AsyncClient) -> None:
    r = await client.get(f"/v1/traces/{uuid4()}")
    assert r.status_code == 401


async def test_detail_assembles_full_rag_chain(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, project_id = test_api_key
    tid = await asyncio.to_thread(_first_rag_trace_id_for_project, project_id)

    r = await client.get(f"/v1/traces/{tid}", headers=_auth(raw_key))
    assert r.status_code == 200, r.text
    body = r.json()

    # trace meta
    assert body["trace"]["trace_id"] == str(tid)
    assert body["trace"]["status"] == "OK"
    assert isinstance(body["trace"]["attributes"], dict)
    assert body["trace"]["attributes"].get("kind") == "rag.qa"

    # exactly one retrieval, with 3 chunks
    assert len(body["retrievals"]) == 1
    r0 = body["retrievals"][0]
    assert r0["top_k"] == 3
    assert len(r0["chunks"]) == 3
    # chunks are ordered by rank
    assert [c["rank"] for c in r0["chunks"]] == [0, 1, 2]
    # similarity scores are within [0, 1]
    assert all(0.0 <= c["similarity_score"] <= 1.0 for c in r0["chunks"])
    # doc_metadata parses to a dict
    assert all(isinstance(c["doc_metadata"], dict) for c in r0["chunks"])


async def test_was_cited_flag_marks_cited_chunks_correctly(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    """The fixture seeds citations at ranks 0..n-1 for each RAG trace, with
    one trace getting 2 citations (ranks 0, 1) and one getting 0. The
    detail endpoint must reflect this exactly per-chunk."""
    raw_key, project_id = test_api_key

    # Iterate all 4 RAG traces; for each, the chunks at rank < citation_count
    # must be was_cited=True, and all others False.
    # ClickHouse LEFT JOIN with default settings fills "missing" rows with
    # column defaults (UUID '00000000-...') rather than NULL, so
    # count(c.citation_id) over-counts. Use two separate queries and
    # merge in Python instead.
    def _fetch_expected() -> dict[UUID, int]:
        ch = get_client()
        rag_rows = ch.query(
            "SELECT DISTINCT trace_id FROM retrievals WHERE project_id = %(pid)s",
            parameters={"pid": str(project_id)},
        ).result_rows
        rag_ids = {UUID(str(r[0])) for r in rag_rows}
        cit_rows = ch.query(
            "SELECT trace_id, count() FROM citations "
            "WHERE project_id = %(pid)s GROUP BY trace_id",
            parameters={"pid": str(project_id)},
        ).result_rows
        cit_counts = {UUID(str(r[0])): int(r[1]) for r in cit_rows}
        return {tid: cit_counts.get(tid, 0) for tid in rag_ids}

    expected = await asyncio.to_thread(_fetch_expected)
    assert len(expected) == 4

    for trace_id, n_citations in expected.items():
        r = await client.get(f"/v1/traces/{trace_id}", headers=_auth(raw_key))
        assert r.status_code == 200
        body = r.json()
        assert len(body["citations"]) == n_citations, (
            f"trace {trace_id}: expected {n_citations} citations, "
            f"got {len(body['citations'])}"
        )

        chunks = body["retrievals"][0]["chunks"]
        for c in chunks:
            expected_cited = c["rank"] < n_citations
            assert c["was_cited"] is expected_cited, (
                f"trace {trace_id} rank {c['rank']}: "
                f"expected was_cited={expected_cited}, got {c['was_cited']}"
            )

        chunks = body["retrievals"][0]["chunks"]
        for c in chunks:
            expected = c["rank"] < int(n_citations)
            assert c["was_cited"] is expected, (
                f"trace {trace_id} rank {c['rank']}: "
                f"expected was_cited={expected}, got {c['was_cited']}"
            )


async def test_detail_plain_trace_has_empty_retrievals_and_citations(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, project_id = test_api_key
    tid = await asyncio.to_thread(_first_plain_trace_id_for_project, project_id)

    r = await client.get(f"/v1/traces/{tid}", headers=_auth(raw_key))
    assert r.status_code == 200
    body = r.json()
    assert body["retrievals"] == []
    assert body["citations"] == []


async def test_unknown_trace_id_returns_404(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    unknown = uuid4()
    r = await client.get(f"/v1/traces/{unknown}", headers=_auth(raw_key))
    assert r.status_code == 404
    assert r.json() == {"error": "trace_not_found"}


async def test_cross_project_trace_id_returns_404_not_403(
    client: AsyncClient,
    seeded_read_dataset: None,
    test_api_key: tuple[str, UUID],
    second_test_api_key: tuple[str, UUID],
) -> None:
    """Cross-project access must look identical to unknown-trace from the
    outside - 404 with the same error key. Returning 403 would leak the
    existence of the trace under another project."""
    primary_key, _ = test_api_key
    _, second_pid = second_test_api_key
    # Grab a trace id that exists ONLY under the second project.
    second_tid = await asyncio.to_thread(
        _first_rag_trace_id_for_project, second_pid
    )

    r = await client.get(f"/v1/traces/{second_tid}", headers=_auth(primary_key))
    assert r.status_code == 404
    assert r.json() == {"error": "trace_not_found"}


async def test_malformed_uuid_returns_422(
    client: AsyncClient,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    r = await client.get("/v1/traces/not-a-uuid", headers=_auth(raw_key))
    assert r.status_code == 422
