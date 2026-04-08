"""step9 tx hash canonicalization and case-insensitive uniqueness

Revision ID: 20260401_000006
Revises: 20260401_000005
Create Date: 2026-04-01 22:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260401_000006"
down_revision: Union[str, None] = "20260401_000005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old case-sensitive unique index first, otherwise lower(tx_hash) can violate it.
    op.drop_index("uq_payment_execution_items_tx_hash_not_null", table_name="payment_execution_items")

    # Canonicalize existing tx hashes to lowercase across payment tables.
    op.execute("UPDATE payment_execution_items SET tx_hash = lower(tx_hash) WHERE tx_hash IS NOT NULL")
    op.execute("UPDATE payment_splits SET tx_hash = lower(tx_hash) WHERE tx_hash IS NOT NULL")
    op.execute("UPDATE payment_orders SET tx_hash = lower(tx_hash) WHERE tx_hash IS NOT NULL")

    # Guard against pre-existing case-variant duplicates before applying CI unique index.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY lower(tx_hash)
                    ORDER BY created_at ASC, id ASC
                ) AS rn
            FROM payment_execution_items
            WHERE tx_hash IS NOT NULL
        )
        UPDATE payment_execution_items pei
        SET
            tx_hash = NULL,
            explorer_url = NULL,
            failure_reason = COALESCE(pei.failure_reason || '; ', '') || 'tx_hash_canonicalized_duplicate_cleared'
        FROM ranked r
        WHERE pei.id = r.id
          AND r.rn > 1
        """
    )

    op.create_index(
        "uq_payment_execution_items_tx_hash_ci_not_null",
        "payment_execution_items",
        [sa.text("lower(tx_hash)")],
        unique=True,
        postgresql_where=sa.text("tx_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_payment_execution_items_tx_hash_ci_not_null", table_name="payment_execution_items")
    op.create_index(
        "uq_payment_execution_items_tx_hash_not_null",
        "payment_execution_items",
        ["tx_hash"],
        unique=True,
        postgresql_where=sa.text("tx_hash IS NOT NULL"),
    )
