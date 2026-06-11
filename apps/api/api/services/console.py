"""Console business logic: project listing/creation and API-key management.

All operations assume the caller has already been resolved to a user
or a (user, project) pair by the dependency layer; this module does
not check membership. The router wires the right dependency for each
endpoint.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import ApiKey, Membership, MembershipRole, Org, Project
from api.security import generate_api_key


class ProjectSlugTaken(Exception):
    """Raised when the chosen slug collides within the org. 409."""


class CannotDetermineOrg(Exception):
    """User has zero or multiple org memberships and the request did
    not pin one. Defensive guard - in Phase A every registered user
    has exactly one membership, so this fires only if the invariant
    breaks (manual DB edits, future multi-org work that hasn't taught
    this endpoint yet, etc.). 400.
    """


class ApiKeyNotFound(Exception):
    """The key id doesn't exist OR belongs to a different project.

    Uniform 404 so the caller cannot use the response to discover
    that a key with that UUID exists somewhere else.
    """


@dataclass(frozen=True)
class ProjectListRow:
    project: Project
    org: Org
    role: MembershipRole


async def list_projects_for_user(
    db: AsyncSession, *, user_id: UUID
) -> list[ProjectListRow]:
    stmt = (
        select(Project, Org, Membership.role)
        .join(Org, Org.id == Project.org_id)
        .join(Membership, Membership.org_id == Org.id)
        .where(Membership.user_id == user_id)
        .order_by(Project.created_at)
    )
    rows = (await db.execute(stmt)).all()
    return [ProjectListRow(project=p, org=o, role=r) for p, o, r in rows]


async def create_project_for_user(
    db: AsyncSession, *, user_id: UUID, name: str, slug: str
) -> Project:
    # Schema is responsible for deriving and validating ``slug`` before
    # it reaches here; this layer can assume a non-empty, pattern-valid
    # value.
    org_id = await _single_org_for_user(db, user_id)
    project = Project(org_id=org_id, name=name, slug=slug)
    db.add(project)
    try:
        await db.commit()
    except IntegrityError:
        # uq_projects_org_slug. The user can pick a different slug and
        # retry - no server-side suffix retry here (unlike register's
        # org slug) because the caller has agency at console time.
        await db.rollback()
        raise ProjectSlugTaken from None
    return project


async def create_api_key_for_project(
    db: AsyncSession, *, project_id: UUID, name: str
) -> tuple[ApiKey, str]:
    """Create an API key. Return ``(row, raw_key)``. ``raw_key`` is
    the only chance to capture the full token - the row stores the
    argon2 hash and the 11-char prefix."""
    generated = generate_api_key()
    api_key = ApiKey(
        project_id=project_id,
        name=name,
        key_prefix=generated.prefix,
        hashed_key=generated.hashed,
    )
    db.add(api_key)
    await db.commit()
    return api_key, generated.raw


async def list_api_keys_for_project(
    db: AsyncSession, *, project_id: UUID
) -> Sequence[ApiKey]:
    stmt = (
        select(ApiKey)
        .where(ApiKey.project_id == project_id)
        .order_by(ApiKey.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().all()


async def revoke_api_key_for_project(
    db: AsyncSession, *, project_id: UUID, key_id: UUID
) -> None:
    """Soft-delete the key by stamping ``revoked_at`` (preserves audit
    trail). Idempotent: re-revoking a revoked key is a no-op but still
    returns successfully. Raises :class:`ApiKeyNotFound` if the id
    does not belong to this project (or does not exist at all - the
    two are deliberately indistinguishable)."""
    key = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.id == key_id, ApiKey.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if key is None:
        raise ApiKeyNotFound
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await db.commit()


async def _single_org_for_user(db: AsyncSession, user_id: UUID) -> UUID:
    org_ids = (
        await db.execute(
            select(Membership.org_id).where(Membership.user_id == user_id)
        )
    ).scalars().all()
    if len(org_ids) != 1:
        raise CannotDetermineOrg
    return org_ids[0]
