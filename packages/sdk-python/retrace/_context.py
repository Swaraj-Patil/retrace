"""Per-call trace context.

``ContextVar`` propagates correctly across ``asyncio`` tasks and is
isolated per-thread, which is what we need: a value set inside one
``asyncio.Task`` (or one thread) does not leak into a sibling.
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID, uuid4

current_trace_id: ContextVar[UUID | None] = ContextVar("retrace_current_trace_id", default=None)


def get_current_trace_id() -> UUID | None:
    return current_trace_id.get()


def ensure_trace_id() -> UUID:
    """Return the current trace_id, generating and setting a fresh one if unset.

    Day 4: every OpenAI call without an outer scope becomes its own
    one-span trace. The manual trace API lands Day 5.
    """
    existing = current_trace_id.get()
    if existing is not None:
        return existing
    new_id = uuid4()
    current_trace_id.set(new_id)
    return new_id


__all__ = ["current_trace_id", "ensure_trace_id", "get_current_trace_id"]
