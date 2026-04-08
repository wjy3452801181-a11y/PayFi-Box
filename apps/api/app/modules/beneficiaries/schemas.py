from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BeneficiaryListItem(BaseModel):
    beneficiary_id: UUID
    name: str
    country: str
    risk_level: str
    is_blacklisted: bool
    organization_id: UUID | None = None
    has_wallet_address: bool
    payment_count: int
    latest_payment_at: datetime | None = None


class BeneficiaryListFilters(BaseModel):
    country: str | None = None
    risk_level: str | None = None
    is_blacklisted: bool | None = None
    name: str | None = None
    organization_id: UUID | None = None


class BeneficiaryListResponse(BaseModel):
    total: int
    limit: int
    filters: BeneficiaryListFilters
    items: list[BeneficiaryListItem]


class BeneficiaryCoreDetails(BaseModel):
    beneficiary_id: UUID
    name: str
    country: str
    risk_level: str
    is_blacklisted: bool
    organization_id: UUID | None = None
    wallet_address: str | None = None
    bank_account_mock: str | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class BeneficiaryStats(BaseModel):
    total_payments: int
    total_payment_volume: float
    executed_payments: int
    failed_payments: int
    latest_payment_at: datetime | None = None


class BeneficiaryRecentPayment(BaseModel):
    payment_order_id: UUID
    created_at: datetime
    amount: float
    currency: str
    status: str
    risk_level: str
    reference: str
    source_command_id: UUID | None = None


class BeneficiaryRiskProfile(BaseModel):
    risk_level: str
    is_blacklisted: bool
    reason_codes: list[str]
    message: str


class BeneficiaryDetailResponse(BaseModel):
    beneficiary: BeneficiaryCoreDetails
    stats: BeneficiaryStats
    recent_payments: list[BeneficiaryRecentPayment]
    risk_profile: BeneficiaryRiskProfile


class BeneficiaryPatchRequest(BaseModel):
    wallet_address: str | None = None
