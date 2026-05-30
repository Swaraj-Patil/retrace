"""Read-side queries against ClickHouse.

All queries are scoped by ``project_id`` from the auth context - that
is a security boundary, enforced in test_read_traces.py with a second
project.

ClickHouse SQL stays in this module; routers stay thin.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from clickhouse_connect.driver.client import Client

_log = logging.getLogger("retrace.api.read")

MAX_LIST_LIMIT = 200
DEFAULT_LIST_LIMIT = 50


async def list_traces(
    ch: Client,
    *,
    project_id: UUID,
    limit: int,
    offset: int,
    rag_only: bool,
    start_from: datetime | None,
    start_to: datetime | None,
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(rows, total)`` for the trace list.

    ``rows`` carries the page; ``total`` is the count *before* limit/offset
    so the client can paginate. Both run under the same filter set.
    """
    base_filter, params = _build_trace_filter(
        project_id=project_id,
        rag_only=rag_only,
        start_from=start_from,
        start_to=start_to,
    )

    # The list query joins the three pre-aggregated CTEs onto traces.
    # Pre-aggregating in CTEs rather than correlated subqueries is the
    # ClickHouse-idiomatic shape for this kind of fan-in.
    list_sql = f"""
        WITH
          ret_agg AS (
            SELECT trace_id, count() AS retrieval_count
            FROM retrievals
            WHERE project_id = %(pid)s
            GROUP BY trace_id
          ),
          chunk_agg AS (
            SELECT r.trace_id AS trace_id, count() AS chunk_count
            FROM retrieved_chunks c
            INNER JOIN retrievals r ON c.retrieval_id = r.retrieval_id
            WHERE r.project_id = %(pid)s AND c.project_id = %(pid)s
            GROUP BY r.trace_id
          ),
          cit_agg AS (
            SELECT trace_id, count() AS citation_count
            FROM citations
            WHERE project_id = %(pid)s
            GROUP BY trace_id
          )
        SELECT
          t.trace_id,
          t.start_time,
          t.model,
          t.latency_ms,
          t.tokens_in,
          t.tokens_out,
          t.status,
          ifNull(ret.retrieval_count, 0) > 0 AS has_retrieval,
          ifNull(chunk_agg.chunk_count, 0) AS chunk_count,
          ifNull(cit.citation_count, 0) AS citation_count
        FROM traces t
        LEFT JOIN ret_agg AS ret ON t.trace_id = ret.trace_id
        LEFT JOIN chunk_agg ON t.trace_id = chunk_agg.trace_id
        LEFT JOIN cit_agg AS cit ON t.trace_id = cit.trace_id
        WHERE {base_filter}
        ORDER BY t.start_time DESC, t.trace_id
        LIMIT %(limit)s OFFSET %(offset)s
    """
    list_params = {**params, "limit": limit, "offset": offset}

    # Total uses the same filter without limit/offset. For ``rag_only``
    # we still need the retrieval CTE because the filter references it.
    if rag_only:
        count_sql = f"""
            WITH ret_agg AS (
              SELECT trace_id, count() AS retrieval_count
              FROM retrievals WHERE project_id = %(pid)s GROUP BY trace_id
            )
            SELECT count()
            FROM traces t
            LEFT JOIN ret_agg AS ret ON t.trace_id = ret.trace_id
            WHERE {base_filter}
        """
    else:
        count_sql = f"SELECT count() FROM traces t WHERE {base_filter}"

    # clickhouse-connect's HTTP client raises on concurrent queries within
    # one session, and ``get_client()`` returns a process-wide cached
    # instance - so list + count must run serially. The runtime cost is
    # small at our scale.
    rows = await asyncio.to_thread(_query_rows, ch, list_sql, list_params)
    total = await asyncio.to_thread(_query_scalar_int, ch, count_sql, params)

    items = [
        {
            "trace_id": row[0],
            "start_time": row[1],
            "model": row[2],
            "latency_ms": int(row[3]),
            "tokens_in": int(row[4]),
            "tokens_out": int(row[5]),
            "status": row[6],
            "has_retrieval": bool(row[7]),
            "chunk_count": int(row[8]),
            "citation_count": int(row[9]),
        }
        for row in rows
    ]
    return items, total


def _build_trace_filter(
    *,
    project_id: UUID,
    rag_only: bool,
    start_from: datetime | None,
    start_to: datetime | None,
) -> tuple[str, dict[str, Any]]:
    clauses = ["t.project_id = %(pid)s"]
    params: dict[str, Any] = {"pid": str(project_id)}
    if start_from is not None:
        clauses.append("t.start_time >= %(start_from)s")
        params["start_from"] = start_from
    if start_to is not None:
        clauses.append("t.start_time <= %(start_to)s")
        params["start_to"] = start_to
    if rag_only:
        clauses.append("ifNull(ret.retrieval_count, 0) > 0")
    return " AND ".join(clauses), params


def _query_rows(ch: Client, sql: str, params: dict[str, Any]) -> list[tuple[Any, ...]]:
    return ch.query(sql, parameters=params).result_rows


