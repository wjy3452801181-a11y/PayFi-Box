#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
USER_ID="${USER_ID:-deaa3ed3-c910-53d0-8796-755d9c82add6}"
SESSION_ID="${SESSION_ID:-5ad9af15-ca05-5124-8ae6-3492f0090dca}"

if ! command -v jq >/dev/null 2>&1; then
  echo "[FAIL] jq is required but not installed"
  exit 2
fi

assert_json() {
  local name="$1"
  local json="$2"
  local expr="$3"
  if echo "$json" | jq -e "$expr" >/dev/null; then
    echo "[PASS] $name"
  else
    echo "[FAIL] $name"
    echo "  expr: $expr"
    echo "  json: $json"
    exit 1
  fi
}

echo "== 0) API health =="
health="$(curl -s "$API_BASE/health")"
assert_json "health" "$health" '.status=="ok" and .service=="payfi-box-api"'

echo
echo "== A) user_wallet confirm =="
cmd_uw="$(curl -s -X POST "$API_BASE/api/command" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\",\"text\":\"给 ACME 支付 88 USDT\"}")"
cmd_uw_id="$(echo "$cmd_uw" | jq -r '.command_id')"

confirm_uw="$(curl -s -X POST "$API_BASE/api/confirm" \
  -H "Content-Type: application/json" \
  -d "{\"command_id\":\"$cmd_uw_id\",\"confirmed\":true,\"execution_mode\":\"user_wallet\"}")"

assert_json "user_wallet mode" "$confirm_uw" '.execution_mode=="user_wallet"'
assert_json "user_wallet next_action" "$confirm_uw" '.next_action=="sign_in_wallet"'
assert_json "user_wallet unsigned payload" "$confirm_uw" '(.unsigned_transactions | length) >= 1'
assert_json "user_wallet no backend submit at confirm" "$confirm_uw" '.execution.tx_hash == null and ([.execution_items[].tx_hash] | all(. == null))'

uw_payment_id="$(echo "$confirm_uw" | jq -r '.payment_order_id')"
uw_item_id="$(echo "$confirm_uw" | jq -r '.execution_items[0].execution_item_id')"
uw_item_hex="${uw_item_id//-/}"
uw_fake_tx="0x${uw_item_hex}${uw_item_hex}"

echo
echo "== B) user_wallet attach-tx + sync-receipt =="
attach_uw="$(curl -s -X POST "$API_BASE/api/execution-items/$uw_item_id/attach-tx" \
  -H "Content-Type: application/json" \
  -d "{\"tx_hash\":\"$uw_fake_tx\",\"wallet_address\":\"0xEf724DF77c65aFfC8c3A67AE0dB0adD344F607B3\"}")"

assert_json "user_wallet attach-tx ok" "$attach_uw" '.status=="ok"'
assert_json "user_wallet attach submitted" "$attach_uw" '.item_status=="submitted" and .onchain_status=="submitted_onchain"'
assert_json "user_wallet attach hash echoed" "$attach_uw" ".tx_hash==\"$uw_fake_tx\""

sync_uw="$(curl -s -X POST "$API_BASE/api/execution-items/$uw_item_id/sync-receipt" \
  -H "Content-Type: application/json" \
  -d '{}')"
assert_json "user_wallet sync returns deterministic state" "$sync_uw" '.status=="pending" or .status=="ok" or .status=="no_change"'

echo
echo "== C) safe confirm + attach proposal + attach tx + sync =="
cmd_safe="$(curl -s -X POST "$API_BASE/api/command" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\",\"text\":\"Pay ACME 66 USDT\"}")"
cmd_safe_id="$(echo "$cmd_safe" | jq -r '.command_id')"

confirm_safe="$(curl -s -X POST "$API_BASE/api/confirm" \
  -H "Content-Type: application/json" \
  -d "{\"command_id\":\"$cmd_safe_id\",\"confirmed\":true,\"execution_mode\":\"safe\"}")"

