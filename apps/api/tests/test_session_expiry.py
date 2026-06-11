"""Tests for time-based session expiry.

The session-token validator joins on ``expires_at > func.now()``, so a
session row whose ``expires_at`` is in the past must yield the uniform
``invalid_credentials`` 401 even though the token hash still verifies
and the row is not ``revoked_at``-stamped. This closes the last auth
path: revocation (action-based) was covered by the logout tests;
expiry (time-based) is covered here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import delete

from api.db.session import SessionLocal
from api.models import User, UserSession
from api.security import generate_session_token, hash_password


async def test_expired_session_token_returns_401(client: AsyncClient) -> None:
    """Insert a fresh user with a session that already expired and
    confirm the auth dependency rejects the token uniformly. Token is
    well-formed and hash-verifies; only ``expires_at`` makes it invalid."""
    email = f"expired-{uuid4().hex}@retrace.test"
    token = generate_session_token()

    async with SessionLocal() as session:
        user = User(
            email=email,
            name="Expired",
            hashed_password=hash_password("doesnt-matter-1234"),
        )
        session.add(user)
        await session.flush()

        session.add(
            UserSession(
                user_id=user.id,
                token_prefix=token.prefix,
                hashed_token=token.hashed,
                # One day in the past: the row is otherwise valid (not
                # revoked, hash matches), so a 401 here can only come
                # from the ``expires_at > now()`` clause.
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await session.commit()
        user_id = user.id

    try:
        r = await client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {token.raw}"},
        )
        assert r.status_code == 401
        assert r.json() == {"error": "invalid_credentials"}
    finally:
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
