from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    Beneficiary,
    CommandExecution,
    PaymentExecutionBatch,
    PaymentExecutionItem,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentSplit,
    PaymentSplitStatus,
    RiskCheck,
    User,
)
from app.modules.audit.service import build_audit_timeline_items
from app.modules.payments.schemas import (
    PaymentAuditSummary,
    PaymentBeneficiaryDetails,
    PaymentBeneficiarySummary,
    PaymentCommandDetails,
    PaymentCoreDetails,
    PaymentDetailResponse,
    PaymentExecutionBatchSummary,
    PaymentExecutionItemEventSummary,
    PaymentExecutionItemSummary,
    PaymentExecutionSummary,
    PaymentExecutionSplitSummary,
    PaymentListFilters,
    PaymentListItem,
    PaymentListResponse,
    PaymentListSort,
    PaymentRiskCheckDetails,
    PaymentSplitDetails,
    PaymentTimelineSummary,
    RetryMockRequest,
    RetryMockResponse,
)
from app.modules.risk.reason_codes import normalize_reason_codes

SortBy = Literal["created_at", "amount", "status", "risk_level"]
SortOrder = Literal["asc", "desc"]


def list_payments(
    session: Session,
    *,
    status_value: str | None,
    risk_level: str | None,
    user_id: UUID | None,
    organization_id: UUID | None,
    beneficiary_name: str | None,
    limit: int,
    sort_by: SortBy,
    sort_order: SortOrder,
) -> PaymentListResponse:
    split_count_subquery = (
        select(
            PaymentSplit.payment_order_id.label("payment_order_id"),
            func.count(PaymentSplit.id).label("split_count"),
        )
        .group_by(PaymentSplit.payment_order_id)
        .subquery()
    )

    stmt = (
        select(
            PaymentOrder,
            Beneficiary,
            CommandExecution.trace_id.label("command_trace_id"),
            func.coalesce(split_count_subquery.c.split_count, 0).label("split_count"),
        )
        .join(Beneficiary, Beneficiary.id == PaymentOrder.beneficiary_id)
        .outerjoin(CommandExecution, CommandExecution.id == PaymentOrder.source_command_id)
        .outerjoin(
            split_count_subquery,
            split_count_subquery.c.payment_order_id == PaymentOrder.id,
        )
    )

    if status_value:
        stmt = stmt.where(PaymentOrder.status == status_value)
    if risk_level:
        stmt = stmt.where(PaymentOrder.risk_level == risk_level)
    if user_id:
        stmt = stmt.where(PaymentOrder.user_id == user_id)
    if organization_id:
        stmt = stmt.where(PaymentOrder.organization_id == organization_id)
    if beneficiary_name:
        stmt = stmt.where(Beneficiary.name.ilike(f"%{beneficiary_name}%"))

    total = int(session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())

    sort_column = {
        "created_at": PaymentOrder.created_at,
        "amount": PaymentOrder.amount,
        "status": PaymentOrder.status,
        "risk_level": PaymentOrder.risk_level,
    }[sort_by]
    if sort_order == "asc":
        stmt = stmt.order_by(sort_column.asc(), PaymentOrder.id.asc())
    else:
        stmt = stmt.order_by(sort_column.desc(), PaymentOrder.id.desc())

    rows = session.execute(stmt.limit(limit)).all()
    items: list[PaymentListItem] = []
    for payment, beneficiary, command_trace_id, split_count in rows:
        executed = payment.status == PaymentOrderStatus.EXECUTED.value
        audit_trace_id = f"{command_trace_id}-confirm" if command_trace_id else None
        execution_summary = _build_execution_summary(payment=payment, audit_logs=[])
        items.append(
            PaymentListItem(
                id=payment.id,
                payment_order_id=payment.id,
                created_at=payment.created_at,
                user_id=payment.user_id,
                organization_id=payment.organization_id,
                beneficiary=PaymentBeneficiarySummary(
                    id=beneficiary.id,
                    name=beneficiary.name,
                    country=beneficiary.country,
                    risk_level=beneficiary.risk_level,
                    is_blacklisted=beneficiary.is_blacklisted,
                ),
                beneficiary_name=beneficiary.name,
                beneficiary_country=beneficiary.country,
                amount=_to_float(payment.amount),
                currency=payment.currency,
                status=payment.status,
                funding_source=payment.funding_source,
                funding_reference_id=payment.funding_reference_id,
                risk_level=payment.risk_level,
                requires_confirmation=payment.requires_confirmation,
                execution_route=payment.execution_route,
                execution_mode=payment.execution_mode,
                reference=payment.reference,
                source_command_id=payment.source_command_id,
                trace_id=command_trace_id,
                audit_trace_id=audit_trace_id,
                split_count=int(split_count or 0),
                mock_execution_executed=executed,
                onchain_status=payment.onchain_status,
                tx_hash=payment.tx_hash,
                explorer_url=payment.explorer_url,
                execution_summary=execution_summary,
            )
        )

    return PaymentListResponse(
        total=total,
        limit=limit,
        filters=PaymentListFilters(
            status=status_value,
            risk_level=risk_level,
            user_id=user_id,
            organization_id=organization_id,
            beneficiary_name=beneficiary_name,
        ),
        sort=PaymentListSort(sort_by=sort_by, sort_order=sort_order),
        items=items,
    )


