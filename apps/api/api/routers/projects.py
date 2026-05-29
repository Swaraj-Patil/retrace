"""Project metadata endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import ProjectContext, get_current_project, get_db
from api.models import Org
from api.schemas.projects import ProjectMeResponse

router = APIRouter(prefix="/v1", tags=["projects"])


@router.get("/projects/me", response_model=ProjectMeResponse)
async def projects_me(
    ctx: Annotated[ProjectContext, Depends(get_current_project)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectMeResponse:
    # ProjectContext already carries project_id, project_name, and org_id
    # from the auth JOIN. org_name is the only field that needs a fetch.
    org_name = (await db.execute(select(Org.name).where(Org.id == ctx.org_id))).scalar_one()
    return ProjectMeResponse(
        project_id=ctx.project_id,
        project_name=ctx.project_name,
        org_id=ctx.org_id,
        org_name=org_name,
    )
