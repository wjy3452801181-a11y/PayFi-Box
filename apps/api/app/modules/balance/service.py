from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AuditLog,
    CommandExecution,
    FiatDepositOrder,
    FiatDepositOrderStatus,
    KycVerification,
    KycVerificationStatus,
    PaymentOrder,
    PlatformBalanceAccount,
    PlatformBalanceLedgerEntry,
    User,
)
from app.modules.balance.lifecycle import (
    BALANCE_FUNDING_SOURCE,
    bind_balance_lock_to_payment,
    create_balance_lock_for_command,
    credit_deposit_order_to_balance,
    get_or_create_balance_account,
    load_balance_lock_by_command,
    quantize_token_amount,
    release_balance_lock_without_payment,
    settle_balance_lock_for_payment,
)
from app.modules.balance.schemas import (
    BalanceCheckSummary,
    BalancePaymentConfirmRequest,
    BalancePaymentConfirmResponse,
    BalancePaymentPreviewRequest,
    BalancePaymentPreviewResponse,
    CreateFiatDepositRequest,
    CreateFiatDepositResponse,
    DepositDetailResponse,
    FiatDepositOrderView,
    PlatformBalanceAccountResponse,
    PlatformBalanceAccountView,
    PlatformBalanceLedgerEntryView,
    PlatformBalanceLedgerResponse,
    PlatformBalanceLockView,
    StartDepositStripePaymentRequest,
    StartDepositStripePaymentResponse,
)
from app.modules.command.schemas import CommandRequest
from app.modules.command.service import handle_command
from app.modules.confirm.durable_service import handle_confirm
from app.modules.confirm.schemas import ConfirmRequest
from app.modules.merchant.service import (
    BPS_DENOM,
    FIAT_UNIT,
    STRIPE_CHANNEL,
    STABLECOIN_SET,
    TOKEN_UNIT,
    _load_effective_kyc_for_deposit,
    _load_latest_kyc_for_subject,
    _normalize_stripe_checkout_locale,
    _format_stripe_checkout_failure,
    _resolve_fx_rate,
    _stripe_get,
    _to_fiat_minor_units,
    _validate_stripe_secret_key,
    stripe,
)


def get_balance_account(
    session: Session,
    *,
    user_id: UUID,
    currency: str,
) -> PlatformBalanceAccountResponse:
    _require_user(session=session, user_id=user_id)
    normalized_currency = currency.upper().strip()
    account = get_or_create_balance_account(
        session=session,
        user_id=user_id,
        currency=normalized_currency,
        lock=False,
    )
    session.commit()
    session.refresh(account)
    return PlatformBalanceAccountResponse(account=_to_account_view(account))


def get_balance_ledger(
    session: Session,
    *,
    user_id: UUID,
    currency: str,
    limit: int,
) -> PlatformBalanceLedgerResponse:
    _require_user(session=session, user_id=user_id)
    normalized_currency = currency.upper().strip()
    account = get_or_create_balance_account(
        session=session,
        user_id=user_id,
        currency=normalized_currency,
        lock=False,
    )
    items = session.execute(
        select(PlatformBalanceLedgerEntry)
        .where(PlatformBalanceLedgerEntry.account_id == account.id)
        .order_by(PlatformBalanceLedgerEntry.created_at.desc())
        .limit(limit)
    ).scalars().all()
    total = int(
        session.execute(
            select(func.count())
            .select_from(PlatformBalanceLedgerEntry)
            .where(PlatformBalanceLedgerEntry.account_id == account.id)
        ).scalar_one()
    )
    session.commit()
    return PlatformBalanceLedgerResponse(
        account=_to_account_view(account),
        total=total,
        limit=limit,
        items=[_to_ledger_view(item) for item in items],
    )


