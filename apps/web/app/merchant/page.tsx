"use client";

import dynamic from "next/dynamic";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  type CreateFiatPaymentResponse,
  type KycStartResponse,
  type MarkFiatReceivedResponse,
  type MerchantFiatPaymentDetailResponse,
  type SettlementQuoteResponse,
  type StripeSessionResponse,
  type TimelineItem,
  getKycVerification,
  getMerchantFiatPaymentDetail,
  postStartStripePayment,
  postCreateFiatPayment,
  postMerchantKycStart,
  postExecutionItemAttachSafeProposal,
  postExecutionItemAttachTx,
  postExecutionItemSyncReceipt,
  postMarkFiatReceived,
  postMerchantQuote,
  postSyncStripePayment,
} from "../../lib/api";
import { formatAmount, formatTime } from "../../lib/format";
import { useI18n } from "../../lib/i18n-provider";
import { deriveMerchantState } from "../../lib/merchant-flow";
import { useRecipientDirectory } from "../../lib/use-recipient-directory";
import {
  formatRecipientLabel,
} from "../../lib/recipient-book";
import { DeferredPanelShell } from "../../components/deferred-panel-shell";
import { RecipientSelector } from "../../components/recipient-selector";
import { EmptyStateCard } from "../../components/empty-state-card";
import { StatusBadge } from "../../components/status-badge";
import { StripeNextStepCard } from "../../components/stripe-next-step-card";
import { QuoteCard } from "../../components/merchant/quote-card";
import { FiatIntentCard } from "../../components/merchant/fiat-intent-card";
import { PayoutResultCard } from "../../components/merchant/payout-result-card";
const ExecutionItemTable = dynamic(
  () => import("../../components/execution-item-table").then((mod) => mod.ExecutionItemTable),
  { loading: () => <DeferredPanelShell /> },
);
const TimelineView = dynamic(
  () => import("../../components/timeline-view").then((mod) => mod.TimelineView),
  { loading: () => <DeferredPanelShell /> },
);
const ExecutionAttachPanel = dynamic(
  () => import("../../components/execution-attach-panel").then((mod) => mod.ExecutionAttachPanel),
  { loading: () => <DeferredPanelShell /> },
);
const TechnicalDetailsAccordion = dynamic(
  () =>
    import("../../components/merchant/technical-details-accordion").then(
      (mod) => mod.TechnicalDetailsAccordion,
    ),
  { loading: () => <DeferredPanelShell /> },
);

type ExecutionMode = "operator" | "user_wallet" | "safe";

type FlowStep = {
  key: string;
  title: string;
  description: string;
  done: boolean;
  active: boolean;
};

type MerchantCopilot = {
  title: string;
  summary: string;
  nextStep: string;
  detail: string;
  chips: string[];
  status: string;
};
const LAST_FIAT_PAYMENT_ID_KEY = "payfi_last_fiat_payment_id";

function containsAny(input: string, keywords: string[]): boolean {
  return keywords.some((keyword) => input.includes(keyword));
}

