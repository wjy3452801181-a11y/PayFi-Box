"""step13 access credentials

Revision ID: 20260409_000012
Revises: 20260406_000011
Create Date: 2026-04-09 13:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260409_000012"
down_revision: Union[str, None] = "20260406_000011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_access_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False, server_default="primary"),
        sa.Column("access_code_hash", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_access_credentials_user_id"),
    )
    op.create_index(op.f("ix_user_access_credentials_user_id"), "user_access_credentials", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_access_credentials_is_active"), "user_access_credentials", ["is_active"], unique=False)
    op.create_index(op.f("ix_user_access_credentials_created_at"), "user_access_credentials", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_access_credentials_created_at"), table_name="user_access_credentials")
    op.drop_index(op.f("ix_user_access_credentials_is_active"), table_name="user_access_credentials")
    op.drop_index(op.f("ix_user_access_credentials_user_id"), table_name="user_access_credentials")
    op.drop_table("user_access_credentials")
