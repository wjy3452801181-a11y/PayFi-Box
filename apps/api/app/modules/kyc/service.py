from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AuditLog,
    FiatPaymentIntent,
    FiatPaymentIntentStatus,
    KycVerification,
    KycVerificationStatus,
    User,
)
from app.modules.kyc.schemas import (
    KycDetailResponse,
    KycStartRequest,
    KycStartResponse,
    KycVerificationView,
)

try:
    import stripe
except Exception:  # pragma: no cover - dependency guard for local environments
    stripe = None


def start_kyc_verification(session: Session, request: KycStartRequest) -> KycStartResponse:
    settings = get_settings()
    subject = session.get(User, request.subject_id)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"subject not found: {request.subject_id}",
        )

    existing = session.execute(
        select(KycVerification)
        .where(
            KycVerification.subject_type == request.subject_type,
            KycVerification.subject_id == request.subject_id,
            KycVerification.provider == request.provider,
        )
        .order_by(KycVerification.created_at.desc(), KycVerification.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None and not request.force_new:
        if settings.settlement_kyc_demo_mode and existing.status != KycVerificationStatus.VERIFIED.value:
            now = datetime.now(timezone.utc)
            before_status = existing.status
            existing.status = KycVerificationStatus.VERIFIED.value
            existing.verified_at = now
            existing.failure_reason = None
            meta = dict(existing.metadata_json or {}) if isinstance(existing.metadata_json, dict) else {}
            meta["demo_mode"] = True
            meta["provider_status"] = "verified"
            existing.metadata_json = meta
            session.add(existing)
            session.add(
                AuditLog(
                    id=uuid.uuid4(),
                    actor_user_id=request.subject_id if request.subject_type == "merchant" else None,
                    entity_type="kyc_verification",
                    entity_id=existing.id,
                    action="kyc_verification_demo_auto_verified",
                    before_json={"status": before_status},
                    after_json={"status": existing.status, "demo_mode": True},
                    trace_id=f"trace-kyc-{existing.id.hex[:12]}",
                )
            )
            _promote_pending_fiat_intents_for_verified_kyc(
                session=session,
                verification=existing,
            )
            session.commit()
            session.refresh(existing)
            return KycStartResponse(
                status="ok",
                verification=_to_view(existing),
                next_action="none",
                message="Demo KYC 已自动通过。 (Demo KYC auto-verified.)",
            )
        if existing.status == KycVerificationStatus.VERIFIED.value:
            return KycStartResponse(
                status="ok",
                verification=_to_view(existing),
                next_action="none",
                message="KYC 已完成验证。 (KYC is already verified.)",
            )
        if existing.status in {
            KycVerificationStatus.PENDING.value,
            KycVerificationStatus.NOT_STARTED.value,
            KycVerificationStatus.REQUIRES_REVIEW.value,
        }:
            return KycStartResponse(
                status="ok",
                verification=_to_view(existing),
                next_action="complete_kyc",
                message="返回现有 KYC 会话，请继续完成验证。 (Returning existing KYC session.)",
            )

    if settings.settlement_kyc_demo_mode:
        verification = _create_demo_verified_kyc(
            session=session,
            request=request,
        )
        _promote_pending_fiat_intents_for_verified_kyc(
            session=session,
            verification=verification,
        )
        session.commit()
        session.refresh(verification)
        return KycStartResponse(
            status="ok",
            verification=_to_view(verification),
            next_action="none",
            message="Demo KYC 已自动通过。 (Demo KYC auto-verified.)",
        )

    if not settings.stripe_secret_key:
        return KycStartResponse(
            status="failed",
            verification=None,
            next_action="none",
            message="未配置 STRIPE_SECRET_KEY，无法发起 KYC。 (STRIPE_SECRET_KEY is missing.)",
        )
    if stripe is None:
        return KycStartResponse(
            status="failed",
            verification=None,
            next_action="none",
            message="Stripe SDK 未安装，无法发起 KYC。 (Stripe SDK is not installed.)",
        )

    stripe.api_key = settings.stripe_secret_key
    try:
        provider_session = stripe.identity.VerificationSession.create(
            type="document",
            metadata={
                "subject_type": request.subject_type,
                "subject_id": str(request.subject_id),
            },
            return_url=settings.stripe_identity_return_url,
        )
    except Exception as exc:
        return KycStartResponse(
            status="failed",
            verification=None,
            next_action="none",
            message=f"KYC 会话创建失败：{exc} (Failed to create KYC verification session.)",
        )

    provider_session_id = _stripe_get(provider_session, "id")
    provider_status = str(_stripe_get(provider_session, "status") or "pending").lower()
    verification = KycVerification(
        id=uuid.uuid4(),
        subject_type=request.subject_type,
        subject_id=request.subject_id,
        provider=request.provider,
        provider_verification_session_id=str(provider_session_id) if provider_session_id else None,
        status=_map_provider_status(provider_status),
        verification_url=_safe_str(_stripe_get(provider_session, "url")),
        metadata_json={
            "provider_status": provider_status,
            "client_secret": _safe_str(_stripe_get(provider_session, "client_secret")),
            "request_locale": request.locale,
        },
    )
    session.add(verification)
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_user_id=request.subject_id if request.subject_type == "merchant" else None,
            entity_type="kyc_verification",
            entity_id=verification.id,
            action="kyc_verification_started",
            before_json=None,
            after_json={
                "status": verification.status,
                "provider": verification.provider,
                "provider_verification_session_id": verification.provider_verification_session_id,
            },
            trace_id=f"trace-kyc-{verification.id.hex[:12]}",
        )
    )
    session.commit()
    session.refresh(verification)
    return KycStartResponse(
        status="ok",
        verification=_to_view(verification),
        next_action="complete_kyc",
        message="KYC 会话已创建，请完成身份验证。 (KYC verification session created.)",
    )


