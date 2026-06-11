"""Tests for POST /v1/auth/register.

The happy path bootstraps a user, org, owner membership, and a default
project in one transaction and returns a session token so the caller
lands authenticated in one round trip. Validation failures (short
password, bad email shape) and duplicate-email collisions short-circuit
before any rows are written.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import delete, select

from api.db.session import SessionLocal
from api.models import Membership, MembershipRole, Org, Project, User


def _fresh_email() -> str:
    return f"register-{uuid4().hex}@retrace.test"


async def _drop_user_by_email(email: str) -> None:
    async with SessionLocal() as session:
        user_id = (
            await session.execute(select(User.id).where(User.email == email))
        ).scalar_one_or_none()
        if user_id is None:
            return
        # Find any orgs the user owned and delete them too so the cascade
        # cleans memberships/projects/sessions in one go.
        org_ids = (
            await session.execute(
                select(Membership.org_id).where(Membership.user_id == user_id)
            )
        ).scalars().all()
        for org_id in org_ids:
            await session.execute(delete(Org).where(Org.id == org_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_register_returns_201_with_session_token(client: AsyncClient) -> None:
    email = _fresh_email()
    try:
        r = await client.post(
            "/v1/auth/register",
            json={"email": email, "password": "hunter2hunter2", "name": "Reg"},
        )
        assert r.status_code == 201
        body = r.json()
        assert set(body.keys()) == {"token", "expires_at"}
        assert body["token"].startswith("rts_")
        # Token should authenticate against /me immediately.
        me = await client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {body['token']}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == email
    finally:
        await _drop_user_by_email(email)


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    email = _fresh_email()
    try:
        r1 = await client.post(
            "/v1/auth/register",
            json={"email": email, "password": "hunter2hunter2"},
        )
        assert r1.status_code == 201
        r2 = await client.post(
            "/v1/auth/register",
            json={"email": email, "password": "hunter2hunter2"},
        )
        assert r2.status_code == 409
        assert r2.json() == {"error": "email_already_registered"}
    finally:
        await _drop_user_by_email(email)


async def test_register_short_password_returns_422(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/auth/register",
        json={"email": "x@example.com", "password": "short"},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any(d["loc"] == ["body", "password"] for d in detail)


async def test_register_bad_email_returns_422(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/auth/register",
        json={"email": "not-an-email-at-all", "password": "hunter2hunter2"},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any(d["loc"] == ["body", "email"] for d in detail)


async def test_register_bootstraps_user_org_membership_project_atomically(
    client: AsyncClient,
) -> None:
    """All four rows must exist after a successful register: User,
    Org, Membership(role=owner), Project(name="Default Project")."""
    email = _fresh_email()
    try:
        r = await client.post(
            "/v1/auth/register",
            json={"email": email, "password": "hunter2hunter2", "name": "Bootstrapper"},
        )
        assert r.status_code == 201

        async with SessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one()
            assert user.hashed_password is not None
            assert user.hashed_password.startswith("$argon2")
            assert user.name == "Bootstrapper"

            membership = (
                await session.execute(
                    select(Membership).where(Membership.user_id == user.id)
                )
            ).scalar_one()
            assert membership.role == MembershipRole.OWNER

            org = (
                await session.execute(select(Org).where(Org.id == membership.org_id))
            ).scalar_one()
            # Name uses email-local prefix + "'s Workspace".
            assert org.name.endswith("'s Workspace")
            # Slug is the email-local part (since the local has no
            # special chars in this test fixture).
            assert org.slug.startswith(email.split("@", 1)[0].lower())

            project = (
                await session.execute(
                    select(Project).where(Project.org_id == org.id)
                )
            ).scalar_one()
            assert project.name == "Default Project"
            assert project.slug == "default"
    finally:
        await _drop_user_by_email(email)


async def test_register_failed_duplicate_does_not_leave_partial_rows(
    client: AsyncClient,
) -> None:
    """A 409 on duplicate email must not leave half-created state -
    the pre-check fires before any inserts run, so a failed
    registration is invisible at the DB level."""
    email = _fresh_email()
    try:
        r1 = await client.post(
            "/v1/auth/register",
            json={"email": email, "password": "hunter2hunter2"},
        )
        assert r1.status_code == 201

        async with SessionLocal() as session:
            users_before = (
                await session.execute(select(User).where(User.email == email))
            ).scalars().all()
            orgs_before_count = len(
                (
                    await session.execute(
                        select(Org).where(
                            Org.id == (
                                await session.execute(
                                    select(Membership.org_id).where(
                                        Membership.user_id == users_before[0].id
                                    )
                                )
                            ).scalar_one()
                        )
                    )
                ).scalars().all()
            )
        assert len(users_before) == 1
        assert orgs_before_count == 1

        # Second register with same email should 409 and not mutate state.
        r2 = await client.post(
            "/v1/auth/register",
            json={"email": email, "password": "different-pw-1234"},
        )
        assert r2.status_code == 409

        async with SessionLocal() as session:
            users_after = (
                await session.execute(select(User).where(User.email == email))
            ).scalars().all()
        # Same user row, same id - no extra inserts happened.
        assert len(users_after) == 1
        assert users_after[0].id == users_before[0].id
    finally:
        await _drop_user_by_email(email)
