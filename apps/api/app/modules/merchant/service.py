from __future__ import annotations

import socket
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

try:
    import stripe
except Exception:  # pragma: no cover - dependency guard for local environments
    stripe = None

from app.core.config import get_settings
from app.db.models import (
    AuditLog,
    Beneficiary,
    CommandExecution,
    CommandExecutionStatus,
    ConversationSession,
    FiatCollection,
    FiatCollectionStatus,
    FiatDepositOrder,
    FiatDepositOrderStatus,
    FiatPaymentIntent,
    FiatPaymentIntentStatus,
    KycVerification,
    KycVerificationStatus,
    PaymentExecutionBatch,
    PaymentExecutionItem,
    SettlementQuote,
    SettlementQuoteStatus,
    SessionStatus,
    StablecoinPayoutLink,
    User,
)
from app.modules.balance.lifecycle import credit_deposit_order_to_balance
from app.modules.audit.service import build_audit_timeline_items
from app.modules.confirm.durable_service import handle_confirm
from app.modules.confirm.schemas import ConfirmRequest
from app.modules.merchant.schemas import (
    CreateStripeSessionRequest,
    CreateStripeSessionResponse,
    CreateFiatPaymentRequest,
    CreateFiatPaymentResponse,
    FiatCollectionView,
    FiatPaymentCollectionInstructions,
    FiatPaymentIntentView,
    MarkFiatReceivedRequest,
    MarkFiatReceivedResponse,
    MerchantFiatPaymentDetailResponse,
    MerchantFiatPaymentListItem,
    MerchantFiatPaymentListResponse,
    MerchantPayoutStatusView,
    MerchantTimeline,
    KycVerificationView,
    SettlementQuoteRequest,
    SettlementQuoteResponse,
    SettlementQuoteView,
    StablecoinPayoutLinkView,
)
from app.modules.payments.service import get_payment_detail

STABLECOIN_SET = {"USDT", "USDC"}
FIAT_UNIT = Decimal("0.01")
TOKEN_UNIT = Decimal("0.000001")
BPS_DENOM = Decimal("10000")

FX_RATE_MAP: dict[str, Decimal] = {
    "USD": Decimal("1.0000"),
    "USDT": Decimal("1.0000"),
    "USDC": Decimal("1.0000"),
    "EUR": Decimal("1.0800"),
    "CNY": Decimal("0.1380"),
    "SGD": Decimal("0.7400"),
    "HKD": Decimal("0.1280"),
}

STRIPE_CHANNEL = "stripe"
MANUAL_CHANNEL = "manual"
SUPPORTED_FIAT_CHANNELS = {STRIPE_CHANNEL, MANUAL_CHANNEL}

_STRIPE_PLACEHOLDER_MARKERS = (
    "REPLACE_WITH",
    "YOUR_",
    "真实测试值",
    "example",
)

_STRIPE_CHECKOUT_ALLOWED_LOCALES = (
    "auto",
    "bg",
    "cs",
    "da",
    "de",
    "el",
    "en",
    "en-GB",
    "es",
    "es-419",
    "et",
    "fi",
    "fil",
    "fr",
    "fr-CA",
    "hr",
    "hu",
    "id",
    "it",
    "ja",
    "ko",
    "lt",
    "lv",
    "ms",
    "mt",
    "nb",
    "nl",
    "pl",
    "pt",
    "pt-BR",
    "ro",
    "ru",
    "sk",
    "sl",
    "sv",
    "th",
    "tr",
    "vi",
    "zh",
    "zh-HK",
    "zh-TW",
)


def _resolve_host_ipv4(hostname: str) -> str | None:
    try:
        return socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)[0][4][0]
    except Exception:
        return None


def _stripe_network_diagnostic(exc: Exception) -> str | None:
    message = str(exc).lower()
    if not any(token in message for token in ("ssl", "certificate", "eof", "tls", "ssl_error_syscall")):
        return None

    api_ip = _resolve_host_ipv4("api.stripe.com")
    checkout_ip = _resolve_host_ipv4("checkout.stripe.com")
    fake_ip_hit = any(ip and ip.startswith("198.18.") for ip in (api_ip, checkout_ip))

    if fake_ip_hit:
        return (
            "检测到本机代理或 DNS 将 Stripe 域名解析到了 198.18.x.x 的 fake-IP，"
            "Python/Stripe SDK 会直接连到这个拦截地址而导致 TLS 握手失败。"
            "请在代理软件中将 api.stripe.com 和 checkout.stripe.com 设为直连 / bypass，"
            "或关闭 fake-IP 模式后重试。 "
            "(Local proxy/DNS is resolving Stripe domains to 198.18.x fake-IP. "
            "Put api.stripe.com and checkout.stripe.com on direct/bypass or disable fake-IP mode, then retry.)"
        )

    return None


def _format_stripe_checkout_failure(exc: Exception) -> str:
    detail = f"Stripe 会话创建失败：{exc} (Failed to create Stripe checkout session.)"
    diagnostic = _stripe_network_diagnostic(exc)
    if diagnostic:
        return f"{detail} {diagnostic}"
    return detail
_STRIPE_CHECKOUT_LOCALE_LOOKUP = {locale.lower(): locale for locale in _STRIPE_CHECKOUT_ALLOWED_LOCALES}


def _validate_stripe_secret_key(secret_key: str | None) -> tuple[bool, str]:
    if not secret_key or not secret_key.strip():
        return False, "missing"
    normalized = secret_key.strip()
    lowered = normalized.lower()
    if any(marker.lower() in lowered for marker in _STRIPE_PLACEHOLDER_MARKERS):
        return False, "placeholder"
    try:
        normalized.encode("ascii")
    except UnicodeEncodeError:
        return False, "non_ascii"
    if not (normalized.startswith("sk_test_") or normalized.startswith("sk_live_")):
        return False, "invalid_prefix"
    return True, "ok"


def _normalize_stripe_checkout_locale(locale: str | None) -> str | None:
    if not locale:
        return None
    requested = locale.strip()
    if not requested:
        return None
    normalized_key = requested.replace("_", "-").lower()
    alias_map = {
        "zh-cn": "zh",
        "zh-sg": "zh",
        "zh-hans": "zh",
        "en-us": "en",
    }
    canonical = alias_map.get(normalized_key, _STRIPE_CHECKOUT_LOCALE_LOOKUP.get(normalized_key))
    return canonical


def _resolve_stripe_checkout_redirect_url(
    *,
    requested_url: str | None,
    default_url: str,
    settings,
    field_name: str,
) -> str:
    candidate = (requested_url or default_url or "").strip()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be configured",
        )
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be an absolute http(s) URL",
        )
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    allowed = {item.rstrip("/") for item in settings.stripe_checkout_allowed_origins if item.strip()}
    if origin not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} origin is not allowed: {origin}",
        )
    return candidate


def create_settlement_quote(session: Session, request: SettlementQuoteRequest) -> SettlementQuoteResponse:
    merchant = session.get(User, request.merchant_id)
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"merchant not found: {request.merchant_id}")
    beneficiary = session.get(Beneficiary, request.beneficiary_id)
    if beneficiary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"beneficiary not found: {request.beneficiary_id}")

    source_currency = request.source_currency.upper().strip()
    target_currency = request.target_currency.upper().strip()
    target_network = request.target_network.strip().lower()
    if target_currency not in STABLECOIN_SET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"target_currency must be stablecoin in {sorted(STABLECOIN_SET)}",
        )
    fx_rate = _resolve_fx_rate(source_currency=source_currency, target_currency=target_currency)
    source_amount = Decimal(str(request.source_amount)).quantize(FIAT_UNIT, rounding=ROUND_DOWN)
    if source_amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_amount must be > 0")

    settings = get_settings()
    spread_bps = int(settings.settlement_spread_bps)
    platform_fee_bps = int(settings.settlement_platform_fee_bps)
    min_platform_fee = Decimal(str(settings.settlement_min_platform_fee)).quantize(TOKEN_UNIT, rounding=ROUND_UP)
    network_fee = Decimal(str(settings.settlement_network_fee)).quantize(TOKEN_UNIT, rounding=ROUND_UP)

    gross_target_amount = (source_amount * fx_rate).quantize(TOKEN_UNIT, rounding=ROUND_DOWN)
    spread_fee = (gross_target_amount * Decimal(spread_bps) / BPS_DENOM).quantize(TOKEN_UNIT, rounding=ROUND_UP)
    platform_fee = (gross_target_amount * Decimal(platform_fee_bps) / BPS_DENOM).quantize(
        TOKEN_UNIT, rounding=ROUND_UP
    )
    if platform_fee < min_platform_fee:
        platform_fee = min_platform_fee
    total_fee = (spread_fee + platform_fee + network_fee).quantize(TOKEN_UNIT, rounding=ROUND_UP)
    target_amount = (gross_target_amount - total_fee).quantize(TOKEN_UNIT, rounding=ROUND_DOWN)
    if target_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quote target amount is non-positive; increase source_amount",
        )

    quote = SettlementQuote(
        id=uuid.uuid4(),
        merchant_id=merchant.id,
        beneficiary_id=beneficiary.id,
        source_currency=source_currency,
        source_amount=source_amount,
        target_currency=target_currency,
        target_amount=target_amount,
        target_network=target_network,
        fx_rate=fx_rate,
        platform_fee=platform_fee,
        network_fee=network_fee,
        spread_bps=spread_bps,
        total_fee_amount=total_fee,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=max(60, settings.settlement_quote_ttl_seconds)),
        status=SettlementQuoteStatus.ACTIVE.value,
        quote_payload_json={
            "gross_target_amount": float(gross_target_amount),
            "spread_fee": float(spread_fee),
            "platform_fee_bps": platform_fee_bps,
            "platform_fee_min": float(min_platform_fee),
            "pricing_mode": "deterministic_mock",
            "target_network": target_network,
        },
    )
    session.add(quote)
    session.add(
        _build_audit(
            actor_user_id=merchant.id,
            entity_type="settlement_quote",
            entity_id=quote.id,
            action="settlement_quote_created",
            trace_id=f"trace-quote-{quote.id.hex[:12]}",
            before_json=None,
            after_json={
                "source_currency": source_currency,
                "source_amount": float(source_amount),
                "target_currency": target_currency,
                "target_amount": float(target_amount),
                "expires_at": quote.expires_at.isoformat(),
            },
        )
    )
    session.commit()
    session.refresh(quote)

    return SettlementQuoteResponse(
        status="ok",
        quote=_to_quote_view(quote),
        next_action="create_fiat_payment_intent",
        message="报价已生成，请创建法币支付意图。 (Quote created; proceed to create fiat payment intent.)",
    )


