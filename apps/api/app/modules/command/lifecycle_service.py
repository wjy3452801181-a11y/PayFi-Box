from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, CommandExecution, PaymentOrder, PaymentSplit
from app.modules.command.lifecycle_schemas import (
    CommandReplayResponse,
    CommandTimelineItem,
    CommandTimelineResponse,
)
from app.modules.command.parser import classify_intent, parse_command
from app.modules.command.service import build_command_preview_payload, load_beneficiaries_for_lookup


def get_command_timeline(session: Session, command_id: UUID) -> CommandTimelineResponse:
    command = session.get(CommandExecution, command_id)
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"command not found: {command_id}",
        )

    parsed = command.parsed_intent_json if isinstance(command.parsed_intent_json, dict) else {}
    trace_candidates = [f"{command.trace_id}-confirm", command.trace_id]
    audit_logs = session.execute(
        select(AuditLog)
        .where(AuditLog.trace_id.in_(trace_candidates))
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    ).scalars().all()

    payments = session.execute(
        select(PaymentOrder)
        .where(PaymentOrder.source_command_id == command.id)
        .order_by(PaymentOrder.created_at.asc(), PaymentOrder.id.asc())
    ).scalars().all()
    payment_ids = [item.id for item in payments]
    splits = session.execute(
        select(PaymentSplit)
        .where(PaymentSplit.payment_order_id.in_(payment_ids))
        .order_by(PaymentSplit.created_at.asc(), PaymentSplit.id.asc())
    ).scalars().all() if payment_ids else []

    events: list[tuple[datetime, int, CommandTimelineItem]] = []
    _append_event(
        events=events,
        event_time=command.created_at,
        order=10,
        title="命令已接收 (Command received)",
        action="command_received",
        entity_type="command_execution",
        entity_id=command.id,
        details={
            "raw_text": command.raw_text,
            "final_status": command.final_status,
            "trace_id": command.trace_id,
        },
    )

    _append_event(
        events=events,
        event_time=command.created_at,
        order=20,
        title="命令已解析 (Command parsed)",
        action="command_parsed",
        entity_type="command_execution",
        entity_id=command.id,
        details={
            "intent": parsed.get("intent"),
            "confidence": parsed.get("confidence"),
            "missing_fields": parsed.get("missing_fields", []),
        },
    )

    confirmation = parsed.get("confirmation") if isinstance(parsed.get("confirmation"), dict) else None
    has_confirmation_audit = any(
        log.entity_type == "command_execution"
        and log.action
        in {
            "confirm_accepted",
            "confirm_declined",
            "confirm_blocked",
            "confirm_rejected_non_payment",
            "confirm_rejected_incomplete",
        }
        for log in audit_logs
    )
    if confirmation and not has_confirmation_audit:
        _append_event(
            events=events,
            event_time=command.updated_at,
            order=30,
            title=_confirmation_title(str(confirmation.get("status") or "")),
            action="command_confirmation_snapshot",
            entity_type="command_execution",
            entity_id=command.id,
            details=confirmation,
        )

    payment_create_audit_ids = {
        log.entity_id for log in audit_logs if log.action == "create" and log.entity_type == "payment_order"
    }
    split_create_audit_ids = {
        log.entity_id for log in audit_logs if log.action == "create" and log.entity_type == "payment_split"
    }
    execution_audit_ids = {
        log.entity_id
        for log in audit_logs
        if log.action
        in {
            "mock_execute",
            "retry_mock_executed",
            "onchain_tx_confirmed",
            "onchain_tx_failed",
        }
        and log.entity_type in {"payment_order", "payment_split"}
    }

    for payment in payments:
        if payment.id not in payment_create_audit_ids:
            _append_event(
                events=events,
                event_time=payment.created_at,
                order=40,
                title="支付单已创建 (Payment order created)",
                action="payment_order_created_snapshot",
                entity_type="payment_order",
                entity_id=payment.id,
                details={
                    "status": payment.status,
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "reference": payment.reference,
                },
            )
        if payment.id not in execution_audit_ids and payment.status in {"executed", "failed"}:
            _append_event(
                events=events,
                event_time=payment.updated_at,
                order=45,
                title=(
                    "链上执行已完成 (Onchain execution completed)"
                    if payment.execution_mode == "onchain" and payment.status == "executed"
                    else "链上执行失败 (Onchain execution failed)"
                    if payment.execution_mode == "onchain" and payment.status == "failed"
                    else "模拟执行已完成 (Mock execution completed)"
                    if payment.status == "executed"
                    else "模拟执行失败 (Mock execution failed)"
                ),
                action="payment_execution_snapshot",
                entity_type="payment_order",
                entity_id=payment.id,
                details={"status": payment.status},
            )

    for split in splits:
        if split.id in split_create_audit_ids:
            continue
        _append_event(
            events=events,
            event_time=split.created_at,
            order=41,
            title="支付拆分已创建 (Payment split created)",
            action="payment_split_created_snapshot",
            entity_type="payment_split",
            entity_id=split.id,
            details={
                "payment_order_id": str(split.payment_order_id),
                "sequence": split.sequence,
                "amount": float(split.amount),
                "currency": split.currency,
                "status": split.status,
            },
        )

    for audit in audit_logs:
        _append_event(
            events=events,
            event_time=audit.created_at,
            order=50,
            title=_friendly_audit_title(audit),
            action=audit.action,
            entity_type=audit.entity_type,
            entity_id=audit.entity_id,
            details=_resolve_audit_details(audit),
        )

    events.sort(key=lambda item: (item[0], item[1], item[2].action))
    items = [item for _, _, item in events]
    selected_trace_id = f"{command.trace_id}-confirm" if any(log.trace_id.endswith("-confirm") for log in audit_logs) else command.trace_id
    return CommandTimelineResponse(
        command_id=command.id,
        trace_id=selected_trace_id,
        count=len(items),
        items=items,
    )


