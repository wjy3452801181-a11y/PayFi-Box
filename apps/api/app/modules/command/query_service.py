from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Beneficiary, CommandExecution, PaymentOrder
from app.modules.audit.service import build_audit_timeline_items
from app.modules.command.query_schemas import (
    CommandAuditSummary,
    CommandCoreDetails,
    CommandDetailResponse,
    CommandListFilters,
    CommandListItem,
    CommandListPreviewSummary,
    CommandListResponse,
    CommandListSort,
    CommandParsedDetails,
    CommandQuoteSummary,
    CommandRiskSummary,
    LinkedBeneficiarySummary,
    LinkedPaymentSummary,
)
from app.modules.command.quote import generate_mock_quote
from app.modules.command.risk import evaluate_payment_risk

SortBy = Literal["created_at", "final_status"]
SortOrder = Literal["asc", "desc"]


def list_commands(
    session: Session,
    *,
    intent: str | None,
    final_status: str | None,
    user_id: UUID | None,
    session_id: UUID | None,
    limit: int,
    sort_by: SortBy,
    sort_order: SortOrder,
) -> CommandListResponse:
    stmt = select(CommandExecution)
    if final_status:
        stmt = stmt.where(CommandExecution.final_status == final_status)
    if user_id:
        stmt = stmt.where(CommandExecution.user_id == user_id)
    if session_id:
        stmt = stmt.where(CommandExecution.session_id == session_id)

    sort_column = {
        "created_at": CommandExecution.created_at,
        "final_status": CommandExecution.final_status,
    }[sort_by]
    if sort_order == "asc":
        stmt = stmt.order_by(sort_column.asc(), CommandExecution.id.asc())
    else:
        stmt = stmt.order_by(sort_column.desc(), CommandExecution.id.desc())

    commands = session.execute(stmt).scalars().all()
    if intent:
        commands = [item for item in commands if _extract_intent(item.parsed_intent_json) == intent]

    total = len(commands)
    commands = commands[:limit]
    payment_map = _load_linked_payments_map(session=session, command_ids=[item.id for item in commands])

    items: list[CommandListItem] = []
    for command in commands:
        parsed = command.parsed_intent_json if isinstance(command.parsed_intent_json, dict) else {}
        fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {}
        linked = payment_map.get(command.id, [])
        linked_primary = linked[0] if linked else None
        risk_summary, _ = _derive_risk_and_quote(parsed=parsed)
        items.append(
            CommandListItem(
                command_id=command.id,
                created_at=command.created_at,
                user_id=command.user_id,
                session_id=command.session_id,
                raw_text=command.raw_text,
                intent=_extract_intent(parsed),
                confidence=_extract_confidence(parsed),
                final_status=command.final_status,
                trace_id=command.trace_id,
                preview_summary=_build_preview_summary(fields=fields, parsed=parsed),
                resulted_in_payment=bool(linked),
                linked_payment_order_id=linked_primary.id if linked_primary else None,
                linked_payment_order_count=len(linked),
                risk_summary=risk_summary,
                next_action=_extract_next_action(parsed),
            )
        )

    return CommandListResponse(
        total=total,
        limit=limit,
        filters=CommandListFilters(
            intent=intent,
            final_status=final_status,
            user_id=user_id,
            session_id=session_id,
        ),
        sort=CommandListSort(sort_by=sort_by, sort_order=sort_order),
        items=items,
    )


def get_command_detail(session: Session, command_id: UUID) -> CommandDetailResponse:
    command = session.get(CommandExecution, command_id)
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"command not found: {command_id}",
        )

    parsed = command.parsed_intent_json if isinstance(command.parsed_intent_json, dict) else {}
    tool_calls = command.tool_calls_json if isinstance(command.tool_calls_json, list) else None
    linked_payments = session.execute(
        select(PaymentOrder)
        .where(PaymentOrder.source_command_id == command.id)
        .order_by(PaymentOrder.created_at.desc())
    ).scalars().all()
    linked_payment = linked_payments[0] if linked_payments else None

    linked_beneficiary = _derive_linked_beneficiary(
        session=session,
        parsed=parsed,
        linked_payment=linked_payment,
    )
    risk_summary, quote_summary = _derive_risk_and_quote(parsed=parsed)
    selected_trace_id, audit_logs = _load_command_audit_logs(session=session, command=command)
    audit_items = build_audit_timeline_items(audit_logs)

    return CommandDetailResponse(
        command=CommandCoreDetails(
            command_id=command.id,
            created_at=command.created_at,
            updated_at=command.updated_at,
            user_id=command.user_id,
            session_id=command.session_id,
            raw_text=command.raw_text,
            intent=_extract_intent(parsed),
            confidence=_extract_confidence(parsed),
            final_status=command.final_status,
            trace_id=command.trace_id,
        ),
        parsed=CommandParsedDetails(
            parsed_intent_json=command.parsed_intent_json,
            tool_calls_json=tool_calls,
        ),
        risk=risk_summary,
        quote=quote_summary,
        linked_payment=(
            LinkedPaymentSummary(
                payment_order_id=linked_payment.id,
                status=linked_payment.status,
                amount=_to_float(linked_payment.amount),
                currency=linked_payment.currency,
                risk_level=linked_payment.risk_level,
                reference=linked_payment.reference,
                created_at=linked_payment.created_at,
            )
            if linked_payment
            else None
        ),
        linked_beneficiary=linked_beneficiary,
        audit=CommandAuditSummary(
            trace_id=selected_trace_id,
            count=len(audit_items),
            items=audit_items,
        ),
    )


