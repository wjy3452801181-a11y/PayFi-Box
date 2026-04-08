from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from app.db.session import get_db_session
from app.modules.balance.schemas import (
    BalancePaymentConfirmRequest,
    BalancePaymentConfirmResponse,
    BalancePaymentPreviewRequest,
    BalancePaymentPreviewResponse,
    CreateFiatDepositRequest,
    CreateFiatDepositResponse,
    DepositDetailResponse,
    PlatformBalanceAccountResponse,
    PlatformBalanceLedgerResponse,
    StartDepositStripePaymentRequest,
    StartDepositStripePaymentResponse,
)
from app.modules.balance.service import (
    confirm_payment_from_balance,
    create_fiat_deposit,
    get_balance_account,
    get_balance_ledger,
    get_deposit_detail,
    preview_payment_from_balance,
    start_deposit_stripe_payment,
    sync_deposit_stripe_payment_status,
)

router = APIRouter(prefix="/api/balance", tags=["balance"])


@router.post("/deposits", response_model=CreateFiatDepositResponse)
def post_balance_deposit(request: CreateFiatDepositRequest) -> CreateFiatDepositResponse:
    with get_db_session() as session:
        return create_fiat_deposit(session=session, request=request)


@router.post("/deposits/{deposit_order_id}/start-stripe-payment", response_model=StartDepositStripePaymentResponse)
def post_balance_deposit_start_stripe_payment(
    deposit_order_id: UUID,
    request: StartDepositStripePaymentRequest | None = None,
) -> StartDepositStripePaymentResponse:
    with get_db_session() as session:
        return start_deposit_stripe_payment(
            session=session,
            deposit_order_id=deposit_order_id,
            request=request or StartDepositStripePaymentRequest(),
        )


@router.post("/deposits/{deposit_order_id}/sync-stripe-payment", response_model=DepositDetailResponse)
def post_balance_deposit_sync_stripe_payment(deposit_order_id: UUID) -> DepositDetailResponse:
    with get_db_session() as session:
        return sync_deposit_stripe_payment_status(session=session, deposit_order_id=deposit_order_id)


@router.get("/deposits/{deposit_order_id}", response_model=DepositDetailResponse)
def get_balance_deposit_detail(deposit_order_id: UUID) -> DepositDetailResponse:
    with get_db_session() as session:
        return get_deposit_detail(session=session, deposit_order_id=deposit_order_id)


@router.get("/accounts/{user_id}", response_model=PlatformBalanceAccountResponse)
def get_balance_account_by_user(
    user_id: UUID,
    currency: str = Query(default="USDT"),
) -> PlatformBalanceAccountResponse:
    with get_db_session() as session:
        return get_balance_account(session=session, user_id=user_id, currency=currency)


@router.get("/accounts/{user_id}/ledger", response_model=PlatformBalanceLedgerResponse)
def get_balance_ledger_by_user(
    user_id: UUID,
    currency: str = Query(default="USDT"),
    limit: int = Query(default=20, ge=1, le=100),
) -> PlatformBalanceLedgerResponse:
    with get_db_session() as session:
        return get_balance_ledger(session=session, user_id=user_id, currency=currency, limit=limit)


@router.post("/payments/preview", response_model=BalancePaymentPreviewResponse)
def post_balance_payment_preview(request: BalancePaymentPreviewRequest) -> BalancePaymentPreviewResponse:
    with get_db_session() as session:
        return preview_payment_from_balance(session=session, request=request)


@router.post("/payments/confirm", response_model=BalancePaymentConfirmResponse)
def post_balance_payment_confirm(request: BalancePaymentConfirmRequest) -> BalancePaymentConfirmResponse:
    with get_db_session() as session:
        return confirm_payment_from_balance(session=session, request=request)
