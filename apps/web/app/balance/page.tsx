"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  type BalanceAccountResponse,
  type BalanceDepositDetailResponse,
  type BalanceDepositOrderView,
  type BalanceLedgerResponse,
  type BalancePaymentConfirmResponse,
  type BalancePaymentPreviewResponse,
  type BalanceStartStripePaymentResponse,
  type KycStartResponse,
  getRememberedActorId,
  getBalanceAccount,
  getBalanceDepositDetail,
  getBalanceLedger,
  getKycVerification,
  postBalancePaymentConfirm,
  postBalancePaymentPreview,
  postCreateBalanceDeposit,
  postMerchantKycStart,
  postStartBalanceDepositStripePayment,
  postSyncBalanceDepositStripePayment,
  rememberActorId,
} from "../../lib/api";
import { formatAmount, formatTime } from "../../lib/format";
import { useI18n } from "../../lib/i18n-provider";
import { EmptyStateCard } from "../../components/empty-state-card";
import { StatusBadge } from "../../components/status-badge";

const DEFAULT_USER_ID = "babd0649-6a5a-5d02-aa46-9070ee5248d4";
const LAST_DEPOSIT_STORAGE_KEY = "payfi_last_balance_deposit_id";
const ACCESS_TOKEN_PLACEHOLDER = "<access_token from /api/auth/session>";

type ExecutionMode = "operator" | "user_wallet" | "safe";
type BalanceMcpTool = "capability" | "deposit" | "sync" | "preview" | "confirm";

type TreasuryGuidance = {
  title: string;
  summary: string;
  nextStep: string;
  detail: string;
  status: string;
  chips: string[];
};

function extractPreviewField(preview: Record<string, unknown> | undefined, keys: string[]): string {
  if (!preview) return "-";
  for (const key of keys) {
    const value = preview[key];
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value);
    }
  }
  return "-";
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function SnippetBlock({
  title,
  snippet,
  onCopy,
  copied,
  copyLabel,
  copiedLabel,
}: {
  title: string;
  snippet: string;
  onCopy: () => void;
  copied: boolean;
  copyLabel: string;
  copiedLabel: string;
}) {
  return (
    <div className="rounded-[24px] border border-[#d8e1f0] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] p-4 surface-transition">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{title}</p>
        <button
          type="button"
          onClick={onCopy}
          className="rounded-full border border-[#c7d7ee] bg-white px-3 py-1 text-xs font-medium text-[#163358] transition hover:bg-[#edf3ff]"
        >
          {copied ? copiedLabel : copyLabel}
        </button>
      </div>
      <div className="mt-3 overflow-hidden rounded-[18px] border border-[#203456]/10 bg-[#081221] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
        <div className="flex items-center justify-between border-b border-white/6 px-4 py-2">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff6b6b]/80" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#ffd166]/80" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#4ade80]/80" />
          </div>
          <span className="text-[10px] uppercase tracking-[0.22em] text-slate-500">json</span>
        </div>
        <pre className="overflow-x-auto px-4 py-3 text-xs leading-6 text-slate-200">
          <code>{snippet}</code>
        </pre>
      </div>
    </div>
  );
}

function getTreasuryGuidance(input: {
  lang: "zh" | "en";
  availableBalance?: number | null;
  lockedBalance?: number | null;
  latestDeposit?: BalanceDepositOrderView | null;
  previewResult?: BalancePaymentPreviewResponse | null;
  confirmResult?: BalancePaymentConfirmResponse | null;
  currency: string;
}): TreasuryGuidance {
  const availableBalance = input.availableBalance ?? 0;
  const lockedBalance = input.lockedBalance ?? 0;
  const deposit = input.latestDeposit;
  const preview = input.previewResult;
  const confirm = input.confirmResult;
  const postSettlementBalance =
    preview?.balance_check?.sufficient
      ? (preview.balance_check.available_balance || 0) - (preview.balance_check.required_amount || 0)
      : null;

  if (input.lang === "zh") {
    if (deposit?.next_action === "complete_kyc") {
      return {
        title: "AI 资金副驾驶",
        summary: "当前充值流程被身份核验卡住，平台余额不会在 KYC 通过前入账。",
        nextStep: "先完成身份核验，再继续创建充值收款页。",
        detail: "这是平台余额路径的准入门槛。只有身份核验通过，法币才会进入稳定币余额账户。",
        status: "blocked_kyc_required",
        chips: ["kyc", "deposit", input.currency],
      };
    }
    if (deposit?.next_action === "open_checkout") {
      return {
        title: "AI 资金副驾驶",
        summary: "充值单已经建立，但法币还没有真正进入平台余额。",
        nextStep: "打开 Stripe 收款页完成支付，支付成功后再回到当前页面同步状态。",
        detail: "系统已经知道预期可入账的稳定币金额，但在 provider-confirmed 前不会提前给余额记账。",
        status: "awaiting_channel_payment",
        chips: ["checkout", "deposit", input.currency],
      };
    }
    if (deposit?.next_action === "wait_channel_confirmation") {
      return {
        title: "AI 资金副驾驶",
        summary: "收款页已完成，当前在等待 Stripe 或同步接口确认充值到账。",
        nextStep: "优先检查最新状态；到账后平台余额会自动增加。",
        detail: "这里保留真实支付语义：在 provider-confirmed 之前，系统不会把这笔充值提前当成可用余额。",
        status: "payment_processing",
        chips: ["sync", "provider_confirmed", input.currency],
      };
    }
    if (confirm) {
      return {
        title: "AI 资金副驾驶",
        summary: "这笔余额支付已经进入执行层，平台余额正在被消费或锁定。",
        nextStep: "查看结算详情，继续追踪 payment order、execution batch 和链上 tx。",
        detail: "余额账户只提供资金来源，真正的支付执行还是走原有的 payment order / execution batch 主线。",
        status: confirm.payment_status || confirm.status,
        chips: ["platform_balance", "payment_order", "execution_batch"],
      };
    }
    if (preview?.balance_check) {
      if (!preview.balance_check.sufficient) {
        const gap = Math.max((preview.balance_check.required_amount || 0) - (preview.balance_check.available_balance || 0), 0);
        return {
          title: "AI 资金副驾驶",
          summary: "当前平台余额不足以覆盖这笔结算，建议先补仓再提交。",
          nextStep: `建议至少再充值 ${formatAmount(gap)} ${input.currency}，再重新生成结算预览。`,
          detail: "先补足资金来源，再进入 confirm，会比推进到半路因为余额不足中断更稳。",
          status: "pending",
          chips: ["insufficient_balance", input.currency, "deposit_first"],
        };
      }
      return {
        title: "AI 资金副驾驶",
        summary: "当前平台余额足以覆盖这笔结算，可以直接从余额进入执行。",
        nextStep:
          postSettlementBalance !== null
            ? `确认后预计剩余 ${formatAmount(postSettlementBalance)} ${input.currency} 可继续使用。`
            : "确认后可直接进入 payment order 和 execution batch 创建。",
        detail:
          lockedBalance > 0
            ? "系统里已有一部分余额被锁定，说明你已经有正在执行或待完成的结算。"
            : "当前余额状态健康，适合直接用平台余额发起下一笔结算。",
        status: "confirmed",
        chips: ["balance_ready", input.currency, "settle_now"],
      };
    }
    if (availableBalance <= 0) {
      return {
        title: "AI 资金副驾驶",
        summary: "当前平台余额为空，还不能直接从余额发起结算。",
        nextStep: "先创建一笔法币充值，让平台把资金兑换成稳定币余额。",
        detail: "充值成功后，这个页面会展示可用余额、锁定余额，以及可被 MCP 直接调用的资金状态。",
        status: "pending",
        chips: ["no_balance", "deposit_required", input.currency],
      };
    }
    return {
      title: "AI 资金副驾驶",
      summary: "当前平台余额已经可用，下一步适合先生成一笔余额结算预览。",
      nextStep: "输入自然语言结算指令，先看余额是否足够，再决定是否确认。",
      detail: "这条资金路径天然适合 MCP，因为资金已经留存在平台账户里，不需要每次重新走法币收款。",
      status: "ready",
      chips: ["balance_ready", input.currency, "mcp_friendly"],
    };
  }

  if (deposit?.next_action === "complete_kyc") {
    return {
      title: "AI Treasury Copilot",
      summary: "The deposit flow is blocked on identity verification, so no platform balance can be credited yet.",
      nextStep: "Complete identity verification first, then continue to checkout.",
      detail: "This is the admission gate for the stored-value path. Only verified users can fund a platform balance.",
      status: "blocked_kyc_required",
      chips: ["kyc", "deposit", input.currency],
    };
  }
  if (deposit?.next_action === "open_checkout") {
    return {
      title: "AI Treasury Copilot",
      summary: "A deposit order exists, but fiat has not actually entered the platform balance yet.",
      nextStep: "Open Stripe checkout, complete payment, then return here to sync the result.",
      detail: "The system already knows the expected stablecoin credit amount, but it does not yet have provider-confirmed fiat receipt.",
      status: "awaiting_channel_payment",
      chips: ["checkout", "deposit", input.currency],
    };
  }
  if (deposit?.next_action === "wait_channel_confirmation") {
    return {
      title: "AI Treasury Copilot",
      summary: "Checkout is complete, and the system is now waiting for Stripe or the sync path to confirm the deposit.",
      nextStep: "Check the latest status. Once confirmed, the platform balance will credit automatically.",
      detail: "The platform preserves truthful payment semantics here: the balance is not credited before provider-confirmed receipt.",
      status: "payment_processing",
      chips: ["sync", "provider_confirmed", input.currency],
    };
  }
  if (confirm) {
    return {
      title: "AI Treasury Copilot",
      summary: "This balance-funded payment is already in the execution layer, and platform funds are now being consumed or locked.",
        nextStep: "View settlement detail and continue tracking the payment order, execution batch, and onchain transaction.",
      detail: "The balance account is only the funding source. Execution still runs through the existing payment order and batch pipeline.",
      status: confirm.payment_status || confirm.status,
      chips: ["platform_balance", "payment_order", "execution_batch"],
    };
  }
  if (preview?.balance_check) {
    if (!preview.balance_check.sufficient) {
      const gap = Math.max((preview.balance_check.required_amount || 0) - (preview.balance_check.available_balance || 0), 0);
      return {
        title: "AI Treasury Copilot",
        summary: "The current platform balance is not enough to cover this settlement. Fund the account first.",
        nextStep: `Deposit at least ${formatAmount(gap)} ${input.currency}, then regenerate the preview.`,
        detail: "Funding the account before confirm is safer than pushing deeper into the flow and failing on insufficient balance later.",
        status: "pending",
        chips: ["insufficient_balance", input.currency, "deposit_first"],
      };
    }
    return {
      title: "AI Treasury Copilot",
      summary: "The platform balance is sufficient for this settlement, so you can move straight into execution from balance.",
      nextStep:
        postSettlementBalance !== null
          ? `After confirmation, about ${formatAmount(postSettlementBalance)} ${input.currency} should remain available.`
          : "After confirmation, the flow can proceed directly into payment order and execution batch creation.",
      detail:
        lockedBalance > 0
          ? "Part of the balance is already locked, which means another settlement is still in progress or awaiting completion."
          : "The balance posture is healthy and ready for another settlement from stored value.",
      status: "confirmed",
      chips: ["balance_ready", input.currency, "settle_now"],
    };
  }
  if (availableBalance <= 0) {
    return {
      title: "AI Treasury Copilot",
      summary: "The platform balance is empty, so MCP or the web app cannot yet fund settlement directly from balance.",
      nextStep: "Create a fiat deposit first so the platform can convert it into stablecoin balance.",
      detail: "After funding succeeds, this page will show live available balance, locked balance, and MCP-ready funding state.",
      status: "pending",
      chips: ["no_balance", "deposit_required", input.currency],
    };
  }
  return {
    title: "AI Treasury Copilot",
    summary: "The platform balance is already usable, so the next good move is to generate a balance-funded settlement preview.",
    nextStep: "Enter a natural-language settlement request, check balance sufficiency, then decide whether to confirm.",
    detail: "This funding path is naturally MCP-friendly because the funds already sit inside the platform account instead of requiring new fiat collection each time.",
    status: "ready",
    chips: ["balance_ready", input.currency, "mcp_friendly"],
  };
}

