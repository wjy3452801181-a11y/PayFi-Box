"""step10 enforce lowercase tx_hash at persistence layer

Revision ID: 20260401_000008
Revises: 20260401_000007
Create Date: 2026-04-01 23:59:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260401_000008"
down_revision: Union[str, None] = "20260401_000007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Defensive canonicalization before adding lowercase check.
    op.execute("UPDATE payment_execution_items SET tx_hash = lower(tx_hash) WHERE tx_hash IS NOT NULL")
    op.create_check_constraint(
        "ck_pei_tx_hash_lowercase",
        "payment_execution_items",
        "tx_hash IS NULL OR tx_hash = lower(tx_hash)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_pei_tx_hash_lowercase", "payment_execution_items", type_="check")
