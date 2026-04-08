import type {
  CreateFiatPaymentResponse,
  KycStartResponse,
  MarkFiatReceivedResponse,
  MerchantFiatPaymentDetailResponse,
  SettlementQuoteResponse,
  StripeSessionResponse,
} from "./api";

function containsAny(input: string, keywords: string[]): boolean {
  return keywords.some((keyword) => input.includes(keyword));
}

export type MerchantDerivedState = {
  quote: SettlementQuoteResponse["quote"] | MarkFiatReceivedResponse["quote"] | CreateFiatPaymentResponse["quote"] | MerchantFiatPaymentDetailResponse["quote"] | null;
  fiatPayment: MarkFiatReceivedResponse["fiat_payment"] | MerchantFiatPaymentDetailResponse["fiat_payment"] | CreateFiatPaymentResponse["fiat_payment"] | null;
  kycVerification: MerchantFiatPaymentDetailResponse["kyc_verification"] | KycStartResponse["verification"] | null;
  stripeCheckout: StripeSessionResponse["checkout"] | null;
  checkoutUrl: string | null;
  payoutLink: MarkFiatReceivedResponse["payout_link"] | MerchantFiatPaymentDetailResponse["payout_link"] | null;
  payout: MarkFiatReceivedResponse["payout"] | null;
  paymentOrder: MerchantFiatPaymentDetailResponse["payment_order"] | null;
  executionBatch: MerchantFiatPaymentDetailResponse["execution_batch"] | null;
  paymentOrderId: string | null;
  executionBatchId: string | null;
  payoutStatus: string | null;
  onchainStatus: string | null;
  txHash: string | null;
  explorerUrl: string | null;
  isBlocked: boolean;
  noOnchainPayoutCreated: boolean;
  fiatConfirmed: boolean;
  kycVerified: boolean;
  stripeConfirmed: boolean;
  payoutCompleted: boolean;
  settlementStatus: string;
  isStripeChannel: boolean;
  needsKycAction: boolean;
  needsStripeSessionAction: boolean;
  awaitingStripePayment: boolean;
  needsManualMarkReceivedAction: boolean;
  canUseStripeDemoOverride: boolean;
  hasStripeSessionSignals: boolean;
  stripeSessionFailed: boolean;
  stripeCardKycStatus: "awaiting" | "completed" | "blocked";
  stripeCardNextAction: "complete_kyc" | "open_checkout" | "none";
  stripeSessionId: string | undefined;
  stripePaymentIntentId: string | undefined;
};

