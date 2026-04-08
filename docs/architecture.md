# Architecture

## Purpose
This document describes the current step 11 architecture of PayFi Box, including command intake, confirmation, read/query APIs, observability and explainability enhancements, lifecycle timeline/replay/retry capabilities, HashKey testnet execution integration, MVP-level durable execution/idempotency hardening, execution-layer visibility, merchant fiat-in / stablecoin-out settlement flow, Stripe fiat channel integration, and KYC gating.

## Language Structure
This file contains a complete Chinese section followed by a complete English section. Both sections are complete and independently usable.

## 中文版

### 高层系统概览
PayFi Box 当前采用面向黑客松的轻量单仓架构：
- `apps/web`：前端演示层（角色入口、状态面板、后续工作台）
- `apps/api`：后端服务层（FastAPI + 数据模型 + 命令入口 + 确认执行流 + seed 工作流）
- `packages/shared`：共享枚举、状态与 schema 占位
- `infra`：Docker 数据库回退配置（可选）
- `docs`：双语设计与开发文档

### 分层设计

#### Frontend 层
- Next.js App Router
- 当前重点：演示信息与角色入口
- 下一步：连接 `PaymentOrder`、`RiskCheck`、`ReportJob` 的列表与详情视图

#### Backend 层
- FastAPI + Pydantic Settings
- SQLAlchemy 2 负责 ORM 模型
- Alembic 负责 schema 迁移
- Seed 脚本负责演示数据灌入与重置
- Step 3 新增命令入口模块：
  - `POST /api/command`
  - rule-based 分类与字段提取
  - mock risk / quote 预览
  - `command_executions` 持久化
- Step 4 新增确认模块：
  - `POST /api/confirm`
  - confirmable 校验
  - `payment_orders`/`payment_splits` 创建
  - 审计日志与 mock 执行回写
- Step 5 新增查询模块：
  - `GET /api/payments`
  - `GET /api/payments/{id}`
  - `GET /api/audit/{trace_id}`
  - `GET /api/reports/summary`
  - 面向列表页/详情页/时间线/报表看板的前端友好响应
- Step 6 新增可观测与可解释模块：
  - `GET /api/commands`
  - `GET /api/commands/{id}`
  - `GET /api/beneficiaries`
  - `GET /api/beneficiaries/{id}`
  - 风险原因码归一化输出（面向命令、支付详情、报表）
- Step 7B 新增生命周期与可重放/可重试模块：
  - `GET /api/commands/{id}/timeline`
  - `POST /api/commands/{id}/replay`
  - `POST /api/payments/{id}/retry-mock`
  - `GET /api/reports/summary` 增强（`date_from/date_to`、`by_risk_level`、`latest_commands`）
- Step 8C 新增 HashKey Chain Testnet 执行模块：
  - 合约：`apps/contracts/contracts/PaymentExecutor.sol`
  - 部署：Hardhat (`make contract-compile` / `make contract-deploy-hashkey`)
  - 确认执行：`/api/confirm` 在 `PAYMENT_EXECUTION_BACKEND=hashkey_testnet` 时发送真实测试网交易
  - 执行路由：`execution_mode=operator/user_wallet/safe`（默认 `operator`）
  - 执行结果：落库并返回 `tx_hash`、`explorer_url`、`onchain_status`、解码事件摘要（可用时）
- Step 8D 新增耐久执行层（durable execution layer）：
  - 新增 `payment_execution_batches`（执行意图批次）与 `payment_execution_items`（执行项）
  - 将确认流拆分为两阶段：事务内意图登记 + 事务外链上处理
  - 新增 `idempotency_key` 约束（MVP 加固）：同命令/同键重复确认不会重复建单或重复发链
  - 新增部分失败语义：`payment_order.partially_executed` 与 `execution_batch.partially_confirmed`
  - 新增对账入口：`POST /api/executions/reconcile`（恢复 `planned/submitted` 批次）
- Step 8E 新增强化合约防重与后端协同：
  - 合约按执行项防重：`executedItems[executionItemId]`
  - 后端提交前预检 `executedItems`，避免重复发链
  - 合约 duplicate revert 映射为安全幂等结果（非未知崩溃）
  - 新增审计动作：`onchain_duplicate_rejected`
- Step 8F 新增执行层可观测增强：
  - 增强 `GET /api/payments/{id}`：补齐 `execution_batch` 聚合计数与 `execution_items` 逐项观测字段
  - 增加 `timeline_summary`：快速识别 duplicate / partial-failure / reconciliation
  - `POST /api/executions/reconcile` 写入对账审计事件：`execution_batch_reconciled`、`execution_item_reconciled`
  - `GET /api/commands/{id}/timeline` 可直接显示对账与防重事件
- Step 9 新增商户法币入金结算模块：
  - `SettlementQuote` + `FiatPaymentIntent` + `FiatCollection` + `StablecoinPayoutLink`
  - 商户法币侧流程：报价 -> 法币意图 -> 到账确认
  - 到账后桥接现有执行引擎：复用 `/api/confirm` + execution batch/item + 链上执行
  - 新增商户接口：`/api/merchant/quote`、`/api/merchant/fiat-payment`、`/api/merchant/fiat-payment/{id}/mark-received`、`/api/merchant/fiat-payment/{id}`
- Step 10 新增执行模式扩展：
  - `user_wallet`：确认返回可签名交易载荷，后续通过 `attach-tx` + `sync-receipt` 回写执行状态
  - `safe`：确认返回 Safe 提案载荷，后续通过 `attach-safe-proposal` + `attach-tx/sync-receipt` 回写状态
  - 支付详情可见字段：`pending_action`、`unsigned_tx_request`、`safe_proposal_request`、`safe_proposal_attachment`、`tx_attachment`（按模式/状态返回）
  - 三模式统一复用 `payment_order + execution_batch + execution_item`，不引入平行执行引擎
