from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import (
    require_actor_user,
    require_command_access,
    require_deposit_access,
    require_execution_batch_access,
    require_execution_item_access,
    require_fiat_payment_access,
    require_kyc_access,
    require_payment_access,
    require_quote_access,
)
from app.db.models import (
    AuditLog,
    Beneficiary,
    CommandExecution,
    ConversationSession,
    FiatPaymentIntent,
    PaymentExecutionBatch,
    PaymentExecutionItem,
    PaymentOrder,
    PaymentSplit,
    PlatformBalanceAccount,
    PlatformBalanceLock,
    StablecoinPayoutLink,
    User,
)
from app.modules.audit.schemas import AuditTimelineItem, AuditTraceResponse


ACTION_TITLES = {
    "confirm_accepted": "确认已接受 (Command confirmation accepted)",
    "confirm_declined": "确认已拒绝 (Command confirmation declined)",
    "confirm_blocked": "确认被风控拦截 (Confirmation blocked by risk)",
    "confirm_rejected_non_payment": "确认失败：非支付命令 (Rejected: non-payment command)",
    "confirm_rejected_incomplete": "确认失败：字段不完整 (Rejected: missing fields)",
    "create": "对象已创建 (Entity created)",
    "mock_execute": "模拟执行已完成 (Mock execution completed)",
    "onchain_tx_submitted": "链上交易已提交 (Onchain transaction submitted)",
    "onchain_tx_confirmed": "链上交易已确认 (Onchain transaction confirmed)",
    "onchain_event_emitted": "链上事件已解析 (Onchain event decoded)",
    "onchain_receipt_mismatch": "链上回执匹配失败 (Onchain receipt mismatch)",
    "onchain_tx_failed": "链上交易失败 (Onchain transaction failed)",
    "onchain_duplicate_rejected": "链上防重已触发 (Onchain duplicate protection triggered)",
    "execution_batch_planned": "执行批次已规划 (Execution batch planned)",
    "execution_batch_started": "执行批次已开始 (Execution batch started)",
    "execution_batch_in_progress": "执行批次进行中 (Execution batch in progress)",
    "execution_batch_confirmed": "执行批次已确认 (Execution batch confirmed)",
    "execution_batch_partially_confirmed": "执行批次部分确认 (Execution batch partially confirmed)",
    "execution_batch_failed": "执行批次失败 (Execution batch failed)",
    "execution_batch_reconciled": "执行批次已对账 (Execution batch reconciled)",
    "execution_item_planned": "执行项已规划 (Execution item planned)",
    "execution_item_submitting": "执行项提交中 (Execution item submitting)",
    "execution_item_reconciled": "执行项已对账 (Execution item reconciled)",
    "wallet_tx_attached": "钱包交易哈希已附加 (Wallet tx hash attached)",
    "safe_tx_attached": "Safe 执行交易哈希已附加 (Safe tx hash attached)",
    "safe_proposal_attached": "Safe 提案信息已附加 (Safe proposal metadata attached)",
    "execution_item_receipt_synced": "执行项回执已同步 (Execution item receipt synced)",
    "payment_order_in_progress": "支付单执行中 (Payment order in progress)",
    "payment_order_executed": "支付单执行完成 (Payment order executed)",
    "payment_order_partially_executed": "支付单部分执行 (Payment order partially executed)",
    "payment_order_failed": "支付单执行失败 (Payment order failed)",
    "user_wallet_request_prepared": "钱包签名请求已生成 (Wallet-sign request prepared)",
    "safe_proposal_prepared": "Safe 提案已生成 (Safe proposal prepared)",
    "retry_mock_requested": "发起模拟重试 (Mock retry requested)",
    "retry_mock_split_updated": "拆单状态更新 (Split status updated)",
    "retry_mock_executed": "模拟重试已完成 (Mock retry completed)",
    "settlement_quote_created": "结算报价已创建 (Settlement quote created)",
    "settlement_quote_accepted": "结算报价已接受 (Settlement quote accepted)",
    "fiat_payment_intent_created": "法币支付意图已创建 (Fiat payment intent created)",
    "fiat_funds_marked_received": "法币到账已确认 (Fiat funds marked received)",
    "payout_order_linked": "稳定币出金订单已关联 (Stablecoin payout order linked)",
    "payout_execution_started": "稳定币出金已开始 (Stablecoin payout execution started)",
    "settlement_completed": "法币入金结算已完成 (Fiat settlement completed)",
    "settlement_failed": "法币入金结算失败 (Fiat settlement failed)",
    "settlement_bridge_failed": "法币结算桥接失败（可重试） (Settlement bridge failed, retryable)",
}