def replay_command(session: Session, command_id: UUID) -> CommandReplayResponse:
    command = session.get(CommandExecution, command_id)
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"command not found: {command_id}",
        )

    beneficiaries = load_beneficiaries_for_lookup(session=session)
    intent = classify_intent(command.raw_text)
    parsed = parse_command(text=command.raw_text, intent=intent, beneficiaries=beneficiaries)
    preview_payload = build_command_preview_payload(
        session=session,
        intent=intent,
        parsed=parsed,
        execution_mode="operator",
    )

    return CommandReplayResponse(
        mode="replay",
        source_command_id=command.id,
        replayed_at=datetime.now(timezone.utc),
        session_id=command.session_id,
        user_id=command.user_id,
        status=parsed.get("status", "ok"),
        intent=intent,
        confidence=round(parsed.get("confidence", 0.0), 2),
        preview=preview_payload["preview"],
        missing_fields=parsed.get("missing_fields", []),
        follow_up_question=parsed.get("follow_up_question"),
        risk=preview_payload["risk"],
        quote=preview_payload["quote"],
        next_action=preview_payload["next_action"],
        message=preview_payload["message"],
    )


def _append_event(
    *,
    events: list[tuple[datetime, int, CommandTimelineItem]],
    event_time: datetime,
    order: int,
    title: str,
    action: str,
    entity_type: str,
    entity_id: UUID,
    details: dict[str, Any] | None,
) -> None:
    events.append(
        (
            event_time,
            order,
            CommandTimelineItem(
                timestamp=event_time,
                title=title,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
            ),
        )
    )


def _confirmation_title(status_value: str) -> str:
    status_map = {
        "declined": "确认已拒绝 (Confirmation declined)",
        "blocked": "风控拦截 (Blocked by risk policy)",
        "confirmed": "确认已接受 (Confirmation accepted)",
        "executed": "确认并执行完成 (Confirmation executed)",
    }
    return status_map.get(status_value, "确认状态已更新 (Confirmation state updated)")


