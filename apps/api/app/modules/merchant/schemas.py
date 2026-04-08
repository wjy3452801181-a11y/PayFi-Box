from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.audit.schemas import AuditTimelineItem
from app.modules.payments.schemas import (
    PaymentCoreDetails,
    PaymentExecutionBatchSummary,
    PaymentExecutionItemSummary,
    PaymentRiskCheckDetails,
)


class SettlementQuoteView(BaseModel):
    id: UUID
    merchant_id: UUID
    beneficiary_id: UUID
    source_currency: str
    source_amount: float
    target_currency: str
    target_amount: float
    target_network: str
    fx_rate: float
    platform_fee: float
    network_fee: float
    spread_bps: int
    total_fee_amount: float
    estimated_fee: float | None = None
    net_transfer_amount: float | None = None
    route: str | None = None
    eta_text: str | None = None
    expires_at: datetime
    status: str
    quote_payload_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class SettlementQuoteRequest(BaseModel):
    merchant_id: UUID
    beneficiary_id: UUID
    source_currency: str = Field(min_length=2, max_length=16)
    source_amount: float = Field(gt=0)
    target_currency: str = Field(default="USDT", min_length=2, max_length=16)
    target_network: str = Field(default="hashkey_testnet", min_length=2, max_length=32)


class SettlementQuoteResponse(BaseModel):
    status: Literal["ok"]
    quote: SettlementQuoteView
    next_action: Literal["create_fiat_payment_intent"]
    message: str


class FiatPaymentIntentView(BaseModel):
    id: UUID
    merchant_id: UUID
    beneficiary_id: UUID
    quote_id: UUID
    payer_currency: str
    payer_amount: float
    target_stablecoin: str
    target_amount: float
    target_network: str
    status: str
    payment_channel: str
    channel_payment_id: str | None = None
    channel_checkout_session_id: str | None = None
    channel_checkout_url: str | None = None
    channel_status: str | None = None
    channel_confirmed_at: datetime | None = None
    webhook_received_at: datetime | None = None
    next_action: str | None = None
    kyc_verification_id: UUID | None = None
    status_compat: str | None = None
    reference: str
    source_text: str | None = None
    payout_command_id: UUID | None = None
    metadata_json: dict[str, Any] | None = None
    bridge_state: str | None = None
    bridge_failure: dict[str, Any] | None = None
    is_recoverable_bridge_failure: bool = False
    created_at: datetime
    updated_at: datetime


class CreateFiatPaymentRequest(BaseModel):
    quote_id: UUID
    merchant_id: UUID
    beneficiary_id: UUID | None = None
    reference: str | None = None
    source_text: str | None = None
    split_count: int | None = Field(default=None, ge=1, le=20)


class FiatPaymentCollectionInstructions(BaseModel):
    collection_method: str
    note: str
    expected_currency: str
    expected_amount: float
    reference: str


class CreateFiatPaymentResponse(BaseModel):
    status: Literal["ok"]
    fiat_payment: FiatPaymentIntentView
    quote: SettlementQuoteView
    collection_instructions: FiatPaymentCollectionInstructions
    next_action: Literal["start_kyc", "create_stripe_session", "wait_channel_confirmation", "mark_fiat_received"]
    message: str


class CreateStripeSessionRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None
    locale: str | None = None


class CreateStripeSessionResponse(BaseModel):
    status: Literal["ok", "validation_error", "failed"]
    fiat_payment: FiatPaymentIntentView
    quote: SettlementQuoteView
    next_action: Literal["open_checkout", "complete_kyc", "none", "complete_stripe_payment"]
    checkout: dict[str, Any] | None = None
    message: str


class MarkFiatReceivedRequest(BaseModel):
    collection_method: str = Field(default="manual_bank_transfer", min_length=2, max_length=32)
    bank_reference: str | None = None
    received_amount: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=2, max_length=16)
    received_at: datetime | None = None
    confirmed_by_user_id: UUID | None = None
    execution_mode: Literal["operator", "user_wallet", "safe"] | None = None
    idempotency_key: str | None = None
    note: str | None = None
    locale: str | None = None
    demo_admin_override: bool = False


class FiatCollectionView(BaseModel):
    id: UUID
    fiat_payment_intent_id: UUID
    collection_method: str
    bank_reference: str | None = None
    received_amount: float
    currency: str
    received_at: datetime | None = None
    confirmed_by_user_id: UUID | None = None
    status: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class StablecoinPayoutLinkView(BaseModel):
    id: UUID
    fiat_payment_intent_id: UUID
    payment_order_id: UUID | None = None
    execution_batch_id: UUID | None = None
    status: str
    metadata_json: dict[str, Any] | None = None
    bridge_state: str | None = None
    bridge_failure: dict[str, Any] | None = None
    is_recoverable_bridge_failure: bool = False
    created_at: datetime
    updated_at: datetime


class MerchantPayoutStatusView(BaseModel):
    payment_order_id: UUID | None = None
    execution_batch_id: UUID | None = None
    payment_status: str | None = None
    execution_status: str | None = None
    onchain_status: str | None = None
    tx_hash: str | None = None
    explorer_url: str | None = None
    execution_mode: str | None = None


class MarkFiatReceivedResponse(BaseModel):
    status: Literal["ok", "validation_error", "failed"]
    fiat_payment: FiatPaymentIntentView
    quote: SettlementQuoteView
    fiat_collection: FiatCollectionView | None = None
    payout_link: StablecoinPayoutLinkView | None = None
    payout: MerchantPayoutStatusView
    message: str


class MerchantTimeline(BaseModel):
    count: int
    items: list[AuditTimelineItem]


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


class MerchantFiatPaymentDetailResponse(BaseModel):
    fiat_payment: FiatPaymentIntentView
    quote: SettlementQuoteView
    kyc_verification: KycVerificationView | None = None
    fiat_collection: FiatCollectionView | None = None
    payout_link: StablecoinPayoutLinkView | None = None
    payment_order: PaymentCoreDetails | None = None
    execution_batch: PaymentExecutionBatchSummary | None = None
    execution_items: list[PaymentExecutionItemSummary]
    risk_checks: list[PaymentRiskCheckDetails]
    timeline: MerchantTimeline


class MerchantFiatPaymentListItem(BaseModel):
    id: UUID
    merchant_id: UUID
    beneficiary_id: UUID
    quote_id: UUID
    payer_currency: str
    payer_amount: float
    target_stablecoin: str
    target_amount: float
    status: str
    payment_channel: str
    channel_status: str | None = None
    next_action: str | None = None
    kyc_verification_id: UUID | None = None
    reference: str
    payment_order_id: UUID | None = None
    execution_batch_id: UUID | None = None
    payout_status: str | None = None
    created_at: datetime
    updated_at: datetime


class MerchantFiatPaymentListResponse(BaseModel):
    total: int
    limit: int
    items: list[MerchantFiatPaymentListItem]
