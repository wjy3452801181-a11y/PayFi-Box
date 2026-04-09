const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const ACTOR_ID_STORAGE_KEY = "payfi_actor_id";
const ACCESS_SESSION_STORAGE_KEY = "payfi_access_session";

function resolveApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return DEFAULT_API_BASE_URL;
}

export const API_BASE_URL = resolveApiBaseUrl();

export function rememberActorId(actorId: string | null | undefined) {
  if (typeof window === "undefined") return;
  const normalized = actorId?.trim();
  if (!normalized) {
    window.localStorage.removeItem(ACTOR_ID_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(ACTOR_ID_STORAGE_KEY, normalized);
}

export function getRememberedActorId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTOR_ID_STORAGE_KEY);
}

export type AccessSession = {
  user: {
    id: string;
    name: string;
    email: string;
    role: string;
    organization_id?: string | null;
  };
  access_token: string;
  expires_at: string;
};

export function rememberAccessSession(session: AccessSession | null | undefined) {
  if (typeof window === "undefined") return;
  if (!session) {
    window.localStorage.removeItem(ACCESS_SESSION_STORAGE_KEY);
    window.localStorage.removeItem(ACTOR_ID_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(ACCESS_SESSION_STORAGE_KEY, JSON.stringify(session));
  rememberActorId(session.user.id);
}

export function getRememberedAccessSession(): AccessSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(ACCESS_SESSION_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AccessSession;
    if (!parsed?.access_token || !parsed?.user?.id) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function getRememberedAccessToken(): string | null {
  return getRememberedAccessSession()?.access_token || null;
}

export function clearRememberedAccessSession() {
  rememberAccessSession(null);
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  timeoutMs?: number;
  actorId?: string | null;
  accessToken?: string | null;
};

type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? 45_000;
  const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  const actorId = options.actorId?.trim() || getRememberedActorId() || undefined;
  const accessToken = options.accessToken?.trim() || getRememberedAccessToken() || undefined;
  if (actorId) {
    rememberActorId(actorId);
  }
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`请求超时（>${Math.round(timeoutMs / 1000)}s），请重试。 (Request timed out; please retry.)`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutHandle);
  }

  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }

    const reason =
      payload?.detail || payload?.message || `HTTP ${response.status} ${response.statusText}`;
    throw new Error(reason);
  }

  return (await response.json()) as T;
}

export type CommandRequest = {
  user_id: string;
  session_id: string;
  text: string;
  channel?: string | null;
  locale?: string | null;
};

export type AccessSessionRequest = {
  email: string;
  access_code: string;
};

export type ConfirmRequest = {
  command_id: string;
  confirmed: boolean;
  execution_mode?: "operator" | "user_wallet" | "safe";
  idempotency_key?: string | null;
  locale?: string | null;
  note?: string | null;
};

export type CommandResponse = {
  status: "ok" | "needs_clarification";
  command_id: string;
  session_id: string;
  intent: "create_payment" | "query_payments" | "generate_report" | "unknown";
  confidence: number;
  preview: Record<string, unknown>;
  missing_fields: string[];
  follow_up_question?: string | null;
  risk?: {
    decision: "allow" | "review" | "block";
    risk_level: "low" | "medium" | "high";
    reason_codes: string[];
    user_message: string;
  } | null;
  quote?: {
    estimated_fee: number;
    route: string;
    eta_text: string;
    currency: string;
  } | null;
  next_action: string;
  message: string;
};