def create_fiat_payment_intent(session: Session, request: CreateFiatPaymentRequest) -> CreateFiatPaymentResponse:
    quote = session.get(SettlementQuote, request.quote_id)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"quote not found: {request.quote_id}")
    merchant = session.get(User, request.merchant_id)
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"merchant not found: {request.merchant_id}")

    if quote.merchant_id != merchant.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="quote does not belong to merchant")
    if request.beneficiary_id is not None and request.beneficiary_id != quote.beneficiary_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="beneficiary_id does not match quote")

    settings = get_settings()
    payment_channel = (settings.settlement_fiat_channel or STRIPE_CHANNEL).strip().lower()
    if payment_channel not in SUPPORTED_FIAT_CHANNELS:
        payment_channel = STRIPE_CHANNEL
    requires_kyc = bool(settings.settlement_require_kyc)
    latest_kyc = _load_latest_kyc_for_subject(
        session=session,
        subject_type="merchant",
        subject_id=merchant.id,
        provider=settings.settlement_kyc_provider,
    )

    existing_intent = session.execute(
        select(FiatPaymentIntent).where(FiatPaymentIntent.quote_id == quote.id).limit(1)
    ).scalar_one_or_none()
    if existing_intent is not None:
        existing_next_action = _resolve_fiat_next_action(existing_intent)
        return CreateFiatPaymentResponse(
            status="ok",
            fiat_payment=_to_intent_view(existing_intent),
            quote=_to_quote_view(quote),
            collection_instructions=_build_collection_instructions(existing_intent),
            next_action=existing_next_action,
            message="该报价已创建支付意图，返回已有记录。 (Fiat payment intent already exists for this quote.)",
        )

    now = datetime.now(timezone.utc)
    if quote.status == SettlementQuoteStatus.ACTIVE.value and quote.expires_at <= now:
        quote.status = SettlementQuoteStatus.EXPIRED.value
        session.add(quote)
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="quote expired")
    if quote.status != SettlementQuoteStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"quote status is {quote.status}")

    initial_status = FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value
    initial_channel_status = "awaiting_payment"
    if payment_channel == MANUAL_CHANNEL:
        initial_status = FiatPaymentIntentStatus.AWAITING_FIAT.value
        initial_channel_status = "manual_pending"
    elif requires_kyc and (latest_kyc is None or latest_kyc.status != KycVerificationStatus.VERIFIED.value):
        initial_status = FiatPaymentIntentStatus.AWAITING_KYC.value
        initial_channel_status = "blocked_kyc_required"

    intent = FiatPaymentIntent(
        id=uuid.uuid4(),
        merchant_id=quote.merchant_id,
        beneficiary_id=quote.beneficiary_id,
        quote_id=quote.id,
        payer_currency=quote.source_currency,
        payer_amount=quote.source_amount,
        target_stablecoin=quote.target_currency,
        target_amount=quote.target_amount,
        target_network=quote.target_network,
        status=initial_status,
        payment_channel=payment_channel,
        channel_status=initial_channel_status,
        reference=(request.reference or f"FIAT-{uuid.uuid4().hex[:8].upper()}")[:64],
        source_text=request.source_text,
        kyc_verification_id=latest_kyc.id if latest_kyc is not None else None,
        metadata_json={
            "split_count": request.split_count,
            "quote_expires_at": quote.expires_at.isoformat(),
            "kyc_required": requires_kyc,
        },
    )
    _sync_intent_next_action(intent)
    quote.status = SettlementQuoteStatus.ACCEPTED.value
    trace_id = _fiat_trace_id(intent.id)
    session.add(intent)
    session.add(quote)
    session.add(
        _build_audit(
            actor_user_id=merchant.id,
            entity_type="settlement_quote",
            entity_id=quote.id,
            action="settlement_quote_accepted",
            trace_id=trace_id,
            before_json={"status": SettlementQuoteStatus.ACTIVE.value},
            after_json={"status": SettlementQuoteStatus.ACCEPTED.value},
        )
    )
    session.add(
        _build_audit(
            actor_user_id=merchant.id,
            entity_type="fiat_payment_intent",
            entity_id=intent.id,
            action="fiat_payment_intent_created",
            trace_id=trace_id,
            before_json=None,
            after_json={
                "status": intent.status,
                "payment_channel": intent.payment_channel,
                "channel_status": intent.channel_status,
                "reference": intent.reference,
                "payer_amount": float(intent.payer_amount),
                "payer_currency": intent.payer_currency,
                "target_amount": float(intent.target_amount),
                "target_stablecoin": intent.target_stablecoin,
            },
        )
    )
    session.commit()
    session.refresh(intent)
    session.refresh(quote)
    next_action = _resolve_fiat_next_action(intent)
    message = "法币支付意图已创建，等待法币到账确认。 (Fiat payment intent created; waiting for fiat receipt confirmation.)"
    if next_action == "start_kyc":
        message = "法币支付意图已创建，需先完成 KYC。 (Fiat payment intent created; complete KYC before payment.)"
    elif next_action == "create_stripe_session":
        message = "法币支付意图已创建，请创建 Stripe 支付会话。 (Fiat payment intent created; create Stripe session to proceed.)"
    elif next_action == "wait_channel_confirmation":
        message = "支付通道处理中，等待 Stripe 确认。 (Payment channel is processing; waiting for Stripe confirmation.)"

    return CreateFiatPaymentResponse(
        status="ok",
        fiat_payment=_to_intent_view(intent),
        quote=_to_quote_view(quote),
        collection_instructions=_build_collection_instructions(intent),
        next_action=next_action,
        message=message,
    )


def create_stripe_checkout_session(
    session: Session,
    *,
    fiat_payment_intent_id: UUID,
    request: CreateStripeSessionRequest,
) -> CreateStripeSessionResponse:
    settings = get_settings()
    intent = session.execute(
        select(FiatPaymentIntent)
        .where(FiatPaymentIntent.id == fiat_payment_intent_id)
        .with_for_update()
    ).scalar_one_or_none()
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"fiat_payment_intent not found: {fiat_payment_intent_id}",
        )
    quote = session.get(SettlementQuote, intent.quote_id)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"quote not found: {intent.quote_id}")

    if intent.payment_channel != STRIPE_CHANNEL:
        return CreateStripeSessionResponse(
            status="validation_error",
            fiat_payment=_to_intent_view(intent),
            quote=_to_quote_view(quote),
            next_action="none",
            checkout=None,
            message="当前支付意图不是 Stripe 通道。 (This fiat payment intent is not using Stripe channel.)",
        )

    if intent.status in {
        FiatPaymentIntentStatus.COMPLETED.value,
        FiatPaymentIntentStatus.CANCELLED.value,
        FiatPaymentIntentStatus.FAILED.value,
        FiatPaymentIntentStatus.BLOCKED.value,
    }:
        return CreateStripeSessionResponse(
            status="validation_error",
            fiat_payment=_to_intent_view(intent),
            quote=_to_quote_view(quote),
            next_action="none",
            checkout=None,
            message=f"当前状态 {intent.status} 不允许创建 Stripe 会话。 (Current status {intent.status} is not eligible.)",
        )

    kyc = _load_effective_kyc_for_intent(session=session, intent=intent)
    requires_kyc = bool(settings.settlement_require_kyc)
    if requires_kyc and (kyc is None or kyc.status != KycVerificationStatus.VERIFIED.value):
        intent.status = FiatPaymentIntentStatus.AWAITING_KYC.value
        intent.channel_status = "blocked_kyc_required"
        if kyc is not None:
            intent.kyc_verification_id = kyc.id
        _sync_intent_next_action(intent)
        session.add(intent)
        session.commit()
        session.refresh(intent)
        return CreateStripeSessionResponse(
            status="validation_error",
            fiat_payment=_to_intent_view(intent),
            quote=_to_quote_view(quote),
            next_action="complete_kyc",
            checkout=None,
            message="需要先完成 KYC，才能创建 Stripe 支付会话。 (Complete KYC before creating Stripe checkout session.)",
        )

    stripe_key_valid, stripe_key_reason = _validate_stripe_secret_key(settings.stripe_secret_key)
    if not stripe_key_valid:
        message_by_reason = {
            "missing": "未配置 STRIPE_SECRET_KEY，无法创建支付会话。 (STRIPE_SECRET_KEY is missing.)",
            "placeholder": "STRIPE_SECRET_KEY 仍是占位值，请替换为真实 Stripe 测试密钥。 (STRIPE_SECRET_KEY is still a placeholder value; set a real Stripe test key.)",
            "non_ascii": "STRIPE_SECRET_KEY 包含非法字符，请使用真实 ASCII Stripe 密钥。 (STRIPE_SECRET_KEY contains invalid characters; use a real ASCII Stripe key.)",
            "invalid_prefix": "STRIPE_SECRET_KEY 格式无效，应以 sk_test_ 或 sk_live_ 开头。 (Invalid STRIPE_SECRET_KEY format; expected sk_test_ or sk_live_.)",
        }
        return CreateStripeSessionResponse(
            status="failed",
            fiat_payment=_to_intent_view(intent),
            quote=_to_quote_view(quote),
            next_action="none",
            checkout=None,
            message=message_by_reason.get(
                stripe_key_reason,
                "STRIPE_SECRET_KEY 无效，无法创建支付会话。 (Invalid STRIPE_SECRET_KEY.)",
            ),
        )
    if stripe is None:
        return CreateStripeSessionResponse(
            status="failed",
            fiat_payment=_to_intent_view(intent),
            quote=_to_quote_view(quote),
            next_action="none",
            checkout=None,
            message="Stripe SDK 未安装。 (Stripe SDK is not installed.)",
        )

    # Reuse the currently open checkout session when it already exists.
    if (
        intent.channel_checkout_session_id
        and intent.channel_checkout_url
        and intent.channel_status in {"awaiting_payment", "payment_processing", "checkout_session_created", "checkout_completed"}
    ):
        _sync_intent_next_action(intent)
        return CreateStripeSessionResponse(
            status="ok",
            fiat_payment=_to_intent_view(intent),
            quote=_to_quote_view(quote),
            next_action="open_checkout",
            checkout={
                "provider": "stripe",
                "checkout_session_id": intent.channel_checkout_session_id,
                "checkout_url": intent.channel_checkout_url,
                "channel_status": intent.channel_status,
            },
            message="已存在可用 Stripe 会话，返回当前会话。 (Returning existing Stripe checkout session.)",
        )

    stripe.api_key = settings.stripe_secret_key
    amount_minor = _to_fiat_minor_units(intent.payer_amount)
    currency = intent.payer_currency.lower()
    if amount_minor <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payer_amount must be positive")
    metadata = {
        "fiat_payment_intent_id": str(intent.id),
        "quote_id": str(intent.quote_id),
        "merchant_id": str(intent.merchant_id),
        "beneficiary_id": str(intent.beneficiary_id),
        "reference": intent.reference,
    }
    success_url = _resolve_stripe_checkout_redirect_url(
        requested_url=request.success_url,
        default_url=settings.stripe_checkout_success_url,
        settings=settings,
        field_name="success_url",
    )
    cancel_url = _resolve_stripe_checkout_redirect_url(
        requested_url=request.cancel_url,
        default_url=settings.stripe_checkout_cancel_url,
        settings=settings,
        field_name="cancel_url",
    )
    checkout_payload: dict[str, Any] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": [
            {
                "price_data": {
                    "currency": currency,
                    "product_data": {
                        "name": f"PayFi Settlement {intent.reference}",
                        "description": f"Payout {intent.target_amount} {intent.target_stablecoin}",
                    },
                    "unit_amount": amount_minor,
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
        return CreateStripeSessionResponse(
            status="failed",
            fiat_payment=_to_intent_view(intent),
            quote=_to_quote_view(quote),
            next_action="none",
            checkout=None,
            message=_format_stripe_checkout_failure(exc),
        )

    checkout_session_id = str(_stripe_get(checkout_session, "id") or "")
    checkout_url = _stripe_get(checkout_session, "url")
    payment_intent_id = _stripe_get(checkout_session, "payment_intent")
    if isinstance(payment_intent_id, dict):
        payment_intent_id = payment_intent_id.get("id")

    before_status = intent.status
    intent.status = FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value
    intent.channel_status = "awaiting_payment"
    intent.channel_checkout_session_id = checkout_session_id or None
    intent.channel_checkout_url = str(checkout_url) if checkout_url else None
    intent.channel_payment_id = str(payment_intent_id) if payment_intent_id else intent.channel_payment_id
    if kyc is not None:
        intent.kyc_verification_id = kyc.id
    _sync_intent_next_action(intent)
    session.add(intent)
    trace_id = _fiat_trace_id(intent.id)
    session.add(
        _build_audit(
            actor_user_id=intent.merchant_id,
            entity_type="fiat_payment_intent",
            entity_id=intent.id,
            action="stripe_checkout_session_created",
            trace_id=trace_id,
            before_json={"status": before_status},
            after_json={
                "status": intent.status,
                "channel_status": intent.channel_status,
                "channel_checkout_session_id": intent.channel_checkout_session_id,
                "channel_payment_id": intent.channel_payment_id,
            },
        )
    )
    session.commit()
    session.refresh(intent)
    return CreateStripeSessionResponse(
        status="ok",
        fiat_payment=_to_intent_view(intent),
        quote=_to_quote_view(quote),
        next_action="open_checkout",
        checkout={
            "provider": "stripe",
            "checkout_session_id": intent.channel_checkout_session_id,
            "checkout_url": intent.channel_checkout_url,
            "payment_intent_id": intent.channel_payment_id,
            "expires_at": _stripe_get(checkout_session, "expires_at"),
            "channel_status": intent.channel_status,
        },
        message="Stripe 支付会话已创建，请完成法币支付。 (Stripe checkout session created; complete fiat payment.)",
    )


def sync_stripe_payment_status(
    *,
    session: Session,
    fiat_payment_intent_id: UUID,
) -> MerchantFiatPaymentDetailResponse:
    intent = session.execute(
        select(FiatPaymentIntent)
        .where(FiatPaymentIntent.id == fiat_payment_intent_id)
        .with_for_update()
        .limit(1)
    ).scalar_one_or_none()
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"fiat_payment_intent not found: {fiat_payment_intent_id}",
        )
    if intent.payment_channel != STRIPE_CHANNEL:
        return get_fiat_payment_detail(session=session, fiat_payment_intent_id=fiat_payment_intent_id)

    settings = get_settings()
    if stripe is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stripe SDK is not installed.")
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="STRIPE_SECRET_KEY is required to sync Stripe payment status.",
        )

    if not intent.channel_checkout_session_id and not intent.channel_payment_id:
        return get_fiat_payment_detail(session=session, fiat_payment_intent_id=fiat_payment_intent_id)

    stripe.api_key = settings.stripe_secret_key

    payment_intent_payload: dict[str, Any] | None = None
    payment_intent_id: str | None = None
    checkout_payment_status: str | None = None
    checkout_status: str | None = None

    if intent.channel_checkout_session_id:
        checkout = stripe.checkout.Session.retrieve(
            intent.channel_checkout_session_id,
            expand=["payment_intent"],
        )
        checkout_payment_status = _safe_str(_stripe_get(checkout, "payment_status"))
        checkout_status = _safe_str(_stripe_get(checkout, "status"))
        payment_intent_obj = _stripe_get(checkout, "payment_intent")
        if isinstance(payment_intent_obj, dict):
            payment_intent_payload = payment_intent_obj
            payment_intent_id = _safe_str(payment_intent_obj.get("id"))
        elif payment_intent_obj is not None:
            payment_intent_id = _safe_str(payment_intent_obj)
    else:
        payment_intent_id = _safe_str(intent.channel_payment_id)

    if payment_intent_payload is None and payment_intent_id:
        payment_intent_obj = stripe.PaymentIntent.retrieve(payment_intent_id)
        if isinstance(payment_intent_obj, dict):
            payment_intent_payload = payment_intent_obj
        else:
            payment_intent_payload = {
                "id": _safe_str(_stripe_get(payment_intent_obj, "id")) or payment_intent_id,
                "status": _safe_str(_stripe_get(payment_intent_obj, "status")),
                "metadata": _stripe_get(payment_intent_obj, "metadata") or {},
            }

    if payment_intent_payload is None:
        return get_fiat_payment_detail(session=session, fiat_payment_intent_id=fiat_payment_intent_id)

    payment_intent_status = (_safe_str(payment_intent_payload.get("status")) or "").lower()
    payment_intent_id = _safe_str(payment_intent_payload.get("id")) or payment_intent_id
    metadata = payment_intent_payload.get("metadata") if isinstance(payment_intent_payload.get("metadata"), dict) else {}
    if "fiat_payment_intent_id" not in metadata:
        metadata = dict(metadata)
        metadata["fiat_payment_intent_id"] = str(intent.id)
        payment_intent_payload["metadata"] = metadata

    normalized_checkout_payment_status = (checkout_payment_status or "").lower()
    normalized_checkout_status = (checkout_status or "").lower()
    event_type: str | None = None
    if payment_intent_status == "succeeded" or normalized_checkout_payment_status == "paid":
        event_type = "payment_intent.succeeded"
    elif payment_intent_status in {"requires_payment_method", "payment_failed"}:
        event_type = "payment_intent.payment_failed"
    elif payment_intent_status == "canceled" or normalized_checkout_status == "expired":
        event_type = "payment_intent.canceled"

    if event_type:
        sync_event_id = f"sync:{payment_intent_id or intent.id}:{event_type}"
        _handle_payment_intent_event(
            session=session,
            event_type=event_type,
            event_id=sync_event_id,
            event_object=payment_intent_payload,
            received_at=datetime.now(timezone.utc),
        )

    return get_fiat_payment_detail(session=session, fiat_payment_intent_id=fiat_payment_intent_id)


