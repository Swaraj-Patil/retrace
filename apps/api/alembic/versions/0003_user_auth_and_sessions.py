"""user passwords and opaque server-side sessions

Revision ID: 0003_user_auth_and_sessions
Revises: 0002_widen_key_prefix
Create Date: 2026-06-11

Adds the column and table needed for user-session auth alongside the
existing API-key auth:

* ``users.hashed_password`` (nullable): argon2 hash. Nullable so the
  migration is safe against pre-alpha seed rows that have no password;
  the application treats a ``NULL`` hash as ``invalid_credentials`` on
  login (same uniform 401 as a wrong password, no enumeration).
* ``user_sessions``: opaque ``rts_`` tokens, prefix-indexed for O(1)
  lookup and argon2-hashed at rest, mirroring the ``api_keys`` table.
  ``ON DELETE CASCADE`` from ``users`` so deleting a user wipes their
  sessions; ``revoked_at`` is soft-delete (logout sets ``revoked_at``;
  the row is kept for audit).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_user_auth_and_sessions"
down_revision: str | None = "0002_widen_key_prefix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_prefix", sa.String(length=11), nullable=False),
        sa.Column("hashed_token", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("token_prefix", name="uq_user_sessions_token_prefix"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_token_prefix", "user_sessions", ["token_prefix"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_token_prefix", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_column("users", "hashed_password")
