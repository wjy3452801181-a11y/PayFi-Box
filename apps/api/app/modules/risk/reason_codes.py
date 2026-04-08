from __future__ import annotations

from typing import Iterable


RISK_REASON_CODE_ORDER = [
    "BLACKLISTED_BENEFICIARY",
    "HIGH_RISK_BENEFICIARY",
    "MEDIUM_RISK_BENEFICIARY",
    "UNRESOLVED_BENEFICIARY",
    "HIGH_AMOUNT",
    "CROSS_BORDER",
    "SPLIT_PAYMENT",
    "MISSING_REFERENCE_FOR_TRADE_PAYMENT",
    "PASS_BASELINE_POLICY",
]

RISK_REASON_CODE_ALIASES = {
    "HIGH_RISK_CORRIDOR": "CROSS_BORDER",
    "MANUAL_REVIEW_REQUIRED": "HIGH_AMOUNT",
    "SANCTIONS_MATCH": "BLACKLISTED_BENEFICIARY",
}

RISK_REASON_CODE_SET = set(RISK_REASON_CODE_ORDER)


def normalize_reason_code(code: str) -> str | None:
    normalized = str(code).strip().upper()
    normalized = RISK_REASON_CODE_ALIASES.get(normalized, normalized)
    if normalized in RISK_REASON_CODE_SET:
        return normalized
    return None


def normalize_reason_codes(codes: Iterable[str] | None) -> list[str]:
    if not codes:
        return []
    seen: set[str] = set()
    normalized_codes: list[str] = []
    for code in codes:
        normalized = normalize_reason_code(code)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_codes.append(normalized)

    order_index = {code: idx for idx, code in enumerate(RISK_REASON_CODE_ORDER)}
    normalized_codes.sort(key=lambda item: order_index.get(item, 999))
    return normalized_codes
