from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def generate_mock_quote(
    payment_fields: dict[str, Any],
    risk_decision: str,
) -> dict[str, Any]:
    amount_value = payment_fields.get("amount") or 0
    amount = Decimal(str(amount_value))
    currency = payment_fields.get("currency") or "USD"
    eta_preference = payment_fields.get("eta_preference")

    if amount <= Decimal("500"):
        fee = amount * Decimal("0.004") + Decimal("0.50")
    elif amount <= Decimal("10000"):
        fee = amount * Decimal("0.0025") + Decimal("1.00")
    else:
        fee = amount * Decimal("0.0030") + Decimal("15.00")

    if currency in {"USDT", "USDC"}:
        route = f"TRON-{currency}"
    elif currency in {"USD", "EUR"}:
        route = f"SWIFT-{currency}"
    else:
        route = f"LOCAL-{currency}"

    eta_text = "within 2 hours"
    if risk_decision == "review":
        eta_text = "manual review required (same day)"
    elif risk_decision == "block":
        eta_text = "blocked pending compliance decision"
    elif eta_preference == "tonight":
        eta_text = "before tonight"
    elif eta_preference in {"today", "asap"}:
        eta_text = "same day"
    elif amount > Decimal("50000"):
        eta_text = "T+1 business day"

    net_transfer = amount - fee
    if net_transfer < Decimal("0"):
        net_transfer = Decimal("0")

    return {
        "estimated_fee": float(fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "net_transfer_amount": float(net_transfer.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "route": route,
        "eta_text": eta_text,
        "currency": currency,
    }
