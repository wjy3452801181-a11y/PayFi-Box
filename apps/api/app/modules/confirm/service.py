from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from web3 import Web3

from app.core.config import get_settings
from app.db.models import (
    AuditLog,
    Beneficiary,
    CommandExecution,
    CommandExecutionStatus,
    ExecutionMode,
    OnchainExecutionStatus,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentSplit,
    PaymentSplitStatus,
    User,
)
from app.modules.command.risk import evaluate_payment_risk
from app.modules.confirm.schemas import (
    ConfirmRequest,
    ConfirmResponse,
    ConfirmRiskResult,
    ConfirmSplitResult,
    MockExecutionResult,
)
from app.modules.execution.hashkey_service import (
    HashKeyExecutionError,
    HashKeyExecutionResult,
    HashKeyExecutionService,
)

FINAL_COMMAND_STATUSES = {
    CommandExecutionStatus.CONFIRMED.value,
    CommandExecutionStatus.DECLINED.value,
    CommandExecutionStatus.BLOCKED.value,
    CommandExecutionStatus.EXECUTED.value,
}
CONFIRM_EXECUTION_MODES = {"operator", "user_wallet", "safe"}


def handle_confirm(session: Session, request: ConfirmRequest) -> ConfirmResponse:
    confirm_execution_mode = _normalize_confirm_execution_mode(request.execution_mode)
    command = session.get(CommandExecution, request.command_id)
    if command is None:
        return _validation_error(
            command_id=request.command_id,
            trace_id=f"trace-confirm-{request.command_id.hex[:12]}",
            message="未找到对应命令。 (Command not found.)",
            execution_mode=confirm_execution_mode,
        )

    trace_id = _build_confirm_trace_id(command)
    actor_user_id = request.actor_user_id or command.user_id
    if session.get(User, actor_user_id) is None:
        return _validation_error(
            command_id=command.id,
            trace_id=trace_id,
            message="确认操作者不存在。 (Confirmation actor user was not found.)",
            execution_mode=confirm_execution_mode,
        )

    if command.final_status in FINAL_COMMAND_STATUSES:
        return _validation_error(
            command_id=command.id,
            trace_id=trace_id,
            message="该命令已完成确认流程，不能重复确认。 (This command is already finalized.)",
            execution_mode=confirm_execution_mode,
        )

    settings = get_settings()
    execution_backend = _normalize_execution_backend(settings.payment_execution_backend)
    execution_mode = (
        ExecutionMode.ONCHAIN.value
        if execution_backend == "hashkey_testnet"
        else ExecutionMode.MOCK.value
    )

    if not request.confirmed:
        before_status = command.final_status
        _append_confirmation_meta(
            command=command,
            status=CommandExecutionStatus.DECLINED.value,
            trace_id=trace_id,
            note=request.note,
            locale=request.locale,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
        )
        command.final_status = CommandExecutionStatus.DECLINED.value
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="command_execution",
                entity_id=command.id,
                action="confirm_declined",
                before_json={"final_status": before_status},
                after_json={"final_status": CommandExecutionStatus.DECLINED.value},
                trace_id=trace_id,
            )
        )
        session.commit()
        return ConfirmResponse(
            status="declined",
            command_id=command.id,
            execution_mode=confirm_execution_mode,
            next_action="none",
            payment_order_id=None,
            payment_status=None,
            execution=None,
            splits=[],
            unsigned_transactions=None,
            safe_proposal=None,
            risk=None,
            audit_trace_id=trace_id,
            message="已取消确认，本次不创建支付单。 (Confirmation declined; no payment order was created.)",
        )

    parsed = command.parsed_intent_json or {}
    intent = parsed.get("intent")
    fields = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {}

    if intent != "create_payment":
        _mark_command_failed(
            command,
            trace_id,
            reason="non_payment_intent",
            note=request.note,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
        )
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="command_execution",
                entity_id=command.id,
                action="confirm_rejected_non_payment",
                before_json=None,
                after_json={"intent": intent},
                trace_id=trace_id,
            )
        )
        session.commit()
        return _validation_error(
            command_id=command.id,
            trace_id=trace_id,
            message="该命令不是支付创建命令，不能确认。 (Only create_payment commands are confirmable.)",
            execution_mode=confirm_execution_mode,
        )

    existing_order_id = session.execute(
        select(PaymentOrder.id).where(PaymentOrder.source_command_id == command.id)
    ).scalar_one_or_none()
    if existing_order_id is not None:
        return _validation_error(
            command_id=command.id,
            trace_id=trace_id,
            message="该命令已生成支付单，不能重复确认。 (A payment order already exists for this command.)",
            execution_mode=confirm_execution_mode,
        )

    validation_message = _validate_payment_fields(fields=fields)
    if validation_message is not None:
        _mark_command_failed(
            command,
            trace_id,
            reason="missing_required_fields",
            note=request.note,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
        )
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="command_execution",
                entity_id=command.id,
                action="confirm_rejected_incomplete",
                before_json=None,
                after_json={"fields": fields},
                trace_id=trace_id,
            )
        )
        session.commit()
        return _validation_error(
            command_id=command.id,
            trace_id=trace_id,
            message=validation_message,
            execution_mode=confirm_execution_mode,
        )

    amount = Decimal(str(fields["amount"]))
    currency = str(fields["currency"]).upper()
    split_count = _safe_split_count(fields.get("split_count"))
    reference = str(fields.get("reference") or f"CMD-{command.id.hex[:8].upper()}")
    beneficiary_obj = fields.get("beneficiary") if isinstance(fields.get("beneficiary"), dict) else {}
    beneficiary_id = _safe_uuid(beneficiary_obj.get("id"))
    if beneficiary_id is None:
        _mark_command_failed(
            command,
            trace_id,
            reason="unresolved_beneficiary",
            note=request.note,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
        )
        session.commit()
        return _validation_error(
            command_id=command.id,
            trace_id=trace_id,
            message="受益人未解析为系统对象，当前版本不能确认。 (Beneficiary is unresolved and cannot be confirmed in Step 8C.)",
            execution_mode=confirm_execution_mode,
        )

    beneficiary = session.get(Beneficiary, beneficiary_id)
    if beneficiary is None:
        _mark_command_failed(
            command,
            trace_id,
            reason="beneficiary_not_found",
            note=request.note,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
        )
        session.commit()
        return _validation_error(
            command_id=command.id,
            trace_id=trace_id,
            message="受益人不存在。 (Beneficiary not found.)",
            execution_mode=confirm_execution_mode,
        )

    if confirm_execution_mode == "operator" and execution_mode == ExecutionMode.ONCHAIN.value:
        if not beneficiary.wallet_address or not Web3.is_address(beneficiary.wallet_address):
            _mark_command_failed(
                command,
                trace_id,
                reason="invalid_beneficiary_wallet",
                note=request.note,
                execution_backend=execution_backend,
                execution_route=confirm_execution_mode,
            )
            session.commit()
            return _validation_error(
                command_id=command.id,
                trace_id=trace_id,
                message="链上执行需要受益人钱包地址。 (Onchain execution requires a valid beneficiary wallet address.)",
                execution_mode=confirm_execution_mode,
            )
    risk_preview = evaluate_payment_risk(fields)
    if risk_preview["decision"] == "block":
        before_status = command.final_status
        _append_confirmation_meta(
            command=command,
            status=CommandExecutionStatus.BLOCKED.value,
            trace_id=trace_id,
            note=request.note,
            locale=request.locale,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
        )
        command.final_status = CommandExecutionStatus.BLOCKED.value
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="command_execution",
                entity_id=command.id,
                action="confirm_blocked",
                before_json={"final_status": before_status},
                after_json={
                    "final_status": CommandExecutionStatus.BLOCKED.value,
                    "risk": risk_preview,
                },
                trace_id=trace_id,
            )
        )
        session.commit()
        return ConfirmResponse(
            status="blocked",
            command_id=command.id,
            execution_mode=confirm_execution_mode,
            next_action="none",
            payment_order_id=None,
            payment_status=None,
            execution=MockExecutionResult(
                mode="onchain" if execution_mode == ExecutionMode.ONCHAIN.value else "mock",
                executed=False,
                transaction_ref=None,
                network=settings.hashkey_network if execution_mode == ExecutionMode.ONCHAIN.value else None,
                chain_id=settings.hashkey_chain_id if execution_mode == ExecutionMode.ONCHAIN.value else None,
                tx_hash=None,
                explorer_url=None,
                onchain_status=OnchainExecutionStatus.BLOCKED.value if execution_mode == ExecutionMode.ONCHAIN.value else None,
                contract_address=settings.hashkey_payment_executor_address if execution_mode == ExecutionMode.ONCHAIN.value else None,
                token_address=settings.hashkey_payment_token_address if execution_mode == ExecutionMode.ONCHAIN.value else None,
                gas_used=None,
                effective_gas_price=None,
                payment_ref=None,
                decoded_events=[],
                executed_at=None,
                message=(
                    "风险命中拦截，未发送链上交易。 (Blocked by risk policy; no onchain transaction was sent.)"
                    if execution_mode == ExecutionMode.ONCHAIN.value
                    else "风险命中拦截，未执行模拟支付。 (Blocked by risk policy; mock execution did not run.)"
                ),
            ),
            splits=[],
            unsigned_transactions=None,
            safe_proposal=None,
            risk=ConfirmRiskResult(**risk_preview),
            audit_trace_id=trace_id,
            message="确认请求被风控拦截。 (Confirmation was blocked by risk policy.)",
        )

    user = session.get(User, command.user_id)
    organization_id = user.organization_id if user else None
    payment_order = PaymentOrder(
        id=uuid.uuid4(),
        user_id=command.user_id,
        organization_id=organization_id,
        beneficiary_id=beneficiary_id,
        source_command_id=command.id,
        intent_source_text=command.raw_text,
        amount=amount,
        currency=currency,
        status=PaymentOrderStatus.APPROVED.value,
        reference=reference,
        risk_level=risk_preview["risk_level"],
        requires_confirmation=False,
        execution_route=confirm_execution_mode,
        execution_mode=execution_mode,
        network=settings.hashkey_network if execution_mode == ExecutionMode.ONCHAIN.value else None,
        chain_id=settings.hashkey_chain_id if execution_mode == ExecutionMode.ONCHAIN.value else None,
        onchain_status=(
            OnchainExecutionStatus.PENDING_SUBMISSION.value
            if execution_mode == ExecutionMode.ONCHAIN.value
            else None
        ),
        contract_address=settings.hashkey_payment_executor_address if execution_mode == ExecutionMode.ONCHAIN.value else None,
        token_address=settings.hashkey_payment_token_address if execution_mode == ExecutionMode.ONCHAIN.value else None,
        metadata_json={
            "confirmed_by": str(actor_user_id),
            "note": request.note,
            "locale": request.locale,
            "risk_reason_codes": risk_preview["reason_codes"],
            "preview_mode": "step8c_confirm",
            "execution_backend": execution_backend,
            "execution_route": confirm_execution_mode,
        },
    )
    session.add(payment_order)
    session.flush()

    session.add(
        _build_audit_log(
            actor_user_id=actor_user_id,
            entity_type="command_execution",
            entity_id=command.id,
            action="confirm_accepted",
            before_json={"final_status": command.final_status},
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
            after_json={"status": PaymentOrderStatus.APPROVED.value, "reference": payment_order.reference},
            trace_id=trace_id,
        )
    )

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

    if confirm_execution_mode == "operator" and execution_mode == ExecutionMode.ONCHAIN.value:
        return _handle_onchain_execution(
            session=session,
            command=command,
            payment_order=payment_order,
            split_rows=split_rows,
            amount=amount,
            reference=reference,
            beneficiary=beneficiary,
            actor_user_id=actor_user_id,
            request=request,
            trace_id=trace_id,
            risk_preview=risk_preview,
            execution_backend=execution_backend,
            confirm_execution_mode=confirm_execution_mode,
        )

    if confirm_execution_mode == "operator":
        return _handle_mock_execution(
            session=session,
            command=command,
            payment_order=payment_order,
            split_rows=split_rows,
            actor_user_id=actor_user_id,
            request=request,
            trace_id=trace_id,
            risk_preview=risk_preview,
            execution_backend=execution_backend,
            confirm_execution_mode=confirm_execution_mode,
        )

    if confirm_execution_mode == "user_wallet":
        return _handle_user_wallet_scaffold(
            session=session,
            command=command,
            payment_order=payment_order,
            split_rows=split_rows,
            beneficiary=beneficiary,
            actor_user_id=actor_user_id,
            request=request,
            trace_id=trace_id,
            risk_preview=risk_preview,
            execution_backend=execution_backend,
        )

    return _handle_safe_scaffold(
        session=session,
        command=command,
        payment_order=payment_order,
        split_rows=split_rows,
        beneficiary=beneficiary,
        actor_user_id=actor_user_id,
        request=request,
        trace_id=trace_id,
        risk_preview=risk_preview,
        execution_backend=execution_backend,
    )


