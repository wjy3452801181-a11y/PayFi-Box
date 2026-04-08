from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.db.session import get_db_session
from app.modules.payments.schemas import (
    PaymentDetailResponse,
    PaymentListResponse,
    RetryMockRequest,
    RetryMockResponse,
)
from app.modules.payments.service import get_payment_detail, list_payments, retry_payment_mock

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("", response_model=PaymentListResponse)
def get_payments(
    status: str | None = None,
    risk_level: str | None = None,
    user_id: UUID | None = None,
    organization_id: UUID | None = None,
    beneficiary_name: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    sort_by: Literal["created_at", "amount", "status", "risk_level"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> PaymentListResponse:
    with get_db_session() as session:
        return list_payments(
            session=session,
            status_value=status,
            risk_level=risk_level,
            user_id=user_id,
            organization_id=organization_id,
            beneficiary_name=beneficiary_name,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )


@router.get("/{payment_id}", response_model=PaymentDetailResponse)
def get_payment_by_id(payment_id: UUID) -> PaymentDetailResponse:
    with get_db_session() as session:
        return get_payment_detail(session=session, payment_id=payment_id)


@router.post("/{payment_id}/retry-mock", response_model=RetryMockResponse)
def post_payment_retry_mock(payment_id: UUID, request: RetryMockRequest) -> RetryMockResponse:
    with get_db_session() as session:
        return retry_payment_mock(session=session, payment_id=payment_id, request=request)
