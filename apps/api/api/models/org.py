"""Organisation model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.models._mixins import Timestamps, UUIDPrimaryKey


class Org(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "orgs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True, index=True)