def _load_linked_payments_map(
    *,
    session: Session,
    command_ids: list[UUID],
) -> dict[UUID, list[PaymentOrder]]:
    if not command_ids:
        return {}
    rows = session.execute(
        select(PaymentOrder)
        .where(PaymentOrder.source_command_id.in_(command_ids))
        .order_by(PaymentOrder.created_at.desc())
    ).scalars().all()
    result: dict[UUID, list[PaymentOrder]] = {item: [] for item in command_ids}
    for row in rows:
        if row.source_command_id is None:
            continue
        result.setdefault(row.source_command_id, []).append(row)
    return result


def _load_command_audit_logs(
    *,
    session: Session,
    command: CommandExecution,
) -> tuple[str | None, list[AuditLog]]:
    trace_candidates = [f"{command.trace_id}-confirm", command.trace_id]
    for trace_id in trace_candidates:
        logs = session.execute(
            select(AuditLog)
            .where(AuditLog.trace_id == trace_id)
            .order_by(AuditLog.created_at.asc())
        ).scalars().all()
        if logs:
            return trace_id, logs
    return trace_candidates[0], []


def _derive_linked_beneficiary(
    *,
    session: Session,
    parsed: dict[str, Any],
    linked_payment: PaymentOrder | None,
) -> LinkedBeneficiarySummary | None:
    fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {}
    beneficiary_data = fields.get("beneficiary") if isinstance(fields.get("beneficiary"), dict) else None

    if beneficiary_data and beneficiary_data.get("id"):
        beneficiary = session.get(Beneficiary, beneficiary_data["id"])
        if beneficiary:
            return LinkedBeneficiarySummary(
                beneficiary_id=beneficiary.id,
                name=beneficiary.name,
                country=beneficiary.country,
                risk_level=beneficiary.risk_level,
                is_blacklisted=beneficiary.is_blacklisted,
                resolved=True,
            )

    if beneficiary_data:
        return LinkedBeneficiarySummary(
            beneficiary_id=None,
            name=beneficiary_data.get("name"),
            country=beneficiary_data.get("country"),
            risk_level=beneficiary_data.get("risk_level"),
            is_blacklisted=beneficiary_data.get("is_blacklisted"),
            resolved=bool(beneficiary_data.get("resolved")),
        )

    if linked_payment:
        beneficiary = session.get(Beneficiary, linked_payment.beneficiary_id)
        if beneficiary:
            return LinkedBeneficiarySummary(
                beneficiary_id=beneficiary.id,
                name=beneficiary.name,
                country=beneficiary.country,
                risk_level=beneficiary.risk_level,
                is_blacklisted=beneficiary.is_blacklisted,
                resolved=True,
            )
    return None


def _derive_risk_and_quote(parsed: dict[str, Any]) -> tuple[CommandRiskSummary | None, CommandQuoteSummary | None]:
    fields = _extract_payment_like_fields(parsed)
    if not fields:
        return None, None

    missing_fields = parsed.get("missing_fields")
    if isinstance(missing_fields, list) and missing_fields:
        return None, None

    amount = fields.get("amount")
    currency = fields.get("currency")
    if amount is None or currency is None:
        return None, None

    risk = evaluate_payment_risk(fields)
    quote = generate_mock_quote(fields, risk["decision"])
    return (
        CommandRiskSummary(
            decision=risk["decision"],
            risk_level=risk["risk_level"],
            reason_codes=risk["reason_codes"],
            user_message=risk["user_message"],
        ),
        CommandQuoteSummary(**quote),
    )


def _build_preview_summary(*, fields: dict[str, Any], parsed: dict[str, Any]) -> CommandListPreviewSummary | None:
    if not fields:
        fields = _extract_payment_like_fields(parsed) or {}
    if not fields and not parsed.get("missing_fields"):
        return None
    return CommandListPreviewSummary(
        recipient=fields.get("recipient"),
        amount=_safe_float(fields.get("amount")),
        currency=fields.get("currency"),
        reference=fields.get("reference"),
        missing_fields=parsed.get("missing_fields", []) if isinstance(parsed.get("missing_fields"), list) else [],
    )


def _extract_intent(parsed: dict[str, Any] | None) -> str | None:
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("intent")
    return str(value) if value is not None else None


def _extract_confidence(parsed: dict[str, Any] | None) -> float | None:
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("confidence")
    return _safe_float(value)


def _extract_next_action(parsed: dict[str, Any] | None) -> str | None:
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("next_action")
    return str(value) if value is not None else None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_float(value: Decimal) -> float:
    return float(value)


def _extract_payment_like_fields(parsed: dict[str, Any]) -> dict[str, Any] | None:
    fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else None
    if fields:
        return fields

    legacy_amount = parsed.get("amount")
    legacy_currency = parsed.get("currency")
    legacy_beneficiary = parsed.get("beneficiary")
    if legacy_amount is None and legacy_currency is None and legacy_beneficiary is None:
        return None

    beneficiary_obj = None
    if legacy_beneficiary is not None:
        beneficiary_obj = {
            "id": None,
            "name": str(legacy_beneficiary),
            "country": None,
            "risk_level": None,
            "is_blacklisted": None,
            "resolved": False,
        }

    return {
        "recipient": str(legacy_beneficiary) if legacy_beneficiary else None,
        "beneficiary": beneficiary_obj,
        "amount": _safe_float(legacy_amount),
        "currency": str(legacy_currency).upper() if legacy_currency else None,
        "split_count": parsed.get("splits"),
        "reference": parsed.get("reference"),
    }