def create_fiat_deposit(
    session: Session,
    *,
    request: CreateFiatDepositRequest,
) -> CreateFiatDepositResponse:
    user = _require_user(session=session, user_id=request.user_id)
    source_currency = request.source_currency.upper().strip()
    target_currency = request.target_currency.upper().strip()
    if target_currency not in STABLECOIN_SET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"target_currency must be one of {sorted(STABLECOIN_SET)}",
        )

    source_amount = Decimal(str(request.source_amount)).quantize(FIAT_UNIT, rounding=ROUND_DOWN)
    if source_amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_amount must be positive")
    fx_rate = _resolve_fx_rate(source_currency=source_currency, target_currency=target_currency)
    gross_target_amount = (source_amount * fx_rate).quantize(TOKEN_UNIT, rounding=ROUND_DOWN)

    settings = get_settings()
    spread_bps = int(settings.settlement_spread_bps)
    platform_fee_bps = int(settings.settlement_platform_fee_bps)
    min_platform_fee = Decimal(str(settings.settlement_min_platform_fee)).quantize(TOKEN_UNIT, rounding=ROUND_UP)
    spread_fee = (gross_target_amount * Decimal(spread_bps) / BPS_DENOM).quantize(TOKEN_UNIT, rounding=ROUND_UP)
    platform_fee = (gross_target_amount * Decimal(platform_fee_bps) / BPS_DENOM).quantize(
        TOKEN_UNIT, rounding=ROUND_UP
    )
    if platform_fee < min_platform_fee:
        platform_fee = min_platform_fee
    fee_amount = (spread_fee + platform_fee).quantize(TOKEN_UNIT, rounding=ROUND_UP)
    target_amount = (gross_target_amount - fee_amount).quantize(TOKEN_UNIT, rounding=ROUND_DOWN)
    if target_amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="deposit target amount must be positive")

    kyc = _load_balance_kyc(session=session, user_id=user.id)
    requires_kyc = bool(settings.settlement_require_kyc)
    deposit_status = (
        FiatDepositOrderStatus.AWAITING_KYC.value
        if requires_kyc and (kyc is None or kyc.status != KycVerificationStatus.VERIFIED.value)
        else FiatDepositOrderStatus.CREATED.value
    )
    next_action = "complete_kyc" if deposit_status == FiatDepositOrderStatus.AWAITING_KYC.value else "start_stripe_payment"

    deposit_order = FiatDepositOrder(
        id=uuid.uuid4(),
        user_id=user.id,
        source_currency=source_currency,
        source_amount=source_amount,
        target_currency=target_currency,
        target_amount=target_amount,
        fx_rate=fx_rate,
        fee_amount=fee_amount,
        payment_channel=STRIPE_CHANNEL,
        channel_status="blocked_kyc_required" if next_action == "complete_kyc" else "created",
        kyc_verification_id=kyc.id if kyc is not None else None,
        status=deposit_status,
        next_action=next_action,
        reference=request.reference or _build_deposit_reference(),
        metadata_json={
            "gross_target_amount": float(gross_target_amount),
            "spread_fee": float(spread_fee),
            "platform_fee": float(platform_fee),
            "pricing_mode": "platform_balance_deposit",
        },
    )
    session.add(deposit_order)
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_user_id=user.id,
            entity_type="fiat_deposit_order",
            entity_id=deposit_order.id,
            action="fiat_deposit_order_created",
            before_json=None,
            after_json={
                "status": deposit_order.status,
                "source_currency": deposit_order.source_currency,
                "source_amount": float(deposit_order.source_amount),
                "target_currency": deposit_order.target_currency,
                "target_amount": float(deposit_order.target_amount),
                "next_action": deposit_order.next_action,
            },
            trace_id=_deposit_trace_id(deposit_order.id),
        )
    )
    session.commit()
    session.refresh(deposit_order)
    return CreateFiatDepositResponse(
        status="ok",
        deposit_order=_to_deposit_view(deposit_order),
        next_action=next_action,
        message=(
            "充值单已创建，请先完成身份核验。 (Deposit order created; complete identity verification first.)"
            if next_action == "complete_kyc"
            else "充值单已创建，请继续 Stripe 法币入金。 (Deposit order created; continue to Stripe checkout.)"
        ),
    )


