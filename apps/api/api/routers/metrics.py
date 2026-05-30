"""Dashboard metrics endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.clickhouse.client import get_client
from api.dependencies.auth import ProjectContext, get_current_project
from api.schemas.read import MetricsOverviewResponse
from api.services.read import metrics_overview

router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get("/metrics/overview", response_model=MetricsOverviewResponse)
async def metrics_overview_endpoint(
    ctx: Annotated[ProjectContext, Depends(get_current_project)],
    start_from: Annotated[datetime | None, Query(alias="from")] = None,
    start_to: Annotated[datetime | None, Query(alias="to")] = None,
) -> MetricsOverviewResponse:
    ch = get_client()
    payload = await metrics_overview(
        ch,
        project_id=ctx.project_id,
        start_from=start_from,
        start_to=start_to,
    )
    return MetricsOverviewResponse(**payload)  # type: ignore[arg-type]
