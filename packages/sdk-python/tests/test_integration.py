"""End-to-end: SDK -> in-process FastAPI -> ClickHouse.

Drives the full pipeline using ``httpx.ASGITransport`` so the API runs
in-process - no subprocess, no port juggling. ``openai`` is mocked
via ``sys.modules`` (the SDK never installs it as a hard dep), and we
assert the row landed in ClickHouse under the expected ``project_id``.

Engine cross-loop note: the SDK's runtime owns its own asyncio loop
on a daemon thread. When ``flush()`` runs, the ASGI app executes on
that loop, so SQLAlchemy opens pooled connections there. Disposing
the engine from a different loop angers asyncpg, so the test routes
``engine.dispose()`` back through ``runtime.submit()`` on teardown.
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport

import retrace
from retrace._context import current_trace_id
from retrace.instrumentation import _openai

# Importing api.main installs routes; importing api.clickhouse.client gives
# us the row-query helper.
from api.clickhouse.client import get_client
from api.db.session import engine as api_engine
from api.main import app as api_app


@pytest_asyncio.fixture(autouse=True)
async def _clean_clickhouse_for_sdk(
    sdk_test_api_key: tuple[str, UUID],
) -> AsyncIterator[None]:
    """Wipe any leftover traces for the SDK test project before each test."""
    _, project_id = sdk_test_api_key
    pid = str(project_id)
    ch = get_client()
    await asyncio.to_thread(
        ch.command,
        "ALTER TABLE traces DELETE WHERE project_id = %(pid)s",
        parameters={"pid": pid},
        settings={"mutations_sync": 2},
    )
    yield


@pytest_asyncio.fixture
async def _dispose_api_engine_via_runtime() -> AsyncIterator[None]:
    """After the test, dispose the API engine on the SDK runtime's loop.

    Connections were opened by the in-process API during ``flush()`` on
    that loop; disposing from a different loop trips asyncpg.
    """
    yield
    from retrace._runtime import get_runtime

    runtime = get_runtime()
    if runtime.is_running():
        try:
            future = runtime.submit(api_engine.dispose())
            future.result(timeout=5.0)
        except Exception:
            pass


def _install_fake_openai(monkeypatch: pytest.MonkeyPatch) -> type:
    """Inject a fake ``openai`` module structure so the SDK can patch it.

    Returns the FakeCompletions class so the test can call ``.create()``
    after ``retrace.init()`` has wrapped it.
    """

    class FakeCompletions:
        def create(self, **kwargs: Any) -> Any:
            return MagicMock(
                model=kwargs.get("model"),
                usage=MagicMock(prompt_tokens=42, completion_tokens=17),
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
    return FakeCompletions


async def test_sdk_event_lands_in_clickhouse(
    sdk_test_api_key: tuple[str, UUID],
    monkeypatch: pytest.MonkeyPatch,
    _dispose_api_engine_via_runtime: None,
) -> None:
    raw_key, project_id = sdk_test_api_key
    fake_completions_cls = _install_fake_openai(monkeypatch)

    # ASGITransport wires the SDK's httpx client into the in-process app.
    retrace._configure_for_testing(transport=ASGITransport(app=api_app))
    retrace.init(
        api_key=raw_key,
        endpoint="http://retrace-sdk-test",
        batch_size=1,        # send immediately
        flush_interval=60.0, # don't race the timer
    )
    try:
        # Pin the trace_id so we can SELECT the exact row back, not just
        # "any row for this project."
        known_trace_id = uuid4()
        current_trace_id.set(known_trace_id)

        fake_completions_cls().create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.3,
        )

        retrace.flush(timeout=10.0)

        ch = get_client()
        pid = str(project_id)

        def _select_for_trace() -> list[tuple[str, str, int, int, str]]:
            rows = ch.query(
                "SELECT trace_id, model, tokens_in, tokens_out, status "
                "FROM traces WHERE project_id = %(pid)s AND trace_id = %(tid)s",
                parameters={"pid": pid, "tid": str(known_trace_id)},
            ).result_rows
            return [
                (str(r[0]), str(r[1]), int(r[2]), int(r[3]), str(r[4]))
                for r in rows
            ]

        rows = await asyncio.to_thread(_select_for_trace)
        assert len(rows) == 1, f"expected exactly one row, got {rows}"
        trace_id_str, model, tokens_in, tokens_out, status = rows[0]
        assert trace_id_str == str(known_trace_id)
        assert model == "gpt-4o"
        assert tokens_in == 42
        assert tokens_out == 17
        assert status == "ok"
    finally:
        # Uninstall the openai patch before sys.modules teardown wipes the
        # fake module out from under it.
        _openai.uninstall()