- Step 11 新增 Stripe 法币通道 + KYC 门控：
  - 新增 `kyc_verifications`，用于商户/用户 KYC 状态持久化
  - 新增 `POST /api/kyc/start` 与 `GET /api/kyc/{id}`
  - 新增 `POST /api/merchant/fiat-payment/{id}/create-stripe-session` / `POST /api/merchant/fiat-payment/{id}/start-stripe-payment` 与 `POST /api/webhooks/stripe`
  - Stripe `payment_intent.succeeded` 且 KYC 已验证后才桥接现有稳定币出金引擎
  - `checkout.session.completed` 只表示通道结账完成，不直接当作法币最终确认到账
  - Stripe 通道默认禁止前端手工 `mark-received`，到账确认必须来自 provider webhook
  - 仅在显式 demo/admin override 开关开启时保留手工兜底
  - webhook 强制签名校验，且按 `event_id` 做重复投递幂等忽略
- Step 12 新增平台余额 + MCP 接入层：
  - 新增 `platform_balance_accounts`、`platform_balance_ledger_entries`、`platform_balance_locks`、`fiat_deposit_orders`
  - 新增平台余额 API：充值、Stripe 收款、同步入账、余额查询、流水查询、余额支付预览与确认
  - 余额支付只新增“资金来源层”，底层仍复用 `payment_order + execution_batch + execution_item`
  - 新增 MCP 接入点 `/mcp`
  - MCP 工具先开放余额、充值、结算预览与确认，不重造支付引擎
  - MCP 准入由 KYC 前置控制；未 KYC 时只允许走能力检查与身份核验
  - 充值 webhook 重复事件会显式记录 duplicate 审计和重复事件历史，便于解释幂等行为

#### Shared 层
- 在 `packages/shared/src/domain.ts` 维护统一状态定义
- 包含：
  - `user role`
  - `organization type`
  - `payment order status`
  - `payment split status`
  - `risk level`
  - `risk check result`
  - `risk reason code`
  - `execution mode`
  - `execution route`
  - `command execution status`
  - `session status`
  - `report job status`
- 目标：减少前后端状态字符串漂移

#### Data 层
- PostgreSQL 作为主数据库
- 核心实体（11 个）已在 Step 2 落地
- Step 9 新增商户结算实体（`SettlementQuote/FiatPaymentIntent/FiatCollection/StablecoinPayoutLink`）
- Step 12 新增平台余额实体（`PlatformBalanceAccount/PlatformBalanceLedgerEntry/PlatformBalanceLock/FiatDepositOrder`）
- 当前优先保证可演示与可迭代，不做复杂分库分表或多租户设计

### Step 2 数据模型概览
- `Organization`：机构主体（贸易公司/金融机构）
- `User`：系统使用者，支持挂载组织
- `Beneficiary`：收款对象，含风险等级与黑名单标记
- `ConversationSession`：会话轨迹
- `CommandExecution`：自然语言命令及解析结果
- `PaymentOrder`：支付核心单据（生命周期状态）
- `PaymentSplit`：拆单计划
- `PaymentQuote`：报价与路由预览
- `RiskCheck`：策略检查结果（allow/review/block）
- `AuditLog`：审计日志
- `ReportJob`：报送任务

### 实体关系摘要
- `Organization` 1-N `User`
- `Organization` 1-N `Beneficiary`（可选）
- `User` 1-N `ConversationSession`
- `ConversationSession` 1-N `CommandExecution`
- `CommandExecution` 0..N `PaymentOrder`（通过 `source_command_id`）
- `PaymentOrder` 1-N `PaymentSplit`
- `PaymentOrder` 1-N `PaymentQuote`
- `PaymentOrder` 1-N `RiskCheck`
- `User` 1-N `ReportJob`
- `User` 1-N `AuditLog`（作为 actor）

### 支付生命周期设计
统一状态：
- `draft`
- `quoted`
- `pending_confirmation`
- `approved`
- `executed`
- `failed`
- `cancelled`

此生命周期在后端模型与 shared 类型中保持一致。

### 风险模型设计（MVP）
- 风险等级：`low` / `medium` / `high`
- 检查结论：`allow` / `review` / `block`
- 黑名单受益人可直接触发 `block`

### Agent 层占位（未实现真实智能）
- 当前通过 `POST /api/command` 实现规则解析链路，并写入 `CommandExecution`
- 尚未接入真实 LLM 编排（不调用外部 AI）
- 当前解析层可被后续 LLM 分类器/解析器替换

### Step 3 命令入口概览
命令入口管线：
- 接收自然语言命令（`user_id` + `text`）
- 意图分类（`create_payment` / `query_payments` / `generate_report` / `unknown`）
- 槽位提取（收款方、金额、币种、拆单、reference、时间偏好等）
- 缺失字段检测与追问
- mock 风险评估与 mock 报价
- `command_executions` 落库（`raw_text`、`parsed_intent_json`、`tool_calls_json`、`final_status`、`trace_id`）

支持 intents：
- `create_payment`
- `query_payments`
- `generate_report`
- `unknown`

请求示例：

```json
{
  "user_id": "babd0649-6a5a-5d02-aa46-9070ee5248d4",
  "text": "帮我给 Lucy 转 120 USDC，今晚到账，手续费最低",
  "channel": "web",
  "locale": "zh-CN"
}
```

响应示例：

```json
{
  "status": "ok",
  "intent": "create_payment",
  "confidence": 0.95,
  "missing_fields": [],
  "next_action": "confirm_preview",
  "risk": {
    "decision": "allow",
    "risk_level": "low"
  },
  "quote": {
    "estimated_fee": 0.98,
    "route": "TRON-USDC",
    "eta_text": "before tonight"
  }
}
```

解析器限制（Step 3）：
- 当前为规则引擎（regex + 关键词 + demo 数据匹配），非 LLM。
- 对复杂歧义语句覆盖有限，目标是稳定可演示。
- 已按可替换架构拆分，后续可接入真实 LLM。

