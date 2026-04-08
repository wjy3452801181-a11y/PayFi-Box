from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from web3 import Web3

from app.db.models import Beneficiary, PaymentOrder
from app.modules.beneficiaries.schemas import (
    BeneficiaryCoreDetails,
    BeneficiaryDetailResponse,
    BeneficiaryListFilters,
    BeneficiaryListItem,
    BeneficiaryListResponse,
    BeneficiaryPatchRequest,
    BeneficiaryRecentPayment,
    BeneficiaryRiskProfile,
    BeneficiaryStats,
)
from app.modules.risk.reason_codes import normalize_reason_codes


def list_beneficiaries(
    session: Session,
    *,
    country: str | None,
    risk_level: str | None,
    is_blacklisted: bool | None,
    name: str | None,
    organization_id: UUID | None,
    limit: int,
) -> BeneficiaryListResponse:
    payment_stats_subquery = (
        select(
            PaymentOrder.beneficiary_id.label("beneficiary_id"),
            func.count(PaymentOrder.id).label("payment_count"),
            func.max(PaymentOrder.created_at).label("latest_payment_at"),
        )
        .group_by(PaymentOrder.beneficiary_id)
        .subquery()
    )

    stmt = (
        select(
            Beneficiary,
            func.coalesce(payment_stats_subquery.c.payment_count, 0).label("payment_count"),
            payment_stats_subquery.c.latest_payment_at.label("latest_payment_at"),
        )
        .outerjoin(
            payment_stats_subquery,
            payment_stats_subquery.c.beneficiary_id == Beneficiary.id,
        )
    )

    if country:
        stmt = stmt.where(Beneficiary.country == country.upper())
    if risk_level:
        stmt = stmt.where(Beneficiary.risk_level == risk_level)
    if is_blacklisted is not None:
        stmt = stmt.where(Beneficiary.is_blacklisted == is_blacklisted)
    if name:
        stmt = stmt.where(Beneficiary.name.ilike(f"%{name}%"))
    if organization_id:
        stmt = stmt.where(Beneficiary.organization_id == organization_id)

    total = int(session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    rows = session.execute(stmt.order_by(Beneficiary.created_at.desc(), Beneficiary.id.desc()).limit(limit)).all()

    return BeneficiaryListResponse(
        total=total,
        limit=limit,
        filters=BeneficiaryListFilters(
            country=country.upper() if country else None,
            risk_level=risk_level,
            is_blacklisted=is_blacklisted,
            name=name,
            organization_id=organization_id,
        ),
        items=[
            BeneficiaryListItem(
                beneficiary_id=beneficiary.id,
                name=beneficiary.name,
                country=beneficiary.country,
                risk_level=beneficiary.risk_level,
                is_blacklisted=beneficiary.is_blacklisted,
                organization_id=beneficiary.organization_id,
                has_wallet_address=bool(beneficiary.wallet_address),
                payment_count=int(payment_count or 0),
                latest_payment_at=latest_payment_at,
            )
            for beneficiary, payment_count, latest_payment_at in rows
        ],
    )


def get_beneficiary_detail(session: Session, beneficiary_id: UUID) -> BeneficiaryDetailResponse:
    beneficiary = session.get(Beneficiary, beneficiary_id)
    if beneficiary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"beneficiary not found: {beneficiary_id}",
        )

    payments = session.execute(
        select(PaymentOrder)
        .where(PaymentOrder.beneficiary_id == beneficiary.id)
        .order_by(PaymentOrder.created_at.desc())
    ).scalars().all()

    total_volume = sum((_to_float(item.amount) for item in payments), start=0.0)
    stats = BeneficiaryStats(
        total_payments=len(payments),
        total_payment_volume=round(total_volume, 2),
        executed_payments=sum(1 for item in payments if item.status == "executed"),
        failed_payments=sum(1 for item in payments if item.status == "failed"),
        latest_payment_at=payments[0].created_at if payments else None,
    )

    recent_payments = [
        BeneficiaryRecentPayment(
            payment_order_id=item.id,
            created_at=item.created_at,
            amount=_to_float(item.amount),
            currency=item.currency,
            status=item.status,
            risk_level=item.risk_level,
            reference=item.reference,
            source_command_id=item.source_command_id,
        )
        for item in payments[:5]
    ]

    risk_profile = _build_risk_profile(beneficiary=beneficiary, payments=payments)
    return BeneficiaryDetailResponse(
        beneficiary=BeneficiaryCoreDetails(
            beneficiary_id=beneficiary.id,
            name=beneficiary.name,
            country=beneficiary.country,
            risk_level=beneficiary.risk_level,
            is_blacklisted=beneficiary.is_blacklisted,
            organization_id=beneficiary.organization_id,
            wallet_address=beneficiary.wallet_address,
            bank_account_mock=beneficiary.bank_account_mock,
            metadata_json=beneficiary.metadata_json,
            created_at=beneficiary.created_at,
            updated_at=beneficiary.updated_at,
        ),
        stats=stats,
        recent_payments=recent_payments,
        risk_profile=risk_profile,
    )


def patch_beneficiary(
    session: Session,
    *,
    beneficiary_id: UUID,
    request: BeneficiaryPatchRequest,
) -> BeneficiaryDetailResponse:
    beneficiary = session.get(Beneficiary, beneficiary_id)
    if beneficiary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"beneficiary not found: {beneficiary_id}",
        )

    if "wallet_address" not in request.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no supported fields provided; supported fields: wallet_address",
        )

    wallet_address = request.wallet_address
    if wallet_address is None or not wallet_address.strip():
        beneficiary.wallet_address = None
    else:
        value = wallet_address.strip()
        if not Web3.is_address(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid EVM wallet_address",
            )
        beneficiary.wallet_address = Web3.to_checksum_address(value)

    session.add(beneficiary)
    session.commit()
    session.refresh(beneficiary)
    return get_beneficiary_detail(session=session, beneficiary_id=beneficiary_id)


def _build_risk_profile(
    *,
    beneficiary: Beneficiary,
    payments: list[PaymentOrder],
) -> BeneficiaryRiskProfile:
    reason_codes: list[str] = []
    if beneficiary.is_blacklisted:
        reason_codes.append("BLACKLISTED_BENEFICIARY")
    if beneficiary.risk_level == "high":
        reason_codes.append("HIGH_RISK_BENEFICIARY")
    elif beneficiary.risk_level == "medium":
        reason_codes.append("MEDIUM_RISK_BENEFICIARY")
    if beneficiary.country != "CN":
        reason_codes.append("CROSS_BORDER")
    if any(item.amount >= Decimal("10000") for item in payments):
        reason_codes.append("HIGH_AMOUNT")
    reason_codes = normalize_reason_codes(reason_codes)

    if beneficiary.is_blacklisted:
        message = "该受益人命中黑名单，建议阻断。 (This beneficiary is blacklisted and should be blocked.)"
    elif beneficiary.risk_level == "high":
        message = "该受益人为高风险，建议人工复核。 (This beneficiary is high risk; manual review is recommended.)"
    elif beneficiary.risk_level == "medium":
        message = "该受益人为中风险，建议补充检查。 (This beneficiary is medium risk; additional checks are recommended.)"
    else:
        message = "该受益人风险较低，可按常规流程处理。 (This beneficiary is low risk and can follow normal flow.)"

    return BeneficiaryRiskProfile(
        risk_level=beneficiary.risk_level,
        is_blacklisted=beneficiary.is_blacklisted,
        reason_codes=reason_codes or ["PASS_BASELINE_POLICY"],
        message=message,
    )


def _to_float(value: Decimal) -> float:
    return float(value)
