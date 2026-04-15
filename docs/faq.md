# PayFi Box FAQ

## What is PayFi Box?

PayFi Box is an enterprise payment orchestration platform that lets businesses continue paying in fiat while the platform handles stablecoin conversion, global settlement, and audit visibility in the background.

## Is PayFi Box a wallet?

No. PayFi Box is not positioned as a user wallet product.

It is an orchestration layer that connects:
- payment initiation
- fiat collection
- settlement progression
- execution visibility
- audit and review surfaces

## Why not ask enterprises to pay in stablecoin directly?

Because most enterprises still operate through familiar fiat-based payment and approval workflows.

PayFi Box keeps that fiat-first operating model on the front end, while using a more programmable settlement rail in the background.

## What does AI actually do here?

AI is used to support payment operations, not to replace deterministic money movement controls.

AI helps:
- draft settlement actions from natural-language intent
- explain blocked or pending flows
- summarize audit activity
- guide next valid actions for operators
- connect external AI clients through MCP

The source of truth for state and execution remains the deterministic system model.

## Can AI move funds directly?

Not by itself.

AI can help propose, explain, and coordinate actions, but money movement still depends on explicit product flows, provider state, ledger state, and execution rules enforced by the system.

## Who is this for?

PayFi Box is best suited for:
- cross-border trade and export-facing businesses
- platform operators and finance teams
- internal review and audit stakeholders
- AI-native enterprise systems that need programmable payment workflows

## How does it integrate with external systems?

PayFi Box supports:
- browser-based operator workflows
- API access for external systems
- MCP access for AI-native clients

This allows the same product to be used by humans and by external software or AI systems.

## Does the frontend handle secrets?

No.

The intended boundary is:
- `.env` stores secrets and local configuration
- the server and environment boundary handle sensitive credentials
- frontend business code calls a centralized API wrapper instead of dealing with provider secrets directly

## What stage is the product in today?

The product currently has a working local demo across:
- access
- settlement initiation
- merchant operations
- balance workflows
- audit review
- developer onboarding

It is currently in product validation, demo refinement, and early commercialization preparation rather than broad production rollout.

## What is the clearest way to understand the product quickly?

Use the 3-minute demo path:

`/access` → `/command-center` → `/merchant` → `/balance` → `/audit` → `/developers`