### Step 4 确认与模拟执行概览
确认执行管线：
- 输入 `command_id + confirmed` 到 `/api/confirm`
- 校验命令是否可确认（意图、字段完整性、状态）
- `confirmed=false`：仅记录拒绝，不创建支付单
- `confirmed=true` 且风险非 `block`：
  - 创建 `payment_order`
  - 当 `split_count > 1` 时创建 `payment_splits`
  - 写入审计日志（确认、建单、拆单、执行）
  - 返回 mock 执行结果
- 风险 `block`：安全拦截，不执行、不建可执行订单

Step 4 状态流（简化）：
- 命令确认前：`ready / parsed / completed`
- 命令确认后：`declined / blocked / executed`
- 订单确认流：`approved -> executed`（mock）

`/api/confirm` 请求示例：

```json
{
  "command_id": "0f16f30d-7e82-4c6b-a85f-78142d63f94e",
  "confirmed": true,
  "execution_mode": "operator",
  "actor_user_id": "deaa3ed3-c910-53d0-8796-755d9c82add6",
  "note": "approve in demo",
  "locale": "zh-CN"
}
```

`/api/confirm` 响应示例：

```json
{
  "status": "ok",
  "command_id": "0f16f30d-7e82-4c6b-a85f-78142d63f94e",
  "execution_mode": "operator",
  "next_action": "completed",
  "payment_order_id": "b6c53a73-fab2-44e7-b333-2ea6f4640932",
  "payment_status": "executed",
  "execution": {
    "mode": "mock",
    "executed": true,
    "transaction_ref": "MOCK-TX-B6C53A73FAB2"
  },
  "risk": {
    "decision": "review",
    "risk_level": "medium",
    "reason_codes": ["MEDIUM_RISK_BENEFICIARY", "HIGH_AMOUNT", "CROSS_BORDER"]
  },
  "audit_trace_id": "trace-cmd-0f16f30d7e82-confirm"
}
```

Step 4 边界：
- 仅做模拟执行，不接入真实支付通道/链上/银行 API
- 不实现取消流与复杂审批流

### Step 5 查询与展示接口概览
Step 5 查询管线：
- 支付列表：`GET /api/payments`
  - 支持 `status/risk_level/user_id/organization_id/beneficiary_name/limit/sort_by/sort_order`
  - 返回前端可直接渲染的列表项（受益人摘要、拆分数、trace、执行摘要）
- 支付详情：`GET /api/payments/{id}`
  - 返回 `payment/beneficiary/splits/risk_checks/command/execution/audit` 结构
- 审计时间线：`GET /api/audit/{trace_id}`
  - 返回按时间排序的审计事件，含 `title/action/details`
- 报表摘要：`GET /api/reports/summary`
  - 返回 `metrics/by_country/by_currency/by_status/by_risk_level/by_risk_decision/by_risk_reason_code/high_risk_samples/latest_commands/latest_report_jobs`
  - 支持 `user_id/organization_id/country/currency/risk_level/status/date_from/date_to` 轻量筛选

Step 5 目标：
- 支撑 demo UI 的支付列表、详情抽屉、审计时间线和机构报表看板
- 保持查询逻辑确定性与可解释性，不引入复杂分析平台

### Step 6 可观测与可解释增强概览
Step 6 增强管线：
- 命令历史与详情：
  - `GET /api/commands`
  - `GET /api/commands/{id}`
  - 支持按 `intent/final_status/user_id/session_id` 轻量筛选
  - 输出命令到支付单的链接关系（是否产出支付单、关联支付单 ID）
- 受益人浏览与画像：
  - `GET /api/beneficiaries`
  - `GET /api/beneficiaries/{id}`
  - 支持国家、风险、黑名单、名称、组织筛选
  - 输出受益人支付统计、近期支付样本、风险画像
- 风险原因码归一化：
  - 统一规范码集合与别名映射
  - 归一化结果输出到 `command` 风险预检、`payments/{id}` 风险检查、`reports/summary` 风险分组

Step 6 目标：
- 让后端具备可演示的“命令可追踪 + 受益人可解释 + 风险可对齐”能力
- 降低前端额外拼装成本，支持命令页、受益人页、风控看板直连

### Step 7B 生命周期可见性与重放/重试增强
Step 7B 增强管线：
- 命令生命周期时间线：
  - `GET /api/commands/{id}/timeline`
  - 统一聚合 command 接收/解析/确认、支付单创建、拆单、模拟执行、审计事件
- 无副作用重放：
  - `POST /api/commands/{id}/replay`
  - 使用原始文本重跑 rule parser + preview（risk/quote），仅返回结果不落库
- 确定性模拟重试：
  - `POST /api/payments/{id}/retry-mock`
  - 采用保守策略：仅对显式可重试的模拟失败单开放重试
  - 已执行返回 `not_needed`，不可重试返回 `non_retriable`
  - 不绕过风险阻断条件，重试过程写入审计日志
- 报表增强：
  - 日期区间筛选（`date_from/date_to`）
  - 新增 `by_risk_level` 与 `latest_commands` 摘要段

Step 7B 目标：
- 增强命令到支付全链路可视化与可复盘能力
- 提供演示安全的 replay/retry 行为，避免真实执行副作用
- 继续保持同步、确定性、可解释的后端交互模型

### Policy / Risk 层占位
- `RiskCheck` 已作为独立实体存在
- 当前策略为 seed 中的示例规则
- 后续可替换为真实策略引擎与规则配置

