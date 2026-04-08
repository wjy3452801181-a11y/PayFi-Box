from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from web3 import Web3
from web3.exceptions import TransactionNotFound

from app.core.config import get_settings
from app.db.models import (
    AuditLog,
    Beneficiary,
    CommandExecution,
    CommandExecutionStatus,
    ExecutionMode,
    OnchainExecutionStatus,
    PaymentExecutionBatch,
    PaymentExecutionBatchStatus,
    PaymentExecutionItem,
    PaymentExecutionItemStatus,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentSplit,
    PaymentSplitStatus,
    User,
)
from app.modules.balance.lifecycle import bind_balance_lock_to_payment, settle_balance_lock_for_payment
from app.modules.command.risk import evaluate_payment_risk
from app.modules.confirm.schemas import (
    AttachExecutionItemSafeProposalRequest,
    AttachExecutionItemTxRequest,
    ConfirmExecutionItemResult,
    ConfirmRequest,
    ConfirmResponse,
    ConfirmRiskResult,
    ConfirmSplitResult,
    ExecutionItemActionResponse,
    MockExecutionResult,
    ReconcileExecutionBatchResult,
    ReconcileExecutionRequest,
    ReconcileExecutionResponse,
    SyncExecutionItemReceiptRequest,
)
from app.modules.execution.hashkey_service import (
    HashKeyDuplicateExecutionError,
    HashKeyExecutionError,
    HashKeyExecutionResult,
    HashKeyExecutionService,
    PAYMENT_EXECUTOR_ABI,
)

FINAL_COMMAND_STATUSES = {
    CommandExecutionStatus.CONFIRMED.value,
    CommandExecutionStatus.DECLINED.value,
    CommandExecutionStatus.BLOCKED.value,
    CommandExecutionStatus.EXECUTED.value,
}
FINAL_BATCH_STATUSES = {
    PaymentExecutionBatchStatus.CONFIRMED.value,
    PaymentExecutionBatchStatus.FAILED.value,
    PaymentExecutionBatchStatus.CANCELLED.value,
}
CONFIRM_EXECUTION_MODES = {"operator", "user_wallet", "safe"}


@dataclass
class _PlanResult:
    command: CommandExecution
    payment_order: PaymentOrder
    split_rows: list[PaymentSplit]
    batch: PaymentExecutionBatch
    items: list[PaymentExecutionItem]
    trace_id: str
    risk_preview: dict[str, Any]
    execution_backend: str
    execution_mode: str
    confirm_execution_mode: str
    actor_user_id: uuid.UUID
    beneficiary: Beneficiary
    reference: str


def handle_confirm(session: Session, request: ConfirmRequest) -> ConfirmResponse:
    settings = get_settings()
    confirm_execution_mode = _normalize_confirm_execution_mode(request.execution_mode)
    execution_backend = _normalize_execution_backend(settings.payment_execution_backend)
    execution_mode = (
        ExecutionMode.ONCHAIN.value
        if execution_backend == "hashkey_testnet"
        else ExecutionMode.MOCK.value
    )

    plan_or_response = _plan_execution_intent(
        session=session,
        request=request,
        execution_backend=execution_backend,
        execution_mode=execution_mode,
        confirm_execution_mode=confirm_execution_mode,
    )
    if isinstance(plan_or_response, ConfirmResponse):
        return plan_or_response
    plan = plan_or_response

    if plan.confirm_execution_mode == "operator" and plan.execution_mode == ExecutionMode.ONCHAIN.value:
        return _process_operator_onchain(
            session=session,
            plan=plan,
            request=request,
            allow_submit_new=True,
        )
    if plan.confirm_execution_mode == "operator":
        return _process_operator_mock(
            session=session,
            plan=plan,
            request=request,
        )
    if plan.confirm_execution_mode == "user_wallet":
        return _prepare_user_wallet_scaffold(
            session=session,
            plan=plan,
            request=request,
        )
    return _prepare_safe_scaffold(
        session=session,
        plan=plan,
        request=request,
    )


def attach_execution_item_tx(
    session: Session,
    *,
    execution_item_id: uuid.UUID,
    request: AttachExecutionItemTxRequest,
) -> ExecutionItemActionResponse:
    loaded = _load_plan_by_execution_item_id(session=session, execution_item_id=execution_item_id)
    if loaded is None:
        return ExecutionItemActionResponse(
            status="validation_error",
            execution_item_id=execution_item_id,
            message="未找到 execution item。 (Execution item not found.)",
        )
    plan, item = loaded
    if plan.confirm_execution_mode not in {"user_wallet", "safe"}:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="none",
            message="当前 execution mode 不允许手工附加 tx。 (Manual tx attach is only allowed for user_wallet/safe mode.)",
            session=session,
        )
    tx_hash = _normalize_tx_hash(request.tx_hash)
    if tx_hash is None:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="attach_tx",
            message="tx_hash 格式不正确。 (Invalid tx_hash format.)",
            session=session,
        )
    if item.tx_hash and item.tx_hash.lower() != tx_hash.lower():
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="none",
            message="execution item 已绑定其他 tx_hash，拒绝覆盖。 (Execution item already has a different tx_hash.)",
            session=session,
        )
    if item.status in {PaymentExecutionItemStatus.CONFIRMED.value, PaymentExecutionItemStatus.FAILED.value}:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="no_change",
            next_action="none",
            message="execution item 已终态，无需附加 tx。 (Execution item is already finalized.)",
            session=session,
        )
    submitted_at = request.submitted_at or datetime.now(timezone.utc)
    item.tx_hash = tx_hash
    item.explorer_url = _build_tx_explorer_url(tx_hash)
    item.submitted_at = item.submitted_at or submitted_at
    item.status = PaymentExecutionItemStatus.SUBMITTED.value
    item.onchain_status = OnchainExecutionStatus.SUBMITTED_ONCHAIN.value
    item.pending_action = "sync_receipt"
    receipt = dict(item.receipt_json or {}) if isinstance(item.receipt_json, dict) else {}
    receipt["pending_action"] = "sync_receipt"
    receipt["tx_attachment"] = {
        "tx_hash": tx_hash,
        "wallet_address": request.wallet_address,
        "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
        "attached_at": datetime.now(timezone.utc).isoformat(),
        "source": "safe" if plan.confirm_execution_mode == "safe" else "user_wallet",
    }
    item.receipt_json = receipt
    session.add(item)
    if plan.batch.status == PaymentExecutionBatchStatus.PLANNED.value:
        plan.batch.status = PaymentExecutionBatchStatus.IN_PROGRESS.value
        plan.batch.started_at = plan.batch.started_at or submitted_at
        session.add(plan.batch)
        session.add(
            _build_audit_log(
                actor_user_id=plan.actor_user_id,
                entity_type="payment_execution_batch",
                entity_id=plan.batch.id,
                action="execution_batch_started",
                before_json=None,
                after_json={"status": plan.batch.status},
                trace_id=plan.trace_id,
            )
        )
    plan.payment_order.onchain_status = OnchainExecutionStatus.SUBMITTED_ONCHAIN.value
    if plan.payment_order.execution_tx_sent_at is None:
        plan.payment_order.execution_tx_sent_at = submitted_at
    session.add(plan.payment_order)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_item",
            entity_id=item.id,
            action="safe_tx_attached" if plan.confirm_execution_mode == "safe" else "wallet_tx_attached",
            before_json=None,
            after_json={
                "tx_hash": tx_hash,
                "explorer_url": item.explorer_url,
                "execution_mode": plan.confirm_execution_mode,
            },
            trace_id=plan.trace_id,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        reloaded = _load_plan_by_execution_item_id(
            session=session,
            execution_item_id=execution_item_id,
        )
        if reloaded is not None:
            plan, item = reloaded
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="attach_tx",
            message="tx_hash 已被其他 execution item 使用。 (tx_hash is already bound to another execution item.)",
            session=session,
        )
    _refresh_plan_entities(session=session, plan=plan)
    _aggregate_batch_and_order_status(session=session, plan=plan)
    _refresh_plan_entities(session=session, plan=plan)
    refreshed_item = _find_execution_item(plan=plan, execution_item_id=execution_item_id)
    if refreshed_item is None:
        refreshed_item = item
    return _build_execution_item_action_response(
        plan=plan,
        item=refreshed_item,
        status="ok",
        next_action="sync_receipt",
        message="已绑定链上交易哈希，等待回执同步。 (Transaction hash attached; waiting for receipt sync.)",
        session=session,
    )


def attach_execution_item_safe_proposal(
    session: Session,
    *,
    execution_item_id: uuid.UUID,
    request: AttachExecutionItemSafeProposalRequest,
) -> ExecutionItemActionResponse:
    loaded = _load_plan_by_execution_item_id(session=session, execution_item_id=execution_item_id)
    if loaded is None:
        return ExecutionItemActionResponse(
            status="validation_error",
            execution_item_id=execution_item_id,
            message="未找到 execution item。 (Execution item not found.)",
        )
    plan, item = loaded
    if plan.confirm_execution_mode != "safe":
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="none",
            message="该 execution item 不在 safe 模式。 (Execution item is not in safe mode.)",
            session=session,
        )
    receipt = dict(item.receipt_json or {}) if isinstance(item.receipt_json, dict) else {}
    proposal_payload = request.proposal_payload if isinstance(request.proposal_payload, dict) else {}
    receipt["safe_proposal_attachment"] = {
        "safe_address": request.safe_address or get_settings().hashkey_safe_address,
        "proposal_id": request.proposal_id,
        "proposal_url": request.proposal_url,
        "proposer_wallet": request.proposer_wallet,
        "submitted_at": (
            request.submitted_at.isoformat()
            if isinstance(request.submitted_at, datetime)
            else None
        ),
        "payload": proposal_payload,
        "attached_at": datetime.now(timezone.utc).isoformat(),
    }
    item.receipt_json = receipt
    session.add(item)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_item",
            entity_id=item.id,
            action="safe_proposal_attached",
            before_json=None,
            after_json={
                "proposal_id": request.proposal_id,
                "proposal_url": request.proposal_url,
                "safe_address": request.safe_address or get_settings().hashkey_safe_address,
            },
            trace_id=plan.trace_id,
        )
    )
    session.commit()
    _refresh_plan_entities(session=session, plan=plan)
    refreshed_item = _find_execution_item(plan=plan, execution_item_id=execution_item_id) or item
    next_action = "sync_receipt" if refreshed_item.tx_hash else "generate_safe_proposal"
    return _build_execution_item_action_response(
        plan=plan,
        item=refreshed_item,
        status="ok",
        next_action=next_action,
        message="Safe 提案信息已附加。 (Safe proposal metadata attached.)",
        session=session,
    )


