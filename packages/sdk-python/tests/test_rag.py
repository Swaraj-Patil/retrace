"""Unit tests for the manual RAG instrumentation API.

Tests bypass the runtime/sender by monkeypatching ``retrace._enqueue_event``
into a list. The contract under test is "the right events with the
right fields land in the buffer," not the network path - that's the
integration test's job.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

import retrace
from retrace._context import (
    current_retrieval_id,
    current_trace_id,
)
from retrace._models import (
    AnyEvent,
    ChunkEvent,
    CitationEvent,
    RetrievalEvent,
    serialize_payload,
)
from retrace._rag import _CHUNK_ID_NS, _coerce_chunk_id


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[AnyEvent]:
    events: list[AnyEvent] = []
    monkeypatch.setattr(retrace, "_enqueue_event", events.append)
    return events


# ---------- trace() context manager ----------


def test_trace_sets_and_restores_contextvar() -> None:
    assert current_trace_id.get() is None
    with retrace.trace() as tid:
        assert isinstance(tid, UUID)
        assert current_trace_id.get() == tid
    assert current_trace_id.get() is None


def test_trace_accepts_explicit_uuid() -> None:
    explicit = uuid4()
    with retrace.trace(trace_id=explicit) as tid:
        assert tid == explicit
        assert current_trace_id.get() == explicit


def test_trace_accepts_uuid_string() -> None:
    explicit = uuid4()
    with retrace.trace(trace_id=str(explicit)) as tid:
        assert tid == explicit


def test_trace_falls_back_on_invalid_string() -> None:
    with retrace.trace(trace_id="not-a-uuid") as tid:
        assert isinstance(tid, UUID)  # generated fresh
        assert current_trace_id.get() == tid


def test_nested_trace_restores_outer() -> None:
    with retrace.trace() as outer:
        with retrace.trace() as inner:
            assert inner != outer
            assert current_trace_id.get() == inner
        assert current_trace_id.get() == outer
    assert current_trace_id.get() is None


def test_trace_restores_on_exception() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with retrace.trace():
            raise RuntimeError("boom")
    assert current_trace_id.get() is None


# ---------- retrieval() context manager ----------


def test_retrieval_emits_event_on_exit(captured: list[AnyEvent]) -> None:
    with retrace.retrieval(
        query="What is RAG?", embedding_model="text-embedding-3-small", top_k=5
    ) as r:
        assert isinstance(r.retrieval_id, UUID)
        assert isinstance(r.trace_id, UUID)
    [event] = captured
    assert isinstance(event, RetrievalEvent)
    assert event.query == "What is RAG?"
    assert event.embedding_model == "text-embedding-3-small"
    assert event.top_k == 5
    assert event.latency_ms >= 0


def test_retrieval_emits_event_even_on_exception(captured: list[AnyEvent]) -> None:
    with pytest.raises(RuntimeError):
        with retrace.retrieval(query="q", embedding_model="m", top_k=1):
            raise RuntimeError("user code blew up")
    [event] = captured
    assert isinstance(event, RetrievalEvent)


def test_retrieval_inside_trace_shares_trace_id(captured: list[AnyEvent]) -> None:
    with retrace.trace() as tid:
        with retrace.retrieval(query="q", embedding_model="m", top_k=1) as r:
            assert r.trace_id == tid
    [event] = captured
    assert event.trace_id == tid


def test_retrieval_without_trace_generates_scoped_trace_id(
    captured: list[AnyEvent],
) -> None:
    assert current_trace_id.get() is None
    with retrace.retrieval(query="q", embedding_model="m", top_k=1) as r:
        # During the scope, trace_id is set so log_citation could work.
        assert current_trace_id.get() == r.trace_id
    # After the scope, the auto-generated trace_id is gone.
    assert current_trace_id.get() is None
    [event] = captured
    assert event.trace_id == r.trace_id


def test_retrieval_restores_outer_retrieval_id() -> None:
    with retrace.retrieval(query="outer", embedding_model="m", top_k=1) as outer:
        assert current_retrieval_id.get() == outer.retrieval_id
        with retrace.retrieval(query="inner", embedding_model="m", top_k=1) as inner:
            assert current_retrieval_id.get() == inner.retrieval_id
        assert current_retrieval_id.get() == outer.retrieval_id
    assert current_retrieval_id.get() is None


# ---------- log_chunk ----------


def test_log_chunk_inside_retrieval_emits(captured: list[AnyEvent]) -> None:
    with retrace.retrieval(query="q", embedding_model="m", top_k=1) as r:
        r.log_chunk(
            chunk_id="c1",
            rank=0,
            similarity_score=0.9,
            content="hello world",
            source_doc_id="doc-1",
            doc_metadata={"page": 3},
        )
    # 1 ChunkEvent + 1 RetrievalEvent
    chunk = next(e for e in captured if isinstance(e, ChunkEvent))
    assert chunk.retrieval_id == r.retrieval_id
    assert chunk.rank == 0
    assert chunk.similarity_score == 0.9
    assert chunk.content == "hello world"
    assert chunk.source_doc_id == "doc-1"
    assert chunk.doc_metadata == {"page": 3}


def test_log_chunk_outside_retrieval_drops_event(captured: list[AnyEvent]) -> None:
    retrace.log_chunk(chunk_id="c1", rank=0, similarity_score=0.5, content="x")
    assert not any(isinstance(e, ChunkEvent) for e in captured)


def test_log_chunk_invalid_score_drops_only_that_chunk(
    captured: list[AnyEvent],
) -> None:
    with retrace.retrieval(query="q", embedding_model="m", top_k=3):
        retrace.log_chunk(chunk_id="a", rank=0, similarity_score=0.5, content="ok")
        retrace.log_chunk(chunk_id="b", rank=1, similarity_score=1.5, content="bad")
        retrace.log_chunk(chunk_id="c", rank=2, similarity_score=0.8, content="ok2")
    chunks = [e for e in captured if isinstance(e, ChunkEvent)]
    assert len(chunks) == 2
    assert {c.content for c in chunks} == {"ok", "ok2"}


def test_log_chunk_negative_rank_drops_event(captured: list[AnyEvent]) -> None:
    with retrace.retrieval(query="q", embedding_model="m", top_k=1):
        retrace.log_chunk(chunk_id="a", rank=-1, similarity_score=0.5, content="x")
    assert not any(isinstance(e, ChunkEvent) for e in captured)


def test_log_chunk_content_truncated_above_limit(captured: list[AnyEvent]) -> None:
    huge = "a" * 9000
    with retrace.retrieval(query="q", embedding_model="m", top_k=1):
        retrace.log_chunk(chunk_id="a", rank=0, similarity_score=0.5, content=huge)
    [chunk] = [e for e in captured if isinstance(e, ChunkEvent)]
    assert len(chunk.content) == 8192


def test_log_chunk_none_content_drops_event(captured: list[AnyEvent]) -> None:
    with retrace.retrieval(query="q", embedding_model="m", top_k=1):
        retrace.log_chunk(chunk_id="a", rank=0, similarity_score=0.5, content=None)  # type: ignore[arg-type]
    assert not any(isinstance(e, ChunkEvent) for e in captured)


def test_log_chunk_coerces_non_uuid_string(captured: list[AnyEvent]) -> None:
    expected = _coerce_chunk_id("chunk-xyz")
    with retrace.retrieval(query="q", embedding_model="m", top_k=1):
        retrace.log_chunk(chunk_id="chunk-xyz", rank=0, similarity_score=0.5, content="x")
    [chunk] = [e for e in captured if isinstance(e, ChunkEvent)]
    assert chunk.chunk_id == expected


def test_chunk_id_namespace_is_stable() -> None:
    """The same string id must coerce to the same UUID across calls,
    sessions, and processes. Otherwise log_citation can't reference
    chunks logged earlier."""
    a = _coerce_chunk_id("chunk-1")
    b = _coerce_chunk_id("chunk-1")
    assert a == b
    # And the namespace is the documented stable one.
    from uuid import NAMESPACE_DNS, uuid5

    assert _CHUNK_ID_NS == uuid5(NAMESPACE_DNS, "retrace.sdk.chunk")


def test_log_chunks_bulk_skips_invalid(captured: list[AnyEvent]) -> None:
    with retrace.retrieval(query="q", embedding_model="m", top_k=3):
        retrace.log_chunks(
            [
                {"chunk_id": "a", "rank": 0, "similarity_score": 0.9, "content": "x"},
                {"chunk_id": "b", "rank": 1, "similarity_score": 2.0, "content": "y"},
                {"chunk_id": "c", "rank": 2, "similarity_score": 0.5, "content": "z"},
            ]
        )
    chunks = [e for e in captured if isinstance(e, ChunkEvent)]
    assert {c.content for c in chunks} == {"x", "z"}


def test_log_chunks_skips_entry_with_unexpected_key(
    captured: list[AnyEvent],
) -> None:
    with retrace.retrieval(query="q", embedding_model="m", top_k=2):
        retrace.log_chunks(
            [
                {"chunk_id": "a", "rank": 0, "similarity_score": 0.9, "content": "x"},
                {
                    "chunk_id": "b",
                    "rank": 1,
                    "similarity_score": 0.5,
                    "content": "y",
                    "garbage_kwarg": True,
                },
            ]
        )
    chunks = [e for e in captured if isinstance(e, ChunkEvent)]
    assert {c.content for c in chunks} == {"x"}


# ---------- log_citation ----------


def test_log_citation_without_trace_drops(captured: list[AnyEvent]) -> None:
    retrace.log_citation(chunk_id="c1", response_span_start=0, response_span_end=10)
    assert not any(isinstance(e, CitationEvent) for e in captured)


def test_log_citation_inside_trace_emits(captured: list[AnyEvent]) -> None:
    with retrace.trace() as tid:
        retrace.log_citation(chunk_id="c1", response_span_start=0, response_span_end=40)
    [citation] = [e for e in captured if isinstance(e, CitationEvent)]
    assert citation.trace_id == tid
    assert citation.response_span_start == 0
    assert citation.response_span_end == 40


def test_log_citation_chunk_id_matches_log_chunk(captured: list[AnyEvent]) -> None:
    """A citation referencing the same string id as a logged chunk must
    resolve to the same UUID. This is the central contract."""
    with retrace.trace():
        with retrace.retrieval(query="q", embedding_model="m", top_k=1):
            retrace.log_chunk(chunk_id="c1", rank=0, similarity_score=0.9, content="x")
        retrace.log_citation(
            chunk_id="c1", response_span_start=0, response_span_end=5
        )
    [chunk] = [e for e in captured if isinstance(e, ChunkEvent)]
    [citation] = [e for e in captured if isinstance(e, CitationEvent)]
    assert citation.chunk_id == chunk.chunk_id


def test_log_citation_negative_span_drops(captured: list[AnyEvent]) -> None:
    with retrace.trace():
        retrace.log_citation(
            chunk_id="c1", response_span_start=-1, response_span_end=10
        )
        retrace.log_citation(
            chunk_id="c2", response_span_start=0, response_span_end=-3
        )
    assert not any(isinstance(e, CitationEvent) for e in captured)


# ---------- @trace_retrieval decorator ----------


def test_decorator_parenthesized_form(captured: list[AnyEvent]) -> None:
    @retrace.trace_retrieval(embedding_model="m1", top_k=3)
    def fetch(query: str) -> list[str]:
        return ["chunk-a", "chunk-b"]

    result = fetch("what is rag?")
    assert result == ["chunk-a", "chunk-b"]
    [event] = [e for e in captured if isinstance(e, RetrievalEvent)]
    assert event.query == "what is rag?"
    assert event.embedding_model == "m1"
    assert event.top_k == 3


def test_decorator_bare_form_uses_defaults(captured: list[AnyEvent]) -> None:
    @retrace.trace_retrieval
    def fetch(query: str) -> str:
        return "ok"

    fetch("hello")
    [event] = [e for e in captured if isinstance(e, RetrievalEvent)]
    assert event.query == "hello"
    assert event.embedding_model == ""
    assert event.top_k == 0


def test_decorator_no_paren_factory_form(captured: list[AnyEvent]) -> None:
    @retrace.trace_retrieval()
    def fetch(query: str) -> str:
        return "ok"

    fetch("hi")
    [event] = [e for e in captured if isinstance(e, RetrievalEvent)]
    assert event.query == "hi"


def test_decorator_prefers_kwarg_query(captured: list[AnyEvent]) -> None:
    @retrace.trace_retrieval(embedding_model="m", top_k=1)
    def fetch(*args: Any, **kwargs: Any) -> None:
        pass

    fetch("from_positional", query="from_kwarg")
    [event] = [e for e in captured if isinstance(e, RetrievalEvent)]
    assert event.query == "from_kwarg"


def test_decorator_warns_when_query_absent(
    captured: list[AnyEvent], caplog: pytest.LogCaptureFixture
) -> None:
    @retrace.trace_retrieval(embedding_model="m", top_k=1)
    def fetch() -> None:
        pass

    with caplog.at_level("WARNING", logger="retrace"):
        fetch()

    [event] = [e for e in captured if isinstance(e, RetrievalEvent)]
    assert event.query == ""
    assert any("could not determine query" in rec.message for rec in caplog.records)


async def test_decorator_works_on_async_function(captured: list[AnyEvent]) -> None:
    @retrace.trace_retrieval(embedding_model="m", top_k=2)
    async def fetch(query: str) -> str:
        return "async-result"

    result = await fetch("async-query")
    assert result == "async-result"
    [event] = [e for e in captured if isinstance(e, RetrievalEvent)]
    assert event.query == "async-query"


def test_decorator_user_exception_propagates(captured: list[AnyEvent]) -> None:
    @retrace.trace_retrieval(embedding_model="m", top_k=1)
    def fetch(query: str) -> None:
        raise RuntimeError("user blew up")

    with pytest.raises(RuntimeError, match="user blew up"):
        fetch("q")
    # Retrieval event still recorded (exit ran).
    assert any(isinstance(e, RetrievalEvent) for e in captured)


# ---------- serialize_payload dispatch ----------


def test_serialize_payload_dispatches_all_four_arrays() -> None:
    import json

    with retrace.trace() as tid:
        events: list[AnyEvent] = []

        # Build one of each via the public API by tapping into the contextvar.
        with retrace.retrieval(query="q", embedding_model="m", top_k=1) as r:
            events.append(
                _make_chunk(retrieval_id=r.retrieval_id, content="hi")
            )
        # retrieval scope's exit already pushed a RetrievalEvent through
        # _enqueue_event, but we're working with hand-built events here.
        events.append(
            _make_retrieval(retrieval_id=r.retrieval_id, trace_id=tid, query="q")
        )
        events.append(_make_trace(trace_id=tid))
        events.append(_make_citation(trace_id=tid, chunk_id=uuid4()))

    payload = json.loads(serialize_payload(events))
    assert {len(payload["traces"]), len(payload["retrievals"]), len(payload["chunks"]), len(payload["citations"])} == {1}


# ---------- helpers ----------


def _make_chunk(*, retrieval_id: UUID, content: str) -> ChunkEvent:
    from datetime import UTC, datetime

    return ChunkEvent(
        chunk_id=uuid4(),
        retrieval_id=retrieval_id,
        rank=0,
        similarity_score=0.5,
        content=content,
        source_doc_id="",
        timestamp=datetime.now(UTC),
    )


def _make_retrieval(*, retrieval_id: UUID, trace_id: UUID, query: str) -> RetrievalEvent:
    from datetime import UTC, datetime

    return RetrievalEvent(
        retrieval_id=retrieval_id,
        trace_id=trace_id,
        span_id=uuid4(),
        query=query,
        embedding_model="m",
        top_k=1,
        latency_ms=1,
        timestamp=datetime.now(UTC),
    )


def _make_trace(*, trace_id: UUID) -> Any:
    from datetime import UTC, datetime

    from retrace._models import TraceEvent

    now = datetime.now(UTC)
    return TraceEvent(
        trace_id=trace_id,
        span_id=uuid4(),
        start_time=now,
        end_time=now,
        model="gpt-4o",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
        status="ok",
    )


def _make_citation(*, trace_id: UUID, chunk_id: UUID) -> CitationEvent:
    from datetime import UTC, datetime

    return CitationEvent(
        citation_id=uuid4(),
        trace_id=trace_id,
        chunk_id=chunk_id,
        response_span_start=0,
        response_span_end=10,
        timestamp=datetime.now(UTC),
    )
