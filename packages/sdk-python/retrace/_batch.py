"""In-memory event buffer with an async background flusher.

Lifecycle:
- ``enqueue(event)``     append under lock; if size threshold hit, signal the loop.
- ``_run()``             wakes on ``size_trigger`` *or* ``flush_interval`` timeout.
- ``_flush_once()``      **swap-and-send**: take the buffer under lock, replace it
                         with a fresh list, release the lock, then send the
                         snapshot. New events keep accumulating during the
                         network call without blocking ``enqueue``.

Hard ceiling: at most ``MAX_BUFFER_SIZE`` events. Past that, oldest are
dropped with a warning. Drops are *silent to user code* by design.
"""

from __future__ import annotations

import asyncio

from retrace._client import HttpClient
from retrace._logging import get_logger
from retrace._models import AnyEvent, serialize_payload

_log = get_logger()

MAX_BUFFER_SIZE = 10_000


class AsyncBatchSender:
    def __init__(
        self,
        client: HttpClient,
        *,
        batch_size: int,
        flush_interval: float,
    ) -> None:
        self._client = client
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer: list[AnyEvent] = []
        self._lock = asyncio.Lock()
        self._size_trigger = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._shutting_down = False

    def start(self) -> None:
        """Spawn the background flusher task on the running loop. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._shutting_down = False
        self._task = asyncio.create_task(self._run(), name="retrace-flusher")

    async def enqueue(self, event: AnyEvent) -> None:
        signal = False
        async with self._lock:
            self._buffer.append(event)
            overflow = len(self._buffer) - MAX_BUFFER_SIZE
            if overflow > 0:
                del self._buffer[:overflow]
                _log.warning(
                    "retrace: buffer overflow, dropped %d oldest event(s)", overflow
                )
            if len(self._buffer) >= self._batch_size:
                signal = True
        if signal:
            self._size_trigger.set()

    async def flush(self) -> None:
        """Force an immediate flush (waits for it to complete)."""
        await self._flush_once()

    async def shutdown(self) -> None:
        """Stop the background task, drain remaining events, close the client."""
        self._shutting_down = True
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                _log.warning("retrace: flusher task raised during shutdown", exc_info=True)
        # Final drain - the cancellation may have left events behind.
        try:
            await self._flush_once()
        except Exception:
            _log.warning("retrace: error draining buffer on shutdown", exc_info=True)
        await self._client.aclose()

    async def _run(self) -> None:
        """Wake on size signal or interval timeout; flush; repeat."""
        while not self._shutting_down:
            try:
                try:
                    await asyncio.wait_for(
                        self._size_trigger.wait(), timeout=self._flush_interval
                    )
                except asyncio.TimeoutError:
                    pass
                # Clear before flushing so events arriving during the send
                # cleanly re-arm the trigger for the next round.
                self._size_trigger.clear()
                await self._flush_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.warning("retrace: error in flush loop", exc_info=True)

    async def _flush_once(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            snapshot = self._buffer
            self._buffer = []
        try:
            payload = serialize_payload(snapshot)
        except Exception:
            _log.warning(
                "retrace: failed to serialize batch of %d event(s); dropped",
                len(snapshot),
                exc_info=True,
            )
            return
        try:
            await self._client.send_traces(payload)
        except Exception:
            # send_traces is supposed to swallow everything; belt-and-suspenders.
            _log.warning("retrace: unexpected error sending batch", exc_info=True)


__all__ = ["AsyncBatchSender", "MAX_BUFFER_SIZE"]