def mark_fiat_received(
    session: Session,
    fiat_payment_intent_id: UUID,
    request: MarkFiatReceivedRequest,
) -> MarkFiatReceivedResponse:
    settings = get_settings()
    # Pessimistic lock to serialize concurrent mark-received calls for the same intent.
    intent = session.execute(
        select(FiatPaymentIntent)
        .where(FiatPaymentIntent.id == fiat_payment_intent_id)
        .with_for_update()
    ).scalar_one_or_none()
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"fiat_payment_intent not found: {fiat_payment_intent_id}",
        )
    quote = session.get(SettlementQuote, intent.quote_id)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"quote not found: {intent.quote_id}")

    actor_user_id = request.confirmed_by_user_id or intent.merchant_id
    actor = session.get(User, actor_user_id)
    if actor is None:
        return _mark_received_validation_error(
            intent=intent,
            quote=quote,
            message="确认人不存在。 (confirmed_by_user_id was not found.)",
        )

    is_stripe_channel = intent.payment_channel == STRIPE_CHANNEL
    is_provider_confirmed_call = request.collection_method == "stripe_webhook"
    allows_demo_admin_override = (
        bool(settings.settlement_allow_manual_mark_received_override)
        and bool(request.demo_admin_override)
    )
    if is_stripe_channel and not is_provider_confirmed_call and not allows_demo_admin_override:
        return _mark_received_validation_error(
            intent=intent,
            quote=quote,
            message=(
                "Stripe 通道仅允许 provider webhook 确认到账；"
                "手工确认仅限 demo/admin override。"
                " (Stripe channel requires provider-confirmed webhook; manual mark-received is demo/admin override only.)"
            ),
        )

    link = session.execute(
        select(StablecoinPayoutLink)
        .where(StablecoinPayoutLink.fiat_payment_intent_id == intent.id)
        .with_for_update()
        .limit(1)
    ).scalar_one_or_none()

    if intent.status in {
        FiatPaymentIntentStatus.CANCELLED.value,
        FiatPaymentIntentStatus.FAILED.value,
        FiatPaymentIntentStatus.BLOCKED.value,
    }:
        return _mark_received_validation_error(
            intent=intent,
            quote=quote,
            message=f"当前状态 {intent.status} 不允许确认到账。 (Current status {intent.status} is non-confirmable.)",
        )
    if intent.status == FiatPaymentIntentStatus.AWAITING_KYC.value:
        return _mark_received_validation_error(
            intent=intent,
            quote=quote,
            message="KYC 未完成，不能确认到账。 (KYC is not verified yet.)",
        )

    if intent.status in {FiatPaymentIntentStatus.PAYOUT_IN_PROGRESS.value, FiatPaymentIntentStatus.COMPLETED.value}:
        return _build_mark_received_response(
            session=session,
            intent=intent,
            quote=quote,
            status="ok",
            message="该意图已进入 payout 阶段，返回当前状态。 (Intent is already in payout stage; returning current state.)",
        )

    if intent.status == FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value and link is not None:
        if link.status in {"completed", "payout_in_progress", "partially_confirmed"}:
            return _build_mark_received_response(
                session=session,
                intent=intent,
                quote=quote,
                status="ok",
                message=(
                    "该意图已进入 payout 阶段，返回当前状态。 "
                    "(Intent is already in payout stage; returning current state.)"
                ),
            )
        if link.status == "blocked":
            return _mark_received_validation_error(
                intent=intent,
                quote=quote,
                message=(
                    "该意图曾被风控阻断，不能通过重复 mark-received 绕过。 "
                    "(This intent was risk-blocked; repeated mark-received cannot bypass it.)"
                ),
            )

    allowed_mark_received_statuses = {
        FiatPaymentIntentStatus.AWAITING_FIAT.value,
        FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value,
        FiatPaymentIntentStatus.PAYMENT_PROCESSING.value,
        FiatPaymentIntentStatus.FIAT_RECEIVED.value,
        FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value,
    }
    if intent.status not in allowed_mark_received_statuses:
        return _mark_received_validation_error(
            intent=intent,
            quote=quote,
            message=(
                f"当前状态 {intent.status} 不支持 mark-received。 "
                f"(Current status {intent.status} is not eligible for mark-received.)"
            ),
        )

    received_currency = (request.currency or intent.payer_currency).upper().strip()
    received_amount = Decimal(str(request.received_amount if request.received_amount is not None else intent.payer_amount))
    received_amount = received_amount.quantize(FIAT_UNIT, rounding=ROUND_DOWN)
    if received_currency != intent.payer_currency:
        return _mark_received_validation_error(
            intent=intent,
            quote=quote,
            message="到账币种与意图不一致。 (Received currency does not match fiat intent currency.)",
        )
    if received_amount != intent.payer_amount:
        return _mark_received_validation_error(
            intent=intent,
            quote=quote,
            message="到账金额与意图不一致。 (Received amount does not match fiat intent amount.)",
        )

    trace_id = _fiat_trace_id(intent.id)
    collection = session.execute(
        select(FiatCollection)
        .where(FiatCollection.fiat_payment_intent_id == intent.id)
        .with_for_update()
        .limit(1)
    ).scalar_one_or_none()
    if collection is None:
        collection = FiatCollection(
            id=uuid.uuid4(),
            fiat_payment_intent_id=intent.id,
            collection_method=(
                "stripe_demo_admin_override"
                if is_stripe_channel and allows_demo_admin_override and not is_provider_confirmed_call
                else request.collection_method
            ),
            bank_reference=request.bank_reference,
            received_amount=received_amount,
            currency=received_currency,
            received_at=request.received_at or datetime.now(timezone.utc),
            confirmed_by_user_id=actor.id,
            status=FiatCollectionStatus.CONFIRMED.value,
            metadata_json={
                "mode": "manual_or_simulated",
                "demo_admin_override": bool(allows_demo_admin_override),
                "provider_confirmed": bool(is_provider_confirmed_call),
            },
        )
        session.add(collection)
    else:
        collection.collection_method = (
            "stripe_demo_admin_override"
            if is_stripe_channel and allows_demo_admin_override and not is_provider_confirmed_call
            else request.collection_method
        )
        collection.bank_reference = request.bank_reference
        collection.received_amount = received_amount
        collection.currency = received_currency
        collection.received_at = request.received_at or collection.received_at or datetime.now(timezone.utc)
        collection.confirmed_by_user_id = actor.id
        collection.status = FiatCollectionStatus.CONFIRMED.value
        collection_meta = dict(collection.metadata_json or {}) if isinstance(collection.metadata_json, dict) else {}
        collection_meta["demo_admin_override"] = bool(allows_demo_admin_override)
        collection_meta["provider_confirmed"] = bool(is_provider_confirmed_call)
        collection.metadata_json = collection_meta
        session.add(collection)

    if link is None:
        link = StablecoinPayoutLink(
            id=uuid.uuid4(),
            fiat_payment_intent_id=intent.id,
            status="fiat_received",
            metadata_json={"created_from": "fiat_mark_received"},
        )
        session.add(link)
    else:
        link_metadata = dict(link.metadata_json or {}) if isinstance(link.metadata_json, dict) else {}
        link_metadata["last_mark_received_at"] = datetime.now(timezone.utc).isoformat()
        link.metadata_json = link_metadata
        # Keep terminal/in-progress link statuses stable. Only refresh pre-payout marker.
        if link.status not in {"completed", "blocked", "payout_in_progress", "partially_confirmed"}:
            link.status = "fiat_received"
        session.add(link)

    before_status = intent.status
    intent.status = FiatPaymentIntentStatus.FIAT_RECEIVED.value
    if intent.payment_channel == STRIPE_CHANNEL or request.collection_method.startswith("stripe"):
        if is_stripe_channel and allows_demo_admin_override and not is_provider_confirmed_call:
            intent.channel_status = "payment_processing"
        else:
            intent.channel_status = "payment_processing"
        intent.channel_confirmed_at = intent.channel_confirmed_at or datetime.now(timezone.utc)
    elif intent.payment_channel == MANUAL_CHANNEL and not intent.channel_status:
        intent.channel_status = "manual_confirmed"
    _sync_intent_next_action(intent)
    session.add(intent)
    session.add(
        _build_audit(
            actor_user_id=actor.id,
            entity_type="fiat_payment_intent",
            entity_id=intent.id,
            action=(
                "fiat_funds_marked_received_demo_override"
                if is_stripe_channel and allows_demo_admin_override and not is_provider_confirmed_call
                else "fiat_funds_marked_received"
            ),
            trace_id=trace_id,
            before_json={"status": before_status},
            after_json={
                "status": FiatPaymentIntentStatus.FIAT_RECEIVED.value,
                "received_amount": float(received_amount),
                "currency": received_currency,
                "collection_id": str(collection.id),
                "demo_admin_override": bool(allows_demo_admin_override),
                "provider_confirmed": bool(is_provider_confirmed_call),
            },
        )
    )

    command = session.get(CommandExecution, intent.payout_command_id) if intent.payout_command_id else None
    if command is None:
        command = _create_settlement_command(session=session, intent=intent)
        intent.payout_command_id = command.id
        session.add(intent)
    # Phase 1 commit: fiat confirmation and payout intent are durable before bridge call.
    session.commit()

    confirm_execution_mode = request.execution_mode or "operator"
    confirm_idempotency_key = request.idempotency_key or f"fiat-intent:{intent.id}:{confirm_execution_mode}"
    try:
        confirm_response = handle_confirm(
            session=session,
            request=ConfirmRequest(
                command_id=command.id,
                confirmed=True,
                execution_mode=confirm_execution_mode,
                idempotency_key=confirm_idempotency_key,
                actor_user_id=actor.id,
                note=request.note,
                locale=request.locale,
            ),
        )
    except Exception as exc:
        session.rollback()
        locked_intent = session.execute(
            select(FiatPaymentIntent).where(FiatPaymentIntent.id == fiat_payment_intent_id).with_for_update()
        ).scalar_one_or_none()
        if locked_intent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"fiat_payment_intent not found: {fiat_payment_intent_id}",
            )
        locked_quote = session.get(SettlementQuote, locked_intent.quote_id)
        if locked_quote is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"quote not found: {locked_intent.quote_id}")
        locked_link = session.execute(
            select(StablecoinPayoutLink)
            .where(StablecoinPayoutLink.fiat_payment_intent_id == locked_intent.id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
        if locked_link is None:
            locked_link = StablecoinPayoutLink(
                id=uuid.uuid4(),
                fiat_payment_intent_id=locked_intent.id,
                status="bridge_failed_recoverable",
                metadata_json={"created_from": "fiat_mark_received"},
            )
            session.add(locked_link)
        locked_intent.status = FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value
        _record_bridge_failure(
            intent=locked_intent,
            link=locked_link,
            phase="confirm_bridge",
            reason=str(exc),
            confirm_status=None,
            payment_status=None,
            execution_status=None,
        )
        if locked_link.status not in {"blocked", "completed"}:
            locked_link.status = "bridge_failed_recoverable"
        _sync_intent_next_action(locked_intent)
        session.add(locked_intent)
        session.add(locked_link)
        session.add(
            _build_audit(
                actor_user_id=actor.id,
                entity_type="fiat_payment_intent",
                entity_id=locked_intent.id,
                action="settlement_bridge_failed",
                trace_id=trace_id,
                before_json=None,
                after_json={
                    "status": locked_intent.status,
                    "payout_link_status": locked_link.status,
                    "reason": str(exc),
                },
            )
        )
        session.commit()
        return _build_mark_received_response(
            session=session,
            intent=locked_intent,
            quote=locked_quote,
            status="failed",
            message=(
                "法币已确认，但 payout 桥接失败，可重试 mark-received。 "
                "(Fiat confirmed, but payout bridge failed; mark-received is retryable.)"
            ),
        )

    session.refresh(intent)
    session.refresh(link)
    if confirm_response.payment_order_id is not None:
        link.payment_order_id = confirm_response.payment_order_id
    if confirm_response.execution_batch_id is not None:
        link.execution_batch_id = confirm_response.execution_batch_id

    if confirm_response.status == "ok":
        if confirm_response.payment_status == "executed":
            intent.status = FiatPaymentIntentStatus.COMPLETED.value
            link.status = "completed"
            settlement_action = "settlement_completed"
        elif confirm_response.payment_status == "partially_executed":
            intent.status = FiatPaymentIntentStatus.PAYOUT_IN_PROGRESS.value
            link.status = "partially_confirmed"
            settlement_action = "payout_execution_started"
        elif confirm_response.payment_status == "failed":
            intent.status = FiatPaymentIntentStatus.FAILED.value
            link.status = "failed"
            settlement_action = "settlement_failed"
        else:
            intent.status = FiatPaymentIntentStatus.PAYOUT_IN_PROGRESS.value
            link.status = "payout_in_progress"
            settlement_action = "payout_execution_started"
    elif confirm_response.status == "blocked":
        intent.status = FiatPaymentIntentStatus.FAILED.value
        link.status = "blocked"
        settlement_action = "settlement_failed"
    else:
        # Keep fiat receipt durable and explicitly recoverable when confirm bridge fails without risk block.
        intent.status = FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value
        link.status = "bridge_failed_recoverable"
        settlement_action = "settlement_bridge_failed"
        _record_bridge_failure(
            intent=intent,
            link=link,
            phase="confirm_bridge",
            reason="non_ok_confirm_response",
            confirm_status=confirm_response.status,
            payment_status=confirm_response.payment_status,
            execution_status=confirm_response.execution_status,
        )

    _sync_intent_next_action(intent)
    session.add(intent)
    session.add(link)
    if link.payment_order_id is not None:
        session.add(
            _build_audit(
                actor_user_id=actor.id,
                entity_type="stablecoin_payout_link",
                entity_id=link.id,
                action="payout_order_linked",
                trace_id=trace_id,
                before_json=None,
                after_json={
                    "payment_order_id": str(link.payment_order_id),
                    "execution_batch_id": str(link.execution_batch_id) if link.execution_batch_id else None,
                    "status": link.status,
                },
            )
        )
    session.add(
        _build_audit(
            actor_user_id=actor.id,
            entity_type="fiat_payment_intent",
            entity_id=intent.id,
            action=settlement_action,
            trace_id=trace_id,
            before_json=None,
            after_json={
                "status": intent.status,
                "confirm_status": confirm_response.status,
                "payment_status": confirm_response.payment_status,
                "execution_status": confirm_response.execution_status,
            },
        )
    )
    session.commit()
    session.refresh(intent)
    session.refresh(link)
    if collection is not None:
        session.refresh(collection)

    response_status = "ok"
    response_message = "法币已确认，稳定币 payout 已触发。 (Fiat receipt confirmed and stablecoin payout triggered.)"
    if confirm_response.status == "blocked":
        response_status = "failed"
        response_message = "法币已确认，但 payout 被风控拦截。 (Fiat confirmed, but payout was blocked by risk policy.)"
    elif confirm_response.status != "ok":
        response_status = "failed"
        response_message = (
            "法币已确认，但 payout 桥接失败，可重试 mark-received。 "
            "(Fiat confirmed, but payout bridge failed; mark-received is retryable.)"
        )

    return _build_mark_received_response(
        session=session,
        intent=intent,
        quote=quote,
        status=response_status,
        message=response_message,
    )


def get_fiat_payment_detail(session: Session, fiat_payment_intent_id: UUID) -> MerchantFiatPaymentDetailResponse:
    intent = session.get(FiatPaymentIntent, fiat_payment_intent_id)
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"fiat_payment_intent not found: {fiat_payment_intent_id}",
        )
    quote = session.get(SettlementQuote, intent.quote_id)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"quote not found: {intent.quote_id}")

    collection = session.execute(
        select(FiatCollection).where(FiatCollection.fiat_payment_intent_id == intent.id).limit(1)
    ).scalar_one_or_none()
    link = session.execute(
        select(StablecoinPayoutLink).where(StablecoinPayoutLink.fiat_payment_intent_id == intent.id).limit(1)
    ).scalar_one_or_none()
    kyc = _load_effective_kyc_for_intent(session=session, intent=intent)

    payment_order = None
    execution_batch = None
    execution_items: list[PaymentExecutionItem] = []
    risk_checks: list[Any] = []
    if link is not None and link.payment_order_id is not None:
        payment_detail = get_payment_detail(session=session, payment_id=link.payment_order_id)
        payment_order = payment_detail.payment
        execution_batch = payment_detail.execution_batch
        execution_items = payment_detail.execution_items
        risk_checks = payment_detail.risk_checks

    timeline = _load_fiat_timeline(
        session=session,
        intent=intent,
        quote=quote,
        collection=collection,
        link=link,
    )

    return MerchantFiatPaymentDetailResponse(
        fiat_payment=_to_intent_view(intent),
        quote=_to_quote_view(quote),
        kyc_verification=_to_kyc_view(kyc) if kyc else None,
        fiat_collection=_to_collection_view(collection) if collection else None,
        payout_link=_to_payout_link_view(link) if link else None,
        payment_order=payment_order,
        execution_batch=execution_batch,
        execution_items=execution_items,
        risk_checks=risk_checks,
        timeline=timeline,
    )


