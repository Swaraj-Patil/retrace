"""Org membership model (joins users to orgs with a role)."""

import enum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.models._mixins import Timestamps


class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Membership(Timestamps, Base):
    __tablename__ = "memberships"

    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(
            MembershipRole,
            name="membership_role",
            native_enum=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
