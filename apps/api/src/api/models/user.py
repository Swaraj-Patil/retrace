"""User model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.models._mixins import Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