### Payment Execution 层（Step 8F）
- 执行模式：`mock/simulated/onchain`
- 确认执行路由：`operator` / `user_wallet` / `safe`
- 链路目标：HashKey Chain Testnet（`RPC=https://testnet.hsk.xyz`，`chainId=133`）
- 钱包模型：单一 operator 钱包（后端私钥）签名并提交交易
- 合约事件：`PaymentExecuted`，用于后端事件解码与可视化
- 合约去重防线：`executionItemId` 级别 `executedItems` 防重复执行
- 后端防重协同：提交前预检 + duplicate revert 映射，确保恢复流程不重复发链
- 可观测输出：
  - `GET /api/payments/{id}` 返回 `execution_batch` 聚合计数（`total_items/confirmed_items/failed_items/submitted_items`）
  - `execution_items` 逐项返回 duplicate 标记、duplicate 原因、事件摘要、链上字段
  - `timeline_summary` 返回 duplicate/partial/reconcile 诊断标记
- 拆单执行模型：`split_count > 1` 时按 split 逐笔上链（demo 更直观）
- 回退模型：无拆单时采用订单单笔交易（single tx per order）
- 执行方式：先落地 `execution_batch/item` 再同步发送并等待 receipt，降低“链上成功但库未记录”风险
- mode 扩展路径：
  - `user_wallet`：返回 unsigned transaction payload，`next_action=sign_in_wallet`；由前端签名后通过 `attach-tx` 回传 `tx_hash`
  - `safe`：返回 Safe proposal payload，`next_action=approve_in_safe`；可通过 `attach-safe-proposal` 回填提案信息，再通过 `attach-tx` 回填执行 `tx_hash`
  - `sync-receipt`：按 execution item 手工同步链上回执，复用既有批次/订单聚合状态语义
- 状态：`pending_submission/submitted_onchain/confirmed_onchain/failed_onchain/blocked`
- 批次状态：`planned/in_progress/partially_confirmed/confirmed/failed/cancelled`
- 执行项状态：`planned/submitting/submitted/confirmed/failed`
- 安全边界：仅 Testnet 演示，不等价生产托管/清算系统

### Merchant Settlement 层（Step 9）
目标：
- 商户用法币完成平台侧支付意图，平台内部执行稳定币链上出金。
- 商户无需直接持有或操作稳定币钱包。

核心对象：
- `SettlementQuote`：法币到稳定币报价（含 FX、平台费、网络费、有效期）
- `FiatPaymentIntent`：法币支付意图（商户侧状态机）
- `FiatCollection`：到账确认记录（MVP 手工/模拟）
- `StablecoinPayoutLink`：法币意图到 `payment_order/execution_batch` 的持久化关联

桥接逻辑：
- 入口接口：`POST /api/merchant/fiat-payment/{id}/mark-received`
- 行为：确认法币到账后，创建/复用 payout command，并调用现有 `/api/confirm` 执行链路
- 继承能力：风险拦截、幂等键、拆单执行、链上防重、审计与时间线

状态语义：
- 报价：`active/expired/accepted/cancelled`
- 法币意图：`created/awaiting_fiat/fiat_received/payout_in_progress/completed/failed/cancelled`
- 到账确认：`pending/confirmed/rejected`

### API 面概览（当前）
- `GET /health`
- `POST /api/command`（Step 3 已实现）
- `GET /api/commands`（Step 6 已实现）
- `GET /api/commands/{id}`（Step 6 已实现）
- `GET /api/commands/{id}/timeline`（Step 7B 已实现）
- `POST /api/commands/{id}/replay`（Step 7B 已实现）
- `POST /api/confirm`（Step 8C 已支持 HashKey Testnet 链上执行）
- `POST /api/executions/reconcile`（Step 8D 新增，Step 8F 增加对账审计可见性）
- `POST /api/execution-items/{id}/attach-tx`（execution item 手工附加钱包或 Safe 提交的 `tx_hash`）
- `POST /api/execution-items/{id}/attach-safe-proposal`（safe 模式回填提案元信息）
- `POST /api/execution-items/{id}/sync-receipt`（按 execution item 手工同步链上回执）
- `GET /api/payments`（Step 5 已实现）
- `GET /api/payments/{id}`（Step 5 已实现，Step 8F 增强 execution batch/item 可观测字段）
- `POST /api/payments/{id}/retry-mock`（Step 7B 已实现）
- `GET /api/beneficiaries`（Step 6 已实现）
- `GET /api/beneficiaries/{id}`（Step 6 已实现）
- `GET /api/audit/{trace_id}`（Step 5 已实现）
- `GET /api/reports/summary`（Step 5 已实现，Step 7B 已增强）
- `POST /api/merchant/quote`（Step 9 新增）
- `POST /api/merchant/fiat-payment`（Step 9 新增）
- `POST /api/merchant/fiat-payment/{id}/mark-received`（Step 9 新增）
- `POST /api/merchant/fiat-payment/{id}/create-stripe-session`（Step 11 新增）
- `GET /api/merchant/fiat-payment/{id}`（Step 9 新增）
- `GET /api/merchant/fiat-payments`（Step 9 新增）
- `POST /api/kyc/start`（Step 11 新增）
- `GET /api/kyc/{id}`（Step 11 新增）
- `POST /api/webhooks/stripe`（Step 11 新增）
- `/api/v1/risk`（占位）
- `/api/v1/agent`（占位）

