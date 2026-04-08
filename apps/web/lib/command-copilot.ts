import type { CommandResponse } from "./api";

export type ExecutionMode = "operator" | "user_wallet" | "safe";

export type ParsedPreview = {
  beneficiaryName?: string;
  amount?: number;
  currency?: string;
  splitCount?: number;
  reference?: string;
};

export type AiClarification = {
  title: string;
  body: string;
  question: string | null;
  fields: string[];
};

export type AiRouteRecommendation = {
  recommendedMode: ExecutionMode;
  fallbackMode: ExecutionMode;
  summary: string;
  why: string;
  reasons: string[];
};

export function parsePaymentPreview(command: CommandResponse | null): ParsedPreview | null {
  if (!command) return null;
  const preview = command.preview;
  const extracted = preview?.extracted;
  if (!extracted || typeof extracted !== "object") return null;
  const value = extracted as Record<string, unknown>;
  return {
    beneficiaryName:
      typeof value.recipient === "string" && value.recipient ? value.recipient : undefined,
    amount: typeof value.amount === "number" ? value.amount : undefined,
    currency: typeof value.currency === "string" ? value.currency : undefined,
    splitCount: typeof value.split_count === "number" ? value.split_count : undefined,
    reference: typeof value.reference === "string" && value.reference ? value.reference : undefined,
  };
}

export function buildExamplePrompts(lang: "zh" | "en"): string[] {
  if (lang === "en") {
    return [
      "Send 50 USDC to Lucy",
      "Pay ACME 30000 USDT in 3 splits with reference INV-009",
      "Show last week's cross-border receipts grouped by country and highlight risky ones",
    ];
  }
  return [
    "帮我给 Lucy 转 120 USDC，今晚到账，手续费最低",
    "给 ACME 支付 30000 USDT，拆成 3 笔，备注 INV-009",
    "查询上周跨境收款，按国家分类，并标出高风险交易",
  ];
}

export function buildPaymentCommand(input: {
  lang: "zh" | "en";
  recipientName: string;
  amount: string;
  currency: string;
  reference: string;
}) {
  const normalizedAmount = input.amount.trim() || "100";
  const normalizedCurrency = input.currency.trim().toUpperCase() || "USDT";
  const normalizedRecipient = input.recipientName || (input.lang === "zh" ? "收款方" : "recipient");
  const normalizedReference = input.reference.trim();
  if (input.lang === "zh") {
    if (normalizedReference) {
      return `给 ${normalizedRecipient} 支付 ${normalizedAmount} ${normalizedCurrency}，备注 ${normalizedReference}`;
    }
    return `给 ${normalizedRecipient} 支付 ${normalizedAmount} ${normalizedCurrency}`;
  }
  if (normalizedReference) {
    return `Send ${normalizedAmount} ${normalizedCurrency} to ${normalizedRecipient} with reference ${normalizedReference}`;
  }
  return `Send ${normalizedAmount} ${normalizedCurrency} to ${normalizedRecipient}`;
}

export function getAiPlanSummary(input: {
  t: (key: string) => string;
  hasPreview: boolean;
  missingFields: string[];
  riskDecision?: string | null;
  mode: ExecutionMode;
}) {
  if (!input.hasPreview) return input.t("command.aiPlanEmpty");
  if (input.missingFields.length > 0) {
    return `${input.t("command.aiPlanMissing")} ${input.missingFields.join(", ")}`;
  }
  if (input.riskDecision === "block") return input.t("command.aiPlanBlocked");
  if (input.riskDecision === "review") return input.t("command.aiPlanReview");
  if (input.mode === "operator") return input.t("command.aiPlanOperator");
  if (input.mode === "user_wallet") return input.t("command.aiPlanWallet");
  return input.t("command.aiPlanSafe");
}

