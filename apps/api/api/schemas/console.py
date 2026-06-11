"""Request and response schemas for /v1/console endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from api.schemas._base import _Strict

# Lowercase alnum runs separated by single hyphens. Matches the slug
# style used by ``orgs.slug`` / ``projects.slug`` in the existing seed
# and integration fixtures (e.g., ``demo-project``). Max 63 matches
# the column width.
_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

_SlugField = Annotated[
    str,
    StringConstraints(pattern=_SLUG_PATTERN, min_length=1, max_length=63),
]


def _slugify(s: str) -> str:
    """Lowercase + ASCII-alnum + single dashes. Returns ``""`` when no
    ASCII alphanumerics survive (e.g., a punctuation- or emoji-only
    input)."""
    out: list[str] = []
    for ch in s.lower():
        if ch.isalnum() and ch.isascii():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")[:63]


class ProjectListItem(_Strict):
    id: UUID
    name: str
    slug: str
    org_id: UUID
    org_name: str
    role: str
    created_at: datetime


class ProjectListResponse(_Strict):
    projects: list[ProjectListItem]


class CreateProjectRequest(_Strict):
    name: str = Field(min_length=1, max_length=255)
    slug: _SlugField | None = Field(default=None)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def _derive_slug_or_reject(self) -> CreateProjectRequest:
        # When no explicit slug is given, derive one from the name. If
        # the name has no ASCII alphanumerics (e.g., "!!!" or an emoji-
        # only string) the derivation is empty - reject with a clean
        # 422 instead of silently falling back to a generic slug, which
        # would either misrepresent the user's input or collide with
        # another such project. The router and service can then assume
        # ``self.slug`` is always a non-empty, pattern-valid slug.
        if self.slug is None:
            derived = _slugify(self.name)
            if not derived:
                raise ValueError(
                    "name does not contain ASCII alphanumerics; "
                    "provide an explicit slug"
                )
            self.slug = derived
        return self


class CreateProjectResponse(_Strict):
    id: UUID
    name: str
    slug: str
    org_id: UUID
    created_at: datetime


class ApiKeyListItem(_Strict):
    id: UUID
    name: str
    key_prefix: str
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyListResponse(_Strict):
    keys: list[ApiKeyListItem]


class CreateApiKeyRequest(_Strict):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class CreateApiKeyResponse(_Strict):
    """Returned exactly once at creation time. ``raw_key`` never appears
    in any other endpoint - the user must save it now or revoke and
    regenerate."""

    id: UUID
    name: str
    key_prefix: str
    raw_key: str
    created_at: datetime