def start_deposit_stripe_payment(
    session: Session,
    *,
    deposit_order_id: UUID,
    request: StartDepositStripePaymentRequest,
) -> StartDepositStripePaymentResponse:
    settings = get_settings()
    deposit = session.execute(
        select(FiatDepositOrder)
        .where(FiatDepositOrder.id == deposit_order_id)
        .with_for_update()
    ).scalar_one_or_none()
    if deposit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"deposit_order not found: {deposit_order_id}")

    if deposit.status in {
        FiatDepositOrderStatus.CREDITED.value,
        FiatDepositOrderStatus.CANCELLED.value,
        FiatDepositOrderStatus.FAILED.value,
        FiatDepositOrderStatus.BLOCKED.value,
    }:
        return StartDepositStripePaymentResponse(
            status="validation_error",
            deposit_order=_to_deposit_view(deposit),
            next_action="none",
            checkout=None,
            message=f"当前状态 {deposit.status} 不允许继续收款。 (Current deposit status {deposit.status} is not eligible.)",
        )

    kyc = _load_balance_kyc(session=session, user_id=deposit.user_id)
    if settings.settlement_require_kyc and (kyc is None or kyc.status != KycVerificationStatus.VERIFIED.value):
        deposit.status = FiatDepositOrderStatus.AWAITING_KYC.value
        deposit.channel_status = "blocked_kyc_required"
        deposit.next_action = "complete_kyc"
        if kyc is not None:
            deposit.kyc_verification_id = kyc.id
        session.add(deposit)
        session.commit()
        session.refresh(deposit)
        return StartDepositStripePaymentResponse(
            status="validation_error",
            deposit_order=_to_deposit_view(deposit),
            next_action="complete_kyc",
            checkout=None,
            message="需要先完成身份核验，才能打开 Stripe 收款页。 (Complete identity verification before Stripe checkout.)",
        )

    stripe_key_valid, stripe_key_reason = _validate_stripe_secret_key(settings.stripe_secret_key)
    if not stripe_key_valid:
        return StartDepositStripePaymentResponse(
            status="failed",
            deposit_order=_to_deposit_view(deposit),
            next_action="none",
            checkout=None,
            message=f"Stripe 配置无效：{stripe_key_reason} (Stripe key is not ready.)",
        )
    if stripe is None:
        return StartDepositStripePaymentResponse(
            status="failed",
            deposit_order=_to_deposit_view(deposit),
            next_action="none",
            checkout=None,
            message="Stripe SDK 未安装。 (Stripe SDK is not installed.)",
        )

    if (
        deposit.channel_checkout_session_id
        and deposit.channel_checkout_url
        and deposit.channel_status in {"awaiting_payment", "payment_processing", "checkout_session_created"}
    ):
        return StartDepositStripePaymentResponse(
            status="ok",
            deposit_order=_to_deposit_view(deposit),
            next_action="open_checkout",
            checkout={
                "provider": "stripe",
                "checkout_session_id": deposit.channel_checkout_session_id,
                "checkout_url": deposit.channel_checkout_url,
                "channel_status": deposit.channel_status,
            },
            message="已返回现有 Stripe 收款页。 (Returning existing Stripe checkout session.)",
        )

    stripe.api_key = settings.stripe_secret_key
    metadata = {
        "deposit_order_id": str(deposit.id),
        "user_id": str(deposit.user_id),
        "reference": deposit.reference,
    }
    checkout_payload: dict[str, Any] = {
        "mode": "payment",
        "success_url": request.success_url or settings.stripe_checkout_success_url,
        "cancel_url": request.cancel_url or settings.stripe_checkout_cancel_url,
        "line_items": [
            {
                "price_data": {
                    "currency": deposit.source_currency.lower(),
                    "product_data": {
                        "name": f"PayFi Balance Deposit {deposit.reference}",
                        "description": f"Convert fiat to {deposit.target_currency} platform balance",
                    },
                    "unit_amount": _to_fiat_minor_units(deposit.source_amount),
                },
                "quantity": 1,
            }
        ],
        "metadata": metadata,
        "payment_intent_data": {"metadata": metadata},
    }
    checkout_locale = _normalize_stripe_checkout_locale(request.locale)
    if checkout_locale:
        checkout_payload["locale"] = checkout_locale
    try:
        checkout_session = stripe.checkout.Session.create(**checkout_payload)
    except Exception as exc:
        return StartDepositStripePaymentResponse(
            status="failed",
            deposit_order=_to_deposit_view(deposit),
            next_action="none",
            checkout=None,
            message=_format_stripe_checkout_failure(exc),
        )

    deposit.status = FiatDepositOrderStatus.AWAITING_CHANNEL_PAYMENT.value
    deposit.channel_status = "awaiting_payment"
    deposit.next_action = "open_checkout"
    deposit.channel_checkout_session_id = str(_stripe_get(checkout_session, "id") or "") or None
    deposit.channel_checkout_url = _stripe_get(checkout_session, "url")
    payment_intent_id = _stripe_get(checkout_session, "payment_intent")
    if isinstance(payment_intent_id, dict):
        payment_intent_id = payment_intent_id.get("id")
    deposit.channel_payment_id = str(payment_intent_id) if payment_intent_id else deposit.channel_payment_id
    if kyc is not None:
        deposit.kyc_verification_id = kyc.id
    session.add(deposit)
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_user_id=deposit.user_id,
            entity_type="fiat_deposit_order",
            entity_id=deposit.id,
            action="stripe_checkout_session_created",
            before_json=None,
            after_json={
                "status": deposit.status,
                "channel_status": deposit.channel_status,
                "channel_checkout_session_id": deposit.channel_checkout_session_id,
                "channel_payment_id": deposit.channel_payment_id,
            },
            trace_id=_deposit_trace_id(deposit.id),
        )
    )
    session.commit()
    session.refresh(deposit)
    return StartDepositStripePaymentResponse(
        status="ok",
        deposit_order=_to_deposit_view(deposit),
        next_action="open_checkout",
        checkout={
            "provider": "stripe",
            "checkout_session_id": deposit.channel_checkout_session_id,
            "checkout_url": deposit.channel_checkout_url,
            "payment_intent_id": deposit.channel_payment_id,
            "channel_status": deposit.channel_status,
        },
        message="Stripe 收款页已准备好，请完成法币充值。 (Stripe checkout is ready; complete the fiat deposit.)",
    )


