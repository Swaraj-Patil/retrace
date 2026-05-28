"""API key model (one project can have many keys)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.models._mixins import Timestamps, UUIDPrimaryKey


class ApiKey(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "api_keys"

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # First 8 chars of the raw key, kept plaintext for O(1) lookup before
    # hash verification. Indexed unique so collisions raise loudly.
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False, unique=True, index=True)
    hashed_key: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
