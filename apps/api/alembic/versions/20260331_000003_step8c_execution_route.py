"""step8c execution route for confirm modes

Revision ID: 20260331_000003
Revises: 20260330_000002
Create Date: 2026-03-31 09:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260331_000003"
down_revision: Union[str, None] = "20260330_000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_orders",
        sa.Column(
            "execution_route",
            sa.String(length=32),
            nullable=False,
            server_default="operator",
        ),
    )
    op.create_index(
        op.f("ix_payment_orders_execution_route"),
        "payment_orders",
        ["execution_route"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_orders_execution_route"), table_name="payment_orders")
    op.drop_column("payment_orders", "execution_route")
