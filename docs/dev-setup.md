# Development Setup

## Purpose
This document explains how to run PayFi Box locally through step 11, including PostgreSQL startup, schema migration, demo seeding, onchain config, MVP-level durable confirmation hardening, contract-side idempotency checks, merchant fiat-in settlement flow, Stripe/KYC setup, reconciliation, and common troubleshooting.

## Language Structure
This file contains a complete Chinese section followed by a complete English section. Both sections are complete and independently usable.

## 中文版

### 前置条件
- Node.js 24 或兼容版本
- npm 11 或兼容版本
- Python 3.13 或兼容版本
- 本机 PostgreSQL 16（推荐 Homebrew 安装）
- `make` 命令可用
- Docker + Docker Compose（可选回退）

### 本地安装步骤
```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env
make install
```

### 启动数据库
```bash
make db
```

停止数据库：

```bash
make db-down
```

本地数据库路径说明：
- 默认开发路径是本机 PostgreSQL，不依赖 Docker。
- `make db` 会尝试启动 `postgresql@16` 并创建 `payfi_box`（若不存在）。
- 你也可以手动执行：

```bash
brew services start postgresql@16
createdb payfi_box
```

默认 PostgreSQL 连接参数：

```env
POSTGRES_DB=payfi_box
POSTGRES_PORT=5432
DATABASE_URL=postgresql://localhost:5432/payfi_box
```

Docker 回退（可选，非默认）：

```bash
make db-docker
make db-docker-down
```

### Schema 迁移（Step 2）
执行 Alembic 迁移：

```bash
make migrate
```

该命令会创建 Step 2 的核心表结构（11 个实体）。

### Seed 演示数据
注入 demo 数据：

```bash
make seed
```

说明：seed 使用确定性主键与时间戳，便于重复演示与截图对齐。

重置并重灌 demo 数据：

```bash
make reset-db
```

### API 启动验证
启动 API：

```bash
make api
```

默认地址：

```text
http://localhost:8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

预期返回：

```json
{"status":"ok","service":"payfi-box-api"}
```

### Step 8C（HashKey Testnet 链上执行）
默认后端仍使用 mock 执行；链上执行需显式开启：

说明：`apps/api/.env.example` 默认值是 `PAYMENT_EXECUTION_BACKEND=mock`，便于本地无私钥开发。

```env
PAYMENT_EXECUTION_BACKEND=hashkey_testnet
HASHKEY_RPC_URL=https://testnet.hsk.xyz
HASHKEY_CHAIN_ID=133
HASHKEY_EXPLORER_BASE=https://testnet-explorer.hsk.xyz
HASHKEY_OPERATOR_PRIVATE_KEY=0xYOUR_TESTNET_OPERATOR_PRIVATE_KEY
HASHKEY_PAYMENT_EXECUTOR_ADDRESS=0xYOUR_DEPLOYED_PAYMENT_EXECUTOR
HASHKEY_PAYMENT_TOKEN_ADDRESS=0xYOUR_TESTNET_TOKEN
HASHKEY_SAFE_ADDRESS=0xYOUR_SAFE_ADDRESS_OPTIONAL
```

建议按以下顺序配置：
1. 复制配置文件：`cp apps/api/.env.example apps/api/.env`
2. 填写 `HASHKEY_OPERATOR_PRIVATE_KEY`（测试网钱包私钥，勿提交）
3. 准备测试网 HSK（用于 gas）
4. 部署 `PaymentExecutor` 后回填 `HASHKEY_PAYMENT_EXECUTOR_ADDRESS`

合约编译与部署：

```bash
make install-contracts
make contract-compile
make contract-deploy-hashkey
```

执行模型说明：
- 单 operator 钱包模型：后端使用一个操作钱包私钥同步提交交易。
- 代币前置条件：operator 钱包需要先对 `PaymentExecutor` 合约执行 ERC-20 `approve`。
- 拆单优先：`split_count > 1` 时按 split 逐笔上链。
- 回退策略：无拆单时按订单单笔上链（single tx per order）。
- 同步确认：`/api/confirm` 在进程内等待 receipt 后返回 `tx_hash`/`explorer_url`。
- 风险拦截：`risk=block` 时不发送链上交易。

注意：
- 仅用于 HashKey Chain Testnet 演示，不是生产级托管或清结算方案。

### Step 8D（执行耐久化与恢复）
Step 8D 在 Step 8C 基础上新增：
- 幂等确认加固（MVP）：`/api/confirm` 支持 `idempotency_key`
- 执行意图持久化：`payment_execution_batches` + `payment_execution_items`
- 部分失败语义：`partially_executed` / `partially_confirmed`
- 恢复对账入口：`POST /api/executions/reconcile`

确认请求建议：

```json
{
  "command_id": "ac1e5fb1-7767-450b-bb2b-e06d39d7fdbc",
  "confirmed": true,
  "execution_mode": "operator",
  "idempotency_key": "confirm:ac1e5fb1-7767-450b-bb2b-e06d39d7fdbc:operator"
}
```

手动触发恢复对账：

```bash
curl -X POST http://localhost:8000/api/executions/reconcile \
  -H "Content-Type: application/json" \
  -d '{"limit":20,"resume_planned":false}'
