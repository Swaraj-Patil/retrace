"""SDK configuration and module-level state.

``init()`` builds an ``SdkConfig`` and stores it here. A second call to
``init()`` replaces the config in place - it does not spawn a second
background runtime (the runtime is started exactly once by ``init()``
in ``retrace/__init__.py``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

_DEFAULT_ENDPOINT = "http://localhost:8000"
_ENDPOINT_ENV_VAR = "RETRACE_ENDPOINT"
_API_KEY_PREFIX = "rt_"


@dataclass(frozen=True)
class SdkConfig:
    api_key: str
    endpoint: str
    batch_size: int
    flush_interval: float
    enabled: bool


_config: SdkConfig | None = None


def build_config(
    *,
    api_key: str,
    endpoint: str | None = None,
    batch_size: int = 100,
    flush_interval: float = 5.0,
    enabled: bool = True,
) -> SdkConfig:
    """Validate inputs and return an ``SdkConfig``. Raises ``ValueError`` on bad input.

    This is the only code path that raises from public-facing SDK code -
    it runs at ``init()`` time, before any user-call instrumentation, so
    misconfiguration is surfaced loudly rather than silently swallowed.
    """
    if not isinstance(api_key, str) or not api_key.startswith(_API_KEY_PREFIX):
        raise ValueError(f"api_key must be a string starting with {_API_KEY_PREFIX!r}")

    if endpoint is None:
        endpoint = os.environ.get(_ENDPOINT_ENV_VAR, _DEFAULT_ENDPOINT)
    if not endpoint:
        raise ValueError("endpoint must be a non-empty string")
    endpoint = endpoint.rstrip("/")

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if flush_interval <= 0:
        raise ValueError("flush_interval must be positive")

    return SdkConfig(
        api_key=api_key,
        endpoint=endpoint,
        batch_size=batch_size,
        flush_interval=flush_interval,
        enabled=bool(enabled),
    )


def set_config(cfg: SdkConfig) -> None:
    global _config
    _config = cfg


def get_config() -> SdkConfig | None:
    return _config


def is_initialized() -> bool:
    return _config is not None


def reset_for_tests() -> None:
    """Clear module-level config. Tests only."""
    global _config
    _config = None


__all__ = [
    "SdkConfig",
    "build_config",
    "get_config",
    "is_initialized",
    "replace",
    "reset_for_tests",
    "set_config",
]
