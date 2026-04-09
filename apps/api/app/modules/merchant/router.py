from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.access import (
    get_actor_user_id,
    normalize_actor_scoped_user_id,
    require_actor_matches_user_id,
    require_fiat_payment_access,
    require_quote_access,
)
from app.db.session import get_db_session
from app.modules.merchant.schemas import (
    CreateStripeSessionRequest,
    CreateStripeSessionResponse,
    CreateFiatPaymentRequest,
    CreateFiatPaymentResponse,
    MarkFiatReceivedRequest,
    MarkFiatReceivedResponse,
    MerchantFiatPaymentDetailResponse,
    MerchantFiatPaymentListResponse,
    SettlementQuoteRequest,
    SettlementQuoteResponse,
)
from app.modules.merchant.service import (
    create_stripe_checkout_session,
    create_fiat_payment_intent,
    create_settlement_quote,
    get_fiat_payment_detail,
    list_fiat_payments,
    mark_fiat_received,
    sync_stripe_payment_status,
)

router = APIRouter(prefix="/api/merchant", tags=["merchant"])


@router.post("/quote", response_model=SettlementQuoteResponse)
def post_merchant_quote(
    request: SettlementQuoteRequest,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> SettlementQuoteResponse:
    with get_db_session() as session:
        require_actor_matches_user_id(
            session=session,
            actor_user_id=actor_user_id,
            expected_user_id=request.merchant_id,
            label="merchant_id",
        )
        return create_settlement_quote(session=session, request=request)


@router.post("/fiat-payment", response_model=CreateFiatPaymentResponse)
def post_merchant_fiat_payment(
    request: CreateFiatPaymentRequest,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> CreateFiatPaymentResponse:
    with get_db_session() as session:
        require_actor_matches_user_id(
            session=session,
            actor_user_id=actor_user_id,
            expected_user_id=request.merchant_id,
            label="merchant_id",
        )
        require_quote_access(session=session, actor_user_id=actor_user_id, quote_id=request.quote_id)
        return create_fiat_payment_intent(session=session, request=request)


@router.post("/fiat-payment/{fiat_payment_intent_id}/mark-received", response_model=MarkFiatReceivedResponse)
def post_mark_fiat_received(
    fiat_payment_intent_id: UUID,
    request: MarkFiatReceivedRequest,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> MarkFiatReceivedResponse:
    with get_db_session() as session:
        require_fiat_payment_access(
            session=session,
            actor_user_id=actor_user_id,
            fiat_payment_intent_id=fiat_payment_intent_id,
        )
        if request.confirmed_by_user_id is not None and request.confirmed_by_user_id != actor_user_id:
            raise HTTPException(status_code=403, detail="confirmed_by_user_id does not match the current actor")
        return mark_fiat_received(
            session=session,
            fiat_payment_intent_id=fiat_payment_intent_id,
            request=request.model_copy(update={"confirmed_by_user_id": actor_user_id}),
        )


@router.post(
    "/fiat-payment/{fiat_payment_intent_id}/create-stripe-session",
    response_model=CreateStripeSessionResponse,
)
def post_create_stripe_session(
    fiat_payment_intent_id: UUID,
    request: CreateStripeSessionRequest | None = None,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> CreateStripeSessionResponse:
    with get_db_session() as session:
        require_fiat_payment_access(
            session=session,
            actor_user_id=actor_user_id,
            fiat_payment_intent_id=fiat_payment_intent_id,
        )
        return create_stripe_checkout_session(
            session=session,
            fiat_payment_intent_id=fiat_payment_intent_id,
            request=request or CreateStripeSessionRequest(),
        )


@router.post(
    "/fiat-payment/{fiat_payment_intent_id}/start-stripe-payment",
    response_model=CreateStripeSessionResponse,
)
def post_start_stripe_payment(
    fiat_payment_intent_id: UUID,
    request: CreateStripeSessionRequest | None = None,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> CreateStripeSessionResponse:
    with get_db_session() as session:
        require_fiat_payment_access(
            session=session,
            actor_user_id=actor_user_id,
            fiat_payment_intent_id=fiat_payment_intent_id,
        )
        return create_stripe_checkout_session(
            session=session,
            fiat_payment_intent_id=fiat_payment_intent_id,
            request=request or CreateStripeSessionRequest(),
        )


@router.get("/fiat-payment/{fiat_payment_intent_id}", response_model=MerchantFiatPaymentDetailResponse)
def get_merchant_fiat_payment_detail(
    fiat_payment_intent_id: UUID,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> MerchantFiatPaymentDetailResponse:
    with get_db_session() as session:
        require_fiat_payment_access(
            session=session,
            actor_user_id=actor_user_id,
            fiat_payment_intent_id=fiat_payment_intent_id,
        )
        return get_fiat_payment_detail(session=session, fiat_payment_intent_id=fiat_payment_intent_id)


@router.post("/fiat-payment/{fiat_payment_intent_id}/sync-stripe-payment", response_model=MerchantFiatPaymentDetailResponse)
def post_sync_stripe_payment(
    fiat_payment_intent_id: UUID,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> MerchantFiatPaymentDetailResponse:
    with get_db_session() as session:
        require_fiat_payment_access(
            session=session,
            actor_user_id=actor_user_id,
            fiat_payment_intent_id=fiat_payment_intent_id,
        )
        return sync_stripe_payment_status(session=session, fiat_payment_intent_id=fiat_payment_intent_id)


@router.get("/fiat-payments", response_model=MerchantFiatPaymentListResponse)
def get_merchant_fiat_payments(
    merchant_id: UUID | None = None,
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> MerchantFiatPaymentListResponse:
    with get_db_session() as session:
        scoped_merchant_id = normalize_actor_scoped_user_id(
            session=session,
            actor_user_id=actor_user_id,
            requested_user_id=merchant_id,
        )
        return list_fiat_payments(
            session=session,
            merchant_id=scoped_merchant_id,
            status_value=status,
            limit=limit,
        )
