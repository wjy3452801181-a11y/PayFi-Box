from __future__ import annotations

from collections import defaultdict
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Beneficiary, CommandExecution, PaymentOrder, ReportJob, RiskCheck
from app.modules.reports.schemas import (
    GroupedSummaryItem,
    HighRiskSampleItem,
    ReportCommandPreview,
    ReportJobPreview,
    ReportSummaryFilters,
    ReportSummaryMetrics,
    ReportSummaryResponse,
    RiskReasonCodeSummaryItem,
    RiskDecisionSummaryItem,
)
from app.modules.risk.reason_codes import normalize_reason_codes


def get_reports_summary(
    session: Session,
    *,
    user_id: UUID | None,
    organization_id: UUID | None,
    country: str | None,
    currency: str | None,
    risk_level: str | None,
    status: str | None,
    date_from: date | None,
    date_to: date | None,
) -> ReportSummaryResponse:
    stmt = select(PaymentOrder, Beneficiary).join(Beneficiary, Beneficiary.id == PaymentOrder.beneficiary_id)

    if user_id:
        stmt = stmt.where(PaymentOrder.user_id == user_id)
    if organization_id:
        stmt = stmt.where(PaymentOrder.organization_id == organization_id)
    if country:
        stmt = stmt.where(Beneficiary.country == country.upper())
    if currency:
        stmt = stmt.where(PaymentOrder.currency == currency.upper())
    if risk_level:
        stmt = stmt.where(PaymentOrder.risk_level == risk_level)
    if status:
        stmt = stmt.where(PaymentOrder.status == status)
    if date_from:
        date_from_ts = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        stmt = stmt.where(PaymentOrder.created_at >= date_from_ts)
    if date_to:
        date_to_ts = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        stmt = stmt.where(PaymentOrder.created_at < date_to_ts)

    rows = session.execute(stmt.order_by(PaymentOrder.created_at.desc())).all()

    metrics = _build_metrics(rows)
    by_country = _group_summary(rows, key_fn=lambda item: item[1].country)
    by_currency = _group_summary(rows, key_fn=lambda item: item[0].currency)
    by_status = _group_summary(rows, key_fn=lambda item: item[0].status)
    by_risk_level = _group_summary(rows, key_fn=lambda item: item[0].risk_level)
    by_risk_decision = _build_risk_decision_summary(session=session, rows=rows)
    by_risk_reason_code = _build_risk_reason_code_summary(session=session, rows=rows)
    high_risk_samples = _build_high_risk_samples(rows)
    latest_commands = _load_latest_commands(
        session=session,
        rows=rows,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )
    latest_report_jobs = _load_latest_report_jobs(session=session, user_id=user_id)

    return ReportSummaryResponse(
        generated_at=datetime.now(timezone.utc),
        filters=ReportSummaryFilters(
            user_id=user_id,
            organization_id=organization_id,
            country=country.upper() if country else None,
            currency=currency.upper() if currency else None,
            risk_level=risk_level,
            status=status,
            date_from=date_from,
            date_to=date_to,
        ),
        metrics=metrics,
        by_country=by_country,
        by_currency=by_currency,
        by_status=by_status,
        by_risk_level=by_risk_level,
        by_risk_decision=by_risk_decision,
        by_risk_reason_code=by_risk_reason_code,
        high_risk_samples=high_risk_samples,
        latest_commands=latest_commands,
        latest_report_jobs=latest_report_jobs,
    )


def _build_metrics(rows: list[tuple[PaymentOrder, Beneficiary]]) -> ReportSummaryMetrics:
    total_payments = len(rows)
    total_volume = sum((_to_float(order.amount) for order, _ in rows), start=0.0)
    risky_payments = sum(1 for order, _ in rows if order.risk_level in {"medium", "high"})
    executed_payments = sum(1 for order, _ in rows if order.status == "executed")
    failed_payments = sum(1 for order, _ in rows if order.status == "failed")
    return ReportSummaryMetrics(
        total_payments=total_payments,
        total_volume=round(total_volume, 2),
        risky_payments=risky_payments,
        executed_payments=executed_payments,
        failed_payments=failed_payments,
    )


def _group_summary(
    rows: list[tuple[PaymentOrder, Beneficiary]],
    *,
    key_fn,
) -> list[GroupedSummaryItem]:
    bucket: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "volume": 0.0})
    for order, beneficiary in rows:
        key = str(key_fn((order, beneficiary)) or "UNKNOWN")
        bucket[key]["count"] += 1
        bucket[key]["volume"] += _to_float(order.amount)

    items = [
        GroupedSummaryItem(
            key=key,
            count=int(stats["count"]),
            volume=round(float(stats["volume"]), 2),
        )
        for key, stats in bucket.items()
    ]
    return sorted(items, key=lambda item: (-item.count, item.key))


