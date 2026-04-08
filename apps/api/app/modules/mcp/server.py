from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.db.models import FiatDepositOrder
from app.db.session import get_db_session
from app.modules.balance.schemas import (
    BalancePaymentConfirmRequest,
    BalancePaymentPreviewRequest,
    CreateFiatDepositRequest,
    StartDepositStripePaymentRequest,
)
from app.modules.balance.service import (
    _load_balance_kyc,
    _require_user,
    confirm_payment_from_balance,
    create_fiat_deposit,
    get_balance_account,
    get_balance_ledger,
    get_deposit_detail,
    preview_payment_from_balance,
    start_deposit_stripe_payment,
    sync_deposit_stripe_payment_status,
)
from app.modules.kyc.schemas import KycStartRequest
from app.modules.kyc.service import get_kyc_verification, start_kyc_verification

settings = get_settings()

payfi_mcp = FastMCP(
    name="PayFi Box MCP",
    instructions=(
        "PayFi Box exposes KYC-gated stablecoin settlement tools. "
        "Always check MCP capability status first. "
        "If KYC is not verified, direct the user to start identity check before attempting balance or payment tools. "
        "Preview before confirm. Treat confirm as a high-risk settlement action."
    ),
    website_url="http://127.0.0.1:3000",
    streamable_http_path="/",
)


def _json(model_or_dict):
    if hasattr(model_or_dict, "model_dump"):
        return model_or_dict.model_dump(mode="json")
    return model_or_dict


def _kyc_block_payload(*, user_id: UUID, verification_id: str | None = None) -> dict:
    return {
        "status": "blocked_kyc_required",
        "message": "Complete identity verification before using PayFi Box MCP payment tools.",
        "next_action": "start_kyc",
        "summary": {
            "user_id": str(user_id),
            "kyc_status": "required",
        },
        "technical_details": {
            "subject_type": "user",
            "subject_id": str(user_id),
            "kyc_verification_id": verification_id,
        },
    }


def _http_error_payload(*, message: str, status_code: int, detail: str | dict | list | None, summary: dict | None = None) -> dict:
    return {
        "status": "validation_error",
        "message": message,
        "next_action": "none",
        "summary": summary or {},
        "technical_details": {
            "http_status": status_code,
            "detail": detail,
        },
    }


MCP_PRE_KYC_TOOLS = ["start_user_kyc", "get_kyc_status", "mcp_capability_status"]
MCP_VERIFIED_TOOLS = [
    "get_balance",
    "get_balance_ledger",
    "create_balance_deposit",
    "start_balance_deposit_checkout",
    "sync_balance_deposit_status",
    "get_balance_deposit_detail",
    "payment_preview_from_balance",
    "payment_confirm_from_balance",
]


def _parse_uuid_param(*, field_name: str, raw_value: str, summary: dict | None = None) -> tuple[UUID | None, dict | None]:
    try:
        return UUID(raw_value), None
    except (TypeError, ValueError, AttributeError):
        return None, _http_error_payload(
            message=f"invalid {field_name}",
            status_code=400,
            detail={field_name: "must be a valid UUID"},
            summary=summary or {field_name: raw_value},
        )


def _ensure_mcp_kyc(user_id: UUID) -> dict | None:
    try:
        with get_db_session() as session:
            _require_user(session=session, user_id=user_id)
            verification = _load_balance_kyc(session=session, user_id=user_id)
            if bool(settings.settlement_require_kyc) and (
                verification is None or verification.status.lower() != "verified"
            ):
                return _kyc_block_payload(
                    user_id=user_id,
                    verification_id=str(verification.id) if verification is not None else None,
                )
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": str(user_id)},
        )
    return None


