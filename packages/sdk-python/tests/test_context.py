"""Tests for the ``current_trace_id`` ContextVar.

Two properties matter: ``ContextVar`` values do not leak across
sibling ``asyncio`` tasks, and do not leak across threads. If either
property breaks, two concurrent OpenAI calls would clobber each
other's trace.
"""

from __future__ import annotations

import asyncio
import threading
from uuid import UUID, uuid4

from retrace._context import (
    current_trace_id,
    ensure_trace_id,
    get_current_trace_id,
)


def test_ensure_trace_id_generates_when_unset() -> None:
    assert get_current_trace_id() is None
    tid = ensure_trace_id()
    assert isinstance(tid, UUID)
    assert get_current_trace_id() == tid


def test_ensure_trace_id_returns_existing() -> None:
    seeded = uuid4()
    current_trace_id.set(seeded)
    tid = ensure_trace_id()
    assert tid == seeded


async def test_contextvar_isolation_across_asyncio_tasks() -> None:
    """Two sibling tasks each set their own trace_id; neither sees the other's."""

    async def child(seed: UUID, ready: asyncio.Event, hold: asyncio.Event) -> UUID:
        current_trace_id.set(seed)
        ready.set()
        await hold.wait()
        observed = get_current_trace_id()
        assert observed is not None
        return observed

    a_id, b_id = uuid4(), uuid4()
    a_ready, b_ready = asyncio.Event(), asyncio.Event()
    release = asyncio.Event()

    task_a = asyncio.create_task(child(a_id, a_ready, release))
    task_b = asyncio.create_task(child(b_id, b_ready, release))

    await a_ready.wait()
    await b_ready.wait()
    release.set()

    a_observed, b_observed = await asyncio.gather(task_a, task_b)
    assert a_observed == a_id
    assert b_observed == b_id


def test_contextvar_isolation_across_threads() -> None:
    """A value set in one thread is not visible in another."""
    observed: dict[str, UUID | None] = {}
    barrier = threading.Barrier(2)

    def worker_a() -> None:
        current_trace_id.set(uuid4())
        barrier.wait()
        observed["a"] = get_current_trace_id()

    def worker_b() -> None:
        barrier.wait()
        observed["b"] = get_current_trace_id()

    t_a = threading.Thread(target=worker_a)
    t_b = threading.Thread(target=worker_b)
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    assert observed["a"] is not None
    assert observed["b"] is None
