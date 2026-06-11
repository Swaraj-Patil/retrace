"""Tests for /v1/console/projects.

Session-only. Listing scopes to the caller's memberships - user A
never sees user B's projects. Creation auto-derives a slug from the
name when not supplied; an explicit slug bypasses derivation; a
duplicate slug in the same org returns 409 (no server-side retry -
the caller has agency); a name that contains no ASCII alphanumerics
returns 422 instead of silently falling back to a generic slug.
"""

from __future__ import annotations

from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import delete, select

from api.db.session import SessionLocal
from api.models import Project
from tests.conftest import SessionUserFixture


async def _drop_projects_by_ids(ids: list[UUID]) -> None:
    if not ids:
        return
    async with SessionLocal() as session:
        await session.execute(delete(Project).where(Project.id.in_(ids)))
        await session.commit()


async def _list_projects_for_user(token: str, client: AsyncClient) -> list[dict]:
    r = await client.get(
        "/v1/console/projects", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text
    return r.json()["projects"]


async def test_list_scopes_to_caller_memberships(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
    second_session_user_fixture: SessionUserFixture,
) -> None:
    a_projects = await _list_projects_for_user(session_user_fixture.token, client)
    b_projects = await _list_projects_for_user(
        second_session_user_fixture.token, client
    )

    a_ids = {UUID(p["id"]) for p in a_projects}
    b_ids = {UUID(p["id"]) for p in b_projects}

    assert session_user_fixture.project_id in a_ids
    assert second_session_user_fixture.project_id in b_ids
    # No leakage either direction.
    assert session_user_fixture.project_id not in b_ids
    assert second_session_user_fixture.project_id not in a_ids


async def test_list_returns_org_name_and_role(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    rows = await _list_projects_for_user(session_user_fixture.token, client)
    own = next(p for p in rows if UUID(p["id"]) == session_user_fixture.project_id)
    assert own["role"] == "owner"
    assert UUID(own["org_id"]) == session_user_fixture.org_id
    assert own["org_name"] == "Session Test Org A"


async def test_create_project_auto_slug(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    created_ids: list[UUID] = []
    try:
        r = await client.post(
            "/v1/console/projects",
            json={"name": "My Cool Project"},
            headers={"Authorization": f"Bearer {session_user_fixture.token}"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["slug"] == "my-cool-project"
        assert body["name"] == "My Cool Project"
        assert UUID(body["org_id"]) == session_user_fixture.org_id
        created_ids.append(UUID(body["id"]))
    finally:
        await _drop_projects_by_ids(created_ids)


async def test_create_project_explicit_slug(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    created_ids: list[UUID] = []
    try:
        r = await client.post(
            "/v1/console/projects",
            json={"name": "Whatever Name", "slug": "explicit-slug-here"},
            headers={"Authorization": f"Bearer {session_user_fixture.token}"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["slug"] == "explicit-slug-here"
        created_ids.append(UUID(body["id"]))
    finally:
        await _drop_projects_by_ids(created_ids)


async def test_create_project_duplicate_slug_returns_409(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    created_ids: list[UUID] = []
    headers = {"Authorization": f"Bearer {session_user_fixture.token}"}
    try:
        r1 = await client.post(
            "/v1/console/projects",
            json={"name": "First", "slug": "dup-slug"},
            headers=headers,
        )
        assert r1.status_code == 201
        created_ids.append(UUID(r1.json()["id"]))

        r2 = await client.post(
            "/v1/console/projects",
            json={"name": "Second", "slug": "dup-slug"},
            headers=headers,
        )
        assert r2.status_code == 409
        assert r2.json() == {"error": "project_slug_taken"}
    finally:
        await _drop_projects_by_ids(created_ids)


async def test_create_project_empty_derived_slug_returns_422(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    """A name like ``"!!!"`` slugifies to empty. The schema rejects
    with 422 + a clear message rather than falling back silently to
    a generic slug (which would either collide or misrepresent input)."""
    for name in ("!!!", "🚀🚀🚀", "...---..."):
        r = await client.post(
            "/v1/console/projects",
            json={"name": name},
            headers={"Authorization": f"Bearer {session_user_fixture.token}"},
        )
        assert r.status_code == 422, f"{name!r} should be 422 but got {r.status_code}"
        detail = r.json()["detail"]
        assert any("ASCII alphanumerics" in d["msg"] for d in detail), detail


async def test_create_project_with_explicit_slug_allows_nonsense_name(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    """An explicit slug bypasses the derivation check, so an unusual
    display name is allowed as long as the slug is supplied."""
    created_ids: list[UUID] = []
    try:
        r = await client.post(
            "/v1/console/projects",
            json={"name": "!!!", "slug": "emoji-named"},
            headers={"Authorization": f"Bearer {session_user_fixture.token}"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "!!!"
        assert body["slug"] == "emoji-named"
        created_ids.append(UUID(body["id"]))
    finally:
        await _drop_projects_by_ids(created_ids)


async def test_create_project_bad_slug_pattern_returns_422(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    r = await client.post(
        "/v1/console/projects",
        json={"name": "X", "slug": "NotLowercase"},
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 422


async def test_console_projects_rejects_api_key(
    client: AsyncClient, test_api_key: tuple[str, object]
) -> None:
    """Account management is human-only; sessions only."""
    raw_key, _ = test_api_key
    r = await client.get(
        "/v1/console/projects", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert r.status_code == 401


async def test_console_projects_without_auth_returns_401(client: AsyncClient) -> None:
    r = await client.get("/v1/console/projects")
    assert r.status_code == 401
