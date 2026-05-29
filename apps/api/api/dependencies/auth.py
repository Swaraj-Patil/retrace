"""Bearer-token authentication dependency.

Pulls the API key out of ``Authorization: Bearer rt_...``, looks it up by
the first ``KEY_PREFIX_LEN`` chars (indexed), argon2-verifies the full
token against the stored hash, then loads the project + org and returns
a small ``ProjectContext`` to the endpoint. Any failure raises
``Unauthorized``, which the global exception handler renders as
``401 {"error": "invalid_credentials"}`` - the failure mode is
intentionally uniform so callers cannot distinguish "unknown key" from
"wrong key" from "revoked".

Successful auth also schedules a fire-and-forget update of
``last_used_at`` so request latency does not pay for the write.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import SessionLocal
from api.models import ApiKey, Project
from api.security import KEY_PREFIX_LEN, verify_api_key

_BEARER_PREFIX = "Bearer "
_KEY_NAMESPACE = "rt_"

_logger = structlog.get_logger("retrace.api.auth")


class Unauthorized(Exception):
    """Raised on any authentication failure.

    The exception handler in ``api.main`` renders this as a uniform
    401 response. Do not subclass to add stage-specific variants - the
    point is that callers cannot tell which step failed.
    """


@dataclass(frozen=True)
class ProjectContext:
    project_id: UUID
    project_name: str
    org_id: UUID


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def get_current_project(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectContext:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith(_BEARER_PREFIX):
        raise Unauthorized

    raw_token = auth_header[len(_BEARER_PREFIX) :].strip()
    if not raw_token.startswith(_KEY_NAMESPACE) or len(raw_token) < KEY_PREFIX_LEN:
        raise Unauthorized

    lookup_prefix = raw_token[:KEY_PREFIX_LEN]

    stmt = (
        select(ApiKey, Project)
        .join(Project, Project.id == ApiKey.project_id)
        .where(ApiKey.key_prefix == lookup_prefix, ApiKey.revoked_at.is_(None))
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise Unauthorized

    api_key, project = row
    if not verify_api_key(raw_token, api_key.hashed_key):
        raise Unauthorized

    asyncio.create_task(_update_last_used(api_key.id))

    return ProjectContext(
        project_id=project.id,
        project_name=project.name,
        org_id=project.org_id,
    )


async def _update_last_used(api_key_id: UUID) -> None:
    """Best-effort bump of ``last_used_at``. Never raises into the caller."""
    try:
        async with SessionLocal() as session:
            await session.execute(
                update(ApiKey).where(ApiKey.id == api_key_id).values(last_used_at=func.now())
            )
            await session.commit()
    except Exception as exc:
        _logger.warning(
            "auth.last_used_update_failed",
            api_key_id=str(api_key_id),
            error=repr(exc),
        )
