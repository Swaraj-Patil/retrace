"""Bearer-token authentication dependencies.

Two token kinds, both validated by prefix-index then argon2 verify:

* **API keys** (``rt_…``) — machine-to-machine, project-scoped. Issued
  per project; used by the SDK and ingest.
* **User sessions** (``rts_…``) — opaque, server-side, hashed at rest.
  Issued on register/login; used by the console and read endpoints.

The bearer prefix routes to the right validator, so a single
``Authorization: Bearer …`` header carries either kind. Failures
collapse to ``Unauthorized`` -> ``401 invalid_credentials`` so callers
cannot distinguish "unknown key" from "wrong hash" from "revoked"
from "expired session".

Three dependencies expose the two modes with the right shape:

* :func:`get_current_project` — API-key only. Sessions are rejected
  with 401. Use for ingest and any read endpoint where the project is
  implicit in the credential and a browser session must never reach.
* :func:`get_current_project_any_auth` — either mode. On the session
  branch ``?project_id=`` is required (400 ``project_id_required``)
  and must belong to one of the user's orgs (404 ``project_not_found``
  otherwise, to avoid cross-org enumeration). The API-key branch
  ignores ``project_id`` so existing demo callers do not change.
* :func:`get_current_user` — session only. API keys are rejected
  with 401. Use for /v1/auth and console endpoints (account
  management is a human action and must not be reachable from an SDK
  credential).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import SessionLocal
from api.models import ApiKey, Membership, Project, UserSession
from api.security import (
    KEY_PREFIX_LEN,
    SESSION_TOKEN_NAMESPACE,
    SESSION_TOKEN_PREFIX_LEN,
    verify_api_key,
    verify_session_token,
)

_BEARER_PREFIX = "Bearer "
_API_KEY_NAMESPACE = "rt_"

_logger = structlog.get_logger("retrace.api.auth")


class Unauthorized(Exception):
    """Raised on any authentication failure.

    The exception handler in ``api.main`` renders this as a uniform
    401 response. Do not subclass to add stage-specific variants - the
    point is that callers cannot tell which step failed.
    """


class ProjectIdRequired(Exception):
    """Session caller hit a read endpoint without ``?project_id=…``.

    Auth succeeded; the request is just incomplete for the session
    branch. Rendered as ``400 project_id_required`` by the handler in
    ``api.main``.
    """


class ProjectNotFound(Exception):
    """Project does not exist OR the caller is not a member of its org.

    Uniform 404 so cross-org access cannot be distinguished from a
    typo. Consistent with the existing 404 used for unknown traces.
    """


@dataclass(frozen=True)
class ProjectContext:
    project_id: UUID
    project_name: str
    org_id: UUID


@dataclass(frozen=True)
class UserActor:
    user_id: UUID
    session_id: UUID


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def _extract_bearer(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith(_BEARER_PREFIX):
        raise Unauthorized
    return auth_header[len(_BEARER_PREFIX) :].strip()


async def _resolve_api_key(raw_token: str, db: AsyncSession) -> ProjectContext:
    """Validate an ``rt_`` token. Caller has already confirmed the prefix."""
    if len(raw_token) < KEY_PREFIX_LEN:
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


async def _resolve_session(raw_token: str, db: AsyncSession) -> UserActor:
    """Validate an ``rts_`` token. Caller has already confirmed the prefix."""
    if len(raw_token) < SESSION_TOKEN_PREFIX_LEN:
        raise Unauthorized

    lookup_prefix = raw_token[:SESSION_TOKEN_PREFIX_LEN]
    stmt = select(UserSession).where(
        UserSession.token_prefix == lookup_prefix,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > func.now(),
    )
    session_row = (await db.execute(stmt)).scalar_one_or_none()
    if session_row is None:
        raise Unauthorized

    if not verify_session_token(raw_token, session_row.hashed_token):
        raise Unauthorized

    return UserActor(user_id=session_row.user_id, session_id=session_row.id)


async def _project_context_for_user(
    user_id: UUID, project_id: UUID, db: AsyncSession
) -> ProjectContext:
    """Resolve ``project_id`` against the user's memberships.

    Returns the matching project or raises :class:`ProjectNotFound`.
    "Doesn't exist" and "exists in another org" are deliberately
    indistinguishable.
    """
    stmt = (
        select(Project)
        .join(Membership, Membership.org_id == Project.org_id)
        .where(Project.id == project_id, Membership.user_id == user_id)
    )
    project = (await db.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise ProjectNotFound
    return ProjectContext(
        project_id=project.id,
        project_name=project.name,
        org_id=project.org_id,
    )


async def get_current_project(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectContext:
    """API-key only. Sessions are rejected with 401.

    Used by ingest and ``/v1/projects/me`` — the write path and the
    project-introspection endpoint are machine-only. A browser session
    cannot use these.
    """
    raw_token = _extract_bearer(request)
    # ``rts_`` startswith ``rt_``, so the session-namespace check has
    # to come first to reject sessions explicitly.
    if raw_token.startswith(SESSION_TOKEN_NAMESPACE):
        raise Unauthorized
    if not raw_token.startswith(_API_KEY_NAMESPACE):
        raise Unauthorized
    return await _resolve_api_key(raw_token, db)


async def get_current_project_any_auth(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    project_id: Annotated[UUID | None, Query()] = None,
) -> ProjectContext:
    """API key or user session. Used by read endpoints (traces, metrics).

    * **API-key branch**: ``project_id`` is ignored. The demo's
      existing read calls (no ``?project_id``) keep working unchanged.
    * **Session branch**: ``project_id`` is required (400) and must
      belong to one of the user's orgs (404 otherwise).
    """
    raw_token = _extract_bearer(request)
    if raw_token.startswith(SESSION_TOKEN_NAMESPACE):
        actor = await _resolve_session(raw_token, db)
        if project_id is None:
            raise ProjectIdRequired
        return await _project_context_for_user(actor.user_id, project_id, db)
    if not raw_token.startswith(_API_KEY_NAMESPACE):
        raise Unauthorized
    return await _resolve_api_key(raw_token, db)


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserActor:
    """Session only. API keys are rejected with 401.

    Used by ``/v1/auth/{logout,me}`` and (in Commit 2) the console
    endpoints — account management is a human action and must not be
    reachable from an SDK credential.
    """
    raw_token = _extract_bearer(request)
    if not raw_token.startswith(SESSION_TOKEN_NAMESPACE):
        raise Unauthorized
    return await _resolve_session(raw_token, db)


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