export function deriveMerchantState(input: {
  quoteResult: SettlementQuoteResponse | null;
  fiatIntentResult: CreateFiatPaymentResponse | null;
  kycResult: KycStartResponse | null;
  stripeSessionResult: StripeSessionResponse | null;
  markReceivedResult: MarkFiatReceivedResponse | null;
  detailResult: MerchantFiatPaymentDetailResponse | null;
}): MerchantDerivedState {
  const quote =
    input.quoteResult?.quote ||
    input.markReceivedResult?.quote ||
    input.fiatIntentResult?.quote ||
    input.detailResult?.quote ||
    null;

  const fiatPayment =
    input.markReceivedResult?.fiat_payment ||
    input.detailResult?.fiat_payment ||
    input.fiatIntentResult?.fiat_payment ||
    null;

  const kycVerification = input.detailResult?.kyc_verification || input.kycResult?.verification || null;
  const stripeCheckout = input.stripeSessionResult?.checkout || null;
  const checkoutUrl = stripeCheckout?.checkout_url || fiatPayment?.channel_checkout_url || null;

  const payoutLink = input.markReceivedResult?.payout_link || input.detailResult?.payout_link || null;
  const payout = input.markReceivedResult?.payout || null;
  const paymentOrder = input.detailResult?.payment_order || null;
  const executionBatch = input.detailResult?.execution_batch || null;

  const paymentOrderId = payout?.payment_order_id || payoutLink?.payment_order_id || paymentOrder?.id || null;
  const executionBatchId = payout?.execution_batch_id || payoutLink?.execution_batch_id || executionBatch?.id || null;
  const payoutStatus = payout?.payment_status || paymentOrder?.status || payoutLink?.status || null;
  const onchainStatus = payout?.onchain_status || paymentOrder?.onchain_status || null;
  const txHash =
    payout?.tx_hash ||
    paymentOrder?.tx_hash ||
    input.detailResult?.execution_items.find((item) => item.tx_hash)?.tx_hash ||
    null;
  const explorerUrl =
    payout?.explorer_url ||
    paymentOrder?.explorer_url ||
    input.detailResult?.execution_items.find((item) => item.explorer_url)?.explorer_url ||
    null;

  const normalizedFlags = [
    payoutStatus,
    onchainStatus,
    payoutLink?.status,
    fiatPayment?.bridge_state,
    input.markReceivedResult?.status,
  ]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase());

  const isBlocked = normalizedFlags.some((value) => value.includes("block"));
  const noOnchainPayoutCreated = isBlocked && !txHash;

  const fiatConfirmed = (() => {
    const status = fiatPayment?.status?.toLowerCase();
    if (!status) return false;
    return [
      "fiat_received",
      "payout_in_progress",
      "completed",
      "bridge_failed_recoverable",
      "failed",
      "blocked",
      "executed",
      "partially_executed",
    ].includes(status);
  })();

  const kycVerified = (kycVerification?.status || "").toLowerCase() === "verified";

  const stripeConfirmed = containsAny((fiatPayment?.channel_status || "").toLowerCase(), [
    "payment_succeeded",
    "payment_confirmed",
  ]);

  const payoutCompleted =
    Boolean(txHash) &&
    containsAny(`${(payoutStatus || "").toLowerCase()} ${(onchainStatus || "").toLowerCase()}`, [
      "executed",
      "completed",
      "confirmed_onchain",
      "confirmed",
    ]);

  const settlementStatus = payoutStatus || fiatPayment?.status || quote?.status || "pending";
  const isStripeChannel = fiatPayment?.payment_channel === "stripe";
  const needsKycAction = Boolean(fiatPayment) && isStripeChannel && !kycVerified;
  const needsStripeSessionAction = Boolean(fiatPayment) && isStripeChannel && kycVerified && !checkoutUrl && !fiatConfirmed;
  const awaitingStripePayment = Boolean(fiatPayment) && isStripeChannel && Boolean(checkoutUrl) && !fiatConfirmed;
  const needsManualMarkReceivedAction = Boolean(input.fiatIntentResult) && !isStripeChannel && !fiatConfirmed;
  const canUseStripeDemoOverride = Boolean(fiatPayment) && isStripeChannel && !fiatConfirmed && !isBlocked;
  const hasStripeSessionSignals =
    Boolean(input.stripeSessionResult) ||
    Boolean(checkoutUrl) ||
    Boolean(fiatPayment?.channel_checkout_session_id);
  const stripeSessionFailed = input.stripeSessionResult?.status === "failed" && !checkoutUrl;

  const stripeCardKycStatus: "awaiting" | "completed" | "blocked" = (() => {
    if (kycVerified) return "completed";
    const raw = (kycVerification?.status || "").toLowerCase();
    if (containsAny(raw, ["failed", "expired", "blocked", "requires_review"])) return "blocked";
    return "awaiting";
  })();

  const stripeCardNextAction: "complete_kyc" | "open_checkout" | "none" = (() => {
    if (needsKycAction) return "complete_kyc";
    if (checkoutUrl && !fiatConfirmed) return "open_checkout";
    return "none";
  })();

  const stripeSessionId =
    input.stripeSessionResult?.checkout?.checkout_session_id ||
    fiatPayment?.channel_checkout_session_id ||
    undefined;
  const stripePaymentIntentId =
    input.stripeSessionResult?.checkout?.payment_intent_id ||
    fiatPayment?.channel_payment_id ||
    undefined;

  return {
    quote,
    fiatPayment,
    kycVerification,
    stripeCheckout,
    checkoutUrl,
    payoutLink,
    payout,
    paymentOrder,
    executionBatch,
    paymentOrderId,
    executionBatchId,
    payoutStatus,
    onchainStatus,
    txHash,
    explorerUrl,
    isBlocked,
    noOnchainPayoutCreated,
    fiatConfirmed,
    kycVerified,
    stripeConfirmed,
    payoutCompleted,
    settlementStatus,
    isStripeChannel,
    needsKycAction,
    needsStripeSessionAction,
    awaitingStripePayment,
    needsManualMarkReceivedAction,
    canUseStripeDemoOverride,
    hasStripeSessionSignals,
    stripeSessionFailed,
    stripeCardKycStatus,
    stripeCardNextAction,
    stripeSessionId,
    stripePaymentIntentId,
  };
}
