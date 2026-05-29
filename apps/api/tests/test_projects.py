"""Tests for /v1/projects/me."""

from __future__ import annotations

from uuid import UUID

from httpx import AsyncClient


async def test_projects_me_returns_authenticated_project_metadata(
    client: AsyncClient, test_api_key: tuple[str, UUID]
) -> None:
    raw_key, project_id = test_api_key
    r = await client.get(
        "/v1/projects/me",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "project_id": str(project_id),
        "project_name": "Integration Test Project",
        "org_id": body["org_id"],
        "org_name": "Integration Test Org",
    }
    # org_id is fixture-private; just confirm the value parses.
    UUID(body["org_id"])


async def test_projects_me_without_auth_returns_401(client: AsyncClient) -> None:
    r = await client.get("/v1/projects/me")
    assert r.status_code == 401
    assert r.json() == {"error": "invalid_credentials"}