def list_fiat_payments(
    session: Session,
    *,
    merchant_id: UUID | None,
    status_value: str | None,
    limit: int,
) -> MerchantFiatPaymentListResponse:
    stmt = select(FiatPaymentIntent)
    if merchant_id is not None:
        stmt = stmt.where(FiatPaymentIntent.merchant_id == merchant_id)
    if status_value:
        stmt = stmt.where(FiatPaymentIntent.status == status_value)

    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    intents = session.execute(
        stmt.order_by(FiatPaymentIntent.created_at.desc(), FiatPaymentIntent.id.desc()).limit(limit)
    ).scalars().all()

    intent_ids = [item.id for item in intents]
    link_map: dict[UUID, StablecoinPayoutLink] = {}
    if intent_ids:
        links = session.execute(
            select(StablecoinPayoutLink).where(StablecoinPayoutLink.fiat_payment_intent_id.in_(intent_ids))
        ).scalars().all()
        link_map = {link.fiat_payment_intent_id: link for link in links}

    items = []
    for intent in intents:
        link = link_map.get(intent.id)
        items.append(
            MerchantFiatPaymentListItem(
                id=intent.id,
                merchant_id=intent.merchant_id,
                beneficiary_id=intent.beneficiary_id,
                quote_id=intent.quote_id,
                payer_currency=intent.payer_currency,
                payer_amount=float(intent.payer_amount),
                target_stablecoin=intent.target_stablecoin,
                target_amount=float(intent.target_amount),
                status=intent.status,
                payment_channel=intent.payment_channel,
                channel_status=intent.channel_status,
                next_action=intent.next_action or _resolve_persisted_next_action(intent),
                kyc_verification_id=intent.kyc_verification_id,
                reference=intent.reference,
                payment_order_id=link.payment_order_id if link else None,
                execution_batch_id=link.execution_batch_id if link else None,
                payout_status=link.status if link else None,
                created_at=intent.created_at,
                updated_at=intent.updated_at,
            )
        )

    return MerchantFiatPaymentListResponse(total=total, limit=limit, items=items)


