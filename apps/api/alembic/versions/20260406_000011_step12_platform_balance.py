"""step12 platform balance accounts and deposit orders

Revision ID: 20260406_000011
Revises: 20260403_000010
Create Date: 2026-04-06 18:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260406_000011"
down_revision: Union[str, None] = "20260403_000010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_orders",
        sa.Column("funding_source", sa.String(length=32), nullable=False, server_default="fiat_settlement"),
    )
    op.add_column(
        "payment_orders",
        sa.Column("funding_reference_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_payment_orders_funding_source"), "payment_orders", ["funding_source"], unique=False)
    op.create_index(
        op.f("ix_payment_orders_funding_reference_id"),
        "payment_orders",
        ["funding_reference_id"],
        unique=False,
    )
    op.alter_column("payment_orders", "funding_source", server_default=None)

    op.create_table(
        "platform_balance_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("available_balance", sa.Numeric(precision=36, scale=18), nullable=False, server_default="0"),
        sa.Column("locked_balance", sa.Numeric(precision=36, scale=18), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "currency", name="uq_platform_balance_accounts_user_currency"),
        sa.CheckConstraint("available_balance >= 0", name="ck_platform_balance_accounts_available_nonnegative"),
        sa.CheckConstraint("locked_balance >= 0", name="ck_platform_balance_accounts_locked_nonnegative"),
    )
    op.create_index(op.f("ix_platform_balance_accounts_created_at"), "platform_balance_accounts", ["created_at"], unique=False)
    op.create_index(op.f("ix_platform_balance_accounts_user_id"), "platform_balance_accounts", ["user_id"], unique=False)
    op.create_index(op.f("ix_platform_balance_accounts_currency"), "platform_balance_accounts", ["currency"], unique=False)
    op.create_index(op.f("ix_platform_balance_accounts_status"), "platform_balance_accounts", ["status"], unique=False)

    op.create_table(
        "platform_balance_ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=48), nullable=False),
        sa.Column("amount", sa.Numeric(precision=36, scale=18), nullable=False),
        sa.Column("balance_before", sa.Numeric(precision=36, scale=18), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=36, scale=18), nullable=False),
        sa.Column("reference_type", sa.String(length=48), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["platform_balance_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_balance_ledger_entries_account_id"),
        "platform_balance_ledger_entries",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_platform_balance_ledger_entries_entry_type"),
        "platform_balance_ledger_entries",
        ["entry_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_platform_balance_ledger_entries_reference_id"),
        "platform_balance_ledger_entries",
        ["reference_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_platform_balance_ledger_entries_created_at"),
        "platform_balance_ledger_entries",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "platform_balance_locks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("locked_amount", sa.Numeric(precision=36, scale=18), nullable=False),
        sa.Column("released_amount", sa.Numeric(precision=36, scale=18), nullable=False, server_default="0"),
        sa.Column("consumed_amount", sa.Numeric(precision=36, scale=18), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["platform_balance_accounts.id"]),
        sa.ForeignKeyConstraint(["command_id"], ["command_executions.id"]),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id", name="uq_platform_balance_locks_command_id"),
        sa.UniqueConstraint("payment_order_id", name="uq_platform_balance_locks_payment_order_id"),
        sa.CheckConstraint("locked_amount > 0", name="ck_platform_balance_locks_locked_positive"),
        sa.CheckConstraint("released_amount >= 0", name="ck_platform_balance_locks_released_nonnegative"),
        sa.CheckConstraint("consumed_amount >= 0", name="ck_platform_balance_locks_consumed_nonnegative"),
    )
    op.create_index(op.f("ix_platform_balance_locks_created_at"), "platform_balance_locks", ["created_at"], unique=False)
    op.create_index(op.f("ix_platform_balance_locks_account_id"), "platform_balance_locks", ["account_id"], unique=False)
    op.create_index(op.f("ix_platform_balance_locks_command_id"), "platform_balance_locks", ["command_id"], unique=False)
    op.create_index(op.f("ix_platform_balance_locks_payment_order_id"), "platform_balance_locks", ["payment_order_id"], unique=False)
    op.create_index(op.f("ix_platform_balance_locks_currency"), "platform_balance_locks", ["currency"], unique=False)
    op.create_index(op.f("ix_platform_balance_locks_status"), "platform_balance_locks", ["status"], unique=False)

    op.create_table(
        "fiat_deposit_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_currency", sa.String(length=16), nullable=False),
        sa.Column("source_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("target_currency", sa.String(length=16), nullable=False, server_default="USDT"),
        sa.Column("target_amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("fee_amount", sa.Numeric(precision=18, scale=6), nullable=False, server_default="0"),
        sa.Column("payment_channel", sa.String(length=32), nullable=False, server_default="stripe"),
        sa.Column("channel_payment_id", sa.String(length=128), nullable=True),
        sa.Column("channel_checkout_session_id", sa.String(length=128), nullable=True),
        sa.Column("channel_checkout_url", sa.String(length=1024), nullable=True),
        sa.Column("channel_status", sa.String(length=32), nullable=True),
        sa.Column("channel_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kyc_verification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("next_action", sa.String(length=64), nullable=True),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["kyc_verification_id"], ["kyc_verifications.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_payment_id", name="uq_fiat_deposit_orders_channel_payment_id"),
        sa.UniqueConstraint("channel_checkout_session_id", name="uq_fiat_deposit_orders_channel_checkout_session_id"),
    )
    op.create_index(op.f("ix_fiat_deposit_orders_created_at"), "fiat_deposit_orders", ["created_at"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_user_id"), "fiat_deposit_orders", ["user_id"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_source_currency"), "fiat_deposit_orders", ["source_currency"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_target_currency"), "fiat_deposit_orders", ["target_currency"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_payment_channel"), "fiat_deposit_orders", ["payment_channel"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_channel_payment_id"), "fiat_deposit_orders", ["channel_payment_id"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_channel_checkout_session_id"), "fiat_deposit_orders", ["channel_checkout_session_id"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_channel_status"), "fiat_deposit_orders", ["channel_status"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_kyc_verification_id"), "fiat_deposit_orders", ["kyc_verification_id"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_status"), "fiat_deposit_orders", ["status"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_next_action"), "fiat_deposit_orders", ["next_action"], unique=False)
    op.create_index(op.f("ix_fiat_deposit_orders_reference"), "fiat_deposit_orders", ["reference"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fiat_deposit_orders_reference"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_next_action"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_status"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_kyc_verification_id"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_channel_status"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_channel_checkout_session_id"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_channel_payment_id"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_payment_channel"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_target_currency"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_source_currency"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_user_id"), table_name="fiat_deposit_orders")
    op.drop_index(op.f("ix_fiat_deposit_orders_created_at"), table_name="fiat_deposit_orders")
    op.drop_table("fiat_deposit_orders")

    op.drop_index(op.f("ix_platform_balance_locks_status"), table_name="platform_balance_locks")
    op.drop_index(op.f("ix_platform_balance_locks_currency"), table_name="platform_balance_locks")
    op.drop_index(op.f("ix_platform_balance_locks_payment_order_id"), table_name="platform_balance_locks")
    op.drop_index(op.f("ix_platform_balance_locks_command_id"), table_name="platform_balance_locks")
    op.drop_index(op.f("ix_platform_balance_locks_account_id"), table_name="platform_balance_locks")
    op.drop_index(op.f("ix_platform_balance_locks_created_at"), table_name="platform_balance_locks")
    op.drop_table("platform_balance_locks")

    op.drop_index(op.f("ix_platform_balance_ledger_entries_created_at"), table_name="platform_balance_ledger_entries")
    op.drop_index(op.f("ix_platform_balance_ledger_entries_reference_id"), table_name="platform_balance_ledger_entries")
    op.drop_index(op.f("ix_platform_balance_ledger_entries_entry_type"), table_name="platform_balance_ledger_entries")
    op.drop_index(op.f("ix_platform_balance_ledger_entries_account_id"), table_name="platform_balance_ledger_entries")
    op.drop_table("platform_balance_ledger_entries")

    op.drop_index(op.f("ix_platform_balance_accounts_status"), table_name="platform_balance_accounts")
    op.drop_index(op.f("ix_platform_balance_accounts_currency"), table_name="platform_balance_accounts")
    op.drop_index(op.f("ix_platform_balance_accounts_user_id"), table_name="platform_balance_accounts")
    op.drop_index(op.f("ix_platform_balance_accounts_created_at"), table_name="platform_balance_accounts")
    op.drop_table("platform_balance_accounts")

    op.drop_index(op.f("ix_payment_orders_funding_reference_id"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_funding_source"), table_name="payment_orders")
    op.drop_column("payment_orders", "funding_reference_id")
    op.drop_column("payment_orders", "funding_source")
