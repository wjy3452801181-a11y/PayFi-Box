from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    PaymentExecutionBatch,
    PaymentExecutionItem,
    PaymentExecutionItemStatus,
    PaymentOrder,
    PaymentOrderStatus,
    PlatformBalanceAccount,
    PlatformBalanceAccountStatus,
    PlatformBalanceLedgerEntry,
    PlatformBalanceLock,
    PlatformBalanceLockStatus,
    FiatDepositOrder,
)

BALANCE_FUNDING_SOURCE = "platform_balance"
TOKEN_UNIT = Decimal("0.000001")


def quantize_token_amount(value: Decimal | float | str) -> Decimal:
    return Decimal(str(value)).quantize(TOKEN_UNIT, rounding=ROUND_DOWN)


def get_or_create_balance_account(
    *,
    session: Session,
    user_id: uuid.UUID,
    currency: str,
    lock: bool = False,
) -> PlatformBalanceAccount:
    stmt = select(PlatformBalanceAccount).where(
        PlatformBalanceAccount.user_id == user_id,
        PlatformBalanceAccount.currency == currency,
    )
    if lock:
        stmt = stmt.with_for_update()
    account = session.execute(stmt.limit(1)).scalar_one_or_none()
    if account is not None:
        return account
    account = PlatformBalanceAccount(
        id=uuid.uuid4(),
        user_id=user_id,
        currency=currency,
        available_balance=Decimal("0"),
        locked_balance=Decimal("0"),
        status=PlatformBalanceAccountStatus.ACTIVE.value,
        metadata_json={},
    )
    session.add(account)
    session.flush()
    return account


def load_balance_lock_by_command(
    *,
    session: Session,
    command_id: uuid.UUID,
    lock: bool = False,
) -> PlatformBalanceLock | None:
    stmt = select(PlatformBalanceLock).where(PlatformBalanceLock.command_id == command_id)
    if lock:
        stmt = stmt.with_for_update()
    return session.execute(stmt.limit(1)).scalar_one_or_none()


def create_balance_lock_for_command(
    *,
    session: Session,
    account: PlatformBalanceAccount,
    command_id: uuid.UUID,
    currency: str,
    amount: Decimal,
    actor_user_id: uuid.UUID,
    trace_id: str,
    metadata: dict[str, Any] | None = None,
) -> PlatformBalanceLock:
    existing = load_balance_lock_by_command(session=session, command_id=command_id, lock=True)
    if existing is not None:
        return existing
    amount = quantize_token_amount(amount)
    if account.status != PlatformBalanceAccountStatus.ACTIVE.value:
        raise ValueError("balance_account_not_active")
    if amount <= 0:
        raise ValueError("lock_amount_must_be_positive")
    if Decimal(account.available_balance) < amount:
        raise ValueError("insufficient_balance")

    available_before = quantize_token_amount(account.available_balance)
    account.available_balance = quantize_token_amount(available_before - amount)
    account.locked_balance = quantize_token_amount(Decimal(account.locked_balance) + amount)

    balance_lock = PlatformBalanceLock(
        id=uuid.uuid4(),
        account_id=account.id,
        command_id=command_id,
        currency=currency,
        locked_amount=amount,
        consumed_amount=Decimal("0"),
        released_amount=Decimal("0"),
        status=PlatformBalanceLockStatus.ACTIVE.value,
        metadata_json=metadata or {},
    )
    session.add(account)
    session.add(balance_lock)
    session.flush()
    session.add(
        PlatformBalanceLedgerEntry(
            id=uuid.uuid4(),
            account_id=account.id,
            entry_type="payment_lock",
            amount=-amount,
            balance_before=available_before,
            balance_after=quantize_token_amount(account.available_balance),
            reference_type="platform_balance_lock",
            reference_id=balance_lock.id,
            description="Reserved spendable stablecoin balance for settlement execution.",
            metadata_json={
                "command_id": str(command_id),
                "locked_amount": float(amount),
                "locked_balance_after": float(account.locked_balance),
            },
        )
    )
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            entity_type="platform_balance_lock",
            entity_id=balance_lock.id,
            action="balance_locked",
            before_json=None,
            after_json={
                "account_id": str(account.id),
                "command_id": str(command_id),
                "locked_amount": float(amount),
                "status": balance_lock.status,
            },
            trace_id=trace_id,
        )
    )
    return balance_lock