def sync_deposit_stripe_payment_status(
    session: Session,
    *,
    deposit_order_id: UUID,
) -> DepositDetailResponse:
    settings = get_settings()
    deposit = session.execute(
        select(FiatDepositOrder)
        .where(FiatDepositOrder.id == deposit_order_id)
        .with_for_update()
    ).scalar_one_or_none()
    if deposit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"deposit_order not found: {deposit_order_id}")
    if stripe is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stripe SDK is not installed.")
    stripe.api_key = settings.stripe_secret_key
    if not deposit.channel_checkout_session_id:
        return get_deposit_detail(session=session, deposit_order_id=deposit_order_id)

    try:
        checkout_session = stripe.checkout.Session.retrieve(
            deposit.channel_checkout_session_id,
            expand=["payment_intent"],
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to sync Stripe checkout: {exc}") from exc

    payment_intent = _stripe_get(checkout_session, "payment_intent")
    if isinstance(payment_intent, dict):
        payment_intent_id = payment_intent.get("id")
        payment_intent_status = payment_intent.get("status")
    else:
        payment_intent_id = payment_intent
        payment_intent_status = None

    deposit.channel_payment_id = str(payment_intent_id) if payment_intent_id else deposit.channel_payment_id
    deposit.webhook_received_at = datetime.now(timezone.utc)
    checkout_status = str(_stripe_get(checkout_session, "status") or "").lower()
    payment_status = str(_stripe_get(checkout_session, "payment_status") or "").lower()
    if payment_status == "paid" or payment_intent_status == "succeeded":
        effective_kyc = _load_effective_kyc_for_deposit(session=session, deposit=deposit)
        requires_kyc = bool(settings.settlement_require_kyc)
        if requires_kyc and (effective_kyc is None or effective_kyc.status != KycVerificationStatus.VERIFIED.value):
            deposit.status = FiatDepositOrderStatus.BLOCKED.value
            deposit.channel_status = "blocked_kyc_required"
            deposit.next_action = "complete_kyc"
            meta = dict(deposit.metadata_json or {}) if isinstance(deposit.metadata_json, dict) else {}
            meta["blocked_reason"] = "KYC_REQUIRED_NOT_VERIFIED"
            meta["blocked_at"] = datetime.now(timezone.utc).isoformat()
            deposit.metadata_json = meta
        else:
            deposit.channel_status = "payment_processing"
            deposit.channel_confirmed_at = deposit.channel_confirmed_at or datetime.now(timezone.utc)
            if deposit.status != FiatDepositOrderStatus.CREDITED.value:
                deposit.status = FiatDepositOrderStatus.PAYMENT_PROCESSING.value
                deposit.next_action = "credit_balance"
                credit_deposit_order_to_balance(
                    session=session,
                    deposit_order=deposit,
                    actor_user_id=deposit.user_id,
                    trace_id=_deposit_trace_id(deposit.id),
                )
    elif checkout_status == "expired":
        deposit.status = FiatDepositOrderStatus.FAILED.value
        deposit.channel_status = "checkout_expired"
        deposit.next_action = "none"
    else:
        deposit.status = FiatDepositOrderStatus.AWAITING_CHANNEL_PAYMENT.value
        deposit.channel_status = "awaiting_payment"
        deposit.next_action = "wait_channel_confirmation"

    session.add(deposit)
    session.commit()
    return get_deposit_detail(session=session, deposit_order_id=deposit_order_id)


def get_deposit_detail(
    session: Session,
    *,
    deposit_order_id: UUID,
) -> DepositDetailResponse:
    deposit = session.get(FiatDepositOrder, deposit_order_id)
    if deposit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"deposit_order not found: {deposit_order_id}")

    account = session.execute(
        select(PlatformBalanceAccount)
        .where(
            PlatformBalanceAccount.user_id == deposit.user_id,
            PlatformBalanceAccount.currency == deposit.target_currency,
        )
        .limit(1)
    ).scalar_one_or_none()
    latest_ledger = None
    if account is not None:
        latest_ledger = session.execute(
            select(PlatformBalanceLedgerEntry)
            .where(
                PlatformBalanceLedgerEntry.account_id == account.id,
                PlatformBalanceLedgerEntry.reference_type == "fiat_deposit_order",
                PlatformBalanceLedgerEntry.reference_id == deposit.id,
            )
            .order_by(PlatformBalanceLedgerEntry.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    return DepositDetailResponse(
        deposit_order=_to_deposit_view(deposit),
        account=_to_account_view(account) if account is not None else None,
        latest_ledger_entry=_to_ledger_view(latest_ledger) if latest_ledger is not None else None,
    )


def preview_payment_from_balance(
    session: Session,
    *,
    request: BalancePaymentPreviewRequest,
) -> BalancePaymentPreviewResponse:
    _require_balance_kyc(session=session, user_id=request.user_id)
    command_response = handle_command(
        session=session,
        request=CommandRequest(
            user_id=request.user_id,
            text=request.prompt,
            execution_mode=request.execution_mode,
            channel="platform_balance",
            locale=request.locale,
        ),
    )

    currency = None
    amount = None
    if command_response.preview_summary:
        currency = command_response.preview_summary.currency
        amount = command_response.preview_summary.amount
    balance_check, account_view = _build_balance_check_for_preview(
        session=session,
        user_id=request.user_id,
        currency=currency,
        amount=amount,
    )
    payload = command_response.model_dump()
    payload["funding_source"] = BALANCE_FUNDING_SOURCE
    payload["balance_account"] = account_view.model_dump() if account_view is not None else None
    payload["balance_check"] = balance_check.model_dump() if balance_check is not None else None
    if balance_check is not None and not balance_check.sufficient and payload.get("status") == "ok":
        payload["next_action"] = "top_up_balance"
        payload["message"] = (
            balance_check.reason
            or "平台余额不足，请先充值后再确认结算。 (Insufficient platform balance; top up before settlement.)"
        )
    return BalancePaymentPreviewResponse(**payload)


def confirm_payment_from_balance(
    session: Session,
    *,
    request: BalancePaymentConfirmRequest,
) -> BalancePaymentConfirmResponse:
    _require_balance_kyc(session=session, user_id=request.user_id)
    command = session.get(CommandExecution, request.command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"command not found: {request.command_id}")
    if command.user_id != request.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="command does not belong to the user")

    amount, currency = _extract_command_amount_and_currency(command)
    if amount is None or currency is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="command is missing amount/currency")
    if currency not in STABLECOIN_SET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="platform balance payments currently support stablecoin-denominated settlements only",
        )

    account = get_or_create_balance_account(
        session=session,
        user_id=request.user_id,
        currency=currency,
        lock=True,
    )
    trace_id = _balance_payment_trace_id(command.id)
    try:
        balance_lock = create_balance_lock_for_command(
            session=session,
            account=account,
            command_id=command.id,
            currency=currency,
            amount=amount,
            actor_user_id=request.user_id,
            trace_id=trace_id,
            metadata={"idempotency_key": request.idempotency_key},
        )
    except ValueError as exc:
        reason = str(exc)
        if reason == "insufficient_balance":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="insufficient platform balance") from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason) from exc

    confirm_response = handle_confirm(
        session=session,
        request=ConfirmRequest(
            command_id=request.command_id,
            confirmed=True,
            execution_mode=request.execution_mode,
            idempotency_key=request.idempotency_key,
            actor_user_id=request.user_id,
            note=request.note,
            locale=request.locale,
        ),
    )

    if confirm_response.payment_order_id is not None:
        payment_order = session.get(PaymentOrder, confirm_response.payment_order_id)
        if payment_order is not None:
            bind_balance_lock_to_payment(session=session, payment_order=payment_order)
            settle_balance_lock_for_payment(
                session=session,
                payment_order=payment_order,
                actor_user_id=request.user_id,
                trace_id=confirm_response.audit_trace_id,
            )
            session.add(payment_order)
    elif confirm_response.status in {"blocked", "validation_error", "failed"}:
        release_balance_lock_without_payment(
            session=session,
            balance_lock=balance_lock,
            actor_user_id=request.user_id,
            trace_id=trace_id,
            reason=confirm_response.status,
        )

    session.commit()
    account = get_or_create_balance_account(
        session=session,
        user_id=request.user_id,
        currency=currency,
        lock=False,
    )
    balance_lock = load_balance_lock_by_command(session=session, command_id=command.id, lock=False) or balance_lock
    payload = confirm_response.model_dump()
    payload["funding_source"] = BALANCE_FUNDING_SOURCE
    payload["balance_account"] = _to_account_view(account).model_dump()
    payload["balance_lock"] = _to_lock_view(balance_lock).model_dump() if balance_lock is not None else None
    return BalancePaymentConfirmResponse(**payload)


