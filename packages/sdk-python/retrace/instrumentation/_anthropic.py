"""Monkey-patch ``anthropic.resources.messages.Messages.create``.

Parallel to ``instrumentation/_openai.py``. Same constraints:
- ``anthropic`` is **lazy-imported** inside ``install()`` only.
- Patching is **idempotent**; a sentinel attribute on the wrapper
  detects an already-patched class.
- The wrapper **never** raises into user code. The user's
  ``messages.create()`` call must complete or fail exactly as if
  Retrace were not there.
- Message contents and the system prompt body are **never** captured.
  Only request configuration parameters (plus a derived
  ``has_system_prompt`` boolean) land in ``attributes``.

Field mapping to ``TraceEvent`` (note Anthropic uses different
``usage`` field names than OpenAI):
  tokens_in  <- response.usage.input_tokens
  tokens_out <- response.usage.output_tokens
"""

from __future__ import annotations

import functools
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from retrace._context import ensure_trace_id
from retrace._logging import get_logger
from retrace._models import TraceEvent

_log = get_logger()

_PATCHED_FLAG = "_retrace_patched"

_original_create: Any = None
_target_cls: Any = None

# Request kwargs we copy into ``attributes`` when present. Anthropic-
# specific names (``stop_sequences``, ``top_k``) vs OpenAI's. Like
# OpenAI's whitelist, never includes ``messages`` or ``system``.
_REQUEST_ATTR_KEYS: tuple[str, ...] = (
    "max_tokens",
    "temperature",
    "top_p",
    "top_k",
    "stop_sequences",
    "stream",
    "metadata",
)
_ALLOWED_ATTR_VALUE_TYPES = (str, int, float, bool, list, dict)


def install() -> None:
    """Idempotently patch Anthropic's sync ``messages.create``.

    Silent no-op if ``anthropic`` isn't installed.
    """
    global _original_create, _target_cls

    if _target_cls is not None and getattr(_target_cls.create, _PATCHED_FLAG, False):
        return

    try:
        from anthropic.resources.messages import Messages
    except ImportError:
        _log.debug("retrace: anthropic not installed; skipping instrumentation")
        return
    except Exception:
        _log.warning(
            "retrace: error importing anthropic for instrumentation", exc_info=True
        )
        return

    original = Messages.create
    if getattr(original, _PATCHED_FLAG, False):
        _target_cls = Messages
        return

    Messages.create = _wrap(original)
    _original_create = original
    _target_cls = Messages


def uninstall() -> None:
    global _original_create, _target_cls
    if _target_cls is None or _original_create is None:
        return
    _target_cls.create = _original_create
    _original_create = None
    _target_cls = None


def _wrap(original: Any) -> Any:
    @functools.wraps(original)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            trace_id = ensure_trace_id()
            span_id = uuid4()
            start_dt = datetime.now(UTC)
            start_perf = time.monotonic()
            request_model = kwargs.get("model")
            attributes = _build_attributes(kwargs)
        except Exception:
            _log.warning(
                "retrace: error preparing trace; calling anthropic unwrapped",
                exc_info=True,
            )
            return original(self, *args, **kwargs)

        try:
            response = original(self, *args, **kwargs)
        except Exception:
            try:
                _safe_record_error(
                    trace_id, span_id, start_dt, start_perf, request_model, attributes
                )
            except Exception:
                _log.warning("retrace: error in error-recording path", exc_info=True)
            raise

        try:
            _safe_record_success(
                trace_id,
                span_id,
                start_dt,
                start_perf,
                request_model,
                attributes,
                response,
            )
        except Exception:
            _log.warning("retrace: error in success-recording path", exc_info=True)
        return response

    setattr(wrapper, _PATCHED_FLAG, True)
    return wrapper


def _safe_record_success(
    trace_id: UUID,
    span_id: UUID,
    start_dt: datetime,
    start_perf: float,
    request_model: Any,
    attributes: dict[str, Any],
    response: Any,
) -> None:
    try:
        end_dt = datetime.now(UTC)
        latency_ms = max(0, int((time.monotonic() - start_perf) * 1000))
        usage = getattr(response, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        model = getattr(response, "model", None) or request_model or "unknown"
        event = TraceEvent(
            trace_id=trace_id,
            span_id=span_id,
            start_time=start_dt,
            end_time=end_dt,
            model=str(model),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            status="ok",
            attributes=attributes,
        )
        _enqueue(event)
    except Exception:
        _log.warning("retrace: failed to record success event", exc_info=True)


def _safe_record_error(
    trace_id: UUID,
    span_id: UUID,
    start_dt: datetime,
    start_perf: float,
    request_model: Any,
    attributes: dict[str, Any],
) -> None:
    try:
        end_dt = datetime.now(UTC)
        latency_ms = max(0, int((time.monotonic() - start_perf) * 1000))
        event = TraceEvent(
            trace_id=trace_id,
            span_id=span_id,
            start_time=start_dt,
            end_time=end_dt,
            model=str(request_model or "unknown"),
            tokens_in=0,
            tokens_out=0,
            latency_ms=latency_ms,
            status="error",
            attributes=attributes,
        )
        _enqueue(event)
    except Exception:
        _log.warning("retrace: failed to record error event", exc_info=True)


def _enqueue(event: TraceEvent) -> None:
    import retrace

    retrace._enqueue_event(event)


def _build_attributes(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Whitelist-only config capture. No message contents, no system body."""
    attrs: dict[str, Any] = {}
    messages = kwargs.get("messages")
    if isinstance(messages, list):
        attrs["messages_count"] = len(messages)
    # Anthropic separates the system prompt from ``messages`` as a top-
    # level kwarg. Record only its presence, never its content.
    system = kwargs.get("system")
    attrs["has_system_prompt"] = bool(system)
    for key in _REQUEST_ATTR_KEYS:
        if key not in kwargs:
            continue
        value = kwargs[key]
        if value is None:
            continue
        if isinstance(value, _ALLOWED_ATTR_VALUE_TYPES):
            attrs[key] = value
    return attrs


__all__ = ["install", "uninstall"]
