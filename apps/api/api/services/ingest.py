"""Batch ingestion service.

Three responsibilities:

1. ``validate_fk_closure`` resolves the implicit foreign keys between
   the four arrays. ``chunks`` reference ``retrievals``; ``citations``
   reference both ``traces`` and ``chunks``. References not satisfied
   inside the batch are checked against ClickHouse in a single query
   per missing-set, scoped by ``project_id`` so a client cannot point
   at another project's rows.

2. ``write_batch`` inserts into the four tables in
   trace -> retrieval -> chunk -> citation order so the FK closure
   above remains valid for subsequent batches. Each insert is wrapped
   in ``asyncio.to_thread`` because clickhouse-connect's HTTP client
   is synchronous.

3. The exception types (``BatchTooLarge``, ``UnresolvedReferences``,
   ``PartialInsertFailure``) are caught by handlers in ``api.main``
   and turned into the public error responses.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from clickhouse_connect.driver.client import Client

from api.schemas.ingest import (
    CitationIn,
    IngestRequest,
    RetrievalIn,
    RetrievedChunkIn,
    TraceIn,
)

MAX_BATCH_ITEMS = 1000


class BatchTooLarge(Exception):
    """Total item count across all four arrays exceeds ``MAX_BATCH_ITEMS``."""


class UnresolvedReferences(Exception):
    """FK closure failed: some referenced IDs exist in neither the batch nor
    the project's prior data."""

    def __init__(self, missing: dict[str, set[UUID]]) -> None:
        super().__init__("unresolved_references")
        self.missing = missing


class PartialInsertFailure(Exception):
    """One or more tables wrote successfully but a later table's insert
    raised. Carries the per-table counts at the moment of failure so the
    handler can include them in the error log."""

    def __init__(self, inserted: dict[str, int], cause: BaseException) -> None:
        super().__init__("partial_insert_failure")
        self.inserted = inserted
        self.__cause__ = cause


def total_items(req: IngestRequest) -> int:
    return len(req.traces) + len(req.retrievals) + len(req.chunks) + len(req.citations)


async def validate_fk_closure(
    req: IngestRequest, project_id: UUID, ch_client: Client
) -> None:
    """Raise ``UnresolvedReferences`` if any FK in the batch cannot be
    satisfied either in-batch or in ClickHouse under ``project_id``."""
    in_batch_retrievals = {r.retrieval_id for r in req.retrievals}
    in_batch_traces = {t.trace_id for t in req.traces}
    in_batch_chunks = {c.chunk_id for c in req.chunks}

    needs_retrievals = {c.retrieval_id for c in req.chunks} - in_batch_retrievals
    needs_traces = {c.trace_id for c in req.citations} - in_batch_traces
    needs_chunks = {c.chunk_id for c in req.citations} - in_batch_chunks

    unresolved: dict[str, set[UUID]] = {}

    if needs_retrievals:
        found = await _existing_ids(
            ch_client, "retrievals", "retrieval_id", needs_retrievals, project_id
        )
        if needs_retrievals - found:
            unresolved["retrievals"] = needs_retrievals - found

    if needs_traces:
        found = await _existing_ids(
            ch_client, "traces", "trace_id", needs_traces, project_id
        )
        if needs_traces - found:
            unresolved["traces"] = needs_traces - found

    if needs_chunks:
        found = await _existing_ids(
            ch_client, "retrieved_chunks", "chunk_id", needs_chunks, project_id
        )
        if needs_chunks - found:
            unresolved["chunks"] = needs_chunks - found

    if unresolved:
        raise UnresolvedReferences(missing=unresolved)


async def _existing_ids(
    client: Client,
    table: str,
    id_col: str,
    ids: set[UUID],
    project_id: UUID,
) -> set[UUID]:
    if not ids:
        return set()

    query = (
        f"SELECT DISTINCT {id_col} FROM {table} "
        f"WHERE project_id = %(pid)s AND {id_col} IN %(ids)s"
    )
    params = {"pid": str(project_id), "ids": tuple(str(i) for i in ids)}

    def _run() -> list[tuple[Any, ...]]:
        return client.query(query, parameters=params).result_rows

    rows = await asyncio.to_thread(_run)
    return {row[0] if isinstance(row[0], UUID) else UUID(str(row[0])) for row in rows}


async def write_batch(
    req: IngestRequest, project_id: UUID, ch_client: Client
) -> dict[str, int]:
    """Insert all four tables in dependency order. Returns per-table counts.

    Raises ``PartialInsertFailure`` if any insert fails after at least one
    has already succeeded.
    """
    inserted = {"traces": 0, "retrievals": 0, "chunks": 0, "citations": 0}

    plan: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("traces", "traces", _trace_rows(req.traces, project_id)),
        ("retrievals", "retrievals", _retrieval_rows(req.retrievals, project_id)),
        ("chunks", "retrieved_chunks", _chunk_rows(req.chunks, project_id)),
        ("citations", "citations", _citation_rows(req.citations, project_id)),
    ]

    for response_key, table, rows in plan:
        try:
            await _insert(ch_client, table, rows)
        except Exception as exc:
            if any(v > 0 for v in inserted.values()):
                raise PartialInsertFailure(inserted=inserted, cause=exc) from exc
            raise
        inserted[response_key] = len(rows)

    return inserted


async def _insert(client: Client, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    data = [[row[c] for c in columns] for row in rows]
    await asyncio.to_thread(client.insert, table, data, column_names=columns)


def _trace_rows(traces: list[TraceIn], project_id: UUID) -> list[dict[str, Any]]:
    return [
        {
            "trace_id": t.trace_id,
            "span_id": t.span_id,
            "parent_span_id": t.parent_span_id,
            "project_id": project_id,
            "start_time": t.start_time,
            "end_time": t.end_time,
            "latency_ms": t.latency_ms,
            "model": t.model,
            "tokens_in": t.tokens_in,
            "tokens_out": t.tokens_out,
            "status": t.status,
            "attributes": json.dumps(t.attributes),
        }
        for t in traces
    ]


def _retrieval_rows(
    retrievals: list[RetrievalIn], project_id: UUID
) -> list[dict[str, Any]]:
    return [
        {
            "retrieval_id": r.retrieval_id,
            "trace_id": r.trace_id,
            "span_id": r.span_id,
            "project_id": project_id,
            "query": r.query,
            "embedding_model": r.embedding_model,
            "top_k": r.top_k,
            "latency_ms": r.latency_ms,
            "timestamp": r.timestamp,
        }
        for r in retrievals
    ]


def _chunk_rows(
    chunks: list[RetrievedChunkIn], project_id: UUID
) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": c.chunk_id,
            "retrieval_id": c.retrieval_id,
            "project_id": project_id,
            "rank": c.rank,
            "similarity_score": c.similarity_score,
            "content": c.content,
            "source_doc_id": c.source_doc_id,
            "doc_metadata": json.dumps(c.doc_metadata),
            "timestamp": c.timestamp,
        }
        for c in chunks
    ]


def _citation_rows(
    citations: list[CitationIn], project_id: UUID
) -> list[dict[str, Any]]:
    return [
        {
            "citation_id": c.citation_id,
            "trace_id": c.trace_id,
            "chunk_id": c.chunk_id,
            "project_id": project_id,
            "response_span_start": c.response_span_start,
            "response_span_end": c.response_span_end,
            "timestamp": c.timestamp,
        }
        for c in citations
    ]
