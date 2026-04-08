#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, parse, request


ROOT = Path(__file__).resolve().parents[1]


class VerificationError(Exception):
    def __init__(self, reason: str, hint: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.hint = hint


@dataclass
class CheckResult:
    label: str
    status: str = "SKIP"
    reason: str = ""
    hint: str = ""

    def pass_(self) -> None:
        self.status = "PASS"
        self.reason = ""
        self.hint = ""

    def fail(self, reason: str, hint: str) -> None:
        self.status = "FAIL"
        self.reason = reason
        self.hint = hint


class Step7BVerifier:
    def __init__(
        self,
        *,
        base_url: str,
        reset_db: bool,
        date_from: str,
        date_to: str,
        health_only: bool,
        min_beneficiaries: int,
        min_payments: int,
        min_commands: int,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.reset_db = reset_db
        self.date_from = date_from
        self.date_to = date_to
        self.health_only = health_only
        self.min_beneficiaries = min_beneficiaries
        self.min_payments = min_payments
        self.min_commands = min_commands
        self.timeout_seconds = timeout_seconds
        # Force direct local calls; avoid corporate/system proxy interference on localhost.
        self._opener = request.build_opener(request.ProxyHandler({}))

        self.checks = [
            CheckResult("api health"),
            CheckResult("data preconditions"),
            CheckResult("timeline"),
            CheckResult("replay side effects"),
            CheckResult("retry safety"),
            CheckResult("reports summary"),
            CheckResult("blocked lifecycle"),
        ]
        self.check_map = {c.label: c for c in self.checks}

        self.timeline_command_id: str | None = None
        self.blocked_command_id: str | None = None
        self.executed_payment_id: str | None = None
        self.non_retriable_payment_id: str | None = None
        self.bootstrap_command_id: str | None = None
        self.precondition_snapshot: dict[str, int] | None = None
        self.semantic_coverage: dict[str, dict[str, str]] | None = None

    def run(self) -> int:
        try:
            if self.health_only:
                print("[INFO] baseline mode: OFF (health-only check, no reset/seed)")
            elif self.reset_db:
                print("[INFO] baseline mode: ON (will run make db + make migrate + make reset-db)")
            else:
                print("[INFO] baseline mode: OFF (no automatic reset/seed)")

            if self.reset_db:
                self._prepare_baseline()

            self._run_api_health()
            if self.check_map["api health"].status == "FAIL":
                return self._finish()

            if self.health_only:
                return self._finish()

            self._run_data_preconditions()
            if self.check_map["data preconditions"].status == "FAIL":
                return self._finish()

            self._run_timeline()
            self._run_replay_side_effects()
            self._run_retry_safety()
            self._run_reports_summary()
            self._run_blocked_lifecycle()
            return self._finish()
        except Exception as exc:  # pragma: no cover
            self.check_map["api health"].fail(
                f"unexpected script error: {exc}",
                "Inspect traceback and fix script/runtime prerequisites.",
            )
            return self._finish()

    def _prepare_baseline(self) -> None:
        print("[INFO] resetting local baseline via make db + make migrate + make reset-db")
        self._run_make("db")
        self._run_make("migrate")
        self._run_make("reset-db")
        print("[INFO] baseline reset complete")

    def _run_make(self, target: str) -> None:
        proc = subprocess.run(
            ["make", target],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.returncode != 0:
            output = proc.stdout.strip().splitlines()
            tail = "\n".join(output[-8:]) if output else "(no output)"
            raise VerificationError(
                reason=f"make {target} failed.",
                hint=f"fix the command and retry.\nlast output:\n{tail}",
            )

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url=url, method=method, data=data, headers=headers)
        try:
            with self._opener.open(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise VerificationError(
                reason=f"{method} {path} returned HTTP {exc.code}.",
                hint=f"response: {body}",
            )
        except error.URLError as exc:
            raise VerificationError(
                reason=f"{method} {path} request failed: {exc.reason}",
                hint="ensure API is running at the configured base URL.",
            )

    def _expect(self, cond: bool, reason: str, hint: str) -> None:
        if not cond:
            raise VerificationError(reason=reason, hint=hint)

    def _run_api_health(self) -> None:
        check = self.check_map["api health"]
        try:
            data = self._request_json("GET", "/health")
            self._expect(
                data.get("status") == "ok" and data.get("service") == "payfi-box-api",
                "GET /health did not return expected payload.",
                "start API with make api, then rerun verification.",
            )
            check.pass_()
        except VerificationError as err:
            check.fail(err.reason, err.hint)

    def _run_data_preconditions(self) -> None:
        check = self.check_map["data preconditions"]
        try:
            beneficiary_total = (self._beneficiaries(limit=1).get("total"))
            payment_total = (self._payments(limit=1).get("total"))
            command_total = (self._commands(limit=1).get("total"))
            executed_total = (self._payments(status="executed", limit=1).get("total"))
            create_payment_total = (self._commands(intent="create_payment", limit=1).get("total"))

            payments_for_split = self._payments(limit=100)
            payment_items = payments_for_split.get("items") or []

            medium_risk_total = (self._beneficiaries(risk_level="medium", limit=1).get("total"))
            high_risk_total = (self._beneficiaries(risk_level="high", limit=1).get("total"))

            self._expect(
                isinstance(beneficiary_total, int),
                "beneficiaries total is missing/not int.",
                "check /api/beneficiaries response contract.",
            )
            self._expect(
                isinstance(payment_total, int),
                "payments total is missing/not int.",
                "check /api/payments response contract.",
            )
            self._expect(
                isinstance(command_total, int),
                "commands total is missing/not int.",
                "check /api/commands response contract.",
            )
            self._expect(
                isinstance(executed_total, int),
                "executed payments total is missing/not int.",
                "check /api/payments?status=executed response contract.",
            )
            self._expect(
                isinstance(create_payment_total, int),
                "create_payment commands total is missing/not int.",
                "check /api/commands?intent=create_payment response contract.",
            )
            self._expect(
                isinstance(payment_items, list),
                "payments.items is not a list for split precondition check.",
                "check /api/payments response contract.",
            )
            self._expect(
                isinstance(medium_risk_total, int) and isinstance(high_risk_total, int),
                "risky beneficiaries totals are missing/not int.",
                "check /api/beneficiaries?risk_level=medium/high response contract.",
            )

            split_payment_count = sum(1 for item in payment_items if int(item.get("split_count") or 0) > 1)
            risky_beneficiary_count = int(medium_risk_total) + int(high_risk_total)
            self.precondition_snapshot = {
                "beneficiaries_total": int(beneficiary_total),
                "payments_total": int(payment_total),
                "commands_total": int(command_total),
                "executed_count": int(executed_total),
                "split_payment_count": int(split_payment_count),
                "medium_risk_beneficiary_count": int(medium_risk_total),
                "high_risk_beneficiary_count": int(high_risk_total),
                "risky_beneficiary_count": int(risky_beneficiary_count),
                "create_payment_commands": int(create_payment_total),
            }
            self.semantic_coverage = {
                "executed payment coverage": {
                    "status": "PASS" if int(executed_total) >= 1 else "FAIL",
                    "reason": "" if int(executed_total) >= 1 else "no executed-payment coverage found",
                    "hint": ""
                    if int(executed_total) >= 1
                    else "check seeded payment execution coverage (status=executed), or run make reset-db.",
                    "context": f"executed_count = {int(executed_total)}",
                },
                "split payment coverage": {
                    "status": "PASS" if int(split_payment_count) >= 1 else "FAIL",
                    "reason": "" if int(split_payment_count) >= 1 else "no split-payment coverage found",
                    "hint": ""
                    if int(split_payment_count) >= 1
                    else "ensure seeded split-payment examples exist (payment orders with split_count > 1), or run make reset-db.",
                    "context": f"split_payment_count = {int(split_payment_count)}",
                },
                "risky beneficiary coverage": {
                    "status": "PASS" if int(risky_beneficiary_count) >= 1 else "FAIL",
                    "reason": "" if int(risky_beneficiary_count) >= 1 else "no risky-beneficiary coverage found",
                    "hint": ""
                    if int(risky_beneficiary_count) >= 1
                    else "check beneficiary seed risk levels (medium/high), or run make reset-db.",
                    "context": f"risky_beneficiary_count = {int(risky_beneficiary_count)}",
                },
                "create_payment command coverage": {
                    "status": "PASS" if int(create_payment_total) >= 1 else "FAIL",
                    "reason": "" if int(create_payment_total) >= 1 else "no create_payment-command coverage found",
                    "hint": ""
                    if int(create_payment_total) >= 1
                    else "check command seed dataset includes create_payment intent, or run make reset-db.",
                    "context": f"create_payment_commands = {int(create_payment_total)}",
                },
            }

            violations: list[str] = []
            hint_parts: list[str] = []
            if beneficiary_total < self.min_beneficiaries:
                violations.append(f"beneficiaries={beneficiary_total} (< {self.min_beneficiaries})")
                hint_parts.append(
                    f"increase beneficiary seed coverage or lower --min-beneficiaries (current={beneficiary_total})."
                )
            if payment_total < self.min_payments:
                violations.append(f"payments={payment_total} (< {self.min_payments})")
                hint_parts.append(f"increase payment seed coverage or lower --min-payments (current={payment_total}).")
            if command_total < self.min_commands:
                violations.append(f"commands={command_total} (< {self.min_commands})")
                hint_parts.append(f"increase command seed coverage or lower --min-commands (current={command_total}).")
            if executed_total < 1:
                violations.append("executed_count=0 (< 1)")
                hint_parts.append(
                    "check seeded payment execution coverage (status=executed) and run make reset-db if needed."
                )
            if split_payment_count < 1:
                violations.append("split_payment_count=0 (< 1)")
                hint_parts.append(
                    "ensure split-payment seed examples exist (payment orders with split_count > 1), and run make reset-db if needed."
                )
            if risky_beneficiary_count < 1:
                violations.append("risky_beneficiary_count=0 (< 1)")
                hint_parts.append(
                    "check beneficiary seed risk levels (medium/high) and run make reset-db if needed."
                )
            if create_payment_total < 1:
                violations.append("create_payment_commands=0 (< 1)")
                hint_parts.append(
                    "check command seed dataset includes create_payment intent and run make reset-db if needed."
                )

            self._expect(
                len(violations) == 0,
                "seed data preconditions failed: " + ", ".join(violations),
                " | ".join(hint_parts)
                if hint_parts
                else "run make verify-step7b-reset to prepare baseline, or lower thresholds via --min-beneficiaries/--min-payments/--min-commands.",
            )
            check.pass_()
        except VerificationError as err:
            check.fail(err.reason, err.hint)

    def _payments(self, **params: Any) -> dict[str, Any]:
        q = parse.urlencode(params)
        return self._request_json("GET", f"/api/payments?{q}")

    def _commands(self, **params: Any) -> dict[str, Any]:
        q = parse.urlencode(params)
        return self._request_json("GET", f"/api/commands?{q}")

    def _beneficiaries(self, **params: Any) -> dict[str, Any]:
        q = parse.urlencode(params)
        return self._request_json("GET", f"/api/beneficiaries?{q}")

    def _pick_user_id(self) -> str:
        payments = self._payments(limit=1)
        items = payments.get("items") or []
        self._expect(
            isinstance(items, list) and len(items) > 0 and items[0].get("user_id"),
            "cannot find a user_id from existing payments.",
            "ensure seed data exists (make verify-seed).",
        )
        return str(items[0]["user_id"])

    def _bootstrap_confirmed_flow(self) -> str:
        user_id = self._pick_user_id()
        cmd = self._request_json(
            "POST",
            "/api/command",
            {
                "user_id": user_id,
                "text": "给 ACME 支付 30000 USDT，拆成 3 笔，备注 VERIFY-STEP7B",
            },
        )
        command_id = cmd.get("command_id")
        self._expect(
            isinstance(command_id, str) and command_id,
            "failed to create bootstrap command.",
            "check /api/command behavior and seeded beneficiaries.",
        )
        confirm = self._request_json(
            "POST",
            "/api/confirm",
            {
                "command_id": command_id,
                "confirmed": True,
                "actor_user_id": user_id,
            },
        )
        self._expect(
            confirm.get("status") == "ok" and confirm.get("payment_order_id"),
            "bootstrap confirm did not create a payment order.",
            "check /api/confirm path and create_payment parsing.",
        )
        return str(command_id)

    def _select_confirmed_command(self) -> str:
        if self.reset_db:
            if self.bootstrap_command_id:
                return self.bootstrap_command_id
            self.bootstrap_command_id = self._bootstrap_confirmed_flow()
            return self.bootstrap_command_id

        cmds = self._commands(limit=100)
        items = cmds.get("items") or []
        if isinstance(items, list):
            for item in items:
                if item.get("linked_payment_order_id") and item.get("intent") == "create_payment":
                    return str(item["command_id"])
        raise VerificationError(
            reason="no create_payment command linked to a payment order found.",
            hint="run make verify-step7b-reset or ensure confirmed create_payment commands exist.",
        )

    def _timeline_contains_required_actions(self, items: list[dict[str, Any]]) -> bool:
        actions = [str(x.get("action", "")) for x in items]
        entity_types = [str(x.get("entity_type", "")) for x in items]

        has_confirm = any(a.startswith("confirm_") or a == "command_confirmation_snapshot" for a in actions)
        has_execution = any(a in {"mock_execute", "retry_mock_executed", "payment_execution_snapshot"} for a in actions)
        return (
            "command_received" in actions
            and "command_parsed" in actions
            and has_confirm
            and "payment_order" in entity_types
            and "payment_split" in entity_types
            and has_execution
        )

    def _parse_ts(self, value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    def _run_timeline(self) -> None:
        check = self.check_map["timeline"]
        try:
            command_id = self._select_confirmed_command()
            self.timeline_command_id = command_id
            timeline = self._request_json("GET", f"/api/commands/{command_id}/timeline")
            items = timeline.get("items")
            self._expect(
                isinstance(items, list) and len(items) > 0,
                "timeline returned no items.",
                "ensure command timeline aggregation is enabled.",
            )
            for item in items:
                self._expect("timestamp" in item, "timeline item missing timestamp.", "include timestamp in timeline item.")
                self._expect("title" in item and str(item["title"]).strip(), "timeline item missing title.", "include human-readable title.")
                self._expect("action" in item and str(item["action"]).strip(), "timeline item missing action.", "include action code.")
                self._expect("details" in item, "timeline item missing details field.", "include details field (nullable is fine).")

            timestamps = [self._parse_ts(str(item["timestamp"])) for item in items]
            self._expect(
                timestamps == sorted(timestamps),
                "timeline is not ordered ascending by timestamp.",
                "sort timeline events in ascending order.",
            )
            self._expect(
                self._timeline_contains_required_actions(items),
                "timeline missing expected lifecycle actions/entities.",
                "ensure command/confirm/order/split/execution events are aggregated.",
            )
            check.pass_()
        except VerificationError as err:
            check.fail(err.reason, err.hint)

    def _metrics(self) -> dict[str, int]:
        commands = self._commands(limit=100)
        payments = self._payments(limit=100)
        executed = self._payments(status="executed", limit=100)

        command_total = commands.get("total")
        payment_total = payments.get("total")
        executed_total = executed.get("total")
        payment_items = payments.get("items") or []
        self._expect(isinstance(command_total, int), "commands total is missing/not int.", "check /api/commands response contract.")
        self._expect(isinstance(payment_total, int), "payments total is missing/not int.", "check /api/payments response contract.")
        self._expect(isinstance(executed_total, int), "executed payment total is missing/not int.", "check /api/payments?status=executed contract.")
        self._expect(isinstance(payment_items, list), "payments.items is not a list.", "check /api/payments response shape.")

        if payment_total > 100:
            raise VerificationError(
                reason="payment dataset exceeds 100 rows; split metric becomes ambiguous with current API limit.",
                hint="use a smaller local dataset or add pagination-aware split counting endpoint.",
            )
        split_total = sum(int(item.get("split_count") or 0) for item in payment_items)
        return {
            "commands_total": command_total,
            "payments_total": payment_total,
            "split_total": split_total,
            "executed_total": executed_total,
        }

    def _run_replay_side_effects(self) -> None:
        check = self.check_map["replay side effects"]
        try:
            command_id = self.timeline_command_id or self._select_confirmed_command()
            before = self._metrics()
            replay = self._request_json("POST", f"/api/commands/{command_id}/replay", {})
            after = self._metrics()

            self._expect(replay.get("mode") == "replay", "replay response missing mode=replay.", "return explicit replay mode.")
            self._expect(
                str(replay.get("source_command_id")) == str(command_id),
                "replay response source_command_id mismatch.",
                "ensure replay references original command id.",
            )
            preview = replay.get("preview")
            self._expect(
                isinstance(preview, dict) and isinstance(preview.get("type"), str) and preview.get("type"),
                "replay response missing preview object/type.",
                "return fresh preview payload from parser.",
            )

            self._expect(
                before == after,
                f"replay changed metrics: before={before}, after={after}.",
                "replay must not create commands/payments/splits or execution side effects.",
            )
            check.pass_()
        except VerificationError as err:
            check.fail(err.reason, err.hint)

    def _select_retry_records(self) -> tuple[str, str]:
        executed_items = (self._payments(status="executed", limit=1).get("items") or [])
        self._expect(
            len(executed_items) > 0 and executed_items[0].get("id"),
            "no executed payment available for retry safety check.",
            "ensure seed data has executed payments.",
        )
        executed_id = str(executed_items[0]["id"])

        cancelled_items = (self._payments(status="cancelled", limit=100).get("items") or [])
        non_retriable_id = None
        for item in cancelled_items:
            beneficiary = item.get("beneficiary") or {}
            if beneficiary.get("is_blacklisted") is True and item.get("id"):
                non_retriable_id = str(item["id"])
                break
        if non_retriable_id is None and cancelled_items:
            non_retriable_id = str(cancelled_items[0]["id"])

        self._expect(
            bool(non_retriable_id),
            "no cancelled/non-retriable payment available for retry safety check.",
            "ensure dataset includes cancelled payment examples.",
        )
        return executed_id, str(non_retriable_id)

    def _payment_status(self, payment_id: str) -> str:
        detail = self._request_json("GET", f"/api/payments/{payment_id}")
        status = ((detail.get("payment") or {}).get("status"))
        self._expect(
            isinstance(status, str) and status,
            f"payment detail missing status for {payment_id}.",
            "check /api/payments/{id} contract.",
        )
        return status

    def _run_retry_safety(self) -> None:
        check = self.check_map["retry safety"]
        try:
            executed_id, non_retriable_id = self._select_retry_records()
            self.executed_payment_id = executed_id
            self.non_retriable_payment_id = non_retriable_id

            before = self._payment_status(executed_id)
            resp = self._request_json("POST", f"/api/payments/{executed_id}/retry-mock", {})
            after = self._payment_status(executed_id)
            self._expect(
                resp.get("status") in {"not_needed", "non_retriable"} and resp.get("retry_performed") is False,
                "executed payment retry response is unsafe.",
                "executed payment retry should return not_needed/non_retriable with no mutation.",
            )
            self._expect(
                before == "executed" and after == "executed",
                f"executed payment status changed unexpectedly ({before} -> {after}).",
                "retry on executed payment must keep status unchanged.",
            )

            before_non = self._payment_status(non_retriable_id)
            resp_non = self._request_json("POST", f"/api/payments/{non_retriable_id}/retry-mock", {})
            after_non = self._payment_status(non_retriable_id)
            self._expect(
                resp_non.get("status") == "non_retriable" and resp_non.get("retry_performed") is False,
                "non-retriable payment retry response is unsafe.",
                "cancelled/blocked-like payments must return non_retriable.",
            )
            self._expect(
                before_non == after_non,
                f"non-retriable payment status changed unexpectedly ({before_non} -> {after_non}).",
                "non-retriable retry must never mutate payment status.",
            )
            check.pass_()
        except VerificationError as err:
            check.fail(err.reason, err.hint)

    def _run_reports_summary(self) -> None:
        check = self.check_map["reports summary"]
        try:
            report = self._request_json(
                "GET",
                f"/api/reports/summary?status=executed&risk_level=medium&currency=USDT&date_from={self.date_from}&date_to={self.date_to}",
            )
            filters = report.get("filters") or {}
            self._expect(isinstance(report.get("metrics"), dict), "reports summary missing metrics.", "include metrics section.")
            self._expect(isinstance(report.get("by_country"), list), "reports summary missing by_country.", "include by_country grouping.")
            self._expect(isinstance(report.get("by_currency"), list), "reports summary missing by_currency.", "include by_currency grouping.")
            self._expect(isinstance(report.get("by_status"), list), "reports summary missing by_status.", "include by_status grouping.")
            self._expect(isinstance(report.get("by_risk_level"), list), "reports summary missing by_risk_level.", "include by_risk_level grouping.")
            self._expect(isinstance(report.get("by_risk_reason_code"), list), "reports summary missing by_risk_reason_code.", "include by_risk_reason_code grouping.")
            self._expect(isinstance(report.get("latest_commands"), list), "reports summary missing latest_commands.", "include latest_commands sample.")
            self._expect(isinstance(report.get("latest_report_jobs"), list), "reports summary missing latest_report_jobs.", "include latest_report_jobs sample.")
            self._expect(
                filters.get("status") == "executed"
                and filters.get("risk_level") == "medium"
                and filters.get("currency") == "USDT"
                and filters.get("date_from") == self.date_from
                and filters.get("date_to") == self.date_to,
                "reports summary filters are not reflected in response.",
                "ensure filter echo and parsing are wired correctly.",
            )
            check.pass_()
        except VerificationError as err:
            check.fail(err.reason, err.hint)

    def _run_blocked_lifecycle(self) -> None:
        check = self.check_map["blocked lifecycle"]
        try:
            if self.reset_db:
                self._assert_blocked_flow_with_explicit_creation()
            else:
                self._assert_blocked_flow_without_mutation()
            check.pass_()
        except VerificationError as err:
            check.fail(err.reason, err.hint)

    def _pick_blacklisted_beneficiary_name(self) -> str:
        rows = (self._beneficiaries(is_blacklisted="true", limit=50).get("items") or [])
        self._expect(
            isinstance(rows, list) and len(rows) > 0,
            "no blacklisted beneficiary found.",
            "ensure seed data includes at least one blacklisted beneficiary.",
        )
        for item in rows:
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        raise VerificationError(
            reason="blacklisted beneficiaries exist but none has a usable name.",
            hint="ensure beneficiary.name is non-empty in seed data.",
        )

    def _assert_blocked_flow_with_explicit_creation(self) -> None:
        user_id = self._pick_user_id()
        blocked_name = self._pick_blacklisted_beneficiary_name()
        executed_before = int((self._payments(status="executed", limit=100).get("total") or 0))
        cmd = self._request_json(
            "POST",
            "/api/command",
            {
                "user_id": user_id,
                "text": f"给 {blocked_name} 支付 12000 USDT，备注 BLK-VERIFY",
            },
        )
        cmd_id = cmd.get("command_id")
        self._expect(
            isinstance(cmd_id, str) and cmd_id,
            "failed to create blocked-flow command.",
            "check command endpoint and seeded blacklisted beneficiary data.",
        )
        self.blocked_command_id = str(cmd_id)
        self._expect(
            ((cmd.get("risk") or {}).get("decision") == "block"),
            "blocked-flow command did not emit risk block signal.",
            "blacklisted beneficiary command should return risk.decision=block.",
        )

        confirm = self._request_json(
            "POST",
            "/api/confirm",
            {
                "command_id": cmd_id,
                "confirmed": True,
                "actor_user_id": user_id,
            },
        )
        self._expect(
            confirm.get("status") == "blocked"
            and confirm.get("payment_order_id") is None
            and ((confirm.get("execution") or {}).get("executed") is False),
            "blocked-flow confirmation is inconsistent.",
            "blocked confirm must not produce executable payment order.",
        )

        detail = self._request_json("GET", f"/api/commands/{cmd_id}")
        self._expect(
            ((detail.get("command") or {}).get("final_status") == "blocked")
            and detail.get("linked_payment") is None,
            "blocked command detail invariants failed.",
            "blocked command should remain unlinked to payment orders.",
        )

        replay_before = self._metrics()
        replay = self._request_json("POST", f"/api/commands/{cmd_id}/replay", {})
        replay_after = self._metrics()
        self._expect(
            replay.get("mode") == "replay" and ((replay.get("risk") or {}).get("decision") == "block"),
            "blocked replay did not preserve risk block semantics.",
            "replay must stay blocked for blacklisted beneficiary flow.",
        )
        self._expect(
            replay_before == replay_after,
            f"blocked replay created side effects (before={replay_before}, after={replay_after}).",
            "replay must be side-effect free even for blocked flows.",
        )

        executed_after = int((self._payments(status="executed", limit=100).get("total") or 0))
        self._expect(
            executed_before == executed_after,
            f"blocked flow changed executed payment count ({executed_before} -> {executed_after}).",
            "blocked flow must never create executed payments.",
        )

    def _assert_blocked_flow_without_mutation(self) -> None:
        # Ensure the dataset still exposes at least one blacklisted beneficiary,
        # even in passive (no-mutation) verification mode.
        self._pick_blacklisted_beneficiary_name()

        blocked = self._commands(final_status="blocked", limit=10).get("items") or []
        self._expect(
            isinstance(blocked, list) and len(blocked) > 0,
            "no blocked command found in current dataset for passive verification.",
            "run make verify-step7b-reset to execute deterministic blocked-flow validation.",
        )
        cmd_id = str(blocked[0]["command_id"])
        self.blocked_command_id = cmd_id
        detail = self._request_json("GET", f"/api/commands/{cmd_id}")
        self._expect(
            ((detail.get("command") or {}).get("final_status") == "blocked")
            and detail.get("linked_payment") is None
            and ((detail.get("risk") or {}).get("decision") == "block"),
            "existing blocked command does not satisfy blocked invariants.",
            "inspect blocked command/detail/risk semantics.",
        )

        before = self._metrics()
        replay = self._request_json("POST", f"/api/commands/{cmd_id}/replay", {})
        after = self._metrics()
        self._expect(
            replay.get("mode") == "replay" and ((replay.get("risk") or {}).get("decision") == "block"),
            "blocked replay did not preserve risk block semantics.",
            "replay should remain blocked for blocked source command.",
        )
        self._expect(
            before == after,
            f"blocked replay changed metrics (before={before}, after={after}).",
            "replay should not mutate data in no-reset mode.",
        )

    def _finish(self) -> int:
        pass_count = sum(1 for c in self.checks if c.status == "PASS")
        fail_count = sum(1 for c in self.checks if c.status == "FAIL")
        warn_count = sum(1 for c in self.checks if c.status == "WARN")

        print("\nStep 7B verification summary")
        for c in self.checks:
            print(f"- {c.label}: {c.status}")
            if c.status in {"FAIL", "WARN"}:
                if c.reason:
                    print(f"  reason: {c.reason}")
                if c.hint:
                    print(f"  hint: {c.hint}")

        print("\nContext:")
        print(f"- base_url: {self.base_url}")
        print(f"- reset_db: {self.reset_db}")
        print(f"- reports window: {self.date_from} to {self.date_to}")
        print(
            f"- precondition mins: beneficiaries>={self.min_beneficiaries}, payments>={self.min_payments}, commands>={self.min_commands}"
        )
        if self.precondition_snapshot is not None:
            print("- semantic precondition snapshot:")
            print(f"  - beneficiaries_total: {self.precondition_snapshot['beneficiaries_total']}")
            print(f"  - payments_total: {self.precondition_snapshot['payments_total']}")
            print(f"  - commands_total: {self.precondition_snapshot['commands_total']}")
            print(f"  - executed_count: {self.precondition_snapshot['executed_count']}")
            print(
                f"  - split_payment_count: {self.precondition_snapshot['split_payment_count']} (payment orders with split_count > 1)"
            )
            print(
                f"  - medium_risk_beneficiary_count: {self.precondition_snapshot['medium_risk_beneficiary_count']}"
            )
            print(
                f"  - high_risk_beneficiary_count: {self.precondition_snapshot['high_risk_beneficiary_count']}"
            )
            print(f"  - risky_beneficiary_count: {self.precondition_snapshot['risky_beneficiary_count']}")
            print(f"  - create_payment_commands: {self.precondition_snapshot['create_payment_commands']}")
        if self.semantic_coverage is not None:
            total_semantic = len(self.semantic_coverage)
            pass_semantic = sum(1 for item in self.semantic_coverage.values() if item.get("status") == "PASS")
            fail_semantic = total_semantic - pass_semantic
            semantic_summary = (
                f"{pass_semantic}/{total_semantic} PASS"
                if fail_semantic == 0
                else f"{pass_semantic}/{total_semantic} PASS ({fail_semantic} FAIL)"
            )
            print(f"- semantic coverage: {semantic_summary}")
            for label, item in self.semantic_coverage.items():
                print(f"  - {label}: {item.get('status', 'SKIP')}")
                if item.get("status") == "FAIL":
                    if item.get("reason"):
                        print(f"    reason: {item['reason']}")
                    if item.get("hint"):
                        print(f"    hint: {item['hint']}")
                    if item.get("context"):
                        print("    context:")
                        print(f"      {item['context']}")
        print(f"- timeline command id: {self.timeline_command_id or 'n/a'}")
        print(f"- executed payment id: {self.executed_payment_id or 'n/a'}")
        print(f"- non-retriable payment id: {self.non_retriable_payment_id or 'n/a'}")
        print(f"- blocked command id: {self.blocked_command_id or 'n/a'}")

        print("\nOverall: PASS" if fail_count == 0 else "\nOverall: FAIL")
        print(f"Counts: pass={pass_count}, fail={fail_count}, warn={warn_count}")
        return 0 if fail_count == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 7B backend verification for PayFi Box.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--date-from", default="2026-03-01")
    parser.add_argument("--date-to", default="2026-03-31")
    parser.add_argument("--reset-db", action="store_true", help="Run make db/migrate/reset-db before verification.")
    parser.add_argument("--health-only", action="store_true", help="Only run API health verification.")
    parser.add_argument("--min-beneficiaries", type=int, default=5, help="Minimum beneficiaries count required.")
    parser.add_argument("--min-payments", type=int, default=10, help="Minimum payments count required.")
    parser.add_argument("--min-commands", type=int, default=5, help="Minimum commands count required.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    verifier = Step7BVerifier(
        base_url=args.base_url,
        reset_db=bool(args.reset_db),
        date_from=args.date_from,
        date_to=args.date_to,
        health_only=bool(args.health_only),
        min_beneficiaries=int(args.min_beneficiaries),
        min_payments=int(args.min_payments),
        min_commands=int(args.min_commands),
    )
    return verifier.run()


if __name__ == "__main__":
    sys.exit(main())
