export const USER_ROLES = [
  "retail",
  "trade_company",
  "financial_institution",
] as const;
export type UserRole = (typeof USER_ROLES)[number];

export const ORGANIZATION_TYPES = [
  "trade_company",
  "financial_institution",
] as const;
export type OrganizationType = (typeof ORGANIZATION_TYPES)[number];

export const PAYMENT_ORDER_STATUSES = [
  "draft",
  "quoted",
  "pending_confirmation",
  "approved",
  "partially_executed",
  "executed",
  "failed",
  "cancelled",
] as const;
export type PaymentOrderStatus = (typeof PAYMENT_ORDER_STATUSES)[number];

export const PAYMENT_SPLIT_STATUSES = [
  "draft",
  "scheduled",
  "executed",
  "failed",
  "cancelled",
] as const;
export type PaymentSplitStatus = (typeof PAYMENT_SPLIT_STATUSES)[number];

export const RISK_LEVELS = ["low", "medium", "high"] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

export const RISK_CHECK_RESULTS = ["allow", "review", "block"] as const;
export type RiskCheckResult = (typeof RISK_CHECK_RESULTS)[number];

export const RISK_REASON_CODES = [
  "BLACKLISTED_BENEFICIARY",
  "HIGH_RISK_BENEFICIARY",
  "MEDIUM_RISK_BENEFICIARY",
  "UNRESOLVED_BENEFICIARY",
  "HIGH_AMOUNT",
  "CROSS_BORDER",
  "SPLIT_PAYMENT",
  "MISSING_REFERENCE_FOR_TRADE_PAYMENT",
  "PASS_BASELINE_POLICY",
] as const;
export type RiskReasonCode = (typeof RISK_REASON_CODES)[number];

export const EXECUTION_MODES = ["mock", "simulated", "onchain"] as const;
export type ExecutionMode = (typeof EXECUTION_MODES)[number];
export const EXECUTION_ROUTES = ["operator", "user_wallet", "safe"] as const;
export type ExecutionRoute = (typeof EXECUTION_ROUTES)[number];

export const ONCHAIN_EXECUTION_STATUSES = [
  "pending_submission",
  "submitted_onchain",
  "partially_confirmed_onchain",
  "confirmed_onchain",
  "failed_onchain",
  "blocked",
] as const;
export type OnchainExecutionStatus = (typeof ONCHAIN_EXECUTION_STATUSES)[number];

export const EXECUTION_BATCH_STATUSES = [
  "planned",
  "in_progress",
  "partially_confirmed",
  "confirmed",
  "failed",
  "cancelled",
] as const;
export type ExecutionBatchStatus = (typeof EXECUTION_BATCH_STATUSES)[number];

export const EXECUTION_ITEM_STATUSES = [
  "planned",
  "submitting",
  "submitted",
  "confirmed",
  "failed",
] as const;
export type ExecutionItemStatus = (typeof EXECUTION_ITEM_STATUSES)[number];

export const COMMAND_EXECUTION_STATUSES = [
  "received",
  "parsed",
  "ready",
  "confirmed",
  "declined",
  "blocked",
  "executed",
  "completed",
  "failed",
] as const;
export type CommandExecutionStatus = (typeof COMMAND_EXECUTION_STATUSES)[number];

export const REPORT_JOB_STATUSES = [
  "pending",
  "running",
  "completed",
  "failed",
] as const;
export type ReportJobStatus = (typeof REPORT_JOB_STATUSES)[number];

export const SESSION_STATUSES = ["active", "closed", "abandoned"] as const;
export type SessionStatus = (typeof SESSION_STATUSES)[number];

export interface PaymentIntent {
  id: string;
  sourceText: string;
  userRole: UserRole;
  organizationType?: OrganizationType;
  beneficiaryName?: string;
  amount?: string;
  currency?: string;
  riskLevel: RiskLevel;
  expectedStatus: PaymentOrderStatus;
}

export interface PaymentOrderPreview {
  id: string;
  amount: string;
  currency: string;
  status: PaymentOrderStatus;
  riskLevel: RiskLevel;
  executionRoute: ExecutionRoute;
  executionMode: ExecutionMode;
  requiresConfirmation: boolean;
}

export interface CommandExecutionPreview {
  id: string;
  rawText: string;
  status: CommandExecutionStatus;
  traceId: string;
}

export type RoleCardDefinition = {
  role: UserRole;
  title: string;
  subtitle: string;
  description: string;
  bullets: string[];
};

export const ROLE_CARDS: RoleCardDefinition[] = [
  {
    role: "retail",
    title: "Retail",
    subtitle: "Natural-language payment",
    description:
      "A consumer-facing flow for turning plain-language payment requests into structured actions.",
    bullets: [
      "Intent capture from free-form text",
      "Merchant and amount confirmation",
      "Explainable approval before execution",
    ],
  },
  {
    role: "trade_company",
    title: "Trade Company",
    subtitle: "Cross-border operations",
    description:
      "A business workflow for invoice-linked payments, compliance checks, and cross-border handoffs.",
    bullets: [
      "Invoice and trade-order context",
      "Beneficiary and corridor review",
      "Payment state tracking for operations teams",
    ],
  },
  {
    role: "financial_institution",
    title: "Financial Institution",
    subtitle: "Reporting and oversight",
    description:
      "An institution-facing control layer for risk review, reporting, and transparent audit trails.",
    bullets: [
      "Case review queues for analysts",
      "Structured reporting outputs",
      "Decision and audit trace placeholders",
    ],
  },
];