```

### Step 8E（合约执行项级防重）
Step 8E 在 Step 8D 基础上新增：
- 合约侧执行项防重：`executedItems[executionItemId]`
- 后端提交前预检 `executedItems`，并将 duplicate revert 映射为安全幂等结果
- 审计时间线新增 `onchain_duplicate_rejected` 事件

重部署要求（重要）：
1. 重新部署 `PaymentExecutor`（旧地址不具备 Step 8E 语义保证）
2. 回填 `HASHKEY_PAYMENT_EXECUTOR_ADDRESS`
3. 重启 API

本地合约防重验证：

```bash
make contract-test-idempotency
```

### Step 9（商户法币入金 -> 稳定币出金）
Step 9 在 Step 8E 基础上新增：
- 商户报价模型：`SettlementQuote`
- 法币支付意图模型：`FiatPaymentIntent`
- 法币到账确认模型：`FiatCollection`
- 出金关联模型：`StablecoinPayoutLink`

关键说明：
- 法币到账在 MVP 中由运营手工/模拟确认，不接入真实银行网关。
- 法币到账后复用现有稳定币出金执行链路（`/api/confirm` + execution batch/item + HashKey Testnet）。

可选环境参数（`apps/api/.env`）：

```env
SETTLEMENT_QUOTE_TTL_SECONDS=900
SETTLEMENT_SPREAD_BPS=45
SETTLEMENT_PLATFORM_FEE_BPS=30
SETTLEMENT_MIN_PLATFORM_FEE=0.10
SETTLEMENT_NETWORK_FEE=0.35
```

示例联调：

```bash
# 1) 创建法币到稳定币报价
curl -X POST http://localhost:8000/api/merchant/quote \
  -H "Content-Type: application/json" \
  -d '{"merchant_id":"deaa3ed3-c910-53d0-8796-755d9c82add6","beneficiary_id":"c1779963-6db1-5987-99f6-379acd2bb24b","source_currency":"USD","source_amount":1000,"target_currency":"USDT","target_network":"hashkey_testnet"}'

# 2) 创建法币支付意图
curl -X POST http://localhost:8000/api/merchant/fiat-payment \
  -H "Content-Type: application/json" \
  -d '{"quote_id":"<quote_id>","merchant_id":"deaa3ed3-c910-53d0-8796-755d9c82add6","reference":"MERCH-SETTLE-001"}'

# 3) 手工确认法币到账并触发稳定币出金（仅 manual 通道或 demo/admin override）
curl -X POST http://localhost:8000/api/merchant/fiat-payment/<fiat_payment_intent_id>/mark-received \
  -H "Content-Type: application/json" \
  -d '{"collection_method":"manual_bank_transfer","received_amount":1000,"currency":"USD","confirmed_by_user_id":"deaa3ed3-c910-53d0-8796-755d9c82add6","execution_mode":"operator"}'

