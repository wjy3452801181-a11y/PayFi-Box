from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal


CommandIntent = Literal["create_payment", "query_payments", "generate_report", "unknown"]

PAYMENT_KEYWORDS = (
    "转",
    "付款",
    "支付",
    "pay ",
    "send ",
    "transfer ",
)
QUERY_KEYWORDS = (
    "查询",
    "recent payment",
    "recent payments",
    "payment status",
    "payments",
)
REPORT_KEYWORDS = (
    "报表",
    "report",
    "grouped by",
    "按国家",
    "cross-border",
    "跨境",
    "high risk",
    "高风险",
)
KNOWN_CURRENCIES = ("USDT", "USDC", "USD", "EUR", "CNY")
STATUS_KEYWORDS = ("draft", "quoted", "pending_confirmation", "approved", "executed", "failed", "cancelled")


def classify_intent(text: str) -> CommandIntent:
    lower = text.lower()
    if any(token in lower for token in REPORT_KEYWORDS):
        return "generate_report"
    if any(token in lower for token in QUERY_KEYWORDS):
        return "query_payments"
    if any(token in lower for token in PAYMENT_KEYWORDS):
        return "create_payment"

    has_amount = _extract_amount(lower) is not None
    has_currency = _extract_currency(text) is not None
    if has_amount and has_currency:
        return "create_payment"
    return "unknown"


def parse_command(
    *,
    text: str,
    intent: CommandIntent,
    beneficiaries: list[dict[str, Any]],
) -> dict[str, Any]:
    if intent == "create_payment":
        return parse_payment_command(text=text, beneficiaries=beneficiaries)
    if intent == "query_payments":
        return parse_query_command(text=text, beneficiaries=beneficiaries)
    if intent == "generate_report":
        return parse_report_command(text=text)
    return {
        "intent": "unknown",
        "status": "needs_clarification",
        "fields": {},
        "missing_fields": [],
        "confidence": 0.2,
        "follow_up_question": "请补充你的目标，例如转账、查询支付，或生成报表。",
    }


def parse_payment_command(text: str, beneficiaries: list[dict[str, Any]]) -> dict[str, Any]:
    amount = _extract_amount(text)
    currency = _extract_currency(text)
    split_count = _extract_split_count(text)
    reference = _extract_reference(text)
    eta_preference = _extract_eta_preference(text)
    fee_preference = _extract_fee_preference(text)
    beneficiary_preview = _match_beneficiary(text, beneficiaries)

    missing_fields: list[str] = []
    if beneficiary_preview is None:
        missing_fields.append("recipient")
    if amount is None:
        missing_fields.append("amount")
    if currency is None:
        missing_fields.append("currency")

    confidence = 0.55
    if beneficiary_preview is not None:
        confidence += 0.15
    if amount is not None:
        confidence += 0.15
    if currency is not None:
        confidence += 0.15
    if split_count is not None or reference is not None:
        confidence += 0.05
    confidence = min(confidence, 0.98)

    follow_up_question = _payment_follow_up_question(missing_fields)
    status = "needs_clarification" if missing_fields else "ok"

    return {
        "intent": "create_payment",
        "status": status,
        "fields": {
            "recipient": beneficiary_preview["name"] if beneficiary_preview else None,
            "beneficiary": beneficiary_preview,
            "amount": float(amount) if amount is not None else None,
            "currency": currency,
            "split_count": split_count,
            "reference": reference,
            "eta_preference": eta_preference,
            "fee_preference": fee_preference,
        },
        "missing_fields": missing_fields,
        "confidence": confidence if not missing_fields else min(confidence, 0.72),
        "follow_up_question": follow_up_question,
    }


def parse_query_command(text: str, beneficiaries: list[dict[str, Any]]) -> dict[str, Any]:
    lower = text.lower()
    beneficiary_preview = _match_beneficiary(text, beneficiaries)
    filters: dict[str, Any] = {
        "time_range": _extract_time_range(lower),
        "status": _extract_status(lower),
        "recipient": beneficiary_preview["name"] if beneficiary_preview else None,
        "cross_border_only": ("cross-border" in lower) or ("跨境" in text),
    }
    confidence = 0.62
    if filters["time_range"]:
        confidence += 0.1
    if filters["status"]:
        confidence += 0.1
    if filters["recipient"]:
        confidence += 0.1
    return {
        "intent": "query_payments",
        "status": "ok",
        "fields": filters,
        "missing_fields": [],
        "confidence": min(confidence, 0.9),
        "follow_up_question": None,
    }


