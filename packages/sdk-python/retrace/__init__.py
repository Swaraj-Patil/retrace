"""Retrace Python SDK - public surface.

Today (Day 4 commit 1): ``init()`` wires up config and the background
runtime; ``shutdown()`` tears it down. ``flush()`` is a stub here and
gets a real implementation when the batch sender lands in commit 2.
"""

from __future__ import annotations

import atexit
import threading

from retrace._config import (
    SdkConfig,
    build_config,
    get_config,
    is_initialized,
    set_config,
)
from retrace._logging import get_logger
from retrace._runtime import get_runtime

__version__ = "0.0.1"

_log = get_logger()
_init_lock = threading.Lock()
_atexit_registered = False


def init(
    *,
    api_key: str,
    endpoint: str | None = None,
    batch_size: int = 100,
    flush_interval: float = 5.0,
    enabled: bool = True,
) -> SdkConfig:
    """Configure the SDK. Idempotent - safe to call more than once."""
    global _atexit_registered
    cfg = build_config(
        api_key=api_key,
        endpoint=endpoint,
        batch_size=batch_size,
        flush_interval=flush_interval,
        enabled=enabled,
    )
    with _init_lock:
        set_config(cfg)
        if cfg.enabled:
            get_runtime().start()
        if not _atexit_registered:
            atexit.register(_atexit_shutdown)
            _atexit_registered = True
    return cfg


def flush(timeout: float = 30.0) -> None:
    """Force a flush of the in-memory buffer. No-op until commit 2 wires the batch sender."""
    # Will become: submit the batch sender's flush() coroutine to the runtime
    # and wait on the resulting Future with the given timeout.
    _ = timeout


def shutdown() -> None:
    """Flush remaining events and stop the background runtime."""
    if is_initialized():
        try:
            flush()
        except Exception:
            _log.warning("retrace: error during shutdown flush", exc_info=True)
    get_runtime().stop()


def _atexit_shutdown() -> None:
    try:
        shutdown()
    except Exception:
        # atexit must not raise - swallow and log only.
        _log.warning("retrace: error during atexit shutdown", exc_info=True)


__all__ = ["SdkConfig", "__version__", "flush", "get_config", "init", "shutdown"]