# 4) 查询完整生命周期明细
curl http://localhost:8000/api/merchant/fiat-payment/<fiat_payment_intent_id>
```

### Step 10（Execution Mode 扩展：operator / user_wallet / safe）
Step 10 在现有执行层基础上新增：
- `user_wallet`：`/api/confirm` 返回 unsigned tx，后端不签名不发链。
- `safe`：`/api/confirm` 返回 Safe proposal payload（MVP scaffold，未接 Safe SDK 自动执行）。
- execution item 附加/同步接口：
  - `POST /api/execution-items/{id}/attach-tx`
  - `POST /api/execution-items/{id}/attach-safe-proposal`
  - `POST /api/execution-items/{id}/sync-receipt`

关键说明：
- `operator` 仍是默认主路径，保持现有 HashKey Testnet 真实上链能力。
- `user_wallet/safe` 复用统一 `payment_order + execution_batch + execution_item` 数据模型，不引入平行引擎。
- 钱包或 Safe 外部提交交易后，可通过 `attach-tx` + `sync-receipt` 回写执行状态。
- 支付详情 execution item 会按模式/状态返回 `pending_action`、`unsigned_tx_request`、`safe_proposal_request`、`safe_proposal_attachment`、`tx_attachment`。`attach-tx` 后 `pending_action` 应转为回执同步语义（例如 `sync_receipt`），不再停留在签名/提案阶段。

### Step 11（Stripe 法币通道 + KYC 门控）
Step 11 在 Step 10 基础上新增：
- KYC API：
  - `POST /api/kyc/start`
  - `GET /api/kyc/{id}`
- Stripe 通道 API：
  - `POST /api/merchant/fiat-payment/{id}/create-stripe-session`
  - `POST /api/merchant/fiat-payment/{id}/start-stripe-payment`（同义别名）
  - `POST /api/webhooks/stripe`

新增环境变量（`apps/api/.env`）：

```env
SETTLEMENT_FIAT_CHANNEL=stripe
SETTLEMENT_REQUIRE_KYC=true
SETTLEMENT_KYC_PROVIDER=stripe_identity
SETTLEMENT_ALLOW_MANUAL_MARK_RECEIVED_OVERRIDE=false
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_CHECKOUT_SUCCESS_URL=http://localhost:3000/merchant?stripe=success
STRIPE_CHECKOUT_CANCEL_URL=http://localhost:3000/merchant?stripe=cancel
STRIPE_IDENTITY_RETURN_URL=http://localhost:3000/merchant?kyc=done
```

关键语义（必须保持）：
- 仅在 Stripe `payment_intent.succeeded` 且 KYC 已验证时触发稳定币出金桥接。
- `checkout.session.completed` 仅表示结账流程完成，不直接等价为法币最终确认到账。
- 若 KYC 未完成，即使收到 Stripe success 事件也必须拦截（`blocked_kyc_required`），不创建链上出金。
- Stripe 通道默认禁止前端手工 `mark-received`；到账确认必须来自 provider webhook。
- 仅当 `SETTLEMENT_ALLOW_MANUAL_MARK_RECEIVED_OVERRIDE=true` 且请求显式标记 demo/admin override 时，允许手工兜底。
- webhook 必须通过签名校验（`STRIPE_WEBHOOK_SECRET` + `Stripe-Signature`）。
- 重复 webhook 按 `event_id` 幂等忽略，不会重复触发 payout bridge。

### Step 12（平台余额 + MCP）
Step 12 在 Step 11 基础上新增：
- 平台余额模型：
  - `platform_balance_accounts`
  - `platform_balance_ledger_entries`
  - `platform_balance_locks`
  - `fiat_deposit_orders`
- 平台余额 API：
  - `POST /api/balance/deposits`
  - `POST /api/balance/deposits/{id}/start-stripe-payment`
  - `POST /api/balance/deposits/{id}/sync-stripe-payment`
  - `GET /api/balance/deposits/{id}`
  - `GET /api/balance/accounts/{user_id}`
  - `GET /api/balance/accounts/{user_id}/ledger`
  - `POST /api/balance/payments/preview`
  - `POST /api/balance/payments/confirm`
- MCP endpoint：
  - `http://127.0.0.1:8000/mcp/`

