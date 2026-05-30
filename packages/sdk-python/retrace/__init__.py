"""Retrace Python SDK - public surface.

``init()`` wires up config, the background runtime, an HTTP client,
the async batch sender, and (if ``openai`` is importable) the sync
``chat.completions.create`` monkey-patch. ``flush()`` forces an
immediate send; ``shutdown()`` drains and tears down.

``_configure_for_testing(transport=...)`` is the seam used by the
integration test (commit 4) to drive the SDK against an in-process
FastAPI app via ``httpx.ASGITransport``. It must be called *before*
``init()`` so the active client picks the transport up.
"""

from __future__ import annotations

import atexit
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError

import httpx

from retrace._batch import AsyncBatchSender
from retrace._client import HttpClient
from retrace._config import (
    SdkConfig,
    build_config,
    get_config,
    is_initialized,
    set_config,
)
from retrace._logging import get_logger
from retrace._models import AnyEvent
from retrace._rag import (
    log_chunk,
    log_chunks,
    log_citation,
    retrieval,
    trace,
    trace_retrieval,
)
from retrace._runtime import get_runtime
from retrace.instrumentation import _anthropic as _anthropic_instr
from retrace.instrumentation import _openai as _openai_instr

__version__ = "0.0.1"

_log = get_logger()
_init_lock = threading.Lock()
_atexit_registered = False

_sender: AsyncBatchSender | None = None
_test_transport: httpx.AsyncBaseTransport | None = None


def init(
    *,
    api_key: str,
    endpoint: str | None = None,
    batch_size: int = 100,
    flush_interval: float = 5.0,
    enabled: bool = True,
) -> SdkConfig:
    """Configure the SDK. Idempotent.

    A second call replaces the stored config but does not spawn a
    second runtime task. The existing batch sender (if any) is left
    running with its original batch_size/flush_interval; tear down via
    ``shutdown()`` first if you need to reconfigure those.
    """
    global _atexit_registered, _sender
    cfg = build_config(
        api_key=api_key,
        endpoint=endpoint,
        batch_size=batch_size,
        flush_interval=flush_interval,
        enabled=enabled,
    )
    with _init_lock:
        set_config(cfg)
        if cfg.enabled and _sender is None:
            runtime = get_runtime()
            runtime.start()
            future = runtime.submit(_build_and_start_sender(cfg))
            try:
                _sender = future.result(timeout=10.0)
            except FuturesTimeoutError:
                _log.warning("retrace: batch sender failed to start within 10s")
                _sender = None
            except Exception:
                _log.warning("retrace: error starting batch sender", exc_info=True)
                _sender = None
        if cfg.enabled:
            # Idempotent; each is a silent no-op if its SDK isn't installed.
            try:
                _openai_instr.install()
            except Exception:
                _log.warning("retrace: openai instrumentation failed", exc_info=True)
            try:
                _anthropic_instr.install()
            except Exception:
                _log.warning("retrace: anthropic instrumentation failed", exc_info=True)
        if not _atexit_registered:
            atexit.register(_atexit_shutdown)
            _atexit_registered = True
    return cfg


def _enqueue_event(event: AnyEvent) -> None:
    """Submit any event (trace/retrieval/chunk/citation) to the background sender.

    Non-blocking. Called from sync user-code paths (auto-instrumentation
    wrappers, manual RAG helpers). Fails silently: if the SDK isn't
    initialized or the runtime isn't up, drop the event.
    """
    sender = _sender
    if sender is None:
        return
    runtime = get_runtime()
    if not runtime.is_running():
        return
    try:
        runtime.submit(sender.enqueue(event))
    except Exception:
        _log.warning("retrace: failed to submit event", exc_info=True)


async def _build_and_start_sender(cfg: SdkConfig) -> AsyncBatchSender:
    client = HttpClient(cfg.endpoint, cfg.api_key, transport=_test_transport)
    sender = AsyncBatchSender(
        client, batch_size=cfg.batch_size, flush_interval=cfg.flush_interval
    )
    sender.start()
    return sender


def flush(timeout: float = 30.0) -> None:
    """Force a flush of the in-memory buffer and wait for it to complete.

    Raises ``TimeoutError`` if the flush does not finish within
    ``timeout`` seconds. This is the *one* SDK function that may raise:
    callers asking for synchronous completion deserve to know if it
    didn't happen.
    """
    sender = _sender
    if sender is None:
        return
    runtime = get_runtime()
    if not runtime.is_running():
        return
    future = runtime.submit(sender.flush())
    try:
        future.result(timeout=timeout)
    except FuturesTimeoutError as exc:
        raise TimeoutError(f"retrace flush did not complete within {timeout}s") from exc


def shutdown() -> None:
    """Flush remaining events, stop the runtime, and undo openai patching."""
    global _sender
    sender = _sender
    runtime = get_runtime()
    if sender is not None and runtime.is_running():
        try:
            future = runtime.submit(sender.shutdown())
            future.result(timeout=10.0)
        except Exception:
            _log.warning("retrace: error during shutdown", exc_info=True)
    _sender = None
    runtime.stop()
    try:
        _openai_instr.uninstall()
    except Exception:
        _log.warning("retrace: error uninstalling openai patch", exc_info=True)
    try:
        _anthropic_instr.uninstall()
    except Exception:
        _log.warning("retrace: error uninstalling anthropic patch", exc_info=True)


def _atexit_shutdown() -> None:
    try:
        shutdown()
    except Exception:
        _log.warning("retrace: error during atexit shutdown", exc_info=True)


def _configure_for_testing(*, transport: httpx.AsyncBaseTransport | None) -> None:
    """Test seam. Call before ``init()`` to inject an httpx transport.

    Pass ``transport=None`` to clear it. Not part of the public API.
    """
    global _test_transport
    _test_transport = transport


def _reset_for_tests() -> None:
    """Tear down all module-level state. Tests only.

    Mirrors what an explicit ``shutdown()`` does so the background
    sender task and its HTTP client are properly drained; otherwise
    pytest's loop closes underneath them and asyncio yells about
    "Task was destroyed but it is pending."
    """
    global _sender, _test_transport
    shutdown()
    _sender = None
    _test_transport = None


__all__ = [
    "SdkConfig",
    "__version__",
    "flush",
    "get_config",
    "init",
    "log_chunk",
    "log_chunks",
    "log_citation",
    "retrieval",
    "shutdown",
    "trace",
    "trace_retrieval",
]
