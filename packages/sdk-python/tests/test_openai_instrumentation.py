"""Tests for the OpenAI sync ``chat.completions.create`` monkey-patch.

We don't depend on the real ``openai`` package - the SDK must be
testable without it. Tests inject a fake module structure into
``sys.modules`` that mirrors the path the patcher imports from.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

import retrace
from retrace._models import TraceEvent
from retrace.instrumentation import _openai


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> Iterator[type]:
    """Stand in for ``openai.resources.chat.completions.Completions``.

    The test instantiates ``FakeCompletions`` and calls ``create`` on it
    after the SDK has patched the class.
    """

    class FakeCompletions:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            return MagicMock(
                model=kwargs.get("model"),
                usage=MagicMock(prompt_tokens=11, completion_tokens=22),
            )

    fake_root = types.ModuleType("openai")
    fake_resources = types.ModuleType("openai.resources")
    fake_chat = types.ModuleType("openai.resources.chat")
    fake_completions_mod = types.ModuleType("openai.resources.chat.completions")
    fake_completions_mod.Completions = FakeCompletions  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "openai", fake_root)
    monkeypatch.setitem(sys.modules, "openai.resources", fake_resources)
    monkeypatch.setitem(sys.modules, "openai.resources.chat", fake_chat)
    monkeypatch.setitem(
        sys.modules, "openai.resources.chat.completions", fake_completions_mod
    )

    yield FakeCompletions

    # Clean module-level patch state regardless of how the test exited;
    # the fake module is about to vanish from sys.modules.
    _openai.uninstall()


@pytest.fixture
def captured_events(monkeypatch: pytest.MonkeyPatch) -> list[TraceEvent]:
    """Bypass the runtime/sender. Capture events into a list."""
    events: list[TraceEvent] = []
    monkeypatch.setattr(retrace, "_enqueue_event", events.append)
    return events


def test_install_is_idempotent(fake_openai: type) -> None:
    _openai.install()
    patched_once = fake_openai.create
    _openai.install()
    patched_twice = fake_openai.create
    assert patched_once is patched_twice
    assert getattr(fake_openai.create, "_retrace_patched", False) is True


def test_wrapper_captures_success_event(
    fake_openai: type, captured_events: list[TraceEvent]
) -> None:
    _openai.install()
    client = fake_openai()
    response = client.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        top_p=0.95,
    )

    assert response.model == "gpt-4"
    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.status == "ok"
    assert event.model == "gpt-4"
    assert event.tokens_in == 11
    assert event.tokens_out == 22
    assert event.latency_ms >= 0
    assert event.attributes == {
        "messages_count": 1,
        "temperature": 0.7,
        "top_p": 0.95,
    }


def test_attributes_never_include_message_contents(
    fake_openai: type, captured_events: list[TraceEvent]
) -> None:
    _openai.install()
    client = fake_openai()
    secret = "this is a private message and must never be captured"
    client.create(
        model="gpt-4",
        messages=[{"role": "user", "content": secret}],
        temperature=0.1,
    )

    event = captured_events[0]
    assert "messages" not in event.attributes
    # Belt-and-suspenders: scan the whole attrs dict for the secret.
    rendered = repr(event.attributes)
    assert secret not in rendered


def test_wrapper_records_error_event_and_reraises(
    fake_openai: type, captured_events: list[TraceEvent]
) -> None:
    _openai.install()

    class BoomError(RuntimeError):
        pass

    def boom(self: Any, **kwargs: Any) -> Any:
        raise BoomError("upstream is down")

    # Replace the patched method's underlying behavior by re-patching
    # the class with a method that raises. The wrapper sits on top.
    fake_openai.create = _openai._wrap(boom)

    with pytest.raises(BoomError, match="upstream is down"):
        fake_openai().create(model="gpt-4", messages=[{"role": "user", "content": "x"}])

    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.status == "error"
    assert event.model == "gpt-4"
    assert event.tokens_in == 0
    assert event.tokens_out == 0


def test_sdk_side_error_does_not_break_user_call(
    fake_openai: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If our recording code blows up, the user still gets their response."""
    _openai.install()

    def boom_record(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("retrace bug")

    monkeypatch.setattr(_openai, "_safe_record_success", boom_record)
    monkeypatch.setattr(_openai, "_safe_record_error", boom_record)

    client = fake_openai()
    # _safe_record_* swallow their own exceptions, but be defensive:
    # even if the wrapper layer itself misbehaved, the user must still
    # receive their response.
    response = client.create(model="gpt-4", messages=[{"role": "user", "content": "x"}])
    assert response.model == "gpt-4"


def test_uninstall_restores_original(fake_openai: type) -> None:
    pre = fake_openai.create
    assert not getattr(pre, "_retrace_patched", False)

    _openai.install()
    assert getattr(fake_openai.create, "_retrace_patched", False) is True

    _openai.uninstall()
    assert fake_openai.create is pre
    assert not getattr(fake_openai.create, "_retrace_patched", False)


def test_install_silent_no_op_when_openai_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``openai`` isn't installed, ``install()`` does nothing and doesn't raise."""
    # Make sure no leftover fake is in sys.modules.
    for name in (
        "openai",
        "openai.resources",
        "openai.resources.chat",
        "openai.resources.chat.completions",
    ):
        monkeypatch.delitem(sys.modules, name, raising=False)
    _openai.install()
    assert _openai._target_cls is None
    assert _openai._original_create is None


def test_attributes_skip_non_jsonable_values(
    fake_openai: type, captured_events: list[TraceEvent]
) -> None:
    """Non-scalar/non-container values are dropped silently."""
    _openai.install()

    class Custom:
        pass

    fake_openai().create(
        model="gpt-4",
        messages=[],
        temperature=0.2,
        response_format=Custom(),  # not on the allowed-types list
    )

    event = captured_events[0]
    assert event.attributes == {"messages_count": 0, "temperature": 0.2}


def test_wrapper_generates_fresh_trace_id_when_unset(
    fake_openai: type, captured_events: list[TraceEvent]
) -> None:
    from retrace._context import current_trace_id

    assert current_trace_id.get() is None
    _openai.install()
    fake_openai().create(model="gpt-4", messages=[])
    fake_openai().create(model="gpt-4", messages=[])

    assert len(captured_events) == 2
    # Calls inside the same context share the trace_id (ensure_trace_id sets it).
    # Across separate contexts, they'd differ - but pytest gives one context per test.
    assert captured_events[0].trace_id == captured_events[1].trace_id
    assert captured_events[0].span_id != captured_events[1].span_id
