"""Background asyncio loop running in a daemon thread.

The SDK runs an event loop off the main thread so the buffer + flusher
work regardless of whether the user's code is sync or async. Sync user
code calls into the runtime via ``submit()``, which is just
``asyncio.run_coroutine_threadsafe`` returning a
``concurrent.futures.Future``.

Lifecycle:
- ``Runtime.start()`` creates a loop and a daemon thread that runs it.
  Safe to call repeatedly; second call is a no-op.
- ``Runtime.stop()`` cancels every pending task on the loop, runs them
  to completion (so cleanup like ``aclose()`` actually executes), then
  stops the loop and joins the thread.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any

from retrace._logging import get_logger

_log = get_logger()


class Runtime:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError("Runtime not started")
        return self._loop

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running():
            return
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="retrace-sdk-loop",
            daemon=True,
        )
        self._thread.start()
        # Block briefly until the loop is set so callers can submit() immediately.
        self._ready.wait(timeout=5.0)
        if not self._ready.is_set():
            raise RuntimeError("retrace runtime thread failed to start within 5s")

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.close()
            except Exception:
                _log.warning("retrace: error closing event loop", exc_info=True)

    def submit(self, coro: Coroutine[Any, Any, Any]) -> Future[Any]:
        """Schedule ``coro`` on the background loop. Returns a thread-safe Future."""
        if self._loop is None or not self._loop.is_running():
            # Caller must handle this; do not silently drop coroutines.
            raise RuntimeError("Runtime not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self, timeout: float = 5.0) -> None:
        """Cancel pending tasks, stop the loop, and join the thread."""
        if not self.is_running() or self._loop is None:
            return
        loop = self._loop
        loop.call_soon_threadsafe(self._cancel_all_tasks)
        loop.call_soon_threadsafe(loop.stop)
        assert self._thread is not None
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            _log.warning("retrace: background thread did not stop within %ss", timeout)
        self._thread = None
        self._loop = None

    def _cancel_all_tasks(self) -> None:
        assert self._loop is not None
        tasks = [t for t in asyncio.all_tasks(self._loop) if not t.done()]
        for t in tasks:
            t.cancel()


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime


def reset_for_tests() -> None:
    """Stop and discard the module-level runtime. Tests only."""
    global _runtime
    if _runtime is not None:
        _runtime.stop()
        _runtime = None


__all__ = ["Runtime", "get_runtime", "reset_for_tests"]
