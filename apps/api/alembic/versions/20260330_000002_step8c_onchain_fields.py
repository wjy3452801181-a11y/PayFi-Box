"""step8c onchain execution fields

Revision ID: 20260330_000002
Revises: 20260329_000001
Create Date: 2026-03-30 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260330_000002"
down_revision = "20260329_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_orders", sa.Column("network", sa.String(length=64), nullable=True))
    op.add_column("payment_orders", sa.Column("chain_id", sa.Integer(), nullable=True))
    op.add_column("payment_orders", sa.Column("onchain_status", sa.String(length=32), nullable=True))
    op.add_column("payment_orders", sa.Column("tx_hash", sa.String(length=80), nullable=True))
    op.add_column("payment_orders", sa.Column("explorer_url", sa.String(length=255), nullable=True))
    op.add_column("payment_orders", sa.Column("contract_address", sa.String(length=64), nullable=True))
    op.add_column("payment_orders", sa.Column("token_address", sa.String(length=64), nullable=True))
    op.add_column("payment_orders", sa.Column("execution_tx_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "payment_orders",
        sa.Column("execution_tx_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("payment_orders", sa.Column("gas_used", sa.Numeric(precision=38, scale=0), nullable=True))
    op.add_column(
        "payment_orders",
        sa.Column("effective_gas_price", sa.Numeric(precision=38, scale=0), nullable=True),
    )
    op.add_column("payment_orders", sa.Column("onchain_payload_json", sa.JSON(), nullable=True))
    op.create_index(op.f("ix_payment_orders_onchain_status"), "payment_orders", ["onchain_status"], unique=False)
    op.create_index(op.f("ix_payment_orders_tx_hash"), "payment_orders", ["tx_hash"], unique=False)

    op.add_column("payment_splits", sa.Column("tx_hash", sa.String(length=80), nullable=True))
    op.add_column("payment_splits", sa.Column("explorer_url", sa.String(length=255), nullable=True))
    op.add_column("payment_splits", sa.Column("onchain_status", sa.String(length=32), nullable=True))
    op.add_column("payment_splits", sa.Column("execution_tx_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "payment_splits",
        sa.Column("execution_tx_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("payment_splits", sa.Column("gas_used", sa.Numeric(precision=38, scale=0), nullable=True))
    op.create_index(op.f("ix_payment_splits_onchain_status"), "payment_splits", ["onchain_status"], unique=False)
    op.create_index(op.f("ix_payment_splits_tx_hash"), "payment_splits", ["tx_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_splits_tx_hash"), table_name="payment_splits")
    op.drop_index(op.f("ix_payment_splits_onchain_status"), table_name="payment_splits")
    op.drop_column("payment_splits", "gas_used")
    op.drop_column("payment_splits", "execution_tx_confirmed_at")
    op.drop_column("payment_splits", "execution_tx_sent_at")
    op.drop_column("payment_splits", "onchain_status")
    op.drop_column("payment_splits", "explorer_url")
    op.drop_column("payment_splits", "tx_hash")

    op.drop_index(op.f("ix_payment_orders_tx_hash"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_onchain_status"), table_name="payment_orders")
    op.drop_column("payment_orders", "onchain_payload_json")
    op.drop_column("payment_orders", "effective_gas_price")
    op.drop_column("payment_orders", "gas_used")
    op.drop_column("payment_orders", "execution_tx_confirmed_at")
    op.drop_column("payment_orders", "execution_tx_sent_at")
    op.drop_column("payment_orders", "token_address")
    op.drop_column("payment_orders", "contract_address")
    op.drop_column("payment_orders", "explorer_url")
    op.drop_column("payment_orders", "tx_hash")
    op.drop_column("payment_orders", "onchain_status")
    op.drop_column("payment_orders", "chain_id")
    op.drop_column("payment_orders", "network")