def _ensure_deposit_belongs_to_user(*, user_id: UUID, deposit_order_id: UUID) -> dict | None:
    try:
        with get_db_session() as session:
            _require_user(session=session, user_id=user_id)
            deposit = session.get(FiatDepositOrder, deposit_order_id)
            if deposit is None:
                raise HTTPException(status_code=404, detail=f"deposit_order not found: {deposit_order_id}")
            if deposit.user_id != user_id:
                raise HTTPException(status_code=403, detail="deposit_order does not belong to the user")
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": str(user_id), "deposit_order_id": str(deposit_order_id)},
        )
    return None


@payfi_mcp.tool(
    name="mcp_capability_status",
    description="Check whether a user is eligible to use PayFi Box MCP settlement tools. Use this before calling payment tools.",
)
def mcp_capability_status(user_id: str) -> dict:
    uid, parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if parse_error is not None:
        return parse_error
    try:
        with get_db_session() as session:
            _require_user(session=session, user_id=uid)
            verification = _load_balance_kyc(session=session, user_id=uid)
            verified = verification is not None and verification.status.lower() == "verified"
            return {
                "status": "ok" if verified else "blocked_kyc_required",
                "message": (
                    "MCP settlement tools are enabled for this user."
                    if verified
                    else "Identity verification is required before MCP settlement tools can be used."
                ),
                "next_action": "none" if verified else "start_kyc",
                "summary": {
                    "user_id": user_id,
                    "kyc_status": verification.status if verification is not None else "not_started",
                    "mcp_access": "enabled" if verified else "kyc_required",
                },
                "technical_details": {
                    "subject_type": "user",
                    "subject_id": user_id,
                    "kyc_verification_id": str(verification.id) if verification is not None else None,
                    "available_tools": MCP_VERIFIED_TOOLS if verified else MCP_PRE_KYC_TOOLS,
                },
            }
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": user_id},
        )


@payfi_mcp.tool(
    name="start_user_kyc",
    description="Start or resume user identity verification for PayFi Box MCP access.",
)
def start_user_kyc(user_id: str, locale: str | None = None, force_new: bool = False) -> dict:
    uid, parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if parse_error is not None:
        return parse_error
    try:
        with get_db_session() as session:
            response = start_kyc_verification(
                session=session,
                request=KycStartRequest(
                    subject_type="user",
                    subject_id=uid,
                    locale=locale,
                    force_new=force_new,
                ),
            )
            payload = _json(response)
            payload["summary"] = {
                "user_id": user_id,
                "kyc_status": payload.get("verification", {}).get("status") if payload.get("verification") else None,
            }
            return payload
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": user_id},
        )


@payfi_mcp.tool(
    name="get_kyc_status",
    description="Fetch an existing KYC verification record by id.",
)
def get_kyc_status(kyc_verification_id: str) -> dict:
    kyc_id, parse_error = _parse_uuid_param(
        field_name="kyc_verification_id",
        raw_value=kyc_verification_id,
        summary={"kyc_verification_id": kyc_verification_id},
    )
    if parse_error is not None:
        return parse_error
    try:
        with get_db_session() as session:
            response = get_kyc_verification(session=session, kyc_id=kyc_id)
            return _json(response)
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"kyc_verification_id": kyc_verification_id},
        )


@payfi_mcp.tool(
    name="get_balance",
    description="Get a user's platform stablecoin balance. Requires verified KYC.",
)
def get_balance(user_id: str, currency: str = "USDT") -> dict:
    uid, parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if parse_error is not None:
        return parse_error
    blocked = _ensure_mcp_kyc(uid)
    if blocked is not None:
        return blocked
    try:
        with get_db_session() as session:
            response = get_balance_account(session=session, user_id=uid, currency=currency)
            payload = _json(response)
            return {
                "status": "ok",
                "message": "Balance loaded.",
                "next_action": "preview_payment_from_balance",
                "summary": payload["account"],
                "technical_details": payload,
            }
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": user_id, "currency": currency},
        )