def sync_execution_item_receipt(
    session: Session,
    *,
    execution_item_id: uuid.UUID,
    request: SyncExecutionItemReceiptRequest,
) -> ExecutionItemActionResponse:
    loaded = _load_plan_by_execution_item_id(session=session, execution_item_id=execution_item_id)
    if loaded is None:
        return ExecutionItemActionResponse(
            status="validation_error",
            execution_item_id=execution_item_id,
            message="未找到 execution item。 (Execution item not found.)",
        )
    plan, item = loaded
    if request.actor_user_id is not None and session.get(User, request.actor_user_id) is None:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="none",
            message="actor_user_id 不存在。 (actor_user_id not found.)",
            session=session,
        )
    if not item.tx_hash:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="attach_tx",
            message="execution item 尚未绑定 tx_hash。 (Execution item has no tx hash attached.)",
            session=session,
        )
    if item.status in {PaymentExecutionItemStatus.CONFIRMED.value, PaymentExecutionItemStatus.FAILED.value} and not request.force:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="no_change",
            next_action="none",
            message="execution item 已终态，跳过回执同步。 (Execution item is already finalized.)",
            session=session,
        )

    settings = get_settings()
    w3 = Web3(Web3.HTTPProvider(settings.hashkey_rpc_url, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="sync_receipt",
            message=f"无法连接链上 RPC：{settings.hashkey_rpc_url} (Unable to connect chain RPC.)",
            session=session,
        )

    try:
        receipt = w3.eth.get_transaction_receipt(Web3.to_bytes(hexstr=item.tx_hash))
    except TransactionNotFound:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="pending",
            next_action="sync_receipt",
            message="交易尚未上链确认，请稍后重试。 (Transaction not mined yet; retry receipt sync later.)",
            session=session,
        )
    except Exception as exc:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="sync_receipt",
            message=f"读取链上回执失败：{exc} (Failed to fetch transaction receipt.)",
            session=session,
        )

    split_map = {split.id: split for split in plan.split_rows}
    tx_obj = None
    try:
        tx_obj = w3.eth.get_transaction(Web3.to_bytes(hexstr=item.tx_hash))
    except Exception as exc:
        return _build_execution_item_action_response(
            plan=plan,
            item=item,
            status="validation_error",
            next_action="sync_receipt",
            message=f"读取链上交易详情失败：{exc} (Failed to fetch transaction details.)",
            session=session,
        )
    if int(getattr(receipt, "status", 0)) != 1:
        duplicate_detected = _is_execution_item_marked_executed_onchain(
            w3=w3,
            contract_address=plan.payment_order.contract_address,
            execution_item_id=item.id,
        )
        if duplicate_detected:
            _apply_duplicate_item(
                session=session,
                plan=plan,
                item=item,
                reason="execution item already executed onchain",
                split_map=split_map,
            )
        else:
            _apply_failed_item(
                session=session,
                plan=plan,
                item=item,
                reason=f"onchain receipt status is 0: {item.tx_hash}",
                split_map=split_map,
            )
    else:
        receipt_match = _validate_receipt_match_for_execution_item(
            w3=w3,
            plan=plan,
            item=item,
            tx=tx_obj,
            receipt=receipt,
        )
        if not bool(receipt_match.get("ok")):
            _apply_receipt_mismatch_item(
                session=session,
                plan=plan,
                item=item,
                reason=str(receipt_match.get("reason") or "receipt_match_failed"),
                details=receipt_match.get("details") if isinstance(receipt_match.get("details"), dict) else None,
            )
            _refresh_plan_entities(session=session, plan=plan)
            _aggregate_batch_and_order_status(session=session, plan=plan)
            _refresh_plan_entities(session=session, plan=plan)
            refreshed_item = _find_execution_item(plan=plan, execution_item_id=execution_item_id) or item
            return _build_execution_item_action_response(
                plan=plan,
                item=refreshed_item,
                status="validation_error",
                next_action="sync_receipt",
                message=(
                    "交易已成功上链，但与当前执行项不匹配，拒绝确认。 "
                    "(Transaction succeeded onchain but does not match this execution item.)"
                ),
                session=session,
            )
        confirmed_at = datetime.now(timezone.utc)
        decoded_events = (
            receipt_match.get("decoded_events")
            if isinstance(receipt_match.get("decoded_events"), list)
            else []
        )
        matched_event = (
            receipt_match.get("matched_event")
            if isinstance(receipt_match.get("matched_event"), dict)
            else None
        )
        payment_ref = matched_event.get("payment_ref") if matched_event else (decoded_events[0].get("payment_ref") if decoded_events else None)
        confirmed_result = HashKeyExecutionResult(
            tx_hash=item.tx_hash,
            explorer_url=item.explorer_url or _build_tx_explorer_url(item.tx_hash),
            sent_at=item.submitted_at or confirmed_at,
            confirmed_at=confirmed_at,
            gas_used=int(receipt.gasUsed) if getattr(receipt, "gasUsed", None) is not None else None,
            effective_gas_price=(
                int(getattr(receipt, "effectiveGasPrice"))
                if getattr(receipt, "effectiveGasPrice", None) is not None
                else None
            ),
            payment_ref=payment_ref,
            decoded_events=decoded_events,
            contract_address=plan.payment_order.contract_address or "",
            token_address=plan.payment_order.token_address or "",
            network=plan.payment_order.network or settings.hashkey_network,
            chain_id=int(plan.payment_order.chain_id or settings.hashkey_chain_id),
            nonce=item.nonce,
            execution_item_id=_uuid_to_bytes32_hex(item.id),
        )
        _apply_confirmed_item(
            session=session,
            plan=plan,
            item=item,
            result=confirmed_result,
            split_map=split_map,
        )

    _refresh_plan_entities(session=session, plan=plan)
    _aggregate_batch_and_order_status(session=session, plan=plan)
    _refresh_plan_entities(session=session, plan=plan)
    refreshed_item = _find_execution_item(plan=plan, execution_item_id=execution_item_id) or item
    session.add(
        _build_audit_log(
            actor_user_id=request.actor_user_id or plan.actor_user_id,
            entity_type="payment_execution_item",
            entity_id=refreshed_item.id,
            action="execution_item_receipt_synced",
            before_json=None,
            after_json={
                "status": refreshed_item.status,
                "onchain_status": refreshed_item.onchain_status,
                "tx_hash": refreshed_item.tx_hash,
            },
            trace_id=plan.trace_id,
        )
    )
    session.commit()
    if refreshed_item.status == PaymentExecutionItemStatus.CONFIRMED.value:
        return _build_execution_item_action_response(
            plan=plan,
            item=refreshed_item,
            status="ok",
            next_action="none",
            message="执行项链上回执已确认。 (Execution item receipt synced and confirmed.)",
            session=session,
        )
    if refreshed_item.status == PaymentExecutionItemStatus.FAILED.value:
        return _build_execution_item_action_response(
            plan=plan,
            item=refreshed_item,
            status="ok",
            next_action="none",
            message="执行项链上回执显示失败。 (Execution item receipt synced as failed.)",
            session=session,
        )
    return _build_execution_item_action_response(
        plan=plan,
        item=refreshed_item,
        status="pending",
        next_action="sync_receipt",
        message="执行项仍在处理中。 (Execution item is still in progress.)",
        session=session,
    )


def reconcile_execution_batches(
    session: Session,
    request: ReconcileExecutionRequest,
) -> ReconcileExecutionResponse:
    settings = get_settings()
    execution_backend = _normalize_execution_backend(settings.payment_execution_backend)
    items: list[ReconcileExecutionBatchResult] = []

    if request.execution_batch_id is not None:
        batches = session.execute(
            select(PaymentExecutionBatch).where(PaymentExecutionBatch.id == request.execution_batch_id)
        ).scalars().all()
    else:
        batches = session.execute(
            select(PaymentExecutionBatch)
            .where(
                PaymentExecutionBatch.status.in_(
                    [
                        PaymentExecutionBatchStatus.PLANNED.value,
                        PaymentExecutionBatchStatus.IN_PROGRESS.value,
                        PaymentExecutionBatchStatus.PARTIALLY_CONFIRMED.value,
                    ]
                )
            )
            .order_by(PaymentExecutionBatch.created_at.desc())
            .limit(max(request.limit, 1))
        ).scalars().all()

    scanned = len(batches)
    reconciled = 0
    for batch in batches:
        before_batch_status = batch.status
        payment_order = session.get(PaymentOrder, batch.payment_order_id)
        if payment_order is None:
            continue
        before_order_status = payment_order.status
        command = None
        if payment_order.source_command_id is not None:
            command = session.get(CommandExecution, payment_order.source_command_id)
        if command is None:
            continue
        beneficiary = session.get(Beneficiary, payment_order.beneficiary_id)
        if beneficiary is None:
            continue
        split_rows = session.execute(
            select(PaymentSplit)
            .where(PaymentSplit.payment_order_id == payment_order.id)
            .order_by(PaymentSplit.sequence.asc())
        ).scalars().all()
        execution_items = session.execute(
            select(PaymentExecutionItem)
            .where(PaymentExecutionItem.execution_batch_id == batch.id)
            .order_by(PaymentExecutionItem.sequence.asc(), PaymentExecutionItem.created_at.asc())
        ).scalars().all()
        before_item_states = {
            item.id: {
                "status": item.status,
                "onchain_status": item.onchain_status,
                "tx_hash": item.tx_hash,
            }
            for item in execution_items
        }
        plan = _PlanResult(
            command=command,
            payment_order=payment_order,
            split_rows=split_rows,
            batch=batch,
            items=execution_items,
            trace_id=_build_confirm_trace_id(command),
            risk_preview=_extract_or_evaluate_risk(command),
            execution_backend=execution_backend,
            execution_mode=payment_order.execution_mode,
            confirm_execution_mode=payment_order.execution_route or "operator",
            actor_user_id=batch.requested_by_user_id,
            beneficiary=beneficiary,
            reference=payment_order.reference,
        )
        if (
            plan.confirm_execution_mode == "operator"
            and plan.execution_mode == ExecutionMode.ONCHAIN.value
        ):
            _process_operator_onchain(
                session=session,
                plan=plan,
                request=None,
                allow_submit_new=bool(request.resume_planned),
        )
        _refresh_plan_entities(session=session, plan=plan)
        c, f, p = _count_batch_items(plan.items)
        changed_items = 0
        for item in plan.items:
            before_state = before_item_states.get(item.id)
            if before_state is None:
                continue
            after_state = {
                "status": item.status,
                "onchain_status": item.onchain_status,
                "tx_hash": item.tx_hash,
            }
            if before_state != after_state:
                changed_items += 1
                session.add(
                    _build_audit_log(
                        actor_user_id=plan.actor_user_id,
                        entity_type="payment_execution_item",
                        entity_id=item.id,
                        action="execution_item_reconciled",
                        before_json=before_state,
                        after_json=after_state,
                        trace_id=plan.trace_id,
                    )
                )
        session.add(
            _build_audit_log(
                actor_user_id=plan.actor_user_id,
                entity_type="payment_execution_batch",
                entity_id=plan.batch.id,
                action="execution_batch_reconciled",
                before_json={
                    "batch_status": before_batch_status,
                    "payment_status": before_order_status,
                },
                after_json={
                    "batch_status": plan.batch.status,
                    "payment_status": plan.payment_order.status,
                    "confirmed_items": c,
                    "failed_items": f,
                    "pending_items": p,
                    "changed_items": changed_items,
                    "resume_planned": bool(request.resume_planned),
                },
                trace_id=plan.trace_id,
            )
        )
        session.commit()
        items.append(
            ReconcileExecutionBatchResult(
                execution_batch_id=plan.batch.id,
                payment_order_id=plan.payment_order.id,
                status=plan.batch.status,
                confirmed_items=c,
                failed_items=f,
                pending_items=p,
                message="reconciled",
            )
        )
        reconciled += 1

    overall = "ok"
    if any(item.status == PaymentExecutionBatchStatus.FAILED.value for item in items):
        overall = "partial"
    if scanned == 0:
        overall = "failed"
    return ReconcileExecutionResponse(
        status=overall,
        scanned_batches=scanned,
        reconciled_batches=reconciled,
        items=items,
        message=(
            "未找到可对账执行批次。 (No execution batches found for reconciliation.)"
            if scanned == 0
            else "执行批次对账完成。 (Execution batch reconciliation completed.)"
        ),
    )