def bind_balance_lock_to_payment(
    *,
    session: Session,
    payment_order: PaymentOrder,
) -> PlatformBalanceLock | None:
    lock: PlatformBalanceLock | None = None
    if payment_order.funding_source == BALANCE_FUNDING_SOURCE and payment_order.funding_reference_id is not None:
        lock = session.get(PlatformBalanceLock, payment_order.funding_reference_id)
    elif payment_order.source_command_id is not None:
        lock = load_balance_lock_by_command(session=session, command_id=payment_order.source_command_id, lock=True)
    if lock is None:
        return None

    if payment_order.funding_source != BALANCE_FUNDING_SOURCE:
        payment_order.funding_source = BALANCE_FUNDING_SOURCE
    if payment_order.funding_reference_id != lock.id:
        payment_order.funding_reference_id = lock.id
    if lock.payment_order_id != payment_order.id:
        lock.payment_order_id = payment_order.id

    metadata_json = dict(payment_order.metadata_json or {})
    metadata_json["funding_source"] = BALANCE_FUNDING_SOURCE
    metadata_json["balance_lock_id"] = str(lock.id)
    metadata_json["balance_account_id"] = str(lock.account_id)
    payment_order.metadata_json = metadata_json

    session.add(lock)
    session.add(payment_order)
    return lock


def release_balance_lock_without_payment(
    *,
    session: Session,
    balance_lock: PlatformBalanceLock,
    actor_user_id: uuid.UUID | None,
    trace_id: str,
    reason: str,
) -> PlatformBalanceLock:
    account = session.execute(
        select(PlatformBalanceAccount)
        .where(PlatformBalanceAccount.id == balance_lock.account_id)
        .with_for_update()
        .limit(1)
    ).scalar_one()
    remaining = quantize_token_amount(
        Decimal(balance_lock.locked_amount) - Decimal(balance_lock.released_amount) - Decimal(balance_lock.consumed_amount)
    )
    if remaining <= 0:
        return balance_lock

    available_before = quantize_token_amount(account.available_balance)
    account.available_balance = quantize_token_amount(available_before + remaining)
    account.locked_balance = quantize_token_amount(Decimal(account.locked_balance) - remaining)
    balance_lock.released_amount = quantize_token_amount(Decimal(balance_lock.released_amount) + remaining)
    balance_lock.status = (
        PlatformBalanceLockStatus.RELEASED.value
        if Decimal(balance_lock.consumed_amount) == Decimal("0")
        else PlatformBalanceLockStatus.PARTIALLY_SETTLED.value
    )
    meta = dict(balance_lock.metadata_json or {})
    meta["release_reason"] = reason
    meta["released_at"] = datetime.now(timezone.utc).isoformat()
    balance_lock.metadata_json = meta

    session.add(account)
    session.add(balance_lock)
    session.add(
        PlatformBalanceLedgerEntry(
            id=uuid.uuid4(),
            account_id=account.id,
            entry_type="payment_unlock",
            amount=remaining,
            balance_before=available_before,
            balance_after=quantize_token_amount(account.available_balance),
            reference_type="platform_balance_lock",
            reference_id=balance_lock.id,
            description="Released reserved stablecoin balance back to spendable balance.",
            metadata_json={
                "release_reason": reason,
                "released_amount": float(remaining),
                "locked_balance_after": float(account.locked_balance),
            },
        )
    )
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            entity_type="platform_balance_lock",
            entity_id=balance_lock.id,
            action="balance_lock_released",
            before_json=None,
            after_json={
                "released_amount": float(balance_lock.released_amount),
                "consumed_amount": float(balance_lock.consumed_amount),
                "status": balance_lock.status,
                "reason": reason,
            },
            trace_id=trace_id,
        )
    )
    return balance_lock


