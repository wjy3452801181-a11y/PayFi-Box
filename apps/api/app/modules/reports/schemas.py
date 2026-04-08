from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class ReportSummaryFilters(BaseModel):
    user_id: UUID | None = None
    organization_id: UUID | None = None
    country: str | None = None
    currency: str | None = None
    risk_level: str | None = None
    status: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class ReportSummaryMetrics(BaseModel):
    total_payments: int
    total_volume: float
    risky_payments: int
    executed_payments: int
    failed_payments: int


class GroupedSummaryItem(BaseModel):
    key: str
    count: int
    volume: float


class RiskDecisionSummaryItem(BaseModel):
    decision: str
    count: int


class RiskReasonCodeSummaryItem(BaseModel):
    reason_code: str
    count: int


class HighRiskSampleItem(BaseModel):
    id: UUID
    created_at: datetime
    beneficiary_name: str
    beneficiary_country: str
    amount: float
    currency: str
    status: str
    risk_level: str
    reference: str


class ReportJobPreview(BaseModel):
    id: UUID
    user_id: UUID
    report_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    summary_text: str | None = None


class ReportCommandPreview(BaseModel):
    command_id: UUID
    created_at: datetime
    user_id: UUID
    session_id: UUID
    intent: str | None = None
    final_status: str
    trace_id: str
    raw_text: str


class ReportSummaryResponse(BaseModel):
    generated_at: datetime
    filters: ReportSummaryFilters
    metrics: ReportSummaryMetrics
    by_country: list[GroupedSummaryItem]
    by_currency: list[GroupedSummaryItem]
    by_status: list[GroupedSummaryItem]
    by_risk_level: list[GroupedSummaryItem]
    by_risk_decision: list[RiskDecisionSummaryItem]
    by_risk_reason_code: list[RiskReasonCodeSummaryItem]
    high_risk_samples: list[HighRiskSampleItem]
    latest_commands: list[ReportCommandPreview]
    latest_report_jobs: list[ReportJobPreview]
