from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AccessTokenError, parse_access_token
from app.db.models import (
    CommandExecution,
    FiatDepositOrder,
    FiatPaymentIntent,
    KycVerification,
    PaymentExecutionBatch,
    PaymentExecutionItem,
    PaymentOrder,
    SettlementQuote,
    User,
)

AUTH_HEADER_NAME = "Authorization"


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{AUTH_HEADER_NAME} header is required",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.strip().lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{AUTH_HEADER_NAME} must be a Bearer token",
        )
    return token.strip()


def get_actor_user_id(authorization: str | None = Header(default=None, alias=AUTH_HEADER_NAME)) -> UUID:
    token = _extract_bearer_token(authorization)
    try:
        claims = parse_access_token(token)
    except AccessTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return claims.user_id


def require_actor_user(session: Session, actor_user_id: UUID) -> User:
    actor = session.get(User, actor_user_id)
    if actor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"actor user not found: {actor_user_id}",
        )
    return actor


def require_actor_matches_user_id(
    *,
    session: Session,
    actor_user_id: UUID,
    expected_user_id: UUID,
    label: str,
) -> None:
    require_actor_user(session, actor_user_id)
    if actor_user_id != expected_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{label} does not belong to the current actor",
        )


def normalize_actor_scoped_user_id(
    *,
    session: Session,
    actor_user_id: UUID,
    requested_user_id: UUID | None,
) -> UUID:
    require_actor_user(session, actor_user_id)
    if requested_user_id is not None and requested_user_id != actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requested user_id does not belong to the current actor",
        )
    return actor_user_id


def require_command_access(session: Session, *, actor_user_id: UUID, command_id: UUID) -> CommandExecution:
    require_actor_user(session, actor_user_id)
    command = session.get(CommandExecution, command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"command not found: {command_id}")
    if command.user_id != actor_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="command does not belong to the current actor")
    return command


def require_payment_access(session: Session, *, actor_user_id: UUID, payment_id: UUID) -> PaymentOrder:
    require_actor_user(session, actor_user_id)
    payment = session.get(PaymentOrder, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"payment not found: {payment_id}")
    if payment.user_id != actor_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="payment does not belong to the current actor")
    return payment


def require_quote_access(session: Session, *, actor_user_id: UUID, quote_id: UUID) -> SettlementQuote:
    require_actor_user(session, actor_user_id)
    quote = session.get(SettlementQuote, quote_id)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"quote not found: {quote_id}")
    if quote.merchant_id != actor_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="quote does not belong to the current actor")
    return quote


def require_fiat_payment_access(
    session: Session,
    *,
    actor_user_id: UUID,
    fiat_payment_intent_id: UUID,
) -> FiatPaymentIntent:
    require_actor_user(session, actor_user_id)
    intent = session.get(FiatPaymentIntent, fiat_payment_intent_id)
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"fiat_payment_intent not found: {fiat_payment_intent_id}",
        )
    if intent.merchant_id != actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="fiat_payment_intent does not belong to the current actor",
        )
    return intent


def require_deposit_access(session: Session, *, actor_user_id: UUID, deposit_order_id: UUID) -> FiatDepositOrder:
    require_actor_user(session, actor_user_id)
    deposit = session.get(FiatDepositOrder, deposit_order_id)
    if deposit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"deposit_order not found: {deposit_order_id}",
        )
    if deposit.user_id != actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="deposit_order does not belong to the current actor",
        )
    return deposit


def require_kyc_access(session: Session, *, actor_user_id: UUID, kyc_id: UUID) -> KycVerification:
    require_actor_user(session, actor_user_id)
    verification = session.get(KycVerification, kyc_id)
    if verification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"kyc verification not found: {kyc_id}")
    if verification.subject_id != actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="kyc verification does not belong to the current actor",
        )
    return verification


def require_execution_item_access(
    session: Session,
    *,
    actor_user_id: UUID,
    execution_item_id: UUID,
) -> tuple[PaymentExecutionItem, PaymentExecutionBatch, PaymentOrder]:
    require_actor_user(session, actor_user_id)
    row = session.execute(
        select(PaymentExecutionItem, PaymentExecutionBatch, PaymentOrder)
        .join(
            PaymentExecutionBatch,
            PaymentExecutionBatch.id == PaymentExecutionItem.execution_batch_id,
        )
        .join(
            PaymentOrder,
            PaymentOrder.id == PaymentExecutionBatch.payment_order_id,
        )
        .where(PaymentExecutionItem.id == execution_item_id)
        .limit(1)
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"execution item not found: {execution_item_id}",
        )
    item, batch, payment = row
    if payment.user_id != actor_user_id and batch.requested_by_user_id != actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="execution item does not belong to the current actor",
        )
    return item, batch, payment


def require_execution_batch_access(
    session: Session,
    *,
    actor_user_id: UUID,
    execution_batch_id: UUID,
) -> PaymentExecutionBatch:
    require_actor_user(session, actor_user_id)
    row = session.execute(
        select(PaymentExecutionBatch, PaymentOrder)
        .join(PaymentOrder, PaymentOrder.id == PaymentExecutionBatch.payment_order_id)
        .where(PaymentExecutionBatch.id == execution_batch_id)
        .limit(1)
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"execution_batch not found: {execution_batch_id}",
        )
    batch, payment = row
    if payment.user_id != actor_user_id and batch.requested_by_user_id != actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="execution_batch does not belong to the current actor",
        )
    return batch