export function getAiReasonList(input: {
  t: (key: string) => string;
  mode: ExecutionMode;
  riskDecision?: string | null;
  missingFields: string[];
  splitCount?: number;
}) {
  const reasons: string[] = [];
  if (input.missingFields.length > 0) reasons.push(input.t("command.aiReasonMissing"));
  if (input.riskDecision === "review") reasons.push(input.t("command.aiReasonReview"));
  if (input.riskDecision === "block") reasons.push(input.t("command.aiReasonBlocked"));
  if ((input.splitCount || 0) > 1) reasons.push(input.t("command.aiReasonSplit"));
  if (input.mode === "operator") reasons.push(input.t("command.aiReasonOperator"));
  if (input.mode === "user_wallet") reasons.push(input.t("command.aiReasonWallet"));
  if (input.mode === "safe") reasons.push(input.t("command.aiReasonSafe"));
  return reasons.slice(0, 3);
}

export function getAiConfidence(input: {
  missingFields: string[];
  riskDecision?: string | null;
  splitCount?: number;
}): "high" | "medium" | "low" {
  if (input.missingFields.length > 0 || input.riskDecision === "block") return "low";
  if (input.riskDecision === "review" || (input.splitCount || 0) > 1) return "medium";
  return "high";
}

export function getAiRouteSteps(input: {
  t: (key: string) => string;
  mode: ExecutionMode;
  riskDecision?: string | null;
}): string[] {
  const steps = [input.t("command.aiStepInterpret"), input.t("command.aiStepReview")];
  if (input.riskDecision === "block") return [...steps, input.t("command.aiStepHold")];
  if (input.mode === "operator") return [...steps, input.t("command.aiStepOperator"), input.t("command.aiStepMonitor")];
  if (input.mode === "user_wallet") return [...steps, input.t("command.aiStepWallet"), input.t("command.aiStepMonitor")];
  return [...steps, input.t("command.aiStepSafe"), input.t("command.aiStepMonitor")];
}

export function getClarificationCopy(
  lang: "zh" | "en",
  missingFields: string[],
  followUpQuestion?: string | null,
): AiClarification | null {
  if (missingFields.length === 0 && !followUpQuestion) return null;
  if (lang === "zh") {
    return {
      title: "AI 还需要补充信息",
      body:
        missingFields.length > 0
          ? `在进入结算前，还需要补齐这些字段：${missingFields.join("、")}`
          : "进入结算前，建议先补全一条关键信息，避免生成偏差的执行方案。",
      question:
        followUpQuestion ||
        (missingFields.includes("currency")
          ? "这笔结算希望用哪种币种？"
          : missingFields.includes("amount")
            ? "这笔结算的金额是多少？"
            : missingFields.includes("recipient")
              ? "这笔结算要发给谁？"
              : "你希望这笔结算优先速度、费用还是审批控制？"),
      fields: missingFields,
    };
  }
  return {
    title: "AI needs one more clarification",
    body:
      missingFields.length > 0
        ? `Before settlement can proceed, I still need these fields: ${missingFields.join(", ")}`
        : "Before settlement can proceed, one more key detail should be clarified so the route recommendation stays reliable.",
    question:
      followUpQuestion ||
      (missingFields.includes("currency")
        ? "Which currency should this settlement use?"
        : missingFields.includes("amount")
          ? "What amount should be settled?"
          : missingFields.includes("recipient")
            ? "Who should receive this settlement?"
            : "Should this prioritize speed, cost, or approval control?"),
    fields: missingFields,
  };
}