关键语义：
- 平台余额支付并不创建第二套执行引擎，只是新增资金来源层。
- MCP 接入前必须完成 KYC；未 KYC 时，充值与支付工具应返回阻断语义。
- 充值 webhook 重复事件会被幂等忽略，并在审计与 metadata 中留下记录，便于演示说明“为什么只入账一次”。

推荐验证：

```bash
./.venv/bin/python scripts/verify_balance_deposit.py
```

该脚本会覆盖：
- 未 KYC -> 创建充值单后尝试 Stripe checkout，预期 `blocked_kyc_required`
- 已 KYC -> Stripe checkout URL 创建成功
- `payment_intent.succeeded` -> 余额只入账一次
- 同一 event 重投 -> `duplicate_ignored`，无第二次入账

### 启动 Web
```bash
make web
```

默认地址：

```text
http://localhost:3000
```

### 一键本地运行（含数据库）
```bash
make dev
```

### 常用命令速查
- `make install`
- `make db`
- `make db-down`
- `make db-docker`
- `make db-docker-down`
- `make migrate`
- `make seed`
- `make reset-db`
- `make api`
- `make web`
- `make dev`
- `make verify-api`
- `make verify-seed`
- `make verify-step7b`
- `make verify-step7b-reset`
- `make contract-compile`
- `make contract-deploy-hashkey`
- `make contract-test-idempotency`

### Step 7B 一键回归验证
推荐在演示前与重构后执行：

```bash
make verify-step7b
```

脚本默认行为：
- 不自动执行 reset/seed（仅验证当前本地数据）
- 先检查 `GET /health`；若 API 不可达立即失败并停止后续检查
- 数据前提检查（precondition）：
  - `beneficiaries >= 5`
  - `payments >= 10`
  - `commands >= 5`
  - `executed_count >= 1`
  - `split_payment_count >= 1`（`split_payment_count` 表示 `split_count > 1` 的 payment order 数量，而不是 `payment_splits` 表中的记录条数）
  - `medium_risk_beneficiary_count`（快照展示）
  - `high_risk_beneficiary_count`（快照展示）
  - `risky_beneficiary_count >= 1`（`medium/high`）
  - `create_payment_commands >= 1`
- 再执行 Step 7B 核心校验：
  - `GET /health`
  - `GET /api/commands/{id}/timeline`
  - `POST /api/commands/{id}/replay`（无副作用）
  - `POST /api/payments/{id}/retry-mock`（安全重试语义）
  - `GET /api/reports/summary` 丰富筛选与分组
  - blocked 流程完整性（命令风控 block + confirm blocked）

输出与退出码：
- 每个检查项输出 `PASS/FAIL`
- 失败时带 `reason` 与 `hint`
- `semantic coverage` 会把语义覆盖子项逐条展示，便于快速定位（executed/split/risky/create_payment）
- `semantic coverage` 现在会先输出紧凑汇总行（例如 `4/4 PASS` 或 `3/4 PASS (1 FAIL)`），方便快速诊断
- 全部通过返回 0；任一失败返回非 0

基线模式（显式 reset + seed）：

```bash
make verify-step7b-reset
```

该模式会先执行：`make db` + `make migrate` + `make reset-db`，再执行完整校验。

可选直跑 Python：

```bash
python scripts/verify_step7b.py
```

显式 reset：

```bash
python scripts/verify_step7b.py --reset-db
```

自定义 precondition 阈值：

```bash
python scripts/verify_step7b.py --min-beneficiaries 5 --min-payments 10 --min-commands 5
```

仅健康检查（不 reset）：

```bash
python scripts/verify_step7b.py --health-only
```

### 常见故障排查
- 数据库连接失败：
  - 确认本机 PostgreSQL 服务已启动（`brew services list | grep postgresql`）
  - 确认 `make db` 已执行成功
  - 确认本地 `5432` 未被其他服务占用
  - 若本机服务不可用，可临时切换 `make db-docker`
- 迁移失败：
  - 确认 `apps/api/.env` 中 `DATABASE_URL` 正确
  - 确认 `.venv` 已存在且已安装依赖（`make install`）
