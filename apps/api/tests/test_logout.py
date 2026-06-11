"""Tests for POST /v1/auth/logout.

Logout soft-deletes the session via ``revoked_at`` so the existing
auth dependency rejects the (now stale) token with the uniform 401.
Idempotency falls out for free: a second logout call with the same
token never reaches the handler because ``get_current_user`` rejects
it at the bearer layer.
"""

from __future__ import annotations

from httpx import AsyncClient


async def _login(client: AsyncClient, email: str, password: str) -> str:
    r = await client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def test_logout_returns_204_then_token_fails_at_me(
    client: AsyncClient, session_user_fixture
) -> None:
    # Fresh session via login so we don't revoke the fixture's
    # session token (other tests rely on it).
    token = await _login(
        client, session_user_fixture.email, session_user_fixture.password
    )
    headers = {"Authorization": f"Bearer {token}"}

    me_before = await client.get("/v1/auth/me", headers=headers)
    assert me_before.status_code == 200

    out = await client.post("/v1/auth/logout", headers=headers)
    assert out.status_code == 204
    assert out.content in (b"", b"null")  # 204 has no body

    me_after = await client.get("/v1/auth/me", headers=headers)
    assert me_after.status_code == 401
    assert me_after.json() == {"error": "invalid_credentials"}


async def test_logout_is_idempotent_via_401(
    client: AsyncClient, session_user_fixture
) -> None:
    """The second logout call returns 401 because the auth-layer
    dependency rejects the stale token before the handler runs - no
    special-casing required in the handler."""
    token = await _login(
        client, session_user_fixture.email, session_user_fixture.password
    )
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post("/v1/auth/logout", headers=headers)
    assert first.status_code == 204

    second = await client.post("/v1/auth/logout", headers=headers)
    assert second.status_code == 401
    assert second.json() == {"error": "invalid_credentials"}


async def test_logout_without_auth_returns_401(client: AsyncClient) -> None:
    r = await client.post("/v1/auth/logout")
    assert r.status_code == 401


async def test_logout_with_api_key_returns_401(
    client: AsyncClient, test_api_key: tuple[str, object]
) -> None:
    raw_key, _ = test_api_key
    r = await client.post(
        "/v1/auth/logout", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert r.status_code == 401
