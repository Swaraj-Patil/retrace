"""Tests for POST /v1/auth/login.

Every failure mode collapses to the uniform 401 ``invalid_credentials``
- wrong password, unknown email, and "user has no hashed_password" are
deliberately indistinguishable. The login path is rate-limited per
(client_ip, email): the 6th attempt inside a 60s window returns 429,
before the argon2 verify even runs.
"""

from __future__ import annotations

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import delete, select

from api.db.session import SessionLocal
from api.models import User
from tests.conftest import SessionUserFixture


_INVALID = {"error": "invalid_credentials"}


async def test_login_good_credentials_returns_token(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
) -> None:
    r = await client.post(
        "/v1/auth/login",
        json={
            "email": session_user_fixture.email,
            "password": session_user_fixture.password,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"token", "expires_at"}
    assert body["token"].startswith("rts_")
    # The returned token must work against /me immediately.
    me = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {body['token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == session_user_fixture.email


async def test_login_wrong_password_returns_401(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
) -> None:
    r = await client.post(
        "/v1/auth/login",
        json={"email": session_user_fixture.email, "password": "not-the-right-one"},
    )
    assert r.status_code == 401
    assert r.json() == _INVALID


async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/auth/login",
        json={
            "email": f"unknown-{uuid4().hex}@retrace.test",
            "password": "whatever-1234",
        },
    )
    assert r.status_code == 401
    assert r.json() == _INVALID


async def test_login_user_with_null_password_returns_401(client: AsyncClient) -> None:
    """A user row with ``hashed_password IS NULL`` (e.g., the demo
    seed user) cannot log in. Same uniform 401 as a wrong password
    so the caller cannot enumerate which accounts have a password."""
    email = f"null-pw-{uuid4().hex}@retrace.test"
    async with SessionLocal() as session:
        user = User(email=email, name="No Password", hashed_password=None)
        session.add(user)
        await session.commit()
    try:
        r = await client.post(
            "/v1/auth/login",
            json={"email": email, "password": "anything-1234"},
        )
        assert r.status_code == 401
        assert r.json() == _INVALID
    finally:
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.email == email))
            await session.commit()


async def test_login_sixth_attempt_returns_429(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
) -> None:
    """Five attempts (any outcome) within the window are allowed; the
    sixth is throttled with 429 + Retry-After before the argon2 verify."""
    payload = {
        "email": session_user_fixture.email,
        "password": "definitely-wrong-password",
    }
    for _ in range(5):
        r = await client.post("/v1/auth/login", json=payload)
        assert r.status_code == 401, r.text

    r = await client.post("/v1/auth/login", json=payload)
    assert r.status_code == 429
    assert r.json() == {"error": "rate_limited"}
    assert r.headers.get("Retry-After") == "60"


async def test_login_rate_limit_blocks_good_password_too(
    client: AsyncClient,
    session_user_fixture: SessionUserFixture,
) -> None:
    """Rate limit fires *before* the password check, so even a correct
    password is rejected once the bucket is full. That's the property
    that keeps argon2 off the brute-force hot path."""
    for _ in range(5):
        r = await client.post(
            "/v1/auth/login",
            json={"email": session_user_fixture.email, "password": "nope"},
        )
        assert r.status_code == 401

    r = await client.post(
        "/v1/auth/login",
        json={
            "email": session_user_fixture.email,
            "password": session_user_fixture.password,
        },
    )
    assert r.status_code == 429