def _plan_execution_intent(
    *,
    session: Session,
    request: ConfirmRequest,
    execution_backend: str,
    execution_mode: str,
    confirm_execution_mode: str,
) -> _PlanResult | ConfirmResponse:
    locked_command = session.execute(
        select(CommandExecution)
        .where(CommandExecution.id == request.command_id)
        .with_for_update()
    ).scalar_one_or_none()
    if locked_command is None:
        session.rollback()
        return _validation_error(
            command_id=request.command_id,
            trace_id=f"trace-confirm-{request.command_id.hex[:12]}",
            execution_mode=confirm_execution_mode,
            message="未找到对应命令。 (Command not found.)",
        )

    trace_id = _build_confirm_trace_id(locked_command)
    actor_user_id = request.actor_user_id or locked_command.user_id
    if session.get(User, actor_user_id) is None:
        session.rollback()
        return _validation_error(
            command_id=locked_command.id,
            trace_id=trace_id,
            execution_mode=confirm_execution_mode,
            message="确认操作者不存在。 (Confirmation actor user was not found.)",
        )

    if not _is_settlement_bridge_command(locked_command):
        latest_command_in_session = session.execute(
            select(CommandExecution.id)
            .where(CommandExecution.session_id == locked_command.session_id)
            .order_by(CommandExecution.created_at.desc(), CommandExecution.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_command_in_session is not None and latest_command_in_session != locked_command.id:
            session.rollback()
            return _validation_error(
                command_id=locked_command.id,
                trace_id=trace_id,
                execution_mode=confirm_execution_mode,
                message=(
                    "当前命令不是会话中的最新预览，请刷新后重试。 "
                    "(This command is stale; only the latest preview command in session can be confirmed.)"
                ),
            )

    idempotency_key = _resolve_idempotency_key(
        request=request,
        command=locked_command,
        confirm_execution_mode=confirm_execution_mode,
    )
    # Idempotency is command-scoped: only reuse an existing batch when both
    # source_command_id and idempotency_key match.
    existing_batch = session.execute(
        select(PaymentExecutionBatch)
        .where(
            PaymentExecutionBatch.source_command_id == locked_command.id,
            PaymentExecutionBatch.idempotency_key == idempotency_key,
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_batch is not None:
        session.commit()
        return _build_idempotent_response(
            session=session,
            command_id=locked_command.id,
            batch_id=existing_batch.id,
            execution_mode=confirm_execution_mode,
            trace_id=trace_id,
            message="命中幂等键，返回已存在执行结果。 (Idempotency key matched; returning existing execution state.)",
        )

    existing_order = session.execute(
        select(PaymentOrder).where(PaymentOrder.source_command_id == locked_command.id).limit(1)
    ).scalar_one_or_none()
    if existing_order is not None:
        latest_batch = session.execute(
            select(PaymentExecutionBatch)
            .where(PaymentExecutionBatch.payment_order_id == existing_order.id)
            .order_by(PaymentExecutionBatch.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        session.commit()
        if latest_batch is not None:
            return _build_idempotent_response(
                session=session,
                command_id=locked_command.id,
                batch_id=latest_batch.id,
                execution_mode=confirm_execution_mode,
                trace_id=trace_id,
                message="该命令已存在执行批次，返回当前状态。 (Execution batch already exists for this command.)",
            )
        return _validation_error(
            command_id=locked_command.id,
            trace_id=trace_id,
            execution_mode=confirm_execution_mode,
            message="该命令已生成支付单。 (A payment order already exists for this command.)",
        )

    if locked_command.final_status in FINAL_COMMAND_STATUSES:
        session.rollback()
        return _validation_error(
            command_id=locked_command.id,
            trace_id=trace_id,
            execution_mode=confirm_execution_mode,
            message="该命令已完成确认流程，不能重复确认。 (This command is already finalized.)",
        )

    if not request.confirmed:
        before_status = locked_command.final_status
        _append_confirmation_meta(
            command=locked_command,
            status=CommandExecutionStatus.DECLINED.value,
            trace_id=trace_id,
            note=request.note,
            locale=request.locale,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
            idempotency_key=idempotency_key,
        )
        locked_command.final_status = CommandExecutionStatus.DECLINED.value
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="command_execution",
                entity_id=locked_command.id,
                action="confirm_declined",
                before_json={"final_status": before_status},
                after_json={"final_status": CommandExecutionStatus.DECLINED.value},
                trace_id=trace_id,
            )
        )
        session.commit()
        return ConfirmResponse(
            status="declined",
            command_id=locked_command.id,
            execution_mode=confirm_execution_mode,
            next_action="none",
            payment_order_id=None,
            execution_batch_id=None,
            payment_status=None,
            execution_status=None,
            execution=None,
            splits=[],
            execution_items=[],
            unsigned_transactions=None,
            safe_proposal=None,
            risk=None,
            audit_trace_id=trace_id,
            message="已取消确认，本次不创建支付单。 (Confirmation declined; no payment order was created.)",
        )

    parsed = locked_command.parsed_intent_json or {}
    intent = parsed.get("intent")
    fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {}
    if intent != "create_payment":
        _mark_command_failed(
            command=locked_command,
            trace_id=trace_id,
            reason="non_payment_intent",
            note=request.note,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
            idempotency_key=idempotency_key,
        )
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="command_execution",
                entity_id=locked_command.id,
                action="confirm_rejected_non_payment",
                before_json=None,
                after_json={"intent": intent},
                trace_id=trace_id,
            )
        )
        session.commit()
        return _validation_error(
            command_id=locked_command.id,
            trace_id=trace_id,
            execution_mode=confirm_execution_mode,
            message="该命令不是支付创建命令，不能确认。 (Only create_payment commands are confirmable.)",
        )

    validation_message = _validate_payment_fields(fields=fields)
    if validation_message is not None:
        _mark_command_failed(
            command=locked_command,
            trace_id=trace_id,
            reason="missing_required_fields",
            note=request.note,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
            idempotency_key=idempotency_key,
        )
        session.commit()
        return _validation_error(
            command_id=locked_command.id,
            trace_id=trace_id,
            execution_mode=confirm_execution_mode,
            message=validation_message,
        )

    amount = Decimal(str(fields["amount"]))
    currency = str(fields["currency"]).upper()
    split_count = _safe_split_count(fields.get("split_count"))
    reference = str(fields.get("reference") or f"CMD-{locked_command.id.hex[:8].upper()}")
    beneficiary_obj = fields.get("beneficiary") if isinstance(fields.get("beneficiary"), dict) else {}
    beneficiary_id = _safe_uuid(beneficiary_obj.get("id"))
    if beneficiary_id is None:
        _mark_command_failed(
            command=locked_command,
            trace_id=trace_id,
            reason="unresolved_beneficiary",
            note=request.note,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
            idempotency_key=idempotency_key,
        )
        session.commit()
        return _validation_error(
            command_id=locked_command.id,
            trace_id=trace_id,
            execution_mode=confirm_execution_mode,
            message="受益人未解析为系统对象，当前版本不能确认。 (Beneficiary is unresolved and cannot be confirmed.)",
        )

    beneficiary = session.get(Beneficiary, beneficiary_id)
    if beneficiary is None:
        _mark_command_failed(
            command=locked_command,
            trace_id=trace_id,
            reason="beneficiary_not_found",
            note=request.note,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
            idempotency_key=idempotency_key,
        )
        session.commit()
        return _validation_error(
            command_id=locked_command.id,
            trace_id=trace_id,
            execution_mode=confirm_execution_mode,
            message="受益人不存在。 (Beneficiary not found.)",
        )

    risk_preview = evaluate_payment_risk(fields)
    if risk_preview["decision"] == "block":
        before_status = locked_command.final_status
        _append_confirmation_meta(
            command=locked_command,
            status=CommandExecutionStatus.BLOCKED.value,
            trace_id=trace_id,
            note=request.note,
            locale=request.locale,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
            idempotency_key=idempotency_key,
        )
        locked_command.final_status = CommandExecutionStatus.BLOCKED.value
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="command_execution",
                entity_id=locked_command.id,
                action="confirm_blocked",
                before_json={"final_status": before_status},
                after_json={"final_status": CommandExecutionStatus.BLOCKED.value, "risk": risk_preview},
                trace_id=trace_id,
            )
        )
        session.commit()
        return ConfirmResponse(
            status="blocked",
            command_id=locked_command.id,
            execution_mode=confirm_execution_mode,
            next_action="none",
            payment_order_id=None,
            execution_batch_id=None,
            payment_status=None,
            execution_status=None,
            execution=MockExecutionResult(
                mode="onchain" if execution_mode == ExecutionMode.ONCHAIN.value else "mock",
                executed=False,
                transaction_ref=None,
                network=get_settings().hashkey_network if execution_mode == ExecutionMode.ONCHAIN.value else None,
                chain_id=get_settings().hashkey_chain_id if execution_mode == ExecutionMode.ONCHAIN.value else None,
                tx_hash=None,
                explorer_url=None,
                onchain_status=(
                    OnchainExecutionStatus.BLOCKED.value
                    if execution_mode == ExecutionMode.ONCHAIN.value
                    else None
                ),
                contract_address=(
                    get_settings().hashkey_payment_executor_address
                    if execution_mode == ExecutionMode.ONCHAIN.value
                    else None
                ),
                token_address=(
                    get_settings().hashkey_payment_token_address
                    if execution_mode == ExecutionMode.ONCHAIN.value
                    else None
                ),
                gas_used=None,
                effective_gas_price=None,
                payment_ref=None,
                decoded_events=[],
                split_executions=[],
                executed_at=None,
                message=(
                    "风险命中拦截，未发送链上交易。 (Blocked by risk policy; no onchain transaction was sent.)"
                ),
            ),
            splits=[],
            execution_items=[],
            unsigned_transactions=None,
            safe_proposal=None,
            risk=ConfirmRiskResult(**risk_preview),
            audit_trace_id=trace_id,
            message="确认请求被风控拦截。 (Confirmation was blocked by risk policy.)",
        )

    if execution_mode == ExecutionMode.ONCHAIN.value:
        if not beneficiary.wallet_address or not Web3.is_address(beneficiary.wallet_address):
            _mark_command_failed(
                command=locked_command,
                trace_id=trace_id,
                reason="invalid_beneficiary_wallet",
                note=request.note,
                execution_backend=execution_backend,
                execution_route=confirm_execution_mode,
                idempotency_key=idempotency_key,
            )
            session.commit()
            return _validation_error(
                command_id=locked_command.id,
                trace_id=trace_id,
                execution_mode=confirm_execution_mode,
                message="链上执行需要受益人钱包地址。 (Onchain execution requires a valid beneficiary wallet address.)",
            )

    user = session.get(User, locked_command.user_id)
    organization_id = user.organization_id if user else None
    payment_order = PaymentOrder(
        id=uuid.uuid4(),
        user_id=locked_command.user_id,
        organization_id=organization_id,
        beneficiary_id=beneficiary_id,
        source_command_id=locked_command.id,
        intent_source_text=locked_command.raw_text,
        amount=amount,
        currency=currency,
        status=PaymentOrderStatus.APPROVED.value,
        reference=reference,
        risk_level=risk_preview["risk_level"],
        requires_confirmation=False,
        execution_route=confirm_execution_mode,
        execution_mode=execution_mode,
        network=get_settings().hashkey_network if execution_mode == ExecutionMode.ONCHAIN.value else None,
        chain_id=get_settings().hashkey_chain_id if execution_mode == ExecutionMode.ONCHAIN.value else None,
        onchain_status=(
            OnchainExecutionStatus.PENDING_SUBMISSION.value
            if execution_mode == ExecutionMode.ONCHAIN.value
            else None
        ),
        contract_address=(
            get_settings().hashkey_payment_executor_address
            if execution_mode == ExecutionMode.ONCHAIN.value
            else None
        ),
        token_address=(
            get_settings().hashkey_payment_token_address
            if execution_mode == ExecutionMode.ONCHAIN.value
            else None
        ),
        metadata_json={
            "confirmed_by": str(actor_user_id),
            "note": request.note,
            "locale": request.locale,
            "risk_reason_codes": risk_preview["reason_codes"],
            "preview_mode": "step8d_confirm",
            "execution_backend": execution_backend,
            "execution_route": confirm_execution_mode,
            "idempotency_key": idempotency_key,
        },
    )
    session.add(payment_order)
    session.flush()
    split_rows: list[PaymentSplit] = []
    if split_count > 1:
        split_rows = _create_payment_splits(
            session=session,
            payment_order=payment_order,
            split_count=split_count,
            amount=amount,
            currency=currency,
            trace_id=trace_id,
            actor_user_id=actor_user_id,
            default_onchain_status=(
                OnchainExecutionStatus.PENDING_SUBMISSION.value
                if execution_mode == ExecutionMode.ONCHAIN.value
                else None
            ),
        )

    batch = PaymentExecutionBatch(
        id=uuid.uuid4(),
        payment_order_id=payment_order.id,
        source_command_id=locked_command.id,
        execution_mode=confirm_execution_mode,
        idempotency_key=idempotency_key,
        status=PaymentExecutionBatchStatus.PLANNED.value,
        requested_by_user_id=actor_user_id,
        metadata_json={
            "trace_id": trace_id,
            "execution_backend": execution_backend,
            "execution_mode": execution_mode,
        },
    )
    session.add(batch)
    session.flush()

    items: list[PaymentExecutionItem] = []
    targets: list[tuple[int, Decimal, uuid.UUID | None]] = []
    if split_rows:
        for split in split_rows:
            targets.append((split.sequence, Decimal(split.amount), split.id))
    else:
        targets.append((1, Decimal(payment_order.amount), None))
    for sequence, split_amount, split_id in targets:
        item = PaymentExecutionItem(
            id=uuid.uuid4(),
            execution_batch_id=batch.id,
            payment_split_id=split_id,
            sequence=int(sequence),
            amount=split_amount,
            currency=payment_order.currency,
            beneficiary_address=Web3.to_checksum_address(str(beneficiary.wallet_address)),
            status=PaymentExecutionItemStatus.PLANNED.value,
            onchain_status=(
                OnchainExecutionStatus.PENDING_SUBMISSION.value
                if execution_mode == ExecutionMode.ONCHAIN.value
                else None
            ),
            pending_action=_resolve_pending_action_from_mode(confirm_execution_mode),
        )
        session.add(item)
        session.flush()
        items.append(item)
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="payment_execution_item",
                entity_id=item.id,
                action="execution_item_planned",
                before_json=None,
                after_json={
                    "sequence": item.sequence,
                    "amount": float(item.amount),
                    "currency": item.currency,
                    "status": item.status,
                },
                trace_id=trace_id,
            )
        )

    _append_confirmation_meta(
        command=locked_command,
        status=CommandExecutionStatus.CONFIRMED.value,
        trace_id=trace_id,
        note=request.note,
        locale=request.locale,
        payment_order_id=payment_order.id,
        execution_backend=execution_backend,
        execution_route=confirm_execution_mode,
        idempotency_key=idempotency_key,
    )
    locked_command.final_status = CommandExecutionStatus.CONFIRMED.value

    session.add(
        _build_audit_log(
            actor_user_id=actor_user_id,
            entity_type="command_execution",
            entity_id=locked_command.id,
            action="confirm_accepted",
            before_json={"final_status": CommandExecutionStatus.READY.value},
            after_json={"final_status": CommandExecutionStatus.CONFIRMED.value},
            trace_id=trace_id,
        )
    )
    session.add(
        _build_audit_log(
            actor_user_id=actor_user_id,
            entity_type="payment_order",
            entity_id=payment_order.id,
            action="create",
            before_json=None,
            after_json={"status": payment_order.status, "reference": payment_order.reference},
            trace_id=trace_id,
        )
    )
    session.add(
        _build_audit_log(
            actor_user_id=actor_user_id,
            entity_type="payment_execution_batch",
            entity_id=batch.id,
            action="execution_batch_planned",
            before_json=None,
            after_json={
                "status": batch.status,
                "idempotency_key": batch.idempotency_key,
                "item_count": len(items),
            },
            trace_id=trace_id,
        )
    )
    session.commit()
    return _PlanResult(
        command=locked_command,
        payment_order=payment_order,
        split_rows=split_rows,
        batch=batch,
        items=items,
        trace_id=trace_id,
        risk_preview=risk_preview,
        execution_backend=execution_backend,
        execution_mode=execution_mode,
        confirm_execution_mode=confirm_execution_mode,
        actor_user_id=actor_user_id,
        beneficiary=beneficiary,
        reference=reference,
    )