@payfi_mcp.tool(
    name="get_balance_ledger",
    description="Get recent platform balance ledger entries for a user. Requires verified KYC.",
)
def get_balance_ledger_tool(user_id: str, currency: str = "USDT", limit: int = 10) -> dict:
    uid, parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if parse_error is not None:
        return parse_error
    blocked = _ensure_mcp_kyc(uid)
    if blocked is not None:
        return blocked
    try:
        with get_db_session() as session:
            response = get_balance_ledger(session=session, user_id=uid, currency=currency, limit=limit)
            payload = _json(response)
            return {
                "status": "ok",
                "message": "Balance ledger loaded.",
                "next_action": "none",
                "summary": {
                    "currency": payload["account"]["currency"],
                    "available_balance": payload["account"]["available_balance"],
                    "locked_balance": payload["account"]["locked_balance"],
                    "items_returned": len(payload["items"]),
                },
                "technical_details": payload,
            }
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": user_id, "currency": currency},
        )


@payfi_mcp.tool(
    name="payment_preview_from_balance",
    description="Preview a settlement funded by platform balance. Requires verified KYC.",
)
def payment_preview_from_balance(
    user_id: str,
    prompt: str,
    execution_mode: str = "operator",
    locale: str | None = None,
) -> dict:
    uid, parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if parse_error is not None:
        return parse_error
    blocked = _ensure_mcp_kyc(uid)
    if blocked is not None:
        return blocked
    try:
        with get_db_session() as session:
            response = preview_payment_from_balance(
                session=session,
                request=BalancePaymentPreviewRequest(
                    user_id=uid,
                    prompt=prompt,
                    execution_mode=execution_mode,
                    locale=locale,
                ),
            )
            payload = _json(response)
            return {
                "status": payload["status"],
                "message": payload["message"],
                "next_action": payload["next_action"],
                "summary": {
                    "recipient": payload.get("preview_summary", {}).get("recipient"),
                    "amount": payload.get("preview_summary", {}).get("amount"),
                    "currency": payload.get("preview_summary", {}).get("currency"),
                    "risk_level": payload.get("preview_summary", {}).get("risk_level"),
                    "estimated_fee": payload.get("preview_summary", {}).get("estimated_fee"),
                    "net_transfer": payload.get("preview_summary", {}).get("net_transfer"),
                    "sufficient_balance": payload.get("balance_check", {}).get("sufficient"),
                },
                "technical_details": payload,
            }
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": user_id, "prompt": prompt},
        )


@payfi_mcp.tool(
    name="payment_confirm_from_balance",
    description="Confirm a previously previewed balance-funded settlement. Requires verified KYC and a current command_id.",
)
def payment_confirm_from_balance(
    user_id: str,
    command_id: str,
    execution_mode: str = "operator",
    idempotency_key: str | None = None,
    locale: str | None = None,
    note: str | None = None,
) -> dict:
    uid, user_parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if user_parse_error is not None:
        return user_parse_error
    cmd_id, command_parse_error = _parse_uuid_param(
        field_name="command_id",
        raw_value=command_id,
        summary={"user_id": user_id, "command_id": command_id},
    )
    if command_parse_error is not None:
        return command_parse_error
    blocked = _ensure_mcp_kyc(uid)
    if blocked is not None:
        return blocked
    try:
        with get_db_session() as session:
            response = confirm_payment_from_balance(
                session=session,
                request=BalancePaymentConfirmRequest(
                    user_id=uid,
                    command_id=cmd_id,
                    execution_mode=execution_mode,
                    idempotency_key=idempotency_key,
                    locale=locale,
                    note=note,
                ),
            )
            payload = _json(response)
            return {
                "status": payload["status"],
                "message": payload["message"],
                "next_action": payload["next_action"],
                "summary": {
                    "payment_order_id": payload.get("payment_order_id"),
                    "execution_batch_id": payload.get("execution_batch_id"),
                    "payment_status": payload.get("payment_status"),
                    "execution_status": payload.get("execution_status"),
                    "execution_mode": payload.get("execution_mode"),
                    "tx_hash": (payload.get("execution") or {}).get("tx_hash"),
                    "explorer_url": (payload.get("execution") or {}).get("explorer_url"),
                },
                "technical_details": payload,
            }
    except HTTPException as exc:
        return {
            "status": "validation_error",
            "message": str(exc.detail),
            "next_action": "none",
            "summary": {"user_id": user_id, "command_id": command_id},
            "technical_details": {"http_status": exc.status_code, "detail": exc.detail},
        }


