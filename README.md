# PayFi Box

PayFi Box is a stablecoin settlement infrastructure for web and AI-native clients. It combines natural-language settlement initiation, fiat collection, KYC gating, platform balance management, onchain stablecoin execution, and auditable settlement detail in one product surface.

PayFi Box 面向真实资金流的结算场景：用户可以通过网页或 MCP 发起结算，平台完成报价、风控、法币入金、平台余额管理、链上稳定币执行与结算核查。

## What It Does

- Natural-language settlement initiation for payment requests and payout instructions
- Merchant fiat-in -> stablecoin-out settlement with KYC and Stripe collection
- Platform balance accounts that let users deposit fiat, convert to stablecoin balance, and settle from balance
- MCP access so external AI clients can query balances, create deposits, preview settlements, and confirm eligible actions
- Truthful settlement detail with execution batches, execution items, timelines, and audit-friendly status semantics

## Current Scope

PayFi Box currently runs with:

- Web frontend: Next.js + TypeScript + Tailwind CSS
- API backend: FastAPI + SQLAlchemy + Alembic
- Onchain execution: HashKey Chain Testnet
- Fiat collection: Stripe Test Mode
- KYC gating for merchant settlement and MCP balance tools

Current scope is intentionally limited to test environments. It is not production custody software, not a mainnet settlement system, and not a full treasury platform.

## Product Surfaces

| Surface | Route | Purpose |
| --- | --- | --- |
| Home | `/` | Product overview and primary entry points |
| Settlement Initiation | `/command-center` | Natural-language settlement initiation with AI guidance |
| Settlement Operations | `/merchant` | Merchant fiat collection and stablecoin payout workflow |
| Platform Balance | `/balance` | Fiat deposit, balance view, balance-funded settlement |
| MCP Access | `/mcp` | Developer-facing MCP connection and tool guidance |
| Settlement Modes | `/modes` | Operator / wallet / Safe submission model explanation |
| Settlement Detail | `/payments/:id` | Execution truth, timeline, and audit summary |

## Core Workflows

### 1. Settlement Initiation

Users submit a natural-language request. The system parses intent, identifies missing fields, evaluates risk, recommends a settlement mode, and produces a settlement preview before confirmation.

### 2. Merchant Fiat Settlement

Merchants create a quote, open a fiat payment intent, complete KYC, collect fiat via Stripe, and trigger stablecoin payout once provider-confirmed funds are available.

### 3. Platform Balance

Verified users can deposit fiat, convert it into platform-held stablecoin balance, and later settle directly from that balance without reopening the fiat collection flow each time.

### 4. MCP Access

External AI clients can connect through MCP after KYC. MCP tools expose capability checks, KYC status, balance queries, deposit actions, and balance-funded settlement preview and confirmation.

### 5. Settlement Detail and Audit

Every flow converges on the same settlement truth layer:

- payment order
- execution batch
- execution items
- timeline
- onchain status
- audit-facing summary

## Architecture

### Key Design Principle

PayFi Box keeps a single execution backbone.

Merchant settlement and platform-balance-funded settlement do not create separate execution engines. Both ultimately feed the same:

- `payment_order`
- `payment_execution_batch`
- `payment_execution_item`

This keeps status semantics, timelines, and audit visibility aligned across all entry points.

### Monorepo Structure

```text
.
├── apps
│   ├── api
│   ├── contracts
│   └── web
├── docs
├── infra
├── packages
│   └── shared
├── scripts
└── Makefile
```

### Main Modules

- `apps/web`
  - Next.js app
  - product surfaces, AI-assisted initiation, balance UI, merchant workflow, MCP docs
- `apps/api`
  - FastAPI services
  - settlement initiation, confirmation, merchant settlement, balance system, MCP endpoint
- `apps/contracts`
  - Solidity executor and HashKey Testnet deployment workflow
- `packages/shared`
  - shared enums and domain types
- `docs`
  - architecture, local setup, and progress notes

## API Overview

### Settlement Initiation

- `POST /api/command`
- `POST /api/confirm`
- `GET /api/commands`
- `GET /api/commands/{id}`
- `GET /api/commands/{id}/timeline`
- `GET /api/payments`
- `GET /api/payments/{id}`

### Merchant Settlement

