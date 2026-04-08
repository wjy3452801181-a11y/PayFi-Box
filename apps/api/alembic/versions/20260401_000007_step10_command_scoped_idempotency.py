"""step10 command-scoped idempotency for execution batches

Revision ID: 20260401_000007
Revises: 20260401_000006
Create Date: 2026-04-01 23:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260401_000007"
down_revision: Union[str, None] = "20260401_000006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_execution_batches",
        sa.Column("source_command_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_payment_execution_batches_source_command_id"),
        "payment_execution_batches",
        ["source_command_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_peb_source_command_id",
        "payment_execution_batches",
        "command_executions",
        ["source_command_id"],
        ["id"],
    )

    op.execute(
        """
        UPDATE payment_execution_batches b
        SET source_command_id = p.source_command_id
        FROM payment_orders p
        WHERE p.id = b.payment_order_id
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM payment_execution_batches
                WHERE source_command_id IS NULL
            ) THEN
                RAISE EXCEPTION 'source_command_id backfill failed for payment_execution_batches';
            END IF;
        END $$;
        """
    )
    op.alter_column("payment_execution_batches", "source_command_id", nullable=False)

    op.drop_constraint(
        "uq_payment_execution_batches_idempotency_key",
        "payment_execution_batches",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_payment_execution_batches_idempotency_key"),
        table_name="payment_execution_batches",
    )
    op.create_index(
        op.f("ix_payment_execution_batches_idempotency_key"),
        "payment_execution_batches",
        ["idempotency_key"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_payment_execution_batches_command_idempotency",
        "payment_execution_batches",
        ["source_command_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_payment_execution_batches_command_idempotency",
        "payment_execution_batches",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_payment_execution_batches_idempotency_key"),
        table_name="payment_execution_batches",
    )
    op.create_index(
        op.f("ix_payment_execution_batches_idempotency_key"),
        "payment_execution_batches",
        ["idempotency_key"],
        unique=True,
    )
    op.create_unique_constraint(
        "uq_payment_execution_batches_idempotency_key",
        "payment_execution_batches",
        ["idempotency_key"],
    )

    op.drop_constraint(
        "fk_peb_source_command_id",
        "payment_execution_batches",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_payment_execution_batches_source_command_id"),
        table_name="payment_execution_batches",
    )
    op.drop_column("payment_execution_batches", "source_command_id")
