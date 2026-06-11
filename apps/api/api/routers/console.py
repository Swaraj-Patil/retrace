"""Console endpoints: project listing/creation and API-key management.

Session-only (``get_current_user``). Per-project endpoints additionally
require the caller to be a member of the project's org
(``get_user_authorized_project_context``); failure is 404, identical
to "doesn't exist" so cross-org enumeration is impossible.

API keys are the only credential that can write telemetry; the keys
themselves are managed only from here, never from the SDK. A browser
session creates them; the raw token is shown exactly once at creation;
revocation soft-deletes via ``revoked_at`` so audit history survives.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import (
    ProjectContext,
    UserActor,
    get_current_user,
    get_db,
    get_user_authorized_project_context,
)
from api.schemas.console import (
    ApiKeyListItem,
    ApiKeyListResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    CreateProjectRequest,
    CreateProjectResponse,
    ProjectListItem,
    ProjectListResponse,
)
from api.services.console import (
    create_api_key_for_project,
    create_project_for_user,
    list_api_keys_for_project,
    list_projects_for_user,
    revoke_api_key_for_project,
)

router = APIRouter(prefix="/v1/console", tags=["console"])


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    actor: Annotated[UserActor, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectListResponse:
    rows = await list_projects_for_user(db, user_id=actor.user_id)
    return ProjectListResponse(
        projects=[
            ProjectListItem(
                id=row.project.id,
                name=row.project.name,
                slug=row.project.slug,
                org_id=row.org.id,
                org_name=row.org.name,
                role=row.role.value,
                created_at=row.project.created_at,
            )
            for row in rows
        ]
    )


@router.post(
    "/projects",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateProjectResponse,
)
async def create_project(
    body: CreateProjectRequest,
    actor: Annotated[UserActor, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateProjectResponse:
    project = await create_project_for_user(
        db,
        user_id=actor.user_id,
        name=body.name,
        slug=body.slug,
    )
    return CreateProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        org_id=project.org_id,
        created_at=project.created_at,
    )


@router.get(
    "/projects/{project_id}/keys",
    response_model=ApiKeyListResponse,
)
async def list_keys(
    ctx: Annotated[ProjectContext, Depends(get_user_authorized_project_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyListResponse:
    keys = await list_api_keys_for_project(db, project_id=ctx.project_id)
    return ApiKeyListResponse(
        keys=[
            ApiKeyListItem(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                last_used_at=k.last_used_at,
                revoked_at=k.revoked_at,
                created_at=k.created_at,
            )
            for k in keys
        ]
    )


@router.post(
    "/projects/{project_id}/keys",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateApiKeyResponse,
)
async def create_key(
    body: CreateApiKeyRequest,
    ctx: Annotated[ProjectContext, Depends(get_user_authorized_project_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateApiKeyResponse:
    key, raw = await create_api_key_for_project(
        db, project_id=ctx.project_id, name=body.name
    )
    return CreateApiKeyResponse(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        raw_key=raw,
        created_at=key.created_at,
    )


@router.delete(
    "/projects/{project_id}/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_key(
    key_id: UUID,
    ctx: Annotated[ProjectContext, Depends(get_user_authorized_project_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await revoke_api_key_for_project(db, project_id=ctx.project_id, key_id=key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
