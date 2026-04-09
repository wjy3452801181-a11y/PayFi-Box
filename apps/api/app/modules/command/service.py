from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Beneficiary,
    CommandExecution,
    CommandExecutionStatus,
    ConversationSession,
    PaymentOrder,
    RiskLevel,
    SessionStatus,
    User,
)
from app.modules.command.parser import classify_intent, parse_command
from app.modules.command.quote import generate_mock_quote
from app.modules.command.risk import evaluate_payment_risk
from app.modules.command.schemas import CommandRequest, CommandResponse


def handle_command(session: Session, request: CommandRequest) -> CommandResponse:
    user = session.get(User, request.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user_id not found: {request.user_id}",
        )

    conv_session = _resolve_or_create_session(session=session, request=request)
    beneficiaries = load_beneficiaries_for_lookup(session=session, actor_user=user)

    intent = classify_intent(request.text)
    parsed = parse_command(text=request.text, intent=intent, beneficiaries=beneficiaries)

    preview_execution_mode = _normalize_preview_execution_mode(request.execution_mode)
    preview_payload = build_command_preview_payload(
        session=session,
        actor_user=user,
        intent=intent,
        parsed=parsed,
        execution_mode=preview_execution_mode,
    )

    command_status = _map_command_status(intent=intent, parsed=parsed)
    command_id = uuid.uuid4()
    trace_id = f"trace-cmd-{command_id.hex[:12]}"
    parsed_payload = {
        "intent": intent,
        "confidence": parsed["confidence"],
        "fields": _to_json_safe(parsed["fields"]),
        "missing_fields": parsed["missing_fields"],
    }

    command_execution = CommandExecution(
        id=command_id,
        session_id=conv_session.id,
        user_id=request.user_id,
        raw_text=request.text,
        parsed_intent_json=parsed_payload,
        tool_calls_json=preview_payload["tool_calls"],
        final_status=command_status,
        trace_id=trace_id,
    )
    session.add(command_execution)
    session.commit()

    return CommandResponse(
        status=parsed.get("status", "ok"),
        command_id=command_id,
        session_id=conv_session.id,
        intent=intent,
        confidence=round(parsed["confidence"], 2),
        preview=preview_payload["preview"],
        missing_fields=parsed.get("missing_fields", []),
        follow_up_question=parsed.get("follow_up_question"),
        risk=preview_payload["risk"],
        quote=preview_payload["quote"],
        execution_mode=preview_execution_mode,
        next_action=preview_payload["next_action"],
        mode_specific_cta=preview_payload.get("mode_specific_cta"),
        preview_summary=preview_payload.get("preview_summary"),
        technical_details=preview_payload.get("technical_details"),
        message=preview_payload["message"],
    )


