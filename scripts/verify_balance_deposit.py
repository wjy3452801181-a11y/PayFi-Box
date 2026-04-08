#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import error, request

API_APP_PATH = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_APP_PATH) not in sys.path:
    sys.path.append(str(API_APP_PATH))

from sqlalchemy import select

from app.db.models import KycVerification, User, UserRole
from app.db.session import get_db_session

DEFAULT_API_BASE = "http://127.0.0.1:8000"
DEFAULT_WEBHOOK_SECRET = "whsec_localtest"
SEED_NAMESPACE = uuid.UUID("4f78f387-47a6-4ec1-a9f9-e1ecfe2f0844")
DEFAULT_UNVERIFIED_USER_ID = str(uuid.uuid5(SEED_NAMESPACE, "user.fi.wang"))
DEFAULT_VERIFIED_USER_ID = str(uuid.uuid5(SEED_NAMESPACE, "user.trade.chen"))


class VerificationError(Exception):
    pass


@dataclass
class CaseOutcome:
    name: str
    status: str
    info: dict[str, Any]


def _latest_user_kyc_status(user_id: str) -> str | None:
    uid = uuid.UUID(user_id)
    with get_db_session() as session:
        verification = session.execute(
            select(KycVerification)
            .where(KycVerification.subject_type == "user", KycVerification.subject_id == uid)
            .order_by(KycVerification.created_at.desc())
        ).scalars().first()
        return verification.status if verification is not None else None


def _ensure_user_record(*, user_id: str, name: str, email: str, role: str) -> str:
    uid = uuid.UUID(user_id)
    with get_db_session() as session:
        user = session.get(User, uid)
        if user is None:
            session.add(
                User(
                    id=uid,
                    name=name,
                    email=email,
                    role=role,
                    organization_id=None,
                )
            )
            session.commit()
    return user_id


def _resolve_unverified_user_id(requested_user_id: str) -> str:
    requested_id = _ensure_user_record(
        user_id=requested_user_id,
        name="Balance Verify Unverified",
        email=f"verify-unverified-{requested_user_id[:8]}@payfi.demo",
        role=UserRole.RETAIL.value,
    )
    if (_latest_user_kyc_status(requested_id) or "").lower() != "verified":
        return requested_id

    replacement_id = str(uuid.uuid4())
    return _ensure_user_record(
        user_id=replacement_id,
        name="Balance Verify Unverified",
        email=f"verify-unverified-{replacement_id[:8]}@payfi.demo",
        role=UserRole.RETAIL.value,
    )


def _resolve_verified_user_id(requested_user_id: str) -> str:
    return _ensure_user_record(
        user_id=requested_user_id,
        name="Balance Verify Verified",
        email=f"verify-verified-{requested_user_id[:8]}@payfi.demo",
        role=UserRole.TRADE_COMPANY.value,
    )


