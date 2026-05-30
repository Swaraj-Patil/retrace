"""Read endpoints for traces."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.clickhouse.client import get_client
from api.dependencies.auth import ProjectContext, get_current_project
from api.schemas.read import TraceDetailResponse, TraceListResponse
from api.services.read import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    get_trace_detail,
    list_traces,
)


class TraceNotFound(Exception):
    """Raised when a trace_id is unknown under the authenticated project.

    Mapped to 404 by the handler in ``api.main``. Returning the same
    response for "doesn't exist" and "exists in another project"
    prevents cross-project enumeration.
    """


router = APIRouter(prefix="/v1", tags=["traces"])


@router.get("/traces", response_model=TraceListResponse)
async def list_traces_endpoint(
    ctx: Annotated[ProjectContext, Depends(get_current_project)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = DEFAULT_LIST_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    rag_only: Annotated[bool, Query()] = False,
    # ``from`` is a Python keyword; expose the query param as ``from``/``to``
    # via alias.
    start_from: Annotated[datetime | None, Query(alias="from")] = None,
    start_to: Annotated[datetime | None, Query(alias="to")] = None,
) -> TraceListResponse:
    ch = get_client()
    items, total = await list_traces(
        ch,
        project_id=ctx.project_id,
        limit=limit,
        offset=offset,
        rag_only=rag_only,
        start_from=start_from,
        start_to=start_to,
    )
    return TraceListResponse(
        traces=items,  # type: ignore[arg-type]
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace_endpoint(
    trace_id: UUID,
    ctx: Annotated[ProjectContext, Depends(get_current_project)],
) -> TraceDetailResponse:
    ch = get_client()
    detail = await get_trace_detail(ch, project_id=ctx.project_id, trace_id=trace_id)
    if detail is None:
        raise TraceNotFound
    return TraceDetailResponse(**detail)  # type: ignore[arg-type]
