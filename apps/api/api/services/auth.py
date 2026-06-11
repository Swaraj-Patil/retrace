"""User-account business logic: register, login, session lifecycle.

The router layer (``api.routers.auth``) is thin; everything that needs
a transaction or talks to the security helpers lives here.
"""

from __future__ import annotations

import secrets as stdlib_secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Membership, MembershipRole, Org, Project, User, UserSession
from api.security import (
    generate_session_token,
    hash_password,
    verify_password,
)
from api.security.sessions import SESSION_TTL

_DEFAULT_PROJECT_NAME = "Default Project"
_DEFAULT_PROJECT_SLUG = "default"
_SLUG_RETRY_ATTEMPTS = 5


class EmailAlreadyRegistered(Exception):
    """Raised when the email already has a user row."""


class OrgSlugCollision(Exception):
    """Raised when every slug attempt collides. Should be virtually impossible."""


@dataclass(frozen=True)
class IssuedSession:
    raw_token: str
    expires_at: datetime


@dataclass(frozen=True)
class RegisteredUser:
    user_id: UUID
    org_id: UUID
    project_id: UUID
    session: IssuedSession


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    name: str | None,
) -> RegisteredUser:
    """Bootstrap a user in a single transaction.

    Creates the user, an org named ``"<local>'s Workspace"``, an owner
    membership, and a "Default Project". Org slug derives from the
    email local-part; up to 5 retries with a random suffix on collision.
    Returns a fresh session token so the caller lands authenticated in
    one step.
    """
    normalized_email = email.strip().lower()

    existing = (
        await db.execute(select(User.id).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyRegistered

    local = normalized_email.split("@", 1)[0]
    user = User(
        email=normalized_email,
        name=name,
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.flush()

    org = await _create_org_with_slug_retry(
        db,
        name=f"{local}'s Workspace",
        base_slug=_slugify(local) or "workspace",
    )

    db.add(Membership(org_id=org.id, user_id=user.id, role=MembershipRole.OWNER))
    project = Project(
        org_id=org.id,
        name=_DEFAULT_PROJECT_NAME,
        slug=_DEFAULT_PROJECT_SLUG,
    )
    db.add(project)
    await db.flush()

    issued = _generate_session_row(user_id=user.id)
    db.add(issued.row)
    await db.commit()

    return RegisteredUser(
        user_id=user.id,
        org_id=org.id,
        project_id=project.id,
        session=IssuedSession(raw_token=issued.raw_token, expires_at=issued.row.expires_at),
    )


async def authenticate_user(
    db: AsyncSession, *, email: str, password: str
) -> User | None:
    """Look up the user by lowercase email and verify the password.

    Returns the user on success, ``None`` on any failure (unknown email,
    wrong password, or user with no ``hashed_password``). The caller is
    responsible for translating ``None`` into a uniform 401.
    """
    normalized_email = email.strip().lower()
    user = (
        await db.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if user is None or user.hashed_password is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def issue_session(db: AsyncSession, *, user_id: UUID) -> IssuedSession:
    """Create and persist a new session for ``user_id``."""
    issued = _generate_session_row(user_id=user_id)
    db.add(issued.row)
    await db.commit()
    return IssuedSession(raw_token=issued.raw_token, expires_at=issued.row.expires_at)


async def revoke_session(db: AsyncSession, *, session_id: UUID) -> None:
    """Soft-delete the session by stamping ``revoked_at``.

    Idempotency falls out: a second logout with the same token never
    re-enters this function because the auth dependency would already
    have raised 401 on the stale token.
    """
    session = (
        await db.execute(select(UserSession).where(UserSession.id == session_id))
    ).scalar_one_or_none()
    if session is None:
        return
    session.revoked_at = datetime.now(UTC)
    await db.commit()


@dataclass
class _GeneratedSessionRow:
    raw_token: str
    row: UserSession


def _generate_session_row(*, user_id: UUID) -> _GeneratedSessionRow:
    token = generate_session_token()
    expires_at = datetime.now(UTC) + SESSION_TTL
    row = UserSession(
        user_id=user_id,
        token_prefix=token.prefix,
        hashed_token=token.hashed,
        expires_at=expires_at,
    )
    return _GeneratedSessionRow(raw_token=token.raw, row=row)


async def _create_org_with_slug_retry(
    db: AsyncSession, *, name: str, base_slug: str
) -> Org:
    """Insert an Org, retrying with a fresh random suffix on slug collision.

    Each attempt opens a savepoint so the outer registration transaction
    survives a collision. Five attempts is wildly more than needed —
    base_slug + 16 bits of suffix entropy makes a single collision
    astronomically unlikely; five attempts means a chained collision
    would have to happen against half a billion existing rows, which is
    several orders of magnitude beyond what Phase A will ever see.
    """
    slug = base_slug
    for attempt in range(_SLUG_RETRY_ATTEMPTS):
        try:
            async with db.begin_nested():
                org = Org(name=name, slug=slug)
                db.add(org)
                await db.flush()
            return org
        except IntegrityError:
            slug = f"{base_slug}-{stdlib_secrets.token_hex(2)}"
            if attempt == _SLUG_RETRY_ATTEMPTS - 1:
                raise OrgSlugCollision from None
    raise OrgSlugCollision  # pragma: no cover - the loop always returns or raises


def _slugify(s: str) -> str:
    """Lowercase + ASCII-alnum + single dashes. Returns ``""`` if no chars survive."""
    out: list[str] = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")[:50]
