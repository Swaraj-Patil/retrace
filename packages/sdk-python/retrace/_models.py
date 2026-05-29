"""Buffered event shape and JSON serialization.

``TraceEvent`` mirrors ``api.schemas.ingest.TraceIn`` field-for-field so
the SDK's wire payload is just ``{"traces": [asdict(event), ...]}`` -
no pydantic on the SDK buffer side.
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


def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def event_to_dict(event: TraceEvent) -> dict[str, Any]:
    return asdict(event)


def serialize_payload(events: list[TraceEvent]) -> bytes:
    """Build the JSON body for ``POST /v1/ingest`` from a batch of trace events."""
    payload = {"traces": [event_to_dict(e) for e in events]}
    return json.dumps(payload, default=_json_default).encode("utf-8")


__all__ = ["TraceEvent", "event_to_dict", "serialize_payload"]
