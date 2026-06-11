"""User model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.models._mixins import Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Nullable so pre-alpha seed/fixture rows without a password don't
    # block the migration. Login treats ``NULL`` as ``invalid_credentials``
    # (same uniform 401 as a wrong password).
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