def _friendly_audit_title(log: AuditLog) -> str:
    mapping = {
        ("confirm_accepted", "command_execution"): "确认已接受 (Confirmation accepted)",
        ("confirm_declined", "command_execution"): "确认已拒绝 (Confirmation declined)",
        ("confirm_blocked", "command_execution"): "风控拦截 (Blocked by risk policy)",
        ("create", "payment_order"): "支付单已创建 (Payment order created)",
        ("create", "payment_split"): "支付拆分已创建 (Payment split created)",
        ("mock_execute", "payment_order"): "模拟执行已完成 (Mock execution completed)",
        ("onchain_tx_submitted", "payment_order"): "链上交易已提交 (Onchain transaction submitted)",
        ("onchain_tx_submitted", "payment_split"): "拆单链上交易已提交 (Split onchain transaction submitted)",
        ("onchain_tx_confirmed", "payment_order"): "链上交易已确认 (Onchain transaction confirmed)",
        ("onchain_tx_confirmed", "payment_split"): "拆单链上交易已确认 (Split onchain transaction confirmed)",
        ("onchain_event_emitted", "payment_order"): "链上事件已解析 (Onchain event decoded)",
        ("onchain_event_emitted", "payment_split"): "拆单链上事件已解析 (Split onchain event decoded)",
        ("onchain_tx_failed", "payment_order"): "链上交易失败 (Onchain transaction failed)",
        ("onchain_tx_failed", "payment_split"): "拆单链上交易失败 (Split onchain transaction failed)",
        ("execution_batch_planned", "payment_execution_batch"): "执行批次已规划 (Execution batch planned)",
        ("execution_batch_started", "payment_execution_batch"): "执行批次已开始 (Execution batch started)",
        ("execution_batch_in_progress", "payment_execution_batch"): "执行批次进行中 (Execution batch in progress)",
        ("execution_batch_confirmed", "payment_execution_batch"): "执行批次已确认 (Execution batch confirmed)",
        ("execution_batch_partially_confirmed", "payment_execution_batch"): "执行批次部分确认 (Execution batch partially confirmed)",
        ("execution_batch_failed", "payment_execution_batch"): "执行批次失败 (Execution batch failed)",
        ("execution_batch_reconciled", "payment_execution_batch"): "执行批次已对账 (Execution batch reconciled)",
        ("execution_item_planned", "payment_execution_item"): "执行项已规划 (Execution item planned)",
        ("execution_item_submitting", "payment_execution_item"): "执行项提交中 (Execution item submitting)",
        ("execution_item_reconciled", "payment_execution_item"): "执行项已对账 (Execution item reconciled)",
        ("onchain_tx_submitted", "payment_execution_item"): "执行项链上交易已提交 (Execution-item tx submitted)",
        ("onchain_tx_confirmed", "payment_execution_item"): "执行项链上交易已确认 (Execution-item tx confirmed)",
        ("onchain_tx_failed", "payment_execution_item"): "执行项链上交易失败 (Execution-item tx failed)",
        ("onchain_duplicate_rejected", "payment_execution_item"): "执行项链上防重触发 (Execution-item duplicate protection triggered)",
        ("onchain_event_emitted", "payment_execution_item"): "执行项链上事件已解析 (Execution-item event decoded)",
        ("wallet_tx_attached", "payment_execution_item"): "钱包交易哈希已附加 (Wallet tx hash attached)",
        ("safe_tx_attached", "payment_execution_item"): "Safe 执行交易哈希已附加 (Safe tx hash attached)",
        ("safe_proposal_attached", "payment_execution_item"): "Safe 提案信息已附加 (Safe proposal metadata attached)",
        ("execution_item_receipt_synced", "payment_execution_item"): "执行项回执已同步 (Execution-item receipt synced)",
        ("payment_order_executed", "payment_order"): "支付单执行完成 (Payment order executed)",
        ("payment_order_partially_executed", "payment_order"): "支付单部分执行 (Payment order partially executed)",
        ("payment_order_failed", "payment_order"): "支付单执行失败 (Payment order failed)",
        ("user_wallet_request_prepared", "payment_execution_batch"): "钱包签名请求已生成 (Wallet-sign request prepared)",
        ("safe_proposal_prepared", "payment_execution_batch"): "Safe 提案已生成 (Safe proposal prepared)",
        ("user_wallet_request_prepared", "payment_order"): "钱包签名请求已生成 (Wallet-sign request prepared)",
        ("safe_proposal_prepared", "payment_order"): "Safe 提案已生成 (Safe proposal prepared)",
        ("retry_mock_requested", "payment_order"): "发起重试请求 (Retry requested)",
        ("retry_mock_executed", "payment_order"): "重试执行完成 (Retry mock execution completed)",
    }
    if (log.action, log.entity_type) in mapping:
        return mapping[(log.action, log.entity_type)]
    formatted = log.action.replace("_", " ").title()
    return f"{formatted} ({log.action})"


def _resolve_audit_details(log: AuditLog) -> dict[str, Any] | None:
    if isinstance(log.after_json, dict):
        return log.after_json
    if isinstance(log.before_json, dict):
        return log.before_json
    return None