def _process_operator_onchain(
    *,
    session: Session,
    plan: _PlanResult,
    request: ConfirmRequest | None,
    allow_submit_new: bool,
) -> ConfirmResponse:
    _refresh_plan_entities(session=session, plan=plan)
    if plan.batch.status in FINAL_BATCH_STATUSES:
        return _build_confirm_response_from_plan(plan=plan, override_status="ok")

    settings = get_settings()
    executor = HashKeyExecutionService(settings)

    if plan.batch.started_at is None:
        plan.batch.started_at = datetime.now(timezone.utc)
    plan.batch.status = PaymentExecutionBatchStatus.IN_PROGRESS.value
    session.add(plan.batch)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_batch",
            entity_id=plan.batch.id,
            action="execution_batch_started",
            before_json=None,
            after_json={"status": plan.batch.status},
            trace_id=plan.trace_id,
        )
    )
    session.commit()

    nonce = executor.get_pending_nonce()
    max_nonce = max([item.nonce or -1 for item in plan.items], default=-1)
    if max_nonce >= nonce:
        nonce = max_nonce + 1

    split_map = {split.id: split for split in plan.split_rows}
    total_items = len(plan.items)
    for item in plan.items:
        if item.status == PaymentExecutionItemStatus.CONFIRMED.value:
            continue

        if item.status in {PaymentExecutionItemStatus.SUBMITTING.value, PaymentExecutionItemStatus.SUBMITTED.value}:
            if item.tx_hash:
                _reconcile_submitted_item(
                    session=session,
                    plan=plan,
                    item=item,
                    executor=executor,
                )
            elif allow_submit_new:
                item.status = PaymentExecutionItemStatus.FAILED.value
                item.failure_reason = "missing_tx_hash_while_submitting"
                item.onchain_status = OnchainExecutionStatus.FAILED_ONCHAIN.value
                item.pending_action = None
                session.add(item)
                session.commit()
            continue

        if item.status == PaymentExecutionItemStatus.FAILED.value:
            continue

        if not allow_submit_new:
            continue

        item.status = PaymentExecutionItemStatus.SUBMITTING.value
        item.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value
        item.pending_action = "confirm_now"
        session.add(item)
        session.add(
            _build_audit_log(
                actor_user_id=plan.actor_user_id,
                entity_type="payment_execution_item",
                entity_id=item.id,
                action="execution_item_submitting",
                before_json=None,
                after_json={"sequence": item.sequence, "status": item.status},
                trace_id=plan.trace_id,
            )
        )
        session.commit()

        try:
            submitted = executor.submit_payment(
                order_id=plan.payment_order.id,
                beneficiary_address=item.beneficiary_address,
                amount=Decimal(item.amount),
                reference=plan.reference,
                split_index=item.sequence,
                split_count=total_items,
                nonce=nonce,
                execution_item_id=item.id,
            )
            nonce = max(nonce + 1, submitted.nonce + 1)
            item.status = PaymentExecutionItemStatus.SUBMITTED.value
            item.tx_hash = submitted.tx_hash
            item.explorer_url = submitted.explorer_url
            item.nonce = submitted.nonce
            item.submitted_at = submitted.sent_at
            item.onchain_status = OnchainExecutionStatus.SUBMITTED_ONCHAIN.value
            item.pending_action = "sync_receipt"
            session.add(item)
            session.add(
                _build_audit_log(
                    actor_user_id=plan.actor_user_id,
                    entity_type="payment_execution_item",
                    entity_id=item.id,
                    action="onchain_tx_submitted",
                    before_json=None,
                    after_json={
                        "tx_hash": submitted.tx_hash,
                        "explorer_url": submitted.explorer_url,
                        "nonce": submitted.nonce,
                        "network": submitted.network,
                        "chain_id": submitted.chain_id,
                    },
                    trace_id=plan.trace_id,
                )
            )
            session.commit()

            try:
                result = executor.confirm_submitted_payment(
                    tx_hash=submitted.tx_hash,
                    sent_at=submitted.sent_at,
                    nonce=submitted.nonce,
                    execution_item_id=submitted.execution_item_id,
                )
                _apply_confirmed_item(
                    session=session,
                    plan=plan,
                    item=item,
                    result=result,
                    split_map=split_map,
                )
            except HashKeyDuplicateExecutionError as exc:
                _apply_duplicate_item(
                    session=session,
                    plan=plan,
                    item=item,
                    reason=str(exc),
                    split_map=split_map,
                )
            except HashKeyExecutionError as exc:
                _apply_failed_item(
                    session=session,
                    plan=plan,
                    item=item,
                    reason=str(exc),
                    split_map=split_map,
                )
        except HashKeyDuplicateExecutionError as exc:
            _apply_duplicate_item(
                session=session,
                plan=plan,
                item=item,
                reason=str(exc),
                split_map=split_map,
            )
        except HashKeyExecutionError as exc:
            _apply_failed_item(
                session=session,
                plan=plan,
                item=item,
                reason=str(exc),
                split_map=split_map,
            )

    _refresh_plan_entities(session=session, plan=plan)
    _aggregate_batch_and_order_status(session=session, plan=plan)
    return _build_confirm_response_from_plan(plan=plan)


def _process_operator_mock(
    *,
    session: Session,
    plan: _PlanResult,
    request: ConfirmRequest | None,
) -> ConfirmResponse:
    _refresh_plan_entities(session=session, plan=plan)
    executed_at = datetime.now(timezone.utc)
    for item in plan.items:
        item.status = PaymentExecutionItemStatus.CONFIRMED.value
        item.confirmed_at = executed_at
        item.failure_reason = None
        item.onchain_status = None
        item.pending_action = None
        item.receipt_json = {"mode": "mock", "transaction_ref": f"MOCK-TX-{item.id.hex[:12].upper()}"}
        session.add(item)
    for split in plan.split_rows:
        split.status = PaymentSplitStatus.EXECUTED.value
        session.add(split)
    plan.batch.status = PaymentExecutionBatchStatus.CONFIRMED.value
    plan.batch.started_at = plan.batch.started_at or executed_at
    plan.batch.finished_at = executed_at
    session.add(plan.batch)
    plan.payment_order.status = PaymentOrderStatus.EXECUTED.value
    plan.payment_order.onchain_status = None
    plan.payment_order.execution_mode = ExecutionMode.MOCK.value
    plan.payment_order.execution_tx_confirmed_at = executed_at
    plan.payment_order.tx_hash = None
    plan.payment_order.explorer_url = None
    bind_balance_lock_to_payment(session=session, payment_order=plan.payment_order)
    settle_balance_lock_for_payment(
        session=session,
        payment_order=plan.payment_order,
        actor_user_id=plan.actor_user_id,
        trace_id=plan.trace_id,
    )
    session.add(plan.payment_order)
    _append_confirmation_meta(
        command=plan.command,
        status=CommandExecutionStatus.EXECUTED.value,
        trace_id=plan.trace_id,
        note=request.note if request else None,
        locale=request.locale if request else None,
        payment_order_id=plan.payment_order.id,
        execution_backend=plan.execution_backend,
        execution_route=plan.confirm_execution_mode,
        idempotency_key=plan.batch.idempotency_key,
    )
    plan.command.final_status = CommandExecutionStatus.EXECUTED.value
    session.add(plan.command)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_batch",
            entity_id=plan.batch.id,
            action="mock_execute",
            before_json=None,
            after_json={"status": plan.batch.status, "item_count": len(plan.items)},
            trace_id=plan.trace_id,
        )
    )
    session.commit()
    _refresh_plan_entities(session=session, plan=plan)
    return _build_confirm_response_from_plan(plan=plan)


def _prepare_user_wallet_scaffold(
    *,
    session: Session,
    plan: _PlanResult,
    request: ConfirmRequest | None,
) -> ConfirmResponse:
    _refresh_plan_entities(session=session, plan=plan)
    tx_requests = _build_unsigned_transactions_from_items(plan=plan)
    tx_request_map = {
        str(item.get("execution_item_id")): item
        for item in tx_requests
        if isinstance(item, dict) and item.get("execution_item_id")
    }
    for item in plan.items:
        item.status = PaymentExecutionItemStatus.PLANNED.value
        item.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value
        item.pending_action = "generate_unsigned_tx"
        receipt = dict(item.receipt_json or {}) if isinstance(item.receipt_json, dict) else {}
        receipt["pending_action"] = "generate_unsigned_tx"
        receipt["unsigned_tx_request"] = tx_request_map.get(str(item.id))
        item.receipt_json = receipt
        session.add(item)
    plan.batch.status = PaymentExecutionBatchStatus.PLANNED.value
    session.add(plan.batch)
    plan.payment_order.status = PaymentOrderStatus.APPROVED.value
    plan.payment_order.execution_mode = ExecutionMode.ONCHAIN.value
    plan.payment_order.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value
    session.add(plan.payment_order)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_batch",
            entity_id=plan.batch.id,
            action="user_wallet_request_prepared",
            before_json=None,
            after_json={"next_action": "generate_unsigned_tx", "tx_count": len(plan.items)},
            trace_id=plan.trace_id,
        )
    )
    session.commit()
    _refresh_plan_entities(session=session, plan=plan)
    response = _build_confirm_response_from_plan(plan=plan)
    response.next_action = "generate_unsigned_tx"
    response.status = "ok"
    response.message = "已进入 user_wallet 模式，等待钱包签名。 (user_wallet mode prepared; waiting for wallet signature.)"
    response.unsigned_transactions = tx_requests
    return response


def _prepare_safe_scaffold(
    *,
    session: Session,
    plan: _PlanResult,
    request: ConfirmRequest | None,
) -> ConfirmResponse:
    _refresh_plan_entities(session=session, plan=plan)
    tx_requests = _build_unsigned_transactions_from_items(plan=plan)
    safe_address = get_settings().hashkey_safe_address
    for item in plan.items:
        item.status = PaymentExecutionItemStatus.PLANNED.value
        item.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value
        item.pending_action = "generate_safe_proposal"
        receipt = dict(item.receipt_json or {}) if isinstance(item.receipt_json, dict) else {}
        receipt["pending_action"] = "generate_safe_proposal"
        receipt["safe_proposal_request"] = {
            "safe_address": safe_address,
            "proposal_type": "safe_transaction_proposal",
            "execution_item_id": str(item.id),
        }
        receipt["unsigned_tx_request"] = next(
            (tx for tx in tx_requests if str(tx.get("execution_item_id")) == str(item.id)),
            None,
        )
        item.receipt_json = receipt
        session.add(item)
    plan.batch.status = PaymentExecutionBatchStatus.PLANNED.value
    session.add(plan.batch)
    plan.payment_order.status = PaymentOrderStatus.APPROVED.value
    plan.payment_order.execution_mode = ExecutionMode.ONCHAIN.value
    plan.payment_order.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value
    session.add(plan.payment_order)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_batch",
            entity_id=plan.batch.id,
            action="safe_proposal_prepared",
            before_json=None,
            after_json={"next_action": "generate_safe_proposal", "tx_count": len(plan.items)},
            trace_id=plan.trace_id,
        )
    )
    session.commit()
    _refresh_plan_entities(session=session, plan=plan)
    response = _build_confirm_response_from_plan(plan=plan)
    response.next_action = "generate_safe_proposal"
    response.status = "ok"
    response.message = "已进入 safe 模式，等待 Safe 审批。 (safe mode prepared; waiting for Safe approval.)"
    response.safe_proposal = {
        "safe_address": safe_address,
        "network": get_settings().hashkey_network,
        "chain_id": get_settings().hashkey_chain_id,
        "proposal_status": "prepared",
        "proposal_type": "safe_transaction_proposal",
        "transactions": tx_requests,
    }
    return response


def _reconcile_submitted_item(
    *,
    session: Session,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    executor: HashKeyExecutionService,
) -> None:
    if not item.tx_hash:
        return
    split_map = {split.id: split for split in plan.split_rows}
    try:
        result = executor.confirm_submitted_payment(
            tx_hash=item.tx_hash,
            sent_at=item.submitted_at or datetime.now(timezone.utc),
            nonce=item.nonce,
            execution_item_id=_uuid_to_bytes32_hex(item.id),
        )
        _apply_confirmed_item(
            session=session,
            plan=plan,
            item=item,
            result=result,
            split_map=split_map,
        )
    except HashKeyDuplicateExecutionError as exc:
        _apply_duplicate_item(
            session=session,
            plan=plan,
            item=item,
            reason=str(exc),
            split_map=split_map,
        )
    except HashKeyExecutionError as exc:
        _apply_failed_item(
            session=session,
            plan=plan,
            item=item,
            reason=str(exc),
            split_map=split_map,
        )


def _apply_confirmed_item(
    *,
    session: Session,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    result: HashKeyExecutionResult,
    split_map: dict[uuid.UUID, PaymentSplit],
) -> None:
    verification = _validate_execution_result_match_for_item(
        plan=plan,
        item=item,
        result=result,
    )
    if not bool(verification.get("ok")):
        _apply_receipt_mismatch_item(
            session=session,
            plan=plan,
            item=item,
            reason=str(verification.get("reason") or "execution_result_mismatch"),
            details=verification.get("details") if isinstance(verification.get("details"), dict) else None,
        )
        return

    item.status = PaymentExecutionItemStatus.CONFIRMED.value
    item.onchain_status = OnchainExecutionStatus.CONFIRMED_ONCHAIN.value
    item.tx_hash = result.tx_hash
    item.explorer_url = result.explorer_url
    item.nonce = result.nonce
    item.submitted_at = result.sent_at
    item.confirmed_at = result.confirmed_at
    item.failure_reason = None
    item.pending_action = None
    item.receipt_json = {
        "tx_hash": result.tx_hash,
        "payment_ref": result.payment_ref,
        "gas_used": result.gas_used,
        "effective_gas_price": result.effective_gas_price,
        "events": result.decoded_events,
        "execution_item_id": result.execution_item_id,
    }
    session.add(item)
    if item.payment_split_id and item.payment_split_id in split_map:
        split = split_map[item.payment_split_id]
        split.status = PaymentSplitStatus.EXECUTED.value
        split.tx_hash = result.tx_hash
        split.explorer_url = result.explorer_url
        split.onchain_status = OnchainExecutionStatus.CONFIRMED_ONCHAIN.value
        split.execution_tx_sent_at = result.sent_at
        split.execution_tx_confirmed_at = result.confirmed_at
        split.gas_used = Decimal(str(result.gas_used)) if result.gas_used is not None else None
        session.add(split)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_item",
            entity_id=item.id,
            action="onchain_tx_confirmed",
            before_json=None,
            after_json={
                "tx_hash": result.tx_hash,
                "gas_used": result.gas_used,
                "effective_gas_price": result.effective_gas_price,
                "confirmed_at": result.confirmed_at.isoformat(),
            },
            trace_id=plan.trace_id,
        )
    )
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_item",
            entity_id=item.id,
            action="onchain_event_emitted",
            before_json=None,
            after_json={"tx_hash": result.tx_hash, "events": result.decoded_events},
            trace_id=plan.trace_id,
        )
    )
    session.commit()


