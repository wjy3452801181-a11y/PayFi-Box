"""step8d durable execution models and constraints

Revision ID: 20260331_000004
Revises: 20260331_000003
Create Date: 2026-03-31 22:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260331_000004"
down_revision: Union[str, None] = "20260331_000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                source_command_id,
                ROW_NUMBER() OVER (
                    PARTITION BY source_command_id
                    ORDER BY created_at ASC, id ASC
                ) AS rn
            FROM payment_orders
            WHERE source_command_id IS NOT NULL
        )
        UPDATE payment_orders po
        SET source_command_id = NULL
        FROM ranked r
        WHERE po.id = r.id
          AND r.rn > 1
        """
    )

    op.drop_index(op.f("ix_payment_orders_source_command_id"), table_name="payment_orders")
    op.create_index(
        "uq_payment_orders_source_command_id",
        "payment_orders",
        ["source_command_id"],
        unique=True,
    )

    op.create_table(
        "payment_execution_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_execution_batches_idempotency_key"),
    )
    op.create_index(op.f("ix_payment_execution_batches_created_at"), "payment_execution_batches", ["created_at"], unique=False)
    op.create_index(op.f("ix_payment_execution_batches_idempotency_key"), "payment_execution_batches", ["idempotency_key"], unique=True)
    op.create_index(op.f("ix_payment_execution_batches_payment_order_id"), "payment_execution_batches", ["payment_order_id"], unique=False)
    op.create_index(op.f("ix_payment_execution_batches_requested_by_user_id"), "payment_execution_batches", ["requested_by_user_id"], unique=False)
    op.create_index(op.f("ix_payment_execution_batches_status"), "payment_execution_batches", ["status"], unique=False)

    op.create_table(
        "payment_execution_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_split_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("beneficiary_address", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tx_hash", sa.String(length=80), nullable=True),
        sa.Column("explorer_url", sa.String(length=255), nullable=True),
        sa.Column("nonce", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("receipt_json", sa.JSON(), nullable=True),
        sa.Column("onchain_status", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["execution_batch_id"], ["payment_execution_batches.id"]),
        sa.ForeignKeyConstraint(["payment_split_id"], ["payment_splits.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_batch_id", "sequence", name="uq_payment_execution_items_batch_sequence"),
    )
    op.create_index(op.f("ix_payment_execution_items_confirmed_at"), "payment_execution_items", ["confirmed_at"], unique=False)
    op.create_index(op.f("ix_payment_execution_items_created_at"), "payment_execution_items", ["created_at"], unique=False)
    op.create_index(op.f("ix_payment_execution_items_execution_batch_id"), "payment_execution_items", ["execution_batch_id"], unique=False)
    op.create_index(op.f("ix_payment_execution_items_onchain_status"), "payment_execution_items", ["onchain_status"], unique=False)
    op.create_index(op.f("ix_payment_execution_items_payment_split_id"), "payment_execution_items", ["payment_split_id"], unique=False)
    op.create_index(op.f("ix_payment_execution_items_status"), "payment_execution_items", ["status"], unique=False)
    op.create_index(op.f("ix_payment_execution_items_tx_hash"), "payment_execution_items", ["tx_hash"], unique=False)
    op.create_index(
        "uq_payment_execution_items_tx_hash_not_null",
        "payment_execution_items",
        ["tx_hash"],
        unique=True,
        postgresql_where=sa.text("tx_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_payment_execution_items_tx_hash_not_null", table_name="payment_execution_items")
    op.drop_index(op.f("ix_payment_execution_items_tx_hash"), table_name="payment_execution_items")
    op.drop_index(op.f("ix_payment_execution_items_status"), table_name="payment_execution_items")
    op.drop_index(op.f("ix_payment_execution_items_payment_split_id"), table_name="payment_execution_items")
    op.drop_index(op.f("ix_payment_execution_items_onchain_status"), table_name="payment_execution_items")
    op.drop_index(op.f("ix_payment_execution_items_execution_batch_id"), table_name="payment_execution_items")
    op.drop_index(op.f("ix_payment_execution_items_created_at"), table_name="payment_execution_items")
    op.drop_index(op.f("ix_payment_execution_items_confirmed_at"), table_name="payment_execution_items")
    op.drop_table("payment_execution_items")

    op.drop_index(op.f("ix_payment_execution_batches_status"), table_name="payment_execution_batches")
    op.drop_index(op.f("ix_payment_execution_batches_requested_by_user_id"), table_name="payment_execution_batches")
    op.drop_index(op.f("ix_payment_execution_batches_payment_order_id"), table_name="payment_execution_batches")
    op.drop_index(op.f("ix_payment_execution_batches_idempotency_key"), table_name="payment_execution_batches")
    op.drop_index(op.f("ix_payment_execution_batches_created_at"), table_name="payment_execution_batches")
    op.drop_table("payment_execution_batches")

    op.drop_index("uq_payment_orders_source_command_id", table_name="payment_orders")
    op.create_index(op.f("ix_payment_orders_source_command_id"), "payment_orders", ["source_command_id"], unique=False)
