"""Argon2 password hashing for user accounts.

Separate ``PasswordHasher`` instance from API-key / session hashing so
the cost parameters can be tuned independently in the future. Passwords
are verified at login time (rare); API keys and session tokens are
verified on every authenticated request (hot path).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, raw_password)
    except (VerifyMismatchError, InvalidHashError):
        return False