def credit_deposit_order_to_balance(
    *,
    session: Session,
    deposit_order: FiatDepositOrder,
    actor_user_id: uuid.UUID | None,
    trace_id: str,
) -> PlatformBalanceAccount:
    account = get_or_create_balance_account(
        session=session,
        user_id=deposit_order.user_id,
        currency=deposit_order.target_currency,
        lock=True,
    )
    if deposit_order.status == "credited":
        return account

    amount = quantize_token_amount(deposit_order.target_amount)
    available_before = quantize_token_amount(account.available_balance)
    account.available_balance = quantize_token_amount(available_before + amount)
    deposit_order.status = "credited"
    deposit_order.next_action = "use_balance"
    meta = dict(deposit_order.metadata_json or {})
    meta["credited_account_id"] = str(account.id)
    meta["credited_at"] = datetime.now(timezone.utc).isoformat()
    deposit_order.metadata_json = meta

    session.add(account)
    session.add(deposit_order)
    session.add(
        PlatformBalanceLedgerEntry(
            id=uuid.uuid4(),
            account_id=account.id,
            entry_type="conversion_credit",
            amount=amount,
            balance_before=available_before,
            balance_after=quantize_token_amount(account.available_balance),
            reference_type="fiat_deposit_order",
            reference_id=deposit_order.id,
            description="Converted fiat deposit credited to platform stablecoin balance.",
            metadata_json={
                "source_currency": deposit_order.source_currency,
                "source_amount": float(deposit_order.source_amount),
                "target_currency": deposit_order.target_currency,
                "target_amount": float(amount),
            },
        )
    )
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            entity_type="fiat_deposit_order",
            entity_id=deposit_order.id,
            action="stablecoin_balance_credited",
            before_json=None,
            after_json={
                "target_currency": deposit_order.target_currency,
                "target_amount": float(amount),
                "account_id": str(account.id),
                "status": deposit_order.status,
            },
            trace_id=trace_id,
        )
    )
    return account