def get_payment_detail(session: Session, payment_id: UUID) -> PaymentDetailResponse:
    payment = session.get(PaymentOrder, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"payment not found: {payment_id}",
        )

    beneficiary = session.get(Beneficiary, payment.beneficiary_id)
    splits = session.execute(
        select(PaymentSplit)
        .where(PaymentSplit.payment_order_id == payment.id)
        .order_by(PaymentSplit.sequence.asc())
    ).scalars().all()
    risk_checks = session.execute(
        select(RiskCheck)
        .where(RiskCheck.payment_order_id == payment.id)
        .order_by(RiskCheck.created_at.asc())
    ).scalars().all()
    execution_batch = session.execute(
        select(PaymentExecutionBatch)
        .where(PaymentExecutionBatch.payment_order_id == payment.id)
        .order_by(PaymentExecutionBatch.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    execution_items = []
    if execution_batch is not None:
        execution_items = session.execute(
            select(PaymentExecutionItem)
            .where(PaymentExecutionItem.execution_batch_id == execution_batch.id)
            .order_by(PaymentExecutionItem.sequence.asc(), PaymentExecutionItem.created_at.asc())
        ).scalars().all()

    command = None
    if payment.source_command_id:
        command = session.get(CommandExecution, payment.source_command_id)

    selected_trace_id, audit_logs = _load_related_audit_logs(
        session=session,
        payment=payment,
        command=command,
    )
    audit_items = build_audit_timeline_items(audit_logs)
    execution_item_audit_logs = _group_execution_item_audit_logs(audit_logs)
    execution = _build_execution_summary(
        payment=payment,
        audit_logs=audit_logs,
        split_rows=splits,
    )
    total_items, confirmed_items, failed_items, submitted_items = _count_execution_item_states(execution_items)
    execution_item_summaries = [
        _build_execution_item_summary(
            item=item,
            item_logs=execution_item_audit_logs.get(item.id, []),
            execution_mode=execution_batch.execution_mode if execution_batch is not None else payment.execution_route,
        )
        for item in execution_items
    ]

    return PaymentDetailResponse(
        payment=PaymentCoreDetails(
            id=payment.id,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            user_id=payment.user_id,
            organization_id=payment.organization_id,
            beneficiary_id=payment.beneficiary_id,
            source_command_id=payment.source_command_id,
            intent_source_text=payment.intent_source_text,
            amount=_to_float(payment.amount),
            currency=payment.currency,
            status=payment.status,
            funding_source=payment.funding_source,
            funding_reference_id=payment.funding_reference_id,
            risk_level=payment.risk_level,
            requires_confirmation=payment.requires_confirmation,
            execution_route=payment.execution_route,
            execution_mode=payment.execution_mode,
            network=payment.network,
            chain_id=payment.chain_id,
            onchain_status=payment.onchain_status,
            tx_hash=payment.tx_hash,
            explorer_url=payment.explorer_url,
            contract_address=payment.contract_address,
            token_address=payment.token_address,
            execution_tx_sent_at=payment.execution_tx_sent_at,
            execution_tx_confirmed_at=payment.execution_tx_confirmed_at,
            gas_used=int(payment.gas_used) if payment.gas_used is not None else None,
            effective_gas_price=(
                int(payment.effective_gas_price) if payment.effective_gas_price is not None else None
            ),
            onchain_payload_json=payment.onchain_payload_json,
            reference=payment.reference,
            metadata_json=payment.metadata_json,
        ),
        beneficiary=(
            PaymentBeneficiaryDetails(
                id=beneficiary.id,
                organization_id=beneficiary.organization_id,
                name=beneficiary.name,
                country=beneficiary.country,
                wallet_address=beneficiary.wallet_address,
                bank_account_mock=beneficiary.bank_account_mock,
                risk_level=beneficiary.risk_level,
                is_blacklisted=beneficiary.is_blacklisted,
                metadata_json=beneficiary.metadata_json,
            )
            if beneficiary
            else None
        ),
        splits=[
            PaymentSplitDetails(
                id=item.id,
                sequence=item.sequence,
                amount=_to_float(item.amount),
                currency=item.currency,
                status=item.status,
                tx_hash=item.tx_hash,
                explorer_url=item.explorer_url,
                onchain_status=item.onchain_status,
                execution_tx_sent_at=item.execution_tx_sent_at,
                execution_tx_confirmed_at=item.execution_tx_confirmed_at,
                gas_used=int(item.gas_used) if item.gas_used is not None else None,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in splits
        ],
        execution_batch=(
            PaymentExecutionBatchSummary(
                id=execution_batch.id,
                execution_mode=execution_batch.execution_mode,
                idempotency_key=execution_batch.idempotency_key,
                status=execution_batch.status,
                requested_by_user_id=execution_batch.requested_by_user_id,
                total_items=total_items,
                confirmed_items=confirmed_items,
                failed_items=failed_items,
                submitted_items=submitted_items,
                started_at=execution_batch.started_at,
                finished_at=execution_batch.finished_at,
                failure_reason=execution_batch.failure_reason,
                created_at=execution_batch.created_at,
            )
            if execution_batch is not None
            else None
        ),
        execution_items=execution_item_summaries,
        risk_checks=[
            PaymentRiskCheckDetails(
                id=item.id,
                check_type=item.check_type,
                result=item.result,
                score=_to_float(item.score) if item.score is not None else None,
                reason_codes=item.reason_codes_json or [],
                normalized_reason_codes=normalize_reason_codes(item.reason_codes_json),
                raw_payload_json=item.raw_payload_json,
                created_at=item.created_at,
            )
            for item in risk_checks
        ],
        command=_build_command_details(command),
        execution=execution,
        audit=PaymentAuditSummary(
            trace_id=selected_trace_id,
            count=len(audit_items),
            items=audit_items,
        ),
        timeline_summary=_build_payment_timeline_summary(
            payment=payment,
            execution_batch=execution_batch,
            execution_items=execution_items,
            audit_items=audit_items,
        ),
    )


def retry_payment_mock(
    session: Session,
    *,
    payment_id: UUID,
    request: RetryMockRequest,
) -> RetryMockResponse:
    payment = session.get(PaymentOrder, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"payment not found: {payment_id}",
        )

    actor_user_id = request.actor_user_id or payment.user_id
    actor = session.get(User, actor_user_id)
    command = session.get(CommandExecution, payment.source_command_id) if payment.source_command_id else None
    trace_id = f"{command.trace_id}-confirm" if command else f"trace-payment-{payment.id.hex[:12]}-retry"
    previous_status = payment.status

    if actor is None:
        return RetryMockResponse(
            status="validation_error",
            payment_order_id=payment.id,
            previous_status=previous_status,
            payment_status=payment.status,
            retry_performed=False,
            execution=None,
            audit_trace_id=trace_id,
            message="重试发起人不存在。 (Retry actor user was not found.)",
        )

    if payment.status == PaymentOrderStatus.EXECUTED.value:
        execution = PaymentExecutionSummary(
            mode=payment.execution_mode,
            executed=True,
            status=payment.status,
            transaction_ref=f"MOCK-TX-{payment.id.hex[:12].upper()}",
            executed_at=payment.updated_at,
            message="订单已是执行成功状态，无需重试。 (Payment is already executed; retry is not needed.)",
        )
        return RetryMockResponse(
            status="not_needed",
            payment_order_id=payment.id,
            previous_status=previous_status,
            payment_status=payment.status,
            retry_performed=False,
            execution=execution,
            audit_trace_id=trace_id,
            message="当前订单无需重试。 (Retry is not required for this payment.)",
        )

    if payment.status != PaymentOrderStatus.FAILED.value:
        return RetryMockResponse(
            status="non_retriable",
            payment_order_id=payment.id,
            previous_status=previous_status,
            payment_status=payment.status,
            retry_performed=False,
            execution=None,
            audit_trace_id=trace_id,
            message=f"当前状态 {payment.status} 不支持重试。 (Current status {payment.status} is non-retriable.)",
        )

    blocked, blocked_reason = _is_retry_blocked(session=session, payment=payment)
    if blocked:
        return RetryMockResponse(
            status="non_retriable",
            payment_order_id=payment.id,
            previous_status=previous_status,
            payment_status=payment.status,
            retry_performed=False,
            execution=None,
            audit_trace_id=trace_id,
            message=f"该订单命中阻断条件，不能重试。 (Retry blocked by policy: {blocked_reason})",
        )

    retryable, retryable_reason = _is_retryable_mock_failure(session=session, payment=payment)
    if not retryable:
        return RetryMockResponse(
            status="non_retriable",
            payment_order_id=payment.id,
            previous_status=previous_status,
            payment_status=payment.status,
            retry_performed=False,
            execution=None,
            audit_trace_id=trace_id,
            message=(
                "当前失败状态未标记为可重试模拟失败，保持保守不重试。 "
                f"(No retryable mock-failure signal found: {retryable_reason})"
            ),
        )

    session.add(
        _build_payment_audit_log(
            actor_user_id=actor_user_id,
            entity_type="payment_order",
            entity_id=payment.id,
            action="retry_mock_requested",
            before_json={"status": previous_status},
            after_json={"status": previous_status, "note": request.note},
            trace_id=trace_id,
        )
    )

    metadata_json = dict(payment.metadata_json or {})
    try:
        retry_count = int(metadata_json.get("mock_retry_count", 0)) + 1
    except Exception:
        retry_count = 1
    executed_at = datetime.now(timezone.utc)
    transaction_ref = f"MOCK-RETRY-{payment.id.hex[:8].upper()}-{retry_count:02d}"
    payment.status = PaymentOrderStatus.EXECUTED.value
    metadata_json["mock_retry_count"] = retry_count
    metadata_json["last_mock_retry_at"] = executed_at.isoformat()
    metadata_json["last_mock_retry_ref"] = transaction_ref
    metadata_json["last_mock_retry_note"] = request.note
    payment.metadata_json = metadata_json

    split_rows = session.execute(
        select(PaymentSplit)
        .where(PaymentSplit.payment_order_id == payment.id)
        .order_by(PaymentSplit.sequence.asc())
    ).scalars().all()
    for split in split_rows:
        before_split_status = split.status
        if split.status != PaymentSplitStatus.EXECUTED.value:
            split.status = PaymentSplitStatus.EXECUTED.value
            session.add(
                _build_payment_audit_log(
                    actor_user_id=actor_user_id,
                    entity_type="payment_split",
                    entity_id=split.id,
                    action="retry_mock_split_updated",
                    before_json={"status": before_split_status},
                    after_json={"status": split.status, "sequence": split.sequence},
                    trace_id=trace_id,
                )
            )

    session.add(
        _build_payment_audit_log(
            actor_user_id=actor_user_id,
            entity_type="payment_order",
            entity_id=payment.id,
            action="retry_mock_executed",
            before_json={"status": previous_status},
            after_json={
                "status": payment.status,
                "transaction_ref": transaction_ref,
                "retry_count": retry_count,
            },
            trace_id=trace_id,
        )
    )
    session.commit()

    execution = PaymentExecutionSummary(
        execution_route=payment.execution_route,
        mode=payment.execution_mode,
        executed=True,
        status=payment.status,
        transaction_ref=transaction_ref,
        executed_at=executed_at,
        message="模拟重试执行成功。 (Mock retry execution completed successfully.)",
    )
    return RetryMockResponse(
        status="ok",
        payment_order_id=payment.id,
        previous_status=previous_status,
        payment_status=payment.status,
        retry_performed=True,
        execution=execution,
        audit_trace_id=trace_id,
        message="已完成确定性模拟重试。 (Deterministic mock retry completed.)",
    )


def _build_execution_summary(
    *,
    payment: PaymentOrder,
    audit_logs: list[AuditLog],
    split_rows: list[PaymentSplit] | None = None,
) -> PaymentExecutionSummary:
    metadata_json = payment.metadata_json if isinstance(payment.metadata_json, dict) else {}
    onchain_payload = payment.onchain_payload_json if isinstance(payment.onchain_payload_json, dict) else {}

    if payment.execution_mode == "onchain":
        tx_rows = onchain_payload.get("txs") if isinstance(onchain_payload.get("txs"), list) else []
        latest_tx = tx_rows[-1] if tx_rows else {}
        tx_hash = payment.tx_hash or latest_tx.get("tx_hash")
        explorer_url = payment.explorer_url or latest_tx.get("explorer_url")
        payment_ref = latest_tx.get("payment_ref")
        decoded_events = latest_tx.get("events") if isinstance(latest_tx.get("events"), list) else []
        split_executions: list[PaymentExecutionSplitSummary] = []
        tx_by_split_index: dict[int, dict] = {}
        for tx in tx_rows:
            try:
                split_index = int(tx.get("split_index"))
            except Exception:
                continue
            tx_by_split_index[split_index] = tx
        for split in split_rows or []:
            tx = tx_by_split_index.get(int(split.sequence), {})
            split_executions.append(
                PaymentExecutionSplitSummary(
                    sequence=split.sequence,
                    amount=float(split.amount),
                    currency=split.currency,
                    status=split.status,
                    tx_hash=split.tx_hash,
                    explorer_url=split.explorer_url,
                    onchain_status=split.onchain_status,
                    execution_tx_sent_at=split.execution_tx_sent_at,
                    execution_tx_confirmed_at=split.execution_tx_confirmed_at,
                    gas_used=int(split.gas_used) if split.gas_used is not None else None,
                    payment_ref=tx.get("payment_ref"),
                )
            )
        if payment.status == PaymentOrderStatus.EXECUTED.value:
            message = "链上执行已确认。 (Onchain execution confirmed.)"
        elif payment.status == PaymentOrderStatus.FAILED.value:
            message = "链上执行失败。 (Onchain execution failed.)"
        elif payment.status == PaymentOrderStatus.CANCELLED.value:
            message = "订单已取消。 (Payment was cancelled.)"
        else:
            message = "订单已创建，等待链上处理。 (Payment order created and waiting for onchain processing.)"

        return PaymentExecutionSummary(
            execution_route=payment.execution_route,
            mode=payment.execution_mode,
            executed=payment.status == PaymentOrderStatus.EXECUTED.value,
            status=payment.status,
            transaction_ref=None,
            network=payment.network,
            chain_id=payment.chain_id,
            tx_hash=tx_hash,
            explorer_url=explorer_url,
            onchain_status=payment.onchain_status,
            contract_address=payment.contract_address,
            token_address=payment.token_address,
            gas_used=int(payment.gas_used) if payment.gas_used is not None else None,
            effective_gas_price=(
                int(payment.effective_gas_price) if payment.effective_gas_price is not None else None
            ),
            payment_ref=payment_ref,
            decoded_events=decoded_events,
            split_executions=split_executions or None,
            executed_at=payment.execution_tx_confirmed_at,
            message=message,
        )

    executed = payment.status == PaymentOrderStatus.EXECUTED.value
    transaction_ref: str | None = None
    executed_at = payment.updated_at if executed else None
    for log in reversed(audit_logs):
        if log.action == "mock_execute":
            payload = log.after_json or {}
            transaction_ref = str(payload.get("transaction_ref")) if payload.get("transaction_ref") else None
            executed_at = log.created_at
            break
    if executed and transaction_ref is None:
        transaction_ref = f"MOCK-TX-{payment.id.hex[:12].upper()}"

    if payment.status == PaymentOrderStatus.EXECUTED.value:
        message = "模拟执行已完成。 (Mock execution completed.)"
    elif payment.status == PaymentOrderStatus.FAILED.value:
        message = "订单执行失败。 (Payment execution failed.)"
    elif payment.status == PaymentOrderStatus.CANCELLED.value:
        message = "订单已取消。 (Payment was cancelled.)"
    else:
        message = "订单已创建，等待下一步处理。 (Payment order created and waiting for next action.)"

    return PaymentExecutionSummary(
        execution_route=payment.execution_route,
        mode=payment.execution_mode,
        executed=executed,
        status=payment.status,
        transaction_ref=transaction_ref,
        network=None,
        chain_id=None,
        tx_hash=None,
        explorer_url=None,
        onchain_status=payment.onchain_status,
        contract_address=payment.contract_address,
        token_address=payment.token_address,
        gas_used=None,
        effective_gas_price=None,
        payment_ref=None,
        decoded_events=metadata_json.get("onchain_events") if isinstance(metadata_json.get("onchain_events"), list) else [],
        split_executions=[
            PaymentExecutionSplitSummary(
                sequence=item.sequence,
                amount=float(item.amount),
                currency=item.currency,
                status=item.status,
                tx_hash=item.tx_hash,
                explorer_url=item.explorer_url,
                onchain_status=item.onchain_status,
                execution_tx_sent_at=item.execution_tx_sent_at,
                execution_tx_confirmed_at=item.execution_tx_confirmed_at,
                gas_used=int(item.gas_used) if item.gas_used is not None else None,
                payment_ref=None,
            )
            for item in (split_rows or [])
        ]
        or None,
        executed_at=executed_at,
        message=message,
    )


def _build_command_details(command: CommandExecution | None) -> PaymentCommandDetails | None:
    if command is None:
        return None
    intent = None
    if isinstance(command.parsed_intent_json, dict):
        intent_value = command.parsed_intent_json.get("intent")
        intent = str(intent_value) if intent_value is not None else None
    return PaymentCommandDetails(
        id=command.id,
        session_id=command.session_id,
        user_id=command.user_id,
        raw_text=command.raw_text,
        intent=intent,
        final_status=command.final_status,
        trace_id=command.trace_id,
        created_at=command.created_at,
    )


def _load_related_audit_logs(
    *,
    session: Session,
    payment: PaymentOrder,
    command: CommandExecution | None,
) -> tuple[str | None, list[AuditLog]]:
    execution_batches = session.execute(
        select(PaymentExecutionBatch.id).where(PaymentExecutionBatch.payment_order_id == payment.id)
    ).scalars().all()
    split_ids = session.execute(
        select(PaymentSplit.id).where(PaymentSplit.payment_order_id == payment.id)
    ).scalars().all()
    execution_item_ids = []
    if execution_batches:
        execution_item_ids = session.execute(
            select(PaymentExecutionItem.id).where(
                PaymentExecutionItem.execution_batch_id.in_(execution_batches)
            )
        ).scalars().all()
    related_entity_ids = [payment.id, *split_ids, *execution_batches, *execution_item_ids]
    if command is not None:
        related_entity_ids.append(command.id)

    if command is not None:
        trace_candidates = [f"{command.trace_id}-confirm", command.trace_id]
    else:
        trace_candidates = []

    for trace_id in trace_candidates:
        logs = session.execute(
            select(AuditLog)
            .where(
                AuditLog.trace_id == trace_id,
                AuditLog.entity_id.in_(related_entity_ids),
            )
            .order_by(AuditLog.created_at.asc())
        ).scalars().all()
        if logs:
            return trace_id, logs

    # Fallback: when source_command_id is null (or trace id drifted), still surface
    # relevant payment/execution logs by entity linkage.
    fallback_logs = session.execute(
        select(AuditLog)
        .where(
            AuditLog.entity_id.in_(related_entity_ids),
        )
        .order_by(AuditLog.created_at.asc())
    ).scalars().all()
    if fallback_logs:
        selected_trace_id = fallback_logs[-1].trace_id
        return selected_trace_id, fallback_logs
    return trace_candidates[0] if trace_candidates else None, []


def _to_float(value: Decimal) -> float:
    return float(value)


def _uuid_to_bytes32_hex(value: UUID) -> str:
    return "0x" + (value.bytes + b"\x00" * 16).hex()


def _count_execution_item_states(items: list[PaymentExecutionItem]) -> tuple[int, int, int, int]:
    total_items = len(items)
    confirmed_items = sum(1 for item in items if item.status == "confirmed")
    failed_items = sum(1 for item in items if item.status == "failed")
    submitted_items = sum(1 for item in items if item.status in {"submitting", "submitted"})
    return total_items, confirmed_items, failed_items, submitted_items


def _group_execution_item_audit_logs(audit_logs: list[AuditLog]) -> dict[UUID, list[AuditLog]]:
    grouped: dict[UUID, list[AuditLog]] = {}
    for log in audit_logs:
        if log.entity_type != "payment_execution_item":
            continue
        grouped.setdefault(log.entity_id, []).append(log)
    return grouped


def _build_execution_item_summary(
    *,
    item: PaymentExecutionItem,
    item_logs: list[AuditLog],
    execution_mode: str | None,
) -> PaymentExecutionItemSummary:
    receipt = item.receipt_json if isinstance(item.receipt_json, dict) else {}
    decoded_events = receipt.get("events") if isinstance(receipt.get("events"), list) else None
    duplicate_payload = receipt.get("duplicate_protection") if isinstance(receipt.get("duplicate_protection"), dict) else {}
    unsigned_tx_request = (
        receipt.get("unsigned_tx_request")
        if isinstance(receipt.get("unsigned_tx_request"), dict)
        else None
    )
    safe_proposal_request = (
        receipt.get("safe_proposal_request")
        if isinstance(receipt.get("safe_proposal_request"), dict)
        else None
    )
    safe_proposal_attachment = (
        receipt.get("safe_proposal_attachment")
        if isinstance(receipt.get("safe_proposal_attachment"), dict)
        else None
    )
    tx_attachment = (
        receipt.get("tx_attachment")
        if isinstance(receipt.get("tx_attachment"), dict)
        else None
    )
    pending_action = _derive_execution_item_pending_action(
        item=item,
        execution_mode=execution_mode,
        receipt=receipt,
        tx_attachment=tx_attachment,
    )
    duplicate_logs = [log for log in item_logs if log.action == "onchain_duplicate_rejected"]
    duplicate_reason = None
    if duplicate_logs:
        latest_duplicate_log = duplicate_logs[-1]
        if isinstance(latest_duplicate_log.after_json, dict):
            duplicate_reason = str(latest_duplicate_log.after_json.get("reason") or "") or None
    if duplicate_reason is None:
        duplicate_reason = str(duplicate_payload.get("reason") or "") or None
    is_duplicate_rejected = bool(duplicate_logs) or bool(duplicate_payload.get("detected"))
    latest_log = item_logs[-1] if item_logs else None

    return PaymentExecutionItemSummary(
        id=item.id,
        onchain_execution_item_id=_uuid_to_bytes32_hex(item.id),
        payment_split_id=item.payment_split_id,
        execution_mode=execution_mode,
        sequence=item.sequence,
        amount=float(item.amount),
        currency=item.currency,
        beneficiary_address=item.beneficiary_address,
        status=item.status,
        tx_hash=item.tx_hash,
        explorer_url=item.explorer_url,
        nonce=item.nonce,
        submitted_at=item.submitted_at,
        confirmed_at=item.confirmed_at,
        failure_reason=item.failure_reason,
        onchain_status=item.onchain_status,
        is_duplicate_rejected=is_duplicate_rejected,
        duplicate_reason=duplicate_reason,
        pending_action=pending_action,
        unsigned_tx_request=unsigned_tx_request,
        safe_proposal_request=safe_proposal_request,
        safe_proposal_attachment=safe_proposal_attachment,
        tx_attachment=tx_attachment,
        decoded_events=decoded_events,
        event_summary=PaymentExecutionItemEventSummary(
            event_count=len(item_logs),
            latest_action=latest_log.action if latest_log else None,
            latest_timestamp=latest_log.created_at if latest_log else None,
        ),
    )


def _derive_execution_item_pending_action(
    *,
    item: PaymentExecutionItem,
    execution_mode: str | None,
    receipt: dict[str, object],
    tx_attachment: dict[str, object] | None,
) -> str | None:
    if item.status in {"confirmed", "failed"}:
        return None
    persisted_pending = getattr(item, "pending_action", None)
    if persisted_pending:
        normalized_persisted = _normalize_pending_action_label(str(persisted_pending))
        if normalized_persisted:
            return normalized_persisted
    if item.tx_hash or tx_attachment is not None:
        if item.onchain_status not in {"confirmed_onchain", "failed_onchain"}:
            return "sync_receipt"
        return None
    mode = (execution_mode or "").lower()
    if mode == "user_wallet":
        return "generate_unsigned_tx"
    if mode == "safe":
        return "generate_safe_proposal"
    if mode == "operator":
        return "confirm_now"
    raw_pending = receipt.get("pending_action")
    return _normalize_pending_action_label(str(raw_pending)) if raw_pending else None


def _normalize_pending_action_label(value: str) -> str | None:
    normalized = (value or "").strip().lower()
    if normalized in {"generate_unsigned_tx", "generate_safe_proposal", "confirm_now", "sync_receipt", "none"}:
        return None if normalized == "none" else normalized
    if normalized == "sign_in_wallet":
        return "generate_unsigned_tx"
    if normalized == "approve_in_safe":
        return "generate_safe_proposal"
    if normalized == "attach_tx":
        return "sync_receipt"
    return None


def _build_payment_timeline_summary(
    *,
    payment: PaymentOrder,
    execution_batch: PaymentExecutionBatch | None,
    execution_items: list[PaymentExecutionItem],
    audit_items: list[object],
) -> PaymentTimelineSummary:
    latest_item = audit_items[-1] if audit_items else None
    has_duplicate_rejection = any(getattr(item, "action", "") == "onchain_duplicate_rejected" for item in audit_items)
    has_reconciliation = any(
        getattr(item, "action", "") in {"execution_batch_reconciled", "execution_item_reconciled"}
        for item in audit_items
    )
    has_partial_failure = (
        payment.status == PaymentOrderStatus.PARTIALLY_EXECUTED.value
        or (execution_batch is not None and execution_batch.status == "partially_confirmed")
        or any(item.status == "failed" for item in execution_items)
    )
    return PaymentTimelineSummary(
        count=len(audit_items),
        latest_action=getattr(latest_item, "action", None) if latest_item else None,
        latest_timestamp=getattr(latest_item, "timestamp", None) if latest_item else None,
        has_duplicate_rejection=has_duplicate_rejection,
        has_partial_failure=has_partial_failure,
        has_reconciliation=has_reconciliation,
    )


def _is_retry_blocked(
    *,
    session: Session,
    payment: PaymentOrder,
) -> tuple[bool, str]:
    beneficiary = session.get(Beneficiary, payment.beneficiary_id)
    if beneficiary and beneficiary.is_blacklisted:
        return True, "BLACKLISTED_BENEFICIARY"

    blocked_risk = session.execute(
        select(RiskCheck.id)
        .where(
            RiskCheck.payment_order_id == payment.id,
            RiskCheck.result == "block",
        )
        .limit(1)
    ).scalar_one_or_none()
    if blocked_risk is not None:
        return True, "RISK_CHECK_BLOCK"

    metadata_json = payment.metadata_json if isinstance(payment.metadata_json, dict) else {}
    normalized_codes = normalize_reason_codes(metadata_json.get("risk_reason_codes"))
    if "BLACKLISTED_BENEFICIARY" in normalized_codes:
        return True, "BLACKLISTED_BENEFICIARY"

    return False, "NONE"


def _is_retryable_mock_failure(
    *,
    session: Session,
    payment: PaymentOrder,
) -> tuple[bool, str]:
    metadata_json = payment.metadata_json if isinstance(payment.metadata_json, dict) else {}
    if metadata_json.get("mock_retryable") is True:
        return True, "METADATA_MOCK_RETRYABLE"

    failure_audit_id = session.execute(
        select(AuditLog.id)
        .where(
            AuditLog.entity_type == "payment_order",
            AuditLog.entity_id == payment.id,
            AuditLog.action.in_(("mock_execute_failed", "retry_mock_failed")),
        )
        .limit(1)
    ).scalar_one_or_none()
    if failure_audit_id is not None:
        return True, "AUDIT_FAILURE_ACTION"

    return False, "NO_RETRYABLE_FAILURE_SIGNAL"


def _build_payment_audit_log(
    *,
    actor_user_id: UUID,
    entity_type: str,
    entity_id: UUID,
    action: str,
    before_json: dict[str, object] | None,
    after_json: dict[str, object] | None,
    trace_id: str,
) -> AuditLog:
    return AuditLog(
        id=uuid.uuid4(),
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_json=before_json,
        after_json=after_json,
        trace_id=trace_id,
    )