### Step 2-9 对后续工作的支撑
- Agent 侧：可直接读写 `ConversationSession + CommandExecution + PaymentOrder`
- API 侧：已具备命令写入、确认执行、命令追踪、受益人画像、支付查询与报表查询链路
- 报表侧：可基于 `ReportJob + RiskCheck + PaymentOrder` 构造演示报表
- 评审侧：可通过 seed 数据展示端到端业务轨迹
- 确认侧：`/api/confirm` 已完成首版 command-to-order mock 流程
- 展示侧：`/api/commands`、`/api/beneficiaries`、`/api/payments`、`/api/audit/{trace_id}`、`/api/reports/summary` 已可直接驱动前端演示页
- 运营侧：`/api/commands/{id}/timeline`、`/api/commands/{id}/replay`、`/api/payments/{id}/retry-mock` 已提供可追踪、可复盘、可演示重试能力
- 执行侧：`/api/confirm`、`/api/payments/{id}`、`/api/audit/{trace_id}` 已支持链上交易与事件可观测字段
- Step 8D 执行控制侧：新增 `execution_batch/item` 保障幂等、部分失败、恢复对账能力
- Step 8E 执行协同侧：新增 `onchain_duplicate_rejected` 事件与 `onchain_execution_item_id` 响应字段，链上/库内可对齐追踪
- Step 8F 执行观测侧：支付详情与命令时间线已可直观展示 duplicate/partial/reconcile 生命周期事件
- Step 9 商户结算侧：法币报价与到账确认可无缝桥接现有链上稳定币出金引擎，且可在单一明细视图中观测全生命周期
- Step 10 执行模式侧：`user_wallet/safe` 通过 execution-item 附加与回执同步接口接入统一执行架构，保持 `operator` 链路不受影响
- Step 11 法币通道侧：Stripe webhook + KYC 门控将“法币确认”从手工触发升级为事件驱动触发，并保持 payout 引擎复用

### 未来集成点
- LLM 意图解析与工具编排
- 实际支付执行适配层
- 风险策略配置中心
- 报送模板与导出管道
- 任务调度与异步处理

## English

### High-Level Overview
PayFi Box currently uses a hackathon-friendly monorepo architecture:
- `apps/web`: frontend demo layer (role entry points and status sections)
- `apps/api`: backend service layer (FastAPI + data models + command intake + confirmation flow + seed workflow)
- `packages/shared`: shared enums, statuses, and schema placeholders
- `infra`: optional Docker DB fallback
- `docs`: bilingual product and engineering docs

### Layer Design

#### Frontend Layer
- Next.js App Router
- Current focus: role-oriented demo presentation
- Next step: connect list/detail views for `PaymentOrder`, `RiskCheck`, and `ReportJob`

#### Backend Layer
- FastAPI + Pydantic Settings
- SQLAlchemy 2 for ORM models
- Alembic for schema migrations
- Seed scripts for repeatable demo data and reset flows
- Step 3 command-intake module:
  - `POST /api/command`
  - rule-based intent classification and slot extraction
  - mock risk / quote preview
  - `command_executions` persistence
- Step 4 confirmation module:
  - `POST /api/confirm`
  - confirmability validation
  - `payment_orders` / `payment_splits` creation
  - audit logging and mock execution writeback
- Step 5 query module:
  - `GET /api/payments`
  - `GET /api/payments/{id}`
  - `GET /api/audit/{trace_id}`
  - `GET /api/reports/summary`
  - frontend-ready response shapes for list/detail/timeline/dashboard
- Step 6 observability and explainability module:
  - `GET /api/commands`
  - `GET /api/commands/{id}`
  - `GET /api/beneficiaries`
  - `GET /api/beneficiaries/{id}`
- Step 7B lifecycle and replay/retry module:
  - `GET /api/commands/{id}/timeline`
  - `POST /api/commands/{id}/replay`
  - `POST /api/payments/{id}/retry-mock`
  - enhanced `GET /api/reports/summary` (`date_from/date_to`, `by_risk_level`, `latest_commands`)
  - normalized risk reason-code outputs across command/payment/report surfaces
- Step 8C HashKey testnet execution module:
  - contract: `apps/contracts/contracts/PaymentExecutor.sol`
  - deployment workflow: Hardhat (`make contract-compile` / `make contract-deploy-hashkey`)
  - `/api/confirm` can submit real testnet transactions when `PAYMENT_EXECUTION_BACKEND=hashkey_testnet`
  - execution routing: `execution_mode=operator/user_wallet/safe` (default `operator`)
  - persisted + returned execution fields include `tx_hash`, `explorer_url`, `onchain_status`, and decoded event summary (when available)
- Step 8D durable execution enhancements:
  - adds `payment_execution_batches` and `payment_execution_items`
  - splits confirmation into transactional planning + post-commit execution processing
  - enforces request-level idempotency with `idempotency_key` (MVP hardening for testnet demo)
  - supports partial execution semantics (`partially_executed`, `partially_confirmed`)
  - adds reconciliation endpoint: `POST /api/executions/reconcile`
- Step 8E contract/backend idempotency hardening:
  - contract enforces item-level duplicate protection with `executedItems[executionItemId]`
  - backend performs pre-submit `executedItems` preflight checks
  - duplicate revert is mapped to a safe idempotent outcome instead of a generic crash path
  - adds audit action `onchain_duplicate_rejected` for timeline visibility
- Step 8F execution observability enhancements:
  - `GET /api/payments/{id}` now exposes `execution_batch` counters and richer `execution_items`
  - payment detail includes `timeline_summary` for duplicate/partial/reconcile visibility
  - reconciliation writes explicit audit actions: `execution_batch_reconciled`, `execution_item_reconciled`
  - command timeline can directly show reconciliation and duplicate-protection events
- Step 9 merchant fiat-in settlement module:
  - adds `SettlementQuote`, `FiatPaymentIntent`, `FiatCollection`, and `StablecoinPayoutLink`
  - merchant fiat lifecycle: quote -> fiat intent -> fiat-received confirmation
  - bridges into existing payout execution path by reusing `/api/confirm` + execution batch/item + onchain execution
  - adds merchant APIs: `/api/merchant/quote`, `/api/merchant/fiat-payment`, `/api/merchant/fiat-payment/{id}/mark-received`, `/api/merchant/fiat-payment/{id}`
- Step 10 execution-mode expansion:
  - `user_wallet`: confirm returns signable tx payloads; backend state is updated via `attach-tx` + `sync-receipt`
  - `safe`: confirm returns Safe proposal payloads; backend state is updated via `attach-safe-proposal` + `attach-tx/sync-receipt`
  - payment detail visibility fields include `pending_action`, `unsigned_tx_request`, `safe_proposal_request`, `safe_proposal_attachment`, and `tx_attachment` (mode/state-dependent)
  - all three modes share the same `payment_order + execution_batch + execution_item` backbone (no parallel execution engine)