def get_kyc_verification(session: Session, kyc_id: UUID) -> KycDetailResponse:
    verification = session.get(KycVerification, kyc_id)
    if verification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"kyc verification not found: {kyc_id}")
    return KycDetailResponse(status="ok", verification=_to_view(verification))


def _to_view(item: KycVerification) -> KycVerificationView:
    return KycVerificationView(
        id=item.id,
        subject_type=item.subject_type,
        subject_id=item.subject_id,
        provider=item.provider,
        provider_verification_session_id=item.provider_verification_session_id,
        status=item.status,
        verification_url=item.verification_url,
        verified_at=item.verified_at,
        failure_reason=item.failure_reason,
        metadata_json=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _map_provider_status(provider_status: str) -> str:
    if provider_status == "verified":
        return KycVerificationStatus.VERIFIED.value
    if provider_status in {"canceled", "expired"}:
        return KycVerificationStatus.EXPIRED.value
    if provider_status in {"requires_input", "unverified", "processing"}:
        return KycVerificationStatus.PENDING.value
    if provider_status in {"failed", "rejected"}:
        return KycVerificationStatus.FAILED.value
    return KycVerificationStatus.PENDING.value


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


def _create_demo_verified_kyc(
    *,
    session: Session,
    request: KycStartRequest,
) -> KycVerification:
    now = datetime.now(timezone.utc)
    verification = KycVerification(
        id=uuid.uuid4(),
        subject_type=request.subject_type,
        subject_id=request.subject_id,
        provider=request.provider,
        provider_verification_session_id=f"demo_kyc_{uuid.uuid4().hex[:12]}",
        status=KycVerificationStatus.VERIFIED.value,
        verification_url=f"http://localhost:3000/merchant?kyc=demo_verified&kyc_id={uuid.uuid4()}",
        verified_at=now,
        metadata_json={
            "provider_status": "verified",
            "demo_mode": True,
            "request_locale": request.locale,
        },
    )
    session.add(verification)
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_user_id=request.subject_id if request.subject_type == "merchant" else None,
            entity_type="kyc_verification",
            entity_id=verification.id,
            action="kyc_verification_demo_auto_verified",
            before_json=None,
            after_json={
                "status": verification.status,
                "provider": verification.provider,
                "provider_verification_session_id": verification.provider_verification_session_id,
                "demo_mode": True,
            },
            trace_id=f"trace-kyc-{verification.id.hex[:12]}",
        )
    )
    session.flush()
    return verification


def _promote_pending_fiat_intents_for_verified_kyc(
    *,
    session: Session,
    verification: KycVerification,
) -> None:
    if verification.subject_type != "merchant" or verification.status != KycVerificationStatus.VERIFIED.value:
        return
    pending_intents = session.execute(
        select(FiatPaymentIntent)
        .where(
            FiatPaymentIntent.merchant_id == verification.subject_id,
            FiatPaymentIntent.payment_channel == "stripe",
            FiatPaymentIntent.status == FiatPaymentIntentStatus.AWAITING_KYC.value,
        )
        .with_for_update()
    ).scalars().all()
    for intent in pending_intents:
        before_status = intent.status
        intent.status = FiatPaymentIntentStatus.AWAITING_CHANNEL_PAYMENT.value
        intent.channel_status = "awaiting_payment"
        intent.kyc_verification_id = verification.id
        intent.next_action = "create_stripe_session"
        session.add(intent)
        session.add(
            AuditLog(
                id=uuid.uuid4(),
                actor_user_id=intent.merchant_id,
                entity_type="fiat_payment_intent",
                entity_id=intent.id,
                action="kyc_verified_for_fiat_intent",
                before_json={"status": before_status},
                after_json={
                    "status": intent.status,
                    "channel_status": intent.channel_status,
                    "kyc_verification_id": str(verification.id),
                    "source": "demo_auto_verify",
                },
                trace_id=f"trace-fiat-{intent.id.hex[:12]}",
            )
        )
