"""Shared fixtures for SDK tests.

Every test that touches SDK module-level state runs with a clean slate:
config wiped, runtime stopped. Without this the runtime thread spawned
by one test leaks into the next.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from retrace import _config, _runtime


@pytest.fixture(autouse=True)
def reset_sdk_state() -> Iterator[None]:
    _config.reset_for_tests()
    _runtime.reset_for_tests()
    yield
    _config.reset_for_tests()
    _runtime.reset_for_tests()
