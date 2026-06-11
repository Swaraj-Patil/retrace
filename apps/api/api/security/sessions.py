"""Generation, hashing and verification of user-session tokens.

Format: ``rts_<24 bytes url-safe base64>``. The first
``SESSION_TOKEN_PREFIX_LEN`` chars (``rts_`` + 7 chars of the random
body) are stored plaintext on the row (``token_prefix``) for O(1)
lookup; the full token is argon2-hashed into ``hashed_token`` for
verification. The ``rts_`` namespace distinguishes session tokens
from API keys (``rt_``) at the bearer-token layer so a single
auth dependency can dispatch by prefix.

Session tokens and API keys both use long random secrets, so the
hasher cost is identical for now. The dedicated module makes it
cheap to diverge later (e.g., lower memory cost on the session
verify path if it becomes the dominant cost).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

SESSION_TOKEN_NAMESPACE = "rts_"
SESSION_TOKEN_PREFIX_LEN = 11
SESSION_TTL = timedelta(days=30)
_RAW_TOKEN_BYTES = 24

_hasher = PasswordHasher()


@dataclass(frozen=True)
class GeneratedSessionToken:
    raw: str
    prefix: str
    hashed: str


def generate_session_token() -> GeneratedSessionToken:
    """Generate a new session token. Return the raw token (show once) plus prefix and hash."""
    raw = SESSION_TOKEN_NAMESPACE + secrets.token_urlsafe(_RAW_TOKEN_BYTES)
    return GeneratedSessionToken(
        raw=raw,
        prefix=raw[:SESSION_TOKEN_PREFIX_LEN],
        hashed=_hasher.hash(raw),
    )


def verify_session_token(raw_token: str, hashed_token: str) -> bool:
    try:
        return _hasher.verify(hashed_token, raw_token)
    except (VerifyMismatchError, InvalidHashError):
        return False