- Step 11 Stripe fiat channel + KYC gating:
  - adds `kyc_verifications` for durable merchant/user KYC state
  - adds `POST /api/kyc/start` and `GET /api/kyc/{id}`
  - adds `POST /api/merchant/fiat-payment/{id}/create-stripe-session` / `POST /api/merchant/fiat-payment/{id}/start-stripe-payment` and `POST /api/webhooks/stripe`
  - payout bridge is triggered only after Stripe `payment_intent.succeeded` with verified KYC
  - `checkout.session.completed` is treated as channel progress only, not final fiat confirmation
  - Stripe channel blocks manual frontend `mark-received` by default; confirmation must come from provider webhook
  - manual fallback is demo/admin-only and requires explicit override switch
  - webhook signature verification is required, and duplicate deliveries are idempotently ignored by `event_id`
- Step 12 platform balance + MCP access layer:
  - adds `platform_balance_accounts`, `platform_balance_ledger_entries`, `platform_balance_locks`, and `fiat_deposit_orders`
  - adds balance APIs for deposit creation, Stripe collection, sync, balance query, ledger query, and balance-funded settlement preview/confirm
  - balance-funded settlement only adds a funding-source layer; the existing `payment_order + execution_batch + execution_item` execution backbone remains unchanged
  - mounts MCP at `/mcp`
  - MCP initially exposes balance, deposit, preview, and confirm tools without creating a second payment engine
  - KYC is enforced before MCP payment/deposit access is granted
  - duplicate deposit webhooks now leave explicit audit markers and duplicate-event history for explainable idempotency

#### Shared Layer
- Unified status definitions live in `packages/shared/src/domain.ts`
- Includes:
  - `user role`
  - `organization type`
  - `payment order status`
  - `payment split status`
  - `risk level`
  - `risk check result`
  - `risk reason code`
  - `execution mode`
  - `execution route`
  - `command execution status`
  - `session status`
  - `report job status`
- Goal: keep frontend/backend state values aligned

#### Data Layer
- PostgreSQL is the primary database
- 11 core entities are implemented in step 2
- Step 9 adds merchant settlement entities (`SettlementQuote/FiatPaymentIntent/FiatCollection/StablecoinPayoutLink`)
- Step 12 adds platform balance entities (`PlatformBalanceAccount/PlatformBalanceLedgerEntry/PlatformBalanceLock/FiatDepositOrder`)
- The design intentionally favors speed and readability over multi-tenant complexity

### Step 2 Data Model Overview
- `Organization`: legal/business entity (trade company or financial institution)
- `User`: system user, optionally linked to an organization
- `Beneficiary`: payee profile with risk and blacklist flags
- `ConversationSession`: user interaction session
- `CommandExecution`: natural-language input and parsing trace
- `PaymentOrder`: core payment object with lifecycle status
- `PaymentSplit`: split plan items
- `PaymentQuote`: fee/route/ETA preview
- `RiskCheck`: policy/compliance check results
- `AuditLog`: auditable event stream
- `ReportJob`: reporting generation request

### Entity Relationship Summary
- `Organization` 1-N `User`
- `Organization` 1-N `Beneficiary` (optional)
- `User` 1-N `ConversationSession`
- `ConversationSession` 1-N `CommandExecution`
- `CommandExecution` 0..N `PaymentOrder` via `source_command_id`
- `PaymentOrder` 1-N `PaymentSplit`
- `PaymentOrder` 1-N `PaymentQuote`
- `PaymentOrder` 1-N `RiskCheck`
- `User` 1-N `ReportJob`
- `User` 1-N `AuditLog` as actor

### Payment Lifecycle
Unified statuses:
- `draft`
- `quoted`
- `pending_confirmation`
- `approved`
- `executed`
- `failed`
- `cancelled`

These values are consistent between backend models and shared definitions.

### Risk Model (MVP)
- Risk levels: `low` / `medium` / `high`
- Check results: `allow` / `review` / `block`
- Blacklisted beneficiaries can directly trigger `block`

### Agent Layer Placeholder (No Real AI Yet)
- `POST /api/command` now provides a deterministic command-intake pipeline
- `CommandExecution` stores raw text, parsed intent JSON, tool-call traces, and status
- Real LLM orchestration is intentionally deferred; parser layer is replaceable

### Step 3 Command Intake Overview
Command pipeline:
- Accept natural-language input (`user_id` + `text`)
- Classify intent (`create_payment`, `query_payments`, `generate_report`, `unknown`)
- Extract slots (recipient, amount, currency, splits, reference, urgency)
- Detect missing required fields and return follow-up question
- Generate mock risk and quote previews
- Persist each command into `command_executions`

Supported intents:
- `create_payment`
- `query_payments`
- `generate_report`
- `unknown`

Request example:

```json
{
  "user_id": "babd0649-6a5a-5d02-aa46-9070ee5248d4",
  "text": "Send 50 USDC to Lucy",
  "channel": "web",
  "locale": "en-US"
}
```

Response example:

```json
{
  "status": "ok",
  "intent": "create_payment",
  "confidence": 0.95,
  "missing_fields": [],
  "next_action": "confirm_preview",
  "risk": {
    "decision": "allow",
    "risk_level": "low"
  },
  "quote": {
    "estimated_fee": 0.7,
    "route": "TRON-USDC",
    "eta_text": "within 2 hours"
  }
}
```

Parser limitations (Step 3):
- Current implementation is rule-based (regex + keywords + demo-data matching), not LLM-integrated.
- Coverage is intentionally limited to deterministic MVP command flows.
- The classifier/parser layer is designed to be replaced or augmented by a real LLM later.

