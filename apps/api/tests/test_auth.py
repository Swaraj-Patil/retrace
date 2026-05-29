"""Tests for the bearer-token auth dependency.

Every failure path must yield the same 401/`invalid_credentials`
response - we deliberately do not let callers distinguish between
"unknown key", "wrong hash", "revoked", etc.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from api.db.session import SessionLocal
from api.models import ApiKey
from tests.conftest import PROTECTED_TEST_PATH

_EXPECTED_401_BODY = {"error": "invalid_credentials"}


async def test_missing_authorization_header_returns_401(client: AsyncClient) -> None:
    r = await client.get(PROTECTED_TEST_PATH)
    assert r.status_code == 401
    assert r.json() == _EXPECTED_401_BODY


async def test_token_without_rt_prefix_returns_401(client: AsyncClient) -> None:
    r = await client.get(
        PROTECTED_TEST_PATH,
        headers={"Authorization": "Bearer not-an-rt-prefixed-key"},
    )
    assert r.status_code == 401
    assert r.json() == _EXPECTED_401_BODY


async def test_token_too_short_returns_401(client: AsyncClient) -> None:
    # Shorter than KEY_PREFIX_LEN (11): cannot even form the lookup slice.
    r = await client.get(
        PROTECTED_TEST_PATH,
        headers={"Authorization": "Bearer rt_xy"},
    )
    assert r.status_code == 401
    assert r.json() == _EXPECTED_401_BODY


async def test_unknown_prefix_returns_401(
    client: AsyncClient,
    test_api_key: tuple[str, UUID],
) -> None:
    # Well-formed key shape, but no row in api_keys with this prefix.
    forged = "rt_ZZZZZZZZ_no_such_key_in_db"
    r = await client.get(
        PROTECTED_TEST_PATH,
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert r.status_code == 401
    assert r.json() == _EXPECTED_401_BODY


async def test_valid_prefix_wrong_body_returns_401(
    client: AsyncClient,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    # Keep the real prefix so the row lookup succeeds; swap the body so
    # argon2 verification fails.
    forged = raw_key[:11] + "tampered_remainder_xyz"
    r = await client.get(
        PROTECTED_TEST_PATH,
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert r.status_code == 401
    assert r.json() == _EXPECTED_401_BODY


async def test_revoked_key_returns_401(
    client: AsyncClient,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, _ = test_api_key
    prefix = raw_key[:11]
    await _set_revoked_at(prefix, datetime.now(UTC))
    try:
        r = await client.get(
            PROTECTED_TEST_PATH,
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert r.status_code == 401
        assert r.json() == _EXPECTED_401_BODY
    finally:
        await _set_revoked_at(prefix, None)


async def test_valid_key_returns_200_with_project_context(
    client: AsyncClient,
    test_api_key: tuple[str, UUID],
) -> None:
    raw_key, project_id = test_api_key
    r = await client.get(
        PROTECTED_TEST_PATH,
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == str(project_id)
    assert body["project_name"] == "Integration Test Project"


async def _set_revoked_at(prefix: str, value: datetime | None) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(ApiKey).where(ApiKey.key_prefix == prefix).values(revoked_at=value)
        )
        await session.commit()