def _apply_failed_item(
    *,
    session: Session,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    reason: str,
    split_map: dict[uuid.UUID, PaymentSplit],
) -> None:
    item.status = PaymentExecutionItemStatus.FAILED.value
    item.onchain_status = OnchainExecutionStatus.FAILED_ONCHAIN.value
    item.failure_reason = reason
    item.confirmed_at = datetime.now(timezone.utc)
    item.pending_action = None
    session.add(item)
    if item.payment_split_id and item.payment_split_id in split_map:
        split = split_map[item.payment_split_id]
        if split.status != PaymentSplitStatus.EXECUTED.value:
            split.status = PaymentSplitStatus.FAILED.value
            split.onchain_status = OnchainExecutionStatus.FAILED_ONCHAIN.value
            session.add(split)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_item",
            entity_id=item.id,
            action="onchain_tx_failed",
            before_json=None,
            after_json={"tx_hash": item.tx_hash, "error": reason},
            trace_id=plan.trace_id,
        )
    )
    session.commit()


def _apply_duplicate_item(
    *,
    session: Session,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    reason: str,
    split_map: dict[uuid.UUID, PaymentSplit],
) -> None:
    now = datetime.now(timezone.utc)
    item.status = PaymentExecutionItemStatus.CONFIRMED.value
    item.onchain_status = OnchainExecutionStatus.CONFIRMED_ONCHAIN.value
    item.confirmed_at = now
    item.failure_reason = None
    item.pending_action = None
    receipt = item.receipt_json if isinstance(item.receipt_json, dict) else {}
    receipt["execution_item_id"] = _uuid_to_bytes32_hex(item.id)
    receipt["duplicate_protection"] = {
        "detected": True,
        "reason": reason,
        "status": "already_executed_onchain",
    }
    item.receipt_json = receipt
    session.add(item)
    if item.payment_split_id and item.payment_split_id in split_map:
        split = split_map[item.payment_split_id]
        if split.status != PaymentSplitStatus.EXECUTED.value:
            split.status = PaymentSplitStatus.EXECUTED.value
        split.onchain_status = OnchainExecutionStatus.CONFIRMED_ONCHAIN.value
        split.execution_tx_confirmed_at = split.execution_tx_confirmed_at or now
        session.add(split)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_item",
            entity_id=item.id,
            action="onchain_duplicate_rejected",
            before_json=None,
            after_json={
                "tx_hash": item.tx_hash,
                "execution_item_id": _uuid_to_bytes32_hex(item.id),
                "reason": reason,
            },
            trace_id=plan.trace_id,
        )
    )
    session.commit()


def _apply_receipt_mismatch_item(
    *,
    session: Session,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    reason: str,
    details: dict[str, Any] | None,
) -> None:
    now = datetime.now(timezone.utc)
    before_json = {
        "status": item.status,
        "onchain_status": item.onchain_status,
        "tx_hash": item.tx_hash,
    }
    if item.status not in {PaymentExecutionItemStatus.CONFIRMED.value, PaymentExecutionItemStatus.FAILED.value}:
        item.status = PaymentExecutionItemStatus.SUBMITTED.value if item.tx_hash else PaymentExecutionItemStatus.SUBMITTING.value
    if item.onchain_status in {None, OnchainExecutionStatus.PENDING_SUBMISSION.value}:
        item.onchain_status = OnchainExecutionStatus.SUBMITTED_ONCHAIN.value if item.tx_hash else OnchainExecutionStatus.PENDING_SUBMISSION.value
    item.failure_reason = f"receipt_match_failed: {reason}"
    item.pending_action = "sync_receipt" if item.tx_hash else _resolve_pending_action_from_mode(plan.confirm_execution_mode)
    receipt = dict(item.receipt_json or {}) if isinstance(item.receipt_json, dict) else {}
    failures = receipt.get("receipt_match_failures")
    history = failures if isinstance(failures, list) else []
    history.append(
        {
            "at": now.isoformat(),
            "reason": reason,
            "details": details or {},
        }
    )
    receipt["receipt_match_failures"] = history[-10:]
    item.receipt_json = receipt
    session.add(item)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_item",
            entity_id=item.id,
            action="onchain_receipt_mismatch",
            before_json=before_json,
            after_json={
                "status": item.status,
                "onchain_status": item.onchain_status,
                "tx_hash": item.tx_hash,
                "reason": reason,
                "details": details or {},
            },
            trace_id=plan.trace_id,
        )
    )
    session.commit()


def _validate_receipt_match_for_execution_item(
    *,
    w3: Web3,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    tx: Any,
    receipt: Any,
) -> dict[str, Any]:
    settings = get_settings()
    expected_chain_id = int(plan.payment_order.chain_id or settings.hashkey_chain_id)
    actual_chain_id = int(w3.eth.chain_id)
    if actual_chain_id != expected_chain_id:
        return {
            "ok": False,
            "reason": "CHAIN_ID_MISMATCH",
            "details": {"expected_chain_id": expected_chain_id, "actual_chain_id": actual_chain_id},
        }

    expected_contract = plan.payment_order.contract_address or settings.hashkey_payment_executor_address
    expected_token = plan.payment_order.token_address or settings.hashkey_payment_token_address
    if not expected_contract or not Web3.is_address(expected_contract):
        return {
            "ok": False,
            "reason": "MISSING_OR_INVALID_CONTRACT_ADDRESS",
            "details": {"expected_contract": expected_contract},
        }
    if not expected_token or not Web3.is_address(expected_token):
        return {
            "ok": False,
            "reason": "MISSING_OR_INVALID_TOKEN_ADDRESS",
            "details": {"expected_token": expected_token},
        }

    tx_to = getattr(tx, "to", None)
    tx_input = _normalize_hex_data(getattr(tx, "input", None) or getattr(tx, "data", None))
    direct_contract_target = _same_evm_address(tx_to, expected_contract)

    if plan.confirm_execution_mode in {"operator", "user_wallet"}:
        if not direct_contract_target:
            return {
                "ok": False,
                "reason": "TX_TARGET_MISMATCH",
                "details": {"expected_to": expected_contract, "actual_to": tx_to},
            }
        if not tx_input:
            return {
                "ok": False,
                "reason": "TX_CALLDATA_MISSING",
                "details": {"expected_contract": expected_contract, "actual_to": tx_to},
            }
        decoded_call = _decode_execute_payment_call_data(
            w3=w3,
            contract_address=expected_contract,
            call_data=tx_input,
        )
        if decoded_call is None:
            return {
                "ok": False,
                "reason": "TX_CALLDATA_UNDECODABLE",
                "details": {"expected_function": "executePayment", "actual_to": tx_to},
            }
        call_mismatches = _validate_decoded_call_against_item(
            plan=plan,
            item=item,
            decoded_call=decoded_call,
            expected_token=expected_token,
            token_decimals=settings.hashkey_payment_token_decimals,
        )
        if call_mismatches:
            return {
                "ok": False,
                "reason": "TX_CALLDATA_FIELDS_MISMATCH",
                "details": {"mismatches": call_mismatches},
            }
    elif plan.confirm_execution_mode == "safe":
        safe_address = settings.hashkey_safe_address
        safe_target_ok = bool(safe_address and _same_evm_address(tx_to, safe_address))
        if not (safe_target_ok or direct_contract_target):
            return {
                "ok": False,
                "reason": "TX_TARGET_MISMATCH",
                "details": {
                    "expected_to": expected_contract,
                    "safe_address": safe_address,
                    "actual_to": tx_to,
                },
            }
        if direct_contract_target and tx_input:
            decoded_call = _decode_execute_payment_call_data(
                w3=w3,
                contract_address=expected_contract,
                call_data=tx_input,
            )
            if decoded_call is None:
                return {
                    "ok": False,
                    "reason": "TX_CALLDATA_UNDECODABLE",
                    "details": {"expected_function": "executePayment", "actual_to": tx_to},
                }
            call_mismatches = _validate_decoded_call_against_item(
                plan=plan,
                item=item,
                decoded_call=decoded_call,
                expected_token=expected_token,
                token_decimals=settings.hashkey_payment_token_decimals,
            )
            if call_mismatches:
                return {
                    "ok": False,
                    "reason": "TX_CALLDATA_FIELDS_MISMATCH",
                    "details": {"mismatches": call_mismatches},
                }

    decoded_events = _decode_payment_events_from_receipt(
        w3=w3,
        contract_address=expected_contract,
        receipt=receipt,
    )
    matched_event = _find_matching_payment_event_for_item(
        events=decoded_events,
        execution_item_id=item.id,
    )
    if matched_event is None:
        return {
            "ok": False,
            "reason": "EVENT_EXECUTION_ITEM_MISMATCH",
            "details": {
                "expected_execution_item_id": _uuid_to_bytes32_hex(item.id),
                "decoded_execution_item_ids": [event.get("execution_item_id") for event in decoded_events],
            },
            "decoded_events": decoded_events,
        }

    mismatches = _validate_matched_event_against_item(
        plan=plan,
        item=item,
        matched_event=matched_event,
        expected_token=expected_token,
        token_decimals=settings.hashkey_payment_token_decimals,
    )
    if mismatches:
        return {
            "ok": False,
            "reason": "EVENT_BUSINESS_FIELDS_MISMATCH",
            "details": {"mismatches": mismatches},
            "decoded_events": decoded_events,
            "matched_event": matched_event,
        }

    return {
        "ok": True,
        "decoded_events": decoded_events,
        "matched_event": matched_event,
    }


def _validate_execution_result_match_for_item(
    *,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    result: HashKeyExecutionResult,
) -> dict[str, Any]:
    settings = get_settings()
    expected_chain_id = int(plan.payment_order.chain_id or settings.hashkey_chain_id)
    expected_contract = plan.payment_order.contract_address or settings.hashkey_payment_executor_address
    expected_token = plan.payment_order.token_address or settings.hashkey_payment_token_address
    expected_execution_item_id = _uuid_to_bytes32_hex(item.id)

    mismatches: list[dict[str, Any]] = []
    if int(result.chain_id) != expected_chain_id:
        mismatches.append(
            {
                "field": "chain_id",
                "expected": expected_chain_id,
                "actual": int(result.chain_id),
            }
        )
    if expected_contract and not _same_evm_address(result.contract_address, expected_contract):
        mismatches.append(
            {
                "field": "contract_address",
                "expected": expected_contract,
                "actual": result.contract_address,
            }
        )
    if expected_token and not _same_evm_address(result.token_address, expected_token):
        mismatches.append(
            {
                "field": "token_address",
                "expected": expected_token,
                "actual": result.token_address,
            }
        )
    if result.execution_item_id and str(result.execution_item_id).lower() != expected_execution_item_id.lower():
        mismatches.append(
            {
                "field": "execution_item_id",
                "expected": expected_execution_item_id,
                "actual": result.execution_item_id,
            }
        )
    if item.tx_hash and item.tx_hash.lower() != str(result.tx_hash).lower():
        mismatches.append(
            {
                "field": "tx_hash",
                "expected": item.tx_hash,
                "actual": result.tx_hash,
            }
        )
    if mismatches:
        return {"ok": False, "reason": "EXECUTION_RESULT_HEADER_MISMATCH", "details": {"mismatches": mismatches}}

    matched_event = _find_matching_payment_event_for_item(
        events=result.decoded_events,
        execution_item_id=item.id,
    )
    if matched_event is None:
        return {
            "ok": False,
            "reason": "EXECUTION_RESULT_MISSING_MATCHED_EVENT",
            "details": {
                "expected_execution_item_id": expected_execution_item_id,
                "decoded_execution_item_ids": [event.get("execution_item_id") for event in result.decoded_events],
            },
        }

    event_mismatches = _validate_matched_event_against_item(
        plan=plan,
        item=item,
        matched_event=matched_event,
        expected_token=expected_token,
        token_decimals=settings.hashkey_payment_token_decimals,
    )
    if event_mismatches:
        return {
            "ok": False,
            "reason": "EXECUTION_RESULT_EVENT_MISMATCH",
            "details": {"mismatches": event_mismatches},
        }
    return {"ok": True}


def _find_matching_payment_event_for_item(
    *,
    events: list[dict[str, Any]],
    execution_item_id: uuid.UUID,
) -> dict[str, Any] | None:
    expected_execution_item_id = _uuid_to_bytes32_hex(execution_item_id).lower()
    for event in events:
        event_item_id = str(event.get("execution_item_id") or "").lower()
        if event_item_id == expected_execution_item_id:
            return event
    return None


