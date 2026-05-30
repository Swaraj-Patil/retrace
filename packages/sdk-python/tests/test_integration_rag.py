"""End-to-end RAG flow: SDK -> in-process FastAPI -> ClickHouse.

Drives a full RAG flow (trace -> retrieval with 4 chunks -> fake
OpenAI call -> 2 citations) through ASGITransport into the live
API, asserts all four entity types landed in ClickHouse with the
right counts, and - **the load-bearing contract** - asserts every
entity links back to the same trace_id.

That shared-trace_id assertion is *the* contract Retrace is built
around: the ability to see, for a given trace, every retrieval and
every chunk and every citation that contributed to it. If
``assert_all_entities_share_trace_id`` ever fails, the RAG-native
claim is broken and any "fix" should be a real fix, not a relaxed
assertion.

Fixture duplication note: ``_install_fake_openai`` and
``_dispose_api_engine_via_runtime`` parallel the ones in
test_integration.py. We duplicate rather than share via a helper
module because pytest's namespace-package handling for the two
``tests/`` dirs in this repo makes cross-file test imports brittle.
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from clickhouse_connect.driver import Client
from httpx import ASGITransport

import retrace
from retrace.instrumentation import _openai

from api.clickhouse.client import get_client
from api.db.session import engine as api_engine
from api.main import app as api_app

_RAG_TABLES = ("traces", "retrievals", "retrieved_chunks", "citations")


@pytest_asyncio.fixture(autouse=True)
async def _clean_clickhouse_all_four(
    sdk_test_api_key: tuple[str, UUID],
) -> AsyncIterator[None]:
    """Wipe every RAG table for the SDK test project before each test."""
    _, project_id = sdk_test_api_key
    pid = str(project_id)
    ch = get_client()
    for table in _RAG_TABLES:
        await asyncio.to_thread(
            ch.command,
            f"ALTER TABLE {table} DELETE WHERE project_id = %(pid)s",
            parameters={"pid": pid},
            settings={"mutations_sync": 2},
        )
    yield


@pytest_asyncio.fixture
async def _dispose_api_engine_via_runtime() -> AsyncIterator[None]:
    """Dispose the API engine on the SDK runtime's loop after the test.

    flush() runs the ASGI app on the runtime loop, so SQLAlchemy opens
    connections there. Disposing from a different loop trips asyncpg.
    """
    yield
    from retrace._runtime import get_runtime

    runtime = get_runtime()
    if runtime.is_running():
        try:
            future = runtime.submit(api_engine.dispose())
            future.result(timeout=5.0)
        except Exception:
            pass


def _install_fake_openai(monkeypatch: pytest.MonkeyPatch) -> type:
    class FakeCompletions:
        def create(self, **kwargs: Any) -> Any:
            return MagicMock(
                model=kwargs.get("model"),
                usage=MagicMock(prompt_tokens=120, completion_tokens=80),
            )

    fake_root = types.ModuleType("openai")
    fake_resources = types.ModuleType("openai.resources")
    fake_chat = types.ModuleType("openai.resources.chat")
    fake_completions_mod = types.ModuleType("openai.resources.chat.completions")
    fake_completions_mod.Completions = FakeCompletions  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "openai", fake_root)
    monkeypatch.setitem(sys.modules, "openai.resources", fake_resources)
    monkeypatch.setitem(sys.modules, "openai.resources.chat", fake_chat)
    monkeypatch.setitem(
        sys.modules, "openai.resources.chat.completions", fake_completions_mod
    )
    return FakeCompletions


async def test_full_rag_flow_lands_in_clickhouse_with_shared_trace_id(
    sdk_test_api_key: tuple[str, UUID],
    monkeypatch: pytest.MonkeyPatch,
    _dispose_api_engine_via_runtime: None,
) -> None:
    raw_key, project_id = sdk_test_api_key
    fake_completions_cls = _install_fake_openai(monkeypatch)

    # Send everything in one batch so the API's FK closure resolves in-batch
    # rather than across multiple HTTP requests.
    retrace._configure_for_testing(transport=ASGITransport(app=api_app))
    retrace.init(
        api_key=raw_key,
        endpoint="http://retrace-rag-test",
        batch_size=100,
        flush_interval=60.0,
    )

    try:
        # Pinning the trace_id is what lets the wedge assertion below be a
        # strict equality check, not a "they all match each other" check.
        known_trace_id = uuid4()

        with retrace.trace(trace_id=known_trace_id):
            with retrace.retrieval(
                query="What is RAG?",
                embedding_model="text-embedding-3-small",
                top_k=4,
            ) as r:
                for rank in range(4):
                    r.log_chunk(
                        chunk_id=f"chunk-{rank}",
                        rank=rank,
                        similarity_score=0.9 - rank * 0.1,
                        content=f"chunk content {rank}",
                        source_doc_id=f"doc-{rank}",
                        doc_metadata={"page": rank + 1},
                    )

            fake_completions_cls().create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Use the chunks to answer."}],
                temperature=0.3,
            )

            retrace.log_citation(
                chunk_id="chunk-0", response_span_start=0, response_span_end=40
            )
            retrace.log_citation(
                chunk_id="chunk-1", response_span_start=41, response_span_end=80
            )

        retrace.flush(timeout=10.0)

        ch = get_client()
        pid = str(project_id)

        counts = await asyncio.to_thread(_count_all, ch, pid)
        assert counts == {
            "traces": 1,
            "retrievals": 1,
            "retrieved_chunks": 4,
            "citations": 2,
        }, f"unexpected row counts: {counts}"

        await asyncio.to_thread(
            assert_all_entities_share_trace_id, ch, pid, known_trace_id
        )
    finally:
        _openai.uninstall()


def _count_all(ch: Client, project_id_str: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _RAG_TABLES:
        rows = ch.query(
            f"SELECT count() FROM {table} WHERE project_id = %(pid)s",
            parameters={"pid": project_id_str},
        ).result_rows
        counts[table] = int(rows[0][0])
    return counts


def assert_all_entities_share_trace_id(
    ch: Client, project_id_str: str, expected_trace_id: UUID
) -> None:
    """**The wedge contract.**

    Every row across all four RAG tables - whether it carries trace_id
    directly (traces, retrievals, citations) or reaches it via FK
    through retrievals (retrieved_chunks) - must resolve to the same
    expected_trace_id. The RAG-native value prop is *this linkage*;
    if this fails, traces/retrievals/citations have become disconnected
    and the product is no longer the thing we sell.

    Future maintainer: if you find yourself relaxing this assertion to
    make a test pass, stop. Fix the linkage instead.
    """
    expected = str(expected_trace_id)

    direct_columns: dict[str, set[str]] = {}
    for table in ("traces", "retrievals", "citations"):
        rows = ch.query(
            f"SELECT trace_id FROM {table} WHERE project_id = %(pid)s",
            parameters={"pid": project_id_str},
        ).result_rows
        direct_columns[table] = {str(r[0]) for r in rows}

    chunk_trace_ids = {
        str(row[0])
        for row in ch.query(
            "SELECT r.trace_id "
            "FROM retrieved_chunks c "
            "INNER JOIN retrievals r ON c.retrieval_id = r.retrieval_id "
            "WHERE c.project_id = %(pid)s",
            parameters={"pid": project_id_str},
        ).result_rows
    }

    bound = {**direct_columns, "retrieved_chunks (via retrievals)": chunk_trace_ids}
    for entity, trace_ids in bound.items():
        assert trace_ids == {expected}, (
            f"RAG linkage broken at {entity}: expected {{{expected}}}, got {trace_ids}. "
            f"Every entity in a single RAG flow must share the same trace_id; "
            f"this is the wedge contract."
        )
