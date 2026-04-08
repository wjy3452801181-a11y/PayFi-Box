from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.modules.audit.schemas import AuditTimelineItem


class PaymentBeneficiarySummary(BaseModel):
    id: UUID | None = None
    name: str | None = None
    country: str | None = None
    risk_level: str | None = None
    is_blacklisted: bool | None = None


class PaymentExecutionSplitSummary(BaseModel):
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


class PaymentExecutionBatchSummary(BaseModel):
    id: UUID
    execution_mode: str
    idempotency_key: str
    status: str
    requested_by_user_id: UUID
    total_items: int = 0
    confirmed_items: int = 0
    failed_items: int = 0
    submitted_items: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime


class PaymentExecutionItemEventSummary(BaseModel):
    event_count: int = 0
    latest_action: str | None = None
    latest_timestamp: datetime | None = None


class PaymentExecutionItemSummary(BaseModel):
    id: UUID
    onchain_execution_item_id: str | None = None
    payment_split_id: UUID | None = None
    execution_mode: str | None = None
    sequence: int
    amount: float
    currency: str
    beneficiary_address: str
    status: str
    tx_hash: str | None = None
    explorer_url: str | None = None
    nonce: int | None = None
    submitted_at: datetime | None = None
    confirmed_at: datetime | None = None
    failure_reason: str | None = None
    onchain_status: str | None = None
    is_duplicate_rejected: bool = False
    duplicate_reason: str | None = None
    pending_action: str | None = None
    unsigned_tx_request: dict[str, Any] | None = None
    safe_proposal_request: dict[str, Any] | None = None
    safe_proposal_attachment: dict[str, Any] | None = None
    tx_attachment: dict[str, Any] | None = None
    decoded_events: list[dict[str, Any]] | None = None
    event_summary: PaymentExecutionItemEventSummary | None = None


class PaymentExecutionSummary(BaseModel):
    execution_route: str | None = None
    mode: str
    executed: bool
    status: str
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
    split_executions: list[PaymentExecutionSplitSummary] | None = None
    executed_at: datetime | None = None
    message: str | None = None


class PaymentListItem(BaseModel):
    id: UUID
    payment_order_id: UUID
    created_at: datetime
    user_id: UUID
    organization_id: UUID | None = None
    beneficiary: PaymentBeneficiarySummary
    beneficiary_name: str | None = None
    beneficiary_country: str | None = None
    amount: float
    currency: str
    status: str
    funding_source: str | None = None
    funding_reference_id: UUID | None = None
    risk_level: str
    requires_confirmation: bool
    execution_route: str | None = None
    execution_mode: str
    reference: str
    source_command_id: UUID | None = None
    trace_id: str | None = None
    audit_trace_id: str | None = None
    split_count: int
    mock_execution_executed: bool
    onchain_status: str | None = None
    tx_hash: str | None = None
    explorer_url: str | None = None
    execution_summary: PaymentExecutionSummary


class PaymentListFilters(BaseModel):
    status: str | None = None
    risk_level: str | None = None
    user_id: UUID | None = None
    organization_id: UUID | None = None
    beneficiary_name: str | None = None


class PaymentListSort(BaseModel):
    sort_by: str
    sort_order: str


class PaymentListResponse(BaseModel):
    total: int
    limit: int
    filters: PaymentListFilters
    sort: PaymentListSort
    items: list[PaymentListItem]


class PaymentCoreDetails(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    user_id: UUID
    organization_id: UUID | None = None
    beneficiary_id: UUID
    source_command_id: UUID | None = None
    intent_source_text: str
    amount: float
    currency: str
    status: str
    funding_source: str | None = None
    funding_reference_id: UUID | None = None
    risk_level: str
    requires_confirmation: bool
    execution_route: str | None = None
    execution_mode: str
    network: str | None = None
    chain_id: int | None = None
    onchain_status: str | None = None
    tx_hash: str | None = None
    explorer_url: str | None = None
    contract_address: str | None = None
    token_address: str | None = None
    execution_tx_sent_at: datetime | None = None
    execution_tx_confirmed_at: datetime | None = None
    gas_used: int | None = None
    effective_gas_price: int | None = None
    onchain_payload_json: dict[str, Any] | None = None
    reference: str
    metadata_json: dict[str, Any] | None = None


class PaymentBeneficiaryDetails(PaymentBeneficiarySummary):
    organization_id: UUID | None = None
    wallet_address: str | None = None
    bank_account_mock: str | None = None
    metadata_json: dict[str, Any] | None = None


class PaymentSplitDetails(BaseModel):
    id: UUID
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
    created_at: datetime
    updated_at: datetime


class PaymentRiskCheckDetails(BaseModel):
    id: UUID
    check_type: str
    result: str
    score: float | None = None
    reason_codes: list[str]
    normalized_reason_codes: list[str]
    raw_payload_json: dict[str, Any] | None = None
    created_at: datetime


class PaymentCommandDetails(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    raw_text: str
    intent: str | None = None
    final_status: str
    trace_id: str
    created_at: datetime


class PaymentAuditSummary(BaseModel):
    trace_id: str | None = None
    count: int
    items: list[AuditTimelineItem]


class PaymentTimelineSummary(BaseModel):
    count: int
    latest_action: str | None = None
    latest_timestamp: datetime | None = None
    has_duplicate_rejection: bool = False
    has_partial_failure: bool = False
    has_reconciliation: bool = False


class PaymentDetailResponse(BaseModel):
    payment: PaymentCoreDetails
    beneficiary: PaymentBeneficiaryDetails | None = None
    splits: list[PaymentSplitDetails]
    execution_batch: PaymentExecutionBatchSummary | None = None
    execution_items: list[PaymentExecutionItemSummary]
    risk_checks: list[PaymentRiskCheckDetails]
    command: PaymentCommandDetails | None = None
    execution: PaymentExecutionSummary
    audit: PaymentAuditSummary
    timeline_summary: PaymentTimelineSummary | None = None


class RetryMockRequest(BaseModel):
    actor_user_id: UUID | None = None
    note: str | None = None


class RetryMockResponse(BaseModel):
    status: Literal["ok", "not_needed", "non_retriable", "validation_error"]
    payment_order_id: UUID
    previous_status: str
    payment_status: str
    retry_performed: bool
    execution: PaymentExecutionSummary | None = None
    audit_trace_id: str
    message: str