export function getRouteRecommendation(input: {
  lang: "zh" | "en";
  selectedMode: ExecutionMode;
  riskDecision?: string | null;
  missingFields: string[];
  splitCount?: number;
  amount?: number;
}): AiRouteRecommendation {
  const { lang, selectedMode, riskDecision, missingFields, splitCount, amount } = input;

  const highControl = riskDecision === "review" || (splitCount || 0) > 1 || (amount || 0) >= 5000;
  const walletFriendly = (amount || 0) >= 1000 && (amount || 0) < 5000 && riskDecision !== "review";

  let recommendedMode: ExecutionMode = selectedMode;
  if (missingFields.length > 0 || riskDecision === "block") {
    recommendedMode = selectedMode;
  } else if (highControl) {
    recommendedMode = "safe";
  } else if (walletFriendly) {
    recommendedMode = "user_wallet";
  } else {
    recommendedMode = "operator";
  }

  const fallbackMode: ExecutionMode =
    recommendedMode === "safe" ? "operator" : recommendedMode === "operator" ? "user_wallet" : "operator";

  if (lang === "zh") {
    if (missingFields.length > 0) {
      return {
        recommendedMode,
        fallbackMode,
        summary: "先补齐关键信息，再确定最终结算路径。",
        why: "当前最重要的不是直接提交，而是先把收款方、金额或币种补完整，再由系统给出更稳定的结算建议。",
        reasons: ["待补字段", "需要澄清意图", "暂不建议直接提交"],
      };
    }
    if (riskDecision === "block") {
      return {
        recommendedMode,
        fallbackMode,
        summary: "当前交易被拦截，建议暂停推进并先处理风控问题。",
        why: "命中阻断规则时，继续切换模式不会改变结果，最合理的动作是先核查收款方、资金来源或交易背景。",
        reasons: ["风险拦截", "未进入执行", "建议人工复核"],
      };
    }
    if (highControl) {
      return {
        recommendedMode,
        fallbackMode,
        summary: "这笔结算更适合高控制路径，建议优先走 Safe。",
        why: "当前金额、拆分数量或风险信号更适合先审批后提交，能把执行控制和审计记录保留得更完整。",
        reasons: ["高控制要求", "适合审批", "审计更清晰"],
      };
    }
    if (walletFriendly) {
      return {
        recommendedMode,
        fallbackMode,
        summary: "这笔结算适合由用户钱包签名，平台只负责生成待签数据。",
        why: "金额和风险都处于可接受范围，钱包签名既能保留用户控制权，也不会引入 Safe 审批等待。",
        reasons: ["保留用户控制权", "等待时间适中", "无需多签审批"],
      };
    }
    return {
      recommendedMode,
      fallbackMode,
      summary: "这笔结算适合平台直接代提交，路径最短。",
      why: "当前金额较小、风险信号稳定，也没有复杂拆分需求，平台代提交能更快看到 batch、tx hash 和链上结果。",
      reasons: ["执行路径最短", "适合快速结算", "链上结果更快可见"],
    };
  }

  if (missingFields.length > 0) {
    return {
      recommendedMode,
      fallbackMode,
      summary: "Clarify the missing details first, then lock the final settlement route.",
      why: "The most important action right now is not submission. Fill the recipient, amount, or currency first so the route recommendation stays reliable.",
      reasons: ["Missing fields", "Intent still unclear", "Do not submit yet"],
    };
  }
  if (riskDecision === "block") {
    return {
      recommendedMode,
      fallbackMode,
      summary: "This request is currently blocked. Pause the flow and resolve the risk issue first.",
      why: "When a blocking rule is triggered, switching modes will not change the outcome. The correct next step is to inspect the recipient, funding source, or transaction context.",
      reasons: ["Risk blocked", "Execution not started", "Manual review recommended"],
    };
  }
  if (highControl) {
    return {
      recommendedMode,
      fallbackMode,
      summary: "This settlement is better suited to a high-control route. Safe is the recommended path.",
      why: "The current amount, split count, or review signal makes an approval-first route safer and easier to audit.",
      reasons: ["Higher control needed", "Approval-first route", "Clearer audit trail"],
    };
  }
  if (walletFriendly) {
    return {
      recommendedMode,
      fallbackMode,
      summary: "This request fits a wallet-signing path. Let the platform prepare the unsigned payload.",
      why: "The amount and risk posture are still manageable, so wallet signing preserves user control without introducing Safe approval latency.",
      reasons: ["Preserve user control", "Moderate turnaround", "No multisig required"],
    };
  }
  return {
    recommendedMode,
    fallbackMode,
    summary: "This request is best handled by direct operator submission.",
    why: "The amount is small, the risk posture is stable, and there is no complex split requirement. Operator mode gets you to batch creation and onchain visibility fastest.",
    reasons: ["Fastest route", "Low-friction settlement", "Onchain result appears sooner"],
  };
}
