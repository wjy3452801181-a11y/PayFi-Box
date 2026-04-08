#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


DEFAULT_API_BASE = "http://localhost:8000"
DEFAULT_WEBHOOK_SECRET = "whsec_localtest"

# Seed-compatible defaults used in this repo.
DEFAULT_UNVERIFIED_MERCHANT_ID = "75b5c428-5d54-5bf7-838c-65cdee34f68b"
DEFAULT_VERIFIED_MERCHANT_ID = "deaa3ed3-c910-53d0-8796-755d9c82add6"
DEFAULT_BENEFICIARY_ID = "c1779963-6db1-5987-99f6-379acd2bb24b"


class VerificationError(Exception):
    pass


@dataclass
class CaseOutcome:
    name: str
    status: str
    info: dict[str, Any]


class StripeKycVerifier:
    def __init__(
        self,
        *,
        base_url: str,
        webhook_secret: str,
        verified_merchant_id: str,
        unverified_merchant_id: str,
        beneficiary_id: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.webhook_secret = webhook_secret
        self.verified_merchant_id = verified_merchant_id
        self.unverified_merchant_id = unverified_merchant_id
        self.beneficiary_id = beneficiary_id
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

        if raw_body is not None:
            body = raw_body
        else:
            body = json.dumps(payload).encode("utf-8") if payload is not None else None
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

    def _create_quote(self, merchant_id: str, amount: float) -> str:
        status, data = self._request_json(
            "POST",
            "/api/merchant/quote",
            payload={
                "merchant_id": merchant_id,
                "beneficiary_id": self.beneficiary_id,
                "source_currency": "USD",
                "source_amount": amount,
                "target_currency": "USDT",
                "target_network": "hashkey_testnet",
            },
        )
        if status != 200:
            raise VerificationError(f"create quote failed: {status} {data}")
        quote_id = data.get("quote", {}).get("id")
        if not quote_id:
            raise VerificationError(f"missing quote.id: {data}")
        return str(quote_id)

    def _create_intent(self, merchant_id: str, quote_id: str, reference: str) -> str:
        status, data = self._request_json(
            "POST",
            "/api/merchant/fiat-payment",
            payload={
                "quote_id": quote_id,
                "merchant_id": merchant_id,
                "beneficiary_id": self.beneficiary_id,
                "reference": reference,
            },
        )
        if status != 200:
            raise VerificationError(f"create fiat intent failed: {status} {data}")
        intent_id = data.get("fiat_payment", {}).get("id")
        if not intent_id:
            raise VerificationError(f"missing fiat_payment.id: {data}")
        return str(intent_id)

    def _start_stripe_payment(self, fiat_payment_id: str) -> tuple[int, dict[str, Any]]:
        return self._request_json(
            "POST",
            f"/api/merchant/fiat-payment/{fiat_payment_id}/start-stripe-payment",
            payload={},
        )

    def _make_sig_header(self, payload_json: str) -> str:
        ts = str(int(time.time()))
        signed = f"{ts}.{payload_json}".encode("utf-8")
        digest = hmac.new(self.webhook_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        return f"t={ts},v1={digest}"

    def _send_payment_succeeded_webhook(self, *, fiat_payment_id: str, payment_intent_id: str, event_id: str) -> tuple[int, dict[str, Any]]:
        payload = {
            "id": event_id,
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": payment_intent_id,
                    "metadata": {"fiat_payment_intent_id": fiat_payment_id},
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

    def _get_intent_detail(self, fiat_payment_id: str) -> dict[str, Any]:
        status, data = self._request_json("GET", f"/api/merchant/fiat-payment/{fiat_payment_id}")
        if status != 200:
            raise VerificationError(f"get fiat payment detail failed: {status} {data}")
        return data

    def _print_case(self, outcome: CaseOutcome) -> None:
        print(f"\n=== {outcome.name} ===")
        print(f"PASS: {outcome.status == 'PASS'}")
        print(json.dumps({"status": outcome.status, **outcome.info}, ensure_ascii=False, indent=2))

    def case_a_unverified_kyc(self) -> CaseOutcome:
        quote_id = self._create_quote(self.unverified_merchant_id, 101.0)
        fiat_id = self._create_intent(
            self.unverified_merchant_id,
            quote_id,
            reference=f"CASE-A-{uuid.uuid4().hex[:8]}",
        )
        status, result = self._start_stripe_payment(fiat_id)
        channel_status = result.get("fiat_payment", {}).get("channel_status")
        ok = status == 200 and channel_status == "blocked_kyc_required"
        return CaseOutcome(
            name="Case A: Unverified KYC",
            status="PASS" if ok else "FAIL",
            info={
                "http_status": status,
                "fiat_payment_id": fiat_id,
                "result_status": result.get("status"),
                "channel_status": channel_status,
                "next_action": result.get("next_action"),
                "message": result.get("message"),
            },
        )

    def case_b_verified_kyc(self) -> CaseOutcome:
        if not os.environ.get("STRIPE_SECRET_KEY"):
            return CaseOutcome(
                name="Case B: Verified KYC",
                status="SKIP",
                info={"reason": "STRIPE_SECRET_KEY not set; cannot create real Stripe checkout session."},
            )

        quote_id = self._create_quote(self.verified_merchant_id, 102.0)
        fiat_id = self._create_intent(
            self.verified_merchant_id,
            quote_id,
            reference=f"CASE-B-{uuid.uuid4().hex[:8]}",
        )
        status, result = self._start_stripe_payment(fiat_id)
        checkout_url = result.get("checkout", {}).get("checkout_url")
        ok = status == 200 and bool(checkout_url)
        return CaseOutcome(
            name="Case B: Verified KYC",
            status="PASS" if ok else "FAIL",
            info={
                "http_status": status,
                "fiat_payment_id": fiat_id,
                "result_status": result.get("status"),
                "checkout_session_id": result.get("checkout", {}).get("checkout_session_id"),
                "checkout_url": checkout_url,
                "message": result.get("message"),
            },
        )

    def case_c_webhook_success(self) -> CaseOutcome:
        quote_id = self._create_quote(self.verified_merchant_id, 103.0)
        fiat_id = self._create_intent(
            self.verified_merchant_id,
            quote_id,
            reference=f"CASE-C-{uuid.uuid4().hex[:8]}",
        )
        event_id = f"evt_case_c_{uuid.uuid4().hex[:12]}"
        payment_intent_id = f"pi_case_c_{uuid.uuid4().hex[:12]}"
        status, webhook_result = self._send_payment_succeeded_webhook(
            fiat_payment_id=fiat_id,
            payment_intent_id=payment_intent_id,
            event_id=event_id,
        )

        # Chain execution is synchronous but can still take a short moment.
        detail = self._get_intent_detail(fiat_id)
        fiat = detail.get("fiat_payment", {})
        payout_link = detail.get("payout_link") or {}
        payment_order = detail.get("payment_order") or {}

        ok = (
            status == 200
            and fiat.get("status") == "completed"
            and bool(payout_link.get("payment_order_id"))
            and bool(payout_link.get("execution_batch_id"))
            and bool(payment_order.get("tx_hash"))
        )
        return CaseOutcome(
            name="Case C: Webhook Success",
            status="PASS" if ok else "FAIL",
            info={
                "http_status": status,
                "event_result": webhook_result.get("result"),
                "fiat_payment_id": fiat_id,
                "fiat_status": fiat.get("status"),
                "payment_order_id": payout_link.get("payment_order_id"),
                "execution_batch_id": payout_link.get("execution_batch_id"),
                "tx_hash": payment_order.get("tx_hash"),
                "onchain_status": payment_order.get("onchain_status"),
            },
        )

    def case_d_webhook_redelivery(self, *, source: CaseOutcome) -> CaseOutcome:
        if source.status != "PASS":
            return CaseOutcome(
                name="Case D: Webhook Redelivery",
                status="SKIP",
                info={"reason": "Case C did not pass; duplicate-delivery check skipped."},
            )

        # Rebuild identifiers from Case C is not available directly, so we create a dedicated C->D flow.
        quote_id = self._create_quote(self.verified_merchant_id, 104.0)
        fiat_id = self._create_intent(
            self.verified_merchant_id,
            quote_id,
            reference=f"CASE-D-{uuid.uuid4().hex[:8]}",
        )
        event_id = f"evt_case_d_{uuid.uuid4().hex[:12]}"
        payment_intent_id = f"pi_case_d_{uuid.uuid4().hex[:12]}"

        status_first, first = self._send_payment_succeeded_webhook(
            fiat_payment_id=fiat_id,
            payment_intent_id=payment_intent_id,
            event_id=event_id,
        )
        detail_first = self._get_intent_detail(fiat_id)
        payout_first = detail_first.get("payout_link") or {}
        order_first = detail_first.get("payment_order") or {}

        status_second, second = self._send_payment_succeeded_webhook(
            fiat_payment_id=fiat_id,
            payment_intent_id=payment_intent_id,
            event_id=event_id,
        )
        detail_second = self._get_intent_detail(fiat_id)
        payout_second = detail_second.get("payout_link") or {}
        order_second = detail_second.get("payment_order") or {}

        duplicate_ignored = second.get("result", {}).get("status") == "duplicate_ignored"
        no_second_payout = (
            payout_first.get("payment_order_id") == payout_second.get("payment_order_id")
            and payout_first.get("execution_batch_id") == payout_second.get("execution_batch_id")
            and order_first.get("tx_hash") == order_second.get("tx_hash")
        )
        ok = status_first == 200 and status_second == 200 and duplicate_ignored and no_second_payout

        return CaseOutcome(
            name="Case D: Webhook Redelivery",
            status="PASS" if ok else "FAIL",
            info={
                "first_http_status": status_first,
                "first_result": first.get("result"),
                "second_http_status": status_second,
                "second_result": second.get("result"),
                "same_payment_order_id": payout_first.get("payment_order_id") == payout_second.get("payment_order_id"),
                "same_execution_batch_id": payout_first.get("execution_batch_id") == payout_second.get("execution_batch_id"),
                "same_tx_hash": order_first.get("tx_hash") == order_second.get("tx_hash"),
                "payment_order_id": payout_second.get("payment_order_id"),
                "execution_batch_id": payout_second.get("execution_batch_id"),
                "tx_hash": order_second.get("tx_hash"),
                "fiat_payment_id": fiat_id,
            },
        )

    def run(self) -> int:
        self._assert_health()
        outcomes: list[CaseOutcome] = []

        case_a = self.case_a_unverified_kyc()
        outcomes.append(case_a)
        self._print_case(case_a)

        case_b = self.case_b_verified_kyc()
        outcomes.append(case_b)
        self._print_case(case_b)

        case_c = self.case_c_webhook_success()
        outcomes.append(case_c)
        self._print_case(case_c)

        case_d = self.case_d_webhook_redelivery(source=case_c)
        outcomes.append(case_d)
        self._print_case(case_d)

        failed = [o for o in outcomes if o.status == "FAIL"]
        skipped = [o for o in outcomes if o.status == "SKIP"]
        print("\n=== Stripe + KYC Verification Summary ===")
        print(f"PASS: {len([o for o in outcomes if o.status == 'PASS'])}")
        print(f"FAIL: {len(failed)}")
        print(f"SKIP: {len(skipped)}")
        if failed:
            print("Overall: FAIL")
            return 1
        print("Overall: PASS")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Stripe + KYC merchant settlement cases.")
    parser.add_argument("--base-url", default=os.environ.get("API_BASE_URL", DEFAULT_API_BASE))
    parser.add_argument("--webhook-secret", default=os.environ.get("STRIPE_WEBHOOK_SECRET", DEFAULT_WEBHOOK_SECRET))
    parser.add_argument("--verified-merchant-id", default=os.environ.get("VERIFIED_MERCHANT_ID", DEFAULT_VERIFIED_MERCHANT_ID))
    parser.add_argument("--unverified-merchant-id", default=os.environ.get("UNVERIFIED_MERCHANT_ID", DEFAULT_UNVERIFIED_MERCHANT_ID))
    parser.add_argument("--beneficiary-id", default=os.environ.get("BENEFICIARY_ID", DEFAULT_BENEFICIARY_ID))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    verifier = StripeKycVerifier(
        base_url=args.base_url,
        webhook_secret=args.webhook_secret,
        verified_merchant_id=args.verified_merchant_id,
        unverified_merchant_id=args.unverified_merchant_id,
        beneficiary_id=args.beneficiary_id,
    )
    try:
        return verifier.run()
    except VerificationError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
