"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  type CommandResponse,
  type ConfirmResponse,
  postExecutionItemAttachSafeProposal,
  postExecutionItemAttachTx,
  postExecutionItemSyncReceipt,
  postCommand,
  postConfirm,
} from "../../lib/api";
import {
  buildExamplePrompts,
  buildPaymentCommand,
  getAiConfidence,
  getAiPlanSummary,
  getAiReasonList,
  getAiRouteSteps,
  getClarificationCopy,
  getRouteRecommendation,
  parsePaymentPreview,
  type ExecutionMode,
} from "../../lib/command-copilot";
import { useI18n } from "../../lib/i18n-provider";
import { useRecipientDirectory } from "../../lib/use-recipient-directory";
import {
  formatRecipientLabel,
} from "../../lib/recipient-book";
import { DeferredPanelShell } from "../../components/deferred-panel-shell";
import { RecipientSelector } from "../../components/recipient-selector";
import { EmptyStateCard } from "../../components/empty-state-card";
import { RiskSummaryCard } from "../../components/risk-summary-card";
import { StatusBadge } from "../../components/status-badge";
import { ModeNextStepCard } from "../../components/mode-next-step-card";
import { PreviewSummaryCard } from "../../components/preview-summary-card";
import { PrimaryActionCard } from "../../components/primary-action-card";
const TechnicalDetailsAccordion = dynamic(
  () => import("../../components/technical-details-accordion").then((mod) => mod.TechnicalDetailsAccordion),
  { loading: () => <DeferredPanelShell /> },
);
const ExecutionAttachPanel = dynamic(
  () => import("../../components/execution-attach-panel").then((mod) => mod.ExecutionAttachPanel),
  { loading: () => <DeferredPanelShell /> },
);
type PreviewPhase = "idle" | "loading" | "ready" | "error";

