"""Project response schemas."""

from __future__ import annotations

from uuid import UUID

from api.schemas._base import _Strict


class ProjectMeResponse(_Strict):
    project_id: UUID
    project_name: str
    org_id: UUID
    org_name: str