- seed 失败：
  - 先执行 `make migrate`
  - 再执行 `make seed`
  - 如果脏数据导致冲突，执行 `make reset-db`
- API 启动失败：
  - 检查 `.venv/bin/python` 是否存在
  - 重新执行 `make install-api`

### 面向 Codex 的后续说明
- Step 2 已提供可扩展的数据底座
- Step 3 建议优先实现：
  - 命令解析链路（`CommandExecution` -> `PaymentOrder`）
  - 支付单查询/过滤 API
  - 风险复核视图与报表任务接口

### 相关文档
- [项目总览](../README.md)
- [产品规格](product-spec.md)
- [架构说明](architecture.md)
- [演示与种子计划](demo-plan.md)

## English

### Prerequisites
- Node.js 24 or compatible
- npm 11 or compatible
- Python 3.13 or compatible
- Local PostgreSQL 16 (Homebrew recommended)
- `make` available
- Docker + Docker Compose (optional fallback)

### Local Install Steps
```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env
make install
```

### Start Database
```bash
make db
```

Stop database:

```bash
make db-down
```

Local DB path notes:
- The default local development path is a locally installed PostgreSQL service, not Docker.
- `make db` attempts to start `postgresql@16` and creates `payfi_box` if it does not exist.
- You can also run it manually:

```bash
brew services start postgresql@16
createdb payfi_box
```

Default PostgreSQL settings:

```env
POSTGRES_DB=payfi_box
POSTGRES_PORT=5432
DATABASE_URL=postgresql://localhost:5432/payfi_box
```

Docker fallback (optional, non-default):

```bash
make db-docker
make db-docker-down
```

### Schema Migration (Step 2)
Run Alembic migration:

```bash
make migrate
```

This creates the step 2 core schema (11 entities).

### Seed Demo Data
Load demo data:

```bash
make seed
```

Note: seed uses deterministic IDs and timestamps for repeatable demos and screenshot consistency.

Reset and reseed demo data:

```bash
make reset-db
```

### API Start Verification
Start API:

```bash
make api
```

Default URL:

```text
http://localhost:8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","service":"payfi-box-api"}
```

### Step 8C (HashKey Testnet Onchain Execution)
The default backend remains mock execution. Onchain execution is opt-in:

Note: `apps/api/.env.example` defaults to `PAYMENT_EXECUTION_BACKEND=mock` for local development without private keys.

```env
PAYMENT_EXECUTION_BACKEND=hashkey_testnet
HASHKEY_RPC_URL=https://testnet.hsk.xyz
HASHKEY_CHAIN_ID=133
HASHKEY_EXPLORER_BASE=https://testnet-explorer.hsk.xyz
HASHKEY_OPERATOR_PRIVATE_KEY=0xYOUR_TESTNET_OPERATOR_PRIVATE_KEY
HASHKEY_PAYMENT_EXECUTOR_ADDRESS=0xYOUR_DEPLOYED_PAYMENT_EXECUTOR
HASHKEY_PAYMENT_TOKEN_ADDRESS=0xYOUR_TESTNET_TOKEN
HASHKEY_SAFE_ADDRESS=0xYOUR_SAFE_ADDRESS_OPTIONAL
```

Recommended setup order:
1. Copy config file: `cp apps/api/.env.example apps/api/.env`
2. Fill `HASHKEY_OPERATOR_PRIVATE_KEY` (testnet wallet key; do not commit)
3. Get testnet HSK for gas
4. Deploy `PaymentExecutor`, then fill `HASHKEY_PAYMENT_EXECUTOR_ADDRESS`

Contract compile/deploy:

```bash
make install-contracts
make contract-compile
make contract-deploy-hashkey
```

Execution model notes:
- Single operator wallet model: backend submits transactions with one operator private key.
- Token precondition: the operator wallet must call ERC-20 `approve` for `PaymentExecutor` first.
- Split-first model: one tx per split when `split_count > 1`.
- Fallback model: one tx per order when no split rows exist.
- Synchronous confirmation: `/api/confirm` waits for receipt in-process and returns `tx_hash`/`explorer_url`.
- Risk boundary: no onchain tx is submitted when `risk=block`.

Note:
- This is HashKey Chain Testnet demo execution only, not production custody or settlement.