- `POST /api/merchant/quote`
- `POST /api/merchant/fiat-payment`
- `POST /api/merchant/fiat-payment/{id}/start-stripe-payment`
- `POST /api/merchant/fiat-payment/{id}/sync-stripe-payment`
- `GET /api/merchant/fiat-payment/{id}`

### KYC

- `POST /api/kyc/start`
- `GET /api/kyc/{id}`

### Platform Balance

- `POST /api/balance/deposits`
- `POST /api/balance/deposits/{id}/start-stripe-payment`
- `POST /api/balance/deposits/{id}/sync-stripe-payment`
- `GET /api/balance/deposits/{id}`
- `GET /api/balance/accounts/{user_id}`
- `GET /api/balance/accounts/{user_id}/ledger`
- `POST /api/balance/payments/preview`
- `POST /api/balance/payments/confirm`

### MCP

- Endpoint: `http://127.0.0.1:8000/mcp/`
- Current tools:
  - `mcp_capability_status`
  - `start_user_kyc`
  - `get_kyc_status`
  - `get_balance`
  - `get_balance_ledger`
  - `create_balance_deposit`
  - `start_balance_deposit_checkout`
  - `sync_balance_deposit_status`
  - `get_balance_deposit_detail`
  - `payment_preview_from_balance`
  - `payment_confirm_from_balance`

KYC is enforced before deposit and payment tools are made available through MCP.

## Local Setup

### Prerequisites

- Node.js 24 or compatible
- npm 11 or compatible
- Python 3.13 or compatible
- PostgreSQL 16
- `make`

### Install

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env
make install
```

### Database

```bash
make db
make migrate
make seed
```

### Start Services

```bash
make api-start
make web-start
```

Status helpers:

```bash
make api-status
make web-status
```

Stop helpers:

```bash
make api-stop
make web-stop
```

## Local URLs

- Web: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- API health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- MCP endpoint: [http://127.0.0.1:8000/mcp/](http://127.0.0.1:8000/mcp/)

## Environment Notes

### Stripe

For merchant settlement and platform-balance deposit flows, configure Stripe in `apps/api/.env`.

Key variables include:

```env
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_CHECKOUT_SUCCESS_URL=http://127.0.0.1:3000/merchant?stripe=success
STRIPE_CHECKOUT_CANCEL_URL=http://127.0.0.1:3000/merchant?stripe=cancel
STRIPE_IDENTITY_RETURN_URL=http://127.0.0.1:3000/merchant?kyc=done
```

Balance deposit flows can also provide route-specific success and cancel URLs from the frontend.

### HashKey Testnet

For onchain execution, configure the HashKey testnet settings in `apps/api/.env`.

```env
PAYMENT_EXECUTION_BACKEND=hashkey_testnet
HASHKEY_RPC_URL=https://testnet.hsk.xyz
HASHKEY_CHAIN_ID=133
HASHKEY_EXPLORER_BASE=https://testnet-explorer.hsk.xyz
HASHKEY_OPERATOR_PRIVATE_KEY=0x...
HASHKEY_PAYMENT_EXECUTOR_ADDRESS=0x...
HASHKEY_PAYMENT_TOKEN_ADDRESS=0x...
```

If not configured, the system can remain on safer local execution defaults for non-onchain development paths.

## Verification

### Health Check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"payfi-box-api"}
```

### Balance Deposit Verification

Run the end-to-end verification script:

```bash
env -u DATABASE_URL ./.venv/bin/python scripts/verify_balance_deposit.py
```

It verifies:

- KYC blocking when the user is not verified
- checkout creation for verified users
- provider-confirmed balance credit
- duplicate webhook idempotency

## Recommended First Run

1. Start the API and web app
2. Open `/command-center` to see settlement initiation
3. Open `/merchant` to see fiat collection -> stablecoin payout
4. Open `/balance` to see platform balance and balance-funded settlement
5. Open `/mcp` to review MCP connection and tool access

## Documentation

- [Architecture](docs/architecture.md)
- [Development Setup](docs/dev-setup.md)
- [Progress Notes](docs/progress-2026-04-06.md)

## Current Positioning

PayFi Box is currently best understood as:

- a stablecoin settlement infrastructure
- a web product with AI-assisted settlement initiation
- a platform-balance settlement system
- an MCP-accessible settlement backend for external AI clients

It is not yet:

- a production custody platform
- a mainnet treasury platform
- a fully permissioned enterprise payment stack

## License

This repository is licensed under Apache License 2.0. See [LICENSE](LICENSE).