export default function CommandCenterPage() {
  const { lang, t, statusLabel } = useI18n();
  const examplePrompts = useMemo(() => buildExamplePrompts(lang), [lang]);
  const aiSummaries = [
    { title: t("command.aiIntakeTitle"), body: t("command.aiIntakeBody") },
    { title: t("command.aiRiskTitle"), body: t("command.aiRiskBody") },
    { title: t("command.aiRouteTitle"), body: t("command.aiRouteBody") },
  ];

  const [userId, setUserId] = useState("deaa3ed3-c910-53d0-8796-755d9c82add6");
  const [sessionId, setSessionId] = useState("5ad9af15-ca05-5124-8ae6-3492f0090dca");
  const [amount, setAmount] = useState("100");
  const [currency, setCurrency] = useState("USDT");
  const [reference, setReference] = useState("INV-SETTLEMENT-001");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("operator");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [customPrompt, setCustomPrompt] = useState("");

  const [commandResult, setCommandResult] = useState<CommandResponse | null>(null);
  const [confirmResult, setConfirmResult] = useState<ConfirmResponse | null>(null);
  const [previewPhase, setPreviewPhase] = useState<PreviewPhase>("idle");
  const [boundCommandId, setBoundCommandId] = useState<string | null>(null);
  const latestRequestSeq = useRef(0);

  const [loadingCommand, setLoadingCommand] = useState(false);
  const [loadingConfirm, setLoadingConfirm] = useState(false);
  const [loadingAttach, setLoadingAttach] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [showAttachPanel, setShowAttachPanel] = useState(false);

  const {
    recipients,
    selectedRecipientId,
    setSelectedRecipientId,
    selectedRecipient,
    addRecipient,
  } = useRecipientDirectory(30);

  const parsedPreview = useMemo(() => parsePaymentPreview(commandResult), [commandResult]);

  const derivedPrompt = useMemo(() => {
    return buildPaymentCommand({
      lang,
      recipientName: selectedRecipient?.name || "",
      amount,
      currency,
      reference,
    });
  }, [lang, selectedRecipient?.name, amount, currency, reference]);

  const effectivePrompt = customPrompt.trim() || derivedPrompt;
  const canConfirm =
    previewPhase === "ready" &&
    !!commandResult &&
    !!boundCommandId &&
    boundCommandId === commandResult.command_id;
  const aiRouteValue = confirmResult?.next_action || commandResult?.next_action || executionMode;
  const aiRiskValue = commandResult?.risk?.decision || commandResult?.risk?.risk_level || "pending";
  const aiPlanSummary = getAiPlanSummary({
    t,
    hasPreview: Boolean(commandResult),
    missingFields: commandResult?.missing_fields ?? [],
    riskDecision: commandResult?.risk?.decision,
    mode: executionMode,
  });
  const aiReasonList = getAiReasonList({
    t,
    mode: executionMode,
    riskDecision: commandResult?.risk?.decision,
    missingFields: commandResult?.missing_fields ?? [],
    splitCount: parsedPreview?.splitCount,
  });
  const aiConfidence = getAiConfidence({
    missingFields: commandResult?.missing_fields ?? [],
    riskDecision: commandResult?.risk?.decision,
    splitCount: parsedPreview?.splitCount,
  });
  const clarification = getClarificationCopy(
    lang,
    commandResult?.missing_fields ?? [],
    commandResult?.follow_up_question,
  );
  const routeRecommendation = getRouteRecommendation({
    lang,
    selectedMode: executionMode,
    riskDecision: commandResult?.risk?.decision,
    missingFields: commandResult?.missing_fields ?? [],
    splitCount: parsedPreview?.splitCount,
    amount: parsedPreview?.amount ?? Number(amount),
  });
  const aiRouteSteps = getAiRouteSteps({
    t,
    mode: routeRecommendation.recommendedMode,
    riskDecision: commandResult?.risk?.decision,
  });

  function handleCreateRecipient(payload: {
    name: string;
    address: string;
    network: string;
    note?: string;
  }) {
    addRecipient(payload);
  }

  async function handleSubmitCommand(event: FormEvent) {
    event.preventDefault();
    const requestSeq = ++latestRequestSeq.current;
    setLoadingCommand(true);
    setError(null);
    setInfoMessage(null);
    setPreviewPhase("loading");

    // Prevent stale preview confirmation by clearing previous response state.
    setCommandResult(null);
    setConfirmResult(null);
    setBoundCommandId(null);

    try {
      const response = await postCommand({
        user_id: userId.trim(),
        session_id: sessionId.trim(),
        text: effectivePrompt,
        channel: "web",
        locale: lang === "zh" ? "zh-CN" : "en-US",
      });
      if (requestSeq !== latestRequestSeq.current) return;
      setCommandResult(response);
      setBoundCommandId(response.command_id);
      setPreviewPhase("ready");
    } catch (err) {
      if (requestSeq !== latestRequestSeq.current) return;
      const message = err instanceof Error ? err.message : t("common.error");
      setError(message);
      setPreviewPhase("error");
    } finally {
      if (requestSeq === latestRequestSeq.current) {
        setLoadingCommand(false);
      }
    }
  }

  async function handleConfirm() {
    if (!canConfirm || !boundCommandId) return;
    setLoadingConfirm(true);
    setError(null);
    setInfoMessage(null);
    try {
      const response = await postConfirm({
        command_id: boundCommandId,
        confirmed: true,
        execution_mode: executionMode,
        idempotency_key: idempotencyKey.trim() || undefined,
        locale: lang === "zh" ? "zh-CN" : "en-US",
      });
      if (response.command_id !== boundCommandId) {
        setError(t("command.staleConfirmGuard"));
        return;
      }
      setConfirmResult(response);
      setShowAttachPanel(response.execution_mode !== "operator");
    } catch (err) {
      const message = err instanceof Error ? err.message : t("common.error");
      setError(message);
    } finally {
      setLoadingConfirm(false);
    }
  }

  async function copyToClipboard(value: string, successMessage: string) {
    try {
      await navigator.clipboard.writeText(value);
      setInfoMessage(successMessage);
    } catch {
      setError(t("command.copyFailed"));
    }
  }

  async function handleCopyUnsigned() {
    if (!confirmResult?.unsigned_transactions?.length) {
      setInfoMessage(t("command.noUnsignedPayload"));
      return;
    }
    await copyToClipboard(
      JSON.stringify(confirmResult.unsigned_transactions, null, 2),
      t("command.copiedUnsignedPayload"),
    );
  }

  async function handleCopySafeProposal() {
    if (!confirmResult?.safe_proposal) {
      setInfoMessage(t("command.noSafePayload"));
      return;
    }
    await copyToClipboard(
      JSON.stringify(confirmResult.safe_proposal, null, 2),
      t("command.copiedSafePayload"),
    );
  }

  function handleAttachTx() {
    setShowAttachPanel(true);
  }

  async function handleAttachTxSubmit(input: {
    executionItemId: string;
    txHash: string;
    walletAddress?: string;
  }) {
    setLoadingAttach(true);
    setError(null);
    setInfoMessage(null);
    try {
      const result = await postExecutionItemAttachTx(input.executionItemId, {
        tx_hash: input.txHash,
        wallet_address: input.walletAddress || null,
        locale: lang === "zh" ? "zh-CN" : "en-US",
      });
      setInfoMessage(result.message);
      setConfirmResult((current) => {
        if (!current) return current;
        return {
          ...current,
          execution_items: current.execution_items.map((item) =>
            item.execution_item_id === input.executionItemId
              ? {
                  ...item,
                  tx_hash: result.tx_hash ?? item.tx_hash,
                  status: result.item_status ?? item.status,
                  onchain_status: result.onchain_status ?? item.onchain_status,
                }
              : item,
          ),
        };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoadingAttach(false);
    }
  }

  async function handleAttachSafeProposalSubmit(input: {
    executionItemId: string;
    safeAddress?: string;
    proposalId?: string;
    proposalUrl?: string;
    proposerWallet?: string;
  }) {
    setLoadingAttach(true);
    setError(null);
    setInfoMessage(null);
    try {
      const result = await postExecutionItemAttachSafeProposal(input.executionItemId, {
        safe_address: input.safeAddress || null,
        proposal_id: input.proposalId || null,
        proposal_url: input.proposalUrl || null,
        proposer_wallet: input.proposerWallet || null,
      });
      setInfoMessage(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoadingAttach(false);
    }
  }

  async function handleSyncReceiptSubmit(executionItemId: string) {
    setLoadingAttach(true);
    setError(null);
    setInfoMessage(null);
    try {
      const result = await postExecutionItemSyncReceipt(executionItemId, { force: false });
      setInfoMessage(result.message);
      setConfirmResult((current) => {
        if (!current) return current;
        return {
          ...current,
          execution_items: current.execution_items.map((item) =>
            item.execution_item_id === executionItemId
              ? {
                  ...item,
                  tx_hash: result.tx_hash ?? item.tx_hash,
                  status: result.item_status ?? item.status,
                  onchain_status: result.onchain_status ?? item.onchain_status,
                }
              : item,
          ),
        };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoadingAttach(false);
    }
  }

  return (
    <main className="space-y-8 pb-24 motion-scale-in">
      <section className="relative overflow-hidden rounded-[36px] border border-slate-900 bg-[linear-gradient(180deg,#0b1730_0%,#274a72_64%,#5d829a_100%)] px-6 py-8 text-white shadow-[0_32px_100px_rgba(9,18,34,0.22)] lg:px-8 lg:py-9">
        <div className="absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:124px_124px]" />
        <div className="absolute right-[-10%] top-[-10%] h-[420px] w-[420px] rounded-full border border-white/20" />
        <div className="absolute right-[8%] top-[26%] h-[260px] w-[260px] rounded-full border border-white/15" />
        <div className="relative grid gap-8 lg:grid-cols-[1fr_360px] lg:items-end">
          <div>
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d7d39a]">{t("command.badge")}</p>
            <h1 className="mt-4 text-4xl font-medium tracking-[-0.04em] leading-[0.96] lg:text-6xl">
              {t("command.title")}
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-slate-100/90 lg:text-lg">
              {t("command.intro")}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/merchant"
                className="inline-flex items-center rounded-xl bg-[#c6d3f1] px-5 py-2.5 text-sm font-semibold text-slate-900 transition hover:bg-[#d7e0f7]"
              >
                {t("home.secondaryCta")}
              </Link>
              <Link
                href="/modes"
                className="inline-flex items-center rounded-xl border border-white/55 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
              >
                {t("home.tertiaryCta")}
              </Link>
            </div>
          </div>

          <div className="grid gap-3">
            {aiSummaries.map((item, index) => (
              <div
                key={item.title}
                className={`motion-fade-up rounded-[22px] border border-white/10 bg-white/[0.06] px-4 py-4 backdrop-blur ${
                  index === 0 ? "motion-delay-1" : index === 1 ? "motion-delay-2" : "motion-delay-3"
                }`}
              >
                <p className="text-[11px] uppercase tracking-[0.22em] text-slate-300">{item.title}</p>
                <p className="mt-2 text-sm leading-7 text-slate-100/88">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <article className="motion-fade-up motion-delay-1 surface-transition rounded-[26px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
          <p className="text-[11px] uppercase tracking-[0.2em] text-[#496896]">{t("command.aiInputTitle")}</p>
          <h2 className="mt-2 text-lg font-semibold text-slate-900">{t("command.aiInputHeading")}</h2>
          <p className="mt-2 text-sm leading-7 text-slate-600">{t("command.aiInputBody")}</p>
          <div className="mt-4 rounded-2xl border border-[#d8e1f0] bg-[#f7f9fd] px-4 py-3">
            <p className="font-mono text-sm leading-7 text-slate-800">{effectivePrompt}</p>
          </div>
        </article>

        <article className="motion-fade-up motion-delay-2 surface-transition rounded-[26px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
          <p className="text-[11px] uppercase tracking-[0.2em] text-[#496896]">{t("command.aiExtractTitle")}</p>
          <h2 className="mt-2 text-lg font-semibold text-slate-900">{t("command.aiExtractHeading")}</h2>
          <p className="mt-2 text-sm leading-7 text-slate-600">{t("command.aiExtractBody")}</p>
          <div className="mt-4 grid gap-2">
            <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-2 text-sm text-slate-700">
              {t("command.beneficiary")}: {parsedPreview?.beneficiaryName || selectedRecipient?.name || "-"}
            </div>
            <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-2 text-sm text-slate-700">
              {t("common.amount")}: {parsedPreview?.amount ?? amount} {parsedPreview?.currency || currency}
            </div>
            <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-2 text-sm text-slate-700">
              {t("command.splitCount")}: {parsedPreview?.splitCount ?? "-"}
            </div>
          </div>
        </article>

        <article className="motion-fade-up motion-delay-3 surface-transition rounded-[26px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
          <p className="text-[11px] uppercase tracking-[0.2em] text-[#496896]">{t("command.aiRouteTitle")}</p>
          <h2 className="mt-2 text-lg font-semibold text-slate-900">{t("command.aiRouteHeading")}</h2>
          <p className="mt-2 text-sm leading-7 text-slate-600">{t("command.aiRouteBodyLong")}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <StatusBadge status={aiRiskValue} />
            <StatusBadge status={executionMode} />
            <StatusBadge status={aiRouteValue} />
          </div>
          <p className="mt-3 text-sm text-slate-600">
            {commandResult ? commandResult.message : t("command.aiAwaitingPreview")}
          </p>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
        <form onSubmit={handleSubmitCommand} className="space-y-4">
          <section className="motion-fade-up surface-transition rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                  {t("command.aiCopilotTitle")}
                </h2>
                <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600">
                  {t("command.nlpHint")}
                </p>
              </div>
              <StatusBadge status={previewPhase === "ready" ? "confirmed" : previewPhase} />
            </div>

            <div className="mt-4 rounded-[24px] border border-[#d8e1f0] bg-[linear-gradient(180deg,#f8fbff_0%,#f3f7fd_100%)] p-4">
              <div className="mb-3 flex flex-wrap gap-2">
                <span className="rounded-full border border-[#d8e1f0] bg-white px-2.5 py-1 text-xs font-medium text-slate-700">
                  {t("command.aiComposerSignalA")}
                </span>
                <span className="rounded-full border border-[#d8e1f0] bg-white px-2.5 py-1 text-xs font-medium text-slate-700">
                  {t("command.aiComposerSignalB")}
                </span>
                <span className="rounded-full border border-[#d8e1f0] bg-white px-2.5 py-1 text-xs font-medium text-slate-700">
                  {t("command.aiComposerSignalC")}
                </span>
              </div>
              <textarea
                value={customPrompt}
                onChange={(event) => {
                  setCustomPrompt(event.target.value);
                  if (previewPhase === "ready") {
                    setCommandResult(null);
                    setConfirmResult(null);
                    setBoundCommandId(null);
                    setPreviewPhase("idle");
                  }
                }}
                rows={5}
                placeholder={t("command.inputPlaceholder")}
                className="w-full rounded-2xl border border-[#c8d4ea] bg-white px-4 py-4 text-sm leading-8 text-slate-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)] outline-none ring-[#496896] transition-all duration-200 focus:border-[#7fa1d4] focus:ring-2"
              />
              <div className="mt-4 flex flex-wrap gap-2">
                {examplePrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => {
                      setCustomPrompt(prompt);
                      setPreviewPhase("idle");
                      setCommandResult(null);
                      setConfirmResult(null);
                      setBoundCommandId(null);
                    }}
                    className="rounded-lg border border-[#c8d4ea] bg-white px-2.5 py-1.5 text-xs text-slate-700 hover:bg-[#f4f8ff]"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={loadingCommand || !effectivePrompt.trim()}
                className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#203a61] disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {loadingCommand ? t("command.parsing") : t("command.previewBtn")}
              </button>
              <p className="text-xs text-slate-500">{t("command.nlpSubhint")}</p>
            </div>
          </section>

          <section className="motion-fade-up motion-delay-1 surface-transition rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
              {t("command.recipientCard")}
            </h2>
            <div className="mt-4 rounded-2xl border border-[#d8e1f0] bg-[#f7f9fd] p-3">
              <RecipientSelector
                recipients={recipients}
                selectedRecipientId={selectedRecipientId}
                onSelectRecipient={setSelectedRecipientId}
                onCreateRecipient={handleCreateRecipient}
              />
              {selectedRecipient ? (
                <div className="mt-3 grid gap-1 text-sm text-slate-700">
                  <p>
                    {t("recipient.selected")}:{" "}
                    <span className="font-medium">{formatRecipientLabel(selectedRecipient)}</span>
                  </p>
                  <p>
                    {t("recipient.network")}:{" "}
                    <span className="font-medium">{selectedRecipient.network}</span>
                  </p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-500">{t("common.noData")}</p>
              )}
            </div>
          </section>

          <section className="motion-fade-up motion-delay-2 surface-transition rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
              {t("command.amountCard")}
            </h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <label className="space-y-1 sm:col-span-2">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                  {t("command.amountLabel")}
                </span>
                <input
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  type="number"
                  min="0"
                  step="0.01"
                  className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                  {t("command.currencyLabel")}
                </span>
                <select
                  value={currency}
                  onChange={(event) => setCurrency(event.target.value)}
                  className="w-full rounded-xl border border-[#c8d4ea] bg-white px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                >
                  <option value="USDT">USDT</option>
                  <option value="USDC">USDC</option>
                  <option value="USD">USD</option>
                </select>
              </label>
            </div>
            <label className="mt-3 block space-y-1">
              <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                {t("command.referenceLabel")}
              </span>
              <input
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                placeholder="INV-001"
              />
            </label>
          </section>

          <section className="motion-fade-up motion-delay-3 surface-transition rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
              {t("command.modeCard")}
            </h2>
            <div className="mt-3 grid gap-2">
              {(["operator", "user_wallet", "safe"] as ExecutionMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => {
                    setExecutionMode(mode);
                    setConfirmResult(null);
                    setInfoMessage(null);
                  }}
                  className={`rounded-xl border px-3 py-2 text-left transition ${
                    executionMode === mode
                      ? "border-[#5d82b8] bg-[#edf3ff]"
                      : "border-[#d8e1f0] bg-[#f7f9fd] hover:border-[#b7cae5]"
                  }`}
                >
                  <p className="text-sm font-semibold text-slate-900">{statusLabel(mode)}</p>
                  <p className="text-xs text-slate-600">
                    {mode === "operator"
                      ? t("command.modeOperator")
                      : mode === "user_wallet"
                        ? t("command.modeUserWallet")
                        : t("command.modeSafe")}
                  </p>
                </button>
              ))}
            </div>
            <p className="mt-4 text-xs leading-6 text-slate-500">{t("command.modeHelp")}</p>
          </section>

          <details className="rounded-[24px] border border-[#d8e1f0] bg-[#f7f9fd] p-3">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
              {t("command.advancedSettings")}
            </summary>
            <div className="mt-3 space-y-3">
              <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-2 text-xs text-slate-600">
                {t("command.effectivePrompt")}: {effectivePrompt}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1">
                  <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                    {t("command.userId")}
                  </span>
                  <input
                    value={userId}
                    onChange={(event) => setUserId(event.target.value)}
                    className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                    placeholder="UUID"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                    {t("command.sessionId")}
                  </span>
                  <input
                    value={sessionId}
                    onChange={(event) => setSessionId(event.target.value)}
                    className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                    placeholder="UUID"
                  />
                </label>
              </div>
              <label className="space-y-1">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                  {t("command.idempotencyKey")}
                </span>
                <input
                  value={idempotencyKey}
                  onChange={(event) => setIdempotencyKey(event.target.value)}
                  className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
                  placeholder={t("command.idempotencyPlaceholder")}
                />
              </label>
            </div>
          </details>
        </form>

        <section className="space-y-4">
          {error ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
              {error}
            </div>
          ) : null}
          {infoMessage ? (
            <div className="rounded-2xl border border-teal-200 bg-teal-50 p-4 text-sm text-teal-800">
              {infoMessage}
            </div>
          ) : null}

          <section className="motion-fade-up surface-transition rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                {t("command.previewConfirmCard")}
              </h2>
              {commandResult ? <StatusBadge status={commandResult.status} /> : null}
            </div>

            {previewPhase === "loading" ? (
              <div className="mt-3">
                <EmptyStateCard title={t("command.previewLoadingTitle")} description={t("command.previewLoading")} />
              </div>
            ) : null}

            {commandResult ? (
              <div className="mt-3 space-y-3 text-sm">
                <PreviewSummaryCard
                  preview={commandResult}
                  parsedPreview={parsedPreview}
                  fallbackRecipient={selectedRecipient?.name}
                  fallbackAmount={amount}
                  fallbackCurrency={currency}
                  fallbackReference={reference}
                  executionModeLabel={statusLabel(executionMode)}
                  confidenceLabel={statusLabel(aiConfidence)}
                />

                <section className="motion-scale-in rounded-[24px] border border-[#d8e1f0] bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#496896]">
                    {t("command.aiInterpretationTitle")}
                  </p>
                  <h3 className="mt-1 text-lg font-semibold text-slate-900">{t("command.aiInterpretationHeading")}</h3>
                  <p className="mt-2 text-sm leading-7 text-slate-700">
                    {parsedPreview?.beneficiaryName || selectedRecipient?.name || "-"}
                    {" · "}
                    {parsedPreview?.amount ?? amount} {parsedPreview?.currency || currency}
                    {parsedPreview?.reference ? ` · ${parsedPreview.reference}` : ""}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {aiReasonList.length > 0 ? (
                      aiReasonList.map((reason) => (
                        <span
                          key={reason}
                          className="rounded-full border border-[#c8d4ea] bg-[#f7f9fd] px-2.5 py-1 text-xs font-medium text-slate-700"
                        >
                          {reason}
                        </span>
                      ))
                    ) : (
                      <span className="rounded-full border border-[#c8d4ea] bg-[#f7f9fd] px-2.5 py-1 text-xs font-medium text-slate-700">
                        {t("command.aiReasonAwaiting")}
                      </span>
                    )}
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.aiConfidence")}</p>
                      <p className="mt-2 font-semibold text-slate-900">{statusLabel(aiConfidence)}</p>
                    </div>
                    <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.aiStructuredFields")}</p>
                      <p className="mt-2 font-semibold text-slate-900">
                        {[parsedPreview?.beneficiaryName, parsedPreview?.amount, parsedPreview?.currency, parsedPreview?.reference]
                          .filter(Boolean)
                          .length}
                      </p>
                    </div>
                    <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.aiRecommendedMode")}</p>
                      <p className="mt-2 font-semibold text-slate-900">{statusLabel(routeRecommendation.recommendedMode)}</p>
                    </div>
                  </div>
                </section>

                <RiskSummaryCard risk={commandResult.risk} title={t("command.aiRiskPanelTitle")} />

                {clarification ? (
                  <section className="motion-scale-in rounded-[24px] border border-amber-300 bg-[linear-gradient(180deg,#fff9e9_0%,#fff7df_100%)] p-4 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-700">
                          {clarification.title}
                        </p>
                        <p className="mt-2 text-sm leading-7 text-amber-900">{clarification.body}</p>
                      </div>
                      <StatusBadge status="pending" />
                    </div>
                    <div className="mt-4 rounded-2xl border border-amber-200 bg-white/70 px-4 py-4">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-amber-700">
                        {lang === "zh" ? "AI 建议先确认的问题" : "AI follow-up question"}
                      </p>
                      <p className="mt-2 text-sm font-medium leading-7 text-amber-950">
                        {clarification.question}
                      </p>
                    </div>
                    {clarification.fields.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {clarification.fields.map((field) => (
                          <span
                            key={field}
                            className="rounded-full border border-amber-300 bg-white px-2.5 py-1 text-xs font-medium text-amber-800"
                          >
                            {field}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </section>
                ) : null}

                <section className="motion-scale-in rounded-[24px] border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#496896]">
                    {t("command.aiRouteHeading")}
                  </p>
                  <h3 className="mt-1 text-lg font-semibold text-slate-900">{t("command.aiPlanTitle")}</h3>
                  <p className="mt-2 text-sm leading-7 text-slate-700">{aiPlanSummary}</p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
                        {t("command.aiRecommendedMode")}
                      </p>
                      <div className="mt-2">
                        <StatusBadge status={routeRecommendation.recommendedMode} />
                      </div>
                    </div>
                    <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
                        {t("command.aiRecommendedNext")}
                      </p>
                      <div className="mt-2">
                        <StatusBadge status={commandResult.next_action} />
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <StatusBadge status={commandResult.risk?.decision || "pending"} />
                    {routeRecommendation.reasons.map((reason) => (
                      <span
                        key={`plan-${reason}`}
                        className="rounded-full border border-[#c8d4ea] bg-white px-2.5 py-1 text-xs font-medium text-slate-700"
                      >
                        {reason}
                      </span>
                    ))}
                  </div>
                  <div className="mt-4 rounded-2xl border border-[#d8e1f0] bg-white px-4 py-4">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.aiRouteWhy")}</p>
                    <p className="mt-2 text-sm leading-7 text-slate-700">{routeRecommendation.why}</p>
                    <div className="mt-3 space-y-2">
                      {aiRouteSteps.map((step, index) => (
                        <div key={step} className="flex items-start gap-3">
                          <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[#edf3ff] text-xs font-semibold text-[#32527f]">
                            {index + 1}
                          </span>
                          <p className="pt-0.5 text-sm leading-6 text-slate-700">{step}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
                        {lang === "zh" ? "已选模式" : "Selected mode"}
                      </p>
                      <div className="mt-2">
                        <StatusBadge status={executionMode} />
                      </div>
                    </div>
                    <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
                        {lang === "zh" ? "备选路径" : "Alternative route"}
                      </p>
                      <div className="mt-2">
                        <StatusBadge status={routeRecommendation.fallbackMode} />
                      </div>
                    </div>
                  </div>
                  {routeRecommendation.recommendedMode !== executionMode ? (
                    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#d8e1f0] bg-white px-4 py-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">
                          {lang === "zh"
                            ? `AI 建议改为 ${statusLabel(routeRecommendation.recommendedMode)}`
                            : `AI recommends switching to ${statusLabel(routeRecommendation.recommendedMode)}`}
                        </p>
                        <p className="mt-1 text-xs leading-6 text-slate-600">{routeRecommendation.summary}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setExecutionMode(routeRecommendation.recommendedMode)}
                        className="rounded-xl border border-[#bfd0ec] bg-[#edf3ff] px-3 py-2 text-sm font-medium text-[#32527f] transition hover:bg-[#e3ecfb]"
                      >
                        {lang === "zh" ? "套用 AI 推荐" : "Apply recommendation"}
                      </button>
                    </div>
                  ) : null}
                </section>

                <p className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-2 text-slate-700">
                  {commandResult.message}
                </p>
                <p className="text-xs text-slate-500">
                  {t("common.nextAction")}: {statusLabel(commandResult.next_action)}
                </p>
                {commandResult.missing_fields.length > 0 ? (
                  <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-amber-800">
                    {t("command.missingFields")}: {commandResult.missing_fields.join(", ")}
                  </div>
                ) : null}

                <ModeNextStepCard
                  mode={executionMode}
                  previewReady={previewPhase === "ready"}
                  confirmResult={confirmResult}
                  onCopyUnsigned={handleCopyUnsigned}
                  onAttachTx={handleAttachTx}
                  onCopySafeProposal={handleCopySafeProposal}
                  onAttachSafe={handleAttachTx}
                />

                <PrimaryActionCard
                  mode={executionMode}
                  canConfirm={canConfirm}
                  loading={loadingConfirm}
                  onConfirm={handleConfirm}
                  summary={t("command.primaryActionSummary")}
                  guidance={t("command.aiRouteRationale")}
                />

                {confirmResult ? (
                  <section className="rounded-2xl border border-[#d8e1f0] bg-[#f9fbff] p-4 shadow-sm motion-scale-in surface-transition">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                        {t("command.aiReceiptTitle")}
                      </h3>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={confirmResult.status} />
                        <StatusBadge status={confirmResult.execution_mode} />
                        {confirmResult.payment_status ? (
                          <StatusBadge status={confirmResult.payment_status} />
                        ) : null}
                      </div>
                    </div>
                    <p className="mt-2 text-sm text-slate-700">
                      {confirmResult.message || t("command.aiReceiptPending")}
                    </p>
                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3">
                        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.aiRecommendedNext")}</p>
                        <p className="mt-2 font-semibold text-slate-900">{statusLabel(confirmResult.next_action)}</p>
                      </div>
                      <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3">
                        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.aiRecommendedMode")}</p>
                        <p className="mt-2 font-semibold text-slate-900">{statusLabel(confirmResult.execution_mode)}</p>
                      </div>
                      <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3">
                        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.paymentOrder")}</p>
                        <p className="mt-2 break-all font-mono text-xs text-slate-700">{confirmResult.payment_order_id || "-"}</p>
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {t("common.nextAction")}: {statusLabel(confirmResult.next_action)}
                    </p>
                    {confirmResult.payment_order_id ? (
                      <div className="mt-3">
                        <Link
                          href={`/payments/${confirmResult.payment_order_id}`}
                          className="inline-flex items-center rounded-xl border border-[#bfd0ec] bg-[#edf3ff] px-3 py-1.5 text-sm font-medium text-[#32527f] hover:bg-[#e3ecfb]"
                        >
                          {t("command.nextOpenPayment")}
                        </Link>
                      </div>
                    ) : null}
                  </section>
                ) : null}

                {confirmResult &&
                showAttachPanel &&
                (confirmResult.execution_mode === "user_wallet" ||
                  confirmResult.execution_mode === "safe") ? (
                  <ExecutionAttachPanel
                    mode={confirmResult.execution_mode}
                    items={confirmResult.execution_items}
                    loading={loadingAttach}
                    onAttachTx={handleAttachTxSubmit}
                    onAttachSafeProposal={handleAttachSafeProposalSubmit}
                    onSyncReceipt={handleSyncReceiptSubmit}
                  />
                ) : null}

                <details className="rounded-[24px] border border-[#d8e1f0] bg-[#f8fbff] p-4 shadow-sm surface-transition">
                  <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                    {t("command.supportingDetailsTitle")}
                  </summary>
                  <p className="mt-2 text-sm leading-7 text-slate-600">
                    {t("command.supportingDetailsBody")}
                  </p>
                  <div className="mt-4">
                    <TechnicalDetailsAccordion
                      preview={commandResult}
                      confirmResult={confirmResult}
                    />
                  </div>
                </details>
              </div>
            ) : previewPhase !== "loading" ? (
              <div className="mt-3">
                <EmptyStateCard title={t("command.previewConfirmCard")} description={t("command.noPreview")} />
              </div>
            ) : null}
          </section>
        </section>
      </section>
    </main>
  );
}
