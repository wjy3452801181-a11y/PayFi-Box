from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.risk.reason_codes import normalize_reason_codes


def evaluate_payment_risk(payment_fields: dict[str, Any]) -> dict[str, Any]:
    beneficiary = payment_fields.get("beneficiary")
    amount_value = payment_fields.get("amount")
    amount = Decimal(str(amount_value)) if amount_value is not None else Decimal("0")
    beneficiary_country = beneficiary.get("country") if beneficiary else None
    beneficiary_risk = beneficiary.get("risk_level") if beneficiary else None
    is_blacklisted = bool(beneficiary.get("is_blacklisted")) if beneficiary else False
    beneficiary_resolved = bool(beneficiary.get("resolved")) if isinstance(beneficiary, dict) else False
    is_high_amount = amount >= Decimal("10000")
    is_cross_border = bool(beneficiary_country and beneficiary_country.upper() != "CN")
    split_count = _safe_int(payment_fields.get("split_count"), default=1)
    has_split = split_count > 1
    has_reference = bool(payment_fields.get("reference"))
    looks_like_trade_payment = has_split or amount >= Decimal("5000")
    unresolved_beneficiary = beneficiary is None or not beneficiary_resolved

    reason_codes: list[str] = []
    decision = "allow"
    risk_level = "low"
    user_message = "风控预检通过，可进入预览确认。 (Risk pre-check passed for preview.)"

    base_reason_flags = {
        "MEDIUM_RISK_BENEFICIARY": beneficiary_risk == "medium",
        "HIGH_AMOUNT": is_high_amount,
        "CROSS_BORDER": is_cross_border,
        "SPLIT_PAYMENT": has_split,
        "MISSING_REFERENCE_FOR_TRADE_PAYMENT": looks_like_trade_payment and not has_reference,
        "UNRESOLVED_BENEFICIARY": unresolved_beneficiary,
    }

    if is_blacklisted:
        decision = "block"
        risk_level = "high"
        blacklisted_flags = {"BLACKLISTED_BENEFICIARY": True, **base_reason_flags}
        reason_codes = normalize_reason_codes(
            [code for code, enabled in blacklisted_flags.items() if enabled]
        )
        user_message = "受益人命中黑名单，命令应拦截。 (Beneficiary is blacklisted; this command should be blocked.)"
    elif beneficiary_risk == "high":
        decision = "review"
        risk_level = "high"
        high_flags = {"HIGH_RISK_BENEFICIARY": True, **base_reason_flags}
        reason_codes = normalize_reason_codes(
            [code for code, enabled in high_flags.items() if enabled]
        )
        user_message = "受益人为高风险，建议人工复核。 (Beneficiary is high risk; manual review is recommended.)"
    elif (
        is_high_amount
        or is_cross_border
        or beneficiary_risk == "medium"
        or unresolved_beneficiary
        or has_split
        or (looks_like_trade_payment and not has_reference)
    ):
        decision = "review"
        risk_level = "medium"
        reason_codes = normalize_reason_codes(
            [code for code, enabled in base_reason_flags.items() if enabled]
        )
        if unresolved_beneficiary:
            user_message = "受益人尚未解析完成，建议先确认对象信息。 (Beneficiary is unresolved; please verify recipient details.)"
        elif is_high_amount and is_cross_border:
            user_message = "检测到大额跨境付款，建议人工复核。 (Large cross-border payment detected; manual review is recommended.)"
        elif is_high_amount:
            user_message = "检测到大额付款，建议人工复核。 (Large amount detected; manual review is recommended.)"
        elif has_split and not has_reference:
            user_message = "拆单交易缺少参考号，建议补充后再确认。 (Split payment is missing a reference; add one before confirmation.)"
        elif beneficiary_risk == "medium":
            user_message = "受益人为中风险，建议补充检查。 (Medium-risk beneficiary; additional checks are recommended.)"
        else:
            user_message = "检测到跨境付款，建议补充复核。 (Cross-border payment detected; additional review is recommended.)"
    else:
        reason_codes = ["PASS_BASELINE_POLICY"]

    return {
        "decision": decision,
        "risk_level": risk_level,
        "reason_codes": reason_codes,
        "user_message": user_message,
    }


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default