def _handle_onchain_execution(
    *,
    session: Session,
    command: CommandExecution,
    payment_order: PaymentOrder,
    split_rows: list[PaymentSplit],
    amount: Decimal,
    reference: str,
    beneficiary: Beneficiary,
    actor_user_id: uuid.UUID,
    request: ConfirmRequest,
    trace_id: str,
    risk_preview: dict[str, Any],
    execution_backend: str,
    confirm_execution_mode: str,
) -> ConfirmResponse:
    settings = get_settings()
    split_results: list[ConfirmSplitResult] = []
    try:
        executor = HashKeyExecutionService(settings)
        nonce = executor.get_pending_nonce()
        targets = []
        if split_rows:
            for split in split_rows:
                targets.append((split.sequence, Decimal(split.amount), split))
        else:
            targets.append((1, amount, None))

        tx_results: list[HashKeyExecutionResult] = []
        for sequence, split_amount, split_row in targets:
            tx_result = executor.execute_payment(
                order_id=payment_order.id,
                beneficiary_address=str(beneficiary.wallet_address),
                amount=split_amount,
                reference=reference,
                split_index=sequence,
                split_count=len(targets),
                nonce=nonce,
            )
            nonce += 1
            tx_results.append(tx_result)

            if split_row is not None:
                split_row.status = PaymentSplitStatus.EXECUTED.value
                split_row.tx_hash = tx_result.tx_hash
                split_row.explorer_url = tx_result.explorer_url
                split_row.onchain_status = OnchainExecutionStatus.CONFIRMED_ONCHAIN.value
                split_row.execution_tx_sent_at = tx_result.sent_at
                split_row.execution_tx_confirmed_at = tx_result.confirmed_at
                split_row.gas_used = Decimal(str(tx_result.gas_used)) if tx_result.gas_used is not None else None

                split_results.append(
                    ConfirmSplitResult(
                        sequence=split_row.sequence,
                        amount=float(split_row.amount),
                        currency=split_row.currency,
                        status=split_row.status,
                        tx_hash=split_row.tx_hash,
                        explorer_url=split_row.explorer_url,
                        onchain_status=split_row.onchain_status,
                        execution_tx_sent_at=split_row.execution_tx_sent_at,
                        execution_tx_confirmed_at=split_row.execution_tx_confirmed_at,
                        gas_used=int(split_row.gas_used) if split_row.gas_used is not None else None,
                        payment_ref=tx_result.payment_ref,
                    )
                )
                target_entity_type = "payment_split"
                target_entity_id = split_row.id
            else:
                target_entity_type = "payment_order"
                target_entity_id = payment_order.id

            session.add(
                _build_audit_log(
                    actor_user_id=actor_user_id,
                    entity_type=target_entity_type,
                    entity_id=target_entity_id,
                    action="onchain_tx_submitted",
                    before_json=None,
                    after_json={
                        "tx_hash": tx_result.tx_hash,
                        "explorer_url": tx_result.explorer_url,
                        "network": tx_result.network,
                        "chain_id": tx_result.chain_id,
                        "sent_at": tx_result.sent_at.isoformat(),
                    },
                    trace_id=trace_id,
                )
            )
            session.add(
                _build_audit_log(
                    actor_user_id=actor_user_id,
                    entity_type=target_entity_type,
                    entity_id=target_entity_id,
                    action="onchain_tx_confirmed",
                    before_json=None,
                    after_json={
                        "tx_hash": tx_result.tx_hash,
                        "gas_used": tx_result.gas_used,
                        "effective_gas_price": tx_result.effective_gas_price,
                        "confirmed_at": tx_result.confirmed_at.isoformat(),
                    },
                    trace_id=trace_id,
                )
            )
            session.add(
                _build_audit_log(
                    actor_user_id=actor_user_id,
                    entity_type=target_entity_type,
                    entity_id=target_entity_id,
                    action="onchain_event_emitted",
                    before_json=None,
                    after_json={
                        "tx_hash": tx_result.tx_hash,
                        "events": tx_result.decoded_events,
                    },
                    trace_id=trace_id,
                )
            )

        total_gas = sum(item.gas_used or 0 for item in tx_results)
        payment_order.status = PaymentOrderStatus.EXECUTED.value
        payment_order.onchain_status = OnchainExecutionStatus.CONFIRMED_ONCHAIN.value
        payment_order.execution_tx_sent_at = min(item.sent_at for item in tx_results)
        payment_order.execution_tx_confirmed_at = max(item.confirmed_at for item in tx_results)
        payment_order.gas_used = Decimal(str(total_gas))
        payment_order.effective_gas_price = (
            Decimal(str(tx_results[-1].effective_gas_price))
            if tx_results and tx_results[-1].effective_gas_price is not None
            else None
        )
        if len(tx_results) == 1:
            payment_order.tx_hash = tx_results[0].tx_hash
            payment_order.explorer_url = tx_results[0].explorer_url
        else:
            payment_order.tx_hash = None
            payment_order.explorer_url = None

        onchain_payload = {
            "split_execution_mode": "per_split" if split_rows else "single_tx",
            "tx_count": len(tx_results),
            "txs": [
                {
                    "split_index": index + 1,
                    "tx_hash": item.tx_hash,
                    "explorer_url": item.explorer_url,
                    "payment_ref": item.payment_ref,
                    "gas_used": item.gas_used,
                    "effective_gas_price": item.effective_gas_price,
                    "events": item.decoded_events,
                }
                for index, item in enumerate(tx_results)
            ],
        }
        payment_order.onchain_payload_json = onchain_payload

        metadata_json = dict(payment_order.metadata_json or {})
        metadata_json["onchain"] = onchain_payload
        payment_order.metadata_json = metadata_json

        _append_confirmation_meta(
            command=command,
            status=CommandExecutionStatus.EXECUTED.value,
            trace_id=trace_id,
            note=request.note,
            locale=request.locale,
            payment_order_id=payment_order.id,
            execution_backend=execution_backend,
            execution_route=confirm_execution_mode,
        )
        command.final_status = CommandExecutionStatus.EXECUTED.value
        session.commit()

        top_tx = tx_results[-1]
        return ConfirmResponse(
            status="ok",
            command_id=command.id,
            execution_mode=confirm_execution_mode,
            next_action="completed",
            payment_order_id=payment_order.id,
            payment_status=payment_order.status,
            execution=MockExecutionResult(
                mode="onchain",
                executed=True,
                transaction_ref=None,
                network=payment_order.network,
                chain_id=payment_order.chain_id,
                tx_hash=payment_order.tx_hash or top_tx.tx_hash,
                explorer_url=payment_order.explorer_url or top_tx.explorer_url,
                onchain_status=payment_order.onchain_status,
                contract_address=payment_order.contract_address,
                token_address=payment_order.token_address,
                gas_used=int(payment_order.gas_used) if payment_order.gas_used is not None else None,
                effective_gas_price=(
                    int(payment_order.effective_gas_price)
                    if payment_order.effective_gas_price is not None
                    else None
                ),
                payment_ref=top_tx.payment_ref,
                decoded_events=top_tx.decoded_events,
                split_executions=[item.model_dump(mode="json") for item in split_results],
                executed_at=payment_order.execution_tx_confirmed_at,
                message="链上测试网执行完成。 (Onchain execution completed on HashKey testnet.)",
            ),
            splits=split_results,
            unsigned_transactions=None,
            safe_proposal=None,
            risk=ConfirmRiskResult(**risk_preview),
            audit_trace_id=trace_id,
            message=(
                "已完成 HashKey Testnet 链上执行。 (Payment confirmation completed with HashKey testnet execution.)"
            ),
        )
    except HashKeyExecutionError as exc:
        payment_order.status = PaymentOrderStatus.FAILED.value
        payment_order.onchain_status = OnchainExecutionStatus.FAILED_ONCHAIN.value
        for split in split_rows:
            if split.status != PaymentSplitStatus.EXECUTED.value:
                split.status = PaymentSplitStatus.FAILED.value
                split.onchain_status = OnchainExecutionStatus.FAILED_ONCHAIN.value
        session.add(
            _build_audit_log(
                actor_user_id=actor_user_id,
                entity_type="payment_order",
                entity_id=payment_order.id,
                action="onchain_tx_failed",
                before_json={"status": PaymentOrderStatus.APPROVED.value},
                after_json={
                    "status": PaymentOrderStatus.FAILED.value,
                    "error": str(exc),
                },
                trace_id=trace_id,
            )
        )
        _append_confirmation_meta(
            command=command,
            status=CommandExecutionStatus.FAILED.value,
            trace_id=trace_id,
            note=request.note,
            locale=request.locale,
            payment_order_id=payment_order.id,
            execution_backend=execution_backend,
            reason="onchain_execution_failed",
            execution_route=confirm_execution_mode,
        )
        command.final_status = CommandExecutionStatus.FAILED.value
        session.commit()
        return ConfirmResponse(
            status="failed",
            command_id=command.id,
            execution_mode=confirm_execution_mode,
            next_action="none",
            payment_order_id=payment_order.id,
            payment_status=payment_order.status,
            execution=MockExecutionResult(
                mode="onchain",
                executed=False,
                transaction_ref=None,
                network=payment_order.network,
                chain_id=payment_order.chain_id,
                tx_hash=None,
                explorer_url=None,
                onchain_status=payment_order.onchain_status,
                contract_address=payment_order.contract_address,
                token_address=payment_order.token_address,
                gas_used=None,
                effective_gas_price=None,
                payment_ref=None,
                decoded_events=[],
                split_executions=[
                    {
                        "sequence": item.sequence,
                        "amount": float(item.amount),
                        "currency": item.currency,
                        "status": item.status,
                        "tx_hash": item.tx_hash,
                        "explorer_url": item.explorer_url,
                        "onchain_status": item.onchain_status,
                        "execution_tx_sent_at": (
                            item.execution_tx_sent_at.isoformat()
                            if item.execution_tx_sent_at
                            else None
                        ),
                        "execution_tx_confirmed_at": (
                            item.execution_tx_confirmed_at.isoformat()
                            if item.execution_tx_confirmed_at
                            else None
                        ),
                        "gas_used": int(item.gas_used) if item.gas_used is not None else None,
                        "payment_ref": None,
                    }
                    for item in split_rows
                ],
                executed_at=None,
                message=f"链上执行失败：{exc} (Onchain execution failed: {exc})",
            ),
            splits=[
                ConfirmSplitResult(
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
                for item in split_rows
            ],
            unsigned_transactions=None,
            safe_proposal=None,
            risk=ConfirmRiskResult(**risk_preview),
            audit_trace_id=trace_id,
            message="链上执行失败，支付单已标记 failed。 (Onchain execution failed and payment order is marked as failed.)",
        )


def _handle_mock_execution(
    *,
    session: Session,
    command: CommandExecution,
    payment_order: PaymentOrder,
    split_rows: list[PaymentSplit],
    actor_user_id: uuid.UUID,
    request: ConfirmRequest,
    trace_id: str,
    risk_preview: dict[str, Any],
    execution_backend: str,
    confirm_execution_mode: str,
) -> ConfirmResponse:
    execution = _run_mock_execution(
        payment_order_id=payment_order.id,
        base_time=command.created_at,
    )
    before_status = payment_order.status
    payment_order.status = PaymentOrderStatus.EXECUTED.value
    for split in split_rows:
        split.status = PaymentSplitStatus.EXECUTED.value
    session.add(
        _build_audit_log(
            actor_user_id=actor_user_id,
            entity_type="payment_order",
            entity_id=payment_order.id,
            action="mock_execute",
            before_json={"status": before_status},
            after_json={
                "status": PaymentOrderStatus.EXECUTED.value,
                "transaction_ref": execution["transaction_ref"],
            },
            trace_id=trace_id,
        )
    )

    _append_confirmation_meta(
        command=command,
        status=CommandExecutionStatus.EXECUTED.value,
        trace_id=trace_id,
        note=request.note,
        locale=request.locale,
        payment_order_id=payment_order.id,
        execution_backend=execution_backend,
        execution_route=confirm_execution_mode,
    )
    command.final_status = CommandExecutionStatus.EXECUTED.value
    session.commit()

    split_result = [
        ConfirmSplitResult(
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
        for item in split_rows
    ]

    return ConfirmResponse(
        status="ok",
        command_id=command.id,
        execution_mode=confirm_execution_mode,
        next_action="completed",
        payment_order_id=payment_order.id,
        payment_status=payment_order.status,
        execution=MockExecutionResult(
            **execution,
            split_executions=[item.model_dump(mode="json") for item in split_result],
        ),
        splits=split_result,
        unsigned_transactions=None,
        safe_proposal=None,
        risk=ConfirmRiskResult(**risk_preview),
        audit_trace_id=trace_id,
        message=(
            "已在复核建议下完成模拟执行。 (Mock execution completed under review recommendation.)"
            if risk_preview["decision"] == "review"
            else "支付确认已完成（模拟执行）。 (Payment confirmation completed in mock execution mode.)"
        ),
    )


def _handle_user_wallet_scaffold(
    *,
    session: Session,
    command: CommandExecution,
    payment_order: PaymentOrder,
    split_rows: list[PaymentSplit],
    beneficiary: Beneficiary,
    actor_user_id: uuid.UUID,
    request: ConfirmRequest,
    trace_id: str,
    risk_preview: dict[str, Any],
    execution_backend: str,
) -> ConfirmResponse:
    settings = get_settings()
    payment_order.execution_mode = ExecutionMode.ONCHAIN.value
    payment_order.network = settings.hashkey_network
    payment_order.chain_id = settings.hashkey_chain_id
    payment_order.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value
    payment_order.contract_address = settings.hashkey_payment_executor_address
    payment_order.token_address = settings.hashkey_payment_token_address
    payment_order.status = PaymentOrderStatus.APPROVED.value

    unsigned_transactions = _build_unsigned_transactions(
        payment_order=payment_order,
        split_rows=split_rows,
        beneficiary=beneficiary,
        settings=settings,
    )
    for split in split_rows:
        split.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value

    metadata_json = dict(payment_order.metadata_json or {})
    metadata_json["user_wallet"] = {
        "prepared": True,
        "tx_count": len(unsigned_transactions),
        "next_action": "sign_in_wallet",
    }
    payment_order.metadata_json = metadata_json

    _append_confirmation_meta(
        command=command,
        status=CommandExecutionStatus.CONFIRMED.value,
        trace_id=trace_id,
        note=request.note,
        locale=request.locale,
        payment_order_id=payment_order.id,
        execution_backend=execution_backend,
        execution_route="user_wallet",
    )
    command.final_status = CommandExecutionStatus.CONFIRMED.value

    session.add(
        _build_audit_log(
            actor_user_id=actor_user_id,
            entity_type="payment_order",
            entity_id=payment_order.id,
            action="user_wallet_request_prepared",
            before_json=None,
            after_json={
                "next_action": "sign_in_wallet",
                "tx_count": len(unsigned_transactions),
            },
            trace_id=trace_id,
        )
    )
    session.commit()

    pending_splits = _build_pending_split_results(split_rows)

    return ConfirmResponse(
        status="ok",
        command_id=command.id,
        execution_mode="user_wallet",
        next_action="sign_in_wallet",
        payment_order_id=payment_order.id,
        payment_status=payment_order.status,
        execution=MockExecutionResult(
            mode="onchain",
            executed=False,
            transaction_ref=None,
            network=payment_order.network,
            chain_id=payment_order.chain_id,
            tx_hash=None,
            explorer_url=None,
            onchain_status=payment_order.onchain_status,
            contract_address=payment_order.contract_address,
            token_address=payment_order.token_address,
            gas_used=None,
            effective_gas_price=None,
            payment_ref=None,
            decoded_events=[],
            split_executions=[item.model_dump(mode="json") for item in pending_splits],
            executed_at=None,
            message="已生成待钱包签名交易，请在钱包中签名。 (Unsigned tx payload prepared; please sign in wallet.)",
        ),
        splits=pending_splits,
        unsigned_transactions=unsigned_transactions,
        safe_proposal=None,
        risk=ConfirmRiskResult(**risk_preview),
        audit_trace_id=trace_id,
        message="已进入 user_wallet 模式，等待钱包签名。 (user_wallet mode prepared; waiting for wallet signature.)",
    )


def _handle_safe_scaffold(
    *,
    session: Session,
    command: CommandExecution,
    payment_order: PaymentOrder,
    split_rows: list[PaymentSplit],
    beneficiary: Beneficiary,
    actor_user_id: uuid.UUID,
    request: ConfirmRequest,
    trace_id: str,
    risk_preview: dict[str, Any],
    execution_backend: str,
) -> ConfirmResponse:
    settings = get_settings()
    payment_order.execution_mode = ExecutionMode.ONCHAIN.value
    payment_order.network = settings.hashkey_network
    payment_order.chain_id = settings.hashkey_chain_id
    payment_order.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value
    payment_order.contract_address = settings.hashkey_payment_executor_address
    payment_order.token_address = settings.hashkey_payment_token_address
    payment_order.status = PaymentOrderStatus.APPROVED.value

    unsigned_transactions = _build_unsigned_transactions(
        payment_order=payment_order,
        split_rows=split_rows,
        beneficiary=beneficiary,
        settings=settings,
    )
    for split in split_rows:
        split.onchain_status = OnchainExecutionStatus.PENDING_SUBMISSION.value

    safe_proposal = {
        "safe_address": None,
        "network": settings.hashkey_network,
        "chain_id": settings.hashkey_chain_id,
        "proposal_status": "prepared",
        "transactions": [
            {
                "to": tx["to"],
                "value": tx["value"],
                "data": tx["data"],
                "operation": 0,
                "description": tx["description"],
                "meta": tx["meta"],
            }
            for tx in unsigned_transactions
        ],
    }

    metadata_json = dict(payment_order.metadata_json or {})
    metadata_json["safe"] = {
        "prepared": True,
        "tx_count": len(unsigned_transactions),
        "next_action": "approve_in_safe",
    }
    payment_order.metadata_json = metadata_json

    _append_confirmation_meta(
        command=command,
        status=CommandExecutionStatus.CONFIRMED.value,
        trace_id=trace_id,
        note=request.note,
        locale=request.locale,
        payment_order_id=payment_order.id,
        execution_backend=execution_backend,
        execution_route="safe",
    )
    command.final_status = CommandExecutionStatus.CONFIRMED.value

    session.add(
        _build_audit_log(
            actor_user_id=actor_user_id,
            entity_type="payment_order",
            entity_id=payment_order.id,
            action="safe_proposal_prepared",
            before_json=None,
            after_json={
                "next_action": "approve_in_safe",
                "tx_count": len(unsigned_transactions),
            },
            trace_id=trace_id,
        )
    )
    session.commit()

    pending_splits = _build_pending_split_results(split_rows)

    return ConfirmResponse(
        status="ok",
        command_id=command.id,
        execution_mode="safe",
        next_action="approve_in_safe",
        payment_order_id=payment_order.id,
        payment_status=payment_order.status,
        execution=MockExecutionResult(
            mode="onchain",
            executed=False,
            transaction_ref=None,
            network=payment_order.network,
            chain_id=payment_order.chain_id,
            tx_hash=None,
            explorer_url=None,
            onchain_status=payment_order.onchain_status,
            contract_address=payment_order.contract_address,
            token_address=payment_order.token_address,
            gas_used=None,
            effective_gas_price=None,
            payment_ref=None,
            decoded_events=[],
            split_executions=[item.model_dump(mode="json") for item in pending_splits],
            executed_at=None,
            message="已生成 Safe 提案草稿，等待多签审批。 (Safe-style proposal prepared; waiting for Safe approvals.)",
        ),
        splits=pending_splits,
        unsigned_transactions=None,
        safe_proposal=safe_proposal,
        risk=ConfirmRiskResult(**risk_preview),
        audit_trace_id=trace_id,
        message="已进入 safe 模式，等待 Safe 审批。 (safe mode prepared; waiting for Safe approval.)",
    )


def _build_pending_split_results(split_rows: list[PaymentSplit]) -> list[ConfirmSplitResult]:
    return [
        ConfirmSplitResult(
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
        for item in split_rows
    ]


def _build_unsigned_transactions(
    *,
    payment_order: PaymentOrder,
    split_rows: list[PaymentSplit],
    beneficiary: Beneficiary,
    settings: Any,
) -> list[dict[str, Any]]:
    if split_rows:
        targets = [(item.sequence, Decimal(item.amount)) for item in split_rows]
    else:
        targets = [(1, Decimal(payment_order.amount))]

    contract_address = settings.hashkey_payment_executor_address
    token_address = settings.hashkey_payment_token_address
    txs: list[dict[str, Any]] = []
    for split_index, split_amount in targets:
        txs.append(
            {
                "to": contract_address,
                "value": "0x0",
                "data": None,
                "description": "PaymentExecutor.executePayment",
                "meta": {
                    "order_id": str(payment_order.id),
                    "beneficiary": beneficiary.wallet_address,
                    "token": token_address,
                    "amount": str(split_amount),
                    "currency": payment_order.currency,
                    "reference": payment_order.reference,
                    "split_index": split_index,
                    "split_count": len(targets),
                    "chain_id": settings.hashkey_chain_id,
                    "rpc_url": settings.hashkey_rpc_url,
                    "network": settings.hashkey_network,
                },
            }
        )
    return txs


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
                after_json={
                    "sequence": index,
                    "amount": float(split_amount),
                    "status": split.status,
                },
                trace_id=trace_id,
            )
        )
    return split_rows


def _run_mock_execution(*, payment_order_id: uuid.UUID, base_time: datetime | None) -> dict[str, Any]:
    if base_time is None:
        executed_at = datetime.now(timezone.utc)
    else:
        executed_at = base_time.astimezone(timezone.utc)
    return {
        "mode": "mock",
        "executed": True,
        "transaction_ref": f"MOCK-TX-{payment_order_id.hex[:12].upper()}",
        "network": None,
        "chain_id": None,
        "tx_hash": None,
        "explorer_url": None,
        "onchain_status": None,
        "contract_address": None,
        "token_address": None,
        "gas_used": None,
        "effective_gas_price": None,
        "payment_ref": None,
        "decoded_events": [],
        "executed_at": executed_at,
        "message": "模拟执行完成。 (Mock execution completed successfully.)",
    }


def _build_confirm_trace_id(command: CommandExecution) -> str:
    base = command.trace_id or f"trace-cmd-{command.id.hex[:12]}"
    return f"{base}-confirm"


def _mark_command_failed(
    command: CommandExecution,
    trace_id: str,
    reason: str,
    note: str | None,
    execution_backend: str,
    execution_route: str = "operator",
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


def _validation_error(
    *,
    command_id: uuid.UUID,
    trace_id: str,
    message: str,
    execution_mode: str = "operator",
) -> ConfirmResponse:
    return ConfirmResponse(
        status="validation_error",
        command_id=command_id,
        execution_mode=_normalize_confirm_execution_mode(execution_mode),
        next_action="none",
        payment_order_id=None,
        payment_status=None,
        execution=None,
        splits=[],
        unsigned_transactions=None,
        safe_proposal=None,
        risk=None,
        audit_trace_id=trace_id,
        message=message,
    )