function getMerchantCopilot(input: {
  lang: "zh" | "en";
  quoteReady: boolean;
  fiatPaymentReady: boolean;
  needsKycAction: boolean;
  needsStripeSessionAction: boolean;
  awaitingStripePayment: boolean;
  needsManualMarkReceivedAction: boolean;
  fiatConfirmed: boolean;
  payoutCompleted: boolean;
  isBlocked: boolean;
  noOnchainPayoutCreated: boolean;
  paymentOrderId: string | null;
  executionBatchId: string | null;
  txHash: string | null;
  executionMode: ExecutionMode;
}): MerchantCopilot {
  const chips = [
    input.paymentOrderId ? `payment_order` : null,
    input.executionBatchId ? `execution_batch` : null,
    input.txHash ? `tx_hash` : null,
    input.executionMode,
  ].filter(Boolean) as string[];

  if (input.lang === "zh") {
    if (!input.quoteReady) {
      return {
        title: "AI 结算副驾驶",
        summary: "当前还没有生成结算报价，系统还无法判断商户支付多少、收款方实际到账多少。",
        nextStep: "先生成结算报价，锁定法币金额、稳定币到账金额和费用结构。",
        detail: "这是整条结算流程的起点。没有 quote，后面的 fiat intent、KYC、Stripe 收款和链上出金都不会建立。",
        chips,
        status: "pending",
      };
    }
    if (!input.fiatPaymentReady) {
      return {
        title: "AI 结算副驾驶",
        summary: "报价已经就绪，但还没有创建结算意图，所以这笔资金流还没有被系统正式登记。",
        nextStep: "创建结算意图，把这笔交易推进到可收法币、可追踪、可关联 payout 的状态。",
        detail: "一旦 intent 创建成功，系统会开始记录支付通道状态、后续 KYC、收款和 payout 桥接对象。",
        chips,
        status: "pending",
      };
    }
    if (input.needsKycAction) {
      return {
        title: "AI 结算副驾驶",
        summary: "当前阻塞点是身份核验。没有完成 KYC，Stripe 收款会话不会被创建。",
        nextStep: "先完成身份核验，验证通过后再打开 Stripe 收款页。",
        detail: "这是接入门槛，不是可跳过的前端步骤。KYC 通过后，平台才会允许法币进入稳定币结算主线。",
        chips,
        status: "blocked_kyc_required",
      };
    }
    if (input.needsStripeSessionAction) {
      return {
        title: "AI 结算副驾驶",
        summary: "身份核验已完成，下一步是创建 Stripe 收款会话，让商户实际完成法币支付。",
        nextStep: "打开 Stripe 收款页，完成法币支付后系统会回到当前结算单继续推进。",
        detail: "这一阶段会生成 checkout session、payment intent 和对应的支付通道状态。",
        chips,
        status: "awaiting_channel_payment",
      };
    }
    if (input.awaitingStripePayment) {
      return {
        title: "AI 结算副驾驶",
        summary: "收款页已经生成，当前在等待 Stripe 或同步接口确认法币已实际到账。",
        nextStep: "如果商户已经支付，优先检查最新状态；不要手工假定到账。",
        detail: "只有 provider-confirmed 状态才能推进到 stablecoin payout，前端按钮本身不会把这笔法币直接标记为已收款。",
        chips,
        status: "payment_processing",
      };
    }
    if (input.needsManualMarkReceivedAction) {
      return {
        title: "AI 结算副驾驶",
        summary: "这是一条非 Stripe 的人工兜底路径，当前等待明确确认法币到账后，才会触发链上稳定币出金。",
        nextStep: "确认到账并进入结算，让系统创建 payment order、execution batch 和 execution items。",
        detail: "这一模式仅保留给管理员兜底场景。正常 Stripe 流程不会依赖前端手工声明到账。",
        chips,
        status: "fiat_received",
      };
    }
    if (input.isBlocked) {
      return {
        title: "AI 结算副驾驶",
        summary: "当前结算已被策略阻断，链上出金没有继续创建。",
        nextStep: input.noOnchainPayoutCreated
          ? "先解释风险原因，再决定是否需要更换收款方或重建整笔结算。"
          : "先检查已生成的对象，再决定是否需要人工干预。",
        detail: input.noOnchainPayoutCreated
          ? "系统明确保留了真实状态：这笔交易被拦截，且没有创建链上出金。"
          : "系统保留了已生成对象与阻断结果，方便继续核查。",
        chips,
        status: "blocked",
      };
    }
    if (input.payoutCompleted) {
      return {
        title: "AI 结算副驾驶",
        summary: "法币收款、桥接对象创建和链上稳定币结算都已经完成。",
        nextStep: "现在最适合打开结算详情，核查 payment order、execution batch 和链上 tx。",
        detail: "这一步最适合核查平台如何把法币收款转成可审计的稳定币执行轨迹。",
        chips,
        status: "completed",
      };
    }
    if (input.fiatConfirmed) {
      return {
        title: "AI 结算副驾驶",
        summary: "法币已经确认到账，当前正在把这笔资金桥接到稳定币执行引擎。",
        nextStep: "继续观察 payout 进度，必要时查看 execution items 或同步回执。",
        detail: "此时平台通常已经开始创建 payment order、execution batch，接下来重点看链上执行结果。",
        chips,
        status: "payout_in_progress",
      };
    }
    return {
      title: "AI 结算副驾驶",
      summary: "当前结算还在准备阶段，但流程对象已经开始建立。",
      nextStep: "继续按当前高亮步骤推进，系统会保持 quote、收款、payout 三层状态同步。",
      detail: "这是一个多阶段结算工作台，重点不是只看成功，而是每一步都能解释为什么要继续或暂停。",
      chips,
      status: "pending",
    };
  }

  if (!input.quoteReady) {
    return {
      title: "AI Settlement Copilot",
      summary: "No settlement quote exists yet, so the system cannot lock the merchant pay amount, recipient proceeds, or fee shape.",
      nextStep: "Generate the quote first so the fiat amount, stablecoin proceeds, and fee structure are anchored.",
      detail: "This is the start of the settlement path. Without a quote, the fiat intent, KYC, Stripe collection, and payout bridge cannot be created.",
      chips,
      status: "pending",
    };
  }
  if (!input.fiatPaymentReady) {
    return {
      title: "AI Settlement Copilot",
      summary: "The quote is ready, but no settlement intent exists yet, so this flow is not formally registered in the system.",
      nextStep: "Create the settlement intent to move the flow into a payable, trackable, payout-linked state.",
      detail: "Once the intent exists, the system will track payment channel state, KYC progression, fiat receipt, and payout bridge objects.",
      chips,
      status: "pending",
    };
  }
  if (input.needsKycAction) {
    return {
      title: "AI Settlement Copilot",
      summary: "Identity verification is the current blocker. Until KYC is completed, Stripe checkout cannot be created.",
      nextStep: "Complete identity verification first, then open Stripe checkout.",
      detail: "This is a hard eligibility gate, not an optional frontend step. KYC must pass before fiat can enter the stablecoin settlement path.",
      chips,
      status: "blocked_kyc_required",
    };
  }
  if (input.needsStripeSessionAction) {
    return {
      title: "AI Settlement Copilot",
      summary: "Identity verification is complete. The next action is to create a Stripe checkout session so the merchant can actually pay fiat.",
      nextStep: "Open Stripe checkout and let the merchant complete payment before returning to this settlement.",
      detail: "This stage creates the checkout session, payment intent, and the provider-side payment state used by the settlement flow.",
      chips,
      status: "awaiting_channel_payment",
    };
  }
  if (input.awaitingStripePayment) {
    return {
      title: "AI Settlement Copilot",
      summary: "Checkout is ready. The flow is now waiting for provider-confirmed fiat receipt through Stripe or an explicit status sync.",
      nextStep: "If payment has already been made, check the latest status instead of manually assuming funds arrived.",
      detail: "Only provider-confirmed status can advance this flow into stablecoin payout. A frontend click alone should not mark fiat as received.",
      chips,
      status: "payment_processing",
    };
  }
  if (input.needsManualMarkReceivedAction) {
    return {
      title: "AI Settlement Copilot",
      summary: "This is a non-Stripe manual fallback path. The flow is waiting for an explicit fiat-received step before stablecoin payout can begin.",
      nextStep: "Confirm fiat receipt and move the settlement into payout creation.",
      detail: "This manual path is reserved for administrative fallback. The normal Stripe path should rely on provider-confirmed receipt instead.",
      chips,
      status: "fiat_received",
    };
  }
  if (input.isBlocked) {
    return {
      title: "AI Settlement Copilot",
      summary: "This settlement has been blocked by policy, and onchain payout has not continued.",
      nextStep: input.noOnchainPayoutCreated
        ? "Explain the risk outcome first, then decide whether the recipient or the whole settlement should be rebuilt."
        : "Inspect the objects that already exist before deciding whether operator intervention is required.",
      detail: input.noOnchainPayoutCreated
        ? "The system is preserving truthful state here: settlement blocked, no onchain payout created."
        : "The system is preserving both the created artifacts and the blocked outcome for review.",
      chips,
      status: "blocked",
    };
  }
  if (input.payoutCompleted) {
    return {
      title: "AI Settlement Copilot",
      summary: "Fiat collection, bridge creation, and onchain stablecoin settlement are complete.",
      nextStep: "View settlement detail next and inspect the payment order, execution batch, and onchain transaction.",
      detail: "This is the clearest point to inspect how platform-side fiat collection becomes an auditable stablecoin payout trail.",
      chips,
      status: "completed",
    };
  }
  if (input.fiatConfirmed) {
    return {
      title: "AI Settlement Copilot",
      summary: "Fiat receipt is already confirmed. The system is now bridging this flow into the stablecoin execution engine.",
      nextStep: "Keep monitoring payout progress and inspect execution items or receipts if anything slows down.",
      detail: "At this stage the platform typically begins creating the payment order and execution batch, so the next signal to watch is onchain execution.",
      chips,
      status: "payout_in_progress",
    };
  }
  return {
    title: "AI Settlement Copilot",
    summary: "The settlement is still in preparation, but the core objects are beginning to line up.",
    nextStep: "Follow the highlighted step and keep the quote, collection, and payout layers in sync.",
    detail: "This workspace is meant to explain not just whether settlement succeeded, but why the flow should continue or pause at each stage.",
    chips,
    status: "pending",
  };
}