def _load_env_value(name: str) -> str | None:
    direct = os.environ.get(name)
    if direct:
        return direct
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(os.path.dirname(script_dir), "apps", "api", ".env")
    if not os.path.exists(candidate):
        return None
    try:
        with open(candidate, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip("\"'")
    except OSError:
        return None
    return None


def _is_local_stripe_network_block(message: str | None) -> bool:
    text = (message or "").lower()
    if "198.18." in text or "fake-ip" in text or "tls 握手失败" in text or "tls handshake" in text:
        return True
    try:
        api_ip = socket.getaddrinfo("api.stripe.com", 443, proto=socket.IPPROTO_TCP)[0][4][0]
        checkout_ip = socket.getaddrinfo("checkout.stripe.com", 443, proto=socket.IPPROTO_TCP)[0][4][0]
    except Exception:
        return False
    return any(ip.startswith("198.18.") for ip in (api_ip, checkout_ip))


class BalanceDepositVerifier:
    def __init__(
        self,
        *,
        base_url: str,
        webhook_secret: str,
        unverified_user_id: str,
        verified_user_id: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.webhook_secret = webhook_secret
        self.unverified_user_id = unverified_user_id
        self.verified_user_id = verified_user_id
        self.timeout_seconds = timeout_seconds
        self._opener = request.build_opener(request.ProxyHandler({}))

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        body = raw_body if raw_body is not None else (json.dumps(payload).encode("utf-8") if payload is not None else None)
        req = request.Request(url=url, method=method, data=body, headers=headers)

        try:
            with self._opener.open(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
                return resp.status, data
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {"raw": raw}
            return exc.code, data
        except error.URLError as exc:
            raise VerificationError(f"{method} {path} failed: {exc.reason}") from exc

    def _assert_health(self) -> None:
        status, data = self._request_json("GET", "/health")
        if status != 200 or data.get("status") != "ok":
            raise VerificationError(f"API not healthy: status={status}, body={data}")

    def _start_user_kyc(self, user_id: str) -> dict[str, Any]:
        status, data = self._request_json(
            "POST",
            "/api/kyc/start",
            payload={"subject_type": "user", "subject_id": user_id},
        )
        if status != 200:
            raise VerificationError(f"start user kyc failed: {status} {data}")
        return data

    def _create_deposit(self, user_id: str, amount: float, reference: str) -> dict[str, Any]:
        status, data = self._request_json(
            "POST",
            "/api/balance/deposits",
            payload={
                "user_id": user_id,
                "source_currency": "HKD",
                "source_amount": amount,
                "target_currency": "USDT",
                "reference": reference,
            },
        )
        if status != 200:
            raise VerificationError(f"create deposit failed: {status} {data}")
        return data

    def _start_checkout(self, deposit_order_id: str) -> tuple[int, dict[str, Any]]:
        return self._request_json(
            "POST",
            f"/api/balance/deposits/{deposit_order_id}/start-stripe-payment",
            payload={
                "success_url": "http://127.0.0.1:3000/balance?stripe=success",
                "cancel_url": "http://127.0.0.1:3000/balance?stripe=cancel",
                "locale": "zh",
            },
        )

    def _sync_deposit(self, deposit_order_id: str) -> tuple[int, dict[str, Any]]:
        return self._request_json("POST", f"/api/balance/deposits/{deposit_order_id}/sync-stripe-payment", payload={})

    def _get_deposit(self, deposit_order_id: str) -> dict[str, Any]:
        status, data = self._request_json("GET", f"/api/balance/deposits/{deposit_order_id}")
        if status != 200:
            raise VerificationError(f"get deposit detail failed: {status} {data}")
        return data

    def _get_balance(self, user_id: str, currency: str = "USDT") -> dict[str, Any]:
        status, data = self._request_json("GET", f"/api/balance/accounts/{user_id}?currency={currency}")
        if status != 200:
            raise VerificationError(f"get balance failed: {status} {data}")
        return data

    def _make_sig_header(self, payload_json: str) -> str:
        ts = str(int(time.time()))
        signed = f"{ts}.{payload_json}".encode("utf-8")
        digest = hmac.new(self.webhook_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        return f"t={ts},v1={digest}"

    def _send_payment_succeeded_webhook(self, *, deposit_order_id: str, payment_intent_id: str, event_id: str) -> tuple[int, dict[str, Any]]:
        payload = {
            "id": event_id,
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": payment_intent_id,
                    "metadata": {"deposit_order_id": deposit_order_id},
                }
            },
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        sig_header = self._make_sig_header(payload_json)
        return self._request_json(
            "POST",
            "/api/webhooks/stripe",
            raw_body=payload_json.encode("utf-8"),
            extra_headers={"Stripe-Signature": sig_header},
        )

    def case_a_unverified_kyc(self) -> CaseOutcome:
        result = self._create_deposit(
            self.unverified_user_id,
            301.0,
            reference=f"DEP-A-{uuid.uuid4().hex[:8]}",
        )
        deposit_order_id = result["deposit_order"]["id"]
        status, start_result = self._start_checkout(deposit_order_id)
        ok = (
            status == 200
            and start_result.get("status") == "validation_error"
            and start_result.get("next_action") == "complete_kyc"
            and start_result.get("deposit_order", {}).get("channel_status") == "blocked_kyc_required"
        )
        return CaseOutcome(
            name="Case A: Unverified KYC",
            status="PASS" if ok else "FAIL",
            info={
                "deposit_order_id": deposit_order_id,
                "http_status": status,
                "result_status": start_result.get("status"),
                "next_action": start_result.get("next_action"),
                "channel_status": start_result.get("deposit_order", {}).get("channel_status"),
                "message": start_result.get("message"),
            },
        )

    def case_b_verified_kyc(self) -> CaseOutcome:
        self._start_user_kyc(self.verified_user_id)
        result = self._create_deposit(
            self.verified_user_id,
            302.0,
            reference=f"DEP-B-{uuid.uuid4().hex[:8]}",
        )
        deposit_order_id = result["deposit_order"]["id"]
        status, start_result = self._start_checkout(deposit_order_id)
        checkout = start_result.get("checkout") or {}
        result_status = start_result.get("status")
        message = start_result.get("message")
        if status == 200 and result_status == "failed" and _is_local_stripe_network_block(message):
            return CaseOutcome(
                name="Case B: Verified KYC",
                status="SKIP",
                info={
                    "deposit_order_id": deposit_order_id,
                    "http_status": status,
                    "result_status": result_status,
                    "message": message,
                    "skip_reason": "local_stripe_proxy_fake_ip",
                },
            )
        ok = status == 200 and result_status == "ok" and bool(checkout.get("checkout_url"))
        return CaseOutcome(
            name="Case B: Verified KYC",
            status="PASS" if ok else "FAIL",
            info={
                "deposit_order_id": deposit_order_id,
                "http_status": status,
                "result_status": result_status,
                "checkout_session_id": checkout.get("checkout_session_id"),
                "checkout_url": checkout.get("checkout_url"),
                "channel_status": start_result.get("deposit_order", {}).get("channel_status"),
                "message": message,
            },
        )

    def case_c_webhook_success(self) -> CaseOutcome:
        self._start_user_kyc(self.verified_user_id)
        result = self._create_deposit(
            self.verified_user_id,
            303.0,
            reference=f"DEP-C-{uuid.uuid4().hex[:8]}",
        )
        deposit_order_id = result["deposit_order"]["id"]
        _, start_result = self._start_checkout(deposit_order_id)
        checkout = start_result.get("checkout") or {}
        deposit = self._get_deposit(deposit_order_id)
        payment_intent_id = (
            checkout.get("payment_intent_id")
            or deposit["deposit_order"].get("channel_payment_id")
            or f"pi_demo_{uuid.uuid4().hex[:18]}"
        )
        before_balance = self._get_balance(self.verified_user_id)["account"]["available_balance"]
        event_id = f"evt_dep_success_{uuid.uuid4().hex[:10]}"
        status, webhook_result = self._send_payment_succeeded_webhook(
            deposit_order_id=deposit_order_id,
            payment_intent_id=payment_intent_id,
            event_id=event_id,
        )
        after = self._get_deposit(deposit_order_id)
        after_balance = self._get_balance(self.verified_user_id)["account"]["available_balance"]
        ok = (
            status == 200
            and webhook_result.get("result", {}).get("status") in {"updated", "credited", "ok"}
            and after["deposit_order"]["status"] == "credited"
            and after["latest_ledger_entry"] is not None
            and after_balance > before_balance
        )
        return CaseOutcome(
            name="Case C: Webhook Success",
            status="PASS" if ok else "FAIL",
            info={
                "deposit_order_id": deposit_order_id,
                "event_id": event_id,
                "http_status": status,
                "webhook_http_body": webhook_result,
                "webhook_result": webhook_result.get("result"),
                "deposit_status": after["deposit_order"]["status"],
                "channel_status": after["deposit_order"]["channel_status"],
                "balance_before": before_balance,
                "balance_after": after_balance,
                "latest_ledger_entry_id": (after.get("latest_ledger_entry") or {}).get("id"),
            },
        )

    def case_d_webhook_duplicate(self) -> CaseOutcome:
        self._start_user_kyc(self.verified_user_id)
        result = self._create_deposit(
            self.verified_user_id,
            304.0,
            reference=f"DEP-D-{uuid.uuid4().hex[:8]}",
        )
        deposit_order_id = result["deposit_order"]["id"]
        _, start_result = self._start_checkout(deposit_order_id)
        checkout = start_result.get("checkout") or {}
        payment_intent_id = checkout.get("payment_intent_id") or f"pi_demo_{uuid.uuid4().hex[:18]}"
        event_id = f"evt_dep_dup_{uuid.uuid4().hex[:10]}"
        self._send_payment_succeeded_webhook(
            deposit_order_id=deposit_order_id,
            payment_intent_id=payment_intent_id,
            event_id=event_id,
        )
        balance_after_first = self._get_balance(self.verified_user_id)["account"]["available_balance"]
        first_detail = self._get_deposit(deposit_order_id)
        first_ledger_id = (first_detail.get("latest_ledger_entry") or {}).get("id")
        status, second_result = self._send_payment_succeeded_webhook(
            deposit_order_id=deposit_order_id,
            payment_intent_id=payment_intent_id,
            event_id=event_id,
        )
        balance_after_second = self._get_balance(self.verified_user_id)["account"]["available_balance"]
        second_detail = self._get_deposit(deposit_order_id)
        second_ledger_id = (second_detail.get("latest_ledger_entry") or {}).get("id")
        duplicate_status = second_result.get("result", {}).get("status")
        ok = (
            status == 200
            and duplicate_status == "duplicate_ignored"
            and balance_after_first == balance_after_second
            and first_ledger_id == second_ledger_id
        )
        return CaseOutcome(
            name="Case D: Webhook Duplicate",
            status="PASS" if ok else "FAIL",
            info={
                "deposit_order_id": deposit_order_id,
                "event_id": event_id,
                "http_status": status,
                "webhook_http_body": second_result,
                "duplicate_status": duplicate_status,
                "balance_after_first": balance_after_first,
                "balance_after_second": balance_after_second,
                "ledger_id_before": first_ledger_id,
                "ledger_id_after": second_ledger_id,
            },
        )

    def run(self) -> list[CaseOutcome]:
        self._assert_health()
        return [
            self.case_a_unverified_kyc(),
            self.case_b_verified_kyc(),
            self.case_c_webhook_success(),
            self.case_d_webhook_duplicate(),
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify PayFi Box balance deposit + Stripe + KYC flow.")
    parser.add_argument("--api-base", default=os.environ.get("API_BASE_URL", DEFAULT_API_BASE))
    parser.add_argument("--webhook-secret", default=_load_env_value("STRIPE_WEBHOOK_SECRET") or DEFAULT_WEBHOOK_SECRET)
    parser.add_argument("--unverified-user-id", default=os.environ.get("UNVERIFIED_USER_ID", DEFAULT_UNVERIFIED_USER_ID))
    parser.add_argument("--verified-user-id", default=os.environ.get("VERIFIED_USER_ID", DEFAULT_VERIFIED_USER_ID))
    args = parser.parse_args()

    effective_unverified_user_id = _resolve_unverified_user_id(args.unverified_user_id)
    effective_verified_user_id = _resolve_verified_user_id(args.verified_user_id)

    verifier = BalanceDepositVerifier(
        base_url=args.api_base,
        webhook_secret=args.webhook_secret,
        unverified_user_id=effective_unverified_user_id,
        verified_user_id=effective_verified_user_id,
    )

    try:
        outcomes = verifier.run()
    except VerificationError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    failed = False
    for outcome in outcomes:
        print(f"\n=== {outcome.name} ===")
        print(f"PASS: {outcome.status == 'PASS'}")
        print(json.dumps({"status": outcome.status, **outcome.info}, ensure_ascii=False, indent=2))
        failed = failed or outcome.status == "FAIL"

    print(
        json.dumps(
            {
                "effective_unverified_user_id": effective_unverified_user_id,
                "effective_verified_user_id": effective_verified_user_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