### Step 4 Confirmation and Mock Execution Overview
Confirmation pipeline:
- Submit `command_id + confirmed` to `/api/confirm`
- Validate that command is confirmable (intent, required fields, and current status)
- `confirmed=false`: mark declined and stop
- `confirmed=true` and risk not blocked:
  - create `payment_order`
  - create `payment_splits` when `split_count > 1`
  - write audit logs for confirmation, order creation, split creation, and execution
  - return deterministic mock execution result
- risk `block`: safe block response, no executable order is created

Step 4 status flow (simplified):
- Command status after confirmation: `declined` / `blocked` / `executed`
- Payment order status in mock confirmation: `approved -> executed`

`/api/confirm` request example:

```json
{
  "command_id": "0f16f30d-7e82-4c6b-a85f-78142d63f94e",
  "confirmed": true,
  "execution_mode": "operator",
  "actor_user_id": "deaa3ed3-c910-53d0-8796-755d9c82add6",
  "note": "approve in demo",
  "locale": "en-US"
}
```

`/api/confirm` response example:

```json
{
  "status": "ok",
  "command_id": "0f16f30d-7e82-4c6b-a85f-78142d63f94e",
  "execution_mode": "operator",
  "next_action": "completed",
  "payment_order_id": "b6c53a73-fab2-44e7-b333-2ea6f4640932",
  "payment_status": "executed",
  "execution": {
    "mode": "mock",
    "executed": true,
    "transaction_ref": "MOCK-TX-B6C53A73FAB2"
  },
  "risk": {
    "decision": "review",
    "risk_level": "medium",
    "reason_codes": ["MEDIUM_RISK_BENEFICIARY", "HIGH_AMOUNT", "CROSS_BORDER"]
  },
  "audit_trace_id": "trace-cmd-0f16f30d7e82-confirm"
}
```

Step 4 boundaries:
- Simulated execution only (no real provider, bank, or blockchain rails)
- No cancellation flow or complex approval workflow yet

### Step 5 Read/Query API Overview
Step 5 query pipeline:
- Payment list: `GET /api/payments`
  - supports `status/risk_level/user_id/organization_id/beneficiary_name/limit/sort_by/sort_order`
  - returns frontend-ready items with beneficiary summary, split count, trace IDs, and execution summary
- Payment detail: `GET /api/payments/{id}`
  - returns nested sections: `payment/beneficiary/splits/risk_checks/command/execution/audit`
- Audit timeline: `GET /api/audit/{trace_id}`
  - returns time-ordered timeline items with `title/action/details`
- Report summary: `GET /api/reports/summary`
  - returns `metrics/by_country/by_currency/by_status/by_risk_level/by_risk_decision/by_risk_reason_code/high_risk_samples/latest_commands/latest_report_jobs`
  - supports lightweight filters: `user_id/organization_id/country/currency/risk_level/status/date_from/date_to`

Step 5 objective:
- Directly support demo UI payment list/detail/report pages and observability views
- Keep APIs deterministic, readable, and hackathon-friendly

### Step 6 Observability and Explainability Enhancements
Step 6 enhancement pipeline:
- Command history and inspection:
  - `GET /api/commands`
  - `GET /api/commands/{id}`
  - lightweight filters on `intent/final_status/user_id/session_id`
  - explicit command-to-payment linkage fields
- Beneficiary browsing and profiling:
  - `GET /api/beneficiaries`
  - `GET /api/beneficiaries/{id}`
  - filters by country/risk/blacklist/name/organization
  - beneficiary usage stats, recent-payment samples, and risk profile blocks
- Risk reason-code normalization:
  - canonical reason-code set with alias mapping
  - normalized outputs available for command risk preview, payment detail risk checks, and report summary groupings

Step 6 objective:
- Make backend inspection flows feel product-complete for demos (commands + beneficiaries + risk explainability)
- Reduce frontend transformation effort via directly renderable response structures

### Step 7B Lifecycle Visibility, Replay, and Retry Enhancements
Step 7B enhancement pipeline:
- Command lifecycle timeline:
  - `GET /api/commands/{id}/timeline`
  - combines command intake/parse/confirmation, order and split creation, mock execution, and audit events
- Side-effect-free replay:
  - `POST /api/commands/{id}/replay`
  - re-runs deterministic parse/preview from original command text without creating orders or execution side effects
- Deterministic mock retry:
  - `POST /api/payments/{id}/retry-mock`
  - conservative by default: retry is only allowed for explicitly retryable mock-failure states
  - returns explicit `not_needed` / `non_retriable` otherwise
  - does not bypass risk blocking conditions and always appends audit logs
- Richer reports summary:
  - date-range filtering (`date_from/date_to`)
  - additional sections such as `by_risk_level` and `latest_commands`

Step 7B objective:
- improve lifecycle observability and replayability for demo operations
- provide safe simulated retry behavior without pretending real execution rails
- keep backend behavior synchronous, deterministic, and easy to inspect

### Policy / Risk Layer Placeholder
- `RiskCheck` exists as a dedicated entity
- Current policy behavior is demo-seed driven
- Can be replaced by a configurable policy engine later

### Payment Execution Layer (Step 8F)
- Execution modes: `mock/simulated/onchain`
- Confirm execution routes: `operator` / `user_wallet` / `safe`
- Network target: HashKey Chain Testnet (`RPC=https://testnet.hsk.xyz`, `chainId=133`)
- Wallet model: single operator wallet (backend private key) signs and submits transactions
- Contract event decoding: `PaymentExecuted` from `PaymentExecutor`
- Contract idempotency guard: execution-item-level duplicate rejection via `executedItems`
- Backend idempotency cooperation: pre-submit `executedItems` preflight + safe duplicate-revert mapping
- Observability outputs:
  - `GET /api/payments/{id}` returns execution-batch counters and per-item execution visibility
  - `execution_items` include duplicate flags/reasons plus decoded-event summaries
  - `timeline_summary` exposes duplicate/partial/reconciliation status at a glance
