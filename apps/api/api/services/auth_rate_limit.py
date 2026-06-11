"""In-memory sliding-window rate limit for login attempts.

PER-PROCESS. Each uvicorn worker enforces its own window independently,
so the effective limit multiplies by the number of workers. That's fine
for Phase A (single-worker dev/demo) but needs Redis or a DB-backed
counter when we scale out — flag is the same posture as the
fire-and-forget ``last_used_at`` update in the API-key path.

The check is keyed by ``(client_ip, email)`` so a hostile client can't
trivially lock out a user by hammering from elsewhere, and a legitimate
user fumbling their password from one device can't be DoS'd by an
unrelated user on the same email. Every attempt (success or failure)
counts, so the limit fires before the password is even checked — that
keeps the argon2 verify off the brute-force hot path.
"""

from __future__ import annotations

import threading
import time
from collections import deque

_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 60.0

_state: dict[str, deque[float]] = {}
_lock = threading.Lock()


class RateLimited(Exception):
    """Raised when a (client_ip, email) bucket exceeds the window limit."""


def _bucket_key(client_ip: str, email: str) -> str:
    return f"{client_ip}|{email}"


def check_login_rate_limit(client_ip: str, email: str) -> None:
    """Record a login attempt; raise :class:`RateLimited` if the bucket is full."""
    key = _bucket_key(client_ip, email)
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    with _lock:
        bucket = _state.setdefault(key, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _MAX_ATTEMPTS:
            raise RateLimited
        bucket.append(now)


def reset_login_rate_limit() -> None:
    """Test helper. Clear every bucket. Never called in production."""
    with _lock:
        _state.clear()