def _require_user(*, session: Session, user_id: UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"user not found: {user_id}")
    return user


def _load_balance_kyc(*, session: Session, user_id: UUID) -> KycVerification | None:
    settings = get_settings()
    return _load_latest_kyc_for_subject(
        session=session,
        subject_type="user",
        subject_id=user_id,
        provider=settings.settlement_kyc_provider,
    )


def _require_balance_kyc(*, session: Session, user_id: UUID) -> KycVerification:
    _require_user(session=session, user_id=user_id)
    kyc = _load_balance_kyc(session=session, user_id=user_id)
    if bool(get_settings().settlement_require_kyc) and (
        kyc is None or kyc.status != KycVerificationStatus.VERIFIED.value
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="kyc verification is required before using platform balance",
        )
    if kyc is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="kyc verification is required")
    return kyc


def _build_balance_check_for_preview(
    *,
    session: Session,
    user_id: UUID,
    currency: str | None,
    amount: float | None,
) -> tuple[BalanceCheckSummary | None, PlatformBalanceAccountView | None]:
    if not currency:
        return (
            BalanceCheckSummary(
                currency="UNKNOWN",
                available_balance=0,
                locked_balance=0,
                required_amount=None,
                sufficient=False,
                reason="AI 仍需补充币种后才能校验平台余额。 (Currency is still missing for balance validation.)",
            ),
            None,
        )
    normalized_currency = currency.upper().strip()
    if normalized_currency not in STABLECOIN_SET:
        return (
            BalanceCheckSummary(
                currency=normalized_currency,
                available_balance=0,
                locked_balance=0,
                required_amount=amount,
                sufficient=False,
                reason="平台余额支付当前只支持稳定币面额。 (Platform balance currently supports stablecoin-denominated settlements only.)",
            ),
            None,
        )

    account = get_or_create_balance_account(
        session=session,
        user_id=user_id,
        currency=normalized_currency,
        lock=False,
    )
    account_view = _to_account_view(account)
    required_amount = float(amount) if amount is not None else None
    sufficient = required_amount is not None and float(account.available_balance) >= required_amount
    return (
        BalanceCheckSummary(
            currency=normalized_currency,
            available_balance=float(account.available_balance),
            locked_balance=float(account.locked_balance),
            required_amount=required_amount,
            sufficient=sufficient,
            reason=(
                None
                if sufficient
                else "平台可用稳定币余额不足。 (Available platform stablecoin balance is insufficient.)"
            ),
        ),
        account_view,
    )