export type ConfirmResponse = {
  status: "ok" | "declined" | "blocked" | "validation_error" | "failed";
  command_id: string;
  execution_mode: "operator" | "user_wallet" | "safe";
  next_action: "completed" | "sign_in_wallet" | "approve_in_safe" | "none";
  payment_order_id?: string | null;
  execution_batch_id?: string | null;
  payment_status?: string | null;
  execution_status?: string | null;
  execution?: {
    mode: "mock" | "onchain";
    executed: boolean;
    transaction_ref?: string | null;
    network?: string | null;
    chain_id?: number | null;
    tx_hash?: string | null;
    explorer_url?: string | null;
    onchain_status?: string | null;
    message: string;
    split_executions?: Array<{
      sequence: number;
      amount: number;
      currency: string;
      status: string;
      tx_hash?: string | null;
      explorer_url?: string | null;
      onchain_status?: string | null;
    }> | null;
  } | null;
  splits: Array<{
    sequence: number;
    amount: number;
    currency: string;
    status: string;
    tx_hash?: string | null;
    explorer_url?: string | null;
    onchain_status?: string | null;
  }>;
  execution_items: Array<{
    execution_item_id: string;
    onchain_execution_item_id?: string | null;
    sequence: number;
    amount: number;
    currency: string;
    status: string;
    tx_hash?: string | null;
    explorer_url?: string | null;
    onchain_status?: string | null;
    failure_reason?: string | null;
  }>;
  unsigned_transactions?: Array<Record<string, unknown>> | null;
  safe_proposal?: Record<string, unknown> | null;
  risk?: {
    decision: string;
    risk_level: string;
    reason_codes: string[];
  } | null;
  audit_trace_id: string;
  message: string;
};

export type ExecutionItemActionResponse = {
  status: "ok" | "validation_error" | "pending" | "no_change";
  execution_item_id: string;
  execution_batch_id?: string | null;
  payment_order_id?: string | null;
  execution_mode?: string | null;
  item_status?: string | null;
  batch_status?: string | null;
  payment_status?: string | null;
  onchain_status?: string | null;
  tx_hash?: string | null;
  explorer_url?: string | null;
  next_action?: "sync_receipt" | "attach_tx" | "approve_in_safe" | "none";
  message: string;
};

export type ExecutionItemSummary = {
  id: string;
  onchain_execution_item_id?: string | null;
  payment_split_id?: string | null;
  execution_mode?: string | null;
  sequence: number;
  amount: number;
  currency: string;
  beneficiary_address: string;
  status: string;
  tx_hash?: string | null;
  explorer_url?: string | null;
  nonce?: number | null;
  submitted_at?: string | null;
  confirmed_at?: string | null;
  failure_reason?: string | null;
  onchain_status?: string | null;
  is_duplicate_rejected: boolean;
  duplicate_reason?: string | null;
  pending_action?: string | null;
  unsigned_tx_request?: Record<string, unknown> | null;
  safe_proposal_request?: Record<string, unknown> | null;
  safe_proposal_attachment?: Record<string, unknown> | null;
  tx_attachment?: Record<string, unknown> | null;
  decoded_events?: Array<Record<string, unknown>> | null;
  event_summary?: {
    event_count: number;
    latest_action?: string | null;
    latest_timestamp?: string | null;
  } | null;
};

export type TimelineItem = {
  timestamp: string;
  title: string;
  action: string;
  entity_type: string;
  entity_id: string;
  details?: Record<string, unknown> | null;
};

export type PaymentDetailResponse = {
  payment: {
    id: string;
    created_at: string;
    updated_at: string;
    user_id: string;
    organization_id?: string | null;
    beneficiary_id: string;
    source_command_id?: string | null;
    amount: number;
    currency: string;
    status: string;
    risk_level: string;
    execution_route?: string | null;
    execution_mode: string;
    onchain_status?: string | null;
    tx_hash?: string | null;
    explorer_url?: string | null;
    reference: string;
  };
  beneficiary?: {
    id?: string | null;
    name?: string | null;
    country?: string | null;
    risk_level?: string | null;
    is_blacklisted?: boolean | null;
    wallet_address?: string | null;
    bank_account_mock?: string | null;
  } | null;
  splits: Array<{
    id: string;
    sequence: number;
    amount: number;
    currency: string;
    status: string;
    tx_hash?: string | null;
    explorer_url?: string | null;
    onchain_status?: string | null;
  }>;
  execution_batch?: {
    id: string;
    execution_mode: string;
    idempotency_key: string;
    status: string;
    requested_by_user_id: string;
    total_items: number;
    confirmed_items: number;
    failed_items: number;
    submitted_items: number;
    started_at?: string | null;
    finished_at?: string | null;
    failure_reason?: string | null;
    created_at: string;
  } | null;
  execution_items: ExecutionItemSummary[];
  risk_checks: Array<{
    id: string;
    check_type: string;
    result: string;
    score?: number | null;
    reason_codes: string[];
    normalized_reason_codes: string[];
    created_at: string;
  }>;
  command?: {
    id: string;
    session_id: string;
    user_id: string;
    raw_text: string;
    intent?: string | null;
    final_status: string;
    trace_id: string;
    created_at: string;
  } | null;
  execution: {
    execution_route?: string | null;
    mode: string;
    executed: boolean;
    status: string;
    network?: string | null;
    chain_id?: number | null;
    tx_hash?: string | null;
    explorer_url?: string | null;
    onchain_status?: string | null;
    message?: string | null;
    split_executions?: Array<Record<string, unknown>> | null;
  };
  audit: {
    trace_id?: string | null;
    count: number;
    items: TimelineItem[];
  };
  timeline_summary?: {
    count: number;
    latest_action?: string | null;
    latest_timestamp?: string | null;
    has_duplicate_rejection: boolean;
    has_partial_failure: boolean;
    has_reconciliation: boolean;
  } | null;
};

