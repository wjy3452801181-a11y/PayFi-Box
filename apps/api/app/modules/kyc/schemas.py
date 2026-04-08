from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class KycVerificationView(BaseModel):
    id: UUID
    subject_type: str
    subject_id: UUID
    provider: str
    provider_verification_session_id: str | None = None
    status: str
    verification_url: str | None = None
    verified_at: datetime | None = None
    failure_reason: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class KycStartRequest(BaseModel):
    subject_type: Literal["merchant", "user"] = "merchant"
    subject_id: UUID
    provider: Literal["stripe_identity"] = "stripe_identity"
    locale: str | None = None
    force_new: bool = False


class KycStartResponse(BaseModel):
    status: Literal["ok", "validation_error", "failed"]
    verification: KycVerificationView | None = None
    next_action: Literal["complete_kyc", "none"]
    message: str


class KycDetailResponse(BaseModel):
    status: Literal["ok"]
    verification: KycVerificationView
