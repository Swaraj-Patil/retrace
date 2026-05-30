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
