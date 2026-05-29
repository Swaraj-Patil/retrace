"""Unit tests for argon2-cffi-backed key hashing helpers."""

from __future__ import annotations

from api.security import hash_api_key, verify_api_key


def test_hash_verify_roundtrip() -> None:
    raw = "rt_some_random_key_body_xyz"
    hashed = hash_api_key(raw)
    assert hashed.startswith("$argon2")
    assert verify_api_key(raw, hashed) is True


def test_verify_returns_false_on_mismatch() -> None:
    hashed = hash_api_key("rt_correct_key")
    assert verify_api_key("rt_wrong_key", hashed) is False