export type PaymentsListResponse = {
  total: number;
  limit: number;
  items: Array<{
    id: string;
    payment_order_id: string;
    created_at: string;
    beneficiary_name?: string | null;
    beneficiary_country?: string | null;
    amount: number;
    currency: string;
    status: string;
    risk_level: string;
    split_count: number;
    reference: string;
    tx_hash?: string | null;
  }>;
};

export type CommandListResponse = {
  total: number;
  limit: number;
  items: Array<{
    command_id: string;
    created_at: string;
    user_id: string;
    session_id: string;
    raw_text: string;
    intent?: string | null;
    confidence?: number | null;
    final_status: string;
    trace_id: string;
    linked_payment_order_id?: string | null;
  }>;
};

export type CommandTimelineResponse = {
  command_id: string;
  trace_id: string;
  count: number;
  items: TimelineItem[];
};

export type BeneficiaryListResponse = {
  total: number;
  limit: number;
  items: Array<{
    beneficiary_id: string;
    name: string;
    country: string;
    risk_level: string;
    is_blacklisted: boolean;
    has_wallet_address?: boolean;
  }>;
};

export type BeneficiaryDetailResponse = {
  beneficiary: {
    beneficiary_id: string;
    name: string;
    country: string;
    risk_level: string;
    is_blacklisted: boolean;
    organization_id?: string | null;
    wallet_address?: string | null;
    bank_account_mock?: string | null;
    metadata_json?: Record<string, unknown> | null;
    created_at: string;
    updated_at: string;
  };
  stats: {
    total_payments: number;
    total_payment_volume: number;
    executed_payments: number;
    failed_payments: number;
    latest_payment_at?: string | null;
  };
  recent_payments: Array<{
    payment_order_id: string;
    created_at: string;
    amount: number;
    currency: string;
    status: string;
    risk_level: string;
    reference: string;
    source_command_id?: string | null;
  }>;
  risk_profile: {
    risk_level: string;
    is_blacklisted: boolean;
    reason_codes: string[];
    message: string;
  };
};

export type SettlementQuoteResponse = {
  status: "ok";
  quote: {
    id: string;
    merchant_id: string;
    beneficiary_id: string;
    source_currency: string;
    source_amount: number;
    target_currency: string;
    target_amount: number;
    target_network: string;
    fx_rate: number;
    platform_fee: number;
    network_fee: number;
    spread_bps: number;
    total_fee_amount: number;
    expires_at: string;
    status: string;
  };
  next_action: "create_fiat_payment_intent";
  message: string;
};

