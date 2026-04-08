"""step9 merchant fiat-in stablecoin-out settlement models

Revision ID: 20260401_000005
Revises: 20260331_000004
Create Date: 2026-04-01 01:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260401_000005"
down_revision: Union[str, None] = "20260331_000004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settlement_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("beneficiary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_currency", sa.String(length=16), nullable=False),
        sa.Column("source_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("target_currency", sa.String(length=16), nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("target_network", sa.String(length=32), nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("platform_fee", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("network_fee", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("spread_bps", sa.Integer(), nullable=False),
        sa.Column("total_fee_amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("quote_payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["beneficiary_id"], ["beneficiaries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_settlement_quotes_created_at"), "settlement_quotes", ["created_at"], unique=False)
    op.create_index(op.f("ix_settlement_quotes_merchant_id"), "settlement_quotes", ["merchant_id"], unique=False)
    op.create_index(op.f("ix_settlement_quotes_beneficiary_id"), "settlement_quotes", ["beneficiary_id"], unique=False)
    op.create_index(op.f("ix_settlement_quotes_source_currency"), "settlement_quotes", ["source_currency"], unique=False)
    op.create_index(op.f("ix_settlement_quotes_target_currency"), "settlement_quotes", ["target_currency"], unique=False)
    op.create_index(op.f("ix_settlement_quotes_status"), "settlement_quotes", ["status"], unique=False)
    op.create_index(op.f("ix_settlement_quotes_expires_at"), "settlement_quotes", ["expires_at"], unique=False)

    op.create_table(
        "fiat_payment_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("beneficiary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payer_currency", sa.String(length=16), nullable=False),
        sa.Column("payer_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("target_stablecoin", sa.String(length=16), nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("target_network", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("payout_command_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["beneficiary_id"], ["beneficiaries.id"]),
        sa.ForeignKeyConstraint(["quote_id"], ["settlement_quotes.id"]),
        sa.ForeignKeyConstraint(["payout_command_id"], ["command_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", name="uq_fiat_payment_intents_quote_id"),
    )
    op.create_index(op.f("ix_fiat_payment_intents_created_at"), "fiat_payment_intents", ["created_at"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_merchant_id"), "fiat_payment_intents", ["merchant_id"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_beneficiary_id"), "fiat_payment_intents", ["beneficiary_id"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_quote_id"), "fiat_payment_intents", ["quote_id"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_payer_currency"), "fiat_payment_intents", ["payer_currency"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_target_stablecoin"), "fiat_payment_intents", ["target_stablecoin"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_status"), "fiat_payment_intents", ["status"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_reference"), "fiat_payment_intents", ["reference"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_payout_command_id"), "fiat_payment_intents", ["payout_command_id"], unique=False)

    op.create_table(
        "fiat_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fiat_payment_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_method", sa.String(length=32), nullable=False),
        sa.Column("bank_reference", sa.String(length=128), nullable=True),
        sa.Column("received_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fiat_payment_intent_id"], ["fiat_payment_intents.id"]),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fiat_payment_intent_id", name="uq_fiat_collections_payment_intent_id"),
    )
    op.create_index(op.f("ix_fiat_collections_created_at"), "fiat_collections", ["created_at"], unique=False)
    op.create_index(op.f("ix_fiat_collections_fiat_payment_intent_id"), "fiat_collections", ["fiat_payment_intent_id"], unique=False)
    op.create_index(op.f("ix_fiat_collections_bank_reference"), "fiat_collections", ["bank_reference"], unique=False)
    op.create_index(op.f("ix_fiat_collections_currency"), "fiat_collections", ["currency"], unique=False)
    op.create_index(op.f("ix_fiat_collections_confirmed_by_user_id"), "fiat_collections", ["confirmed_by_user_id"], unique=False)
    op.create_index(op.f("ix_fiat_collections_status"), "fiat_collections", ["status"], unique=False)

    op.create_table(
        "stablecoin_payout_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fiat_payment_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fiat_payment_intent_id"], ["fiat_payment_intents.id"]),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.ForeignKeyConstraint(["execution_batch_id"], ["payment_execution_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fiat_payment_intent_id", name="uq_stablecoin_payout_links_intent_id"),
    )
    op.create_index(op.f("ix_stablecoin_payout_links_created_at"), "stablecoin_payout_links", ["created_at"], unique=False)
    op.create_index(op.f("ix_stablecoin_payout_links_fiat_payment_intent_id"), "stablecoin_payout_links", ["fiat_payment_intent_id"], unique=False)
    op.create_index(op.f("ix_stablecoin_payout_links_payment_order_id"), "stablecoin_payout_links", ["payment_order_id"], unique=False)
    op.create_index(op.f("ix_stablecoin_payout_links_execution_batch_id"), "stablecoin_payout_links", ["execution_batch_id"], unique=False)
    op.create_index(op.f("ix_stablecoin_payout_links_status"), "stablecoin_payout_links", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_stablecoin_payout_links_status"), table_name="stablecoin_payout_links")
    op.drop_index(op.f("ix_stablecoin_payout_links_execution_batch_id"), table_name="stablecoin_payout_links")
    op.drop_index(op.f("ix_stablecoin_payout_links_payment_order_id"), table_name="stablecoin_payout_links")
    op.drop_index(op.f("ix_stablecoin_payout_links_fiat_payment_intent_id"), table_name="stablecoin_payout_links")
    op.drop_index(op.f("ix_stablecoin_payout_links_created_at"), table_name="stablecoin_payout_links")
    op.drop_table("stablecoin_payout_links")

    op.drop_index(op.f("ix_fiat_collections_status"), table_name="fiat_collections")
    op.drop_index(op.f("ix_fiat_collections_confirmed_by_user_id"), table_name="fiat_collections")
    op.drop_index(op.f("ix_fiat_collections_currency"), table_name="fiat_collections")
    op.drop_index(op.f("ix_fiat_collections_bank_reference"), table_name="fiat_collections")
    op.drop_index(op.f("ix_fiat_collections_fiat_payment_intent_id"), table_name="fiat_collections")
    op.drop_index(op.f("ix_fiat_collections_created_at"), table_name="fiat_collections")
    op.drop_table("fiat_collections")

    op.drop_index(op.f("ix_fiat_payment_intents_payout_command_id"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_reference"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_status"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_target_stablecoin"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_payer_currency"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_quote_id"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_beneficiary_id"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_merchant_id"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_created_at"), table_name="fiat_payment_intents")
    op.drop_table("fiat_payment_intents")

    op.drop_index(op.f("ix_settlement_quotes_expires_at"), table_name="settlement_quotes")
    op.drop_index(op.f("ix_settlement_quotes_status"), table_name="settlement_quotes")
    op.drop_index(op.f("ix_settlement_quotes_target_currency"), table_name="settlement_quotes")
    op.drop_index(op.f("ix_settlement_quotes_source_currency"), table_name="settlement_quotes")
    op.drop_index(op.f("ix_settlement_quotes_beneficiary_id"), table_name="settlement_quotes")
    op.drop_index(op.f("ix_settlement_quotes_merchant_id"), table_name="settlement_quotes")
    op.drop_index(op.f("ix_settlement_quotes_created_at"), table_name="settlement_quotes")
    op.drop_table("settlement_quotes")
