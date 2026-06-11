"""Request and response schemas for /v1/auth endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from api.schemas._base import _Strict

# Best-effort syntactic check: ``<local>@<host>.<tld>``. Catches typos
# and stray whitespace without taking on the ``email-validator`` dep;
# the DB still enforces case-folded uniqueness, which is what actually
# matters.
_EMAIL_PATTERN = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"

_EmailField = Annotated[
    str,
    StringConstraints(pattern=_EMAIL_PATTERN, min_length=3, max_length=320),
]


class RegisterRequest(_Strict):
    email: _EmailField
    password: str = Field(min_length=8, max_length=256)
    name: str | None = Field(default=None, max_length=255)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v


class LoginRequest(_Strict):
    email: _EmailField
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class SessionTokenResponse(_Strict):
    """Returned by ``register`` and ``login`` — same shape so the
    frontend can use one code path for both."""

    token: str
    expires_at: datetime


class OrgRef(_Strict):
    id: UUID
    name: str
    slug: str
    role: str


class MeResponse(_Strict):
    user_id: UUID
    email: str
    name: str | None
    orgs: list[OrgRef]
