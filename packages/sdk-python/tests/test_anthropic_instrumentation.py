"""Tests for the Anthropic sync ``messages.create`` monkey-patch.

Mirrors test_openai_instrumentation.py. ``anthropic`` is faked via
sys.modules - the SDK must be testable without the real package.
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
from retrace.instrumentation import _anthropic


@pytest.fixture
def fake_anthropic(monkeypatch: pytest.MonkeyPatch) -> Iterator[type]:
    """Inject a fake ``anthropic.resources.messages.Messages`` and let the
    SDK patch it. Cleans up the module-level patch state on teardown."""

    class FakeMessages:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            return MagicMock(
                model=kwargs.get("model"),
                usage=MagicMock(input_tokens=33, output_tokens=44),
            )

    fake_root = types.ModuleType("anthropic")
    fake_resources = types.ModuleType("anthropic.resources")
    fake_messages_mod = types.ModuleType("anthropic.resources.messages")
    fake_messages_mod.Messages = FakeMessages  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "anthropic", fake_root)
    monkeypatch.setitem(sys.modules, "anthropic.resources", fake_resources)
    monkeypatch.setitem(sys.modules, "anthropic.resources.messages", fake_messages_mod)

    yield FakeMessages

    _anthropic.uninstall()


@pytest.fixture
def captured_events(monkeypatch: pytest.MonkeyPatch) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    monkeypatch.setattr(retrace, "_enqueue_event", events.append)
    return events


def test_install_is_idempotent(fake_anthropic: type) -> None:
    _anthropic.install()
    once = fake_anthropic.create
    _anthropic.install()
    twice = fake_anthropic.create
    assert once is twice
    assert getattr(fake_anthropic.create, "_retrace_patched", False) is True


def test_wrapper_captures_success_event(
    fake_anthropic: type, captured_events: list[TraceEvent]
) -> None:
    _anthropic.install()
    client = fake_anthropic()

    response = client.create(
        model="claude-3-5-sonnet-20240620",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=1024,
        temperature=0.4,
        system="You are a helpful assistant.",
    )

    assert response.model == "claude-3-5-sonnet-20240620"
    [event] = captured_events
    assert event.status == "ok"
    assert event.model == "claude-3-5-sonnet-20240620"
    assert event.tokens_in == 33
    assert event.tokens_out == 44
    assert event.latency_ms >= 0
    assert event.attributes == {
        "messages_count": 1,
        "has_system_prompt": True,
        "max_tokens": 1024,
        "temperature": 0.4,
    }


def test_attributes_marks_missing_system_as_false(
    fake_anthropic: type, captured_events: list[TraceEvent]
) -> None:
    _anthropic.install()
    fake_anthropic().create(
        model="claude-3-5-sonnet-20240620",
        messages=[{"role": "user", "content": "x"}],
        max_tokens=256,
    )
    [event] = captured_events
    assert event.attributes["has_system_prompt"] is False


def test_attributes_never_include_message_contents_or_system_body(
    fake_anthropic: type, captured_events: list[TraceEvent]
) -> None:
    _anthropic.install()
    secret_msg = "private message content that must never leak"
    secret_system = "private system prompt content that must never leak"
    fake_anthropic().create(
        model="claude-3-5-sonnet-20240620",
        messages=[{"role": "user", "content": secret_msg}],
        max_tokens=128,
        system=secret_system,
    )
    [event] = captured_events
    assert "messages" not in event.attributes
    assert "system" not in event.attributes
    rendered = repr(event.attributes)
    assert secret_msg not in rendered
    assert secret_system not in rendered


def test_wrapper_records_error_event_and_reraises(
    fake_anthropic: type, captured_events: list[TraceEvent]
) -> None:
    _anthropic.install()

    class APIError(RuntimeError):
        pass

    def boom(self: Any, **kwargs: Any) -> Any:
        raise APIError("rate_limited")

    fake_anthropic.create = _anthropic._wrap(boom)

    with pytest.raises(APIError, match="rate_limited"):
        fake_anthropic().create(
            model="claude-3-5-sonnet-20240620",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=64,
        )

    [event] = captured_events
    assert event.status == "error"
    assert event.model == "claude-3-5-sonnet-20240620"
    assert event.tokens_in == 0
    assert event.tokens_out == 0


def test_sdk_side_error_does_not_break_user_call(
    fake_anthropic: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    _anthropic.install()

    def boom_record(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("retrace bug")

    monkeypatch.setattr(_anthropic, "_safe_record_success", boom_record)
    monkeypatch.setattr(_anthropic, "_safe_record_error", boom_record)

    response = fake_anthropic().create(
        model="claude-3-5-sonnet-20240620",
        messages=[{"role": "user", "content": "x"}],
        max_tokens=64,
    )
    assert response.model == "claude-3-5-sonnet-20240620"


def test_uninstall_restores_original(fake_anthropic: type) -> None:
    pre = fake_anthropic.create
    assert not getattr(pre, "_retrace_patched", False)

    _anthropic.install()
    assert getattr(fake_anthropic.create, "_retrace_patched", False) is True

    _anthropic.uninstall()
    assert fake_anthropic.create is pre


def test_install_silent_no_op_when_anthropic_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("anthropic", "anthropic.resources", "anthropic.resources.messages"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    _anthropic.install()
    assert _anthropic._target_cls is None
    assert _anthropic._original_create is None


def test_init_installs_anthropic_patch(fake_anthropic: type) -> None:
    """retrace.init() must auto-install the Anthropic patch alongside OpenAI."""
    retrace.init(api_key="rt_test", endpoint="http://x.test", batch_size=1)
    assert getattr(fake_anthropic.create, "_retrace_patched", False) is True
