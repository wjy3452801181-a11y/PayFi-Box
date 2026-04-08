from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class ConfirmRequest(BaseModel):
    command_id: UUID
    confirmed: bool
    execution_mode: Literal["operator", "user_wallet", "safe"] | None = None
    idempotency_key: str | None = None
    actor_user_id: UUID | None = None
    note: str | None = None
    locale: str | None = None


class MockExecutionResult(BaseModel):
    mode: Literal["mock", "onchain"]
    executed: bool
    transaction_ref: str | None = None
    network: str | None = None
    chain_id: int | None = None
    tx_hash: str | None = None
    explorer_url: str | None = None
    onchain_status: str | None = None
    contract_address: str | None = None
    token_address: str | None = None
    gas_used: int | None = None
    effective_gas_price: int | None = None
    payment_ref: str | None = None
    decoded_events: list[dict[str, Any]] | None = None
    split_executions: list[dict[str, Any]] | None = None
    executed_at: datetime | None = None
    message: str


class ConfirmSplitResult(BaseModel):
    sequence: int
    amount: float
    currency: str
    status: str
    tx_hash: str | None = None
    explorer_url: str | None = None
    onchain_status: str | None = None
    execution_tx_sent_at: datetime | None = None
    execution_tx_confirmed_at: datetime | None = None
    gas_used: int | None = None
    payment_ref: str | None = None


class ConfirmExecutionItemResult(BaseModel):
    execution_item_id: UUID
    onchain_execution_item_id: str | None = None
    sequence: int
    amount: float
    currency: str
    status: str
    tx_hash: str | None = None
    explorer_url: str | None = None
    nonce: int | None = None
    onchain_status: str | None = None
    submitted_at: datetime | None = None
    confirmed_at: datetime | None = None
    failure_reason: str | None = None


class ConfirmRiskResult(BaseModel):
    decision: str
    risk_level: str
    reason_codes: list[str]


class ConfirmResponse(BaseModel):
    status: Literal["ok", "declined", "blocked", "validation_error", "failed"]
    command_id: UUID
    execution_mode: Literal["operator", "user_wallet", "safe"]
    next_action: Literal[
        "confirm_now",
        "generate_unsigned_tx",
        "generate_safe_proposal",
        "sync_receipt",
        "none",
        "completed",
        "sign_in_wallet",
        "approve_in_safe",
    ] = "none"
    mode_specific_cta: str | None = None
    preview_summary: dict[str, Any] | None = None
    technical_details: dict[str, Any] | None = None
    payment_order_id: UUID | None = None
    execution_batch_id: UUID | None = None
    payment_status: str | None = None
    execution_status: str | None = None
    execution: MockExecutionResult | None = None
    splits: list[ConfirmSplitResult]
    execution_items: list[ConfirmExecutionItemResult] = []
    unsigned_transactions: list[dict[str, Any]] | None = None
    safe_proposal: dict[str, Any] | None = None
    risk: ConfirmRiskResult | None = None
    audit_trace_id: str
    message: str


class AttachExecutionItemTxRequest(BaseModel):
    tx_hash: str
    wallet_address: str | None = None
    submitted_at: datetime | None = None
    locale: str | None = None


class AttachExecutionItemSafeProposalRequest(BaseModel):
    safe_address: str | None = None
    proposal_id: str | None = None
    proposal_url: str | None = None
    proposer_wallet: str | None = None
    proposal_payload: dict[str, Any] | None = None
    submitted_at: datetime | None = None


class SyncExecutionItemReceiptRequest(BaseModel):
    actor_user_id: UUID | None = None
    force: bool = False


class ExecutionItemActionResponse(BaseModel):
    status: Literal["ok", "validation_error", "pending", "no_change"]
    execution_item_id: UUID
    execution_batch_id: UUID | None = None
    payment_order_id: UUID | None = None
    execution_mode: str | None = None
    item_status: str | None = None
    batch_status: str | None = None
    payment_status: str | None = None
    onchain_status: str | None = None
    tx_hash: str | None = None
    explorer_url: str | None = None
    total_items: int | None = None
    confirmed_items: int | None = None
    failed_items: int | None = None
    timeline: list[dict[str, Any]] | None = None
    next_action: Literal[
        "confirm_now",
        "generate_unsigned_tx",
        "generate_safe_proposal",
        "sync_receipt",
        "attach_tx",
        "approve_in_safe",
        "none",
    ] = "none"
    message: str


class ReconcileExecutionRequest(BaseModel):
    execution_batch_id: UUID | None = None
    limit: int = 20
    resume_planned: bool = False


class ReconcileExecutionBatchResult(BaseModel):
    execution_batch_id: UUID
    payment_order_id: UUID
    status: str
    confirmed_items: int
    failed_items: int
    pending_items: int
    message: str


class ReconcileExecutionResponse(BaseModel):
    status: Literal["ok", "partial", "failed"]
    scanned_batches: int
    reconciled_batches: int
    items: list[ReconcileExecutionBatchResult]
    message: str
