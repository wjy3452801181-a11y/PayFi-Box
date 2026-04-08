# Demo Seed Plan

## Purpose
This document captures a short seed plan for the next implementation phase so the team can turn the step 1 foundation into a hackathon demo without over-scoping the build.

## Language Structure
This file contains a complete Chinese section followed by a complete English section. Both sections are intended to be fully usable on their own.

## 中文版

### 目标
- 基于当前工程底座，尽快形成可演示的 step 2 版本
- 优先保证从输入到展示结果的闭环，而不是追求真实支付接入

### 建议优先级
- 第一优先级：自然语言输入转结构化支付意图
- 第二优先级：前端三角色工作台与基础状态流转
- 第三优先级：风险提示、报送占位与审计记录展示

### 建议演示路径
- 零售路径：输入一句支付请求，看到解析结果、确认卡片和状态变更
- 贸易路径：输入贸易付款说明，看到结构化字段、风险提示和支付草稿
- 机构路径：打开审核视图，看到案件摘要、风险等级与报送预览

### 最小数据准备
- 3 组零售支付示例文本
- 3 组贸易跨境付款示例文本
- 3 组金融机构审核案例示例数据

### Step 2 建议交付
- 基础表单或聊天输入组件
- `payment intent` 解析接口
- 风险等级占位逻辑
- 报送摘要占位逻辑
- 前后端联调演示流程

## English

### Goal
- Turn the current engineering foundation into a demo-ready step 2 build as quickly as possible
- Prioritize an end-to-end input-to-output flow instead of real payment integration

### Suggested Priorities
- First priority: convert natural-language input into a structured payment intent
- Second priority: add three role-based workspaces and basic state transitions
- Third priority: show risk prompts, reporting placeholders, and audit visibility

### Suggested Demo Paths
- Retail path: enter a payment request and see parsed output, a confirmation card, and status changes
- Trade path: enter a trade payment description and see structured fields, risk prompts, and a payment draft
- Institution path: open a review view and see case summary, risk level, and reporting preview

### Minimum Seed Data
- 3 retail payment sample prompts
- 3 trade cross-border payment sample prompts
- 3 financial-institution review sample cases

### Suggested Step 2 Deliverables
- basic form or chat-style input component
- `payment intent` parsing endpoint
- placeholder risk tiering logic
- placeholder reporting summary logic
- integrated frontend-backend demo flow

