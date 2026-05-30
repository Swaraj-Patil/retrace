"""Tests for ``AsyncBatchSender``: size + time triggers, swap-and-send."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from retrace import _batch
from retrace._batch import AsyncBatchSender
from retrace._models import TraceEvent


class _FakeClient:
    """Records every batch handed to it. Optional gate to simulate slow sends."""

    def __init__(self) -> None:
        self.batches: list[list[dict]] = []
        self.release: asyncio.Event | None = None  # if set, sends block until set
        self.send_started = asyncio.Event()

    async def send_traces(self, payload: bytes) -> bool:
        import json

        self.send_started.set()
        if self.release is not None:
            await self.release.wait()
        data = json.loads(payload)
        self.batches.append(data["traces"])
        return True

    async def aclose(self) -> None:
        return None


def _evt() -> TraceEvent:
    now = datetime.now(UTC)
    return TraceEvent(
        trace_id=uuid4(),
        span_id=uuid4(),
        start_time=now,
        end_time=now,
        model="gpt-4",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
        status="ok",
    )


async def _wait_until(predicate, timeout: float = 2.0, step: float = 0.01) -> None:
    """Tiny helper - poll for an async condition without hammering CPU."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step)
    raise AssertionError("condition not met within timeout")


async def test_flush_triggers_on_size_threshold() -> None:
    client = _FakeClient()
    sender = AsyncBatchSender(client, batch_size=3, flush_interval=60.0)
    sender.start()
    try:
        for _ in range(3):
            await sender.enqueue(_evt())
        await _wait_until(lambda: len(client.batches) == 1)
        assert len(client.batches[0]) == 3
    finally:
        await sender.shutdown()


async def test_flush_triggers_on_interval() -> None:
    client = _FakeClient()
    sender = AsyncBatchSender(client, batch_size=1000, flush_interval=0.05)
    sender.start()
    try:
        await sender.enqueue(_evt())
        await _wait_until(lambda: len(client.batches) == 1, timeout=2.0)
        assert len(client.batches[0]) == 1
    finally:
        await sender.shutdown()


async def test_swap_and_send_lets_new_events_accumulate() -> None:
    """While a batch is being sent, new events must land in the next batch,
    not block on the in-flight send."""
    client = _FakeClient()
    client.release = asyncio.Event()  # gate the send
    sender = AsyncBatchSender(client, batch_size=2, flush_interval=60.0)
    sender.start()
    try:
        # First batch of 2: triggers flush; send_traces blocks on `release`.
        await sender.enqueue(_evt())
        await sender.enqueue(_evt())
        await client.send_started.wait()

        # Send is in flight. Enqueue 2 more; they must NOT block.
        await asyncio.wait_for(sender.enqueue(_evt()), timeout=0.5)
        await asyncio.wait_for(sender.enqueue(_evt()), timeout=0.5)

        # Let the first send finish; the next flush picks up the second batch.
        client.release.set()
        await _wait_until(lambda: len(client.batches) == 2, timeout=2.0)
        assert len(client.batches[0]) == 2
        assert len(client.batches[1]) == 2
    finally:
        client.release.set()
        await sender.shutdown()


async def test_buffer_drops_oldest_at_hard_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """At MAX_BUFFER_SIZE the oldest entries are evicted, not the newest."""
    monkeypatch.setattr(_batch, "MAX_BUFFER_SIZE", 5)

    client = _FakeClient()
    # batch_size > MAX so we don't auto-flush; flush manually to inspect.
    sender = AsyncBatchSender(client, batch_size=999, flush_interval=60.0)
    # Do not start the background task - we want to control flushing.
    events = [_evt() for _ in range(8)]
    for e in events:
        await sender.enqueue(e)
    await sender.flush()
    sent_ids = [t["trace_id"] for t in client.batches[0]]
    expected_ids = [str(e.trace_id) for e in events[-5:]]
    assert sent_ids == expected_ids


async def test_shutdown_drains_remaining_events() -> None:
    client = _FakeClient()
    sender = AsyncBatchSender(client, batch_size=999, flush_interval=60.0)
    sender.start()
    try:
        await sender.enqueue(_evt())
        await sender.enqueue(_evt())
    finally:
        await sender.shutdown()
    # shutdown calls _flush_once after cancelling the task.
    assert sum(len(b) for b in client.batches) == 2


async def test_empty_flush_does_not_call_client() -> None:
    client = _FakeClient()
    sender = AsyncBatchSender(client, batch_size=10, flush_interval=60.0)
    await sender.flush()
    assert client.batches == []
