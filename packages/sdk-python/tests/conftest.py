"""Shared fixtures for SDK tests.

Every test that touches SDK module-level state runs with a clean slate:
config wiped, runtime stopped. Without this the runtime thread spawned
by one test leaks into the next.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import retrace
from retrace import _config, _runtime
from retrace._context import current_trace_id


@pytest.fixture(autouse=True)
def reset_sdk_state() -> Iterator[None]:
    retrace._reset_for_tests()
    _config.reset_for_tests()
    _runtime.reset_for_tests()
    # Sync tests share the pytest thread's contextvars Context; clear the
    # trace_id so each test starts with no current trace.
    current_trace_id.set(None)
    yield
    retrace._reset_for_tests()
    _config.reset_for_tests()
    _runtime.reset_for_tests()
    current_trace_id.set(None)