### Step 8D (Durable Execution and Recovery)
Step 8D adds:
- idempotent confirmation hardening (MVP) via `idempotency_key` on `/api/confirm`
- persisted execution intent entities: `payment_execution_batches` + `payment_execution_items`
- partial-failure semantics: `partially_executed` / `partially_confirmed`
- reconciliation entrypoint: `POST /api/executions/reconcile`

Recommended confirm payload:

```json
{
  "command_id": "ac1e5fb1-7767-450b-bb2b-e06d39d7fdbc",
  "confirmed": true,
  "execution_mode": "operator",
  "idempotency_key": "confirm:ac1e5fb1-7767-450b-bb2b-e06d39d7fdbc:operator"
}
```

Manual reconciliation call:

```bash
curl -X POST http://localhost:8000/api/executions/reconcile \
  -H "Content-Type: application/json" \
  -d '{"limit":20,"resume_planned":false}'
```

### Step 8E (Contract Item-Level Idempotency)
Step 8E adds on top of step 8D:
- contract-side item-level duplicate protection via `executedItems[executionItemId]`
- backend pre-submit `executedItems` preflight + safe duplicate-revert mapping
- timeline/audit event `onchain_duplicate_rejected` for observability

Redeploy requirement (important):
1. Deploy a new `PaymentExecutor` contract (older addresses do not provide step-8E guarantees)
2. Update `HASHKEY_PAYMENT_EXECUTOR_ADDRESS`
3. Restart API

Local contract duplicate-protection verification:

```bash
make contract-test-idempotency
```

### Step 9 (Merchant Fiat-In -> Stablecoin-Out)
Step 9 adds on top of step 8E:
- merchant quote model: `SettlementQuote`
- fiat payment intent model: `FiatPaymentIntent`
- fiat collection confirmation model: `FiatCollection`
- payout linkage model: `StablecoinPayoutLink`

Important notes:
- Fiat receipt confirmation is manual/simulated in MVP mode (no live banking gateway integration yet).
- After fiat is marked received, payout reuses the existing stablecoin execution flow (`/api/confirm` + execution batch/item + HashKey testnet).

Optional settlement pricing config (`apps/api/.env`):

```env
SETTLEMENT_QUOTE_TTL_SECONDS=900
SETTLEMENT_SPREAD_BPS=45
SETTLEMENT_PLATFORM_FEE_BPS=30
SETTLEMENT_MIN_PLATFORM_FEE=0.10
SETTLEMENT_NETWORK_FEE=0.35
```

Example E2E calls:

```bash
# 1) Create fiat-to-stablecoin quote
curl -X POST http://localhost:8000/api/merchant/quote \
  -H "Content-Type: application/json" \
  -d '{"merchant_id":"deaa3ed3-c910-53d0-8796-755d9c82add6","beneficiary_id":"c1779963-6db1-5987-99f6-379acd2bb24b","source_currency":"USD","source_amount":1000,"target_currency":"USDT","target_network":"hashkey_testnet"}'

# 2) Create fiat payment intent from quote
curl -X POST http://localhost:8000/api/merchant/fiat-payment \
  -H "Content-Type: application/json" \
  -d '{"quote_id":"<quote_id>","merchant_id":"deaa3ed3-c910-53d0-8796-755d9c82add6","reference":"MERCH-SETTLE-001"}'

# 3) Mark fiat received and trigger payout (manual channel or demo/admin override only)
curl -X POST http://localhost:8000/api/merchant/fiat-payment/<fiat_payment_intent_id>/mark-received \
  -H "Content-Type: application/json" \
  -d '{"collection_method":"manual_bank_transfer","received_amount":1000,"currency":"USD","confirmed_by_user_id":"deaa3ed3-c910-53d0-8796-755d9c82add6","execution_mode":"operator"}'

# 4) Query full lifecycle detail
curl http://localhost:8000/api/merchant/fiat-payment/<fiat_payment_intent_id>
```