def _validate_matched_event_against_item(
    *,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    matched_event: dict[str, Any],
    expected_token: str | None,
    token_decimals: int,
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    expected_order_id = _uuid_to_bytes32_hex(plan.payment_order.id)
    if str(matched_event.get("order_id") or "").lower() != expected_order_id.lower():
        mismatches.append(
            {
                "field": "order_id",
                "expected": expected_order_id,
                "actual": matched_event.get("order_id"),
            }
        )
    if expected_token and not _same_evm_address(matched_event.get("token"), expected_token):
        mismatches.append(
            {
                "field": "token",
                "expected": expected_token,
                "actual": matched_event.get("token"),
            }
        )
    if not _same_evm_address(matched_event.get("beneficiary"), item.beneficiary_address):
        mismatches.append(
            {
                "field": "beneficiary",
                "expected": item.beneficiary_address,
                "actual": matched_event.get("beneficiary"),
            }
        )
    expected_amount_units = _to_token_units(
        amount=Decimal(item.amount),
        token_decimals=token_decimals,
    )
    actual_amount_units = (
        int(matched_event.get("amount"))
        if matched_event.get("amount") is not None
        else None
    )
    if actual_amount_units != expected_amount_units:
        mismatches.append(
            {
                "field": "amount",
                "expected": expected_amount_units,
                "actual": actual_amount_units,
            }
        )
    expected_split_index = int(item.sequence)
    actual_split_index = (
        int(matched_event.get("split_index"))
        if matched_event.get("split_index") is not None
        else None
    )
    if actual_split_index != expected_split_index:
        mismatches.append(
            {
                "field": "split_index",
                "expected": expected_split_index,
                "actual": actual_split_index,
            }
        )
    expected_split_count = max(len(plan.items), 1)
    actual_split_count = (
        int(matched_event.get("split_count"))
        if matched_event.get("split_count") is not None
        else None
    )
    if actual_split_count != expected_split_count:
        mismatches.append(
            {
                "field": "split_count",
                "expected": expected_split_count,
                "actual": actual_split_count,
            }
        )
    expected_reference = str(plan.reference)
    actual_reference = str(matched_event.get("reference") or "")
    if actual_reference != expected_reference:
        mismatches.append(
            {
                "field": "reference",
                "expected": expected_reference,
                "actual": actual_reference,
            }
        )
    return mismatches


def _decode_execute_payment_call_data(
    *,
    w3: Web3,
    contract_address: str,
    call_data: str | None,
) -> dict[str, Any] | None:
    normalized = _normalize_hex_data(call_data)
    if not normalized:
        return None
    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=PAYMENT_EXECUTOR_ABI,
        )
        function_obj, args = contract.decode_function_input(normalized)
    except Exception:
        return None

    fn_name = getattr(function_obj, "fn_name", "")
    if fn_name != "executePayment":
        return None
    arg_map = dict(args or {})
    return {
        "execution_item_id": _normalize_bytes32_hex(arg_map.get("executionItemId")),
        "order_id": _normalize_bytes32_hex(arg_map.get("orderId")),
        "token": arg_map.get("token"),
        "beneficiary": arg_map.get("beneficiary"),
        "amount": int(arg_map.get("amount")) if arg_map.get("amount") is not None else None,
        "reference": str(arg_map.get("reference") or ""),
        "split_index": int(arg_map.get("splitIndex")) if arg_map.get("splitIndex") is not None else None,
        "split_count": int(arg_map.get("splitCount")) if arg_map.get("splitCount") is not None else None,
    }


