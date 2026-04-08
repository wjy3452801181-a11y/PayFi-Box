# Product Specification

## Purpose
This document defines the initial product scope for PayFi Box, focusing on the hackathon MVP boundary and the intended user roles, use cases, and safety posture.

## Language Structure
This file contains a complete Chinese section followed by a complete English section. Both sections are intended to be fully usable on their own.

## 中文版

### 产品概述
PayFi Box 是一个 AI-native PayFi 产品概念，目标是在一个统一系统中支持三类场景：
- 面向消费者的自然语言零售支付
- 面向贸易企业的跨境支付与业务上下文辅助
- 面向金融机构的报送、风控审核与审计追踪

定位说明：PayFi Box 不是一个钱包，而是一个 AI-native 的支付编排层。

### 目标用户
- 零售用户：希望通过自然语言完成支付意图表达与确认
- 贸易公司：需要将订单、发票、收款方与跨境支付动作串联起来
- 金融机构：需要查看风险上下文、审核建议、结构化报送结果与操作记录

### MVP 范围
- 输入自然语言支付请求并生成结构化意图占位结果
- 提供按角色划分的前端入口与演示页面
- 提供 API 模块骨架，用于承接支付、风控、报送、Agent 与审计功能
- 提供本地 PostgreSQL 基础设施，用于下一阶段接入数据模型
- 提供清晰的工程文档，便于黑客松期间快速协作

### 非目标
- 不在 step 1 中接入真实支付通道
- 不在 step 1 中实现完整审批流或风控规则引擎
- 不在 step 1 中实现真实报送模板生成
- 不在 step 1 中实现多租户、生产部署或复杂权限系统
- 不在 step 1 中实现认证与权限登录流程
- 不在 step 1 中接入区块链能力
- 不在 step 1 中接入支付服务商能力
- 不在 step 1 中接入真实 LLM 服务

### 核心用例
- 零售支付：用户输入“帮我付今天午餐 58 元给商家”，系统解析并生成待确认支付意图
- 贸易跨境：操作员输入与贸易订单相关的付款说明，系统提炼关键字段并准备支付审核上下文
- 金融机构审核：分析员查看 AI 生成的案件摘要、风险等级建议与报送占位信息

### 安全原则
AI 理解，系统决策。

这意味着：
- AI 负责理解自然语言和生成候选结构化结果
- 系统负责规则校验、风险打分、审批约束和最终执行控制
- 任何高风险动作都应保留人工或策略层确认入口

### 计划中的演示故事
- Demo 1：零售用户输入自然语言支付请求，系统生成支付卡片与确认步骤
- Demo 2：贸易公司上传或输入跨境付款描述，系统生成结构化付款单草稿与风险提示
- Demo 3：金融机构查看审核工作台，看到案件摘要、风险标签和报送占位结果

### 未来扩展
- 接入 LLM 驱动的意图抽取与解释层
- 接入真实支付执行服务或模拟清算层
- 支持文档上传、OCR、发票解析与订单核验
- 接入规则引擎、案例管理与可追溯审计日志
- 支持角色权限、组织视图和多实体账户体系

## English

### Product Overview
PayFi Box is an AI-native PayFi product concept designed to support three scenarios within one unified system:
- consumer-facing natural-language retail payments
- trade-company cross-border payments with business context
- financial-institution reporting, risk review, and audit visibility

Positioning: PayFi Box is not a wallet, but an AI-native payment orchestration layer.

### Target Users
- Retail users who want to express payment intent in natural language
- Trade companies that need to connect orders, invoices, beneficiaries, and cross-border payment actions
- Financial institutions that need risk context, review recommendations, structured reports, and operation history

### MVP Scope
- Accept natural-language payment requests and produce structured intent placeholders
- Provide role-based frontend entry points and demo pages
- Provide API module scaffolding for payments, risk, reporting, agent, and audit capabilities
- Provide local PostgreSQL infrastructure for the next phase of data modeling
- Provide clear engineering documentation to support fast hackathon collaboration

### Non-Goals
- No real payment rail integration in step 1
- No full approval workflow or risk rules engine in step 1
- No real regulatory report generation in step 1
- No multi-tenant production infrastructure or complex permission system in step 1
- No authentication or login flows in step 1
- No blockchain integration in step 1
- No payment-provider integration in step 1
- No real LLM service integration in step 1

### Core Use Cases
- Retail payment: a user enters a request such as “pay 58 CNY for my lunch today,” and the system converts it into a confirmation-ready intent
- Trade cross-border payment: an operator enters payment instructions tied to a trade order, and the system extracts key fields and prepares review context
- Financial institution review: an analyst opens a case view with AI-generated summary, suggested risk level, and reporting placeholders

### Safety Principle
AI understands, system decides.

This means:
- AI is responsible for understanding natural language and generating candidate structured output
- The system is responsible for rules validation, risk scoring, approval constraints, and execution control
- Any high-risk action should retain a human or policy-layer confirmation gate

### Planned Demo Stories
- Demo 1: a retail user enters a natural-language payment request and receives a payment card with confirmation steps
- Demo 2: a trade company enters cross-border payment details and receives a draft payment order with risk prompts
- Demo 3: a financial institution opens a review workspace with case summary, risk labels, and reporting placeholders

### Future Extensions
- Add an LLM-powered intent extraction and explanation layer
- Add a real payment execution service or settlement simulator
- Support document upload, OCR, invoice parsing, and order verification
- Add rules engines, case management, and traceable audit logs
- Add role permissions, organization views, and multi-entity account structures