export default function MerchantSettlementPage() {
  const { t, statusLabel, lang } = useI18n();
  const [merchantId, setMerchantId] = useState("deaa3ed3-c910-53d0-8796-755d9c82add6");
  const [sourceCurrency, setSourceCurrency] = useState("USD");
  const [sourceAmount, setSourceAmount] = useState("500");
  const [targetCurrency, setTargetCurrency] = useState("USDT");
  const [targetNetwork, setTargetNetwork] = useState("hashkey_testnet");
  const [reference, setReference] = useState("MERCHANT-SETTLEMENT-001");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("operator");
  const [bankReference, setBankReference] = useState("FIAT-RECV-001");
  const [fiatPaymentIdInput, setFiatPaymentIdInput] = useState("");

  const {
    recipients: recipientOptions,
    selectedRecipientId,
    setSelectedRecipientId,
    selectedRecipient,
    addRecipient,
  } = useRecipientDirectory(30);
  const [quoteResult, setQuoteResult] = useState<SettlementQuoteResponse | null>(null);
  const [fiatIntentResult, setFiatIntentResult] = useState<CreateFiatPaymentResponse | null>(null);
  const [kycResult, setKycResult] = useState<KycStartResponse | null>(null);
  const [stripeSessionResult, setStripeSessionResult] = useState<StripeSessionResponse | null>(null);
  const [markReceivedResult, setMarkReceivedResult] = useState<MarkFiatReceivedResponse | null>(null);
  const [detailResult, setDetailResult] = useState<MerchantFiatPaymentDetailResponse | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedBeneficiaryId = selectedRecipient?.beneficiaryId || null;
  const {
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
  } = useMemo(
    () =>
      deriveMerchantState({
        quoteResult,
        fiatIntentResult,
        kycResult,
        stripeSessionResult,
        markReceivedResult,
        detailResult,
      }),
    [quoteResult, fiatIntentResult, kycResult, stripeSessionResult, markReceivedResult, detailResult],
  );
  const merchantCopilot = getMerchantCopilot({
    lang,
    quoteReady: Boolean(quote),
    fiatPaymentReady: Boolean(fiatPayment),
    needsKycAction,
    needsStripeSessionAction,
    awaitingStripePayment,
    needsManualMarkReceivedAction,
    fiatConfirmed,
    payoutCompleted,
    isBlocked,
    noOnchainPayoutCreated,
    paymentOrderId,
    executionBatchId,
    txHash,
    executionMode,
  });
  const kycActionHref = kycVerification?.verification_url || "/merchant";

  const flowSteps: FlowStep[] = [
    {
      key: "quote",
      title: t("merchant.stepQuoteTitle"),
      description: t("merchant.stepQuoteDesc"),
      done: Boolean(quote),
      active: !quote,
    },
    {
      key: "intent",
      title: t("merchant.stepIntentTitle"),
      description: t("merchant.stepIntentDesc"),
      done: Boolean(fiatPayment),
      active: Boolean(quote) && !fiatPayment,
    },
    {
      key: "kyc",
      title: t("merchant.stepKycTitle"),
      description: t("merchant.stepKycDesc"),
      done: !fiatPayment || !isStripeChannel || kycVerified,
      active: Boolean(fiatPayment) && isStripeChannel && !kycVerified,
    },
    {
      key: "channel_payment",
      title: t("merchant.stepStripeTitle"),
      description: t("merchant.stepStripeDesc"),
      done: !fiatPayment || !isStripeChannel || stripeConfirmed || fiatConfirmed,
      active: Boolean(fiatPayment) && isStripeChannel && kycVerified && !(stripeConfirmed || fiatConfirmed),
    },
    {
      key: "received",
      title: t("merchant.stepReceivedTitle"),
      description: t("merchant.stepReceivedDesc"),
      done: fiatConfirmed,
      active: Boolean(fiatPayment) && !fiatConfirmed,
    },
    {
      key: "payout",
      title: t("merchant.stepPayoutTitle"),
      description: t("merchant.stepPayoutDesc"),
      done: payoutCompleted || isBlocked,
      active: fiatConfirmed && !payoutCompleted && !isBlocked,
    },
  ];

  const timelineItems = useMemo(() => {
    if (!detailResult?.timeline.items?.length) return [];
    return detailResult.timeline.items.map((item) => ({
      ...item,
      title: mapMerchantTimelineTitle(item, t),
    }));
  }, [detailResult, t]);

  function handleCreateRecipient(payload: {
    name: string;
    address: string;
    network: string;
    note?: string;
  }) {
    addRecipient(payload);
  }

  function ensureLinkedRecipient(): string | null {
    if (selectedBeneficiaryId) return selectedBeneficiaryId;
    setError(t("recipient.requiresSynced"));
    return null;
  }

  async function handleCreateQuote(event: FormEvent) {
    event.preventDefault();
    const beneficiaryId = ensureLinkedRecipient();
    if (!beneficiaryId) return;
    setLoading("quote");
    setError(null);
    setFiatIntentResult(null);
    setKycResult(null);
    setStripeSessionResult(null);
    setMarkReceivedResult(null);
    setDetailResult(null);
    try {
      const response = await postMerchantQuote({
        merchant_id: merchantId.trim(),
        beneficiary_id: beneficiaryId,
        source_currency: sourceCurrency.trim().toUpperCase(),
        source_amount: Number(sourceAmount),
        target_currency: targetCurrency.trim().toUpperCase(),
        target_network: targetNetwork.trim(),
      });
      setQuoteResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(null);
    }
  }

  async function handleCreateFiatIntent() {
    if (!quoteResult) return;
    const beneficiaryId = ensureLinkedRecipient();
    if (!beneficiaryId) return;
    setLoading("intent");
    setError(null);
    setKycResult(null);
    setStripeSessionResult(null);
    setMarkReceivedResult(null);
    try {
      const response = await postCreateFiatPayment({
        quote_id: quoteResult.quote.id,
        merchant_id: merchantId.trim(),
        beneficiary_id: beneficiaryId,
        reference: reference.trim(),
        source_text: "Merchant fiat settlement flow",
      });
      setFiatIntentResult(response);
      setFiatPaymentIdInput(response.fiat_payment.id);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(LAST_FIAT_PAYMENT_ID_KEY, response.fiat_payment.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(null);
    }
  }

  async function handleStartKyc() {
    if (!merchantId.trim()) return;
    setLoading("kyc");
    setError(null);
    try {
      const response = await postMerchantKycStart({
        subject_type: "merchant",
        subject_id: merchantId.trim(),
      });
      setKycResult(response);
      const fiatPaymentId = fiatIntentResult?.fiat_payment.id || detailResult?.fiat_payment.id;
      if (fiatPaymentId) {
        const detail = await getMerchantFiatPaymentDetail(fiatPaymentId);
        setDetailResult(detail);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(null);
    }
  }

  async function handleCreateStripeSession() {
    const fiatPaymentId = fiatIntentResult?.fiat_payment.id || detailResult?.fiat_payment.id;
    if (!fiatPaymentId) return;
    setLoading("stripe");
    setError(null);
    let pendingCheckoutTab: Window | null = null;
    const openCheckout = (checkoutUrl: string) => {
      if (typeof window === "undefined") return;
      try {
        if (pendingCheckoutTab && !pendingCheckoutTab.closed) {
          pendingCheckoutTab.location.replace(checkoutUrl);
          try {
            pendingCheckoutTab.opener = null;
          } catch {
            // ignore browser restrictions
          }
          pendingCheckoutTab.focus();
          return;
        }
      } catch {
        // fallback to direct window.open below
      }
      window.open(checkoutUrl, "_blank");
    };
    try {
      if (typeof window !== "undefined") {
        pendingCheckoutTab = window.open("about:blank", "_blank");
        if (pendingCheckoutTab && !pendingCheckoutTab.closed) {
          pendingCheckoutTab.document.title = "Redirecting to Stripe Checkout...";
          pendingCheckoutTab.document.body.innerHTML =
            "<div style='font-family:system-ui;padding:24px;'>Redirecting to Stripe Checkout...</div>";
        }
      }
      const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
      const response = await postStartStripePayment(fiatPaymentId, {
        success_url: `${origin}/merchant?stripe=success&fiat_payment_id=${fiatPaymentId}`,
        cancel_url: `${origin}/merchant?stripe=cancel&fiat_payment_id=${fiatPaymentId}`,
        locale: lang === "zh" ? "zh" : "en",
      });
      setStripeSessionResult(response);
      const checkoutUrl = response.checkout?.checkout_url || response.fiat_payment?.channel_checkout_url;
      if (checkoutUrl) {
        openCheckout(checkoutUrl);
      } else {
        if (pendingCheckoutTab && !pendingCheckoutTab.closed) {
          pendingCheckoutTab.close();
        }
        setError(response.message || t("merchant.stripeSessionFailedHint"));
      }
      void loadDetailById(fiatPaymentId).catch(() => {
        // do not block Stripe checkout experience on detail refresh failure
      });
    } catch (err) {
      if (pendingCheckoutTab && !pendingCheckoutTab.closed) {
        pendingCheckoutTab.close();
      }
      const message = err instanceof Error ? err.message : t("common.error");
      setError(message);
      // Recover from transient request failures: backend may still have created the session.
      try {
        const detail = await getMerchantFiatPaymentDetail(fiatPaymentId);
        setDetailResult(detail);
        const recoveredCheckoutUrl = detail.fiat_payment?.channel_checkout_url;
        if (recoveredCheckoutUrl) {
          setStripeSessionResult((current) => ({
            status: "ok",
            fiat_payment: detail.fiat_payment,
            quote: detail.quote,
            next_action: "open_checkout",
            checkout: {
              provider: "stripe",
              checkout_session_id: detail.fiat_payment.channel_checkout_session_id || null,
              checkout_url: recoveredCheckoutUrl,
              payment_intent_id: detail.fiat_payment.channel_payment_id || null,
              channel_status: detail.fiat_payment.channel_status || null,
            },
            message: current?.message || message,
          }));
          openCheckout(recoveredCheckoutUrl);
          setError(null);
        }
      } catch {
        // keep original error
      }
    } finally {
      setLoading(null);
    }
  }

  async function handleMarkReceived(options?: { demoAdminOverride?: boolean }) {
    const fiatPaymentId = fiatIntentResult?.fiat_payment.id || detailResult?.fiat_payment.id;
    if (!fiatPaymentId || !fiatPayment) return;
    const demoAdminOverride = Boolean(options?.demoAdminOverride);
    setLoading("received");
    setError(null);
    try {
      const response = await postMarkFiatReceived(fiatPaymentId, {
        collection_method:
          fiatPayment.payment_channel === "stripe"
            ? "stripe_demo_admin_override"
            : "manual_bank_transfer",
        bank_reference: bankReference.trim() || stripeSessionResult?.checkout?.payment_intent_id || null,
        received_amount: fiatPayment.payer_amount,
        currency: fiatPayment.payer_currency,
        execution_mode: executionMode,
        demo_admin_override: demoAdminOverride,
        note: demoAdminOverride
          ? "admin manual override confirmation"
          : "manual receipt confirmation",
      });
      setMarkReceivedResult(response);
      setFiatPaymentIdInput(fiatPaymentId);

      try {
        const detail = await getMerchantFiatPaymentDetail(fiatPaymentId);
        setDetailResult(detail);
      } catch {
        // keep current flow visible even if detail refresh fails
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(null);
    }
  }

  async function handleLoadDetail() {
    if (!fiatPaymentIdInput.trim()) return;
    setLoading("detail");
    setError(null);
    try {
      await loadDetailById(fiatPaymentIdInput.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(null);
    }
  }

  async function loadDetailById(
    fiatPaymentId: string,
    options?: { syncStripe?: boolean },
  ) {
    const response = options?.syncStripe
      ? await postSyncStripePayment(fiatPaymentId)
      : await getMerchantFiatPaymentDetail(fiatPaymentId);
    setDetailResult(response);
    setFiatPaymentIdInput(fiatPaymentId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(LAST_FIAT_PAYMENT_ID_KEY, fiatPaymentId);
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    const searchParams = new URLSearchParams(window.location.search);
    const stripeFlag = searchParams.get("stripe");
    if (!stripeFlag) return;
    const fromQuery = searchParams.get("fiat_payment_id") || searchParams.get("fiatPaymentId");
    const stored = window.localStorage.getItem(LAST_FIAT_PAYMENT_ID_KEY);
    const candidateId = (fromQuery || stored || "").trim();
    if (!candidateId) return;

    const shouldSyncStripe = stripeFlag === "success";
    void loadDetailById(candidateId, { syncStripe: shouldSyncStripe })
      .catch(() => {
        // If provider sync fails once, fallback to plain detail fetch so UI still loads.
        return loadDetailById(candidateId).catch(() => {
          setError(t("merchant.detailHint"));
        });
      })
      .finally(() => {
        window.history.replaceState({}, "", "/merchant");
      });
  }, [t]);

  const activeFiatPaymentId = fiatPayment?.id || fiatIntentResult?.fiat_payment.id || null;
  const shouldPollDetail =
    Boolean(activeFiatPaymentId) &&
    (awaitingStripePayment || (fiatConfirmed && !payoutCompleted && !isBlocked));
  const kycPollingStatus = (kycVerification?.status || "").toLowerCase();
  const shouldPollKyc =
    Boolean(kycVerification?.id) &&
    !["verified", "failed", "expired", "blocked"].includes(kycPollingStatus);

  useEffect(() => {
    if ((!shouldPollDetail || !activeFiatPaymentId) && !shouldPollKyc) return;

    let cancelled = false;
    let inFlight = false;
    let timeoutId: number | null = null;

    const scheduleNext = () => {
      if (cancelled) return;
      timeoutId = window.setTimeout(() => {
        void tick();
      }, 8000);
    };

    const tick = async () => {
      if (cancelled || inFlight) return;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") {
        scheduleNext();
        return;
      }

      inFlight = true;
      try {
        const tasks: Promise<unknown>[] = [];

        if (shouldPollKyc && kycVerification?.id) {
          tasks.push(
            getKycVerification(kycVerification.id).then((latest) => {
              if (!cancelled && latest.verification) setKycResult(latest);
            }),
          );
        }

        if (shouldPollDetail && activeFiatPaymentId) {
          tasks.push(loadDetailById(activeFiatPaymentId, { syncStripe: awaitingStripePayment }));
        }

        await Promise.allSettled(tasks);
      } finally {
        inFlight = false;
        scheduleNext();
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") return;
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      void tick();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    scheduleNext();

    return () => {
      cancelled = true;
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [
    activeFiatPaymentId,
    awaitingStripePayment,
    kycVerification?.id,
    shouldPollDetail,
    shouldPollKyc,
  ]);

  async function handleAttachExecutionTx(input: {
    executionItemId: string;
    txHash: string;
    walletAddress?: string;
  }) {
    setLoading("attach_tx");
    setError(null);
    try {
      await postExecutionItemAttachTx(input.executionItemId, {
        tx_hash: input.txHash,
        wallet_address: input.walletAddress || null,
        locale: lang === "zh" ? "zh-CN" : "en-US",
      });
      if (fiatPayment?.id) await loadDetailById(fiatPayment.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(null);
    }
  }

  async function handleAttachSafeProposal(input: {
    executionItemId: string;
    safeAddress?: string;
    proposalId?: string;
    proposalUrl?: string;
    proposerWallet?: string;
  }) {
    setLoading("attach_safe");
    setError(null);
    try {
      await postExecutionItemAttachSafeProposal(input.executionItemId, {
        safe_address: input.safeAddress || null,
        proposal_id: input.proposalId || null,
        proposal_url: input.proposalUrl || null,
        proposer_wallet: input.proposerWallet || null,
      });
      if (fiatPayment?.id) await loadDetailById(fiatPayment.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(null);
    }
  }

  async function handleSyncExecutionReceipt(executionItemId: string) {
    setLoading("sync_receipt");
    setError(null);
    try {
      await postExecutionItemSyncReceipt(executionItemId, { force: false });
      if (fiatPayment?.id) await loadDetailById(fiatPayment.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(null);
    }
  }

  function loadDemoScenario(type: "normal" | "blocked") {
    const target = recipientOptions.find((recipient) => {
      if (!recipient.beneficiaryId) return false;
      const text = `${recipient.note || ""}`.toLowerCase();
      if (type === "blocked") {
        return text.includes("high") || text.includes("黑");
      }
      return !text.includes("high") && !text.includes("黑");
    });
    if (target) setSelectedRecipientId(target.id);
    setSourceCurrency("USD");
    setSourceAmount(type === "blocked" ? "500" : "800");
    setTargetCurrency("USDT");
    setTargetNetwork("hashkey_testnet");
    setExecutionMode("operator");
    setReference(type === "blocked" ? "MERCHANT-RISK-BLOCKED" : "MERCHANT-STANDARD");
    setBankReference(type === "blocked" ? "FIAT-RECV-BLOCKED" : "FIAT-RECV-NORMAL");
  }

  return (
    <main className="space-y-6 motion-scale-in">
      <section className="relative overflow-hidden rounded-[36px] border border-slate-900 bg-[linear-gradient(180deg,#0b1730_0%,#274a72_64%,#5d829a_100%)] p-6 text-white shadow-[0_32px_100px_rgba(9,18,34,0.22)] lg:p-8 motion-fade-up">
        <div className="absolute inset-0 opacity-35 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:124px_124px]" />
        <div className="absolute right-[-8%] top-[-10%] h-[360px] w-[360px] rounded-full border border-white/18" />
        <div className="absolute right-[18%] top-[24%] h-[180px] w-[180px] rounded-full border border-white/12" />
        <div className="relative grid gap-6 lg:grid-cols-[1fr_360px] lg:items-end">
          <div className="motion-fade-up">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d7d39a]">{t("merchant.badge")}</p>
            <h1 className="mt-4 text-4xl font-medium tracking-[-0.04em] leading-[0.96] lg:text-6xl">{t("merchant.title")}</h1>
            <p className="mt-5 max-w-4xl text-base leading-8 text-slate-100/90">{t("merchant.intro")}</p>
          </div>
          <div className="grid gap-3">
            <div className="rounded-[22px] border border-white/10 bg-white/[0.06] px-4 py-4 backdrop-blur motion-fade-up motion-delay-1 surface-transition">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-300">{t("merchant.merchantPays")}</p>
              <p className="mt-2 text-sm leading-7 text-slate-100/88">{t("merchant.stepQuoteDesc")}</p>
            </div>
            <div className="rounded-[22px] border border-white/10 bg-white/[0.06] px-4 py-4 backdrop-blur motion-fade-up motion-delay-2 surface-transition">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-300">{t("merchant.recipientGets")}</p>
              <p className="mt-2 text-sm leading-7 text-slate-100/88">{t("merchant.stepPayoutDesc")}</p>
            </div>
          </div>
        </div>
      </section>

      {error ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 motion-fade-up motion-delay-1">
          {error}
        </section>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <section className="space-y-6 motion-fade-up motion-delay-1">
          <section className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm motion-fade-up motion-delay-1 surface-transition">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                {t("merchant.flowTitle")}
              </h2>
              <StatusBadge status={settlementStatus} />
            </div>
            <ol className="grid gap-3 md:grid-cols-4">
              {flowSteps.map((step, index) => (
                <li
                  key={step.key}
                  className={`rounded-xl border p-3 ${
                    step.done
                      ? "border-emerald-200 bg-emerald-50"
                      : step.active
                        ? "border-[#bfd0ec] bg-[#edf3ff]"
                        : "border-[#d8e1f0] bg-[#f7f9fd]"
                  }`}
                >
                  <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
                    {t("merchant.stepLabel")} {index + 1}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">{step.title}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-600">{step.description}</p>
                </li>
              ))}
            </ol>
          </section>

          <section className="rounded-[30px] border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-5 shadow-sm motion-fade-up motion-delay-2 surface-transition">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#496896]">
                  {merchantCopilot.title}
                </p>
                <h2 className="mt-1 text-lg font-semibold text-slate-900">
                  {lang === "zh" ? "结算判断" : "Settlement guidance"}
                </h2>
              </div>
              <StatusBadge status={merchantCopilot.status} />
            </div>
            <p className="mt-3 text-sm leading-7 text-slate-700">{merchantCopilot.summary}</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-[#d8e1f0] bg-white px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
                  {lang === "zh" ? "下一步" : "Next step"}
                </p>
                <p className="mt-2 text-sm font-medium leading-7 text-slate-900">{merchantCopilot.nextStep}</p>
              </div>
              <div className="rounded-2xl border border-[#d8e1f0] bg-white px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
                  {lang === "zh" ? "为什么现在这样判断" : "Why the flow looks like this"}
                </p>
                <p className="mt-2 text-sm leading-7 text-slate-700">{merchantCopilot.detail}</p>
              </div>
            </div>
            {merchantCopilot.chips.length > 0 ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {merchantCopilot.chips.map((chip) => (
                  <span
                    key={chip}
                    className="rounded-full border border-[#c8d4ea] bg-white px-2.5 py-1 text-xs font-medium text-slate-700"
                  >
                    {chip}
                  </span>
                ))}
              </div>
            ) : null}
          </section>

          <details className="rounded-[24px] border border-[#d8e1f0] bg-[#f8fbff] p-4 motion-fade-up motion-delay-2 surface-transition">
            <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
              {t("merchant.presetsTitle")}
            </summary>
            <p className="mt-2 text-sm leading-7 text-slate-600">{t("merchant.presetsBody")}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => loadDemoScenario("normal")}
                className="rounded-lg border border-[#c8d4ea] bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-[#f4f8ff]"
              >
                {t("merchant.demoNormal")}
              </button>
              <button
                type="button"
                onClick={() => loadDemoScenario("blocked")}
                className="rounded-lg border border-rose-300 bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 hover:bg-rose-100"
              >
                {t("merchant.demoBlocked")}
              </button>
            </div>
          </details>

          <div className="motion-fade-up motion-delay-2 surface-transition">
            <QuoteCard
              loading={loading === "quote"}
              merchantId={merchantId}
              sourceCurrency={sourceCurrency}
              sourceAmount={sourceAmount}
              targetCurrency={targetCurrency}
              targetNetwork={targetNetwork}
              recipients={recipientOptions}
              selectedRecipientId={selectedRecipientId}
              onMerchantIdChange={setMerchantId}
              onSourceCurrencyChange={setSourceCurrency}
              onSourceAmountChange={setSourceAmount}
              onTargetCurrencyChange={setTargetCurrency}
              onTargetNetworkChange={setTargetNetwork}
              onSelectRecipient={setSelectedRecipientId}
              onCreateRecipient={handleCreateRecipient}
              onSubmit={handleCreateQuote}
              quote={quote}
            />
          </div>

          <div className="motion-fade-up motion-delay-3 surface-transition">
            <FiatIntentCard
              quoteReady={Boolean(quote)}
              intent={fiatIntentResult?.fiat_payment || detailResult?.fiat_payment || null}
              loading={loading === "intent"}
              onCreateIntent={handleCreateFiatIntent}
              reference={reference}
              onReferenceChange={setReference}
            />
          </div>

          {fiatPayment && isStripeChannel ? (
            <div className="motion-fade-up motion-delay-3 surface-transition">
              <StripeNextStepCard
                fiatPaymentId={fiatPayment.id}
                kycStatus={stripeCardKycStatus}
                stripeCheckoutUrl={checkoutUrl || undefined}
                nextAction={stripeCardNextAction}
                language={lang}
                stripeSessionId={stripeSessionId}
                paymentIntentId={stripePaymentIntentId}
                loading={loading === "kyc" || loading === "stripe" || loading === "detail"}
                kycHref={kycActionHref}
              />
            </div>
          ) : null}

          <section className="space-y-3 rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm motion-fade-up motion-delay-4 surface-transition">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
              {t("merchant.actionCardTitle")}
            </h2>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-1">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">{t("command.executionMode")}</span>
                <select
                  value={executionMode}
                  onChange={(event) => setExecutionMode(event.target.value as ExecutionMode)}
                  className="w-full rounded-xl border border-[#c8d4ea] bg-white px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                >
                  <option value="operator">operator</option>
                  <option value="user_wallet">user_wallet</option>
                  <option value="safe">safe</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">{t("merchant.bankReference")}</span>
                <input
                  value={bankReference}
                  onChange={(event) => setBankReference(event.target.value)}
                  className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                />
              </label>
            </div>

            {needsKycAction ? (
              <NextStepCard
                title={t("merchant.nextKycTitle")}
                message={t("merchant.nextKycMessage")}
                buttonLabel={loading === "kyc" ? t("merchant.startingKyc") : t("merchant.startKyc")}
                onClick={handleStartKyc}
                disabled={loading === "kyc"}
              />
            ) : null}
            {needsStripeSessionAction ? (
              <NextStepCard
                title={t("merchant.nextStripeTitle")}
                message={t("merchant.nextStripeMessage")}
                buttonLabel={loading === "stripe" ? t("merchant.creatingStripeSession") : t("merchant.createStripeSession")}
                onClick={handleCreateStripeSession}
                disabled={loading === "stripe"}
              />
            ) : null}
            {stripeSessionFailed ? (
              <section className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 motion-fade-up">
                <p className="font-semibold">{t("merchant.stripeSessionFailedTitle")}</p>
                <p className="mt-1">{stripeSessionResult?.message || t("merchant.stripeSessionFailedHint")}</p>
                <button
                  type="button"
                  onClick={handleCreateStripeSession}
                  disabled={loading === "stripe"}
                  className="mt-3 rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                >
                  {loading === "stripe" ? t("merchant.creatingStripeSession") : t("merchant.retryStripeSession")}
                </button>
              </section>
            ) : null}
            {awaitingStripePayment ? (
              <NextStepCard
                title={t("merchant.nextStripeWaitTitle")}
                message={t("merchant.nextStripeWaitMessage")}
                buttonLabel={loading === "detail" ? t("merchant.loadingDetail") : t("merchant.refreshStatus")}
                onClick={handleLoadDetail}
                disabled={loading === "detail"}
              />
            ) : null}
            {needsManualMarkReceivedAction ? (
              <NextStepCard
                title={t("merchant.nextIntentTitle")}
                message={t("merchant.nextIntentMessage")}
                buttonLabel={loading === "received" ? t("merchant.markingReceived") : t("merchant.startPayout")}
                onClick={() => handleMarkReceived()}
                disabled={loading === "received"}
              />
            ) : null}
          </section>

          {(detailResult?.execution_items?.length || fiatPayment) ? (
            <div className="motion-fade-up motion-delay-4 surface-transition">
              <ExecutionAttachPanel
                mode={
                  ((detailResult?.payment_order?.execution_mode as ExecutionMode | undefined) ||
                    executionMode) as ExecutionMode
                }
                items={detailResult?.execution_items ?? []}
                loading={loading === "attach_tx" || loading === "attach_safe" || loading === "sync_receipt"}
                onOperatorSubmit={() => handleMarkReceived()}
                onAttachTx={handleAttachExecutionTx}
                onAttachSafeProposal={handleAttachSafeProposal}
                onSyncReceipt={handleSyncExecutionReceipt}
              />
            </div>
          ) : null}

          {canUseStripeDemoOverride ? (
            <details className="rounded-2xl border border-amber-300 bg-amber-50 p-3 motion-fade-up motion-delay-4 surface-transition">
              <summary className="cursor-pointer text-sm font-semibold text-amber-800">
                {t("merchant.demoOverrideTitle")}
              </summary>
              <p className="mt-2 text-sm text-amber-800">{t("merchant.demoOverrideMessage")}</p>
              <button
                type="button"
                onClick={() => handleMarkReceived({ demoAdminOverride: true })}
                disabled={loading === "received"}
                className="mt-3 rounded-lg border border-amber-400 bg-amber-100 px-3 py-2 text-sm font-medium text-amber-900 hover:bg-amber-200 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
              >
                {loading === "received" ? t("merchant.markingReceived") : t("merchant.demoOverrideButton")}
              </button>
            </details>
          ) : null}

          <div className="motion-fade-up motion-delay-5 surface-transition">
            <PayoutResultCard
              paymentOrderId={paymentOrderId}
              executionBatchId={executionBatchId}
              payoutStatus={payoutStatus}
              onchainStatus={onchainStatus}
              txHash={txHash}
              explorerUrl={explorerUrl}
              network={quote?.target_network || targetNetwork}
              blocked={isBlocked}
              noOnchainPayoutCreated={noOnchainPayoutCreated}
            />
          </div>

          <section className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm motion-fade-up motion-delay-5 surface-transition">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
              {t("merchant.demoReadyTitle")}
            </h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3">
                <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("merchant.summaryStatus")}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <StatusBadge status={settlementStatus} />
                  {onchainStatus ? <StatusBadge status={onchainStatus} /> : null}
                </div>
              </div>
              <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3">
                <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("merchant.paymentOrderId")}</p>
                <p className="mt-2 break-all font-mono text-xs text-slate-700">{paymentOrderId || "-"}</p>
              </div>
              <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3">
                <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("common.txHash")}</p>
                <p className="mt-2 break-all font-mono text-xs text-slate-700">{txHash || "-"}</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-7 text-slate-700">{t("merchant.demoReadyBody")}</p>
          </section>

          <details className="rounded-[24px] border border-[#d8e1f0] bg-[#f8fbff] p-4 motion-fade-up motion-delay-5 surface-transition">
            <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
              {t("merchant.supportingDetailsTitle")}
            </summary>
            <p className="mt-2 text-sm leading-7 text-slate-600">
              {t("merchant.supportingDetailsBody")}
            </p>
            <div className="mt-4">
              <TechnicalDetailsAccordion
                quoteResult={quoteResult}
                fiatIntentResult={fiatIntentResult}
                kycResult={kycResult}
                stripeSessionResult={stripeSessionResult}
                markReceivedResult={markReceivedResult}
                detailResult={detailResult}
                paymentOrderId={paymentOrderId}
                executionBatchId={executionBatchId}
                txHash={txHash}
              />
            </div>
          </details>

          <details className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm motion-fade-up motion-delay-5 surface-transition">
            <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
              {t("merchant.detailTitle")}
            </summary>
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="space-y-1">
                  <span className="text-xs uppercase tracking-[0.1em] text-slate-500">{t("merchant.fiatPaymentId")}</span>
                  <input
                    value={fiatPaymentIdInput}
                    onChange={(event) => setFiatPaymentIdInput(event.target.value)}
                    className="w-[420px] max-w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                  />
                </label>
                <button
                  type="button"
                  onClick={handleLoadDetail}
                  disabled={!fiatPaymentIdInput || loading === "detail"}
                  className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#203a61] disabled:cursor-not-allowed disabled:bg-slate-400"
                >
                  {loading === "detail" ? t("merchant.loadingDetail") : t("merchant.loadDetail")}
                </button>
              </div>

              {detailResult ? (
                <div className="space-y-4">
                  <ExecutionItemTable
                    items={detailResult.execution_items}
                    title={t("merchant.executionItemsTitle")}
                    emptyText={t("component.noExecutionItems")}
                  />
                  <TimelineView title={t("merchant.timeline")} items={timelineItems} />
                </div>
              ) : (
                <EmptyStateCard title={t("merchant.detailTitle")} description={t("merchant.detailEmpty")} />
              )}
            </div>
          </details>
        </section>

        <aside className="space-y-4 xl:sticky xl:top-24 xl:h-fit motion-fade-up motion-delay-2">
          <section className="overflow-hidden rounded-[30px] border border-[#c8d4ea] bg-white shadow-sm motion-fade-up motion-delay-2 surface-transition">
            <div className="border-b border-[#d8e1f0] bg-[linear-gradient(180deg,#091427_0%,#163358_100%)] px-5 py-5 text-white">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-300">{t("merchant.summaryTitle")}</p>
              <div className="mt-4 grid gap-3">
                <div className="rounded-2xl border border-white/12 bg-white/[0.06] px-4 py-3">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-slate-300">{t("merchant.merchantPays")}</p>
                  <p className="mt-2 text-2xl font-medium tracking-[-0.03em]">
                    {quote ? `${formatAmount(quote.source_amount)} ${quote.source_currency}` : "-"}
                  </p>
                </div>
                <div className="rounded-2xl border border-white/12 bg-white/[0.06] px-4 py-3">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-slate-300">{t("merchant.recipientGets")}</p>
                  <p className="mt-2 text-2xl font-medium tracking-[-0.03em]">
                    {quote ? `${formatAmount(quote.target_amount)} ${quote.target_currency}` : "-"}
                  </p>
                </div>
              </div>
            </div>
            <div className="space-y-4 p-5">
              <div className="grid gap-3">
                <div className="rounded-2xl border border-[#d8e1f0] bg-[#f7f9fd] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("merchant.summaryStatus")}</p>
                    <StatusBadge status={settlementStatus} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <StatusBadge status={kycVerification?.status || "not_started"} />
                    <StatusBadge status={fiatPayment?.channel_status || "pending"} />
                  </div>
                </div>
                <div className="rounded-2xl border border-[#d8e1f0] bg-white p-4 text-sm text-slate-700">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("merchant.feeBreakdown")}</p>
                      <p className="mt-2 font-semibold text-slate-900">
                        {quote
                          ? `${formatAmount(quote.platform_fee)} + ${formatAmount(quote.network_fee)} = ${formatAmount(
                              quote.total_fee_amount,
                            )}`
                          : "-"}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("common.mode")}</p>
                      <p className="mt-2 font-semibold text-slate-900">{statusLabel(executionMode)}</p>
                    </div>
                  </div>
                </div>
              </div>
              <div className="space-y-3 text-sm text-slate-700">
                <div className="flex items-start justify-between gap-4">
                  <span className="text-slate-500">{t("merchant.beneficiaryLabel")}</span>
                  <span className="max-w-[220px] text-right font-semibold text-slate-900">
                    {selectedRecipient ? formatRecipientLabel(selectedRecipient) : "-"}
                  </span>
                </div>
                <div className="flex items-start justify-between gap-4">
                  <span className="text-slate-500">{t("merchant.expiresAt")}</span>
                  <span className="text-right font-semibold text-slate-900">{formatTime(quote?.expires_at)}</span>
                </div>
                {explorerUrl ? (
                  <a
                    href={explorerUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center rounded-xl border border-[#c8d4ea] bg-[#f7f9fd] px-3 py-2 text-sm font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
                  >
                    {t("common.openExplorer")}
                  </a>
                ) : null}
              </div>
              <p className="text-xs leading-6 text-slate-500">{t("merchant.summaryHint")}</p>
            </div>
          </section>

          <details className="rounded-[24px] border border-[#c8d4ea] bg-white p-4 shadow-sm motion-fade-up motion-delay-3 surface-transition">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.14em] text-slate-600">
              {t("merchant.debugSection")}
            </summary>
            <div className="mt-3 space-y-2 text-xs text-slate-600">
              <p>merchant_id: {merchantId}</p>
              <p>beneficiary_id: {selectedBeneficiaryId || "-"}</p>
              <p>fiat_payment_id: {fiatPayment?.id || "-"}</p>
              <p>payment_order_id: {paymentOrderId || "-"}</p>
              <p>execution_batch_id: {executionBatchId || "-"}</p>
            </div>
          </details>
        </aside>
      </div>
    </main>
  );
}

function NextStepCard(props: {
  title: string;
  message: string;
  buttonLabel: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="rounded-[24px] border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-4 motion-scale-in surface-transition">
      <p className="text-xs uppercase tracking-[0.12em] text-[#496896]">{t("common.nextAction")}</p>
      <p className="mt-1 text-sm font-semibold text-slate-900">{props.title}</p>
      <p className="mt-1 text-sm leading-7 text-slate-700">{props.message}</p>
      <button
        type="button"
        onClick={props.onClick}
        disabled={props.disabled}
        className="mt-3 inline-flex items-center rounded-xl bg-slate-950 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[#203a61] disabled:cursor-not-allowed disabled:bg-slate-400"
      >
        {props.buttonLabel}
      </button>
    </div>
  );
}

function mapMerchantTimelineTitle(item: TimelineItem, t: (key: string) => string): string {
  const hay = `${item.title} ${item.action} ${JSON.stringify(item.details || {})}`.toLowerCase();

  if (containsAny(hay, ["quote"]) && containsAny(hay, ["create", "created"])) return t("merchant.timelineQuoteCreated");
  if (containsAny(hay, ["kyc"]) && containsAny(hay, ["start", "started", "created"])) return t("merchant.timelineKycStarted");
  if (containsAny(hay, ["kyc"]) && containsAny(hay, ["verified", "status_updated"])) return t("merchant.timelineKycVerified");
  if (containsAny(hay, ["stripe"]) && containsAny(hay, ["checkout", "session"]) && containsAny(hay, ["create", "created"])) {
    return t("merchant.timelineStripeSessionCreated");
  }
  if (containsAny(hay, ["stripe"]) && containsAny(hay, ["payment", "checkout"]) && containsAny(hay, ["confirm", "completed", "succeeded"])) {
    return t("merchant.timelineStripePaymentConfirmed");
  }
  if (containsAny(hay, ["fiat"]) && containsAny(hay, ["intent"]) && containsAny(hay, ["create", "created"])) {
    return t("merchant.timelineIntentCreated");
  }
  if (containsAny(hay, ["fiat"]) && containsAny(hay, ["mark", "received", "confirm"])) {
    return t("merchant.timelineFiatReceived");
  }
  if (containsAny(hay, ["payout"]) && containsAny(hay, ["link", "linked"])) return t("merchant.timelinePayoutLinked");
  if (containsAny(hay, ["submit", "submitted"]) && containsAny(hay, ["tx", "transaction", "onchain"])) {
    return t("merchant.timelineTxSubmitted");
  }
  if (containsAny(hay, ["confirm", "confirmed"]) && containsAny(hay, ["tx", "transaction", "onchain"])) {
    return t("merchant.timelineTxConfirmed");
  }
  if (containsAny(hay, ["settlement"]) && containsAny(hay, ["complete", "completed"])) {
    return t("merchant.timelineSettlementCompleted");
  }
  if (containsAny(hay, ["block", "blocked"])) return t("merchant.timelineSettlementBlocked");
  if (containsAny(hay, ["no_onchain", "no on-chain payout", "no onchain payout"])) {
    return t("merchant.timelineNoOnchain");
  }
  return item.title;
}
