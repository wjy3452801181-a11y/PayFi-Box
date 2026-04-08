from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    Base,
    Beneficiary,
    CommandExecution,
    CommandExecutionStatus,
    ConversationSession,
    ExecutionMode,
    Organization,
    OrganizationType,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentQuote,
    PaymentSplit,
    PaymentSplitStatus,
    ReportJob,
    ReportJobStatus,
    RiskCheck,
    RiskCheckResult,
    RiskLevel,
    SessionStatus,
    User,
    UserRole,
)
from app.db.session import get_db_session, get_engine

SEED_NAMESPACE = uuid.UUID("4f78f387-47a6-4ec1-a9f9-e1ecfe2f0844")


def _sid(name: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, name)


def _d(value: str) -> Decimal:
    return Decimal(value)


def _apply_deterministic_timestamps(
    records: list[dict[str, Any]],
    *,
    base_time: datetime,
    step_minutes: int,
) -> None:
    for index, record in enumerate(records):
        created_at = base_time + timedelta(minutes=index * step_minutes)
        record.setdefault("created_at", created_at)
        record.setdefault("updated_at", created_at)


def _upsert_many(session: Session, model: type, records: list[dict[str, Any]]) -> None:
    for record in records:
        session.merge(model(**record))


def _clear_all_data(session: Session) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())