- Split execution model: one tx per split when `split_count > 1`
- Fallback model: single transaction per order when no split rows are present
- Execution mode: persist execution intent first (`batch/item`), then synchronous send + in-process receipt wait
- Mode expansion paths:
  - `user_wallet`: returns unsigned transaction payload (`next_action=sign_in_wallet`); frontend signs/submits, then backend ingests `tx_hash` via `attach-tx`
  - `safe`: returns Safe proposal payload (`next_action=approve_in_safe`); backend ingests proposal metadata via `attach-safe-proposal`, then ingests executed `tx_hash` via `attach-tx`
  - `sync-receipt`: execution-item-level manual receipt sync, reusing existing batch/order aggregation semantics
- Onchain lifecycle: `pending_submission/submitted_onchain/confirmed_onchain/failed_onchain/blocked`
- Batch lifecycle: `planned/in_progress/partially_confirmed/confirmed/failed/cancelled`
- Item lifecycle: `planned/submitting/submitted/confirmed/failed`
- Safety boundary: testnet-only demo execution, not production custody/settlement

### Merchant Settlement Layer (Step 9)
Goal:
- Merchants pay in fiat on-platform while the platform settles stablecoin payout onchain.
- Merchants do not need to directly manage stablecoin wallets.

Core objects:
- `SettlementQuote`: fiat-to-stablecoin quote (FX, platform fee, network fee, expiry)
- `FiatPaymentIntent`: fiat payment intent with merchant-facing lifecycle
- `FiatCollection`: fiat receipt confirmation record (manual/simulated in MVP)
- `StablecoinPayoutLink`: durable link from fiat intent to `payment_order/execution_batch`

Bridge behavior:
- Entry API: `POST /api/merchant/fiat-payment/{id}/mark-received`
- After fiat confirmation, backend creates/reuses payout command and calls existing `/api/confirm` execution path
- Reuses existing safeguards: risk blocking, idempotency keys, split execution, onchain duplicate protection, audit/timeline visibility

Status semantics:
- Quote: `active/expired/accepted/cancelled`
- Fiat intent: `created/awaiting_fiat/fiat_received/payout_in_progress/completed/failed/cancelled`
- Collection: `pending/confirmed/rejected`

### Current API Surface
- `GET /health`
- `POST /api/command` (implemented in step 3)
- `GET /api/commands` (implemented in step 6)
- `GET /api/commands/{id}` (implemented in step 6)
- `GET /api/commands/{id}/timeline` (implemented in step 7B)
- `POST /api/commands/{id}/replay` (implemented in step 7B)
- `POST /api/confirm` (step 8C includes HashKey testnet onchain execution path)
- `POST /api/executions/reconcile` (added in step 8D, with reconciliation audit visibility in step 8F)
- `POST /api/execution-items/{id}/attach-tx` (attach wallet/Safe submitted `tx_hash` at execution-item level)
- `POST /api/execution-items/{id}/attach-safe-proposal` (attach safe-proposal metadata for safe mode)
- `POST /api/execution-items/{id}/sync-receipt` (execution-item-level manual receipt sync)
- `GET /api/payments` (implemented in step 5)
- `GET /api/payments/{id}` (implemented in step 5, enhanced in step 8F with execution-layer visibility)
- `POST /api/payments/{id}/retry-mock` (implemented in step 7B)
- `GET /api/beneficiaries` (implemented in step 6)
- `GET /api/beneficiaries/{id}` (implemented in step 6)
- `GET /api/audit/{trace_id}` (implemented in step 5)
- `GET /api/reports/summary` (implemented in step 5, enhanced in step 7B)
- `POST /api/merchant/quote` (added in step 9)
- `POST /api/merchant/fiat-payment` (added in step 9)
- `POST /api/merchant/fiat-payment/{id}/mark-received` (added in step 9)
- `POST /api/merchant/fiat-payment/{id}/create-stripe-session` (added in step 11)
- `GET /api/merchant/fiat-payment/{id}` (added in step 9)
- `GET /api/merchant/fiat-payments` (added in step 9)
- `POST /api/kyc/start` (added in step 11)
- `GET /api/kyc/{id}` (added in step 11)
- `POST /api/webhooks/stripe` (added in step 11)
- `/api/v1/risk` (placeholder)
- `/api/v1/agent` (placeholder)

### How Step 2-10 Supports Future Agent and API Work
- Agent flows can directly build on `ConversationSession + CommandExecution + PaymentOrder`
- API foundations now cover command intake, confirmation, command inspection, beneficiary profiling, and demo-facing queries
- Reporting can be bootstrapped from `ReportJob + RiskCheck + PaymentOrder`
- Seed data enables end-to-end demos for judges and teammates
- `/api/confirm` now provides a first command-to-order confirmation path
- Step 6 endpoints extend this with command/beneficiary observability without schema refactoring
- Step 7B endpoints add lifecycle timelines, side-effect-free replay, and deterministic mock retry for operational demos
- Step 8C execution path adds explorer-verifiable tx metadata and onchain event traces to confirmation/payment/audit surfaces
- Step 8D adds durable execution control (`batch/item`) for idempotency, partial-failure semantics, and recovery/reconciliation
- Step 8E adds contract/backend duplicate-protection convergence so replay/reconcile flows keep item-level idempotency guarantees
- Step 8F adds execution-layer observability so payment detail and timelines directly expose batch/item lifecycle and reconciliation effects
- Step 9 adds a merchant-facing fiat-in layer that transparently feeds the existing onchain stablecoin payout engine with full lifecycle visibility
- Step 10 adds mode-aware execution handoff (`operator/user_wallet/safe`) while preserving one durable execution model for frontend integration
- Step 11 adds webhook-driven Stripe confirmation and KYC gating, so fiat-side truth can trigger payout safely without introducing a second execution engine

### Future Integration Points
- LLM parsing and orchestration layer
- real payment execution adapters
- configurable risk policy center
- report templating/export pipeline
- asynchronous job scheduling
