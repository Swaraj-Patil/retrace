"""Tests for POST /v1/ingest.

Every test runs against the live local ClickHouse. The autouse
``_clean_clickhouse`` fixture below wipes any rows tagged with the
test project_id before each test so test order does not matter and
counts are predictable.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient

from api.clickhouse.client import get_client

_TABLES = ("traces", "retrievals", "retrieved_chunks", "citations")


@pytest_asyncio.fixture(autouse=True)
async def _clean_clickhouse(test_api_key: tuple[str, UUID]) -> AsyncIterator[None]:
    _, project_id = test_api_key
    pid = str(project_id)
    client = get_client()
    for table in _TABLES:
        await asyncio.to_thread(
            client.command,
            f"ALTER TABLE {table} DELETE WHERE project_id = %(pid)s",
            parameters={"pid": pid},
            settings={"mutations_sync": 2},
        )
    yield


def _auth_headers(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _rag_payload() -> tuple[dict[str, object], UUID, UUID]:
    """One trace + one retrieval + four chunks + two citations, all FK-consistent."""
    now = datetime.now(UTC).replace(microsecond=0)
    trace_id = uuid4()
    span_id = uuid4()
    retrieval_id = uuid4()
    chunks: list[dict[str, object]] = []
    chunk_ids: list[UUID] = []
    for rank in range(4):
        cid = uuid4()
        chunk_ids.append(cid)
        chunks.append(
            {
                "chunk_id": str(cid),
                "retrieval_id": str(retrieval_id),
                "rank": rank,
                "similarity_score": 0.9 - rank * 0.1,
                "content": f"chunk-{rank}",
                "source_doc_id": f"doc-{rank}",
                "doc_metadata": {"page": rank},
                "timestamp": _iso(now),
            }
        )

    citations = [
        {
            "citation_id": str(uuid4()),
            "trace_id": str(trace_id),
            "chunk_id": str(chunk_ids[0]),
            "response_span_start": 0,
            "response_span_end": 40,
            "timestamp": _iso(now),
        },
        {
            "citation_id": str(uuid4()),
            "trace_id": str(trace_id),
            "chunk_id": str(chunk_ids[1]),
            "response_span_start": 41,
            "response_span_end": 80,
            "timestamp": _iso(now),
        },
    ]

    body = {
        "traces": [
            {
                "trace_id": str(trace_id),
                "span_id": str(span_id),
                "parent_span_id": None,
                "start_time": _iso(now),
                "end_time": _iso(now + timedelta(milliseconds=200)),
                "model": "gpt-4o",
                "tokens_in": 500,
                "tokens_out": 120,
                "latency_ms": 200,
                "status": "OK",
                "attributes": {"kind": "rag.qa"},
            }
        ],
        "retrievals": [
            {
                "retrieval_id": str(retrieval_id),
                "trace_id": str(trace_id),
                "span_id": str(uuid4()),
                "query": "what is retrace?",
                "embedding_model": "text-embedding-3-small",
                "top_k": 4,
                "latency_ms": 50,
                "timestamp": _iso(now),
            }
        ],
        "chunks": chunks,
        "citations": citations,
    }
    return body, trace_id, retrieval_id


async def test_empty_batch_returns_200_with_zero_counts(
    client: AsyncClient, test_api_key: tuple[str, UUID]
) -> None:
    raw_key, project_id = test_api_key
    r = await client.post("/v1/ingest", json={}, headers=_auth_headers(raw_key))
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == str(project_id)
    assert body["inserted"] == {"traces": 0, "retrievals": 0, "chunks": 0, "citations": 0}


async def test_full_rag_batch_roundtrips_through_clickhouse(
    client: AsyncClient, test_api_key: tuple[str, UUID]
) -> None:
    raw_key, project_id = test_api_key
    body, trace_id, retrieval_id = _rag_payload()

    r = await client.post("/v1/ingest", json=body, headers=_auth_headers(raw_key))
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == {
        "traces": 1,
        "retrievals": 1,
        "chunks": 4,
        "citations": 2,
    }

    # Round-trip: SELECT back from ClickHouse and confirm the rows landed
    # under the authenticated project_id.
    ch = get_client()
    pid = str(project_id)

    def _count(table: str) -> int:
        rows = ch.query(
            f"SELECT count() FROM {table} WHERE project_id = %(pid)s",
            parameters={"pid": pid},
        ).result_rows
        return int(rows[0][0])

    assert await asyncio.to_thread(_count, "traces") == 1
    assert await asyncio.to_thread(_count, "retrievals") == 1
    assert await asyncio.to_thread(_count, "retrieved_chunks") == 4
    assert await asyncio.to_thread(_count, "citations") == 2

    # And the trace_id specifically is the one we sent.
    def _trace_ids() -> list[str]:
        return [
            str(row[0])
            for row in ch.query(
                "SELECT trace_id FROM traces WHERE project_id = %(pid)s",
                parameters={"pid": pid},
            ).result_rows
        ]

    assert str(trace_id) in await asyncio.to_thread(_trace_ids)


async def test_batch_over_1000_items_returns_413(
    client: AsyncClient, test_api_key: tuple[str, UUID]
) -> None:
    raw_key, _ = test_api_key
    now = datetime.now(UTC).replace(microsecond=0)
    traces = [
        {
            "trace_id": str(uuid4()),
            "span_id": str(uuid4()),
            "parent_span_id": None,
            "start_time": _iso(now),
            "end_time": _iso(now),
            "model": "gpt-4o",
            "tokens_in": 1,
            "tokens_out": 1,
            "latency_ms": 1,
            "status": "OK",
            "attributes": {},
        }
        for _ in range(1001)
    ]
    r = await client.post(
        "/v1/ingest",
        json={"traces": traces},
        headers=_auth_headers(raw_key),
    )
    assert r.status_code == 413
    assert r.json() == {"error": "batch_too_large", "max_items": 1000}


async def test_similarity_score_above_one_returns_422(
    client: AsyncClient, test_api_key: tuple[str, UUID]
) -> None:
    raw_key, _ = test_api_key
    now = datetime.now(UTC).replace(microsecond=0)
    body = {
        "chunks": [
            {
                "chunk_id": str(uuid4()),
                "retrieval_id": str(uuid4()),
                "rank": 0,
                "similarity_score": 1.5,
                "content": "x",
                "source_doc_id": "doc",
                "doc_metadata": {},
                "timestamp": _iso(now),
            }
        ]
    }
    r = await client.post("/v1/ingest", json=body, headers=_auth_headers(raw_key))
    assert r.status_code == 422
    assert any("similarity_score" in str(loc) for loc in r.json()["detail"][0]["loc"])


async def test_chunk_referencing_unknown_retrieval_returns_422(
    client: AsyncClient, test_api_key: tuple[str, UUID]
) -> None:
    raw_key, _ = test_api_key
    now = datetime.now(UTC).replace(microsecond=0)
    unknown_retrieval = uuid4()
    body = {
        "chunks": [
            {
                "chunk_id": str(uuid4()),
                "retrieval_id": str(unknown_retrieval),
                "rank": 0,
                "similarity_score": 0.5,
                "content": "x",
                "source_doc_id": "doc",
                "doc_metadata": {},
                "timestamp": _iso(now),
            }
        ]
    }
    r = await client.post("/v1/ingest", json=body, headers=_auth_headers(raw_key))
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "unresolved_references"
    assert str(unknown_retrieval) in body["missing"]["retrievals"]


async def test_top_level_project_id_in_body_returns_422(
    client: AsyncClient, test_api_key: tuple[str, UUID]
) -> None:
    raw_key, _ = test_api_key
    # extra="forbid" should reject an unknown top-level field.
    r = await client.post(
        "/v1/ingest",
        json={"project_id": str(uuid4()), "traces": []},
        headers=_auth_headers(raw_key),
    )
    assert r.status_code == 422