def _query_scalar_int(ch: Client, sql: str, params: dict[str, Any]) -> int:
    rows = ch.query(sql, parameters=params).result_rows
    return int(rows[0][0]) if rows else 0


async def get_trace_detail(
    ch: Client,
    *,
    project_id: UUID,
    trace_id: UUID,
) -> dict[str, Any] | None:
    """Assemble the full RAG chain for one trace.

    Returns ``None`` when no trace with ``trace_id`` exists under
    ``project_id``. The caller turns ``None`` into a 404. The same
    response handles both "doesn't exist at all" and "exists but
    belongs to a different project" so cross-project enumeration
    isn't possible.
    """
    pid = str(project_id)
    tid = str(trace_id)

    trace_row = await asyncio.to_thread(_fetch_trace_row, ch, pid, tid)
    if trace_row is None:
        return None

    # See comment in list_traces() - one shared CH client, no concurrent
    # queries.
    retrieval_rows = await asyncio.to_thread(_fetch_retrieval_rows, ch, pid, tid)
    citation_rows = await asyncio.to_thread(_fetch_citation_rows, ch, pid, tid)

    chunk_rows: list[tuple[Any, ...]] = []
    if retrieval_rows:
        retrieval_ids = tuple(str(r[0]) for r in retrieval_rows)
        chunk_rows = await asyncio.to_thread(
            _fetch_chunk_rows, ch, pid, retrieval_ids
        )

    cited_chunk_ids = {row[1] for row in citation_rows}

    chunks_by_retrieval: dict[Any, list[dict[str, Any]]] = {}
    for c in chunk_rows:
        chunks_by_retrieval.setdefault(c[1], []).append(
            {
                "chunk_id": c[0],
                "rank": int(c[2]),
                "similarity_score": float(c[3]),
                "content": c[4],
                "source_doc_id": c[5],
                "doc_metadata": _safe_json(c[6]),
                "was_cited": c[0] in cited_chunk_ids,
            }
        )

    retrievals = [
        {
            "retrieval_id": r[0],
            "query": r[1],
            "embedding_model": r[2],
            "top_k": int(r[3]),
            "latency_ms": int(r[4]),
            "chunks": chunks_by_retrieval.get(r[0], []),
        }
        for r in retrieval_rows
    ]

    citations = [
        {
            "citation_id": c[0],
            "chunk_id": c[1],
            "response_span_start": int(c[2]),
            "response_span_end": int(c[3]),
        }
        for c in citation_rows
    ]

    return {
        "trace": {
            "trace_id": trace_row[0],
            "start_time": trace_row[1],
            "model": trace_row[2],
            "latency_ms": int(trace_row[3]),
            "tokens_in": int(trace_row[4]),
            "tokens_out": int(trace_row[5]),
            "status": trace_row[6],
            "attributes": _safe_json(trace_row[7]),
        },
        "retrievals": retrievals,
        "citations": citations,
    }


def _fetch_trace_row(ch: Client, pid: str, tid: str) -> tuple[Any, ...] | None:
    rows = ch.query(
        "SELECT trace_id, start_time, model, latency_ms, tokens_in, tokens_out, status, attributes "
        "FROM traces WHERE project_id = %(pid)s AND trace_id = %(tid)s LIMIT 1",
        parameters={"pid": pid, "tid": tid},
    ).result_rows
    return rows[0] if rows else None


def _fetch_retrieval_rows(ch: Client, pid: str, tid: str) -> list[tuple[Any, ...]]:
    return ch.query(
        "SELECT retrieval_id, query, embedding_model, top_k, latency_ms "
        "FROM retrievals WHERE project_id = %(pid)s AND trace_id = %(tid)s "
        "ORDER BY timestamp, retrieval_id",
        parameters={"pid": pid, "tid": tid},
    ).result_rows


def _fetch_citation_rows(ch: Client, pid: str, tid: str) -> list[tuple[Any, ...]]:
    return ch.query(
        "SELECT citation_id, chunk_id, response_span_start, response_span_end "
        "FROM citations WHERE project_id = %(pid)s AND trace_id = %(tid)s "
        "ORDER BY response_span_start, citation_id",
        parameters={"pid": pid, "tid": tid},
    ).result_rows


def _fetch_chunk_rows(
    ch: Client, pid: str, retrieval_ids: tuple[str, ...]
) -> list[tuple[Any, ...]]:
    return ch.query(
        "SELECT chunk_id, retrieval_id, rank, similarity_score, content, source_doc_id, doc_metadata "
        "FROM retrieved_chunks "
        "WHERE project_id = %(pid)s AND retrieval_id IN %(rids)s "
        "ORDER BY retrieval_id, rank",
        parameters={"pid": pid, "rids": retrieval_ids},
    ).result_rows


def _safe_json(value: Any) -> dict[str, Any]:
    """Parse a JSON-encoded String column. Return {} on bad input rather
    than crashing the read - a malformed row shouldn't 500 a dashboard."""
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        _log.warning("read: failed to parse JSON column %r", value)
        return {}
    return parsed if isinstance(parsed, dict) else {}


__all__ = [
    "DEFAULT_LIST_LIMIT",
    "MAX_LIST_LIMIT",
    "get_trace_detail",
    "list_traces",
]
