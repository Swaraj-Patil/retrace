"""Generation, hashing and verification of project API keys.

Format: ``rt_<24 bytes url-safe base64>``. The first ``KEY_PREFIX_LEN`` chars
are stored in plaintext on the row (``key_prefix``) so lookup is O(1); the full
key is argon2-hashed into ``hashed_key`` for verification.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from passlib.context import CryptContext

KEY_PREFIX_LEN = 8
_RAW_KEY_BYTES = 24
_KEY_NAMESPACE = "rt_"

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


@dataclass(frozen=True)
class GeneratedApiKey:
    raw: str
    prefix: str
    hashed: str


def generate_api_key() -> GeneratedApiKey:
    """Generate a new API key. Return the raw key (show once) plus prefix and hash."""
    raw = _KEY_NAMESPACE + secrets.token_urlsafe(_RAW_KEY_BYTES)
    return GeneratedApiKey(
        raw=raw,
        prefix=raw[:KEY_PREFIX_LEN],
        hashed=hash_api_key(raw),
    )


def hash_api_key(raw_key: str) -> str:
    return _pwd_context.hash(raw_key)


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    return _pwd_context.verify(raw_key, hashed_key)