def _validate_decoded_call_against_item(
    *,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    decoded_call: dict[str, Any],
    expected_token: str | None,
    token_decimals: int,
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    expected_execution_item_id = _uuid_to_bytes32_hex(item.id)
    expected_order_id = _uuid_to_bytes32_hex(plan.payment_order.id)

    if str(decoded_call.get("execution_item_id") or "").lower() != expected_execution_item_id.lower():
        mismatches.append(
            {
                "field": "execution_item_id",
                "expected": expected_execution_item_id,
                "actual": decoded_call.get("execution_item_id"),
            }
        )
    if str(decoded_call.get("order_id") or "").lower() != expected_order_id.lower():
        mismatches.append(
            {
                "field": "order_id",
                "expected": expected_order_id,
                "actual": decoded_call.get("order_id"),
            }
        )
    if expected_token and not _same_evm_address(decoded_call.get("token"), expected_token):
        mismatches.append(
            {
                "field": "token",
                "expected": expected_token,
                "actual": decoded_call.get("token"),
            }
        )
    if not _same_evm_address(decoded_call.get("beneficiary"), item.beneficiary_address):
        mismatches.append(
            {
                "field": "beneficiary",
                "expected": item.beneficiary_address,
                "actual": decoded_call.get("beneficiary"),
            }
        )
    expected_amount_units = _to_token_units(amount=Decimal(item.amount), token_decimals=token_decimals)
    if decoded_call.get("amount") != expected_amount_units:
        mismatches.append(
            {
                "field": "amount",
                "expected": expected_amount_units,
                "actual": decoded_call.get("amount"),
            }
        )
    expected_split_index = int(item.sequence)
    if decoded_call.get("split_index") != expected_split_index:
        mismatches.append(
            {
                "field": "split_index",
                "expected": expected_split_index,
                "actual": decoded_call.get("split_index"),
            }
        )
    expected_split_count = max(len(plan.items), 1)
    if decoded_call.get("split_count") != expected_split_count:
        mismatches.append(
            {
                "field": "split_count",
                "expected": expected_split_count,
                "actual": decoded_call.get("split_count"),
            }
        )
    expected_reference = str(plan.reference)
    if str(decoded_call.get("reference") or "") != expected_reference:
        mismatches.append(
            {
                "field": "reference",
                "expected": expected_reference,
                "actual": decoded_call.get("reference"),
            }
        )
    return mismatches


def _same_evm_address(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    if not Web3.is_address(a) or not Web3.is_address(b):
        return str(a).lower() == str(b).lower()
    return Web3.to_checksum_address(a) == Web3.to_checksum_address(b)


def _normalize_hex_data(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if hasattr(value, "hex"):
        try:
            raw = value.hex()
            if isinstance(raw, str):
                return raw if raw.startswith("0x") else f"0x{raw}"
        except Exception:
            pass
    text = str(value).strip()
    if not text:
        return None
    normalized = text if text.startswith("0x") else f"0x{text}"
    return normalized.lower()


def _normalize_bytes32_hex(value: Any) -> str | None:
    normalized = _normalize_hex_data(value)
    if not normalized:
        return None
    if len(normalized) == 66:
        return normalized
    if len(normalized) < 66:
        return "0x" + normalized[2:].rjust(64, "0")
    return normalized[:66]


def _aggregate_batch_and_order_status(*, session: Session, plan: _PlanResult) -> None:
    _refresh_plan_entities(session=session, plan=plan)
    confirmed_count, failed_count, pending_count = _count_batch_items(plan.items)
    now = datetime.now(timezone.utc)

    if confirmed_count == len(plan.items) and pending_count == 0:
        plan.batch.status = PaymentExecutionBatchStatus.CONFIRMED.value
        plan.payment_order.status = PaymentOrderStatus.EXECUTED.value
        plan.payment_order.onchain_status = OnchainExecutionStatus.CONFIRMED_ONCHAIN.value
        plan.command.final_status = CommandExecutionStatus.EXECUTED.value
        batch_action = "execution_batch_confirmed"
        order_action = "payment_order_executed"
    elif confirmed_count > 0 and failed_count > 0:
        plan.batch.status = PaymentExecutionBatchStatus.PARTIALLY_CONFIRMED.value
        plan.payment_order.status = PaymentOrderStatus.PARTIALLY_EXECUTED.value
        plan.payment_order.onchain_status = OnchainExecutionStatus.PARTIALLY_CONFIRMED_ONCHAIN.value
        plan.command.final_status = CommandExecutionStatus.EXECUTED.value
        batch_action = "execution_batch_partially_confirmed"
        order_action = "payment_order_partially_executed"
    elif failed_count > 0 and confirmed_count == 0 and pending_count == 0:
        plan.batch.status = PaymentExecutionBatchStatus.FAILED.value
        plan.payment_order.status = PaymentOrderStatus.FAILED.value
        plan.payment_order.onchain_status = OnchainExecutionStatus.FAILED_ONCHAIN.value
        plan.command.final_status = CommandExecutionStatus.FAILED.value
        batch_action = "execution_batch_failed"
        order_action = "payment_order_failed"
    else:
        plan.batch.status = PaymentExecutionBatchStatus.IN_PROGRESS.value
        batch_action = "execution_batch_in_progress"
        order_action = "payment_order_in_progress"

    plan.batch.finished_at = now if plan.batch.status in FINAL_BATCH_STATUSES else None

    tx_items = [item for item in plan.items if item.tx_hash]
    if len(tx_items) == 1:
        plan.payment_order.tx_hash = tx_items[0].tx_hash
        plan.payment_order.explorer_url = tx_items[0].explorer_url
    else:
        plan.payment_order.tx_hash = None
        plan.payment_order.explorer_url = None

    submitted_times = [item.submitted_at for item in plan.items if item.submitted_at]
    confirmed_times = [item.confirmed_at for item in plan.items if item.confirmed_at]
    if submitted_times:
        plan.payment_order.execution_tx_sent_at = min(submitted_times)
    if confirmed_times:
        plan.payment_order.execution_tx_confirmed_at = max(confirmed_times)

    total_gas = 0
    payload_txs: list[dict[str, Any]] = []
    for item in plan.items:
        receipt = item.receipt_json if isinstance(item.receipt_json, dict) else {}
        gas_used = receipt.get("gas_used")
        if gas_used is not None:
            total_gas += int(gas_used)
        payload_txs.append(
            {
                "execution_item_id": str(item.id),
                "onchain_execution_item_id": _uuid_to_bytes32_hex(item.id),
                "sequence": item.sequence,
                "status": item.status,
                "tx_hash": item.tx_hash,
                "explorer_url": item.explorer_url,
                "nonce": item.nonce,
                "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
                "confirmed_at": item.confirmed_at.isoformat() if item.confirmed_at else None,
                "failure_reason": item.failure_reason,
                "onchain_status": item.onchain_status,
                "receipt": receipt,
            }
        )
    plan.payment_order.gas_used = Decimal(str(total_gas)) if total_gas > 0 else None
    plan.payment_order.onchain_payload_json = {
        "tx_count": len(payload_txs),
        "confirmed_items": confirmed_count,
        "failed_items": failed_count,
        "pending_items": pending_count,
        "txs": payload_txs,
    }
    metadata_json = dict(plan.payment_order.metadata_json or {})
    metadata_json["execution_batch_id"] = str(plan.batch.id)
    metadata_json["execution_batch_status"] = plan.batch.status
    plan.payment_order.metadata_json = metadata_json
    bind_balance_lock_to_payment(session=session, payment_order=plan.payment_order)
    settle_balance_lock_for_payment(
        session=session,
        payment_order=plan.payment_order,
        actor_user_id=plan.actor_user_id,
        trace_id=plan.trace_id,
    )

    _append_confirmation_meta(
        command=plan.command,
        status=plan.command.final_status,
        trace_id=plan.trace_id,
        note=None,
        locale=None,
        payment_order_id=plan.payment_order.id,
        execution_backend=plan.execution_backend,
        execution_route=plan.confirm_execution_mode,
        idempotency_key=plan.batch.idempotency_key,
    )

    session.add(plan.batch)
    session.add(plan.payment_order)
    session.add(plan.command)
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_execution_batch",
            entity_id=plan.batch.id,
            action=batch_action,
            before_json=None,
            after_json={
                "status": plan.batch.status,
                "confirmed_items": confirmed_count,
                "failed_items": failed_count,
                "pending_items": pending_count,
            },
            trace_id=plan.trace_id,
        )
    )
    session.add(
        _build_audit_log(
            actor_user_id=plan.actor_user_id,
            entity_type="payment_order",
            entity_id=plan.payment_order.id,
            action=order_action,
            before_json=None,
            after_json={
                "status": plan.payment_order.status,
                "onchain_status": plan.payment_order.onchain_status,
            },
            trace_id=plan.trace_id,
        )
    )
    session.commit()


def _build_confirm_response_from_plan(
    *,
    plan: _PlanResult,
    override_status: str | None = None,
) -> ConfirmResponse:
    execution_items = [_build_execution_item_result(item) for item in plan.items]
    split_results = [_build_split_result(split) for split in plan.split_rows]
    execution = _build_execution_result(plan=plan)

    status = override_status or _map_batch_status_to_response_status(plan.batch.status)
    next_action = _resolve_confirm_next_action(
        confirm_execution_mode=plan.confirm_execution_mode,
        batch_status=plan.batch.status,
    )
    preview_summary = _build_confirm_preview_summary(plan=plan)
    technical_details = _build_confirm_technical_details(plan=plan)

    return ConfirmResponse(
        status=status,
        command_id=plan.command.id,
        execution_mode=plan.confirm_execution_mode,
        next_action=next_action,
        mode_specific_cta=_resolve_mode_specific_cta(plan.confirm_execution_mode),
        preview_summary=preview_summary,
        technical_details=technical_details,
        payment_order_id=plan.payment_order.id,
        execution_batch_id=plan.batch.id,
        payment_status=plan.payment_order.status,
        execution_status=plan.batch.status,
        execution=execution,
        splits=split_results,
        execution_items=execution_items,
        unsigned_transactions=None,
        safe_proposal=None,
        risk=ConfirmRiskResult(**plan.risk_preview) if plan.risk_preview else None,
        audit_trace_id=plan.trace_id,
        message=_build_confirm_message(plan=plan, status=status),
    )


def _build_idempotent_response(
    *,
    session: Session,
    command_id: uuid.UUID,
    batch_id: uuid.UUID,
    execution_mode: str,
    trace_id: str,
    message: str,
) -> ConfirmResponse:
    batch = session.get(PaymentExecutionBatch, batch_id)
    if batch is None:
        return _validation_error(
            command_id=command_id,
            trace_id=trace_id,
            execution_mode=execution_mode,
            message="执行批次不存在。 (Execution batch not found.)",
        )
    payment_order = session.get(PaymentOrder, batch.payment_order_id)
    command = session.get(CommandExecution, command_id)
    if payment_order is None or command is None:
        return _validation_error(
            command_id=command_id,
            trace_id=trace_id,
            execution_mode=execution_mode,
            message="执行数据不完整。 (Execution entities are incomplete.)",
        )
    split_rows = session.execute(
        select(PaymentSplit)
        .where(PaymentSplit.payment_order_id == payment_order.id)
        .order_by(PaymentSplit.sequence.asc())
    ).scalars().all()
    items = session.execute(
        select(PaymentExecutionItem)
        .where(PaymentExecutionItem.execution_batch_id == batch.id)
        .order_by(PaymentExecutionItem.sequence.asc(), PaymentExecutionItem.created_at.asc())
    ).scalars().all()
    beneficiary = session.get(Beneficiary, payment_order.beneficiary_id)
    if beneficiary is None:
        return _validation_error(
            command_id=command_id,
            trace_id=trace_id,
            execution_mode=execution_mode,
            message="受益人不存在。 (Beneficiary not found.)",
        )
    plan = _PlanResult(
        command=command,
        payment_order=payment_order,
        split_rows=split_rows,
        batch=batch,
        items=items,
        trace_id=trace_id,
        risk_preview=_extract_or_evaluate_risk(command),
        execution_backend=_normalize_execution_backend(get_settings().payment_execution_backend),
        execution_mode=payment_order.execution_mode,
        confirm_execution_mode=payment_order.execution_route or execution_mode,
        actor_user_id=batch.requested_by_user_id,
        beneficiary=beneficiary,
        reference=payment_order.reference,
    )
    response = _build_confirm_response_from_plan(plan=plan, override_status="ok")
    response.message = message
    if plan.confirm_execution_mode == "user_wallet":
        response.unsigned_transactions = _build_unsigned_transactions_from_items(plan=plan)
    if plan.confirm_execution_mode == "safe":
        response.safe_proposal = {
            "safe_address": get_settings().hashkey_safe_address,
            "network": get_settings().hashkey_network,
            "chain_id": get_settings().hashkey_chain_id,
            "proposal_status": "prepared",
            "proposal_type": "safe_transaction_proposal",
            "transactions": _build_unsigned_transactions_from_items(plan=plan),
        }
    return response


def _refresh_plan_entities(*, session: Session, plan: _PlanResult) -> None:
    plan.command = session.get(CommandExecution, plan.command.id) or plan.command
    plan.payment_order = session.get(PaymentOrder, plan.payment_order.id) or plan.payment_order
    plan.batch = session.get(PaymentExecutionBatch, plan.batch.id) or plan.batch
    plan.split_rows = session.execute(
        select(PaymentSplit)
        .where(PaymentSplit.payment_order_id == plan.payment_order.id)
        .order_by(PaymentSplit.sequence.asc())
    ).scalars().all()
    plan.items = session.execute(
        select(PaymentExecutionItem)
        .where(PaymentExecutionItem.execution_batch_id == plan.batch.id)
        .order_by(PaymentExecutionItem.sequence.asc(), PaymentExecutionItem.created_at.asc())
    ).scalars().all()


def _resolve_idempotency_key(
    *,
    request: ConfirmRequest,
    command: CommandExecution,
    confirm_execution_mode: str,
) -> str:
    raw = (request.idempotency_key or "").strip()
    if raw:
        return raw[:120]
    return f"confirm:{command.id}:{confirm_execution_mode}"


def _build_unsigned_transactions_from_items(*, plan: _PlanResult) -> list[dict[str, Any]]:
    settings = get_settings()
    txs: list[dict[str, Any]] = []
    split_count = max(len(plan.items), 1)
    for item in plan.items:
        to = plan.payment_order.contract_address or settings.hashkey_payment_executor_address
        token = plan.payment_order.token_address or settings.hashkey_payment_token_address
        data = _encode_execute_payment_call_data(
            contract_address=to,
            token_address=token,
            beneficiary_address=item.beneficiary_address,
            amount=Decimal(item.amount),
            reference=plan.payment_order.reference,
            order_id=plan.payment_order.id,
            execution_item_id=item.id,
            split_index=item.sequence,
            split_count=split_count,
            token_decimals=settings.hashkey_payment_token_decimals,
        )
        txs.append(
            {
                "execution_item_id": str(item.id),
                "onchain_execution_item_id": _uuid_to_bytes32_hex(item.id),
                "to": to,
                "value": "0x0",
                "data": data,
                "chain_id": int(plan.payment_order.chain_id or settings.hashkey_chain_id),
                "network": plan.payment_order.network or settings.hashkey_network,
                "explorer_base": settings.hashkey_explorer_base,
                "token_address": token,
                "beneficiary_address": item.beneficiary_address,
                "amount": str(item.amount),
                "currency": item.currency,
                "reference": plan.payment_order.reference,
                "split_index": int(item.sequence),
                "split_count": int(split_count),
                "proposal_type": "contract_call",
                "description": "PaymentExecutor.executePayment",
            }
        )
    return txs


def _build_execution_item_result(item: PaymentExecutionItem) -> ConfirmExecutionItemResult:
    return ConfirmExecutionItemResult(
        execution_item_id=item.id,
        onchain_execution_item_id=_uuid_to_bytes32_hex(item.id),
        sequence=item.sequence,
        amount=float(item.amount),
        currency=item.currency,
        status=item.status,
        tx_hash=item.tx_hash,
        explorer_url=item.explorer_url,
        nonce=item.nonce,
        onchain_status=item.onchain_status,
        submitted_at=item.submitted_at,
        confirmed_at=item.confirmed_at,
        failure_reason=item.failure_reason,
    )


def _build_split_result(split: PaymentSplit) -> ConfirmSplitResult:
    return ConfirmSplitResult(
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
        payment_ref=None,
    )


def _build_execution_result(*, plan: _PlanResult) -> MockExecutionResult:
    confirmed_items = [item for item in plan.items if item.status == PaymentExecutionItemStatus.CONFIRMED.value]
    top_item = confirmed_items[-1] if confirmed_items else (plan.items[-1] if plan.items else None)
    top_receipt = top_item.receipt_json if top_item and isinstance(top_item.receipt_json, dict) else {}
    decoded_events = top_receipt.get("events") if isinstance(top_receipt.get("events"), list) else []
    split_executions = [_build_split_result(split).model_dump(mode="json") for split in plan.split_rows]
    return MockExecutionResult(
        mode="onchain" if plan.payment_order.execution_mode == ExecutionMode.ONCHAIN.value else "mock",
        executed=plan.payment_order.status in {PaymentOrderStatus.EXECUTED.value, PaymentOrderStatus.PARTIALLY_EXECUTED.value},
        transaction_ref=None,
        network=plan.payment_order.network,
        chain_id=plan.payment_order.chain_id,
        tx_hash=plan.payment_order.tx_hash or (top_item.tx_hash if top_item else None),
        explorer_url=plan.payment_order.explorer_url or (top_item.explorer_url if top_item else None),
        onchain_status=plan.payment_order.onchain_status,
        contract_address=plan.payment_order.contract_address,
        token_address=plan.payment_order.token_address,
        gas_used=int(plan.payment_order.gas_used) if plan.payment_order.gas_used is not None else None,
        effective_gas_price=(
            int(plan.payment_order.effective_gas_price)
            if plan.payment_order.effective_gas_price is not None
            else None
        ),
        payment_ref=top_receipt.get("payment_ref"),
        decoded_events=decoded_events,
        split_executions=split_executions,
        executed_at=plan.payment_order.execution_tx_confirmed_at,
        message=_build_execution_message(plan=plan),
    )


def _build_confirm_message(*, plan: _PlanResult, status: str) -> str:
    if status == "failed":
        return "链上执行失败，支付单已标记 failed。 (Onchain execution failed and payment order is marked as failed.)"
    if plan.payment_order.status == PaymentOrderStatus.PARTIALLY_EXECUTED.value:
        return "支付已部分执行，请检查失败分笔。 (Payment partially executed; inspect failed split items.)"
    if (
        plan.confirm_execution_mode == "user_wallet"
        and plan.batch.status not in FINAL_BATCH_STATUSES
    ):
        return "已进入 user_wallet 模式，等待钱包签名。 (user_wallet mode prepared; waiting for wallet signature.)"
    if (
        plan.confirm_execution_mode == "safe"
        and plan.batch.status not in FINAL_BATCH_STATUSES
    ):
        return "已进入 safe 模式，等待 Safe 审批。 (safe mode prepared; waiting for Safe approval.)"
    if plan.payment_order.execution_mode == ExecutionMode.ONCHAIN.value:
        return "已完成 HashKey Testnet 链上执行。 (Payment confirmation completed with HashKey testnet execution.)"
    return "支付确认已完成（模拟执行）。 (Payment confirmation completed in mock execution mode.)"


def _build_execution_message(*, plan: _PlanResult) -> str:
    if plan.payment_order.status == PaymentOrderStatus.EXECUTED.value:
        return "链上执行已确认。 (Onchain execution confirmed.)"
    if plan.payment_order.status == PaymentOrderStatus.PARTIALLY_EXECUTED.value:
        return "链上部分确认，存在失败分笔。 (Partially confirmed onchain with failed split item(s).)"
    if plan.payment_order.status == PaymentOrderStatus.FAILED.value:
        return "链上执行失败。 (Onchain execution failed.)"
    if plan.payment_order.execution_mode == ExecutionMode.MOCK.value:
        return "模拟执行已完成。 (Mock execution completed.)"
    return "执行计划已创建。 (Execution plan created.)"


def _resolve_mode_specific_cta(confirm_execution_mode: str) -> str:
    if confirm_execution_mode == "user_wallet":
        return "Generate unsigned transaction(s)"
    if confirm_execution_mode == "safe":
        return "Generate Safe proposal"
    return "Confirm & Submit"


def _resolve_pending_action_from_mode(confirm_execution_mode: str) -> str:
    if confirm_execution_mode == "user_wallet":
        return "generate_unsigned_tx"
    if confirm_execution_mode == "safe":
        return "generate_safe_proposal"
    return "confirm_now"


def _resolve_confirm_next_action(*, confirm_execution_mode: str, batch_status: str) -> str:
    if batch_status in FINAL_BATCH_STATUSES:
        return "none"
    if batch_status == PaymentExecutionBatchStatus.PARTIALLY_CONFIRMED.value:
        return "sync_receipt"
    return _resolve_pending_action_from_mode(confirm_execution_mode)


def _build_confirm_preview_summary(*, plan: _PlanResult) -> dict[str, Any]:
    risk_level = None
    if isinstance(plan.risk_preview, dict):
        risk_level = plan.risk_preview.get("risk_level")
    estimated_fee = None
    metadata_json = plan.payment_order.metadata_json if isinstance(plan.payment_order.metadata_json, dict) else {}
    quote_fee = metadata_json.get("estimated_fee")
    if quote_fee is not None:
        try:
            estimated_fee = float(quote_fee)
        except Exception:
            estimated_fee = None
    amount = float(plan.payment_order.amount)
    net_transfer = amount - estimated_fee if estimated_fee is not None else amount
    return {
        "recipient": plan.beneficiary.name,
        "amount": amount,
        "currency": plan.payment_order.currency,
        "risk_level": risk_level,
        "estimated_fee": estimated_fee,
        "net_transfer": max(net_transfer, 0.0),
    }


def _build_confirm_technical_details(*, plan: _PlanResult) -> dict[str, Any]:
    execution_items = [
        {
            "execution_item_id": str(item.id),
            "sequence": item.sequence,
            "status": item.status,
            "onchain_status": item.onchain_status,
            "pending_action": item.pending_action,
            "tx_hash": item.tx_hash,
            "explorer_url": item.explorer_url,
        }
        for item in plan.items
    ]
    timeline = [
        {
            "title": "Execution batch status",
            "action": "execution_batch_status",
            "timestamp": plan.batch.started_at.isoformat() if plan.batch.started_at else None,
            "details": {
                "status": plan.batch.status,
                "payment_status": plan.payment_order.status,
            },
        }
    ]
    return {
        "payment_order_id": str(plan.payment_order.id),
        "execution_batch_id": str(plan.batch.id),
        "execution_items": execution_items,
        "timeline": timeline,
    }


def _map_batch_status_to_response_status(status: str) -> str:
    if status in {PaymentExecutionBatchStatus.CONFIRMED.value, PaymentExecutionBatchStatus.PARTIALLY_CONFIRMED.value}:
        return "ok"
    if status == PaymentExecutionBatchStatus.FAILED.value:
        return "failed"
    return "ok"


def _count_batch_items(items: list[PaymentExecutionItem]) -> tuple[int, int, int]:
    confirmed = sum(1 for item in items if item.status == PaymentExecutionItemStatus.CONFIRMED.value)
    failed = sum(1 for item in items if item.status == PaymentExecutionItemStatus.FAILED.value)
    pending = len(items) - confirmed - failed
    return confirmed, failed, pending


def _extract_or_evaluate_risk(command: CommandExecution) -> dict[str, Any]:
    parsed = command.parsed_intent_json if isinstance(command.parsed_intent_json, dict) else {}
    fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {}
    try:
        return evaluate_payment_risk(fields)
    except Exception:
        return {"decision": "review", "risk_level": "medium", "reason_codes": ["RISK_REVIEW_REQUIRED"]}


def _is_settlement_bridge_command(command: CommandExecution) -> bool:
    parsed = command.parsed_intent_json if isinstance(command.parsed_intent_json, dict) else {}
    fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {}
    settlement_context = fields.get("settlement_context")
    return isinstance(settlement_context, dict) and bool(settlement_context.get("fiat_payment_intent_id"))


def _normalize_execution_backend(value: str | None) -> str:
    normalized = (value or "mock").strip().lower()
    if normalized in {"hashkey", "hashkey_testnet", "onchain"}:
        return "hashkey_testnet"
    return "mock"


def _normalize_confirm_execution_mode(value: str | None) -> str:
    normalized = (value or "operator").strip().lower()
    if normalized in CONFIRM_EXECUTION_MODES:
        return normalized
    return "operator"


def _validate_payment_fields(fields: dict[str, Any]) -> str | None:
    recipient = fields.get("recipient")
    amount = fields.get("amount")
    currency = fields.get("currency")
    if not recipient:
        return "缺少收款对象。 (Missing recipient.)"
    if amount is None:
        return "缺少付款金额。 (Missing amount.)"
    try:
        if Decimal(str(amount)) <= 0:
            return "付款金额必须大于 0。 (Amount must be greater than 0.)"
    except Exception:
        return "付款金额格式不正确。 (Invalid amount format.)"
    if not currency:
        return "缺少币种。 (Missing currency.)"
    return None


def _safe_split_count(value: Any) -> int:
    try:
        count = int(value) if value is not None else 1
    except Exception:
        return 1
    return max(count, 1)


def _create_payment_splits(
    *,
    session: Session,
    payment_order: PaymentOrder,
    split_count: int,
    amount: Decimal,
    currency: str,
    trace_id: str,
    actor_user_id: uuid.UUID,
    default_onchain_status: str | None = None,
) -> list[PaymentSplit]:
    unit = Decimal("0.01")
    base_amount = (amount / split_count).quantize(unit, rounding=ROUND_DOWN)
    split_rows: list[PaymentSplit] = []
    allocated = Decimal("0.00")
    for index in range(1, split_count + 1):
        split_amount = base_amount
        if index == split_count:
            split_amount = (amount - allocated).quantize(unit)
        allocated += split_amount
        split = PaymentSplit(
            id=uuid.uuid4(),
            payment_order_id=payment_order.id,
            sequence=index,
            amount=split_amount,
            currency=currency,
            status=PaymentSplitStatus.SCHEDULED.value,
            onchain_status=default_onchain_status,
        )
        session.add(split)
        session.flush()
        split_rows.append(split)
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="payment_split",
                entity_id=split.id,
                action="create",
                before_json=None,
                after_json={"sequence": index, "amount": float(split_amount), "status": split.status},
                trace_id=trace_id,
            )
        )
    return split_rows