def seed_demo_data(*, reset: bool = False) -> dict[str, int]:
    organizations = [
        {
            "id": _sid("org.trade.acme"),
            "name": "ACME Trade Ltd.",
            "type": OrganizationType.TRADE_COMPANY.value,
            "country": "SG",
        },
        {
            "id": _sid("org.fi.globebank"),
            "name": "GlobeBank Compliance Center",
            "type": OrganizationType.FINANCIAL_INSTITUTION.value,
            "country": "GB",
        },
    ]

    users = [
        {
            "id": _sid("user.retail.lin"),
            "name": "Lin Xiaoyu",
            "email": "lin.retail@payfi.demo",
            "role": UserRole.RETAIL.value,
            "organization_id": None,
        },
        {
            "id": _sid("user.trade.chen"),
            "name": "Chen Wei",
            "email": "chen.trade@payfi.demo",
            "role": UserRole.TRADE_COMPANY.value,
            "organization_id": _sid("org.trade.acme"),
        },
        {
            "id": _sid("user.fi.wang"),
            "name": "Wang Analyst",
            "email": "wang.analyst@payfi.demo",
            "role": UserRole.FINANCIAL_INSTITUTION.value,
            "organization_id": _sid("org.fi.globebank"),
        },
    ]
    user_id_by_key = {
        "retail_user": users[0]["id"],
        "trade_operator": users[1]["id"],
        "institution_analyst": users[2]["id"],
    }

    beneficiaries = [
        {
            "id": _sid("bene.lucy"),
            "organization_id": None,
            "name": "Lucy Carter",
            "country": "US",
            "wallet_address": "0x1111111111111111111111111111111111111111",
            "bank_account_mock": None,
            "risk_level": RiskLevel.LOW.value,
            "is_blacklisted": False,
            "metadata_json": {"category": "retail_friend", "note": "same-day transfer"},
        },
        {
            "id": _sid("bene.acme.supplier"),
            "organization_id": _sid("org.trade.acme"),
            "name": "ACME Supplier Group",
            "country": "MY",
            "wallet_address": "0xef724df77c65affc8c3a67ae0db0add344f607b3",
            "bank_account_mock": "MY-ACME-0091-2221",
            "risk_level": RiskLevel.MEDIUM.value,
            "is_blacklisted": False,
            "metadata_json": {"category": "supplier", "invoice_policy": "required"},
        },
        {
            "id": _sid("bene.oceanic.parts"),
            "organization_id": _sid("org.trade.acme"),
            "name": "Oceanic Parts FZE",
            "country": "AE",
            "wallet_address": "0x2222222222222222222222222222222222222222",
            "bank_account_mock": "AE-OCE-8891-2229",
            "risk_level": RiskLevel.HIGH.value,
            "is_blacklisted": False,
            "metadata_json": {"category": "cross_border_supplier"},
        },
        {
            "id": _sid("bene.shadow.node"),
            "organization_id": None,
            "name": "Shadow Node Labs",
            "country": "RU",
            "wallet_address": "0x3333333333333333333333333333333333333333",
            "bank_account_mock": "RU-SHD-7711-0082",
            "risk_level": RiskLevel.HIGH.value,
            "is_blacklisted": True,
            "metadata_json": {"category": "watchlist", "reason": "sanctions_match"},
        },
        {
            "id": _sid("bene.retail.david"),
            "organization_id": None,
            "name": "David Chen",
            "country": "CN",
            "wallet_address": None,
            "bank_account_mock": "CN-DAV-2211-7600",
            "risk_level": RiskLevel.LOW.value,
            "is_blacklisted": False,
            "metadata_json": {"category": "retail_recipient"},
        },
        {
            "id": _sid("bene.euro.supply"),
            "organization_id": _sid("org.trade.acme"),
            "name": "EuroSupply GmbH",
            "country": "DE",
            "wallet_address": None,
            "bank_account_mock": "DE-EUR-9910-2203",
            "risk_level": RiskLevel.MEDIUM.value,
            "is_blacklisted": False,
            "metadata_json": {"category": "eu_supplier"},
        },
    ]

    sessions = [
        {
            "id": _sid("session.retail.web"),
            "user_id": _sid("user.retail.lin"),
            "channel": "web",
            "status": SessionStatus.ACTIVE.value,
        },
        {
            "id": _sid("session.trade.console"),
            "user_id": _sid("user.trade.chen"),
            "channel": "web",
            "status": SessionStatus.ACTIVE.value,
        },
        {
            "id": _sid("session.fi.console"),
            "user_id": _sid("user.fi.wang"),
            "channel": "web",
            "status": SessionStatus.ACTIVE.value,
        },
        {
            "id": _sid("session.trade.mobile"),
            "user_id": _sid("user.trade.chen"),
            "channel": "mobile",
            "status": SessionStatus.CLOSED.value,
        },
        {
            "id": _sid("session.retail.mobile"),
            "user_id": _sid("user.retail.lin"),
            "channel": "mobile",
            "status": SessionStatus.ABANDONED.value,
        },
    ]

    command_executions = [
        {
            "id": _sid("command.001"),
            "session_id": _sid("session.retail.web"),
            "user_id": _sid("user.retail.lin"),
            "raw_text": "帮我给 Lucy 转 120 USDC，今晚到账，手续费最低",
            "parsed_intent_json": {
                "intent": "create_payment",
                "amount": "120",
                "currency": "USDC",
                "beneficiary": "Lucy Carter",
            },
            "tool_calls_json": [{"tool": "quote_engine", "status": "ok"}],
            "final_status": CommandExecutionStatus.COMPLETED.value,
            "trace_id": "trace-retail-001",
        },
        {
            "id": _sid("command.002"),
            "session_id": _sid("session.trade.console"),
            "user_id": _sid("user.trade.chen"),
            "raw_text": "给 ACME 支付 30000 USDT，拆成 3 笔，备注 INV-009",
            "parsed_intent_json": {
                "intent": "supplier_payment",
                "amount": "30000",
                "currency": "USDT",
                "splits": 3,
                "reference": "INV-009",
            },
            "tool_calls_json": [
                {"tool": "policy_precheck", "status": "ok"},
                {"tool": "quote_engine", "status": "ok"},
            ],
            "final_status": CommandExecutionStatus.COMPLETED.value,
            "trace_id": "trace-trade-009",
        },
        {
            "id": _sid("command.003"),
            "session_id": _sid("session.fi.console"),
            "user_id": _sid("user.fi.wang"),
            "raw_text": "查询上周跨境收款，按国家分类，并标出高风险交易",
            "parsed_intent_json": {
                "intent": "report_query",
                "time_range": "last_week",
                "group_by": "country",
                "highlight": "high_risk",
            },
            "tool_calls_json": [{"tool": "report_builder", "status": "ok"}],
            "final_status": CommandExecutionStatus.COMPLETED.value,
            "trace_id": "trace-report-001",
        },
        {
            "id": _sid("command.004"),
            "session_id": _sid("session.trade.console"),
            "user_id": _sid("user.trade.chen"),
            "raw_text": "向迪拜 Oceanic Parts 付款 86000 USD，优先今天出款",
            "parsed_intent_json": {
                "intent": "cross_border_payment",
                "amount": "86000",
                "currency": "USD",
                "priority": "high",
            },
            "tool_calls_json": [{"tool": "risk_engine", "status": "review"}],
            "final_status": CommandExecutionStatus.READY.value,
            "trace_id": "trace-trade-010",
        },
        {
            "id": _sid("command.005"),
            "session_id": _sid("session.trade.mobile"),
            "user_id": _sid("user.trade.chen"),
            "raw_text": "给 Shadow Node 转 120000 USDT，尽快执行",
            "parsed_intent_json": {
                "intent": "cross_border_payment",
                "amount": "120000",
                "currency": "USDT",
                "beneficiary": "Shadow Node Labs",
            },
            "tool_calls_json": [{"tool": "sanctions_check", "status": "block"}],
            "final_status": CommandExecutionStatus.BLOCKED.value,
            "trace_id": "trace-trade-011",
        },
        {
            "id": _sid("command.006"),
            "session_id": _sid("session.retail.mobile"),
            "user_id": _sid("user.retail.lin"),
            "raw_text": "给隔壁小王转 88 CNY，晚饭AA",
            "parsed_intent_json": {
                "intent": "payment_transfer",
                "amount": "88",
                "currency": "CNY",
                "beneficiary": "David Chen",
            },
            "tool_calls_json": [{"tool": "quote_engine", "status": "ok"}],
            "final_status": CommandExecutionStatus.PARSED.value,
            "trace_id": "trace-retail-002",
        },
        {
            "id": _sid("command.007"),
            "session_id": _sid("session.trade.console"),
            "user_id": _sid("user.trade.chen"),
            "raw_text": "向 EuroSupply GmbH 支付 45000 EUR，路线走 SEPA",
            "parsed_intent_json": {
                "intent": "supplier_payment",
                "amount": "45000",
                "currency": "EUR",
                "route_hint": "SEPA",
            },
            "tool_calls_json": [{"tool": "route_selector", "status": "ok"}],
            "final_status": CommandExecutionStatus.COMPLETED.value,
            "trace_id": "trace-trade-012",
        },
        {
            "id": _sid("command.008"),
            "session_id": _sid("session.trade.console"),
            "user_id": _sid("user.trade.chen"),
            "raw_text": "给 Oceanic Parts 15750 USD，拆成两笔，今天和明天各一笔",
            "parsed_intent_json": {
                "intent": "split_payment",
                "amount": "15750",
                "currency": "USD",
                "splits": 2,
            },
            "tool_calls_json": [{"tool": "split_planner", "status": "ok"}],
            "final_status": CommandExecutionStatus.READY.value,
            "trace_id": "trace-trade-013",
        },
        {
            "id": _sid("command.009"),
            "session_id": _sid("session.fi.console"),
            "user_id": _sid("user.fi.wang"),
            "raw_text": "生成本周高风险付款复核清单",
            "parsed_intent_json": {
                "intent": "report_job",
                "report_type": "high_risk_review",
                "time_range": "this_week",
            },
            "tool_calls_json": [{"tool": "report_builder", "status": "running"}],
            "final_status": CommandExecutionStatus.READY.value,
            "trace_id": "trace-report-002",
        },
    ]

    payment_orders = [
        {
            "id": _sid("po.001"),
            "user_id": _sid("user.retail.lin"),
            "organization_id": None,
            "beneficiary_id": _sid("bene.lucy"),
            "source_command_id": _sid("command.001"),
            "intent_source_text": "帮我给 Lucy 转 120 USDC，今晚到账，手续费最低",
            "amount": _d("120.00"),
            "currency": "USDC",
            "status": PaymentOrderStatus.EXECUTED.value,
            "reference": "RET-202603-001",
            "risk_level": RiskLevel.LOW.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.MOCK.value,
            "metadata_json": {"scenario": "retail_transfer"},
        },
        {
            "id": _sid("po.002"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.acme.supplier"),
            "source_command_id": None,
            "intent_source_text": "给 ACME 支付 30000 USDT，拆成 3 笔，备注 INV-009",
            "amount": _d("30000.00"),
            "currency": "USDT",
            "status": PaymentOrderStatus.QUOTED.value,
            "reference": "INV-009-A",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"invoice": "INV-009", "batch": 1},
        },
        {
            "id": _sid("po.003"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.acme.supplier"),
            "source_command_id": None,
            "intent_source_text": "给 ACME 支付 30000 USDT，拆成 3 笔，备注 INV-009",
            "amount": _d("30000.00"),
            "currency": "USDT",
            "status": PaymentOrderStatus.PENDING_CONFIRMATION.value,
            "reference": "INV-009-B",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"invoice": "INV-009", "batch": 2},
        },
        {
            "id": _sid("po.004"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.acme.supplier"),
            "source_command_id": _sid("command.002"),
            "intent_source_text": "给 ACME 支付 30000 USDT，拆成 3 笔，备注 INV-009",
            "amount": _d("30000.00"),
            "currency": "USDT",
            "status": PaymentOrderStatus.APPROVED.value,
            "reference": "INV-009-C",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"invoice": "INV-009", "batch": 3},
        },
        {
            "id": _sid("po.005"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.oceanic.parts"),
            "source_command_id": _sid("command.004"),
            "intent_source_text": "向迪拜 Oceanic Parts 付款 86000 USD，优先今天出款",
            "amount": _d("86000.00"),
            "currency": "USD",
            "status": PaymentOrderStatus.FAILED.value,
            "reference": "CB-202603-001",
            "risk_level": RiskLevel.HIGH.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"corridor": "SG-AE", "priority": "high"},
        },
        {
            "id": _sid("po.006"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.shadow.node"),
            "source_command_id": _sid("command.005"),
            "intent_source_text": "给 Shadow Node 转 120000 USDT，尽快执行",
            "amount": _d("120000.00"),
            "currency": "USDT",
            "status": PaymentOrderStatus.CANCELLED.value,
            "reference": "CB-202603-002",
            "risk_level": RiskLevel.HIGH.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"corridor": "SG-RU", "blocked": True},
        },
        {
            "id": _sid("po.007"),
            "user_id": _sid("user.retail.lin"),
            "organization_id": None,
            "beneficiary_id": _sid("bene.retail.david"),
            "source_command_id": _sid("command.006"),
            "intent_source_text": "给隔壁小王转 88 CNY，晚饭AA",
            "amount": _d("88.00"),
            "currency": "CNY",
            "status": PaymentOrderStatus.DRAFT.value,
            "reference": "RET-202603-002",
            "risk_level": RiskLevel.LOW.value,
            "requires_confirmation": False,
            "execution_mode": ExecutionMode.MOCK.value,
            "metadata_json": {"scenario": "aa_dinner"},
        },
        {
            "id": _sid("po.008"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.euro.supply"),
            "source_command_id": _sid("command.007"),
            "intent_source_text": "向 EuroSupply GmbH 支付 45000 EUR，路线走 SEPA",
            "amount": _d("45000.00"),
            "currency": "EUR",
            "status": PaymentOrderStatus.EXECUTED.value,
            "reference": "EU-202603-001",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"route_hint": "SEPA"},
        },
        {
            "id": _sid("po.009"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.oceanic.parts"),
            "source_command_id": _sid("command.008"),
            "intent_source_text": "给 Oceanic Parts 15750 USD，拆成两笔，今天和明天各一笔",
            "amount": _d("15750.00"),
            "currency": "USD",
            "status": PaymentOrderStatus.QUOTED.value,
            "reference": "CB-202603-003",
            "risk_level": RiskLevel.HIGH.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"split_planned": 2},
        },
        {
            "id": _sid("po.010"),
            "user_id": _sid("user.fi.wang"),
            "organization_id": _sid("org.fi.globebank"),
            "beneficiary_id": _sid("bene.acme.supplier"),
            "source_command_id": None,
            "intent_source_text": "机构复核通过后转入对公清结算队列",
            "amount": _d("50000.00"),
            "currency": "USD",
            "status": PaymentOrderStatus.APPROVED.value,
            "reference": "FI-202603-001",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"review_owner": "Wang Analyst"},
        },
        {
            "id": _sid("po.011"),
            "user_id": _sid("user.fi.wang"),
            "organization_id": _sid("org.fi.globebank"),
            "beneficiary_id": _sid("bene.oceanic.parts"),
            "source_command_id": None,
            "intent_source_text": "高风险跨境付款进入人工复核",
            "amount": _d("94000.00"),
            "currency": "USD",
            "status": PaymentOrderStatus.PENDING_CONFIRMATION.value,
            "reference": "FI-202603-002",
            "risk_level": RiskLevel.HIGH.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"review_queue": "high_risk"},
        },
        {
            "id": _sid("po.012"),
            "user_id": _sid("user.retail.lin"),
            "organization_id": None,
            "beneficiary_id": _sid("bene.lucy"),
            "source_command_id": None,
            "intent_source_text": "补转 640 USDC 给 Lucy",
            "amount": _d("640.00"),
            "currency": "USDC",
            "status": PaymentOrderStatus.FAILED.value,
            "reference": "RET-202603-003",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.MOCK.value,
            "metadata_json": {"failure_reason": "quote_expired"},
        },
        {
            "id": _sid("po.013"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.acme.supplier"),
            "source_command_id": None,
            "intent_source_text": "批量供应商结算 125000 USD",
            "amount": _d("125000.00"),
            "currency": "USD",
            "status": PaymentOrderStatus.EXECUTED.value,
            "reference": "SUP-202603-001",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"batch_settlement": True},
        },
        {
            "id": _sid("po.014"),
            "user_id": _sid("user.fi.wang"),
            "organization_id": _sid("org.fi.globebank"),
            "beneficiary_id": _sid("bene.euro.supply"),
            "source_command_id": None,
            "intent_source_text": "机构侧审批后的欧元清算",
            "amount": _d("98000.00"),
            "currency": "EUR",
            "status": PaymentOrderStatus.APPROVED.value,
            "reference": "FI-202603-003",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"report_linked": True},
        },
        {
            "id": _sid("po.015"),
            "user_id": _sid("user.fi.wang"),
            "organization_id": _sid("org.fi.globebank"),
            "beneficiary_id": _sid("bene.shadow.node"),
            "source_command_id": None,
            "intent_source_text": "命中黑名单，终止处理",
            "amount": _d("70000.00"),
            "currency": "USDT",
            "status": PaymentOrderStatus.CANCELLED.value,
            "reference": "FI-202603-004",
            "risk_level": RiskLevel.HIGH.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"blocked_reason": "sanctions_match"},
        },
        {
            "id": _sid("po.016"),
            "user_id": _sid("user.retail.lin"),
            "organization_id": None,
            "beneficiary_id": _sid("bene.retail.david"),
            "source_command_id": None,
            "intent_source_text": "转 199 CNY 给 David，备注车费",
            "amount": _d("199.00"),
            "currency": "CNY",
            "status": PaymentOrderStatus.DRAFT.value,
            "reference": "RET-202603-004",
            "risk_level": RiskLevel.LOW.value,
            "requires_confirmation": False,
            "execution_mode": ExecutionMode.MOCK.value,
            "metadata_json": {"note": "taxi_share"},
        },
        {
            "id": _sid("po.017"),
            "user_id": _sid("user.trade.chen"),
            "organization_id": _sid("org.trade.acme"),
            "beneficiary_id": _sid("bene.lucy"),
            "source_command_id": None,
            "intent_source_text": "向海外顾问支付 3500 USDC",
            "amount": _d("3500.00"),
            "currency": "USDC",
            "status": PaymentOrderStatus.QUOTED.value,
            "reference": "TRD-202603-007",
            "risk_level": RiskLevel.LOW.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"category": "consulting"},
        },
        {
            "id": _sid("po.018"),
            "user_id": _sid("user.fi.wang"),
            "organization_id": _sid("org.fi.globebank"),
            "beneficiary_id": _sid("bene.acme.supplier"),
            "source_command_id": _sid("command.009"),
            "intent_source_text": "大额机构复核后执行",
            "amount": _d("250000.00"),
            "currency": "USD",
            "status": PaymentOrderStatus.EXECUTED.value,
            "reference": "FI-202603-005",
            "risk_level": RiskLevel.MEDIUM.value,
            "requires_confirmation": True,
            "execution_mode": ExecutionMode.SIMULATED.value,
            "metadata_json": {"approval_ticket": "FI-APR-5562"},
        },
    ]

    payment_splits = [
        {
            "id": _sid("split.po002.1"),
            "payment_order_id": _sid("po.002"),
            "sequence": 1,
            "amount": _d("10000.00"),
            "currency": "USDT",
            "status": PaymentSplitStatus.SCHEDULED.value,
        },
        {
            "id": _sid("split.po002.2"),
            "payment_order_id": _sid("po.002"),
            "sequence": 2,
            "amount": _d("10000.00"),
            "currency": "USDT",
            "status": PaymentSplitStatus.SCHEDULED.value,
        },
        {
            "id": _sid("split.po002.3"),
            "payment_order_id": _sid("po.002"),
            "sequence": 3,
            "amount": _d("10000.00"),
            "currency": "USDT",
            "status": PaymentSplitStatus.SCHEDULED.value,
        },
        {
            "id": _sid("split.po008.1"),
            "payment_order_id": _sid("po.008"),
            "sequence": 1,
            "amount": _d("20000.00"),
            "currency": "EUR",
            "status": PaymentSplitStatus.EXECUTED.value,
        },
        {
            "id": _sid("split.po008.2"),
            "payment_order_id": _sid("po.008"),
            "sequence": 2,
            "amount": _d("25000.00"),
            "currency": "EUR",
            "status": PaymentSplitStatus.EXECUTED.value,
        },
        {
            "id": _sid("split.po009.1"),
            "payment_order_id": _sid("po.009"),
            "sequence": 1,
            "amount": _d("7875.00"),
            "currency": "USD",
            "status": PaymentSplitStatus.DRAFT.value,
        },
        {
            "id": _sid("split.po009.2"),
            "payment_order_id": _sid("po.009"),
            "sequence": 2,
            "amount": _d("7875.00"),
            "currency": "USD",
            "status": PaymentSplitStatus.DRAFT.value,
        },
        {
            "id": _sid("split.po013.1"),
            "payment_order_id": _sid("po.013"),
            "sequence": 1,
            "amount": _d("60000.00"),
            "currency": "USD",
            "status": PaymentSplitStatus.EXECUTED.value,
        },
        {
            "id": _sid("split.po013.2"),
            "payment_order_id": _sid("po.013"),
            "sequence": 2,
            "amount": _d("65000.00"),
            "currency": "USD",
            "status": PaymentSplitStatus.EXECUTED.value,
        },
    ]

    payment_quotes = [
        {
            "id": _sid("quote.po001"),
            "payment_order_id": _sid("po.001"),
            "fee": _d("0.80"),
            "fx_rate": None,
            "route": "TRON-USDC",
            "eta_text": "within 2 hours",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po002"),
            "payment_order_id": _sid("po.002"),
            "fee": _d("68.00"),
            "fx_rate": None,
            "route": "TRON-USDT",
            "eta_text": "within 30 minutes",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po003"),
            "payment_order_id": _sid("po.003"),
            "fee": _d("68.00"),
            "fx_rate": None,
            "route": "TRON-USDT",
            "eta_text": "within 30 minutes",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po004"),
            "payment_order_id": _sid("po.004"),
            "fee": _d("67.00"),
            "fx_rate": None,
            "route": "TRON-USDT",
            "eta_text": "within 30 minutes",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po005"),
            "payment_order_id": _sid("po.005"),
            "fee": _d("240.00"),
            "fx_rate": _d("1.000000"),
            "route": "SWIFT-USD",
            "eta_text": "T+1 business day",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po008"),
            "payment_order_id": _sid("po.008"),
            "fee": _d("95.00"),
            "fx_rate": _d("0.920000"),
            "route": "SEPA-EUR",
            "eta_text": "same day",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po009"),
            "payment_order_id": _sid("po.009"),
            "fee": _d("56.00"),
            "fx_rate": _d("1.000000"),
            "route": "SWIFT-USD",
            "eta_text": "T+1 business day",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po010"),
            "payment_order_id": _sid("po.010"),
            "fee": _d("110.00"),
            "fx_rate": _d("1.000000"),
            "route": "SWIFT-USD",
            "eta_text": "same day",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po011"),
            "payment_order_id": _sid("po.011"),
            "fee": _d("260.00"),
            "fx_rate": _d("1.000000"),
            "route": "SWIFT-USD",
            "eta_text": "manual review required",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po013"),
            "payment_order_id": _sid("po.013"),
            "fee": _d("315.00"),
            "fx_rate": _d("1.000000"),
            "route": "SWIFT-USD",
            "eta_text": "T+1 business day",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po014"),
            "payment_order_id": _sid("po.014"),
            "fee": _d("180.00"),
            "fx_rate": _d("0.918000"),
            "route": "SEPA-EUR",
            "eta_text": "same day",
            "eta_at": None,
        },
        {
            "id": _sid("quote.po018"),
            "payment_order_id": _sid("po.018"),
            "fee": _d("480.00"),
            "fx_rate": _d("1.000000"),
            "route": "SWIFT-USD",
            "eta_text": "T+1 business day",
            "eta_at": None,
        },
    ]

    beneficiary_risk_by_id = {item["id"]: item["risk_level"] for item in beneficiaries}
    beneficiary_blacklist_by_id = {item["id"]: item["is_blacklisted"] for item in beneficiaries}
    risk_checks: list[dict[str, Any]] = []
    for order in payment_orders:
        amount = Decimal(str(order["amount"]))
        is_blacklisted = beneficiary_blacklist_by_id[order["beneficiary_id"]]
        risk_level = beneficiary_risk_by_id[order["beneficiary_id"]]

        if is_blacklisted:
            result = RiskCheckResult.BLOCK.value
            score = _d("95.00")
            reason_codes = ["SANCTIONS_MATCH", "BLACKLISTED_BENEFICIARY"]
        elif risk_level == RiskLevel.HIGH.value or amount >= _d("50000.00"):
            result = RiskCheckResult.REVIEW.value
            score = _d("72.00")
            reason_codes = ["HIGH_RISK_CORRIDOR", "MANUAL_REVIEW_REQUIRED"]
        else:
            result = RiskCheckResult.ALLOW.value
            score = _d("18.00")
            reason_codes = ["PASS_BASELINE_POLICY"]

        risk_checks.append(
            {
                "id": _sid(f"risk.{order['reference']}"),
                "payment_order_id": order["id"],
                "check_type": "payment_policy_v1",
                "result": result,
                "score": score,
                "reason_codes_json": reason_codes,
                "raw_payload_json": {
                    "amount": str(order["amount"]),
                    "currency": order["currency"],
                    "risk_level": risk_level,
                    "is_blacklisted": is_blacklisted,
                },
            }
        )

    report_jobs = [
        {
            "id": _sid("report.001"),
            "user_id": _sid("user.fi.wang"),
            "report_type": "cross_border_by_country",
            "filters_json": {"range": "last_week", "group_by": "country"},
            "summary_text": "跨境收款主要来自 AE、MY、DE，AE 风险级别最高。",
            "status": ReportJobStatus.COMPLETED.value,
        },
        {
            "id": _sid("report.002"),
            "user_id": _sid("user.fi.wang"),
            "report_type": "high_risk_review",
            "filters_json": {"range": "this_week", "risk_level": "high"},
            "summary_text": "共发现 4 笔高风险交易，其中 1 笔命中黑名单并已阻断。",
            "status": ReportJobStatus.COMPLETED.value,
        },
        {
            "id": _sid("report.003"),
            "user_id": _sid("user.fi.wang"),
            "report_type": "pending_confirmation_snapshot",
            "filters_json": {"status": "pending_confirmation"},
            "summary_text": None,
            "status": ReportJobStatus.PENDING.value,
        },
        {
            "id": _sid("report.004"),
            "user_id": _sid("user.fi.wang"),
            "report_type": "blocked_transactions",
            "filters_json": {"result": "block"},
            "summary_text": None,
            "status": ReportJobStatus.RUNNING.value,
        },
    ]

    now = datetime(2026, 3, 26, 9, 0, tzinfo=timezone.utc)
    audit_logs = [
        {
            "id": _sid("audit.001"),
            "actor_user_id": user_id_by_key["retail_user"],
            "entity_type": "payment_order",
            "entity_id": _sid("po.001"),
            "action": "create",
            "before_json": None,
            "after_json": {"status": PaymentOrderStatus.DRAFT.value},
            "trace_id": "trace-retail-001",
            "created_at": now - timedelta(minutes=52),
        },
        {
            "id": _sid("audit.002"),
            "actor_user_id": user_id_by_key["retail_user"],
            "entity_type": "payment_order",
            "entity_id": _sid("po.001"),
            "action": "status_change",
            "before_json": {"status": PaymentOrderStatus.DRAFT.value},
            "after_json": {"status": PaymentOrderStatus.EXECUTED.value},
            "trace_id": "trace-retail-001",
            "created_at": now - timedelta(minutes=48),
        },
        {
            "id": _sid("audit.003"),
            "actor_user_id": user_id_by_key["trade_operator"],
            "entity_type": "payment_order",
            "entity_id": _sid("po.002"),
            "action": "create",
            "before_json": None,
            "after_json": {"status": PaymentOrderStatus.QUOTED.value},
            "trace_id": "trace-trade-009",
            "created_at": now - timedelta(minutes=40),
        },
        {
            "id": _sid("audit.004"),
            "actor_user_id": user_id_by_key["trade_operator"],
            "entity_type": "payment_order",
            "entity_id": _sid("po.005"),
            "action": "status_change",
            "before_json": {"status": PaymentOrderStatus.PENDING_CONFIRMATION.value},
            "after_json": {"status": PaymentOrderStatus.FAILED.value},
            "trace_id": "trace-trade-010",
            "created_at": now - timedelta(minutes=32),
        },
        {
            "id": _sid("audit.005"),
            "actor_user_id": user_id_by_key["trade_operator"],
            "entity_type": "payment_order",
            "entity_id": _sid("po.006"),
            "action": "cancel",
            "before_json": {"status": PaymentOrderStatus.PENDING_CONFIRMATION.value},
            "after_json": {"status": PaymentOrderStatus.CANCELLED.value},
            "trace_id": "trace-trade-011",
            "created_at": now - timedelta(minutes=28),
        },
        {
            "id": _sid("audit.006"),
            "actor_user_id": user_id_by_key["institution_analyst"],
            "entity_type": "report_job",
            "entity_id": _sid("report.002"),
            "action": "complete",
            "before_json": {"status": ReportJobStatus.RUNNING.value},
            "after_json": {"status": ReportJobStatus.COMPLETED.value},
            "trace_id": "trace-report-001",
            "created_at": now - timedelta(minutes=20),
        },
        {
            "id": _sid("audit.007"),
            "actor_user_id": user_id_by_key["institution_analyst"],
            "entity_type": "payment_order",
            "entity_id": _sid("po.014"),
            "action": "approve",
            "before_json": {"status": PaymentOrderStatus.PENDING_CONFIRMATION.value},
            "after_json": {"status": PaymentOrderStatus.APPROVED.value},
            "trace_id": "trace-report-002",
            "created_at": now - timedelta(minutes=12),
        },
        {
            "id": _sid("audit.008"),
            "actor_user_id": user_id_by_key["institution_analyst"],
            "entity_type": "payment_order",
            "entity_id": _sid("po.015"),
            "action": "block",
            "before_json": {"status": PaymentOrderStatus.PENDING_CONFIRMATION.value},
            "after_json": {"status": PaymentOrderStatus.CANCELLED.value},
            "trace_id": "trace-report-002",
            "created_at": now - timedelta(minutes=8),
        },
    ]

    _apply_deterministic_timestamps(
        organizations,
        base_time=datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
        step_minutes=15,
    )
    _apply_deterministic_timestamps(
        users,
        base_time=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
        step_minutes=10,
    )
    _apply_deterministic_timestamps(
        beneficiaries,
        base_time=datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
        step_minutes=7,
    )
    _apply_deterministic_timestamps(
        sessions,
        base_time=datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc),
        step_minutes=20,
    )
    _apply_deterministic_timestamps(
        command_executions,
        base_time=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
        step_minutes=35,
    )
    _apply_deterministic_timestamps(
        payment_orders,
        base_time=datetime(2026, 3, 22, 8, 30, tzinfo=timezone.utc),
        step_minutes=50,
    )
    _apply_deterministic_timestamps(
        payment_splits,
        base_time=datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
        step_minutes=9,
    )
    _apply_deterministic_timestamps(
        payment_quotes,
        base_time=datetime(2026, 3, 22, 13, 0, tzinfo=timezone.utc),
        step_minutes=11,
    )
    _apply_deterministic_timestamps(
        risk_checks,
        base_time=datetime(2026, 3, 23, 9, 30, tzinfo=timezone.utc),
        step_minutes=12,
    )
    _apply_deterministic_timestamps(
        report_jobs,
        base_time=datetime(2026, 3, 24, 9, 0, tzinfo=timezone.utc),
        step_minutes=25,
    )

    with get_db_session() as session:
        if reset:
            _clear_all_data(session)

        _upsert_many(session, Organization, organizations)
        session.flush()
        _upsert_many(session, User, users)
        session.flush()
        _upsert_many(session, Beneficiary, beneficiaries)
        session.flush()
        _upsert_many(session, ConversationSession, sessions)
        session.flush()
        _upsert_many(session, CommandExecution, command_executions)
        session.flush()
        _upsert_many(session, PaymentOrder, payment_orders)
        session.flush()
        _upsert_many(session, PaymentSplit, payment_splits)
        session.flush()
        _upsert_many(session, PaymentQuote, payment_quotes)
        session.flush()
        _upsert_many(session, RiskCheck, risk_checks)
        session.flush()
        _upsert_many(session, ReportJob, report_jobs)
        session.flush()
        _upsert_many(session, AuditLog, audit_logs)
        session.commit()

    return {
        "organizations": len(organizations),
        "users": len(users),
        "beneficiaries": len(beneficiaries),
        "sessions": len(sessions),
        "command_executions": len(command_executions),
        "payment_orders": len(payment_orders),
        "payment_splits": len(payment_splits),
        "payment_quotes": len(payment_quotes),
        "risk_checks": len(risk_checks),
        "report_jobs": len(report_jobs),
        "audit_logs": len(audit_logs),
    }