export type CreateFiatPaymentResponse = {
  status: "ok";
  fiat_payment: {
    id: string;
    merchant_id: string;
    beneficiary_id: string;
    quote_id: string;
    payer_currency: string;
    payer_amount: number;
    target_stablecoin: string;
    target_amount: number;
    target_network: string;
    status: string;
    payment_channel: string;
    channel_payment_id?: string | null;
    channel_checkout_session_id?: string | null;
    channel_checkout_url?: string | null;
    channel_status?: string | null;
    channel_confirmed_at?: string | null;
    webhook_received_at?: string | null;
    kyc_verification_id?: string | null;
    status_compat?: string | null;
    reference: string;
    bridge_state?: string | null;
    bridge_failure?: Record<string, unknown> | null;
  };
  quote: SettlementQuoteResponse["quote"];
  collection_instructions: {
    collection_method: string;
    note: string;
    expected_currency: string;
    expected_amount: number;
    reference: string;
  };
  next_action: "start_kyc" | "create_stripe_session" | "wait_channel_confirmation" | "mark_fiat_received";
  message: string;
};

export type StripeSessionResponse = {
  status: "ok" | "validation_error" | "failed";
  fiat_payment: CreateFiatPaymentResponse["fiat_payment"];
  quote: SettlementQuoteResponse["quote"];
  next_action: "complete_stripe_payment" | "complete_kyc" | "open_checkout" | "none";
  checkout?: {
    provider?: string;
    checkout_session_id?: string | null;
    checkout_url?: string | null;
    payment_intent_id?: string | null;
    expires_at?: number | string | null;
    channel_status?: string | null;
  } | null;
  message: string;
};

export type KycStartResponse = {
  status: "ok" | "validation_error" | "failed";
  verification?: {
    id: string;
    subject_type: string;
    subject_id: string;
    provider: string;
    provider_verification_session_id?: string | null;
    status: string;
    verification_url?: string | null;
    verified_at?: string | null;
    failure_reason?: string | null;
  } | null;
  next_action: "complete_kyc" | "none";
  message: string;
};

export type MarkFiatReceivedResponse = {
  status: "ok" | "validation_error" | "failed";
  fiat_payment: CreateFiatPaymentResponse["fiat_payment"];
  quote: SettlementQuoteResponse["quote"];
  fiat_collection?: {
    id: string;
    status: string;
    collection_method: string;
    bank_reference?: string | null;
    received_amount: number;
    currency: string;
    received_at?: string | null;
  } | null;
  payout_link?: {
    id: string;
    payment_order_id?: string | null;
    execution_batch_id?: string | null;
    status: string;
    bridge_state?: string | null;
    bridge_failure?: Record<string, unknown> | null;
  } | null;
  payout: {
    payment_order_id?: string | null;
    execution_batch_id?: string | null;
    payment_status?: string | null;
    execution_status?: string | null;
    onchain_status?: string | null;
    tx_hash?: string | null;
    explorer_url?: string | null;
    execution_mode?: string | null;
  };
  message: string;
};

export type MerchantFiatPaymentDetailResponse = {
  fiat_payment: CreateFiatPaymentResponse["fiat_payment"];
  quote: SettlementQuoteResponse["quote"];
  kyc_verification?: KycStartResponse["verification"] | null;
  fiat_collection?: MarkFiatReceivedResponse["fiat_collection"];
  payout_link?: MarkFiatReceivedResponse["payout_link"];
  payment_order?: PaymentDetailResponse["payment"] | null;
  execution_batch?: PaymentDetailResponse["execution_batch"] | null;
  execution_items: ExecutionItemSummary[];
  risk_checks: PaymentDetailResponse["risk_checks"];
  timeline: {
    count: number;
    items: TimelineItem[];
  };
};

