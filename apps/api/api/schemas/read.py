"""Response schemas for the read API.

Every model uses ``_Strict`` so the response shape is enforced as part
of the public contract: accidentally added fields fail loudly in tests
rather than leaking out of the API.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from api.schemas._base import _Strict


class TraceListItem(_Strict):
    trace_id: UUID
    start_time: datetime
    model: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    status: str
    has_retrieval: bool
    chunk_count: int = Field(ge=0)
    citation_count: int = Field(ge=0)


class TraceListResponse(_Strict):
    traces: list[TraceListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class TraceMeta(_Strict):
    """Trace-level fields shown in the detail view. Narrower than
    ``TraceListItem`` (no aggregate counts) and wider (carries
    ``attributes``)."""

    trace_id: UUID
    start_time: datetime
    model: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    status: str
    attributes: dict[str, object] = Field(default_factory=dict)


class ChunkDetail(_Strict):
    chunk_id: UUID
    rank: int = Field(ge=0)
    similarity_score: float = Field(ge=0.0, le=1.0)
    content: str
    source_doc_id: str
    doc_metadata: dict[str, object] = Field(default_factory=dict)
    # True iff this chunk_id appears in the trace's citations array. This
    # flag is what the UI uses to highlight "retrieved but never cited"
    # chunks - the visible wedge moment in the dashboard.
    was_cited: bool


class RetrievalDetail(_Strict):
    retrieval_id: UUID
    query: str
    embedding_model: str
    top_k: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    chunks: list[ChunkDetail]


class CitationDetail(_Strict):
    citation_id: UUID
    chunk_id: UUID
    response_span_start: int = Field(ge=0)
    response_span_end: int = Field(ge=0)


class TraceDetailResponse(_Strict):
    trace: TraceMeta
    retrievals: list[RetrievalDetail]
    citations: list[CitationDetail]
