"""Tests for GET /v1/auth/me.

Session-only - API keys are rejected at the bearer layer because
account introspection is a human action. The response surfaces the
caller's id/email/name plus their org memberships with role.
"""

from __future__ import annotations

from uuid import UUID

from httpx import AsyncClient

from tests.conftest import SessionUserFixture


async def test_me_returns_user_orgs_and_role(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    r = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert UUID(body["user_id"]) == session_user_fixture.user_id
    assert body["email"] == session_user_fixture.email
    assert isinstance(body["orgs"], list)
    org_ids = [UUID(o["id"]) for o in body["orgs"]]
    assert session_user_fixture.org_id in org_ids
    own_org = next(o for o in body["orgs"] if UUID(o["id"]) == session_user_fixture.org_id)
    assert own_org["role"] == "owner"


async def test_me_without_auth_returns_401(client: AsyncClient) -> None:
    r = await client.get("/v1/auth/me")
    assert r.status_code == 401
    assert r.json() == {"error": "invalid_credentials"}


async def test_me_with_api_key_returns_401(
    client: AsyncClient, test_api_key: tuple[str, object]
) -> None:
    """API keys must not reach /me. Account introspection is a
    human action; sessions only."""
    raw_key, _ = test_api_key
    r = await client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert r.status_code == 401
