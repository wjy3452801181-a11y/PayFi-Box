from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.command.schemas import CommandResponse
from app.modules.confirm.schemas import ConfirmResponse


class PlatformBalanceAccountView(BaseModel):
    id: UUID
    user_id: UUID
    currency: str
    available_balance: float
    locked_balance: float
    status: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class PlatformBalanceLedgerEntryView(BaseModel):
    id: UUID
    account_id: UUID
    entry_type: str
    amount: float
    balance_before: float
    balance_after: float
    reference_type: str | None = None
    reference_id: UUID | None = None
    description: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime


class PlatformBalanceLockView(BaseModel):
    id: UUID
    account_id: UUID
    command_id: UUID
    payment_order_id: UUID | None = None
    currency: str
    locked_amount: float
    consumed_amount: float
    released_amount: float
    status: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class FiatDepositOrderView(BaseModel):
    id: UUID
    user_id: UUID
    source_currency: str
    source_amount: float
    target_currency: str
    target_amount: float
    fx_rate: float
    fee_amount: float
    payment_channel: str
    channel_payment_id: str | None = None
    channel_checkout_session_id: str | None = None
    channel_checkout_url: str | None = None
    channel_status: str | None = None
    channel_confirmed_at: datetime | None = None
    webhook_received_at: datetime | None = None
    kyc_verification_id: UUID | None = None
    status: str
    next_action: str | None = None
    reference: str
    failure_reason: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class CreateFiatDepositRequest(BaseModel):
    user_id: UUID
    source_currency: str = Field(min_length=2, max_length=16)
    source_amount: float = Field(gt=0)
    target_currency: str = Field(default="USDT", min_length=2, max_length=16)
    reference: str | None = None


class CreateFiatDepositResponse(BaseModel):
    status: Literal["ok"]
    deposit_order: FiatDepositOrderView
    next_action: Literal["complete_kyc", "start_stripe_payment"]
    message: str


class StartDepositStripePaymentRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None
    locale: str | None = None


class StartDepositStripePaymentResponse(BaseModel):
    status: Literal["ok", "validation_error", "failed"]
    deposit_order: FiatDepositOrderView
    next_action: Literal["open_checkout", "complete_kyc", "wait_channel_confirmation", "none"]
    checkout: dict[str, Any] | None = None
    message: str


class DepositDetailResponse(BaseModel):
    deposit_order: FiatDepositOrderView
    account: PlatformBalanceAccountView | None = None
    latest_ledger_entry: PlatformBalanceLedgerEntryView | None = None


class PlatformBalanceAccountResponse(BaseModel):
    account: PlatformBalanceAccountView


class PlatformBalanceLedgerResponse(BaseModel):
    account: PlatformBalanceAccountView
    total: int
    limit: int
    items: list[PlatformBalanceLedgerEntryView]


class BalanceCheckSummary(BaseModel):
    currency: str
    available_balance: float
    locked_balance: float
    required_amount: float | None = None
    sufficient: bool
    reason: str | None = None


class BalancePaymentPreviewRequest(BaseModel):
    user_id: UUID
    prompt: str = Field(min_length=1, max_length=2000)
    execution_mode: Literal["operator", "user_wallet", "safe"] | None = None
    locale: str | None = None


class BalancePaymentPreviewResponse(CommandResponse):
    funding_source: Literal["platform_balance"] = "platform_balance"
    balance_account: PlatformBalanceAccountView | None = None
    balance_check: BalanceCheckSummary | None = None


class BalancePaymentConfirmRequest(BaseModel):
    user_id: UUID
    command_id: UUID
    execution_mode: Literal["operator", "user_wallet", "safe"] | None = None
    idempotency_key: str | None = None
    locale: str | None = None
    note: str | None = None


class BalancePaymentConfirmResponse(ConfirmResponse):
    funding_source: Literal["platform_balance"] = "platform_balance"
    balance_account: PlatformBalanceAccountView | None = None
    balance_lock: PlatformBalanceLockView | None = None