def build_command_preview_payload(
    *,
    session: Session,
    actor_user: User,
    intent: str,
    parsed: dict[str, Any],
    execution_mode: str,
) -> dict[str, Any]:
    risk_preview: dict[str, Any] | None = None
    quote_preview: dict[str, Any] | None = None
    preview: dict[str, Any]
    next_action: str
    message: str
    tool_calls: list[dict[str, Any]] = [{"tool": "rule_parser", "status": "ok"}]

    if intent == "create_payment":
        fields = parsed["fields"]
        if not parsed["missing_fields"]:
            risk_preview = evaluate_payment_risk(fields)
            quote_preview = generate_mock_quote(fields, risk_preview["decision"])
            tool_calls.append({"tool": "mock_risk", "status": "ok"})
            tool_calls.append({"tool": "mock_quote", "status": "ok"})
            next_action = _resolve_mode_next_action(execution_mode)
            message = "付款命令已解析，预览可进入确认流程。 (Payment command parsed; preview is ready for confirmation flow.)"
        else:
            next_action = "clarify_missing_fields"
            message = "缺少必要信息，请先补充再生成完整预览。 (More information is needed before finalizing the preview.)"

        preview_beneficiary = fields.get("beneficiary")
        preview_extracted = {
            "recipient": fields.get("recipient"),
            "amount": fields.get("amount"),
            "currency": fields.get("currency"),
            "split_count": fields.get("split_count"),
            "reference": fields.get("reference"),
            "eta_preference": fields.get("eta_preference"),
            "fee_preference": fields.get("fee_preference"),
        }
        preview = {
            "type": "payment_preview",
            "extracted": preview_extracted,
            "beneficiary": preview_beneficiary,
        }
    elif intent == "query_payments":
        filters = parsed["fields"]
        sample = _sample_payments(session=session, actor_user=actor_user, filters=filters)
        preview = {
            "type": "payment_query_preview",
            "filters": filters,
            "result_count": sample["count"],
            "sample": sample["items"],
        }
        next_action = "show_query_preview"
        message = "已解析查询条件，并生成轻量预览结果。 (Query filters parsed; lightweight preview generated.)"
        tool_calls.append({"tool": "payment_query_preview", "status": "ok"})
    elif intent == "generate_report":
        report_preview = _build_report_preview(session=session, actor_user=actor_user, fields=parsed["fields"])
        preview = {
            "type": "report_preview",
            "request": parsed["fields"],
            "summary": report_preview,
        }
        next_action = "prepare_report_generation"
        message = "报表请求已解析，摘要预览已准备好。 (Report request parsed; summary preview is ready.)"
        tool_calls.append({"tool": "report_preview", "status": "ok"})
    else:
        preview = {
            "type": "unknown_preview",
            "extracted": {},
        }
        next_action = "ask_follow_up"
        message = "命令意图不清晰，请补充目标操作。 (Command intent is unclear; please clarify the action.)"
        tool_calls.append({"tool": "rule_parser", "status": "low_confidence"})

    return {
        "risk": risk_preview,
        "quote": quote_preview,
        "preview": preview,
        "next_action": next_action,
        "mode_specific_cta": _resolve_mode_cta(execution_mode) if intent == "create_payment" else None,
        "preview_summary": _build_preview_summary(
            fields=parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {},
            risk_preview=risk_preview,
            quote_preview=quote_preview,
        )
        if intent == "create_payment"
        else None,
        "technical_details": {
            "intent": intent,
            "missing_fields": parsed.get("missing_fields", []),
            "execution_mode": execution_mode,
            "tool_calls": tool_calls,
        },
        "message": message,
        "tool_calls": tool_calls,
    }


def _normalize_preview_execution_mode(execution_mode: str | None) -> str:
    normalized = (execution_mode or "operator").strip().lower()
    if normalized in {"operator", "user_wallet", "safe"}:
        return normalized
    return "operator"


def _resolve_mode_next_action(execution_mode: str) -> str:
    if execution_mode == "user_wallet":
        return "generate_unsigned_tx"
    if execution_mode == "safe":
        return "generate_safe_proposal"
    return "confirm_now"


def _resolve_mode_cta(execution_mode: str) -> str:
    if execution_mode == "user_wallet":
        return "Generate unsigned transaction(s)"
    if execution_mode == "safe":
        return "Generate Safe proposal"
    return "Confirm & Submit"


def _build_preview_summary(
    *,
    fields: dict[str, Any],
    risk_preview: dict[str, Any] | None,
    quote_preview: dict[str, Any] | None,
) -> dict[str, Any]:
    amount = fields.get("amount")
    amount_value = None
    if amount is not None:
        try:
            amount_value = float(amount)
        except Exception:
            amount_value = None
    estimated_fee = quote_preview.get("estimated_fee") if isinstance(quote_preview, dict) else None
    net_transfer = (
        quote_preview.get("net_transfer_amount")
        if isinstance(quote_preview, dict)
        else None
    )
    return {
        "recipient": fields.get("recipient"),
        "amount": amount_value,
        "currency": fields.get("currency"),
        "risk_level": risk_preview.get("risk_level") if isinstance(risk_preview, dict) else None,
        "estimated_fee": float(estimated_fee) if estimated_fee is not None else None,
        "net_transfer": float(net_transfer) if net_transfer is not None else None,
    }


