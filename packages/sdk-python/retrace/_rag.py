"""Manual RAG instrumentation: trace/retrieval scopes, log_chunk/log_citation, decorator.

Public surface (re-exported from ``retrace``):
- ``trace(trace_id=None)``        cross-operation trace scope
- ``retrieval(query, ...)``       retrieval scope yielding a handle with log_chunk/log_chunks
- ``log_chunk(...)``              attach to the *current* retrieval (contextvar)
- ``log_chunks(iterable)``        bulk form; invalid chunks are skipped individually
- ``log_citation(...)``           attach to the *current* trace (contextvar)
- ``@trace_retrieval(...)``       decorator sugar over the retrieval context manager

All functions follow the never-raise contract: bad input is logged at
WARNING and the event is dropped. SDK bugs never propagate to user code.

The chunk_id UUID5 namespace is **stable** so the same string id always
maps to the same UUID across calls, processes, and sessions. That
contract is load-bearing for ``log_citation`` to be able to reference
chunks by their original string id.
"""

from __future__ import annotations

import asyncio
import functools
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

from retrace._context import current_retrieval_id, current_trace_id
from retrace._logging import get_logger
from retrace._models import ChunkEvent, CitationEvent, RetrievalEvent

_log = get_logger()

# Stable namespace for coercing non-UUID chunk_id strings. Do not change
# without considering that existing log_chunk/log_citation pairings break.
_CHUNK_ID_NS = uuid5(NAMESPACE_DNS, "retrace.sdk.chunk")
_MAX_CONTENT_CHARS = 8192