assert_json "safe mode" "$confirm_safe" '.execution_mode=="safe"'
assert_json "safe next_action" "$confirm_safe" '.next_action=="approve_in_safe"'
assert_json "safe proposal payload exists" "$confirm_safe" '.safe_proposal != null and (.safe_proposal.transactions | length) >= 1'
assert_json "safe no backend submit at confirm" "$confirm_safe" '.execution.tx_hash == null and ([.execution_items[].tx_hash] | all(. == null))'

safe_payment_id="$(echo "$confirm_safe" | jq -r '.payment_order_id')"
safe_item_id="$(echo "$confirm_safe" | jq -r '.execution_items[0].execution_item_id')"
safe_item_hex="${safe_item_id//-/}"
safe_fake_tx="0x${safe_item_hex}${safe_item_hex}"

attach_proposal="$(curl -s -X POST "$API_BASE/api/execution-items/$safe_item_id/attach-safe-proposal" \
  -H "Content-Type: application/json" \
  -d '{"proposal_id":"SAFE-PROP-VERIFY-001","proposal_url":"https://app.safe.global/transactions/queue?safe=hashkey:0x1234","safe_address":"0x1234000000000000000000000000000000000000"}')"
assert_json "safe attach proposal ok" "$attach_proposal" '.status=="ok" and .next_action=="approve_in_safe"'

attach_safe_tx="$(curl -s -X POST "$API_BASE/api/execution-items/$safe_item_id/attach-tx" \
  -H "Content-Type: application/json" \
  -d "{\"tx_hash\":\"$safe_fake_tx\"}")"
assert_json "safe attach-tx ok" "$attach_safe_tx" '.status=="ok"'
assert_json "safe attach submitted" "$attach_safe_tx" '.item_status=="submitted" and .onchain_status=="submitted_onchain"'

sync_safe="$(curl -s -X POST "$API_BASE/api/execution-items/$safe_item_id/sync-receipt" \
  -H "Content-Type: application/json" \
  -d '{}')"
assert_json "safe sync returns deterministic state" "$sync_safe" '.status=="pending" or .status=="ok" or .status=="no_change"'

echo
echo "== D) payment detail visibility =="
uw_detail="$(curl -s "$API_BASE/api/payments/$uw_payment_id")"
assert_json "detail user_wallet mode visible" "$uw_detail" '.execution_batch.execution_mode=="user_wallet"'
assert_json "detail user_wallet tx attached visible" "$uw_detail" '[.execution_items[] | select(.execution_mode=="user_wallet") | .tx_attachment != null] | any'
assert_json "detail user_wallet submitted visible" "$uw_detail" '[.execution_items[] | select(.execution_mode=="user_wallet") | .onchain_status=="submitted_onchain"] | any'

safe_detail="$(curl -s "$API_BASE/api/payments/$safe_payment_id")"
assert_json "detail safe mode visible" "$safe_detail" '.execution_batch.execution_mode=="safe"'
assert_json "detail safe proposal visible" "$safe_detail" '[.execution_items[] | select(.execution_mode=="safe") | .safe_proposal_request != null] | any'
assert_json "detail safe tx attached visible" "$safe_detail" '[.execution_items[] | select(.execution_mode=="safe") | .tx_attachment != null] | any'

echo
echo "== Timeline visibility (safe) =="
safe_timeline="$(curl -s "$API_BASE/api/commands/$cmd_safe_id/timeline")"
assert_json "timeline has safe_proposal_prepared" "$safe_timeline" '[.items[].action] | index("safe_proposal_prepared") != null'
assert_json "timeline has safe_proposal_attached" "$safe_timeline" '[.items[].action] | index("safe_proposal_attached") != null'
assert_json "timeline has safe_tx_attached" "$safe_timeline" '[.items[].action] | index("safe_tx_attached") != null'

echo
echo "Execution-mode verification PASSED."
echo "user_wallet: command_id=$cmd_uw_id payment_id=$uw_payment_id item_id=$uw_item_id"
echo "safe: command_id=$cmd_safe_id payment_id=$safe_payment_id item_id=$safe_item_id"