def handle_stripe_webhook(
    session: Session,
    *,
    payload: bytes,
    stripe_signature: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    if stripe is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe SDK is not installed.",
        )

    try:
        event = _parse_stripe_event(
            payload=payload,
            stripe_signature=stripe_signature,
            webhook_secret=settings.stripe_webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    event_type = str(event.get("type") or "")
    event_id = str(event.get("id") or "")
    event_object = (
        event.get("data", {}).get("object")
        if isinstance(event.get("data"), dict)
        else None
    )
    if not isinstance(event_object, dict):
        return {"status": "ignored", "event_type": event_type, "reason": "missing_data_object"}

    received_at = datetime.now(timezone.utc)
    if event_type.startswith("identity.verification_session."):
        result = _handle_identity_verification_event(
            session=session,
            event_type=event_type,
            event_id=event_id,
            event_object=event_object,
            received_at=received_at,
        )
        return {"status": "ok", "event_type": event_type, "result": result}
    if event_type in {"checkout.session.completed", "checkout.session.expired"}:
        if _safe_uuid((event_object.get("metadata") or {}).get("deposit_order_id") if isinstance(event_object.get("metadata"), dict) else None):
            result = _handle_balance_checkout_session_event(
                session=session,
                event_type=event_type,
                event_id=event_id,
                event_object=event_object,
                received_at=received_at,
            )
            return {"status": "ok", "event_type": event_type, "result": result}
        result = _handle_checkout_session_event(
            session=session,
            event_type=event_type,
            event_id=event_id,
            event_object=event_object,
            received_at=received_at,
        )
        return {"status": "ok", "event_type": event_type, "result": result}
    if event_type in {"payment_intent.succeeded", "payment_intent.payment_failed", "payment_intent.canceled"}:
        if _safe_uuid((event_object.get("metadata") or {}).get("deposit_order_id") if isinstance(event_object.get("metadata"), dict) else None):
            result = _handle_balance_payment_intent_event(
                session=session,
                event_type=event_type,
                event_id=event_id,
                event_object=event_object,
                received_at=received_at,
            )
            return {"status": "ok", "event_type": event_type, "result": result}
        result = _handle_payment_intent_event(
            session=session,
            event_type=event_type,
            event_id=event_id,
            event_object=event_object,
            received_at=received_at,
        )
        return {"status": "ok", "event_type": event_type, "result": result}
    return {"status": "ignored", "event_type": event_type, "reason": "unsupported_event_type"}


def _parse_stripe_event(
    *,
    payload: bytes,
    stripe_signature: str | None,
    webhook_secret: str | None,
) -> dict[str, Any]:
    if stripe is None:
        raise ValueError("Stripe SDK is not installed.")
    if not webhook_secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET is required for Stripe webhook verification.")
    if not stripe_signature:
        raise ValueError("Missing Stripe-Signature header.")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=webhook_secret,
        )
    except Exception as exc:
        raise ValueError(f"Invalid Stripe webhook signature: {exc}") from exc
    return dict(event)


def _handle_identity_verification_event(
    *,
    session: Session,
    event_type: str,
    event_id: str,
    event_object: dict[str, Any],
    received_at: datetime,
) -> dict[str, Any]:
    session_id = str(event_object.get("id") or "")
    if not session_id:
        return {"status": "ignored", "reason": "missing_verification_session_id"}

    kyc = session.execute(
        select(KycVerification)
        .where(KycVerification.provider_verification_session_id == session_id)
        .with_for_update()
        .limit(1)
    ).scalar_one_or_none()
    if kyc is None:
        return {"status": "ignored", "reason": "kyc_record_not_found", "session_id": session_id}
    if event_id and _is_duplicate_kyc_webhook_event(metadata_json=kyc.metadata_json, event_id=event_id):
        return {"status": "duplicate_ignored", "kyc_verification_id": str(kyc.id), "event_id": event_id}

    provider_status = str(event_object.get("status") or "").lower()
    mapped_status = _map_stripe_identity_status(event_type=event_type, provider_status=provider_status)
    before_status = kyc.status
    kyc.status = mapped_status
    kyc.verification_url = _safe_str(event_object.get("url")) or kyc.verification_url
    if mapped_status == KycVerificationStatus.VERIFIED.value:
        kyc.verified_at = received_at
        kyc.failure_reason = None
    elif mapped_status in {
        KycVerificationStatus.FAILED.value,
        KycVerificationStatus.EXPIRED.value,
        KycVerificationStatus.REQUIRES_REVIEW.value,
    }:
        kyc.failure_reason = (
            _safe_str(event_object.get("last_error", {}).get("reason"))
            if isinstance(event_object.get("last_error"), dict)
            else _safe_str(event_object.get("last_error"))
        ) or kyc.failure_reason
    kyc_meta = dict(kyc.metadata_json or {}) if isinstance(kyc.metadata_json, dict) else {}
    kyc_meta["last_webhook_event"] = {
        "event_id": event_id,
        "event_type": event_type,
        "provider_status": provider_status,
        "received_at": received_at.isoformat(),
    }
    kyc.metadata_json = kyc_meta
    session.add(kyc)
    trace_id = f"trace-kyc-{kyc.id.hex[:12]}"
    session.add(
        _build_audit(
            actor_user_id=None,
            entity_type="kyc_verification",
            entity_id=kyc.id,
            action="kyc_status_updated",
            trace_id=trace_id,
            before_json={"status": before_status},
            after_json={"status": kyc.status, "event_type": event_type},
        )
    )

    if (
        kyc.subject_type == "merchant"
        and kyc.status == KycVerificationStatus.VERIFIED.value
    ):
        pending_intents = session.execute(
            select(FiatPaymentIntent)
            .where(
                FiatPaymentIntent.merchant_id == kyc.subject_id,
                FiatPaymentIntent.payment_channel == STRIPE_CHANNEL,
                FiatPaymentIntent.status == FiatPaymentIntentStatus.AWAITING_KYC.value,
            )
            .with_for_update()
        ).scalars().all()
        for intent in pending_intents:
            before_intent_status = intent.status
            intent.status = FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value
            intent.channel_status = "awaiting_payment"
            intent.kyc_verification_id = kyc.id
            _sync_intent_next_action(intent)
            session.add(intent)
            session.add(
                _build_audit(
                    actor_user_id=intent.merchant_id,
                    entity_type="fiat_payment_intent",
                    entity_id=intent.id,
                    action="kyc_verified_for_fiat_intent",
                    trace_id=_fiat_trace_id(intent.id),
                    before_json={"status": before_intent_status},
                    after_json={"status": intent.status, "kyc_verification_id": str(kyc.id)},
                )
            )

    session.commit()
    return {
        "status": "updated",
        "kyc_verification_id": str(kyc.id),
        "kyc_status": kyc.status,
    }