def get_audit_trace(session: Session, *, actor_user_id: UUID, trace_id: str) -> AuditTraceResponse:
    actor_user = require_actor_user(session, actor_user_id)
    logs = session.execute(
        select(AuditLog).where(AuditLog.trace_id == trace_id).order_by(AuditLog.created_at.asc())
    ).scalars().all()
    if not logs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"audit trace not found: {trace_id}")
    for log in logs:
        _assert_actor_can_view_log(session=session, actor_user=actor_user, log=log)
    items = build_audit_timeline_items(logs)
    return AuditTraceResponse(trace_id=trace_id, count=len(items), items=items)


def build_audit_timeline_items(logs: list[AuditLog]) -> list[AuditTimelineItem]:
    return [
        AuditTimelineItem(
            timestamp=log.created_at,
            title=_resolve_title(log.action),
            action=log.action,
            actor_user_id=log.actor_user_id,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            before_json=log.before_json,
            after_json=log.after_json,
            details=_resolve_details(log),
        )
        for log in logs
    ]


def _resolve_title(action: str) -> str:
    if action in ACTION_TITLES:
        return ACTION_TITLES[action]
    formatted = action.replace("_", " ").strip().title()
    return f"{formatted} ({action})"


def _resolve_details(log: AuditLog) -> dict[str, object] | None:
    if log.after_json is not None:
        return log.after_json
    if log.before_json is not None:
        return log.before_json
    return None


def _assert_actor_can_view_log(*, session: Session, actor_user: User, log: AuditLog) -> None:
    if log.actor_user_id == actor_user.id:
        return
    if _entity_is_visible_to_actor(session=session, actor_user=actor_user, entity_type=log.entity_type, entity_id=log.entity_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="audit trace does not belong to the current actor",
    )


def _entity_is_visible_to_actor(
    *,
    session: Session,
    actor_user: User,
    entity_type: str,
    entity_id: UUID,
) -> bool:
    actor_user_id = actor_user.id
    if entity_type == "command_execution":
        require_command_access(session, actor_user_id=actor_user_id, command_id=entity_id)
        return True
    if entity_type == "payment_order":
        require_payment_access(session, actor_user_id=actor_user_id, payment_id=entity_id)
        return True
    if entity_type == "payment_execution_batch":
        require_execution_batch_access(session, actor_user_id=actor_user_id, execution_batch_id=entity_id)
        return True
    if entity_type == "payment_execution_item":
        require_execution_item_access(session, actor_user_id=actor_user_id, execution_item_id=entity_id)
        return True
    if entity_type == "settlement_quote":
        require_quote_access(session, actor_user_id=actor_user_id, quote_id=entity_id)
        return True
    if entity_type == "fiat_payment_intent":
        require_fiat_payment_access(session, actor_user_id=actor_user_id, fiat_payment_intent_id=entity_id)
        return True
    if entity_type == "kyc_verification":
        require_kyc_access(session, actor_user_id=actor_user_id, kyc_id=entity_id)
        return True
    if entity_type == "fiat_deposit_order":
        require_deposit_access(session, actor_user_id=actor_user_id, deposit_order_id=entity_id)
        return True
    if entity_type == "payment_split":
        split_row = session.execute(
            select(PaymentSplit, PaymentOrder)
            .join(PaymentOrder, PaymentOrder.id == PaymentSplit.payment_order_id)
            .where(PaymentSplit.id == entity_id)
            .limit(1)
        ).one_or_none()
        if split_row is None or split_row[1].user_id != actor_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="payment split does not belong to the current actor")
        return True
    if entity_type == "beneficiary":
        beneficiary = session.get(Beneficiary, entity_id)
        if beneficiary is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"beneficiary not found: {entity_id}")
        if beneficiary.organization_id is not None and beneficiary.organization_id != actor_user.organization_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="beneficiary does not belong to the current actor")
        return True
    if entity_type == "conversation_session":
        conversation = session.get(ConversationSession, entity_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"conversation_session not found: {entity_id}")
        if conversation.user_id != actor_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="conversation_session does not belong to the current actor")
        return True
    if entity_type == "stablecoin_payout_link":
        payout_row = session.execute(
            select(StablecoinPayoutLink, FiatPaymentIntent)
            .join(FiatPaymentIntent, FiatPaymentIntent.id == StablecoinPayoutLink.fiat_payment_intent_id)
            .where(StablecoinPayoutLink.id == entity_id)
            .limit(1)
        ).one_or_none()
        if payout_row is None or payout_row[1].merchant_id != actor_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="stablecoin_payout_link does not belong to the current actor")
        return True
    if entity_type == "platform_balance_lock":
        lock_row = session.execute(
            select(PlatformBalanceLock, PlatformBalanceAccount)
            .join(PlatformBalanceAccount, PlatformBalanceAccount.id == PlatformBalanceLock.account_id)
            .where(PlatformBalanceLock.id == entity_id)
            .limit(1)
        ).one_or_none()
        if lock_row is None or lock_row[1].user_id != actor_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="platform_balance_lock does not belong to the current actor")
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"audit entity type is not available to the current actor: {entity_type}",
    )
