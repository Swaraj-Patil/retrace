"""Tests for /v1/console/projects/{project_id}/keys.

Five core properties are exercised here:

* ``POST`` returns the raw token exactly once, with ``rt_`` namespace.
* ``GET`` lists each key's metadata - ``key_prefix`` is exposed, but
  the raw token and the argon2 ``hashed_key`` never leave the server.
* ``DELETE`` soft-deletes via ``revoked_at`` and a console-minted key
  is a real production credential: once revoked, it stops authing on
  the existing API-key path (``/v1/projects/me`` returns 401).
* Cross-org access (user A touching user B's project) is uniformly
  404 ``project_not_found`` for list/create/delete - no enumeration.
* Idempotent re-revoke returns 204; unknown key id under the caller's
  own project returns 404 ``api_key_not_found``.
"""

from __future__ import annotations

import uuid as _uuid
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select

from api.db.session import SessionLocal
from api.models import ApiKey
from tests.conftest import SessionUserFixture


async def _create_key(
    client: AsyncClient, *, token: str, project_id: UUID, name: str = "test-key"
) -> dict:
    r = await client.post(
        f"/v1/console/projects/{project_id}/keys",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_key_returns_raw_once(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    created = await _create_key(
        client,
        token=session_user_fixture.token,
        project_id=session_user_fixture.project_id,
        name="first-key",
    )
    assert created["raw_key"].startswith("rt_")
    assert created["key_prefix"] == created["raw_key"][:11]
    assert created["name"] == "first-key"
    # Sanity: the row exists in DB and the hashed_key is set.
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(ApiKey).where(ApiKey.id == UUID(created["id"]))
            )
        ).scalar_one()
        assert row.hashed_key.startswith("$argon2")
        assert row.key_prefix == created["key_prefix"]


async def test_list_keys_omits_raw_and_hashed(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    await _create_key(
        client,
        token=session_user_fixture.token,
        project_id=session_user_fixture.project_id,
        name="lookable-key",
    )
    r = await client.get(
        f"/v1/console/projects/{session_user_fixture.project_id}/keys",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 200
    keys = r.json()["keys"]
    assert keys, "expected at least the key created above"
    for k in keys:
        assert "raw_key" not in k
        assert "hashed_key" not in k
        # Schema is _Strict (extra=forbid), so the response keys
        # are exactly the contract.
        assert set(k.keys()) == {
            "id",
            "name",
            "key_prefix",
            "last_used_at",
            "revoked_at",
            "created_at",
        }


async def test_revoke_key_soft_deletes_and_breaks_rt_auth(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    """The console-minted key authenticates through the real api-key
    path until it's revoked, then it stops - revocation propagates to
    the existing auth dependency without any extra code path."""
    created = await _create_key(
        client,
        token=session_user_fixture.token,
        project_id=session_user_fixture.project_id,
        name="revoke-key",
    )
    raw = created["raw_key"]
    key_id = UUID(created["id"])

    # Pre-revoke: the raw key authenticates the existing api-key path.
    before = await client.get(
        "/v1/projects/me", headers={"Authorization": f"Bearer {raw}"}
    )
    assert before.status_code == 200
    assert UUID(before.json()["project_id"]) == session_user_fixture.project_id

    revoke = await client.delete(
        f"/v1/console/projects/{session_user_fixture.project_id}/keys/{key_id}",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert revoke.status_code == 204

    # Post-revoke: the same raw key now fails the rt_ path with the
    # uniform 401 (no distinction from "unknown key").
    after = await client.get(
        "/v1/projects/me", headers={"Authorization": f"Bearer {raw}"}
    )
    assert after.status_code == 401
    assert after.json() == {"error": "invalid_credentials"}

    # Soft-delete: row still exists with ``revoked_at`` populated.
    async with SessionLocal() as session:
        row = (
            await session.execute(select(ApiKey).where(ApiKey.id == key_id))
        ).scalar_one()
        assert row.revoked_at is not None


async def test_revoke_is_idempotent(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    created = await _create_key(
        client,
        token=session_user_fixture.token,
        project_id=session_user_fixture.project_id,
        name="idemp-key",
    )
    key_id = UUID(created["id"])
    url = f"/v1/console/projects/{session_user_fixture.project_id}/keys/{key_id}"
    headers = {"Authorization": f"Bearer {session_user_fixture.token}"}

    r1 = await client.delete(url, headers=headers)
    assert r1.status_code == 204
    r2 = await client.delete(url, headers=headers)
    # Same key, still in the caller's project. Already revoked - the
    # service short-circuits without re-stamping ``revoked_at`` but
    # still returns 204.
    assert r2.status_code == 204


async def test_revoke_unknown_key_id_in_own_project_returns_404(
    client: AsyncClient, session_user_fixture: SessionUserFixture
) -> None:
    bogus_id = _uuid.uuid4()
    r = await client.delete(
        f"/v1/console/projects/{session_user_fixture.project_id}/keys/{bogus_id}",
        headers={"Authorization": f"Bearer {session_user_fixture.token}"},
    )
    assert r.status_code == 404
    assert r.json() == {"error": "api_key_not_found"}


async def test_cross_org_key_endpoints_all_return_404(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
    second_session_user_fixture: SessionUserFixture,
) -> None:
    """User A acting on user B's project: list/create/delete all
    surface 404 ``project_not_found``. Same shape as "doesn't exist",
    so cross-org enumeration is impossible."""
    a_headers = {"Authorization": f"Bearer {session_user_fixture.token}"}
    foreign_pid = second_session_user_fixture.project_id

    # First, create a real key inside B's project (using B's session)
    # so the cross-org DELETE has a real id to target - we want to
    # verify that even with a valid foreign key_id, A gets 404.
    b_created = await _create_key(
        client,
        token=second_session_user_fixture.token,
        project_id=foreign_pid,
        name="b-key",
    )
    foreign_key_id = UUID(b_created["id"])

    # A lists B's keys.
    r_list = await client.get(
        f"/v1/console/projects/{foreign_pid}/keys", headers=a_headers
    )
    assert r_list.status_code == 404
    assert r_list.json() == {"error": "project_not_found"}

    # A creates a key on B's project.
    r_create = await client.post(
        f"/v1/console/projects/{foreign_pid}/keys",
        json={"name": "should-not-exist"},
        headers=a_headers,
    )
    assert r_create.status_code == 404
    assert r_create.json() == {"error": "project_not_found"}

    # A revokes B's key.
    r_delete = await client.delete(
        f"/v1/console/projects/{foreign_pid}/keys/{foreign_key_id}",
        headers=a_headers,
    )
    assert r_delete.status_code == 404
    assert r_delete.json() == {"error": "project_not_found"}

    # B can still revoke their own key (control case).
    r_b_delete = await client.delete(
        f"/v1/console/projects/{foreign_pid}/keys/{foreign_key_id}",
        headers={"Authorization": f"Bearer {second_session_user_fixture.token}"},
    )
    assert r_b_delete.status_code == 204