### Step 10 (Execution Mode Expansion: operator / user_wallet / safe)
Step 10 adds on top of the existing execution layer:
- `user_wallet`: `/api/confirm` returns unsigned tx payloads; backend does not sign or submit.
- `safe`: `/api/confirm` returns Safe proposal payloads (MVP scaffold, no Safe SDK auto-execution yet).
- execution-item attachment/sync endpoints:
  - `POST /api/execution-items/{id}/attach-tx`
  - `POST /api/execution-items/{id}/attach-safe-proposal`
  - `POST /api/execution-items/{id}/sync-receipt`

Key notes:
- `operator` remains the default and keeps the current HashKey testnet onchain path.
- `user_wallet/safe` reuse the same `payment_order + execution_batch + execution_item` model (no parallel payout engine).
- After external wallet/Safe submission, use `attach-tx` + `sync-receipt` to reconcile execution state.
- Payment-detail execution-item fields now include `pending_action`, `unsigned_tx_request`, `safe_proposal_request`, `safe_proposal_attachment`, and `tx_attachment` (mode/state-dependent). After `attach-tx`, `pending_action` should move to receipt-sync semantics (for example `sync_receipt`) instead of still showing signature/proposal steps.

### Step 11 (Stripe Fiat Channel + KYC Gating)
Step 11 adds on top of step 10:
- KYC APIs:
  - `POST /api/kyc/start`
  - `GET /api/kyc/{id}`
- Stripe channel APIs:
  - `POST /api/merchant/fiat-payment/{id}/create-stripe-session`
  - `POST /api/merchant/fiat-payment/{id}/start-stripe-payment` (alias)
  - `POST /api/webhooks/stripe`

Additional env vars (`apps/api/.env`):

```env
SETTLEMENT_FIAT_CHANNEL=stripe
SETTLEMENT_REQUIRE_KYC=true
SETTLEMENT_KYC_PROVIDER=stripe_identity
SETTLEMENT_ALLOW_MANUAL_MARK_RECEIVED_OVERRIDE=false
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_CHECKOUT_SUCCESS_URL=http://localhost:3000/merchant?stripe=success
STRIPE_CHECKOUT_CANCEL_URL=http://localhost:3000/merchant?stripe=cancel
STRIPE_IDENTITY_RETURN_URL=http://localhost:3000/merchant?kyc=done
```

Required semantics:
- Trigger payout bridge only after Stripe `payment_intent.succeeded` with verified KYC.
- Treat `checkout.session.completed` as channel progress only (not final fiat confirmation).
- If KYC is not verified, Stripe success must be blocked (`blocked_kyc_required`) and no onchain payout can be created.
- Stripe channel must not accept normal frontend manual `mark-received`; fiat confirmation comes from provider webhook.
- Manual fallback is demo/admin-only and requires `SETTLEMENT_ALLOW_MANUAL_MARK_RECEIVED_OVERRIDE=true` plus explicit override in request.
- Webhook signature verification is mandatory (`STRIPE_WEBHOOK_SECRET` + `Stripe-Signature`).
- Duplicate webhook deliveries are idempotently ignored by `event_id`, so payout bridge is not triggered twice.

### Step 12 (Platform Balance + MCP)
Step 12 adds on top of step 11:
- platform balance entities:
  - `platform_balance_accounts`
  - `platform_balance_ledger_entries`
  - `platform_balance_locks`
  - `fiat_deposit_orders`
- platform balance APIs:
  - `POST /api/balance/deposits`
  - `POST /api/balance/deposits/{id}/start-stripe-payment`
  - `POST /api/balance/deposits/{id}/sync-stripe-payment`
  - `GET /api/balance/deposits/{id}`
  - `GET /api/balance/accounts/{user_id}`
  - `GET /api/balance/accounts/{user_id}/ledger`
  - `POST /api/balance/payments/preview`
  - `POST /api/balance/payments/confirm`
- MCP endpoint:
  - `http://127.0.0.1:8000/mcp/`

Required semantics:
- platform balance settlement does not introduce a second execution engine; it only adds a funding-source layer in front of the existing execution backbone
- KYC must be completed before MCP deposit/payment tools are available
- duplicate deposit webhook deliveries are ignored idempotently and also recorded in audit/metadata for demo explainability

Recommended verification:

```bash
./.venv/bin/python scripts/verify_balance_deposit.py
```

The script covers:
- unverified user -> blocked at Stripe checkout start
- verified user -> Stripe checkout URL created
- `payment_intent.succeeded` -> balance credited exactly once
- duplicate event replay -> `duplicate_ignored`, no second balance credit

### Start Web
```bash
make web
```

Default URL:

```text
http://localhost:3000
```

### Run All Local Services
```bash
make dev
```

### Command Quick Reference
- `make install`
- `make db`
- `make db-down`
- `make db-docker`
- `make db-docker-down`
- `make migrate`
- `make seed`
- `make reset-db`
- `make api`
- `make web`
- `make dev`
- `make verify-api`
- `make verify-seed`
- `make verify-step7b`
- `make verify-step7b-reset`
- `make contract-compile`
- `make contract-deploy-hashkey`
- `make contract-test-idempotency`

### Step 7B One-Command Regression Verification
Recommended before demos and after backend refactors:

```bash
make verify-step7b
```

Default script behavior:
- no automatic reset/seed; verifies current local dataset
- checks `GET /health` first; if API is unreachable it fails immediately and stops
- data precondition checks:
  - `beneficiaries >= 5`
  - `payments >= 10`
  - `commands >= 5`
  - `executed_count >= 1`
  - `split_payment_count >= 1` (`split_payment_count` means the number of payment orders whose `split_count` is greater than 1, not the number of rows in `payment_splits`)
  - `medium_risk_beneficiary_count` (reported in snapshot)
  - `high_risk_beneficiary_count` (reported in snapshot)
  - `risky_beneficiary_count >= 1` (`medium/high`)
  - `create_payment_commands >= 1`
- then runs Step 7B checks:
  - `GET /health`
  - `GET /api/commands/{id}/timeline`
  - `POST /api/commands/{id}/replay` (no side effects)
  - `POST /api/payments/{id}/retry-mock` (safe retry behavior)
  - richer `GET /api/reports/summary` filters and grouped sections
  - blocked-flow integrity (`/api/command` risk block + `/api/confirm` blocked)

Output and exit code:
- each check prints `PASS/FAIL`
- failures include `reason` and `hint`
- `semantic coverage` reports each semantic coverage item individually for easier diagnosis (executed/split/risky/create_payment)
- `semantic coverage` now starts with a compact summary line (for example `4/4 PASS` or `3/4 PASS (1 FAIL)`) for faster diagnosis
- exits `0` only when all checks pass; exits non-zero otherwise

Baseline mode (explicit reset + seed):

```bash
make verify-step7b-reset
```

This mode runs `make db` + `make migrate` + `make reset-db` before full verification.

Optional direct Python mode:

```bash
python scripts/verify_step7b.py
```

Explicit reset mode:

```bash
python scripts/verify_step7b.py --reset-db
```

Custom precondition thresholds:

```bash
python scripts/verify_step7b.py --min-beneficiaries 5 --min-payments 10 --min-commands 5
```

Health-only mode (no reset):

```bash
python scripts/verify_step7b.py --health-only
```

### Troubleshooting
- DB connection errors:
  - ensure local PostgreSQL service is running (`brew services list | grep postgresql`)
  - ensure `make db` completed
  - ensure port `5432` is not occupied
  - if local service is unavailable, temporarily use `make db-docker`
- Migration errors:
  - verify `DATABASE_URL` in `apps/api/.env`
  - verify `.venv` and dependencies via `make install`
- Seed failures:
  - run `make migrate` first
  - then run `make seed`
  - if stale data conflicts, run `make reset-db`
- API startup issues:
  - verify `.venv/bin/python` exists
  - re-run `make install-api`

### Notes for Codex-Driven Next Step
- Step 2 now provides a usable data foundation
- Step 3 should prioritize:
  - command parsing flow (`CommandExecution` -> `PaymentOrder`)
  - payment order query/filter APIs
  - risk review and report job endpoints

### Related Docs
- [Project Overview](../README.md)
- [Product Spec](product-spec.md)
- [Architecture](architecture.md)
- [Demo Seed Plan](demo-plan.md)