def _build_confirm_trace_id(command: CommandExecution) -> str:
    base = command.trace_id or f"trace-cmd-{command.id.hex[:12]}"
    return f"{base}-confirm"


def _mark_command_failed(
    *,
    command: CommandExecution,
    trace_id: str,
    reason: str,
    note: str | None,
    execution_backend: str,
    execution_route: str,
    idempotency_key: str,
) -> None:
    _append_confirmation_meta(
        command=command,
        status=CommandExecutionStatus.FAILED.value,
        trace_id=trace_id,
        note=note,
        locale=None,
        reason=reason,
        execution_backend=execution_backend,
        execution_route=execution_route,
        idempotency_key=idempotency_key,
    )
    command.final_status = CommandExecutionStatus.FAILED.value


def _append_confirmation_meta(
    *,
    command: CommandExecution,
    status: str,
    trace_id: str,
    note: str | None,
    locale: str | None,
    reason: str | None = None,
    payment_order_id: uuid.UUID | None = None,
    execution_backend: str = "mock",
    execution_route: str = "operator",
    idempotency_key: str | None = None,
) -> None:
    payload = dict(command.parsed_intent_json or {})
    payload["confirmation"] = {
        "status": status,
        "trace_id": trace_id,
        "note": note,
        "locale": locale,
        "reason": reason,
        "payment_order_id": str(payment_order_id) if payment_order_id else None,
        "execution_backend": execution_backend,
        "execution_mode": _normalize_confirm_execution_mode(execution_route),
        "idempotency_key": idempotency_key,
    }
    command.parsed_intent_json = payload


def _build_audit_log(
    *,
    actor_user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    before_json: dict[str, Any] | None,
    after_json: dict[str, Any] | None,
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


def _safe_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _uuid_to_bytes32_hex(value: uuid.UUID) -> str:
    return "0x" + (value.bytes + b"\x00" * 16).hex()


def _normalize_tx_hash(value: str | None) -> str | None:
    if not value:
        return None
    tx_hash = value.strip()
    if not tx_hash:
        return None
    tx_hash = tx_hash.lower()
    if not tx_hash.startswith("0x"):
        tx_hash = f"0x{tx_hash}"
    if len(tx_hash) != 66:
        return None
    hex_payload = tx_hash[2:]
    try:
        int(hex_payload, 16)
    except ValueError:
        return None
    return tx_hash


def _build_tx_explorer_url(tx_hash: str) -> str:
    return f"{get_settings().hashkey_explorer_base.rstrip('/')}/tx/{tx_hash}"


def _find_execution_item(*, plan: _PlanResult, execution_item_id: uuid.UUID) -> PaymentExecutionItem | None:
    for item in plan.items:
        if item.id == execution_item_id:
            return item
    return None


def _load_plan_by_execution_item_id(
    *,
    session: Session,
    execution_item_id: uuid.UUID,
) -> tuple[_PlanResult, PaymentExecutionItem] | None:
    execution_item = session.get(PaymentExecutionItem, execution_item_id)
    if execution_item is None:
        return None
    batch = session.get(PaymentExecutionBatch, execution_item.execution_batch_id)
    if batch is None:
        return None
    payment_order = session.get(PaymentOrder, batch.payment_order_id)
    if payment_order is None:
        return None
    command = (
        session.get(CommandExecution, payment_order.source_command_id)
        if payment_order.source_command_id is not None
        else None
    )
    if command is None:
        return None
    beneficiary = session.get(Beneficiary, payment_order.beneficiary_id)
    if beneficiary is None:
        return None
    split_rows = session.execute(
        select(PaymentSplit)
        .where(PaymentSplit.payment_order_id == payment_order.id)
        .order_by(PaymentSplit.sequence.asc())
    ).scalars().all()
    items = session.execute(
        select(PaymentExecutionItem)
        .where(PaymentExecutionItem.execution_batch_id == batch.id)
        .order_by(PaymentExecutionItem.sequence.asc(), PaymentExecutionItem.created_at.asc())
    ).scalars().all()
    trace_id = str((batch.metadata_json or {}).get("trace_id") or _build_confirm_trace_id(command))
    plan = _PlanResult(
        command=command,
        payment_order=payment_order,
        split_rows=split_rows,
        batch=batch,
        items=items,
        trace_id=trace_id,
        risk_preview=_extract_or_evaluate_risk(command),
        execution_backend=_normalize_execution_backend(get_settings().payment_execution_backend),
        execution_mode=payment_order.execution_mode,
        confirm_execution_mode=payment_order.execution_route or batch.execution_mode or "operator",
        actor_user_id=batch.requested_by_user_id,
        beneficiary=beneficiary,
        reference=payment_order.reference,
    )
    item = _find_execution_item(plan=plan, execution_item_id=execution_item_id) or execution_item
    return plan, item


def _build_execution_item_action_response(
    *,
    plan: _PlanResult,
    item: PaymentExecutionItem,
    status: str,
    next_action: str,
    message: str,
    session: Session | None = None,
) -> ExecutionItemActionResponse:
    confirmed_items, failed_items, _ = _count_batch_items(plan.items)
    total_items = len(plan.items)
    timeline = _build_execution_item_timeline(
        session=session,
        trace_id=plan.trace_id,
        item_id=item.id,
    )
    return ExecutionItemActionResponse(
        status=status,
        execution_item_id=item.id,
        execution_batch_id=plan.batch.id,
        payment_order_id=plan.payment_order.id,
        execution_mode=plan.confirm_execution_mode,
        item_status=item.status,
        batch_status=plan.batch.status,
        payment_status=plan.payment_order.status,
        onchain_status=item.onchain_status,
        tx_hash=item.tx_hash,
        explorer_url=item.explorer_url,
        total_items=total_items,
        confirmed_items=confirmed_items,
        failed_items=failed_items,
        timeline=timeline,
        next_action=_normalize_action_response_next_action(next_action, plan.confirm_execution_mode),
        message=message,
    )


def _normalize_action_response_next_action(next_action: str, execution_mode: str) -> str:
    normalized = (next_action or "").strip().lower()
    if normalized in {"sync_receipt", "attach_tx", "none", "confirm_now", "generate_unsigned_tx", "generate_safe_proposal"}:
        return normalized
    if normalized in {"sign_in_wallet"}:
        return "generate_unsigned_tx"
    if normalized in {"approve_in_safe"}:
        return "generate_safe_proposal"
    return _resolve_pending_action_from_mode(execution_mode)


def _build_execution_item_timeline(
    *,
    session: Session | None,
    trace_id: str,
    item_id: uuid.UUID,
) -> list[dict[str, Any]]:
    if session is None:
        return []
    rows = session.execute(
        select(AuditLog)
        .where(
            AuditLog.trace_id == trace_id,
            AuditLog.entity_type == "payment_execution_item",
            AuditLog.entity_id == item_id,
        )
        .order_by(AuditLog.created_at.asc())
        .limit(20)
    ).scalars().all()
    return [
        {
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "title": row.action.replace("_", " "),
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id),
            "details": row.after_json if isinstance(row.after_json, dict) else {},
        }
        for row in rows
    ]


def _encode_execute_payment_call_data(
    *,
    contract_address: str | None,
    token_address: str | None,
    beneficiary_address: str,
    amount: Decimal,
    reference: str,
    order_id: uuid.UUID,
    execution_item_id: uuid.UUID,
    split_index: int,
    split_count: int,
    token_decimals: int,
) -> str | None:
    if not contract_address or not token_address:
        return None
    if not Web3.is_address(contract_address) or not Web3.is_address(token_address):
        return None
    if not Web3.is_address(beneficiary_address):
        return None
    try:
        contract = Web3().eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=PAYMENT_EXECUTOR_ABI,
        )
        amount_units = _to_token_units(amount=amount, token_decimals=token_decimals)
        function_call = contract.functions.executePayment(
            _uuid_to_bytes32_hex(execution_item_id),
            _uuid_to_bytes32_hex(order_id),
            Web3.to_checksum_address(token_address),
            Web3.to_checksum_address(beneficiary_address),
            int(amount_units),
            str(reference),
            int(split_index),
            int(split_count),
        )
        return function_call._encode_transaction_data()
    except Exception:
        return None


def _to_token_units(*, amount: Decimal, token_decimals: int) -> int:
    decimals = max(int(token_decimals), 0)
    multiplier = Decimal(10) ** decimals
    amount_units = (amount * multiplier).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return max(int(amount_units), 0)


def _decode_payment_events_from_receipt(
    *,
    w3: Web3,
    contract_address: str | None,
    receipt: Any,
) -> list[dict[str, Any]]:
    if not contract_address or not Web3.is_address(contract_address):
        return []
    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=PAYMENT_EXECUTOR_ABI,
        )
        return HashKeyExecutionService._decode_payment_events(contract=contract, receipt=receipt)
    except Exception:
        return []


def _is_execution_item_marked_executed_onchain(
    *,
    w3: Web3,
    contract_address: str | None,
    execution_item_id: uuid.UUID,
) -> bool:
    if not contract_address or not Web3.is_address(contract_address):
        return False
    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=PAYMENT_EXECUTOR_ABI,
        )
        return bool(
            contract.functions.executedItems(
                bytes.fromhex(_uuid_to_bytes32_hex(execution_item_id)[2:])
            ).call()
        )
    except Exception:
        return False


def _validation_error(
    *,
    command_id: uuid.UUID,
    trace_id: str,
    message: str,
    execution_mode: str,
) -> ConfirmResponse:
    return ConfirmResponse(
        status="validation_error",
        command_id=command_id,
        execution_mode=_normalize_confirm_execution_mode(execution_mode),
        next_action="none",
        payment_order_id=None,
        execution_batch_id=None,
        payment_status=None,
        execution_status=None,
        execution=None,
        splits=[],
        execution_items=[],
        unsigned_transactions=None,
        safe_proposal=None,
        risk=None,
        audit_trace_id=trace_id,
        message=message,
    )