export default function BalancePage() {
  const { t, lang, statusLabel } = useI18n();
  const [userId, setUserId] = useState(() => getRememberedActorId() || DEFAULT_USER_ID);
  const [currency, setCurrency] = useState("USDT");
  const [sourceCurrency, setSourceCurrency] = useState("USD");
  const [sourceAmount, setSourceAmount] = useState("500");
  const [reference, setReference] = useState("BALANCE-FUNDING-001");
  const [paymentPrompt, setPaymentPrompt] = useState("从平台余额给 Alice 支付 150 USDT，今晚到账");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("operator");

  const [accountResult, setAccountResult] = useState<BalanceAccountResponse | null>(null);
  const [ledgerResult, setLedgerResult] = useState<BalanceLedgerResponse | null>(null);
  const [latestDeposit, setLatestDeposit] = useState<BalanceDepositOrderView | null>(null);
  const [latestDepositDetail, setLatestDepositDetail] = useState<BalanceDepositDetailResponse | null>(null);
  const [latestCheckout, setLatestCheckout] = useState<BalanceStartStripePaymentResponse["checkout"] | null>(null);
  const [kycResult, setKycResult] = useState<KycStartResponse | null>(null);
  const [previewResult, setPreviewResult] = useState<BalancePaymentPreviewResponse | null>(null);
  const [confirmResult, setConfirmResult] = useState<BalancePaymentConfirmResponse | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null);
  const [activeLiveTool, setActiveLiveTool] = useState<BalanceMcpTool>("capability");
  const [showMcpExamples, setShowMcpExamples] = useState(false);
  const [showLiveDemo, setShowLiveDemo] = useState(false);

  const activeDepositId = latestDeposit?.id || null;

  useEffect(() => {
    rememberActorId(userId.trim() || null);
  }, [userId]);

  async function refreshBalanceState(targetUserId = userId, targetCurrency = currency) {
    const [account, ledger] = await Promise.all([
      getBalanceAccount(targetUserId, targetCurrency),
      getBalanceLedger(targetUserId, { currency: targetCurrency, limit: 8 }),
    ]);
    setAccountResult(account);
    setLedgerResult(ledger);
  }

  async function loadDepositDetail(depositId: string) {
    const detail = await getBalanceDepositDetail(depositId, userId.trim());
    setLatestDeposit(detail.deposit_order);
    setLatestDepositDetail(detail);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(LAST_DEPOSIT_STORAGE_KEY, depositId);
    }
    return detail;
  }

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const [account, ledger] = await Promise.all([
          getBalanceAccount(userId, currency),
          getBalanceLedger(userId, { currency, limit: 8 }),
        ]);
        if (!active) return;
        setAccountResult(account);
        setLedgerResult(ledger);
      } catch (nextError) {
        if (!active) return;
        setError(nextError instanceof Error ? nextError.message : "Failed to load balance.");
      }
      if (typeof window !== "undefined") {
        const lastDepositId = window.localStorage.getItem(LAST_DEPOSIT_STORAGE_KEY);
        if (lastDepositId) {
          try {
            const detail = await getBalanceDepositDetail(lastDepositId, userId.trim());
            if (!active) return;
            setLatestDeposit(detail.deposit_order);
            setLatestDepositDetail(detail);
          } catch {
            // Ignore missing stale local storage ids.
          }
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [currency, userId]);

  useEffect(() => {
    let active = true;
    const verificationId = latestDeposit?.kyc_verification_id;
    if (!verificationId) return;
    void (async () => {
      try {
        const nextKyc = await getKycVerification(verificationId, userId.trim());
        if (!active) return;
        setKycResult(nextKyc);
      } catch {
        // keep existing state
      }
    })();
    return () => {
      active = false;
    };
  }, [latestDeposit?.kyc_verification_id, userId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const searchParams = new URLSearchParams(window.location.search);
    const stripeFlag = searchParams.get("stripe");
    if (!stripeFlag) return;
    const fromQuery = searchParams.get("deposit_order_id") || searchParams.get("depositOrderId");
    const stored = window.localStorage.getItem(LAST_DEPOSIT_STORAGE_KEY);
    const candidateId = (fromQuery || stored || "").trim();
    if (!candidateId) return;

    const shouldSyncDeposit = stripeFlag === "success";
    void (async () => {
      try {
        if (shouldSyncDeposit) {
          const synced = await postSyncBalanceDepositStripePayment(candidateId, userId.trim());
          setLatestDeposit(synced.deposit_order);
          setLatestDepositDetail(synced);
          await refreshBalanceState();
        } else {
          await loadDepositDetail(candidateId);
        }
      } catch {
        try {
          await loadDepositDetail(candidateId);
        } catch (nextError) {
          setError(nextError instanceof Error ? nextError.message : "Failed to load deposit detail.");
        }
      } finally {
        window.history.replaceState({}, "", "/balance");
      }
    })();
  }, [userId]);

  const previewPayload = previewResult?.preview as Record<string, unknown> | undefined;
  const previewRecipient = extractPreviewField(previewPayload, [
    "beneficiary_name",
    "beneficiary",
    "beneficiary_id",
    "recipient",
  ]);
  const previewAmount = extractPreviewField(previewPayload, ["amount"]);
  const previewCurrency = extractPreviewField(previewPayload, ["currency"]);
  const previewReference = extractPreviewField(previewPayload, ["reference", "memo"]);

  const kycStatus =
    kycResult?.verification?.status ||
    (latestDeposit?.next_action === "complete_kyc" ? "awaiting_kyc" : null);
  const depositMetadata =
    latestDeposit?.metadata_json && typeof latestDeposit.metadata_json === "object" ? latestDeposit.metadata_json : null;
  const lastWebhookEvent =
    depositMetadata && typeof depositMetadata.channel_last_webhook_event === "object"
      ? (depositMetadata.channel_last_webhook_event as Record<string, unknown>)
      : null;
  const duplicateWebhookEvents =
    depositMetadata && Array.isArray(depositMetadata.duplicate_webhook_events)
      ? (depositMetadata.duplicate_webhook_events as Array<Record<string, unknown>>)
      : [];
  const lastDuplicateWebhookEvent =
    depositMetadata && typeof depositMetadata.last_duplicate_webhook_event === "object"
      ? (depositMetadata.last_duplicate_webhook_event as Record<string, unknown>)
      : null;
  const depositHint = useMemo(() => {
    if (!latestDeposit) return null;
    if (latestDeposit.next_action === "complete_kyc") return t("balance.depositHintKyc");
    if (latestDeposit.next_action === "open_checkout") return t("balance.depositHintCheckout");
    if (latestDeposit.next_action === "wait_channel_confirmation") return t("balance.depositHintWaiting");
    return null;
  }, [latestDeposit, t]);

  const shouldPollDeposit =
    Boolean(activeDepositId) &&
    Boolean(latestDeposit) &&
    ["awaiting_channel_payment", "payment_processing"].includes((latestDeposit?.status || "").toLowerCase());

  const capabilitySnippet = useMemo(
    () => `{
  "tool": "mcp_capability_status",
  "arguments": {
    "user_id": "${userId}",
    "access_token": "${ACCESS_TOKEN_PLACEHOLDER}"
  }
}`,
    [userId],
  );

  const depositSnippet = useMemo(
    () => `{
  "tool": "create_balance_deposit",
  "arguments": {
    "user_id": "${userId}",
    "access_token": "${ACCESS_TOKEN_PLACEHOLDER}",
    "source_currency": "${sourceCurrency}",
    "source_amount": ${Number(sourceAmount || 0)},
    "target_currency": "${currency}",
    "reference": "${reference}"
  }
}`,
    [currency, reference, sourceAmount, sourceCurrency, userId],
  );

  const previewSnippet = useMemo(
    () => `{
  "tool": "payment_preview_from_balance",
  "arguments": {
    "user_id": "${userId}",
    "access_token": "${ACCESS_TOKEN_PLACEHOLDER}",
    "prompt": "${paymentPrompt.replaceAll("\\", "\\\\").replaceAll("\"", "\\\"")}",
    "execution_mode": "${executionMode}"
  }
}`,
    [executionMode, paymentPrompt, userId],
  );

  const confirmSnippet = useMemo(
    () =>
      `{
  "tool": "payment_confirm_from_balance",
  "arguments": {
    "user_id": "${userId}",
    "access_token": "${ACCESS_TOKEN_PLACEHOLDER}",
    "command_id": "${previewResult?.command_id || "preview-command-id"}",
    "execution_mode": "${executionMode}",
    "idempotency_key": "balance:${previewResult?.command_id || "preview-command-id"}"
  }
}`,
    [executionMode, previewResult?.command_id, userId],
  );

  const nextMcpAction = useMemo(() => {
    if (latestDeposit?.next_action === "complete_kyc") return t("balance.mcpNextKyc");
    if (latestDeposit?.next_action === "open_checkout") return t("balance.mcpNextCheckout");
    if (latestDeposit?.next_action === "wait_channel_confirmation") return t("balance.mcpNextSync");
    if (previewResult?.next_action === "confirm_now") return t("balance.mcpNextConfirm");
    return t("balance.mcpNextCapability");
  }, [latestDeposit?.next_action, previewResult?.next_action, t]);
  const treasuryGuidance = getTreasuryGuidance({
    lang,
    availableBalance: accountResult?.account.available_balance,
    lockedBalance: accountResult?.account.locked_balance,
    latestDeposit,
    previewResult,
    confirmResult,
    currency,
  });

  const liveToolOptions = useMemo(
    () => [
      { key: "capability" as const, label: t("balance.liveToolCapability"), body: t("balance.liveToolCapabilityBody") },
      { key: "deposit" as const, label: t("balance.liveToolDeposit"), body: t("balance.liveToolDepositBody") },
      { key: "sync" as const, label: t("balance.liveToolSync"), body: t("balance.liveToolSyncBody") },
      { key: "preview" as const, label: t("balance.liveToolPreview"), body: t("balance.liveToolPreviewBody") },
      { key: "confirm" as const, label: t("balance.liveToolConfirm"), body: t("balance.liveToolConfirmBody") },
    ],
    [t],
  );

  const liveMcpDemo = useMemo(() => {
    if (!showLiveDemo) return null;

    const capabilityResponse = {
      status: kycStatus === "awaiting_kyc" ? "blocked_kyc_required" : "ok",
      message:
        kycStatus === "awaiting_kyc"
          ? "Complete identity verification before using PayFi Box MCP payment tools."
          : "MCP settlement tools are enabled for this user.",
      next_action: kycStatus === "awaiting_kyc" ? "start_kyc" : "none",
      summary: {
        user_id: userId,
        kyc_status: kycStatus === "awaiting_kyc" ? "required" : kycResult?.verification?.status || "verified",
        mcp_access: kycStatus === "awaiting_kyc" ? "restricted" : "enabled",
      },
      technical_details: {
        endpoint: "http://127.0.0.1:8000/mcp/",
        available_tools:
          kycStatus === "awaiting_kyc"
            ? ["mcp_capability_status", "start_user_kyc", "get_kyc_status"]
            : [
                "get_balance",
                "get_balance_ledger",
                "create_balance_deposit",
                "start_balance_deposit_checkout",
                "sync_balance_deposit_status",
                "get_balance_deposit_detail",
                "payment_preview_from_balance",
                "payment_confirm_from_balance",
              ],
      },
    };

    const depositResponse = latestDeposit
      ? {
          status: "ok",
          message: "Balance deposit order created.",
          next_action: latestDeposit.next_action || "open_checkout",
          summary: {
            deposit_order_id: latestDeposit.id,
            status: latestDeposit.status,
            source_amount: latestDeposit.source_amount,
            source_currency: latestDeposit.source_currency,
            target_amount: latestDeposit.target_amount,
            target_currency: latestDeposit.target_currency,
          },
          technical_details: {
            reference: latestDeposit.reference,
            kyc_verification_id: latestDeposit.kyc_verification_id,
            channel_status: latestDeposit.channel_status,
          },
        }
      : {
          status: "idle",
          message: "Create a deposit order on this page to generate a live MCP response.",
          next_action: "create_balance_deposit",
        };

    const syncResponse = latestDeposit
      ? {
          status: "ok",
          message:
            latestDeposit.next_action === "wait_channel_confirmation"
              ? "Deposit status checked. Waiting for provider confirmation."
              : "Deposit status synchronized.",
          next_action: latestDeposit.next_action || "use_balance",
          summary: {
            deposit_order_id: latestDeposit.id,
            status: latestDeposit.status,
            channel_status: latestDeposit.channel_status,
            available_balance: accountResult?.account.available_balance ?? null,
            locked_balance: accountResult?.account.locked_balance ?? null,
          },
          technical_details: {
            duplicate_webhooks: duplicateWebhookEvents.length,
            latest_ledger_entry: latestDepositDetail?.latest_ledger_entry?.entry_type || null,
            last_webhook_event: lastWebhookEvent?.event_type || null,
          },
        }
      : {
          status: "idle",
          message: "No deposit order is available to sync yet.",
          next_action: "create_balance_deposit",
        };

    const previewResponse = previewResult
      ? {
          status: previewResult.status,
          message: previewResult.message,
          next_action: previewResult.next_action,
          summary: {
            command_id: previewResult.command_id,
            recipient: previewRecipient,
            amount: previewAmount,
            currency: previewCurrency,
            sufficient_balance: previewResult.balance_check?.sufficient ?? false,
          },
          technical_details: {
            available_balance: previewResult.balance_check?.available_balance,
            required_amount: previewResult.balance_check?.required_amount,
            execution_mode: executionMode,
          },
        }
      : {
          status: "idle",
          message: "Generate a balance preview on this page to see a live MCP response.",
          next_action: "payment_preview_from_balance",
        };

    const confirmResponse = confirmResult
      ? {
          status: confirmResult.status,
          message: confirmResult.message,
          next_action: confirmResult.next_action,
          summary: {
            payment_order_id: confirmResult.payment_order_id,
            execution_batch_id: confirmResult.execution_batch_id,
            payment_status: confirmResult.payment_status,
          },
          technical_details: {
            funding_source: confirmResult.funding_source,
            tx_hash: confirmResult.execution?.tx_hash || null,
            explorer_url: confirmResult.execution?.explorer_url || null,
          },
        }
      : {
          status: "idle",
          message: "Confirm a balance payment on this page to populate the live MCP receipt.",
          next_action: "payment_confirm_from_balance",
        };

    return {
      capability: {
        request: prettyJson({
          tool: "mcp_capability_status",
          arguments: { user_id: userId, access_token: ACCESS_TOKEN_PLACEHOLDER },
        }),
        response: prettyJson(capabilityResponse),
      },
      deposit: {
        request: depositSnippet,
        response: prettyJson(depositResponse),
      },
      sync: {
        request: prettyJson({
          tool: "sync_balance_deposit_status",
          arguments: {
            user_id: userId,
            access_token: ACCESS_TOKEN_PLACEHOLDER,
            deposit_order_id: latestDeposit?.id || "deposit-order-id",
          },
        }),
        response: prettyJson(syncResponse),
      },
      preview: {
        request: previewSnippet,
        response: prettyJson(previewResponse),
      },
      confirm: {
        request: confirmSnippet,
        response: prettyJson(confirmResponse),
      },
    };
  }, [
    accountResult?.account.available_balance,
    accountResult?.account.locked_balance,
    confirmResult,
    confirmSnippet,
    depositSnippet,
    duplicateWebhookEvents.length,
    executionMode,
    kycResult?.verification?.status,
    kycStatus,
    lastWebhookEvent?.event_type,
    latestDeposit,
    latestDepositDetail?.latest_ledger_entry?.entry_type,
    previewAmount,
    previewCurrency,
    previewRecipient,
    previewResult,
    previewSnippet,
    showLiveDemo,
    userId,
  ]);

  const activeLiveToolMeta = liveToolOptions.find((item) => item.key === activeLiveTool) || liveToolOptions[0];
  const activeLivePayload = showLiveDemo && liveMcpDemo ? liveMcpDemo[activeLiveTool] : null;
  const liveBundleSnippet = useMemo(
    () =>
      !showLiveDemo || !activeLivePayload
        ? ""
        : prettyJson({
            tool: activeLiveToolMeta.label,
            endpoint: "http://127.0.0.1:8000/mcp/",
            request: JSON.parse(activeLivePayload.request),
            response: JSON.parse(activeLivePayload.response),
          }),
    [activeLivePayload, activeLiveToolMeta.label, showLiveDemo],
  );

  function handleCopySnippet(key: string, value: string) {
    void navigator.clipboard.writeText(value).then(() => {
      setCopiedSnippet(key);
      window.setTimeout(() => setCopiedSnippet((current) => (current === key ? null : current)), 1600);
    });
  }

  useEffect(() => {
    if (!shouldPollDeposit || !activeDepositId) return;

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
        const detail = await postSyncBalanceDepositStripePayment(activeDepositId, userId.trim());
        if (cancelled) return;
        setLatestDeposit(detail.deposit_order);
        setLatestDepositDetail(detail);
        await refreshBalanceState();
      } catch {
        // keep polling resilient
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
  }, [activeDepositId, shouldPollDeposit, userId]);

  async function handleRefresh() {
    setLoading("refresh");
    setError(null);
    try {
      await refreshBalanceState();
      if (activeDepositId) {
        await loadDepositDetail(activeDepositId);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to refresh balance state.");
    } finally {
      setLoading(null);
    }
  }

  async function handleCreateDeposit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading("deposit");
    setError(null);
    try {
      const response = await postCreateBalanceDeposit({
        user_id: userId,
        source_currency: sourceCurrency,
        source_amount: Number(sourceAmount),
        target_currency: currency,
        reference,
      });
      setLatestDeposit(response.deposit_order);
      setLatestDepositDetail(null);
      setLatestCheckout(null);
      setKycResult(null);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(LAST_DEPOSIT_STORAGE_KEY, response.deposit_order.id);
      }
      await refreshBalanceState();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to create deposit.");
    } finally {
      setLoading(null);
    }
  }

  async function handleStartKyc() {
    setLoading("kyc");
    setError(null);
    try {
      const response = await postMerchantKycStart({
        subject_type: "user",
        subject_id: userId,
        locale: lang,
      });
      setKycResult(response);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to start identity check.");
    } finally {
      setLoading(null);
    }
  }

  async function handleStartStripe() {
    if (!activeDepositId) return;
    setLoading("stripe");
    setError(null);
    try {
      const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
      const response = await postStartBalanceDepositStripePayment(activeDepositId, {
        success_url: `${origin}/balance?stripe=success&deposit_order_id=${activeDepositId}`,
        cancel_url: `${origin}/balance?stripe=cancel&deposit_order_id=${activeDepositId}`,
        locale: lang,
      }, userId.trim());
      setLatestDeposit(response.deposit_order);
      setLatestCheckout(response.checkout || null);
      await loadDepositDetail(activeDepositId);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to open Stripe checkout.");
    } finally {
      setLoading(null);
    }
  }

  async function handleSyncDeposit() {
    if (!activeDepositId) return;
    setLoading("sync");
    setError(null);
    try {
      const detail = await postSyncBalanceDepositStripePayment(activeDepositId, userId.trim());
      setLatestDeposit(detail.deposit_order);
      setLatestDepositDetail(detail);
      await refreshBalanceState();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to sync deposit status.");
    } finally {
      setLoading(null);
    }
  }

  async function handlePreviewPayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading("preview");
    setError(null);
    setPreviewResult(null);
    setConfirmResult(null);
    try {
      const response = await postBalancePaymentPreview({
        user_id: userId,
        prompt: paymentPrompt,
        execution_mode: executionMode,
        locale: lang,
      });
      setPreviewResult(response);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to generate balance preview.");
    } finally {
      setLoading(null);
    }
  }

  async function handleConfirmPayment() {
    if (!previewResult?.command_id) return;
    setLoading("confirm");
    setError(null);
    try {
      const response = await postBalancePaymentConfirm({
        user_id: userId,
        command_id: previewResult.command_id,
        execution_mode: executionMode,
        locale: lang,
        idempotency_key: `balance:${previewResult.command_id}`,
      });
      setConfirmResult(response);
      await refreshBalanceState();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to confirm balance payment.");
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="space-y-6 motion-scale-in">
      <section className="relative overflow-hidden rounded-[36px] border border-slate-900 bg-[radial-gradient(circle_at_top_left,_rgba(115,168,255,0.24),_transparent_34%),linear-gradient(180deg,#081221_0%,#173154_58%,#5d829a_100%)] text-white shadow-[0_32px_100px_rgba(9,18,34,0.22)] motion-fade-up">
        <div className="grid gap-10 p-6 lg:grid-cols-[1.1fr_0.9fr] lg:p-8">
          <div className="space-y-6 text-white motion-fade-up">
            <p className="text-[11px] uppercase tracking-[0.3em] text-slate-300">{t("balance.badge")}</p>
            <div className="space-y-4">
              <h1 className="max-w-3xl text-4xl font-semibold tracking-[-0.04em] sm:text-5xl lg:text-6xl">
                {t("balance.title")}
              </h1>
              <p className="max-w-2xl text-base leading-7 text-slate-200 sm:text-lg">{t("balance.intro")}</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-3xl border border-white/12 bg-white/6 p-4 backdrop-blur surface-transition motion-scale-in motion-delay-1">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-300">{t("balance.available")}</p>
                <p className="mt-3 text-3xl font-semibold">{formatAmount(accountResult?.account.available_balance)}</p>
              </div>
              <div className="rounded-3xl border border-white/12 bg-white/6 p-4 backdrop-blur surface-transition motion-scale-in motion-delay-2">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-300">{t("balance.locked")}</p>
                <p className="mt-3 text-3xl font-semibold">{formatAmount(accountResult?.account.locked_balance)}</p>
              </div>
              <div className="rounded-3xl border border-white/12 bg-white/6 p-4 backdrop-blur surface-transition motion-scale-in motion-delay-3">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-300">{t("balance.accountStatus")}</p>
                <div className="mt-3">
                  <StatusBadge status={accountResult?.account.status || "pending"} />
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-[30px] border border-white/12 bg-white/[0.08] p-6 text-white shadow-[0_20px_60px_rgba(8,18,33,0.3)] backdrop-blur-xl surface-transition motion-fade-up motion-delay-1">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.26em] text-slate-300">{t("balance.accountTitle")}</p>
                <p className="mt-2 text-sm leading-6 text-slate-200">{t("balance.accountBody")}</p>
              </div>
              <button
                type="button"
                onClick={handleRefresh}
                className="rounded-xl border border-white/14 bg-white/10 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/16"
              >
                {loading === "refresh" ? `${t("common.loading")}` : t("balance.refresh")}
              </button>
            </div>
            <div className="mt-6 space-y-4 rounded-3xl border border-white/10 bg-[#0f2038]/70 p-5">
              <label className="space-y-2 text-sm">
                <span className="text-slate-300">{t("balance.userId")}</span>
                <input
                  value={userId}
                  onChange={(event) => setUserId(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/8 px-4 py-3 text-sm text-white outline-none ring-sky-200/50 transition focus:ring-2"
                />
              </label>
              <label className="space-y-2 text-sm">
                <span className="text-slate-300">{t("balance.currency")}</span>
                <select
                  value={currency}
                  onChange={(event) => setCurrency(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/8 px-4 py-3 text-sm text-white outline-none ring-sky-200/50 transition focus:ring-2"
                >
                  <option value="USDT">USDT</option>
                  <option value="USDC">USDC</option>
                </select>
              </label>
              {error ? <div className="rounded-2xl border border-rose-300/30 bg-rose-500/12 px-4 py-3 text-sm text-rose-100">{error}</div> : null}
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-[30px] border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-5 shadow-sm motion-fade-up motion-delay-1 surface-transition">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#496896]">{treasuryGuidance.title}</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-900">
              {lang === "zh" ? "资金判断" : "Treasury guidance"}
            </h2>
          </div>
          <StatusBadge status={treasuryGuidance.status} />
        </div>
        <p className="mt-3 text-sm leading-7 text-slate-700">{treasuryGuidance.summary}</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-[#d8e1f0] bg-white px-4 py-4">
            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
              {lang === "zh" ? "下一步建议" : "Recommended next step"}
            </p>
            <p className="mt-2 text-sm font-medium leading-7 text-slate-900">{treasuryGuidance.nextStep}</p>
          </div>
          <div className="rounded-2xl border border-[#d8e1f0] bg-white px-4 py-4">
            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
              {lang === "zh" ? "为什么系统这样建议" : "Why the system recommends this"}
            </p>
            <p className="mt-2 text-sm leading-7 text-slate-700">{treasuryGuidance.detail}</p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {treasuryGuidance.chips.map((chip) => (
            <span
              key={chip}
              className="rounded-full border border-[#c8d4ea] bg-white px-2.5 py-1 text-xs font-medium text-slate-700"
            >
              {chip}
            </span>
          ))}
        </div>
      </section>

      <section className="grid gap-6 motion-fade-up motion-delay-1 lg:grid-cols-[1.02fr_0.98fr]">
        <div className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("balance.quickPathLabel")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("balance.quickPathTitle")}</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">{t("balance.quickPathBody")}</p>
          <div className="mt-6 grid gap-3">
            {[t("balance.quickPathStepOne"), t("balance.quickPathStepTwo"), t("balance.quickPathStepThree")].map((item) => (
              <div key={item} className="rounded-[22px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-4 text-sm leading-6 text-slate-700">
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("balance.snapshotTitle")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("balance.snapshotTitle")}</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">{t("balance.snapshotBody")}</p>
          <div className="mt-6 grid gap-3">
            <div className="rounded-[22px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] px-4 py-4">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.snapshotUser")}</p>
              <p className="mt-3 break-all font-mono text-sm text-slate-900">{userId}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[22px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.snapshotDeposit")}</p>
                <p className="mt-3 text-sm font-semibold text-slate-900">{latestDeposit?.status || t("common.noData")}</p>
                <p className="mt-2 text-sm text-slate-600">
                  {latestDeposit ? `${formatAmount(latestDeposit.target_amount)} ${latestDeposit.target_currency}` : "-"}
                </p>
              </div>
              <div className="rounded-[22px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.snapshotNext")}</p>
                <p className="mt-3 text-sm font-semibold text-slate-900">{depositHint || nextMcpAction}</p>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-[20px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] px-4 py-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{t("balance.available")}</p>
                <p className="mt-2 text-lg font-semibold text-slate-950">{formatAmount(accountResult?.account.available_balance)}</p>
              </div>
              <div className="rounded-[20px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] px-4 py-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{t("balance.locked")}</p>
                <p className="mt-2 text-lg font-semibold text-slate-950">{formatAmount(accountResult?.account.locked_balance)}</p>
              </div>
              <div className="rounded-[20px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] px-4 py-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{t("common.status")}</p>
                <div className="mt-2"><StatusBadge status={accountResult?.account.status || "pending"} /></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 motion-fade-up motion-delay-2 lg:grid-cols-[1.06fr_0.94fr]">
        <form onSubmit={handleCreateDeposit} className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition motion-scale-in motion-delay-1">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-950">{t("balance.depositTitle")}</p>
            <p className="text-sm leading-6 text-slate-600">{t("balance.depositBody")}</p>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-sm text-slate-700">
              <span>{t("balance.sourceCurrency")}</span>
              <select
                value={sourceCurrency}
                onChange={(event) => setSourceCurrency(event.target.value)}
                className="w-full rounded-xl border border-[#c8d4ea] bg-white px-4 py-3 outline-none ring-[#496896] transition focus:ring-2"
              >
                <option value="USD">USD</option>
                <option value="HKD">HKD</option>
                <option value="CNY">CNY</option>
              </select>
            </label>
            <label className="space-y-2 text-sm text-slate-700">
              <span>{t("balance.sourceAmount")}</span>
              <input
                value={sourceAmount}
                onChange={(event) => setSourceAmount(event.target.value)}
                className="w-full rounded-xl border border-[#c8d4ea] bg-white px-4 py-3 outline-none ring-[#496896] transition focus:ring-2"
              />
            </label>
            <label className="space-y-2 text-sm text-slate-700">
              <span>{t("balance.targetCurrency")}</span>
              <select
                value={currency}
                onChange={(event) => setCurrency(event.target.value)}
                className="w-full rounded-xl border border-[#c8d4ea] bg-white px-4 py-3 outline-none ring-[#496896] transition focus:ring-2"
              >
                <option value="USDT">USDT</option>
                <option value="USDC">USDC</option>
              </select>
            </label>
            <label className="space-y-2 text-sm text-slate-700">
              <span>{t("balance.reference")}</span>
              <input
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                className="w-full rounded-xl border border-[#c8d4ea] bg-white px-4 py-3 outline-none ring-[#496896] transition focus:ring-2"
              />
            </label>
          </div>
          <button
            type="submit"
            className="mt-6 rounded-xl bg-[#0b1730] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#163358]"
          >
            {loading === "deposit" ? t("common.loading") : t("balance.createDeposit")}
          </button>
        </form>

        <div className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition motion-scale-in motion-delay-2">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-950">{t("balance.latestDepositTitle")}</p>
            <p className="text-sm leading-6 text-slate-600">{t("balance.latestDepositBody")}</p>
          </div>
          {!latestDeposit ? (
            <div className="mt-6">
              <EmptyStateCard title={t("balance.noDeposit")} description={t("balance.depositBody")} />
            </div>
          ) : (
            <div className="mt-6 space-y-4">
              <div className="grid gap-4 rounded-[24px] border border-[#d8e1f0] bg-[#f7f9fd] p-5 sm:grid-cols-2 surface-transition">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{t("common.status")}</p>
                  <div className="mt-2">
                    <StatusBadge status={latestDeposit.status} />
                  </div>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{t("common.nextAction")}</p>
                  <div className="mt-2">
                    <StatusBadge status={latestDeposit.next_action || "none"} />
                  </div>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{t("balance.sourceAmount")}</p>
                  <p className="mt-2 text-lg font-semibold text-slate-950">
                    {formatAmount(latestDeposit.source_amount)} {latestDeposit.source_currency}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{t("balance.targetCurrency")}</p>
                  <p className="mt-2 text-lg font-semibold text-slate-950">
                    {formatAmount(latestDeposit.target_amount)} {latestDeposit.target_currency}
                  </p>
                </div>
              </div>

              {depositHint ? <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">{depositHint}</div> : null}

              {lastWebhookEvent || duplicateWebhookEvents.length > 0 ? (
                <div className="rounded-[24px] border border-[#d8e1f0] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] p-5 surface-transition">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-slate-950">{t("balance.webhookAuditTitle")}</p>
                      <p className="text-sm leading-6 text-slate-600">{t("balance.webhookAuditBody")}</p>
                    </div>
                    {duplicateWebhookEvents.length > 0 ? (
                      <div className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
                        {t("balance.webhookDuplicates")} {duplicateWebhookEvents.length}
                      </div>
                    ) : null}
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-[#d8e1f0] bg-white px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.lastWebhook")}</p>
                      <p className="mt-2 font-medium text-slate-950">
                        {lastWebhookEvent ? String(lastWebhookEvent.event_type || "-") : "-"}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {lastWebhookEvent ? formatTime(String(lastWebhookEvent.received_at || "")) : "-"}
                      </p>
                    </div>
                    <div className="rounded-xl border border-[#d8e1f0] bg-white px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.lastDuplicateWebhook")}</p>
                      <p className="mt-2 font-medium text-slate-950">
                        {lastDuplicateWebhookEvent ? String(lastDuplicateWebhookEvent.event_type || "-") : "-"}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {lastDuplicateWebhookEvent ? formatTime(String(lastDuplicateWebhookEvent.received_at || "")) : "-"}
                      </p>
                    </div>
                  </div>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={handleStartKyc}
                  className="rounded-xl border border-[#c8d4ea] bg-white px-4 py-2.5 text-sm font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
                >
                  {loading === "kyc" ? t("common.loading") : t("balance.startKyc")}
                </button>
                <button
                  type="button"
                  onClick={handleStartStripe}
                  className="rounded-xl bg-[#0b1730] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#163358]"
                >
                  {loading === "stripe" ? t("common.loading") : t("balance.openCheckout")}
                </button>
                <button
                  type="button"
                  onClick={handleSyncDeposit}
                  className="rounded-xl border border-[#c8d4ea] bg-white px-4 py-2.5 text-sm font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
                >
                  {loading === "sync" ? t("common.loading") : t("balance.syncDeposit")}
                </button>
              </div>

              {latestCheckout?.checkout_url || latestDeposit.channel_checkout_url ? (
                <a
                  href={latestCheckout?.checkout_url || latestDeposit.channel_checkout_url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex rounded-xl border border-[#c8d4ea] bg-[#edf3ff] px-4 py-3 text-sm font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#e3edff]"
                >
                  {t("balance.openCheckout")}
                </a>
              ) : null}

              <div className="grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
                <div className="rounded-xl border border-[#d8e1f0] bg-white px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">FX</p>
                  <p className="mt-2 font-medium text-slate-950">{latestDeposit.fx_rate}</p>
                </div>
                <div className="rounded-xl border border-[#d8e1f0] bg-white px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Fee</p>
                  <p className="mt-2 font-medium text-slate-950">{formatAmount(latestDeposit.fee_amount)}</p>
                </div>
                <div className="rounded-xl border border-[#d8e1f0] bg-white px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">KYC</p>
                  <div className="mt-2">
                    <StatusBadge status={kycResult?.verification?.status || kycStatus || "pending"} />
                  </div>
                </div>
                <div className="rounded-xl border border-[#d8e1f0] bg-white px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.latestLedger")}</p>
                  <p className="mt-2 font-medium text-slate-950">
                    {latestDepositDetail?.latest_ledger_entry
                      ? `${latestDepositDetail.latest_ledger_entry.entry_type} · ${formatAmount(latestDepositDetail.latest_ledger_entry.amount)}`
                      : "-"}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="grid gap-6 motion-fade-up motion-delay-3 lg:grid-cols-[0.98fr_1.02fr]">
        <div className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition motion-scale-in motion-delay-1">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-950">{t("balance.mcpBridgeTitle")}</p>
            <p className="text-sm leading-6 text-slate-600">{t("balance.mcpBridgeBody")}</p>
          </div>

          <div className="mt-6 grid gap-4 rounded-[24px] border border-[#d8e1f0] bg-[#f7f9fd] p-5 sm:grid-cols-2 surface-transition">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.userId")}</p>
              <p className="mt-2 break-all text-sm font-semibold text-slate-950">{userId}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.mcpNextActionLabel")}</p>
              <p className="mt-2 text-sm font-semibold text-slate-950">{nextMcpAction}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.available")}</p>
              <p className="mt-2 text-lg font-semibold text-slate-950">
                {formatAmount(accountResult?.account.available_balance)} {accountResult?.account.currency || currency}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.mcpEndpointLabel")}</p>
              <p className="mt-2 text-sm font-medium text-slate-950">http://127.0.0.1:8000/mcp/</p>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-3">
            <Link
              href="/mcp"
              className="rounded-xl bg-[#0b1730] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#163358]"
            >
              {t("balance.openMcpGuide")}
            </Link>
            <Link
              href="/command-center"
              className="rounded-xl border border-[#c8d4ea] bg-white px-4 py-2.5 text-sm font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
            >
              {t("balance.openSettlementIntake")}
            </Link>
          </div>
        </div>

        <details
          className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition motion-scale-in motion-delay-2"
          onToggle={(event) => setShowMcpExamples(event.currentTarget.open)}
        >
          <summary className="cursor-pointer text-sm font-semibold text-slate-950">
            {t("balance.mcpExamplesToggle")}
          </summary>
          {showMcpExamples ? (
            <>
              <p className="mt-3 text-sm leading-6 text-slate-600">{t("balance.mcpExamplesBody")}</p>
              <div className="mt-6 space-y-4">
                <SnippetBlock
                  title={t("balance.mcpSnippetCapability")}
                  snippet={capabilitySnippet}
                  onCopy={() => handleCopySnippet("capability", capabilitySnippet)}
                  copied={copiedSnippet === "capability"}
                  copyLabel={t("balance.copySnippet")}
                  copiedLabel={t("balance.copiedSnippet")}
                />
                <SnippetBlock
                  title={t("balance.mcpSnippetDeposit")}
                  snippet={depositSnippet}
                  onCopy={() => handleCopySnippet("deposit", depositSnippet)}
                  copied={copiedSnippet === "deposit"}
                  copyLabel={t("balance.copySnippet")}
                  copiedLabel={t("balance.copiedSnippet")}
                />
                <SnippetBlock
                  title={t("balance.mcpSnippetPreview")}
                  snippet={previewSnippet}
                  onCopy={() => handleCopySnippet("preview", previewSnippet)}
                  copied={copiedSnippet === "preview"}
                  copyLabel={t("balance.copySnippet")}
                  copiedLabel={t("balance.copiedSnippet")}
                />
              </div>
            </>
          ) : null}
        </details>
      </section>

      <section className="motion-fade-up motion-delay-3">
        <details
          className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition motion-scale-in"
          onToggle={(event) => setShowLiveDemo(event.currentTarget.open)}
        >
          <summary className="cursor-pointer text-sm font-semibold text-slate-950">
            {t("balance.liveDemoToggle")}
          </summary>
          {showLiveDemo && activeLivePayload ? (
            <>
              <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-slate-950">{t("balance.liveDemoTitle")}</p>
                  <p className="max-w-3xl text-sm leading-6 text-slate-600">{t("balance.liveDemoToggleBody")}</p>
                </div>
                <div className="inline-flex items-center rounded-full border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-1.5 text-xs font-medium text-slate-500">
                  {t("balance.liveDemoHint")}
                </div>
              </div>

              <div className="mt-6 grid gap-6 lg:grid-cols-[0.36fr_0.64fr]">
                <div className="space-y-3">
                  {liveToolOptions.map((tool) => (
                    <button
                      key={tool.key}
                      type="button"
                      onClick={() => setActiveLiveTool(tool.key)}
                      className={`w-full rounded-[24px] border px-4 py-4 text-left transition ${
                        activeLiveTool === tool.key
                          ? "border-[#8fb3e4] bg-[#edf4ff] shadow-sm"
                          : "border-[#d8e1f0] bg-[#f9fbff] hover:border-[#c1d3ee] hover:bg-white"
                      }`}
                    >
                      <p className="text-sm font-semibold text-slate-950">{tool.label}</p>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{tool.body}</p>
                    </button>
                  ))}
                </div>

                <div className="space-y-4">
                  <div className="rounded-[24px] border border-[#d8e1f0] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.liveSelectedTool")}</p>
                        <p className="mt-2 text-lg font-semibold text-slate-950">{activeLiveToolMeta.label}</p>
                        <p className="mt-2 text-sm leading-6 text-slate-600">{activeLiveToolMeta.body}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => handleCopySnippet(`live-${activeLiveTool}-response`, activeLivePayload.response)}
                          className="rounded-full border border-[#c7d7ee] bg-white px-3 py-1 text-xs font-medium text-[#163358] transition hover:bg-[#edf3ff]"
                        >
                          {copiedSnippet === `live-${activeLiveTool}-response` ? t("balance.copiedSnippet") : t("balance.copyResponse")}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCopySnippet(`live-${activeLiveTool}-bundle`, liveBundleSnippet)}
                          className="rounded-full border border-[#c7d7ee] bg-white px-3 py-1 text-xs font-medium text-[#163358] transition hover:bg-[#edf3ff]"
                        >
                          {copiedSnippet === `live-${activeLiveTool}-bundle` ? t("balance.copiedSnippet") : t("balance.copyBundle")}
                        </button>
                      </div>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-[18px] border border-[#d8e3f2] bg-white px-3 py-3">
                        <p className="text-[10px] uppercase tracking-[0.22em] text-slate-400">{t("common.status")}</p>
                        <p className="mt-2 text-sm font-semibold text-slate-950">
                          {activeLiveTool === "capability"
                            ? (kycStatus === "awaiting_kyc" ? "blocked_kyc_required" : "ok")
                            : activeLiveTool === "deposit" || activeLiveTool === "sync"
                              ? latestDeposit?.status || "idle"
                              : activeLiveTool === "preview"
                                ? previewResult?.status || "idle"
                                : confirmResult?.status || "idle"}
                        </p>
                      </div>
                      <div className="rounded-[18px] border border-[#d8e3f2] bg-white px-3 py-3">
                        <p className="text-[10px] uppercase tracking-[0.22em] text-slate-400">{t("common.nextAction")}</p>
                        <p className="mt-2 text-sm font-semibold text-slate-950">
                          {activeLiveTool === "capability"
                            ? (kycStatus === "awaiting_kyc" ? "start_kyc" : "none")
                            : activeLiveTool === "deposit" || activeLiveTool === "sync"
                              ? latestDeposit?.next_action || "create_balance_deposit"
                              : activeLiveTool === "preview"
                                ? previewResult?.next_action || "payment_preview_from_balance"
                                : confirmResult?.next_action || "payment_confirm_from_balance"}
                        </p>
                      </div>
                      <div className="rounded-[18px] border border-[#d8e3f2] bg-white px-3 py-3">
                        <p className="text-[10px] uppercase tracking-[0.22em] text-slate-400">endpoint</p>
                        <p className="mt-2 truncate font-mono text-sm text-slate-950">/mcp/</p>
                      </div>
                    </div>
                  </div>

                  <SnippetBlock
                    title={t("balance.liveBundleTitle")}
                    snippet={liveBundleSnippet}
                    onCopy={() => handleCopySnippet(`live-${activeLiveTool}-bundle`, liveBundleSnippet)}
                    copied={copiedSnippet === `live-${activeLiveTool}-bundle`}
                    copyLabel={t("balance.copyBundle")}
                    copiedLabel={t("balance.copiedSnippet")}
                  />

                  <div className="grid gap-4 xl:grid-cols-2">
                    <SnippetBlock
                      title={t("balance.liveRequestTitle")}
                      snippet={activeLivePayload.request}
                      onCopy={() => handleCopySnippet(`live-${activeLiveTool}-request`, activeLivePayload.request)}
                      copied={copiedSnippet === `live-${activeLiveTool}-request`}
                      copyLabel={t("balance.copySnippet")}
                      copiedLabel={t("balance.copiedSnippet")}
                    />
                    <SnippetBlock
                      title={t("balance.liveResponseTitle")}
                      snippet={activeLivePayload.response}
                      onCopy={() => handleCopySnippet(`live-${activeLiveTool}-response`, activeLivePayload.response)}
                      copied={copiedSnippet === `live-${activeLiveTool}-response`}
                      copyLabel={t("balance.copyResponse")}
                      copiedLabel={t("balance.copiedSnippet")}
                    />
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </details>
      </section>

      <section className="grid gap-6 motion-fade-up motion-delay-3 lg:grid-cols-[1.06fr_0.94fr]">
        <form onSubmit={handlePreviewPayment} className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition motion-scale-in motion-delay-1">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-950">{t("balance.paymentTitle")}</p>
            <p className="text-sm leading-6 text-slate-600">{t("balance.paymentBody")}</p>
          </div>
          <div className="mt-6 space-y-4">
            <label className="block space-y-2 text-sm text-slate-700">
              <span>{t("balance.promptLabel")}</span>
              <textarea
                value={paymentPrompt}
                onChange={(event) => setPaymentPrompt(event.target.value)}
                rows={5}
                className="w-full rounded-[22px] border border-[#c8d4ea] bg-white px-4 py-4 outline-none ring-[#496896] transition focus:ring-2"
                placeholder={t("balance.promptPlaceholder")}
              />
            </label>
            <label className="block space-y-2 text-sm text-slate-700">
              <span>{t("command.executionMode")}</span>
              <select
                value={executionMode}
                onChange={(event) => setExecutionMode(event.target.value as ExecutionMode)}
                className="w-full rounded-xl border border-[#c8d4ea] bg-white px-4 py-3 outline-none ring-[#496896] transition focus:ring-2"
              >
                <option value="operator">{statusLabel("operator")}</option>
                <option value="user_wallet">{statusLabel("user_wallet")}</option>
                <option value="safe">{statusLabel("safe")}</option>
              </select>
            </label>
            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                className="rounded-xl bg-[#0b1730] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#163358]"
              >
                {loading === "preview" ? t("common.loading") : t("balance.preview")}
              </button>
              <button
                type="button"
                onClick={handleConfirmPayment}
                disabled={!previewResult?.command_id || loading === "confirm"}
                className="rounded-xl border border-[#c8d4ea] bg-white px-5 py-3 text-sm font-semibold text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading === "confirm" ? t("common.loading") : t("balance.confirm")}
              </button>
            </div>
          </div>
        </form>

        <div className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition motion-scale-in motion-delay-2">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-950">{t("balance.balanceCheck")}</p>
            <p className="text-sm leading-6 text-slate-600">{previewResult?.message || t("balance.paymentBody")}</p>
          </div>

          {!previewResult ? (
            <div className="mt-6">
              <EmptyStateCard title={t("balance.paymentTitle")} description={t("balance.paymentBody")} />
            </div>
          ) : (
            <div className="mt-6 space-y-4">
              <div className="grid gap-4 rounded-[24px] border border-[#d8e1f0] bg-[#f7f9fd] p-5 sm:grid-cols-2 surface-transition">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("recipient.label")}</p>
                  <p className="mt-2 text-lg font-semibold text-slate-950">{previewRecipient}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("common.amount")}</p>
                  <p className="mt-2 text-lg font-semibold text-slate-950">{previewAmount} {previewCurrency !== "-" ? previewCurrency : ""}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("common.reference")}</p>
                  <p className="mt-2 text-sm font-medium text-slate-950">{previewReference}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("common.nextAction")}</p>
                  <div className="mt-2">
                    <StatusBadge status={previewResult.next_action || "none"} />
                  </div>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl border border-[#d8e1f0] bg-white px-4 py-3 surface-transition">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.available")}</p>
                  <p className="mt-2 text-lg font-semibold text-slate-950">
                    {formatAmount(previewResult.balance_check?.available_balance)} {previewResult.balance_check?.currency || currency}
                  </p>
                </div>
                <div className="rounded-xl border border-[#d8e1f0] bg-white px-4 py-3 surface-transition">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{t("balance.requiredAmount")}</p>
                  <p className="mt-2 text-lg font-semibold text-slate-950">
                    {formatAmount(previewResult.balance_check?.required_amount)} {previewResult.balance_check?.currency || currency}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <StatusBadge status={previewResult.balance_check?.sufficient ? "allow" : "blocked"} />
                <span className="text-sm text-slate-600">
                  {previewResult.balance_check?.sufficient ? t("balance.sufficient") : previewResult.balance_check?.reason || t("common.error")}
                </span>
              </div>

              {confirmResult ? (
                <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-5 surface-transition motion-fade-up">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-emerald-900">{confirmResult.message}</p>
                      <p className="mt-2 text-sm text-emerald-800">
                        {confirmResult.payment_order_id ? `${t("merchant.paymentOrderId")}: ${confirmResult.payment_order_id}` : "-"}
                      </p>
                    </div>
                    <div className="flex gap-3">
                      <StatusBadge status={confirmResult.payment_status || confirmResult.status} />
                      <StatusBadge status={confirmResult.next_action || "none"} />
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3">
                    {confirmResult.payment_order_id ? (
                      <Link
                        href={`/payments/${confirmResult.payment_order_id}`}
                      className="rounded-xl bg-[#0b1730] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#163358]"
                      >
                        {t("balance.openPayment")}
                      </Link>
                    ) : null}
                    {confirmResult.execution?.explorer_url ? (
                      <a
                        href={confirmResult.execution.explorer_url}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-xl border border-[#c8d4ea] bg-white px-4 py-2.5 text-sm font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
                      >
                        {t("common.openExplorer")}
                      </a>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </section>

      <section className="motion-fade-up motion-delay-4">
        <div className="rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm surface-transition motion-scale-in">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-950">{t("balance.ledgerTitle")}</p>
            <p className="text-sm leading-6 text-slate-600">{t("balance.ledgerBody")}</p>
          </div>
          {ledgerResult?.items?.length ? (
            <div className="mt-6 overflow-x-auto">
              <table className="min-w-full text-left text-sm text-slate-700">
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase tracking-[0.24em] text-slate-400">
                    <th className="px-3 py-3">{t("common.status")}</th>
                    <th className="px-3 py-3">{t("common.amount")}</th>
                    <th className="px-3 py-3">{t("balance.latestLedger")}</th>
                    <th className="px-3 py-3">Before</th>
                    <th className="px-3 py-3">After</th>
                    <th className="px-3 py-3">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {ledgerResult.items.map((item) => (
                    <tr key={item.id} className="border-b border-slate-100">
                      <td className="px-3 py-4"><StatusBadge status={item.entry_type} /></td>
                      <td className="px-3 py-4 font-medium text-slate-950">{formatAmount(item.amount)}</td>
                      <td className="px-3 py-4 text-slate-600">{item.description || item.reference_type || "-"}</td>
                      <td className="px-3 py-4 text-slate-600">{formatAmount(item.balance_before)}</td>
                      <td className="px-3 py-4 text-slate-600">{formatAmount(item.balance_after)}</td>
                      <td className="px-3 py-4 text-slate-500">{formatTime(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="mt-6">
              <EmptyStateCard title={t("common.noData")} description={t("balance.ledgerBody")} />
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
