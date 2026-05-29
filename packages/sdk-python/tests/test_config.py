"""Tests for ``retrace.init()`` validation, idempotency, and env fallback."""

from __future__ import annotations

import pytest

import retrace
from retrace._config import build_config, get_config


def test_init_rejects_key_without_rt_prefix() -> None:
    with pytest.raises(ValueError, match="rt_"):
        retrace.init(api_key="not-prefixed")


def test_init_rejects_non_positive_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        retrace.init(api_key="rt_x", batch_size=0)


def test_init_rejects_non_positive_flush_interval() -> None:
    with pytest.raises(ValueError, match="flush_interval"):
        retrace.init(api_key="rt_x", flush_interval=0)


def test_init_stores_config_with_explicit_endpoint() -> None:
    retrace.init(api_key="rt_test", endpoint="http://example.test:9000")
    cfg = get_config()
    assert cfg is not None
    assert cfg.api_key == "rt_test"
    assert cfg.endpoint == "http://example.test:9000"
    assert cfg.batch_size == 100
    assert cfg.flush_interval == 5.0
    assert cfg.enabled is True


def test_init_strips_trailing_slash_from_endpoint() -> None:
    retrace.init(api_key="rt_test", endpoint="http://api.test/")
    cfg = get_config()
    assert cfg is not None and cfg.endpoint == "http://api.test"


def test_endpoint_falls_back_to_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRACE_ENDPOINT", "http://env.test:1234")
    retrace.init(api_key="rt_test")
    cfg = get_config()
    assert cfg is not None and cfg.endpoint == "http://env.test:1234"


def test_endpoint_default_when_no_arg_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RETRACE_ENDPOINT", raising=False)
    retrace.init(api_key="rt_test")
    cfg = get_config()
    assert cfg is not None and cfg.endpoint == "http://localhost:8000"


def test_init_is_idempotent_and_replaces_config() -> None:
    retrace.init(api_key="rt_first", endpoint="http://a.test")
    retrace.init(api_key="rt_second", endpoint="http://b.test", batch_size=50)

    cfg = get_config()
    assert cfg is not None
    assert cfg.api_key == "rt_second"
    assert cfg.endpoint == "http://b.test"
    assert cfg.batch_size == 50


def test_init_disabled_does_not_start_runtime() -> None:
    from retrace._runtime import get_runtime

    retrace.init(api_key="rt_test", enabled=False)
    assert get_runtime().is_running() is False


def test_init_enabled_starts_runtime() -> None:
    from retrace._runtime import get_runtime

    retrace.init(api_key="rt_test", enabled=True)
    assert get_runtime().is_running() is True


def test_build_config_unit() -> None:
    cfg = build_config(api_key="rt_unit", endpoint="http://x.test", batch_size=10, flush_interval=1)
    assert cfg.batch_size == 10
    assert cfg.flush_interval == 1
    assert cfg.enabled is True
