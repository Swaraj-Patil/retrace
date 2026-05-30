"""Monkey-patch ``openai.resources.chat.completions.Completions.create``.

Constraints (per Day 4 spec):
- The ``openai`` import is **lazy**, inside ``install()`` only, so the
  SDK is installable and usable without openai present.
- Patching is **idempotent**: calling ``install()`` again is a no-op.
  Detection uses a sentinel attribute on the wrapper.
- The wrapper **never** raises into user code. The user's ``create()``
  call must complete or fail exactly as if Retrace were not there.
- Message contents are **never** captured. Only request configuration
  parameters land in ``attributes``. PII opt-in comes later.
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

# Request kwargs we will copy into ``attributes`` if present. Anything
# not on this list (``messages`` in particular) is dropped on the floor.
_REQUEST_ATTR_KEYS: tuple[str, ...] = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "n",
    "stop",
    "stream",
    "user",
    "response_format",
    "tool_choice",
    "seed",
    "logprobs",
    "top_logprobs",
)
_ALLOWED_ATTR_VALUE_TYPES = (str, int, float, bool, list, dict)


def install() -> None:
    """Idempotently patch the sync chat.completions create method.

    Silently no-ops if ``openai`` is not installed - users who don't
    use openai shouldn't see warnings.
    """
    global _original_create, _target_cls

    if _target_cls is not None and getattr(
        _target_cls.create, _PATCHED_FLAG, False
    ):
        return

    try:
        from openai.resources.chat.completions import Completions
    except ImportError:
        _log.debug("retrace: openai not installed; skipping instrumentation")
        return
    except Exception:
        _log.warning(
            "retrace: error importing openai for instrumentation", exc_info=True
        )
        return

    original = Completions.create
    if getattr(original, _PATCHED_FLAG, False):
        # Already wrapped (e.g. another import path). Just record state.
        _target_cls = Completions
        return

    Completions.create = _wrap(original)
    _original_create = original
    _target_cls = Completions


def uninstall() -> None:
    """Restore the original method. Used by tests and clean shutdown."""
    global _original_create, _target_cls
    if _target_cls is None or _original_create is None:
        return
    _target_cls.create = _original_create
    _original_create = None
    _target_cls = None


def _wrap(original: Any) -> Any:
    @functools.wraps(original)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Prep. If anything in here blows up, fall through unwrapped -
        # we'd rather lose the trace than break the user's call.
        try:
            trace_id = ensure_trace_id()
            span_id = uuid4()
            start_dt = datetime.now(UTC)
            start_perf = time.monotonic()
            request_model = kwargs.get("model")
            attributes = _build_attributes(kwargs)
        except Exception:
            _log.warning(
                "retrace: error preparing trace; calling openai unwrapped",
                exc_info=True,
            )
            return original(self, *args, **kwargs)

        try:
            response = original(self, *args, **kwargs)
        except Exception:
            # Belt-and-suspenders: even if _safe_record_error itself blew up
            # (it shouldn't), do not interfere with the user's exception.
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
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
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
    # Lazy import to keep the dependency direction clean
    # (instrumentation imports the package's public enqueue helper).
    import retrace

    retrace._enqueue_event(event)


def _build_attributes(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Extract a small, JSON-safe dict of request config. No message content."""
    attrs: dict[str, Any] = {}
    messages = kwargs.get("messages")
    if isinstance(messages, list):
        attrs["messages_count"] = len(messages)
    tools = kwargs.get("tools")
    if isinstance(tools, list):
        attrs["tools_count"] = len(tools)
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
