"""step11 stripe fiat channel and kyc verification

Revision ID: 20260403_000009
Revises: 20260401_000008
Create Date: 2026-04-03 10:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260403_000009"
down_revision: Union[str, None] = "20260401_000008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kyc_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_verification_session_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("verification_url", sa.String(length=1024), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_verification_session_id"),
    )
    op.create_index(op.f("ix_kyc_verifications_created_at"), "kyc_verifications", ["created_at"], unique=False)
    op.create_index(op.f("ix_kyc_verifications_subject_type"), "kyc_verifications", ["subject_type"], unique=False)
    op.create_index(op.f("ix_kyc_verifications_subject_id"), "kyc_verifications", ["subject_id"], unique=False)
    op.create_index(op.f("ix_kyc_verifications_provider"), "kyc_verifications", ["provider"], unique=False)
    op.create_index(
        op.f("ix_kyc_verifications_provider_verification_session_id"),
        "kyc_verifications",
        ["provider_verification_session_id"],
        unique=False,
    )
    op.create_index(op.f("ix_kyc_verifications_status"), "kyc_verifications", ["status"], unique=False)

    op.add_column(
        "fiat_payment_intents",
        sa.Column("payment_channel", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.add_column(
        "fiat_payment_intents",
        sa.Column("channel_payment_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "fiat_payment_intents",
        sa.Column("channel_checkout_session_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "fiat_payment_intents",
        sa.Column("channel_checkout_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "fiat_payment_intents",
        sa.Column("channel_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fiat_payment_intents",
        sa.Column("channel_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fiat_payment_intents",
        sa.Column("webhook_received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fiat_payment_intents",
        sa.Column("kyc_verification_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.alter_column("fiat_payment_intents", "payment_channel", server_default=None)

    op.create_index(op.f("ix_fiat_payment_intents_payment_channel"), "fiat_payment_intents", ["payment_channel"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_channel_payment_id"), "fiat_payment_intents", ["channel_payment_id"], unique=False)
    op.create_index(
        op.f("ix_fiat_payment_intents_channel_checkout_session_id"),
        "fiat_payment_intents",
        ["channel_checkout_session_id"],
        unique=False,
    )
    op.create_index(op.f("ix_fiat_payment_intents_channel_status"), "fiat_payment_intents", ["channel_status"], unique=False)
    op.create_index(op.f("ix_fiat_payment_intents_kyc_verification_id"), "fiat_payment_intents", ["kyc_verification_id"], unique=False)
    op.create_unique_constraint(
        "uq_fiat_payment_intents_channel_payment_id",
        "fiat_payment_intents",
        ["channel_payment_id"],
    )
    op.create_unique_constraint(
        "uq_fiat_payment_intents_channel_checkout_session_id",
        "fiat_payment_intents",
        ["channel_checkout_session_id"],
    )
    op.create_foreign_key(
        "fk_fiat_payment_intents_kyc_verification_id",
        "fiat_payment_intents",
        "kyc_verifications",
        ["kyc_verification_id"],
        ["id"],
    )

    # Keep historical rows explicit and queryable for manual flow.
    op.execute(
        """
        UPDATE fiat_payment_intents
        SET payment_channel = COALESCE(payment_channel, 'manual'),
            channel_status = CASE
                WHEN status IN ('fiat_received', 'payout_in_progress', 'completed') THEN 'manual_confirmed'
                WHEN status = 'failed' THEN 'manual_failed'
                ELSE 'manual_pending'
            END
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fiat_payment_intents_kyc_verification_id",
        "fiat_payment_intents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_fiat_payment_intents_channel_checkout_session_id",
        "fiat_payment_intents",
        type_="unique",
    )
    op.drop_constraint(
        "uq_fiat_payment_intents_channel_payment_id",
        "fiat_payment_intents",
        type_="unique",
    )
    op.drop_index(op.f("ix_fiat_payment_intents_kyc_verification_id"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_channel_status"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_channel_checkout_session_id"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_channel_payment_id"), table_name="fiat_payment_intents")
    op.drop_index(op.f("ix_fiat_payment_intents_payment_channel"), table_name="fiat_payment_intents")

    op.drop_column("fiat_payment_intents", "kyc_verification_id")
    op.drop_column("fiat_payment_intents", "webhook_received_at")
    op.drop_column("fiat_payment_intents", "channel_confirmed_at")
    op.drop_column("fiat_payment_intents", "channel_status")
    op.drop_column("fiat_payment_intents", "channel_checkout_url")
    op.drop_column("fiat_payment_intents", "channel_checkout_session_id")
    op.drop_column("fiat_payment_intents", "channel_payment_id")
    op.drop_column("fiat_payment_intents", "payment_channel")

    op.drop_index(op.f("ix_kyc_verifications_status"), table_name="kyc_verifications")
    op.drop_index(op.f("ix_kyc_verifications_provider_verification_session_id"), table_name="kyc_verifications")
    op.drop_index(op.f("ix_kyc_verifications_provider"), table_name="kyc_verifications")
    op.drop_index(op.f("ix_kyc_verifications_subject_id"), table_name="kyc_verifications")
    op.drop_index(op.f("ix_kyc_verifications_subject_type"), table_name="kyc_verifications")
    op.drop_index(op.f("ix_kyc_verifications_created_at"), table_name="kyc_verifications")
    op.drop_table("kyc_verifications")