def _coerce_trace_id(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        _log.warning(
            "retrace: trace_id %r is not a valid UUID; generating a fresh one", value
        )
        return uuid4()


def _coerce_chunk_id(value: Any) -> UUID:
    """UUIDs pass through. UUID-shaped strings are parsed. Anything else
    is hashed into a deterministic UUID5 under the stable chunk namespace."""
    if isinstance(value, UUID):
        return value
    s = str(value)
    try:
        return UUID(s)
    except (ValueError, TypeError):
        return uuid5(_CHUNK_ID_NS, s)


@contextmanager
def trace(trace_id: UUID | str | None = None):
    """Cross-operation trace scope.

    All auto-instrumented LLM calls, retrievals, and citations made
    inside this ``with`` block share the same ``trace_id``. Nested
    ``trace()`` calls are supported; the inner scope gets its own
    ``trace_id`` and the outer is restored on exit.
    """
    if trace_id is None:
        resolved = uuid4()
    else:
        resolved = _coerce_trace_id(trace_id)

    token = current_trace_id.set(resolved)
    try:
        yield resolved
    finally:
        try:
            current_trace_id.reset(token)
        except Exception:
            _log.warning("retrace: error restoring trace_id", exc_info=True)


class _RetrievalHandle:
    """Yielded by ``retrace.retrieval()``. Lets users call ``log_chunk``
    via the handle or via the module-level helper interchangeably."""

    def __init__(self, retrieval_id: UUID, trace_id: UUID) -> None:
        self.retrieval_id = retrieval_id
        self.trace_id = trace_id

    def log_chunk(self, **kwargs: Any) -> None:
        log_chunk(**kwargs)

    def log_chunks(self, chunks: Any) -> None:
        log_chunks(chunks)


@contextmanager
def retrieval(
    *,
    query: str,
    embedding_model: str = "",
    top_k: int = 0,
):
    """Retrieval scope.

    On exit (even on exception), emits one ``RetrievalEvent``. Chunks
    logged inside via ``r.log_chunk`` / ``log_chunk`` are emitted
    immediately as ``ChunkEvent``s, not buffered until the scope ends.

    If no outer ``trace()`` scope is active, a fresh trace_id is
    generated and scoped to this retrieval's lifetime (consistent with
    Day 4 instrumentation behavior).
    """
    retrieval_id = uuid4()
    span_id = uuid4()

    outer_trace_id = current_trace_id.get()
    trace_token = None
    if outer_trace_id is None:
        trace_id = uuid4()
        trace_token = current_trace_id.set(trace_id)
    else:
        trace_id = outer_trace_id

    retrieval_token = current_retrieval_id.set(retrieval_id)

    start_perf = time.monotonic()
    timestamp = datetime.now(UTC)

    try:
        yield _RetrievalHandle(retrieval_id, trace_id)
    finally:
        try:
            latency_ms = max(0, int((time.monotonic() - start_perf) * 1000))
            event = RetrievalEvent(
                retrieval_id=retrieval_id,
                trace_id=trace_id,
                span_id=span_id,
                query=str(query) if query is not None else "",
                embedding_model=str(embedding_model or ""),
                top_k=int(top_k) if isinstance(top_k, int) and top_k >= 0 else 0,
                latency_ms=latency_ms,
                timestamp=timestamp,
            )
            _enqueue(event)
        except Exception:
            _log.warning("retrace: error emitting retrieval event", exc_info=True)

        try:
            current_retrieval_id.reset(retrieval_token)
        except Exception:
            _log.warning("retrace: error restoring retrieval_id", exc_info=True)
        if trace_token is not None:
            try:
                current_trace_id.reset(trace_token)
            except Exception:
                _log.warning("retrace: error restoring trace_id", exc_info=True)


def log_chunk(
    *,
    chunk_id: Any,
    rank: int,
    similarity_score: float,
    content: str,
    source_doc_id: str = "",
    doc_metadata: dict[str, Any] | None = None,
) -> None:
    """Log one retrieved chunk to the *current* retrieval scope.

    Drops the chunk (with a warning) if any of: no active retrieval,
    invalid ``rank``, invalid ``similarity_score``, ``content`` is
    ``None``. Truncates ``content`` to 8192 chars with a warning if
    longer. Never raises.
    """
    try:
        retrieval_id = current_retrieval_id.get()
        if retrieval_id is None:
            _log.warning("retrace: log_chunk called outside a retrieval scope; dropped")
            return

        if chunk_id is None:
            _log.warning("retrace: log_chunk requires chunk_id; dropped")
            return

        if not isinstance(rank, bool) and isinstance(rank, int) and rank >= 0:
            rank_val = rank
        else:
            _log.warning("retrace: log_chunk invalid rank %r; dropped", rank)
            return

        try:
            score = float(similarity_score)
        except (TypeError, ValueError):
            _log.warning(
                "retrace: log_chunk invalid similarity_score %r; dropped",
                similarity_score,
            )
            return
        if not (0.0 <= score <= 1.0):
            _log.warning(
                "retrace: log_chunk similarity_score %s out of [0.0, 1.0]; dropped",
                score,
            )
            return

        if content is None:
            _log.warning("retrace: log_chunk content is None; dropped")
            return
        content_str = str(content)
        if len(content_str) > _MAX_CONTENT_CHARS:
            _log.warning(
                "retrace: log_chunk content truncated from %d to %d chars",
                len(content_str),
                _MAX_CONTENT_CHARS,
            )
            content_str = content_str[:_MAX_CONTENT_CHARS]

        event = ChunkEvent(
            chunk_id=_coerce_chunk_id(chunk_id),
            retrieval_id=retrieval_id,
            rank=rank_val,
            similarity_score=score,
            content=content_str,
            source_doc_id=str(source_doc_id) if source_doc_id else "",
            doc_metadata=dict(doc_metadata) if doc_metadata else {},
            timestamp=datetime.now(UTC),
        )
        _enqueue(event)
    except Exception:
        _log.warning("retrace: unexpected error in log_chunk", exc_info=True)


def log_chunks(chunks: Any) -> None:
    """Log multiple chunks. Iterable of dicts; each entry is splatted into
    ``log_chunk`` so invalid keys raise a TypeError that we catch and
    skip that one chunk only."""
    try:
        if not chunks:
            return
        for entry in chunks:
            try:
                log_chunk(**entry)
            except TypeError:
                _log.warning("retrace: log_chunks entry has unexpected keys; skipped")
            except Exception:
                _log.warning("retrace: error logging one chunk; skipped", exc_info=True)
    except Exception:
        _log.warning("retrace: unexpected error in log_chunks", exc_info=True)


def log_citation(
    *,
    chunk_id: Any,
    response_span_start: int,
    response_span_end: int,
) -> None:
    """Link a chunk to a span of the response, attached to the current trace.

    Requires an active ``trace()`` (or retrieval, which auto-opens one).
    No-ops with a warning if no trace is active. The chunk_id is coerced
    via the same stable namespace as ``log_chunk``, so passing the same
    string id in both yields the same UUID.
    """
    try:
        trace_id = current_trace_id.get()
        if trace_id is None:
            _log.warning("retrace: log_citation requires an active trace; dropped")
            return

        if chunk_id is None:
            _log.warning("retrace: log_citation requires chunk_id; dropped")
            return

        if (
            isinstance(response_span_start, bool)
            or not isinstance(response_span_start, int)
            or response_span_start < 0
        ):
            _log.warning(
                "retrace: log_citation invalid response_span_start %r; dropped",
                response_span_start,
            )
            return
        if (
            isinstance(response_span_end, bool)
            or not isinstance(response_span_end, int)
            or response_span_end < 0
        ):
            _log.warning(
                "retrace: log_citation invalid response_span_end %r; dropped",
                response_span_end,
            )
            return

        event = CitationEvent(
            citation_id=uuid4(),
            trace_id=trace_id,
            chunk_id=_coerce_chunk_id(chunk_id),
            response_span_start=response_span_start,
            response_span_end=response_span_end,
            timestamp=datetime.now(UTC),
        )
        _enqueue(event)
    except Exception:
        _log.warning("retrace: unexpected error in log_citation", exc_info=True)


def trace_retrieval(*dargs: Any, **dkwargs: Any):
    """Decorator sugar over ``retrieval()``.

    Supports both bare and parenthesized forms::

        @trace_retrieval                       # bare; embedding_model="", top_k=0
        def fetch(query): ...

        @trace_retrieval(embedding_model=..., top_k=...)
        def fetch(query): ...

    The wrapped function's ``query`` is taken from:
      1. the ``query=`` kwarg, if present
      2. else the first positional argument (including ``self`` if this
         decorates a method - pass ``query=`` explicitly to avoid that)
      3. else empty string with a warning

    Works on sync and async functions. The user's function is never
    prevented from running by SDK-side errors.
    """
    # Bare form detection: @trace_retrieval applied directly to a callable.
    if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
        return _make_retrieval_decorator(embedding_model="", top_k=0)(dargs[0])

    if dargs:
        _log.warning(
            "retrace: @trace_retrieval ignores positional args; pass embedding_model=, top_k= as kwargs"
        )

    return _make_retrieval_decorator(
        embedding_model=dkwargs.get("embedding_model", ""),
        top_k=dkwargs.get("top_k", 0),
    )


def _make_retrieval_decorator(*, embedding_model: str, top_k: int):
    def decorator(fn: Any) -> Any:
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    query = _extract_query(args, kwargs)
                    cm = retrieval(query=query, embedding_model=embedding_model, top_k=top_k)
                except Exception:
                    _log.warning(
                        "retrace: error setting up @trace_retrieval; calling unwrapped",
                        exc_info=True,
                    )
                    return await fn(*args, **kwargs)
                with cm:
                    return await fn(*args, **kwargs)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                query = _extract_query(args, kwargs)
                cm = retrieval(query=query, embedding_model=embedding_model, top_k=top_k)
            except Exception:
                _log.warning(
                    "retrace: error setting up @trace_retrieval; calling unwrapped",
                    exc_info=True,
                )
                return fn(*args, **kwargs)
            with cm:
                return fn(*args, **kwargs)

        return sync_wrapper

    return decorator


def _extract_query(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    if "query" in kwargs:
        v = kwargs["query"]
        return str(v) if v is not None else ""
    if args:
        v = args[0]
        return str(v) if v is not None else ""
    _log.warning(
        "retrace: @trace_retrieval could not determine query from call args; using empty string"
    )
    return ""


def _enqueue(event: Any) -> None:
    # Lazy import to avoid the retrace -> _rag -> retrace cycle at module load.
    import retrace

    retrace._enqueue_event(event)


__all__ = [
    "log_chunk",
    "log_chunks",
    "log_citation",
    "retrieval",
    "trace",
    "trace_retrieval",
]
