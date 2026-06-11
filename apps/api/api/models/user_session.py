"""User session model (opaque server-side token, hashed at rest).

Parallel to ``ApiKey`` in shape: a unique ``token_prefix`` (the first
11 chars of ``rts_<random>``) is kept plaintext for O(1) lookup; the
full token is argon2-hashed into ``hashed_token`` for verification.
Logout soft-deletes via ``revoked_at`` rather than deleting the row,
so the auth path can keep raising the uniform ``invalid_credentials``
401 on a stale token.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.models._mixins import Timestamps, UUIDPrimaryKey


class UserSession(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_prefix: Mapped[str] = mapped_column(
        String(11), nullable=False, unique=True, index=True
    )
    hashed_token: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