@payfi_mcp.tool(
    name="create_balance_deposit",
    description="Create a fiat deposit order that will credit a user's platform stablecoin balance after confirmed fiat receipt. Requires verified KYC.",
)
def create_balance_deposit(
    user_id: str,
    source_currency: str,
    source_amount: float,
    target_currency: str = "USDT",
    reference: str | None = None,
) -> dict:
    uid, parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if parse_error is not None:
        return parse_error
    blocked = _ensure_mcp_kyc(uid)
    if blocked is not None:
        return blocked
    try:
        with get_db_session() as session:
            response = create_fiat_deposit(
                session=session,
                request=CreateFiatDepositRequest(
                    user_id=uid,
                    source_currency=source_currency,
                    source_amount=source_amount,
                    target_currency=target_currency,
                    reference=reference,
                ),
            )
            payload = _json(response)
            deposit = payload["deposit_order"]
            return {
                "status": payload["status"],
                "message": payload["message"],
                "next_action": payload["next_action"],
                "summary": {
                    "deposit_order_id": deposit["id"],
                    "source_currency": deposit["source_currency"],
                    "source_amount": deposit["source_amount"],
                    "target_currency": deposit["target_currency"],
                    "target_amount": deposit["target_amount"],
                    "fee_amount": deposit["fee_amount"],
                    "status": deposit["status"],
                },
                "technical_details": payload,
            }
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={
                "user_id": user_id,
                "source_currency": source_currency,
                "source_amount": source_amount,
                "target_currency": target_currency,
            },
        )


@payfi_mcp.tool(
    name="start_balance_deposit_checkout",
    description="Start or resume Stripe checkout for a balance deposit order. Requires verified KYC and ownership of the deposit order.",
)
def start_balance_deposit_checkout(
    user_id: str,
    deposit_order_id: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
    locale: str | None = None,
) -> dict:
    uid, user_parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if user_parse_error is not None:
        return user_parse_error
    blocked = _ensure_mcp_kyc(uid)
    if blocked is not None:
        return blocked
    deposit_id, deposit_parse_error = _parse_uuid_param(
        field_name="deposit_order_id",
        raw_value=deposit_order_id,
        summary={"user_id": user_id, "deposit_order_id": deposit_order_id},
    )
    if deposit_parse_error is not None:
        return deposit_parse_error
    ownership_error = _ensure_deposit_belongs_to_user(user_id=uid, deposit_order_id=deposit_id)
    if ownership_error is not None:
        return ownership_error
    try:
        with get_db_session() as session:
            response = start_deposit_stripe_payment(
                session=session,
                deposit_order_id=deposit_id,
                request=StartDepositStripePaymentRequest(
                    success_url=success_url,
                    cancel_url=cancel_url,
                    locale=locale,
                ),
            )
            payload = _json(response)
            deposit = payload["deposit_order"]
            checkout = payload.get("checkout") or {}
            return {
                "status": payload["status"],
                "message": payload["message"],
                "next_action": payload["next_action"],
                "summary": {
                    "deposit_order_id": deposit["id"],
                    "status": deposit["status"],
                    "channel_status": deposit.get("channel_status"),
                    "checkout_session_id": checkout.get("checkout_session_id"),
                    "checkout_url": checkout.get("checkout_url"),
                    "payment_intent_id": checkout.get("payment_intent_id"),
                },
                "technical_details": payload,
            }
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": user_id, "deposit_order_id": deposit_order_id},
        )