export type BalanceAccountView = {
  id: string;
  user_id: string;
  currency: string;
  available_balance: number;
  locked_balance: number;
  status: string;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type BalanceLedgerEntryView = {
  id: string;
  account_id: string;
  entry_type: string;
  amount: number;
  balance_before: number;
  balance_after: number;
  reference_type?: string | null;
  reference_id?: string | null;
  description?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};

export type BalanceDepositOrderView = {
  id: string;
  user_id: string;
  source_currency: string;
  source_amount: number;
  target_currency: string;
  target_amount: number;
  fx_rate: number;
  fee_amount: number;
  payment_channel: string;
  channel_payment_id?: string | null;
  channel_checkout_session_id?: string | null;
  channel_checkout_url?: string | null;
  channel_status?: string | null;
  channel_confirmed_at?: string | null;
  webhook_received_at?: string | null;
  kyc_verification_id?: string | null;
  status: string;
  next_action?: string | null;
  reference: string;
  failure_reason?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type BalanceAccountResponse = {
  account: BalanceAccountView;
};

export type BalanceLedgerResponse = {
  account: BalanceAccountView;
  total: number;
  limit: number;
  items: BalanceLedgerEntryView[];
};

export type BalanceDepositResponse = {
  status: "ok";
  deposit_order: BalanceDepositOrderView;
  next_action: "complete_kyc" | "start_stripe_payment";
  message: string;
};

export type BalanceStartStripePaymentResponse = {
  status: "ok" | "validation_error" | "failed";
  deposit_order: BalanceDepositOrderView;
  next_action: "open_checkout" | "complete_kyc" | "wait_channel_confirmation" | "none";
  checkout?: {
    provider?: string;
    checkout_session_id?: string | null;
    checkout_url?: string | null;
    payment_intent_id?: string | null;
    channel_status?: string | null;
  } | null;
  message: string;
};

export type BalanceDepositDetailResponse = {
  deposit_order: BalanceDepositOrderView;
  account?: BalanceAccountView | null;
  latest_ledger_entry?: BalanceLedgerEntryView | null;
};

export type BalancePaymentPreviewResponse = CommandResponse & {
  funding_source: "platform_balance";
  balance_account?: BalanceAccountView | null;
  balance_check?: {
    currency: string;
    available_balance: number;
    locked_balance: number;
    required_amount?: number | null;
    sufficient: boolean;
    reason?: string | null;
  } | null;
};

export type BalancePaymentConfirmResponse = ConfirmResponse & {
  funding_source: "platform_balance";
  balance_account?: BalanceAccountView | null;
  balance_lock?: {
    id: string;
    account_id: string;
    command_id: string;
    payment_order_id?: string | null;
    currency: string;
    locked_amount: number;
    consumed_amount: number;
    released_amount: number;
    status: string;
    metadata_json?: Record<string, unknown> | null;
    created_at: string;
    updated_at: string;
  } | null;
};

export function postAccessSession(payload: AccessSessionRequest): Promise<AccessSession> {
  return requestJson("/api/auth/session", {
    method: "POST",
    body: payload,
    accessToken: null,
  });
}

export function postCommand(payload: CommandRequest): Promise<CommandResponse> {
  return requestJson("/api/command", { method: "POST", body: payload, actorId: payload.user_id });
}

export function postConfirm(payload: ConfirmRequest, actorId?: string | null): Promise<ConfirmResponse> {
  return requestJson("/api/confirm", {
    method: "POST",
    body: payload,
    actorId: actorId || null,
  });
}

export function postExecutionItemAttachTx(
  executionItemId: string,
  payload: {
    tx_hash: string;
    wallet_address?: string | null;
    submitted_at?: string | null;
    locale?: string | null;
  },
  actorId?: string | null,
): Promise<ExecutionItemActionResponse> {
  return requestJson(`/api/execution-items/${executionItemId}/attach-tx`, {
    method: "POST",
    body: payload,
    actorId,
  });
}

export function postExecutionItemAttachSafeProposal(
  executionItemId: string,
  payload: {
    safe_address?: string | null;
    proposal_id?: string | null;
    proposal_url?: string | null;
    proposer_wallet?: string | null;
    proposal_payload?: Record<string, unknown> | null;
    submitted_at?: string | null;
  },
  actorId?: string | null,
): Promise<ExecutionItemActionResponse> {
  return requestJson(`/api/execution-items/${executionItemId}/attach-safe-proposal`, {
    method: "POST",
    body: payload,
    actorId,
  });
}

export function postExecutionItemSyncReceipt(
  executionItemId: string,
  payload?: {
    force?: boolean;
  },
  actorId?: string | null,
): Promise<ExecutionItemActionResponse> {
  return requestJson(`/api/execution-items/${executionItemId}/sync-receipt`, {
    method: "POST",
    body: payload ?? {},
    actorId,
  });
}

export function getPayments(params?: {
  status?: string;
  risk_level?: string;
  beneficiary_name?: string;
  limit?: number;
}, actorId?: string | null): Promise<PaymentsListResponse> {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.risk_level) search.set("risk_level", params.risk_level);
  if (params?.beneficiary_name) search.set("beneficiary_name", params.beneficiary_name);
  if (params?.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return requestJson(`/api/payments${suffix}`, { actorId });
}

export function getPaymentDetail(paymentId: string, actorId?: string | null): Promise<PaymentDetailResponse> {
  return requestJson(`/api/payments/${paymentId}`, { actorId });
}

export function getCommands(params?: {
  limit?: number;
  intent?: string;
  final_status?: string;
}, actorId?: string | null): Promise<CommandListResponse> {
  const search = new URLSearchParams();
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.intent) search.set("intent", params.intent);
  if (params?.final_status) search.set("final_status", params.final_status);
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return requestJson(`/api/commands${suffix}`, { actorId });
}

export function getCommandTimeline(commandId: string, actorId?: string | null): Promise<CommandTimelineResponse> {
  return requestJson(`/api/commands/${commandId}/timeline`, { actorId });
}

export function getBeneficiaries(params?: {
  risk_level?: string;
  is_blacklisted?: boolean;
  name?: string;
  limit?: number;
}): Promise<BeneficiaryListResponse> {
  const search = new URLSearchParams();
  if (params?.risk_level) search.set("risk_level", params.risk_level);
  if (params?.is_blacklisted !== undefined) search.set("is_blacklisted", String(params.is_blacklisted));
  if (params?.name) search.set("name", params.name);
  if (params?.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return requestJson(`/api/beneficiaries${suffix}`);
}

export function getBeneficiaryDetail(beneficiaryId: string): Promise<BeneficiaryDetailResponse> {
  return requestJson(`/api/beneficiaries/${beneficiaryId}`);
}

export function postMerchantQuote(payload: {
  merchant_id: string;
  beneficiary_id: string;
  source_currency: string;
  source_amount: number;
  target_currency: string;
  target_network: string;
}): Promise<SettlementQuoteResponse> {
  return requestJson("/api/merchant/quote", { method: "POST", body: payload, actorId: payload.merchant_id });
}

export function postCreateFiatPayment(payload: {
  quote_id: string;
  merchant_id: string;
  beneficiary_id?: string | null;
  reference?: string | null;
  source_text?: string | null;
  split_count?: number | null;
}): Promise<CreateFiatPaymentResponse> {
  return requestJson("/api/merchant/fiat-payment", { method: "POST", body: payload, actorId: payload.merchant_id });
}

export function postMerchantKycStart(payload: {
  subject_type: "merchant" | "user";
  subject_id: string;
  provider?: "stripe_identity";
  locale?: string | null;
  force_new?: boolean;
}): Promise<KycStartResponse> {
  return requestJson("/api/kyc/start", { method: "POST", body: payload, actorId: payload.subject_id });
}

export function getKycVerification(kycVerificationId: string, actorId?: string | null): Promise<KycStartResponse> {
  return requestJson(`/api/kyc/${kycVerificationId}`, { actorId });
}

export function postCreateStripeSession(
  fiatPaymentIntentId: string,
  payload?: {
    success_url?: string | null;
    cancel_url?: string | null;
    locale?: string | null;
  },
  actorId?: string | null,
): Promise<StripeSessionResponse> {
  return requestJson(`/api/merchant/fiat-payment/${fiatPaymentIntentId}/create-stripe-session`, {
    method: "POST",
    body: payload ?? {},
    actorId,
  });
}

export function postStartStripePayment(
  fiatPaymentIntentId: string,
  payload?: {
    success_url?: string | null;
    cancel_url?: string | null;
    locale?: string | null;
  },
  actorId?: string | null,
): Promise<StripeSessionResponse> {
  return requestJson(`/api/merchant/fiat-payment/${fiatPaymentIntentId}/start-stripe-payment`, {
    method: "POST",
    body: payload ?? {},
    actorId,
  });
}

export function postSyncStripePayment(
  fiatPaymentIntentId: string,
  actorId?: string | null,
): Promise<MerchantFiatPaymentDetailResponse> {
  return requestJson(`/api/merchant/fiat-payment/${fiatPaymentIntentId}/sync-stripe-payment`, {
    method: "POST",
    body: {},
    actorId,
  });
}

export function postMarkFiatReceived(
  fiatPaymentIntentId: string,
  payload: {
    collection_method?: string;
    bank_reference?: string | null;
    received_amount?: number | null;
    currency?: string | null;
    execution_mode?: "operator" | "user_wallet" | "safe" | null;
    idempotency_key?: string | null;
    note?: string | null;
    demo_admin_override?: boolean;
  },
  actorId?: string | null,
): Promise<MarkFiatReceivedResponse> {
  return requestJson(`/api/merchant/fiat-payment/${fiatPaymentIntentId}/mark-received`, {
    method: "POST",
    body: payload,
    actorId,
  });
}

export function getMerchantFiatPaymentDetail(
  fiatPaymentIntentId: string,
  actorId?: string | null,
): Promise<MerchantFiatPaymentDetailResponse> {
  return requestJson(`/api/merchant/fiat-payment/${fiatPaymentIntentId}`, { actorId });
}

export function getBalanceAccount(userId: string, currency = "USDT"): Promise<BalanceAccountResponse> {
  const search = new URLSearchParams({ currency });
  return requestJson(`/api/balance/accounts/${userId}?${search.toString()}`, { actorId: userId });
}

export function getBalanceLedger(
  userId: string,
  params?: { currency?: string; limit?: number },
): Promise<BalanceLedgerResponse> {
  const search = new URLSearchParams();
  if (params?.currency) search.set("currency", params.currency);
  if (params?.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return requestJson(`/api/balance/accounts/${userId}/ledger${suffix}`, { actorId: userId });
}

export function postCreateBalanceDeposit(payload: {
  user_id: string;
  source_currency: string;
  source_amount: number;
  target_currency: string;
  reference?: string | null;
}): Promise<BalanceDepositResponse> {
  return requestJson("/api/balance/deposits", { method: "POST", body: payload, actorId: payload.user_id });
}

export function getBalanceDepositDetail(
  depositOrderId: string,
  actorId?: string | null,
): Promise<BalanceDepositDetailResponse> {
  return requestJson(`/api/balance/deposits/${depositOrderId}`, { actorId });
}

export function postStartBalanceDepositStripePayment(
  depositOrderId: string,
  payload?: {
    success_url?: string | null;
    cancel_url?: string | null;
    locale?: string | null;
  },
  actorId?: string | null,
): Promise<BalanceStartStripePaymentResponse> {
  return requestJson(`/api/balance/deposits/${depositOrderId}/start-stripe-payment`, {
    method: "POST",
    body: payload ?? {},
    actorId,
  });
}

export function postSyncBalanceDepositStripePayment(
  depositOrderId: string,
  actorId?: string | null,
): Promise<BalanceDepositDetailResponse> {
  return requestJson(`/api/balance/deposits/${depositOrderId}/sync-stripe-payment`, {
    method: "POST",
    body: {},
    actorId,
  });
}

export function postBalancePaymentPreview(payload: {
  user_id: string;
  prompt: string;
  execution_mode?: "operator" | "user_wallet" | "safe" | null;
  locale?: string | null;
}): Promise<BalancePaymentPreviewResponse> {
  return requestJson("/api/balance/payments/preview", {
    method: "POST",
    body: payload,
    actorId: payload.user_id,
  });
}

export function postBalancePaymentConfirm(payload: {
  user_id: string;
  command_id: string;
  execution_mode?: "operator" | "user_wallet" | "safe" | null;
  idempotency_key?: string | null;
  locale?: string | null;
  note?: string | null;
}): Promise<BalancePaymentConfirmResponse> {
  return requestJson("/api/balance/payments/confirm", {
    method: "POST",
    body: payload,
    actorId: payload.user_id,
  });
}