def _build_risk_decision_summary(
    *,
    session: Session,
    rows: list[tuple[PaymentOrder, Beneficiary]],
) -> list[RiskDecisionSummaryItem]:
    payment_ids = [order.id for order, _ in rows]
    if not payment_ids:
        return []
    decision_rows = session.execute(
        select(RiskCheck.result, func.count(RiskCheck.id))
        .where(RiskCheck.payment_order_id.in_(payment_ids))
        .group_by(RiskCheck.result)
    ).all()
    items = [RiskDecisionSummaryItem(decision=str(result), count=int(count)) for result, count in decision_rows]
    return sorted(items, key=lambda item: (-item.count, item.decision))


def _build_high_risk_samples(rows: list[tuple[PaymentOrder, Beneficiary]]) -> list[HighRiskSampleItem]:
    high_risk = [(order, beneficiary) for order, beneficiary in rows if order.risk_level == "high"]
    high_risk.sort(key=lambda item: item[0].created_at, reverse=True)
    return [
        HighRiskSampleItem(
            id=order.id,
            created_at=order.created_at,
            beneficiary_name=beneficiary.name,
            beneficiary_country=beneficiary.country,
            amount=_to_float(order.amount),
            currency=order.currency,
            status=order.status,
            risk_level=order.risk_level,
            reference=order.reference,
        )
        for order, beneficiary in high_risk[:5]
    ]


def _build_risk_reason_code_summary(
    *,
    session: Session,
    rows: list[tuple[PaymentOrder, Beneficiary]],
) -> list[RiskReasonCodeSummaryItem]:
    payment_ids = [order.id for order, _ in rows]
    if not payment_ids:
        return []

    code_counter: Counter[str] = Counter()
    risk_check_rows = session.execute(
        select(RiskCheck.reason_codes_json).where(RiskCheck.payment_order_id.in_(payment_ids))
    ).all()
    for (reason_codes,) in risk_check_rows:
        for code in normalize_reason_codes(reason_codes):
            code_counter[code] += 1

    for order, _ in rows:
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        for code in normalize_reason_codes(metadata.get("risk_reason_codes")):
            code_counter[code] += 1

    items = [
        RiskReasonCodeSummaryItem(reason_code=reason_code, count=count)
        for reason_code, count in code_counter.items()
    ]
    return sorted(items, key=lambda item: (-item.count, item.reason_code))


def _load_latest_report_jobs(
    *,
    session: Session,
    user_id: UUID | None,
) -> list[ReportJobPreview]:
    stmt = select(ReportJob)
    if user_id:
        stmt = stmt.where(ReportJob.user_id == user_id)
    stmt = stmt.order_by(ReportJob.created_at.desc()).limit(5)
    jobs = session.execute(stmt).scalars().all()
    return [
        ReportJobPreview(
            id=item.id,
            user_id=item.user_id,
            report_type=item.report_type,
            status=item.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
            summary_text=item.summary_text,
        )
        for item in jobs
    ]


def _load_latest_commands(
    *,
    session: Session,
    rows: list[tuple[PaymentOrder, Beneficiary]],
    user_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> list[ReportCommandPreview]:
    linked_command_ids: list[UUID] = []
    seen: set[UUID] = set()
    for order, _ in rows:
        if order.source_command_id and order.source_command_id not in seen:
            seen.add(order.source_command_id)
            linked_command_ids.append(order.source_command_id)

    commands: list[CommandExecution] = []
    if linked_command_ids:
        commands = session.execute(
            select(CommandExecution)
            .where(CommandExecution.id.in_(linked_command_ids))
            .order_by(CommandExecution.created_at.desc())
            .limit(5)
        ).scalars().all()
    else:
        fallback_stmt = select(CommandExecution)
        if user_id:
            fallback_stmt = fallback_stmt.where(CommandExecution.user_id == user_id)
        if date_from:
            date_from_ts = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            fallback_stmt = fallback_stmt.where(CommandExecution.created_at >= date_from_ts)
        if date_to:
            date_to_ts = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
            fallback_stmt = fallback_stmt.where(CommandExecution.created_at < date_to_ts)
        commands = session.execute(fallback_stmt.order_by(CommandExecution.created_at.desc()).limit(5)).scalars().all()

    previews: list[ReportCommandPreview] = []
    for command in commands:
        parsed = command.parsed_intent_json if isinstance(command.parsed_intent_json, dict) else {}
        intent_value = parsed.get("intent")
        previews.append(
            ReportCommandPreview(
                command_id=command.id,
                created_at=command.created_at,
                user_id=command.user_id,
                session_id=command.session_id,
                intent=str(intent_value) if intent_value is not None else None,
                final_status=command.final_status,
                trace_id=command.trace_id,
                raw_text=command.raw_text,
            )
        )
    return previews


def _to_float(value: Decimal) -> float:
    return float(value)
