"""Tests for ``HttpClient`` retry policy."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from retrace import _client
from retrace._client import HttpClient


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Zero out backoff so retry tests run instantly."""
    monkeypatch.setattr(_client, "_BACKOFF_BASE", 0.0)
    monkeypatch.setattr(_client, "_BACKOFF_MAX_JITTER", 0.0)
    yield


async def test_send_returns_true_on_2xx() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"inserted": {"traces": 1}, "project_id": "x"})

    transport = httpx.MockTransport(handler)
    client = HttpClient("http://api.test", "rt_key", transport=transport)
    try:
        assert await client.send_traces(b'{"traces": []}') is True
    finally:
        await client.aclose()


async def test_send_retries_on_5xx_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HttpClient("http://api.test", "rt_key", transport=transport)
    try:
        assert await client.send_traces(b"{}") is True
    finally:
        await client.aclose()
    assert calls["n"] == 3


async def test_send_gives_up_after_max_5xx_attempts() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = HttpClient("http://api.test", "rt_key", transport=transport)
    try:
        assert await client.send_traces(b"{}") is False
    finally:
        await client.aclose()
    assert calls["n"] == _client._MAX_ATTEMPTS


async def test_send_does_not_retry_on_4xx() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="invalid_credentials")

    transport = httpx.MockTransport(handler)
    client = HttpClient("http://api.test", "rt_key", transport=transport)
    try:
        assert await client.send_traces(b"{}") is False
    finally:
        await client.aclose()
    assert calls["n"] == 1


async def test_send_retries_on_network_error_then_gives_up() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    client = HttpClient("http://api.test", "rt_key", transport=transport)
    try:
        assert await client.send_traces(b"{}") is False
    finally:
        await client.aclose()
    assert calls["n"] == _client._MAX_ATTEMPTS


async def test_send_recovers_after_one_network_error() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("flaky")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HttpClient("http://api.test", "rt_key", transport=transport)
    try:
        assert await client.send_traces(b"{}") is True
    finally:
        await client.aclose()
    assert calls["n"] == 2


async def test_send_uses_bearer_header_and_ingest_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization", "")
        seen["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HttpClient("http://api.test", "rt_secret", transport=transport)
    try:
        await client.send_traces(b'{"traces": []}')
    finally:
        await client.aclose()
    assert seen["url"] == "http://api.test/v1/ingest"
    assert seen["auth"] == "Bearer rt_secret"
    assert seen["content_type"] == "application/json"