@payfi_mcp.tool(
    name="sync_balance_deposit_status",
    description="Sync Stripe payment status for a balance deposit and return the latest credited-balance view. Requires verified KYC and ownership of the deposit order.",
)
def sync_balance_deposit_status(user_id: str, deposit_order_id: str) -> dict:
    uid, user_parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if user_parse_error is not None:
        return user_parse_error
    blocked = _ensure_mcp_kyc(uid)
    if blocked is not None:
        return blocked
    deposit_id, deposit_parse_error = _parse_uuid_param(
        field_name="deposit_order_id",
        raw_value=deposit_order_id,
        summary={"user_id": user_id, "deposit_order_id": deposit_order_id},
    )
    if deposit_parse_error is not None:
        return deposit_parse_error
    ownership_error = _ensure_deposit_belongs_to_user(user_id=uid, deposit_order_id=deposit_id)
    if ownership_error is not None:
        return ownership_error
    try:
        with get_db_session() as session:
            response = sync_deposit_stripe_payment_status(session=session, deposit_order_id=deposit_id)
            payload = _json(response)
            deposit = payload["deposit_order"]
            account = payload.get("account") or {}
            return {
                "status": "ok",
                "message": "Deposit status synchronized.",
                "next_action": deposit.get("next_action") or "none",
                "summary": {
                    "deposit_order_id": deposit["id"],
                    "status": deposit["status"],
                    "channel_status": deposit.get("channel_status"),
                    "target_currency": deposit["target_currency"],
                    "target_amount": deposit["target_amount"],
                    "available_balance": account.get("available_balance"),
                    "locked_balance": account.get("locked_balance"),
                },
                "technical_details": payload,
            }
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": user_id, "deposit_order_id": deposit_order_id},
        )


@payfi_mcp.tool(
    name="get_balance_deposit_detail",
    description="Get the latest detail for a balance deposit order, including any credited balance account view. Requires verified KYC and ownership of the deposit order.",
)
def get_balance_deposit_detail_tool(user_id: str, deposit_order_id: str) -> dict:
    uid, user_parse_error = _parse_uuid_param(field_name="user_id", raw_value=user_id)
    if user_parse_error is not None:
        return user_parse_error
    blocked = _ensure_mcp_kyc(uid)
    if blocked is not None:
        return blocked
    deposit_id, deposit_parse_error = _parse_uuid_param(
        field_name="deposit_order_id",
        raw_value=deposit_order_id,
        summary={"user_id": user_id, "deposit_order_id": deposit_order_id},
    )
    if deposit_parse_error is not None:
        return deposit_parse_error
    ownership_error = _ensure_deposit_belongs_to_user(user_id=uid, deposit_order_id=deposit_id)
    if ownership_error is not None:
        return ownership_error
    try:
        with get_db_session() as session:
            response = get_deposit_detail(session=session, deposit_order_id=deposit_id)
            payload = _json(response)
            deposit = payload["deposit_order"]
            account = payload.get("account") or {}
            return {
                "status": "ok",
                "message": "Deposit detail loaded.",
                "next_action": deposit.get("next_action") or "none",
                "summary": {
                    "deposit_order_id": deposit["id"],
                    "status": deposit["status"],
                    "channel_status": deposit.get("channel_status"),
                    "source_currency": deposit["source_currency"],
                    "source_amount": deposit["source_amount"],
                    "target_currency": deposit["target_currency"],
                    "target_amount": deposit["target_amount"],
                    "available_balance": account.get("available_balance"),
                },
                "technical_details": payload,
            }
    except HTTPException as exc:
        return _http_error_payload(
            message=str(exc.detail),
            status_code=exc.status_code,
            detail=exc.detail,
            summary={"user_id": user_id, "deposit_order_id": deposit_order_id},
        )
