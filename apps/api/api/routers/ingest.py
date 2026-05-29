"""``POST /v1/ingest`` - unified batch ingestion endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.clickhouse.client import get_client
from api.dependencies.auth import ProjectContext, get_current_project
from api.schemas.ingest import InsertedCounts, IngestRequest, IngestResponse
from api.services.ingest import (
    BatchTooLarge,
    total_items,
    validate_fk_closure,
    write_batch,
)

router = APIRouter(prefix="/v1", tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    body: IngestRequest,
    ctx: Annotated[ProjectContext, Depends(get_current_project)],
) -> IngestResponse:
    if total_items(body) > 1000:
        raise BatchTooLarge

    ch_client = get_client()
    await validate_fk_closure(body, ctx.project_id, ch_client)
    counts = await write_batch(body, ctx.project_id, ch_client)

    return IngestResponse(
        inserted=InsertedCounts(**counts),
        project_id=ctx.project_id,
    )
