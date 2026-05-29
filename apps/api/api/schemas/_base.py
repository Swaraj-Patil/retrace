"""Shared Pydantic base for request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    """Reject unknown fields. Apply everywhere a client controls the body
    (so they can't smuggle project_id or other surprises) and everywhere
    the response shape is part of the public contract (so accidentally
    added fields fail loudly in tests)."""

    model_config = ConfigDict(extra="forbid")
