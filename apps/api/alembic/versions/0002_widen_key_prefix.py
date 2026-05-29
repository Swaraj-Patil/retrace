"""widen api_keys.key_prefix to 11 chars

Revision ID: 0002_widen_key_prefix
Revises: 0001_initial
Create Date: 2026-05-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_widen_key_prefix"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "api_keys",
        "key_prefix",
        existing_type=sa.String(length=8),
        type_=sa.String(length=11),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Downgrade truncates any existing prefix to 8 chars to fit the old column.
    # Existing keys become unverifiable on the old code path, which is the
    # expected cost of rolling back this change.
    op.execute(
        "UPDATE api_keys SET key_prefix = LEFT(key_prefix, 8) WHERE LENGTH(key_prefix) > 8"
    )
    op.alter_column(
        "api_keys",
        "key_prefix",
        existing_type=sa.String(length=11),
        type_=sa.String(length=8),
        existing_nullable=False,
    )