def _handle_checkout_session_event(
    *,
    session: Session,
    event_type: str,
    event_id: str,
    event_object: dict[str, Any],
    received_at: datetime,
) -> dict[str, Any]:
    checkout_session_id = _safe_str(event_object.get("id"))
    metadata = event_object.get("metadata") if isinstance(event_object.get("metadata"), dict) else {}
    fiat_payment_intent_id = _safe_uuid(metadata.get("fiat_payment_intent_id"))
    if fiat_payment_intent_id is None and checkout_session_id:
        intent = session.execute(
            select(FiatPaymentIntent)
            .where(FiatPaymentIntent.channel_checkout_session_id == checkout_session_id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
    else:
        intent = session.execute(
            select(FiatPaymentIntent)
            .where(FiatPaymentIntent.id == fiat_payment_intent_id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()

    if intent is None:
        return {
            "status": "ignored",
            "reason": "fiat_payment_intent_not_found",
            "checkout_session_id": checkout_session_id,
        }
    if event_id and _is_duplicate_intent_webhook_event(metadata_json=intent.metadata_json, event_id=event_id):
        return {"status": "duplicate_ignored", "fiat_payment_intent_id": str(intent.id), "event_id": event_id}

    before_status = intent.status
    intent.channel_checkout_session_id = checkout_session_id or intent.channel_checkout_session_id
    payment_intent_id = event_object.get("payment_intent")
    if isinstance(payment_intent_id, str) and payment_intent_id:
        intent.channel_payment_id = payment_intent_id
    intent.webhook_received_at = received_at
    if event_type == "checkout.session.completed":
        intent.channel_status = "payment_processing"
        if intent.status in {
            FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value,
            FiatPaymentIntentStatus.AWAITING_FIAT.value,
        }:
            intent.status = FiatPaymentIntentStatus.PAYMENT_PROCESSING.value
        action = "stripe_checkout_completed"
    else:
        intent.channel_status = "checkout_expired"
        if intent.status not in {
            FiatPaymentIntentStatus.COMPLETED.value,
            FiatPaymentIntentStatus.PAYOUT_IN_PROGRESS.value,
        }:
            intent.status = FiatPaymentIntentStatus.FAILED.value
        action = "stripe_checkout_expired"

    _record_intent_webhook_event(
        intent=intent,
        event_id=event_id,
        event_type=event_type,
        received_at=received_at,
    )
    _sync_intent_next_action(intent)

    session.add(intent)
    session.add(
        _build_audit(
            actor_user_id=intent.merchant_id,
            entity_type="fiat_payment_intent",
            entity_id=intent.id,
            action=action,
            trace_id=_fiat_trace_id(intent.id),
            before_json={"status": before_status},
            after_json={
                "status": intent.status,
                "channel_status": intent.channel_status,
                "channel_checkout_session_id": intent.channel_checkout_session_id,
                "channel_payment_id": intent.channel_payment_id,
                "event_id": event_id,
            },
        )
    )
    session.commit()
    return {
        "status": "updated",
        "fiat_payment_intent_id": str(intent.id),
        "fiat_status": intent.status,
        "channel_status": intent.channel_status,
        "next_action": intent.next_action or _resolve_persisted_next_action(intent),
    }


def _handle_balance_checkout_session_event(
    *,
    session: Session,
    event_type: str,
    event_id: str,
    event_object: dict[str, Any],
    received_at: datetime,
) -> dict[str, Any]:
    metadata = event_object.get("metadata") if isinstance(event_object.get("metadata"), dict) else {}
    deposit_order_id = _safe_uuid(metadata.get("deposit_order_id"))
    checkout_session_id = _safe_str(event_object.get("id"))
    if deposit_order_id is None and checkout_session_id:
        deposit = session.execute(
            select(FiatDepositOrder)
            .where(FiatDepositOrder.channel_checkout_session_id == checkout_session_id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
    else:
        deposit = session.execute(
            select(FiatDepositOrder)
            .where(FiatDepositOrder.id == deposit_order_id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
    if deposit is None:
        return {"status": "ignored", "reason": "deposit_order_not_found", "checkout_session_id": checkout_session_id}
    if event_id and _is_duplicate_deposit_webhook_event(metadata_json=deposit.metadata_json, event_id=event_id):
        _record_duplicate_deposit_webhook_event(
            deposit=deposit,
            event_id=event_id,
            event_type=event_type,
            received_at=received_at,
        )
        session.add(deposit)
        session.add(
            _build_audit(
                actor_user_id=deposit.user_id,
                entity_type="fiat_deposit_order",
                entity_id=deposit.id,
                action="deposit_webhook_duplicate_ignored",
                trace_id=f"trace-deposit-{deposit.id.hex[:12]}",
                before_json={"status": deposit.status},
                after_json={
                    "status": deposit.status,
                    "channel_status": deposit.channel_status,
                    "event_id": event_id,
                    "event_type": event_type,
                },
            )
        )
        session.commit()
        return {"status": "duplicate_ignored", "deposit_order_id": str(deposit.id), "event_id": event_id}

    before_status = deposit.status
    deposit.channel_checkout_session_id = checkout_session_id or deposit.channel_checkout_session_id
    payment_intent_id = event_object.get("payment_intent")
    if isinstance(payment_intent_id, str) and payment_intent_id:
        deposit.channel_payment_id = payment_intent_id
    deposit.webhook_received_at = received_at

    if event_type == "checkout.session.completed":
        deposit.channel_status = "payment_processing"
        if deposit.status in {
            FiatDepositOrderStatus.CREATED.value,
            FiatDepositOrderStatus.AWAITING_CHANNEL_PAYMENT.value,
        }:
            deposit.status = FiatDepositOrderStatus.PAYMENT_PROCESSING.value
            deposit.next_action = "wait_channel_confirmation"
        action = "deposit_checkout_completed"
    else:
        deposit.channel_status = "checkout_expired"
        if deposit.status not in {FiatDepositOrderStatus.CREDITED.value, FiatDepositOrderStatus.CONVERTED.value}:
            deposit.status = FiatDepositOrderStatus.FAILED.value
            deposit.next_action = "none"
        action = "deposit_checkout_expired"

    _record_deposit_webhook_event(
        deposit=deposit,
        event_id=event_id,
        event_type=event_type,
        received_at=received_at,
    )
    session.add(deposit)
    session.add(
        _build_audit(
            actor_user_id=deposit.user_id,
            entity_type="fiat_deposit_order",
            entity_id=deposit.id,
            action=action,
            trace_id=f"trace-deposit-{deposit.id.hex[:12]}",
            before_json={"status": before_status},
            after_json={
                "status": deposit.status,
                "channel_status": deposit.channel_status,
                "channel_checkout_session_id": deposit.channel_checkout_session_id,
                "channel_payment_id": deposit.channel_payment_id,
                "event_id": event_id,
            },
        )
    )
    session.commit()
    return {
        "status": "updated",
        "deposit_order_id": str(deposit.id),
        "deposit_status": deposit.status,
        "channel_status": deposit.channel_status,
        "next_action": deposit.next_action,
    }


def _handle_payment_intent_event(
    *,
    session: Session,
    event_type: str,
    event_id: str,
    event_object: dict[str, Any],
    received_at: datetime,
) -> dict[str, Any]:
    payment_intent_id = _safe_str(event_object.get("id"))
    metadata = event_object.get("metadata") if isinstance(event_object.get("metadata"), dict) else {}
    fiat_payment_intent_id = _safe_uuid(metadata.get("fiat_payment_intent_id"))
    if fiat_payment_intent_id is None and payment_intent_id:
        intent = session.execute(
            select(FiatPaymentIntent)
            .where(FiatPaymentIntent.channel_payment_id == payment_intent_id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
    else:
        intent = session.execute(
            select(FiatPaymentIntent)
            .where(FiatPaymentIntent.id == fiat_payment_intent_id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
    if intent is None:
        return {"status": "ignored", "reason": "fiat_payment_intent_not_found", "payment_intent_id": payment_intent_id}
    if event_id and _is_duplicate_intent_webhook_event(metadata_json=intent.metadata_json, event_id=event_id):
        return {"status": "duplicate_ignored", "fiat_payment_intent_id": str(intent.id), "event_id": event_id}

    before_status = intent.status
    intent.channel_payment_id = payment_intent_id or intent.channel_payment_id
    intent.webhook_received_at = received_at
    action = "stripe_payment_event_received"
    if event_type == "payment_intent.succeeded":
        intent.channel_status = "payment_processing"
        intent.channel_confirmed_at = received_at
        effective_kyc = _load_effective_kyc_for_intent(session=session, intent=intent)
        requires_kyc = bool(get_settings().settlement_require_kyc)
        if requires_kyc and (effective_kyc is None or effective_kyc.status != KycVerificationStatus.VERIFIED.value):
            intent.status = FiatPaymentIntentStatus.BLOCKED.value
            intent.channel_status = "blocked_kyc_required"
            meta = dict(intent.metadata_json or {}) if isinstance(intent.metadata_json, dict) else {}
            meta["blocked_reason"] = "KYC_REQUIRED_NOT_VERIFIED"
            meta["blocked_at"] = received_at.isoformat()
            intent.metadata_json = meta
            action = "stripe_payment_blocked_by_kyc"
        elif intent.status in {
            FiatPaymentIntentStatus.AWAITING_KYC.value,
            FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value,
            FiatPaymentIntentStatus.AWAITING_FIAT.value,
            FiatPaymentIntentStatus.PAYMENT_PROCESSING.value,
            FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value,
            FiatPaymentIntentStatus.FIAT_RECEIVED.value,
        }:
            intent.status = FiatPaymentIntentStatus.PAYMENT_PROCESSING.value
            action = "stripe_payment_confirmed"
        else:
            action = "stripe_payment_confirmed"
    elif event_type == "payment_intent.payment_failed":
        intent.channel_status = "payment_failed"
        if intent.status not in {FiatPaymentIntentStatus.COMPLETED.value, FiatPaymentIntentStatus.PAYOUT_IN_PROGRESS.value}:
            intent.status = FiatPaymentIntentStatus.FAILED.value
        action = "stripe_payment_failed"
    else:
        intent.channel_status = "payment_canceled"
        if intent.status not in {FiatPaymentIntentStatus.COMPLETED.value, FiatPaymentIntentStatus.PAYOUT_IN_PROGRESS.value}:
            intent.status = FiatPaymentIntentStatus.CANCELLED.value
        action = "stripe_payment_canceled"

    _record_intent_webhook_event(
        intent=intent,
        event_id=event_id,
        event_type=event_type,
        received_at=received_at,
    )
    _sync_intent_next_action(intent)

    session.add(intent)
    session.add(
        _build_audit(
            actor_user_id=intent.merchant_id,
            entity_type="fiat_payment_intent",
            entity_id=intent.id,
            action=action,
            trace_id=_fiat_trace_id(intent.id),
            before_json={"status": before_status},
            after_json={
                "status": intent.status,
                "channel_status": intent.channel_status,
                "channel_payment_id": intent.channel_payment_id,
                "event_id": event_id,
            },
        )
    )
    session.commit()

    if event_type != "payment_intent.succeeded":
        return {
            "status": "updated",
            "fiat_payment_intent_id": str(intent.id),
            "fiat_status": intent.status,
            "channel_status": intent.channel_status,
            "next_action": intent.next_action or _resolve_persisted_next_action(intent),
        }
    if intent.status == FiatPaymentIntentStatus.BLOCKED.value:
        return {
            "status": "blocked",
            "fiat_payment_intent_id": str(intent.id),
            "fiat_status": intent.status,
            "channel_status": intent.channel_status,
            "next_action": intent.next_action or _resolve_persisted_next_action(intent),
            "message": "KYC 未完成，Stripe 支付成功事件不会触发出款。 (KYC not verified; payout was blocked.)",
        }

    # Trigger the existing payout bridge only after confirmed channel payment.
    mark_response = mark_fiat_received(
        session=session,
        fiat_payment_intent_id=intent.id,
        request=MarkFiatReceivedRequest(
            collection_method="stripe_webhook",
            bank_reference=intent.channel_payment_id,
            received_amount=float(intent.payer_amount),
            currency=intent.payer_currency,
            confirmed_by_user_id=intent.merchant_id,
            execution_mode="operator",
            idempotency_key=f"stripe:{intent.id}:{intent.channel_payment_id}",
            note="stripe payment_intent.succeeded webhook",
        ),
    )
    result_status = "bridge_triggered" if mark_response.status == "ok" else mark_response.status
    return {
        "status": result_status,
        "fiat_payment_intent_id": str(intent.id),
        "fiat_status": mark_response.fiat_payment.status,
        "channel_status": mark_response.fiat_payment.channel_status,
        "next_action": mark_response.fiat_payment.next_action,
        "mark_received_status": mark_response.status,
        "payment_order_id": str(mark_response.payout.payment_order_id) if mark_response.payout.payment_order_id else None,
        "execution_batch_id": str(mark_response.payout.execution_batch_id) if mark_response.payout.execution_batch_id else None,
        "payout_tx_hash": mark_response.payout.tx_hash,
        "payout_onchain_status": mark_response.payout.onchain_status,
        "message": mark_response.message,
    }


def _handle_balance_payment_intent_event(
    *,
    session: Session,
    event_type: str,
    event_id: str,
    event_object: dict[str, Any],
    received_at: datetime,
) -> dict[str, Any]:
    payment_intent_id = _safe_str(event_object.get("id"))
    metadata = event_object.get("metadata") if isinstance(event_object.get("metadata"), dict) else {}
    deposit_order_id = _safe_uuid(metadata.get("deposit_order_id"))
    if deposit_order_id is None and payment_intent_id:
        deposit = session.execute(
            select(FiatDepositOrder)
            .where(FiatDepositOrder.channel_payment_id == payment_intent_id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
    else:
        deposit = session.execute(
            select(FiatDepositOrder)
            .where(FiatDepositOrder.id == deposit_order_id)
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
    if deposit is None:
        return {"status": "ignored", "reason": "deposit_order_not_found", "payment_intent_id": payment_intent_id}
    if event_id and _is_duplicate_deposit_webhook_event(metadata_json=deposit.metadata_json, event_id=event_id):
        _record_duplicate_deposit_webhook_event(
            deposit=deposit,
            event_id=event_id,
            event_type=event_type,
            received_at=received_at,
        )
        session.add(deposit)
        session.add(
            _build_audit(
                actor_user_id=deposit.user_id,
                entity_type="fiat_deposit_order",
                entity_id=deposit.id,
                action="deposit_webhook_duplicate_ignored",
                trace_id=f"trace-deposit-{deposit.id.hex[:12]}",
                before_json={"status": deposit.status},
                after_json={
                    "status": deposit.status,
                    "channel_status": deposit.channel_status,
                    "event_id": event_id,
                    "event_type": event_type,
                },
            )
        )
        session.commit()
        return {"status": "duplicate_ignored", "deposit_order_id": str(deposit.id), "event_id": event_id}

    before_status = deposit.status
    deposit.channel_payment_id = payment_intent_id or deposit.channel_payment_id
    deposit.webhook_received_at = received_at
    action = "deposit_payment_event_received"

    if event_type == "payment_intent.succeeded":
        deposit.channel_status = "payment_confirmed"
        deposit.channel_confirmed_at = received_at
        requires_kyc = bool(get_settings().settlement_require_kyc)
        effective_kyc = _load_effective_kyc_for_deposit(session=session, deposit=deposit) if requires_kyc else None
        if requires_kyc and (effective_kyc is None or effective_kyc.status != KycVerificationStatus.VERIFIED.value):
            deposit.status = FiatDepositOrderStatus.BLOCKED.value
            deposit.channel_status = "blocked_kyc_required"
            deposit.next_action = "complete_kyc"
            meta = dict(deposit.metadata_json or {}) if isinstance(deposit.metadata_json, dict) else {}
            meta["blocked_reason"] = "KYC_REQUIRED_NOT_VERIFIED"
            meta["blocked_at"] = received_at.isoformat()
            deposit.metadata_json = meta
            action = "deposit_payment_blocked_by_kyc"
        else:
            deposit.status = FiatDepositOrderStatus.PAYMENT_PROCESSING.value
            deposit.next_action = "credit_balance"
            credit_deposit_order_to_balance(
                session=session,
                deposit_order=deposit,
                actor_user_id=deposit.user_id,
                trace_id=f"trace-deposit-{deposit.id.hex[:12]}",
            )
            action = "deposit_balance_credited"
    elif event_type == "payment_intent.payment_failed":
        deposit.channel_status = "payment_failed"
        if deposit.status not in {FiatDepositOrderStatus.CREDITED.value, FiatDepositOrderStatus.CONVERTED.value}:
            deposit.status = FiatDepositOrderStatus.FAILED.value
            deposit.next_action = "none"
        action = "deposit_payment_failed"
    else:
        deposit.channel_status = "payment_canceled"
        if deposit.status not in {FiatDepositOrderStatus.CREDITED.value, FiatDepositOrderStatus.CONVERTED.value}:
            deposit.status = FiatDepositOrderStatus.CANCELLED.value
            deposit.next_action = "none"
        action = "deposit_payment_canceled"

    _record_deposit_webhook_event(
        deposit=deposit,
        event_id=event_id,
        event_type=event_type,
        received_at=received_at,
    )
    session.add(deposit)
    session.add(
        _build_audit(
            actor_user_id=deposit.user_id,
            entity_type="fiat_deposit_order",
            entity_id=deposit.id,
            action=action,
            trace_id=f"trace-deposit-{deposit.id.hex[:12]}",
            before_json={"status": before_status},
            after_json={
                "status": deposit.status,
                "channel_status": deposit.channel_status,
                "channel_payment_id": deposit.channel_payment_id,
                "event_id": event_id,
            },
        )
    )
    session.commit()
    return {
        "status": "updated" if event_type != "payment_intent.succeeded" else "credited",
        "deposit_order_id": str(deposit.id),
        "deposit_status": deposit.status,
        "channel_status": deposit.channel_status,
        "next_action": deposit.next_action,
    }


def _resolve_fiat_next_action(intent: FiatPaymentIntent) -> str:
    if intent.status == FiatPaymentIntentStatus.AWAITING_KYC.value:
        return "start_kyc"
    if intent.payment_channel == STRIPE_CHANNEL and intent.status == FiatPaymentIntentStatus.PAYMENT_PROCESSING.value:
        return "wait_channel_confirmation"
    if intent.payment_channel == STRIPE_CHANNEL and intent.status in {
        FiatPaymentIntentStatus.CREATED.value,
        FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value,
    }:
        return "create_stripe_session"
    return "mark_fiat_received"


def _resolve_persisted_next_action(intent: FiatPaymentIntent) -> str:
    status_value = (intent.status or "").lower()
    channel_status = (intent.channel_status or "").lower()
    payment_channel = (intent.payment_channel or "").lower()

    if status_value in {"completed", "failed", "cancelled", "blocked"}:
        return "none"
    if status_value == FiatPaymentIntentStatus.AWAITING_KYC.value or channel_status == "blocked_kyc_required":
        return "complete_kyc"
    if payment_channel == STRIPE_CHANNEL:
        if channel_status in {"awaiting_payment", "checkout_session_created", "checkout_completed"} and intent.channel_checkout_url:
            return "open_checkout"
        if status_value == FiatPaymentIntentStatus.PAYMENT_PROCESSING.value:
            return "wait_channel_confirmation"
        if status_value in {
            FiatPaymentIntentStatus.CREATED.value,
            FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value,
        }:
            return "create_stripe_session"
    if status_value in {
        FiatPaymentIntentStatus.FIAT_RECEIVED.value,
        FiatPaymentIntentStatus.PAYOUT_IN_PROGRESS.value,
        FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value,
    }:
        return "track_payout"
    return "mark_fiat_received"


def _sync_intent_next_action(intent: FiatPaymentIntent) -> str:
    next_action = _resolve_persisted_next_action(intent)
    intent.next_action = next_action
    return next_action


def _load_latest_kyc_for_subject(
    *,
    session: Session,
    subject_type: str,
    subject_id: UUID,
    provider: str,
) -> KycVerification | None:
    return session.execute(
        select(KycVerification)
        .where(
            KycVerification.subject_type == subject_type,
            KycVerification.subject_id == subject_id,
            KycVerification.provider == provider,
        )
        .order_by(KycVerification.created_at.desc(), KycVerification.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _load_effective_kyc_for_intent(
    *,
    session: Session,
    intent: FiatPaymentIntent,
) -> KycVerification | None:
    if intent.kyc_verification_id is not None:
        kyc = session.get(KycVerification, intent.kyc_verification_id)
        if kyc is not None:
            return kyc
    settings = get_settings()
    return _load_latest_kyc_for_subject(
        session=session,
        subject_type="merchant",
        subject_id=intent.merchant_id,
        provider=settings.settlement_kyc_provider,
    )


def _load_effective_kyc_for_deposit(
    *,
    session: Session,
    deposit: FiatDepositOrder,
) -> KycVerification | None:
    if deposit.kyc_verification_id is not None:
        kyc = session.get(KycVerification, deposit.kyc_verification_id)
        if kyc is not None:
            return kyc
    settings = get_settings()
    return _load_latest_kyc_for_subject(
        session=session,
        subject_type="user",
        subject_id=deposit.user_id,
        provider=settings.settlement_kyc_provider,
    )


def _to_kyc_view(kyc: KycVerification) -> KycVerificationView:
    return KycVerificationView(
        id=kyc.id,
        subject_type=kyc.subject_type,
        subject_id=kyc.subject_id,
        provider=kyc.provider,
        provider_verification_session_id=kyc.provider_verification_session_id,
        status=kyc.status,
        verification_url=kyc.verification_url,
        verified_at=kyc.verified_at,
        failure_reason=kyc.failure_reason,
        metadata_json=kyc.metadata_json,
        created_at=kyc.created_at,
        updated_at=kyc.updated_at,
    )


def _to_fiat_minor_units(value: Decimal) -> int:
    quantized = Decimal(str(value)).quantize(FIAT_UNIT, rounding=ROUND_DOWN)
    return int((quantized * 100).to_integral_value(rounding=ROUND_DOWN))


def _stripe_get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            pass
    return getattr(obj, key, None)


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except Exception:
        return None


def _is_duplicate_kyc_webhook_event(*, metadata_json: Any, event_id: str) -> bool:
    if not event_id or not isinstance(metadata_json, dict):
        return False
    last = metadata_json.get("last_webhook_event")
    return isinstance(last, dict) and str(last.get("event_id") or "") == event_id


def _is_duplicate_intent_webhook_event(*, metadata_json: Any, event_id: str) -> bool:
    if not event_id or not isinstance(metadata_json, dict):
        return False
    last = metadata_json.get("channel_last_webhook_event")
    return isinstance(last, dict) and str(last.get("event_id") or "") == event_id


def _is_duplicate_deposit_webhook_event(*, metadata_json: Any, event_id: str) -> bool:
    if not event_id or not isinstance(metadata_json, dict):
        return False
    last = metadata_json.get("channel_last_webhook_event")
    return isinstance(last, dict) and str(last.get("event_id") or "") == event_id


def _record_intent_webhook_event(
    *,
    intent: FiatPaymentIntent,
    event_id: str,
    event_type: str,
    received_at: datetime,
) -> None:
    meta = dict(intent.metadata_json or {}) if isinstance(intent.metadata_json, dict) else {}
    meta["channel_last_webhook_event"] = {
        "event_id": event_id,
        "event_type": event_type,
        "received_at": received_at.isoformat(),
    }
    intent.metadata_json = meta


def _record_deposit_webhook_event(
    *,
    deposit: FiatDepositOrder,
    event_id: str,
    event_type: str,
    received_at: datetime,
) -> None:
    meta = dict(deposit.metadata_json or {}) if isinstance(deposit.metadata_json, dict) else {}
    meta["channel_last_webhook_event"] = {
        "event_id": event_id,
        "event_type": event_type,
        "received_at": received_at.isoformat(),
    }
    deposit.metadata_json = meta


def _record_duplicate_deposit_webhook_event(
    *,
    deposit: FiatDepositOrder,
    event_id: str,
    event_type: str,
    received_at: datetime,
) -> None:
    meta = dict(deposit.metadata_json or {}) if isinstance(deposit.metadata_json, dict) else {}
    existing = meta.get("duplicate_webhook_events")
    history = list(existing) if isinstance(existing, list) else []
    history.append(
        {
            "event_id": event_id,
            "event_type": event_type,
            "received_at": received_at.isoformat(),
        }
    )
    meta["duplicate_webhook_events"] = history[-10:]
    meta["last_duplicate_webhook_event"] = history[-1]
    deposit.metadata_json = meta


def _map_stripe_identity_status(*, event_type: str, provider_status: str) -> str:
    if event_type == "identity.verification_session.verified" or provider_status == "verified":
        return KycVerificationStatus.VERIFIED.value
    if event_type in {"identity.verification_session.canceled"} or provider_status in {"canceled", "expired"}:
        return KycVerificationStatus.EXPIRED.value
    if event_type in {"identity.verification_session.requires_input", "identity.verification_session.redacted"}:
        return KycVerificationStatus.REQUIRES_REVIEW.value
    if provider_status in {"requires_input", "unverified", "processing"}:
        return KycVerificationStatus.PENDING.value
    if provider_status in {"failed", "rejected"}:
        return KycVerificationStatus.FAILED.value
    return KycVerificationStatus.PENDING.value


def _create_settlement_command(session: Session, intent: FiatPaymentIntent) -> CommandExecution:
    beneficiary = session.get(Beneficiary, intent.beneficiary_id)
    if beneficiary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"beneficiary not found: {intent.beneficiary_id}")
    conv_session = _resolve_merchant_session(session=session, merchant_id=intent.merchant_id)
    split_count = None
    if isinstance(intent.metadata_json, dict):
        split_count = intent.metadata_json.get("split_count")
    command_id = uuid.uuid4()
    parsed = {
        "intent": "create_payment",
        "confidence": 0.99,
        "fields": {
            "recipient": beneficiary.name,
            "beneficiary": {
                "id": str(beneficiary.id),
                "name": beneficiary.name,
                "country": beneficiary.country,
                "risk_level": beneficiary.risk_level,
                "is_blacklisted": beneficiary.is_blacklisted,
                "resolved": True,
            },
            "amount": float(intent.target_amount),
            "currency": intent.target_stablecoin,
            "split_count": split_count,
            "reference": intent.reference,
            "eta_preference": None,
            "fee_preference": None,
            "settlement_context": {
                "fiat_payment_intent_id": str(intent.id),
                "quote_id": str(intent.quote_id),
                "payer_currency": intent.payer_currency,
                "payer_amount": float(intent.payer_amount),
            },
        },
        "missing_fields": [],
    }
    raw_text = (
        intent.source_text
        or f"[fiat-settlement] payout {intent.target_amount} {intent.target_stablecoin} "
        f"to {beneficiary.name} ref {intent.reference}"
    )
    command = CommandExecution(
        id=command_id,
        session_id=conv_session.id,
        user_id=intent.merchant_id,
        raw_text=raw_text,
        parsed_intent_json=parsed,
        tool_calls_json=[{"tool": "fiat_settlement_bridge", "status": "ok"}],
        final_status=CommandExecutionStatus.READY.value,
        trace_id=f"trace-fiatcmd-{command_id.hex[:12]}",
    )
    session.add(command)
    session.flush()
    return command


def _resolve_merchant_session(session: Session, merchant_id: UUID) -> ConversationSession:
    existing = session.execute(
        select(ConversationSession)
        .where(
            ConversationSession.user_id == merchant_id,
            ConversationSession.channel == "merchant_api",
            ConversationSession.status == SessionStatus.ACTIVE.value,
        )
        .order_by(ConversationSession.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    created = ConversationSession(
        id=uuid.uuid4(),
        user_id=merchant_id,
        channel="merchant_api",
        status=SessionStatus.ACTIVE.value,
    )
    session.add(created)
    session.flush()
    return created


def _load_fiat_timeline(
    *,
    session: Session,
    intent: FiatPaymentIntent,
    quote: SettlementQuote,
    collection: FiatCollection | None,
    link: StablecoinPayoutLink | None,
) -> MerchantTimeline:
    entity_ids: list[UUID] = [intent.id, quote.id]
    if intent.kyc_verification_id is not None:
        entity_ids.append(intent.kyc_verification_id)
    if collection is not None:
        entity_ids.append(collection.id)
    if link is not None:
        entity_ids.append(link.id)
        if link.payment_order_id is not None:
            entity_ids.append(link.payment_order_id)
        if link.execution_batch_id is not None:
            entity_ids.append(link.execution_batch_id)
            execution_item_ids = session.execute(
                select(PaymentExecutionItem.id).where(PaymentExecutionItem.execution_batch_id == link.execution_batch_id)
            ).scalars().all()
            entity_ids.extend(execution_item_ids)
    if intent.payout_command_id is not None:
        entity_ids.append(intent.payout_command_id)

    logs = session.execute(
        select(AuditLog)
        .where(AuditLog.entity_id.in_(entity_ids))
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    ).scalars().all()
    items = build_audit_timeline_items(logs)
    return MerchantTimeline(count=len(items), items=items)


def _record_bridge_failure(
    *,
    intent: FiatPaymentIntent,
    link: StablecoinPayoutLink,
    phase: str,
    reason: str,
    confirm_status: str | None,
    payment_status: str | None,
    execution_status: str | None,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    failure_payload = {
        "phase": phase,
        "reason": reason,
        "confirm_status": confirm_status,
        "payment_status": payment_status,
        "execution_status": execution_status,
        "at": now_iso,
        "retryable": True,
    }

    intent_metadata = dict(intent.metadata_json or {}) if isinstance(intent.metadata_json, dict) else {}
    intent_metadata["last_bridge_failure"] = failure_payload
    intent_metadata["bridge_failure_count"] = int(intent_metadata.get("bridge_failure_count", 0)) + 1
    intent.metadata_json = intent_metadata

    link_metadata = dict(link.metadata_json or {}) if isinstance(link.metadata_json, dict) else {}
    link_metadata["bridge_failure"] = failure_payload
    link.metadata_json = link_metadata


def _build_mark_received_response(
    *,
    session: Session,
    intent: FiatPaymentIntent,
    quote: SettlementQuote,
    status: str,
    message: str,
) -> MarkFiatReceivedResponse:
    collection = session.execute(
        select(FiatCollection).where(FiatCollection.fiat_payment_intent_id == intent.id).limit(1)
    ).scalar_one_or_none()
    link = session.execute(
        select(StablecoinPayoutLink).where(StablecoinPayoutLink.fiat_payment_intent_id == intent.id).limit(1)
    ).scalar_one_or_none()

    payment_status = None
    execution_status = None
    onchain_status = None
    tx_hash = None
    explorer_url = None
    execution_mode = None
    if link is not None and link.payment_order_id is not None:
        from app.db.models import PaymentOrder

        order = session.get(PaymentOrder, link.payment_order_id)
        if order is not None:
            payment_status = order.status
            onchain_status = order.onchain_status
            tx_hash = order.tx_hash
            explorer_url = order.explorer_url
            execution_mode = order.execution_mode
    if link is not None and link.execution_batch_id is not None:
        batch = session.get(PaymentExecutionBatch, link.execution_batch_id)
        if batch is not None:
            execution_status = batch.status

    return MarkFiatReceivedResponse(
        status="ok" if status == "ok" else "failed" if status == "failed" else "validation_error",
        fiat_payment=_to_intent_view(intent),
        quote=_to_quote_view(quote),
        fiat_collection=_to_collection_view(collection) if collection else None,
        payout_link=_to_payout_link_view(link) if link else None,
        payout=MerchantPayoutStatusView(
            payment_order_id=link.payment_order_id if link else None,
            execution_batch_id=link.execution_batch_id if link else None,
            payment_status=payment_status,
            execution_status=execution_status,
            onchain_status=onchain_status,
            tx_hash=tx_hash,
            explorer_url=explorer_url,
            execution_mode=execution_mode,
        ),
        message=message,
    )


def _mark_received_validation_error(
    *,
    intent: FiatPaymentIntent,
    quote: SettlementQuote,
    message: str,
) -> MarkFiatReceivedResponse:
    return MarkFiatReceivedResponse(
        status="validation_error",
        fiat_payment=_to_intent_view(intent),
        quote=_to_quote_view(quote),
        fiat_collection=None,
        payout_link=None,
        payout=MerchantPayoutStatusView(),
        message=message,
    )


def _build_collection_instructions(intent: FiatPaymentIntent) -> FiatPaymentCollectionInstructions:
    if intent.payment_channel == STRIPE_CHANNEL:
        note = (
            "Stripe 通道：以 webhook 确认支付成功后才触发稳定币出款。"
            " (Stripe channel: payout triggers only after webhook-confirmed payment success.)"
        )
        method = "stripe_checkout"
    else:
        note = "MVP 模式：法币到账由运营手工确认。 (MVP mode: fiat receipt is confirmed manually.)"
        method = "manual_bank_transfer"
    return FiatPaymentCollectionInstructions(
        collection_method=method,
        note=note,
        expected_currency=intent.payer_currency,
        expected_amount=float(intent.payer_amount),
        reference=intent.reference,
    )


def _resolve_fx_rate(*, source_currency: str, target_currency: str) -> Decimal:
    _ = target_currency
    fx_rate = FX_RATE_MAP.get(source_currency)
    if fx_rate is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported source_currency: {source_currency}",
        )
    return fx_rate.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)


def _to_quote_view(quote: SettlementQuote) -> SettlementQuoteView:
    route = f"{quote.target_network}:{quote.target_currency}"
    eta_text = "after fiat confirmation (testnet payout)"
    return SettlementQuoteView(
        id=quote.id,
        merchant_id=quote.merchant_id,
        beneficiary_id=quote.beneficiary_id,
        source_currency=quote.source_currency,
        source_amount=float(quote.source_amount),
        target_currency=quote.target_currency,
        target_amount=float(quote.target_amount),
        target_network=quote.target_network,
        fx_rate=float(quote.fx_rate),
        platform_fee=float(quote.platform_fee),
        network_fee=float(quote.network_fee),
        spread_bps=quote.spread_bps,
        total_fee_amount=float(quote.total_fee_amount),
        estimated_fee=float(quote.total_fee_amount),
        net_transfer_amount=float(quote.target_amount),
        route=route,
        eta_text=eta_text,
        expires_at=quote.expires_at,
        status=quote.status,
        quote_payload_json=quote.quote_payload_json,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def _to_intent_view(intent: FiatPaymentIntent) -> FiatPaymentIntentView:
    metadata = intent.metadata_json if isinstance(intent.metadata_json, dict) else {}
    bridge_failure = metadata.get("last_bridge_failure") if isinstance(metadata.get("last_bridge_failure"), dict) else None
    bridge_state = (
        FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value
        if intent.status == FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value
        else None
    )
    status_compat = (
        FiatPaymentIntentStatus.FIAT_RECEIVED.value
        if intent.status == FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value
        else intent.status
    )
    return FiatPaymentIntentView(
        id=intent.id,
        merchant_id=intent.merchant_id,
        beneficiary_id=intent.beneficiary_id,
        quote_id=intent.quote_id,
        payer_currency=intent.payer_currency,
        payer_amount=float(intent.payer_amount),
        target_stablecoin=intent.target_stablecoin,
        target_amount=float(intent.target_amount),
        target_network=intent.target_network,
        status=intent.status,
        payment_channel=intent.payment_channel,
        channel_payment_id=intent.channel_payment_id,
        channel_checkout_session_id=intent.channel_checkout_session_id,
        channel_checkout_url=intent.channel_checkout_url,
        channel_status=intent.channel_status,
        channel_confirmed_at=intent.channel_confirmed_at,
        webhook_received_at=intent.webhook_received_at,
        next_action=intent.next_action or _resolve_persisted_next_action(intent),
        kyc_verification_id=intent.kyc_verification_id,
        status_compat=status_compat,
        reference=intent.reference,
        source_text=intent.source_text,
        payout_command_id=intent.payout_command_id,
        metadata_json=intent.metadata_json,
        bridge_state=bridge_state,
        bridge_failure=bridge_failure,
        is_recoverable_bridge_failure=(bridge_state == FiatPaymentIntentStatus.BRIDGE_FAILED_RECOVERABLE.value),
        created_at=intent.created_at,
        updated_at=intent.updated_at,
    )


def _to_collection_view(collection: FiatCollection) -> FiatCollectionView:
    return FiatCollectionView(
        id=collection.id,
        fiat_payment_intent_id=collection.fiat_payment_intent_id,
        collection_method=collection.collection_method,
        bank_reference=collection.bank_reference,
        received_amount=float(collection.received_amount),
        currency=collection.currency,
        received_at=collection.received_at,
        confirmed_by_user_id=collection.confirmed_by_user_id,
        status=collection.status,
        metadata_json=collection.metadata_json,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _to_payout_link_view(link: StablecoinPayoutLink) -> StablecoinPayoutLinkView:
    metadata = link.metadata_json if isinstance(link.metadata_json, dict) else {}
    bridge_failure = metadata.get("bridge_failure") if isinstance(metadata.get("bridge_failure"), dict) else None
    bridge_state = "bridge_failed_recoverable" if link.status == "bridge_failed_recoverable" else None
    return StablecoinPayoutLinkView(
        id=link.id,
        fiat_payment_intent_id=link.fiat_payment_intent_id,
        payment_order_id=link.payment_order_id,
        execution_batch_id=link.execution_batch_id,
        status=link.status,
        metadata_json=link.metadata_json,
        bridge_state=bridge_state,
        bridge_failure=bridge_failure,
        is_recoverable_bridge_failure=(bridge_state == "bridge_failed_recoverable"),
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _fiat_trace_id(intent_id: UUID) -> str:
    return f"trace-fiat-{intent_id.hex[:12]}"


def _build_audit(
    *,
    actor_user_id: UUID | None,
    entity_type: str,
    entity_id: UUID,
    action: str,
    trace_id: str,
    before_json: dict[str, Any] | None,
    after_json: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        id=uuid.uuid4(),
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_json=before_json,
        after_json=after_json,
        trace_id=trace_id,
    )
