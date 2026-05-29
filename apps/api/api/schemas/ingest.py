"""Request and response schemas for ``POST /v1/ingest``.

Every input model uses ``extra="forbid"`` so the boundary is tight: a
client cannot smuggle a ``project_id`` (or any other unknown field)
into a row. The project is always derived from the authenticated API
key on the server side.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TraceIn(_Strict):
    trace_id: UUID
    span_id: UUID
    parent_span_id: UUID | None = None
    start_time: datetime
    end_time: datetime
    model: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    status: str
    attributes: dict[str, object] = Field(default_factory=dict)


class RetrievalIn(_Strict):
    retrieval_id: UUID
    trace_id: UUID
    span_id: UUID
    query: str
    embedding_model: str
    top_k: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    timestamp: datetime


class RetrievedChunkIn(_Strict):
    chunk_id: UUID
    retrieval_id: UUID
    rank: int = Field(ge=0)
    similarity_score: float = Field(ge=0.0, le=1.0)
    content: str
    source_doc_id: str
    doc_metadata: dict[str, object] = Field(default_factory=dict)
    timestamp: datetime


class CitationIn(_Strict):
    citation_id: UUID
    trace_id: UUID
    chunk_id: UUID
    response_span_start: int = Field(ge=0)
    response_span_end: int = Field(ge=0)
    timestamp: datetime


class IngestRequest(_Strict):
    traces: list[TraceIn] = Field(default_factory=list)
    retrievals: list[RetrievalIn] = Field(default_factory=list)
    chunks: list[RetrievedChunkIn] = Field(default_factory=list)
    citations: list[CitationIn] = Field(default_factory=list)


class InsertedCounts(_Strict):
    traces: int
    retrievals: int
    chunks: int
    citations: int


class IngestResponse(_Strict):
    inserted: InsertedCounts
    project_id: UUID