def _extract_command_amount_and_currency(command: CommandExecution) -> tuple[Decimal | None, str | None]:
    parsed = command.parsed_intent_json if isinstance(command.parsed_intent_json, dict) else {}
    fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {}
    raw_amount = fields.get("amount")
    raw_currency = fields.get("currency")
    try:
        amount = quantize_token_amount(Decimal(str(raw_amount))) if raw_amount is not None else None
    except Exception:
        amount = None
    currency = str(raw_currency).upper().strip() if raw_currency else None
    return amount, currency


def _to_account_view(account: Any) -> PlatformBalanceAccountView:
    return PlatformBalanceAccountView(
        id=account.id,
        user_id=account.user_id,
        currency=account.currency,
        available_balance=float(account.available_balance),
        locked_balance=float(account.locked_balance),
        status=account.status,
        metadata_json=account.metadata_json,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _to_ledger_view(entry: Any) -> PlatformBalanceLedgerEntryView:
    return PlatformBalanceLedgerEntryView(
        id=entry.id,
        account_id=entry.account_id,
        entry_type=entry.entry_type,
        amount=float(entry.amount),
        balance_before=float(entry.balance_before),
        balance_after=float(entry.balance_after),
        reference_type=entry.reference_type,
        reference_id=entry.reference_id,
        description=entry.description,
        metadata_json=entry.metadata_json,
        created_at=entry.created_at,
    )


def _to_lock_view(balance_lock: Any) -> PlatformBalanceLockView:
    return PlatformBalanceLockView(
        id=balance_lock.id,
        account_id=balance_lock.account_id,
        command_id=balance_lock.command_id,
        payment_order_id=balance_lock.payment_order_id,
        currency=balance_lock.currency,
        locked_amount=float(balance_lock.locked_amount),
        consumed_amount=float(balance_lock.consumed_amount),
        released_amount=float(balance_lock.released_amount),
        status=balance_lock.status,
        metadata_json=balance_lock.metadata_json,
        created_at=balance_lock.created_at,
        updated_at=balance_lock.updated_at,
    )


def _to_deposit_view(deposit: FiatDepositOrder) -> FiatDepositOrderView:
    return FiatDepositOrderView(
        id=deposit.id,
        user_id=deposit.user_id,
        source_currency=deposit.source_currency,
        source_amount=float(deposit.source_amount),
        target_currency=deposit.target_currency,
        target_amount=float(deposit.target_amount),
        fx_rate=float(deposit.fx_rate),
        fee_amount=float(deposit.fee_amount),
        payment_channel=deposit.payment_channel,
        channel_payment_id=deposit.channel_payment_id,
        channel_checkout_session_id=deposit.channel_checkout_session_id,
        channel_checkout_url=deposit.channel_checkout_url,
        channel_status=deposit.channel_status,
        channel_confirmed_at=deposit.channel_confirmed_at,
        webhook_received_at=deposit.webhook_received_at,
        kyc_verification_id=deposit.kyc_verification_id,
        status=deposit.status,
        next_action=deposit.next_action,
        reference=deposit.reference,
        failure_reason=deposit.failure_reason,
        metadata_json=deposit.metadata_json,
        created_at=deposit.created_at,
        updated_at=deposit.updated_at,
    )


def _build_deposit_reference() -> str:
    return f"DEP-{uuid.uuid4().hex[:8].upper()}"


def _deposit_trace_id(deposit_order_id: UUID) -> str:
    return f"trace-deposit-{deposit_order_id.hex[:12]}"


def _balance_payment_trace_id(command_id: UUID) -> str:
    return f"trace-balance-{command_id.hex[:12]}"