def _resolve_or_create_session(session: Session, request: CommandRequest) -> ConversationSession:
    if request.session_id:
        existing = session.get(ConversationSession, request.session_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session_id not found: {request.session_id}",
            )
        if existing.user_id != request.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_id does not belong to user_id",
            )
        return existing

    new_session = ConversationSession(
        id=uuid.uuid4(),
        user_id=request.user_id,
        channel=request.channel or "web",
        status=SessionStatus.ACTIVE.value,
    )
    session.add(new_session)
    session.flush()
    return new_session


def _beneficiary_visibility_clause(actor_user: User):
    if actor_user.organization_id is None:
        return Beneficiary.organization_id.is_(None)
    return or_(
        Beneficiary.organization_id == actor_user.organization_id,
        Beneficiary.organization_id.is_(None),
    )


def load_beneficiaries_for_lookup(session: Session, *, actor_user: User) -> list[dict[str, Any]]:
    stmt = select(
        Beneficiary.id,
        Beneficiary.name,
        Beneficiary.country,
        Beneficiary.risk_level,
        Beneficiary.is_blacklisted,
    ).where(_beneficiary_visibility_clause(actor_user))
    rows = session.execute(stmt).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "country": row.country,
            "risk_level": row.risk_level,
            "is_blacklisted": row.is_blacklisted,
        }
        for row in rows
    ]


def _sample_payments(session: Session, *, actor_user: User, filters: dict[str, Any]) -> dict[str, Any]:
    conditions = []

    recipient = filters.get("recipient")
    if recipient:
        subquery = select(Beneficiary.id).where(
            Beneficiary.name.ilike(f"%{recipient}%"),
            _beneficiary_visibility_clause(actor_user),
        )
        conditions.append(PaymentOrder.beneficiary_id.in_(subquery))

    status_value = filters.get("status")
    if status_value:
        conditions.append(PaymentOrder.status == status_value)

    query = select(PaymentOrder).where(PaymentOrder.user_id == actor_user.id)
    if conditions:
        query = query.where(and_(*conditions))

    count_stmt = select(func.count()).select_from(query.subquery())
    total = session.execute(count_stmt).scalar_one()

    rows = session.execute(query.order_by(PaymentOrder.created_at.desc()).limit(5)).scalars().all()
    items = [
        {
            "id": str(row.id),
            "reference": row.reference,
            "amount": float(row.amount),
            "currency": row.currency,
            "status": row.status,
            "risk_level": row.risk_level,
        }
        for row in rows
    ]
    return {"count": int(total), "items": items}


def _build_report_preview(session: Session, *, actor_user: User, fields: dict[str, Any]) -> dict[str, Any]:
    total_orders = session.execute(
        select(func.count()).select_from(PaymentOrder).where(PaymentOrder.user_id == actor_user.id)
    ).scalar_one()
    high_risk_orders = session.execute(
        select(func.count())
        .select_from(PaymentOrder)
        .where(
            PaymentOrder.user_id == actor_user.id,
            PaymentOrder.risk_level == RiskLevel.HIGH.value,
        )
    ).scalar_one()
    cross_border_orders = session.execute(
        select(func.count())
        .select_from(PaymentOrder)
        .where(
            PaymentOrder.user_id == actor_user.id,
            PaymentOrder.currency.in_(("USD", "EUR", "USDT", "USDC")),
        )
    ).scalar_one()

    return {
        "time_range": fields.get("time_range"),
        "group_by": fields.get("group_by"),
        "highlight_risky": fields.get("highlight_risky"),
        "cross_border_only": fields.get("cross_border_only"),
        "totals": {
            "payment_orders": int(total_orders),
            "high_risk_payment_orders": int(high_risk_orders),
            "cross_border_payment_orders": int(cross_border_orders),
        },
    }


def _map_command_status(intent: str, parsed: dict[str, Any]) -> str:
    if intent == "unknown":
        return CommandExecutionStatus.FAILED.value
    if intent == "create_payment" and parsed.get("missing_fields"):
        return CommandExecutionStatus.PARSED.value
    if intent == "create_payment":
        return CommandExecutionStatus.READY.value
    return CommandExecutionStatus.COMPLETED.value


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    return value
    amount_value = None
    if amount is not None:
        try:
            amount_value = float(amount)
        except Exception:
            amount_value = None
