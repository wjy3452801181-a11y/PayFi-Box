"""Step 11 mode-aware next_action persistence

Revision ID: 20260403_000010
Revises: 20260403_000009
Create Date: 2026-04-03 23:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260403_000010"
down_revision = "20260403_000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fiat_payment_intents",
        sa.Column("next_action", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_fiat_payment_intents_next_action",
        "fiat_payment_intents",
        ["next_action"],
        unique=False,
    )

    op.add_column(
        "payment_execution_items",
        sa.Column("pending_action", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_payment_execution_items_pending_action",
        "payment_execution_items",
        ["pending_action"],
        unique=False,
    )

    bind = op.get_bind()
    meta = sa.MetaData()
    fiat = sa.Table("fiat_payment_intents", meta, autoload_with=bind)
    batch = sa.Table("payment_execution_batches", meta, autoload_with=bind)
    items = sa.Table("payment_execution_items", meta, autoload_with=bind)

    fiat_rows = bind.execute(
        sa.select(
            fiat.c.id,
            fiat.c.status,
            fiat.c.payment_channel,
            fiat.c.channel_status,
        )
    ).fetchall()
    for row in fiat_rows:
        status = (row.status or "").lower()
        payment_channel = (row.payment_channel or "").lower()
        channel_status = (row.channel_status or "").lower()

        if status in {"completed", "cancelled", "failed", "blocked"}:
            next_action = "none"
        elif status == "awaiting_kyc" or channel_status == "blocked_kyc_required":
            next_action = "complete_kyc"
        elif payment_channel == "stripe" and status in {"created", "awaiting_channel_payment"}:
            next_action = "create_stripe_session"
        elif payment_channel == "stripe" and status == "payment_processing":
            next_action = "wait_channel_confirmation"
        elif status in {"fiat_received", "bridge_failed_recoverable", "payout_in_progress"}:
            next_action = "track_payout"
        else:
            next_action = "mark_fiat_received"

        bind.execute(
            fiat.update()
            .where(fiat.c.id == row.id)
            .values(next_action=next_action)
        )

    item_rows = bind.execute(
        sa.select(
            items.c.id,
            items.c.status,
            items.c.tx_hash,
            items.c.onchain_status,
            batch.c.execution_mode,
        ).select_from(items.join(batch, items.c.execution_batch_id == batch.c.id))
    ).fetchall()
    for row in item_rows:
        item_status = (row.status or "").lower()
        onchain_status = (row.onchain_status or "").lower()
        execution_mode = (row.execution_mode or "").lower()

        if item_status in {"confirmed", "failed"}:
            pending_action = None
        elif row.tx_hash and onchain_status not in {"confirmed_onchain", "failed_onchain"}:
            pending_action = "sync_receipt"
        elif item_status in {"submitted", "submitting"}:
            pending_action = "sync_receipt"
        elif execution_mode == "user_wallet":
            pending_action = "generate_unsigned_tx"
        elif execution_mode == "safe":
            pending_action = "generate_safe_proposal"
        else:
            pending_action = "confirm_now"

        bind.execute(
            items.update()
            .where(items.c.id == row.id)
            .values(pending_action=pending_action)
        )


def downgrade() -> None:
    op.drop_index("ix_payment_execution_items_pending_action", table_name="payment_execution_items")
    op.drop_column("payment_execution_items", "pending_action")

    op.drop_index("ix_fiat_payment_intents_next_action", table_name="fiat_payment_intents")
    op.drop_column("fiat_payment_intents", "next_action")
