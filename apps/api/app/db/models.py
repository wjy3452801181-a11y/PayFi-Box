import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UserRole(str, enum.Enum):
    RETAIL = "retail"
    TRADE_COMPANY = "trade_company"
    FINANCIAL_INSTITUTION = "financial_institution"


class OrganizationType(str, enum.Enum):
    TRADE_COMPANY = "trade_company"
    FINANCIAL_INSTITUTION = "financial_institution"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ABANDONED = "abandoned"


class CommandExecutionStatus(str, enum.Enum):
    RECEIVED = "received"
    PARSED = "parsed"
    READY = "ready"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    BLOCKED = "blocked"
    EXECUTED = "executed"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    QUOTED = "quoted"
    PENDING_CONFIRMATION = "pending_confirmation"
    APPROVED = "approved"
    PARTIALLY_EXECUTED = "partially_executed"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentSplitStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskCheckResult(str, enum.Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class ExecutionMode(str, enum.Enum):
    MOCK = "mock"
    SIMULATED = "simulated"
    ONCHAIN = "onchain"


class OnchainExecutionStatus(str, enum.Enum):
    PENDING_SUBMISSION = "pending_submission"
    SUBMITTED_ONCHAIN = "submitted_onchain"
    PARTIALLY_CONFIRMED_ONCHAIN = "partially_confirmed_onchain"
    CONFIRMED_ONCHAIN = "confirmed_onchain"
    FAILED_ONCHAIN = "failed_onchain"
    BLOCKED = "blocked"


class ExecutionRoute(str, enum.Enum):
    OPERATOR = "operator"
    USER_WALLET = "user_wallet"
    SAFE = "safe"


class PaymentExecutionBatchStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentExecutionItemStatus(str, enum.Enum):
    PLANNED = "planned"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class ReportJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SettlementQuoteStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"


class FiatPaymentIntentStatus(str, enum.Enum):
    CREATED = "created"
    AWAITING_KYC = "awaiting_kyc"
    AWAITING_CHANNEL_PAYMENT = "awaiting_channel_payment"
    PAYMENT_PROCESSING = "payment_processing"
    AWAITING_FIAT = "awaiting_fiat"
    FIAT_RECEIVED = "fiat_received"
    BRIDGE_FAILED_RECOVERABLE = "bridge_failed_recoverable"
    PAYOUT_IN_PROGRESS = "payout_in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class FiatCollectionStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class KycVerificationStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"
    REQUIRES_REVIEW = "requires_review"


class PlatformBalanceAccountStatus(str, enum.Enum):
    ACTIVE = "active"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


class PlatformBalanceLockStatus(str, enum.Enum):
    ACTIVE = "active"
    PARTIALLY_SETTLED = "partially_settled"
    RELEASED = "released"
    CONSUMED = "consumed"


class FiatDepositOrderStatus(str, enum.Enum):
    CREATED = "created"
    AWAITING_KYC = "awaiting_kyc"
    AWAITING_CHANNEL_PAYMENT = "awaiting_channel_payment"
    PAYMENT_PROCESSING = "payment_processing"
    FIAT_RECEIVED = "fiat_received"
    CONVERTED = "converted"
    CREDITED = "credited"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )


class Beneficiary(TimestampMixin, Base):
    __tablename__ = "beneficiaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    wallet_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bank_account_mock: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ConversationSession(TimestampMixin, Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="web")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class CommandExecution(TimestampMixin, Base):
    __tablename__ = "command_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation_sessions.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_intent_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tool_calls_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    final_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class PaymentOrder(TimestampMixin, Base):
    __tablename__ = "payment_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )
    beneficiary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.id"), nullable=False, index=True
    )
    source_command_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("command_executions.id"), nullable=True, index=True, unique=True
    )
    intent_source_text: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    funding_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="fiat_settlement")
    funding_reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    execution_route: Mapped[str] = mapped_column(String(32), nullable=False, default="operator", index=True)
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="mock")
    network: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chain_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onchain_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    explorer_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contract_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_tx_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_tx_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gas_used: Mapped[Decimal | None] = mapped_column(Numeric(38, 0), nullable=True)
    effective_gas_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 0), nullable=True)
    onchain_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PaymentSplit(TimestampMixin, Base):
    __tablename__ = "payment_splits"
    __table_args__ = (UniqueConstraint("payment_order_id", "sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_orders.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    explorer_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    onchain_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    execution_tx_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_tx_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gas_used: Mapped[Decimal | None] = mapped_column(Numeric(38, 0), nullable=True)


class PaymentExecutionBatch(Base):
    __tablename__ = "payment_execution_batches"
    __table_args__ = (
        UniqueConstraint("source_command_id", "idempotency_key", name="uq_payment_execution_batches_command_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_orders.id"), nullable=False, index=True
    )
    source_command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("command_executions.id"), nullable=False, index=True
    )
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class PaymentExecutionItem(Base):
    __tablename__ = "payment_execution_items"
    __table_args__ = (
        UniqueConstraint("execution_batch_id", "sequence"),
        CheckConstraint("tx_hash IS NULL OR tx_hash = lower(tx_hash)", name="ck_pei_tx_hash_lowercase"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_execution_batches.id"), nullable=False, index=True
    )
    payment_split_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_splits.id"), nullable=True, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    beneficiary_address: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    explorer_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nonce: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    onchain_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    pending_action: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PaymentQuote(TimestampMixin, Base):
    __tablename__ = "payment_quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_orders.id"), nullable=False, index=True
    )
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    route: Mapped[str] = mapped_column(String(128), nullable=False)
    eta_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    eta_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RiskCheck(TimestampMixin, Base):
    __tablename__ = "risk_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_orders.id"), nullable=False, index=True
    )
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    reason_codes_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReportJob(TimestampMixin, Base):
    __tablename__ = "report_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)