def settle_balance_lock_for_payment(
    *,
    session: Session,
    payment_order: PaymentOrder,
    actor_user_id: uuid.UUID | None,
    trace_id: str,
) -> PlatformBalanceLock | None:
    lock = bind_balance_lock_to_payment(session=session, payment_order=payment_order)
    if lock is None:
        return None
    if payment_order.status not in {
        PaymentOrderStatus.EXECUTED.value,
        PaymentOrderStatus.PARTIALLY_EXECUTED.value,
        PaymentOrderStatus.FAILED.value,
        PaymentOrderStatus.CANCELLED.value,
    }:
        return lock

    account = session.execute(
        select(PlatformBalanceAccount)
        .where(PlatformBalanceAccount.id == lock.account_id)
        .with_for_update()
        .limit(1)
    ).scalar_one()
    locked_amount = quantize_token_amount(lock.locked_amount)
    confirmed_amount, failed_amount = _summarize_payment_execution_amounts(
        session=session,
        payment_order_id=payment_order.id,
    )

    if payment_order.status == PaymentOrderStatus.EXECUTED.value:
        target_consumed = locked_amount
        target_released = Decimal("0")
    elif payment_order.status in {PaymentOrderStatus.FAILED.value, PaymentOrderStatus.CANCELLED.value}:
        target_consumed = Decimal("0")
        target_released = locked_amount
    else:
        target_consumed = min(quantize_token_amount(confirmed_amount), locked_amount)
        target_released = min(
            quantize_token_amount(failed_amount),
            quantize_token_amount(locked_amount - target_consumed),
        )
        remainder = quantize_token_amount(locked_amount - target_consumed - target_released)
        if remainder > 0:
            target_released = quantize_token_amount(target_released + remainder)

    consume_delta = quantize_token_amount(target_consumed - Decimal(lock.consumed_amount))
    release_delta = quantize_token_amount(target_released - Decimal(lock.released_amount))

    if consume_delta > 0:
        available_before = quantize_token_amount(account.available_balance)
        account.locked_balance = quantize_token_amount(Decimal(account.locked_balance) - consume_delta)
        lock.consumed_amount = quantize_token_amount(Decimal(lock.consumed_amount) + consume_delta)
        session.add(
            PlatformBalanceLedgerEntry(
                id=uuid.uuid4(),
                account_id=account.id,
                entry_type="payment_debit",
                amount=Decimal("0"),
                balance_before=available_before,
                balance_after=available_before,
                reference_type="payment_order",
                reference_id=payment_order.id,
                description="Finalized settlement debit from previously reserved balance.",
                metadata_json={
                    "consumed_amount": float(consume_delta),
                    "locked_balance_after": float(account.locked_balance),
                    "payment_order_id": str(payment_order.id),
                },
            )
        )
    if release_delta > 0:
        available_before = quantize_token_amount(account.available_balance)
        account.available_balance = quantize_token_amount(available_before + release_delta)
        account.locked_balance = quantize_token_amount(Decimal(account.locked_balance) - release_delta)
        lock.released_amount = quantize_token_amount(Decimal(lock.released_amount) + release_delta)
        session.add(
            PlatformBalanceLedgerEntry(
                id=uuid.uuid4(),
                account_id=account.id,
                entry_type="payment_unlock",
                amount=release_delta,
                balance_before=available_before,
                balance_after=quantize_token_amount(account.available_balance),
                reference_type="payment_order",
                reference_id=payment_order.id,
                description="Released unused reserved balance after settlement result.",
                metadata_json={
                    "released_amount": float(release_delta),
                    "locked_balance_after": float(account.locked_balance),
                    "payment_order_id": str(payment_order.id),
                },
            )
        )

    if Decimal(lock.consumed_amount) == locked_amount and Decimal(lock.released_amount) == Decimal("0"):
        lock.status = PlatformBalanceLockStatus.CONSUMED.value
    elif Decimal(lock.released_amount) == locked_amount and Decimal(lock.consumed_amount) == Decimal("0"):
        lock.status = PlatformBalanceLockStatus.RELEASED.value
    else:
        lock.status = PlatformBalanceLockStatus.PARTIALLY_SETTLED.value

    session.add(account)
    session.add(lock)
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            entity_type="platform_balance_lock",
            entity_id=lock.id,
            action="balance_lock_settled",
            before_json=None,
            after_json={
                "payment_order_id": str(payment_order.id),
                "consumed_amount": float(lock.consumed_amount),
                "released_amount": float(lock.released_amount),
                "status": lock.status,
            },
            trace_id=trace_id,
        )
    )
    return lock


def _summarize_payment_execution_amounts(
    *,
    session: Session,
    payment_order_id: uuid.UUID,
) -> tuple[Decimal, Decimal]:
    batch = session.execute(
        select(PaymentExecutionBatch)
        .where(PaymentExecutionBatch.payment_order_id == payment_order_id)
        .order_by(PaymentExecutionBatch.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if batch is None:
        return Decimal("0"), Decimal("0")
    items = session.execute(
        select(PaymentExecutionItem)
        .where(PaymentExecutionItem.execution_batch_id == batch.id)
    ).scalars().all()
    confirmed = Decimal("0")
    failed = Decimal("0")
    for item in items:
        amount = quantize_token_amount(item.amount)
        if item.status == PaymentExecutionItemStatus.CONFIRMED.value:
            confirmed += amount
        elif item.status == PaymentExecutionItemStatus.FAILED.value:
            failed += amount
    return quantize_token_amount(confirmed), quantize_token_amount(failed)