def parse_report_command(text: str) -> dict[str, Any]:
    lower = text.lower()
    fields = {
        "time_range": _extract_time_range(lower),
        "group_by": "country" if ("按国家" in text or "grouped by country" in lower) else None,
        "highlight_risky": ("高风险" in text) or ("risky" in lower) or ("high risk" in lower),
        "cross_border_only": ("跨境" in text) or ("cross-border" in lower),
    }
    confidence = 0.68
    if fields["group_by"] == "country":
        confidence += 0.1
    if fields["highlight_risky"]:
        confidence += 0.1
    return {
        "intent": "generate_report",
        "status": "ok",
        "fields": fields,
        "missing_fields": [],
        "confidence": min(confidence, 0.9),
        "follow_up_question": None,
    }


def _extract_amount(text: str) -> Decimal | None:
    match = re.search(r"(?<![A-Za-z])(\d+(?:\.\d{1,2})?)", text)
    if not match:
        return None
    try:
        return Decimal(match.group(1))
    except (InvalidOperation, ValueError):
        return None


def _extract_currency(text: str) -> str | None:
    upper = text.upper()
    for currency in KNOWN_CURRENCIES:
        if re.search(rf"\b{currency}\b", upper):
            return currency
    return None


def _extract_split_count(text: str) -> int | None:
    patterns = [
        r"拆成\s*(\d+)\s*笔",
        r"in\s*(\d+)\s*splits?",
        r"split\s*into\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_reference(text: str) -> str | None:
    match = re.search(r"\b([A-Z]{2,5}[-_ ]?\d{2,8})\b", text.upper())
    if match:
        return match.group(1).replace(" ", "-")
    return None


def _extract_eta_preference(text: str) -> str | None:
    lower = text.lower()
    if "今晚" in text or "tonight" in lower:
        return "tonight"
    if "今天" in text or "today" in lower:
        return "today"
    if "尽快" in text or "asap" in lower or "urgent" in lower:
        return "asap"
    return None


def _extract_fee_preference(text: str) -> str | None:
    lower = text.lower()
    if "手续费最低" in text or "lowest fee" in lower or "cheapest" in lower:
        return "lowest"
    if "最快" in text or "fastest" in lower:
        return "fastest"
    return None


def _extract_time_range(lower: str) -> str | None:
    if "上周" in lower or "last week" in lower:
        return "last_week"
    if "本周" in lower or "this week" in lower:
        return "this_week"
    if "today" in lower or "今天" in lower:
        return "today"
    if "recent" in lower or "最近" in lower:
        return "recent"
    return None


def _extract_status(lower: str) -> str | None:
    for status in STATUS_KEYWORDS:
        if status in lower:
            return status
    if "已执行" in lower:
        return "executed"
    if "失败" in lower:
        return "failed"
    if "取消" in lower:
        return "cancelled"
    return None


def _match_beneficiary(
    text: str,
    beneficiaries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    lower = text.lower()
    for beneficiary in beneficiaries:
        name = str(beneficiary["name"])
        name_lower = name.lower()
        first_token = name_lower.split(" ")[0]
        if name_lower in lower or (first_token and first_token in lower):
            return {
                "id": beneficiary["id"],
                "name": name,
                "country": beneficiary.get("country"),
                "risk_level": beneficiary.get("risk_level"),
                "is_blacklisted": bool(beneficiary.get("is_blacklisted", False)),
                "resolved": True,
            }

    cn_match = re.search(r"(?:给|向)\s*([A-Za-z\u4e00-\u9fa5][A-Za-z\u4e00-\u9fa5\s]{0,30}?)(?:转|支付|付款)", text)
    if cn_match:
        candidate = cn_match.group(1).strip()
        if candidate:
            return {
                "id": None,
                "name": candidate,
                "country": None,
                "risk_level": None,
                "is_blacklisted": None,
                "resolved": False,
            }

    en_match = re.search(
        r"(?:to|pay)\s+([A-Za-z][A-Za-z\s]{1,40}?)(?:\s+\d|\s+for|\s+in\s+\d+\s+splits|\s*$)",
        text,
        flags=re.IGNORECASE,
    )
    if en_match:
        candidate = en_match.group(1).strip()
        if candidate:
            return {
                "id": None,
                "name": candidate,
                "country": None,
                "risk_level": None,
                "is_blacklisted": None,
                "resolved": False,
            }
    return None


def _payment_follow_up_question(missing_fields: list[str]) -> str | None:
    if not missing_fields:
        return None
    if missing_fields[0] == "recipient":
        return "你想转给谁？"
    if missing_fields[0] == "amount":
        return "付款金额是多少？"
    if missing_fields[0] == "currency":
        return "你想使用 USDT 还是 USDC？"
    return "请补充缺失信息后我再继续。"
