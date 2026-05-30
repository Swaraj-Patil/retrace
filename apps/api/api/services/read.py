"""Read-side queries against ClickHouse.

All queries are scoped by ``project_id`` from the auth context - that
is a security boundary, enforced in test_read_traces.py with a second
project.

ClickHouse SQL stays in this module; routers stay thin.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from clickhouse_connect.driver.client import Client

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

    rows, total = await asyncio.gather(
        asyncio.to_thread(_query_rows, ch, list_sql, list_params),
        asyncio.to_thread(_query_scalar_int, ch, count_sql, params),
    )

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


__all__ = ["DEFAULT_LIST_LIMIT", "MAX_LIST_LIMIT", "list_traces"]
