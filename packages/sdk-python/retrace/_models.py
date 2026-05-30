"""Buffered event shapes and JSON serialization.

Each ``*Event`` dataclass mirrors a corresponding ``*In`` schema in
``api.schemas.ingest`` field-for-field. The buffer holds a mixed list
of the four types; ``serialize_payload`` dispatches each into the
matching array of the ``IngestRequest`` envelope.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class TraceEvent:
    trace_id: UUID
    span_id: UUID
    start_time: datetime
    end_time: datetime
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    status: str
    parent_span_id: UUID | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalEvent:
    retrieval_id: UUID
    trace_id: UUID
    span_id: UUID
    query: str
    embedding_model: str
    top_k: int
    latency_ms: int
    timestamp: datetime


@dataclass(frozen=True)
class ChunkEvent:
    chunk_id: UUID
    retrieval_id: UUID
    rank: int
    similarity_score: float
    content: str
    source_doc_id: str
    timestamp: datetime
    doc_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CitationEvent:
    citation_id: UUID
    trace_id: UUID
    chunk_id: UUID
    response_span_start: int
    response_span_end: int
    timestamp: datetime


AnyEvent = TraceEvent | RetrievalEvent | ChunkEvent | CitationEvent


def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def event_to_dict(event: AnyEvent) -> dict[str, Any]:
    return asdict(event)


def serialize_payload(events: list[AnyEvent]) -> bytes:
    """Bucket events by type into the four arrays of ``IngestRequest`` and
    return the JSON body for ``POST /v1/ingest``."""
    payload: dict[str, list[dict[str, Any]]] = {
        "traces": [],
        "retrievals": [],
        "chunks": [],
        "citations": [],
    }
    for e in events:
        if isinstance(e, TraceEvent):
            payload["traces"].append(event_to_dict(e))
        elif isinstance(e, RetrievalEvent):
            payload["retrievals"].append(event_to_dict(e))
        elif isinstance(e, ChunkEvent):
            payload["chunks"].append(event_to_dict(e))
        elif isinstance(e, CitationEvent):
            payload["citations"].append(event_to_dict(e))
    return json.dumps(payload, default=_json_default).encode("utf-8")


__all__ = [
    "AnyEvent",
    "ChunkEvent",
    "CitationEvent",
    "RetrievalEvent",
    "TraceEvent",
    "event_to_dict",
    "serialize_payload",
]