class SettlementQuote(TimestampMixin, Base):
    __tablename__ = "settlement_quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    beneficiary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.id"), nullable=False, index=True
    )
    source_currency: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_currency: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    target_network: Mapped[str] = mapped_column(String(32), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    network_fee: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    spread_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    total_fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True, default="active")
    quote_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class FiatPaymentIntent(TimestampMixin, Base):
    __tablename__ = "fiat_payment_intents"
    __table_args__ = (UniqueConstraint("quote_id", name="uq_fiat_payment_intents_quote_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    beneficiary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.id"), nullable=False, index=True
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("settlement_quotes.id"), nullable=False, index=True
    )
    payer_currency: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    payer_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_stablecoin: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    target_network: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="created")
    payment_channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="manual")
    channel_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, unique=True)
    channel_checkout_session_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, unique=True
    )
    channel_checkout_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    channel_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    channel_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    payout_command_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("command_executions.id"), nullable=True, index=True
    )
    kyc_verification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kyc_verifications.id"), nullable=True, index=True
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class FiatCollection(TimestampMixin, Base):
    __tablename__ = "fiat_collections"
    __table_args__ = (
        UniqueConstraint("fiat_payment_intent_id", name="uq_fiat_collections_payment_intent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fiat_payment_intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fiat_payment_intents.id"), nullable=False, index=True
    )
    collection_method: Mapped[str] = mapped_column(String(32), nullable=False)
    bank_reference: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    received_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True, default="pending")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class StablecoinPayoutLink(TimestampMixin, Base):
    __tablename__ = "stablecoin_payout_links"
    __table_args__ = (
        UniqueConstraint("fiat_payment_intent_id", name="uq_stablecoin_payout_links_intent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fiat_payment_intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fiat_payment_intents.id"), nullable=False, index=True
    )
    payment_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_orders.id"), nullable=True, index=True
    )
    execution_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_execution_batches.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="pending")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class KycVerification(TimestampMixin, Base):
    __tablename__ = "kyc_verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_verification_session_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="not_started")
    verification_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PlatformBalanceAccount(TimestampMixin, Base):
    __tablename__ = "platform_balance_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_platform_balance_accounts_user_currency"),
        CheckConstraint("available_balance >= 0", name="ck_platform_balance_accounts_available_nonnegative"),
        CheckConstraint("locked_balance >= 0", name="ck_platform_balance_accounts_locked_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    currency: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=0)
    locked_balance: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="active")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PlatformBalanceLedgerEntry(Base):
    __tablename__ = "platform_balance_ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_balance_accounts.id"), nullable=False, index=True
    )
    entry_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class PlatformBalanceLock(TimestampMixin, Base):
    __tablename__ = "platform_balance_locks"
    __table_args__ = (
        UniqueConstraint("command_id", name="uq_platform_balance_locks_command_id"),
        UniqueConstraint("payment_order_id", name="uq_platform_balance_locks_payment_order_id"),
        CheckConstraint("locked_amount > 0", name="ck_platform_balance_locks_locked_positive"),
        CheckConstraint("released_amount >= 0", name="ck_platform_balance_locks_released_nonnegative"),
        CheckConstraint("consumed_amount >= 0", name="ck_platform_balance_locks_consumed_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_balance_accounts.id"), nullable=False, index=True
    )
    command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("command_executions.id"), nullable=False, index=True
    )
    payment_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_orders.id"), nullable=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    locked_amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    released_amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=0)
    consumed_amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="active")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class FiatDepositOrder(TimestampMixin, Base):
    __tablename__ = "fiat_deposit_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    source_currency: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_currency: Mapped[str] = mapped_column(String(16), nullable=False, index=True, default="USDT")
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    payment_channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="stripe")
    channel_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, unique=True)
    channel_checkout_session_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, unique=True
    )
    channel_checkout_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    channel_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    channel_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kyc_verification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kyc_verifications.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="created")
    next_action: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
