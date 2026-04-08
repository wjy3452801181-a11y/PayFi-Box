from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


CommandIntent = Literal["create_payment", "query_payments", "generate_report", "unknown"]
ExecutionMode = Literal["operator", "user_wallet", "safe"]


class CommandRequest(BaseModel):
    session_id: UUID | None = None
    user_id: UUID
    text: str = Field(min_length=1, max_length=2000)
    execution_mode: ExecutionMode | None = None
    channel: str | None = None
    locale: str | None = None


class BeneficiaryPreview(BaseModel):
    id: UUID | None = None
    name: str
    country: str | None = None
    risk_level: str | None = None
    is_blacklisted: bool | None = None
    resolved: bool


class RiskPreview(BaseModel):
    decision: Literal["allow", "review", "block"]
    risk_level: Literal["low", "medium", "high"]
    reason_codes: list[str]
    user_message: str


class QuotePreview(BaseModel):
    estimated_fee: float
    net_transfer_amount: float | None = None
    route: str
    eta_text: str
    currency: str


class CommandPreviewSummary(BaseModel):
    recipient: str | None = None
    amount: float | None = None
    currency: str | None = None
    risk_level: str | None = None
    estimated_fee: float | None = None
    net_transfer: float | None = None


class CommandResponse(BaseModel):
    status: Literal["ok", "needs_clarification"]
    command_id: UUID
    session_id: UUID
    intent: CommandIntent
    confidence: float = Field(ge=0.0, le=1.0)
    preview: dict[str, Any]
    missing_fields: list[str]
    follow_up_question: str | None = None
    risk: RiskPreview | None = None
    quote: QuotePreview | None = None
    execution_mode: ExecutionMode = "operator"
    next_action: str
    mode_specific_cta: str | None = None
    preview_summary: CommandPreviewSummary | None = None
    technical_details: dict[str, Any] | None = None
    message: str
