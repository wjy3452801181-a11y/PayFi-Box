from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.modules.audit.schemas import AuditTimelineItem


class CommandListPreviewSummary(BaseModel):
    recipient: str | None = None
    amount: float | None = None
    currency: str | None = None
    reference: str | None = None
    missing_fields: list[str]


class CommandRiskSummary(BaseModel):
    decision: str
    risk_level: str
    reason_codes: list[str]
    user_message: str


class CommandQuoteSummary(BaseModel):
    estimated_fee: float
    route: str
    eta_text: str
    currency: str


class CommandListItem(BaseModel):
    command_id: UUID
    created_at: datetime
    user_id: UUID
    session_id: UUID
    raw_text: str
    intent: str | None = None
    confidence: float | None = None
    final_status: str
    trace_id: str
    preview_summary: CommandListPreviewSummary | None = None
    resulted_in_payment: bool
    linked_payment_order_id: UUID | None = None
    linked_payment_order_count: int
    risk_summary: CommandRiskSummary | None = None
    next_action: str | None = None


class CommandListFilters(BaseModel):
    intent: str | None = None
    final_status: str | None = None
    user_id: UUID | None = None
    session_id: UUID | None = None


class CommandListSort(BaseModel):
    sort_by: str
    sort_order: str


class CommandListResponse(BaseModel):
    total: int
    limit: int
    filters: CommandListFilters
    sort: CommandListSort
    items: list[CommandListItem]


class LinkedPaymentSummary(BaseModel):
    payment_order_id: UUID
    status: str
    amount: float
    currency: str
    risk_level: str
    reference: str
    created_at: datetime


class LinkedBeneficiarySummary(BaseModel):
    beneficiary_id: UUID | None = None
    name: str | None = None
    country: str | None = None
    risk_level: str | None = None
    is_blacklisted: bool | None = None
    resolved: bool | None = None


class CommandCoreDetails(BaseModel):
    command_id: UUID
    created_at: datetime
    updated_at: datetime
    user_id: UUID
    session_id: UUID
    raw_text: str
    intent: str | None = None
    confidence: float | None = None
    final_status: str
    trace_id: str


class CommandParsedDetails(BaseModel):
    parsed_intent_json: dict[str, Any] | None = None
    tool_calls_json: list[dict[str, Any]] | None = None


class CommandAuditSummary(BaseModel):
    trace_id: str | None = None
    count: int
    items: list[AuditTimelineItem]


class CommandDetailResponse(BaseModel):
    command: CommandCoreDetails
    parsed: CommandParsedDetails
    risk: CommandRiskSummary | None = None
    quote: CommandQuoteSummary | None = None
    linked_payment: LinkedPaymentSummary | None = None
    linked_beneficiary: LinkedBeneficiarySummary | None = None
    audit: CommandAuditSummary
