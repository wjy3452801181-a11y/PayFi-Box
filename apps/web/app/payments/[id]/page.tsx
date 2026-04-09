"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  type CommandTimelineResponse,
  type PaymentDetailResponse,
  getCommandTimeline,
  getRememberedAccessSession,
  getPaymentDetail,
} from "../../../lib/api";
import { formatTime } from "../../../lib/format";
import { useI18n } from "../../../lib/i18n-provider";
import { DeferredPanelShell } from "../../../components/deferred-panel-shell";
import { ExplorerLinkCard } from "../../../components/explorer-link-card";
import { EmptyStateCard } from "../../../components/empty-state-card";
import { JsonView } from "../../../components/json-view";
import { StatusBadge } from "../../../components/status-badge";
const ExecutionItemTable = dynamic(
  () => import("../../../components/execution-item-table").then((mod) => mod.ExecutionItemTable),
  { loading: () => <DeferredPanelShell /> },
);
const TimelineView = dynamic(
  () => import("../../../components/timeline-view").then((mod) => mod.TimelineView),
  { loading: () => <DeferredPanelShell /> },
);

type AuditNarrative = {
  title: string;
  summary: string;
  bullets: string[];
  status: string;
};

function buildAuditNarrative(
  detail: PaymentDetailResponse,
  lang: "zh" | "en",
): AuditNarrative {
  const amountText = `${detail.payment.amount} ${detail.payment.currency}`;
  const recipient = detail.beneficiary?.name || (lang === "zh" ? "收款方" : "recipient");
  const mode = detail.payment.execution_route || detail.payment.execution_mode || "-";
  const hasPartial = Boolean(detail.timeline_summary?.has_partial_failure);
  const hasDuplicate = Boolean(detail.timeline_summary?.has_duplicate_rejection);
  const hasReconciled = Boolean(detail.timeline_summary?.has_reconciliation);
  const onchainStatus = (detail.execution.onchain_status || "").toLowerCase();
  const paymentStatus = (detail.payment.status || "").toLowerCase();
  const hasTx = Boolean(detail.execution.tx_hash);
  const isBlocked = paymentStatus.includes("block");

  if (lang === "zh") {
    if (isBlocked) {
      return {
        title: "AI 审计总结：结算被拦截",
        summary: `这笔给 ${recipient} 的 ${amountText} 结算没有进入正常执行路径，系统保留了阻断结果供后续复核。`,
        bullets: [
          "当前最重要的是解释风险原因，而不是继续切换提交模式。",
          "如果没有链上 tx，说明链上结算还没有真正创建。",
          `当前提交模式记录为 ${mode}，但阻断结果优先于执行路径。`,
        ],
        status: "blocked",
      };
    }
    if (hasPartial) {
      return {
        title: "AI 审计总结：部分执行",
        summary: `这笔 ${amountText} 结算已经有一部分执行成功，但仍有执行项需要继续跟进。`,
        bullets: [
          "重点查看 execution items，确认哪些子项已上链、哪些子项失败或待处理。",
          "partial 状态说明系统没有隐藏失败，而是把执行真相完整保留了下来。",
          hasTx ? "已有链上 tx，可继续围绕 receipt 和 timeline 做核查。" : "尚未形成完整链上结果，优先检查 batch 与 item 状态。",
        ],
        status: "partially_executed",
      };
    }
    if (hasDuplicate) {
      return {
        title: "AI 审计总结：命中重复保护",
        summary: "系统检测到重复请求或重复执行信号，因此拒绝了重复推进，避免产生第二次结算。",
        bullets: [
          "这是幂等保护，不是随机失败。",
          "如果已经存在 payment order 或 tx，应继续围绕已有对象核查，而不是重提同一笔。",
          "时间线里通常会保留 duplicate rejected 的显式信号。",
        ],
        status: "duplicate_rejected",
      };
    }
    if (hasReconciled) {
      return {
        title: "AI 审计总结：状态已对齐",
        summary: "系统已经对这笔结算做过补同步或状态对齐，当前展示的是更接近最终真值的结果。",
        bullets: [
          "这通常意味着系统曾做过 receipt 同步、回补或状态纠偏。",
          "如果你在对账，优先看当前 execution 与 timeline，不要只凭最早的前端提示。",
          hasTx ? "链上结果已可作为最终核查依据。" : "如果仍无 tx，继续看 execution batch 和 item 的推进状态。",
        ],
        status: "reconciled",
      };
    }
    if (hasTx && (onchainStatus.includes("confirmed") || onchainStatus.includes("executed"))) {
      return {
        title: "AI 审计总结：结算完成",
        summary: `这笔发给 ${recipient} 的 ${amountText} 结算已经完成，链上结果可用于最终核查。`,
        bullets: [
          `提交模式为 ${mode}，相关执行真相已经落到 payment order、execution batch 和 tx hash。`,
          "现在最值得查看的是 explorer、timeline 和 risk checks，确认整笔流转没有隐藏异常。",
          "如果需要对外展示，这一页已经具备完整的可审计链路。",
        ],
        status: "executed",
      };
    }
    return {
      title: "AI 审计总结：结算处理中",
      summary: `这笔发给 ${recipient} 的 ${amountText} 结算仍在推进中，当前还没有形成最终完成态。`,
      bullets: [
        `当前提交模式为 ${mode}。`,
        hasTx ? "链上交易已经提交，下一步重点看确认状态。" : "如果还没有 tx，下一步重点看 execution batch 与 items 是否继续推进。",
        "这类状态最适合结合 timeline 和 execution items 一起看。",
      ],
      status: detail.payment.status,
    };
  }

  if (isBlocked) {
    return {
      title: "AI Audit Summary: Settlement blocked",
      summary: `This ${amountText} settlement to ${recipient} did not proceed through the normal execution path, and the blocked result has been preserved for review.`,
      bullets: [
        "The next job is to explain the risk outcome, not to keep switching submission modes.",
        "If there is no onchain tx, onchain settlement was never actually created.",
        `The recorded submission mode is ${mode}, but the blocked outcome takes precedence over route selection.`,
      ],
      status: "blocked",
    };
  }
  if (hasPartial) {
    return {
      title: "AI Audit Summary: Partial execution",
      summary: `This ${amountText} settlement has executed in part, but some execution items still need follow-up.`,
      bullets: [
        "Inspect execution items first to see which children were confirmed and which ones failed or remain pending.",
        "A partial state means the system is preserving execution truth rather than hiding failure.",
        hasTx ? "An onchain tx already exists, so receipt and timeline are the next best sources of truth." : "A full onchain result is not yet present, so batch and item state matter most right now.",
      ],
      status: "partially_executed",
    };
  }
  if (hasDuplicate) {
    return {
      title: "AI Audit Summary: Duplicate protection triggered",
      summary: "The system detected a duplicate request or duplicate execution signal and rejected the replay to avoid a second settlement.",
      bullets: [
        "This is idempotency protection, not a random failure.",
        "If a payment order or tx already exists, continue investigating that object rather than resubmitting the same request.",
        "The timeline should preserve an explicit duplicate-rejected signal.",
      ],
      status: "duplicate_rejected",
    };
  }
  if (hasReconciled) {
    return {
      title: "AI Audit Summary: State reconciled",
      summary: "The system has already re-synced or reconciled this settlement, so the current state is closer to final truth than the earliest UI signal.",
      bullets: [
        "This usually means the platform re-synced receipts or corrected intermediate state.",
        "For ops review, prefer the current execution and timeline state over the first frontend status message.",
        hasTx ? "The onchain result can now act as the final reconciliation anchor." : "If there is still no tx, keep checking the batch and execution-item progression.",
      ],
      status: "reconciled",
    };
  }
  if (hasTx && (onchainStatus.includes("confirmed") || onchainStatus.includes("executed"))) {
    return {
      title: "AI Audit Summary: Settlement completed",
      summary: `This ${amountText} settlement to ${recipient} is complete, and the onchain result can now be used as final truth.`,
      bullets: [
        `The recorded submission mode is ${mode}, and the final execution trail now exists across the payment order, execution batch, and tx hash.`,
        "The most useful final checks are explorer, timeline, and risk checks.",
        "This page is already suitable for an auditable walkthrough of the whole flow.",
      ],
      status: "executed",
    };
  }
  return {
    title: "AI Audit Summary: Settlement still in progress",
    summary: `This ${amountText} settlement to ${recipient} is still moving through execution and has not yet reached its final state.`,
    bullets: [
      `The current submission mode is ${mode}.`,
      hasTx ? "An onchain transaction already exists, so confirmation state is the main thing to watch next." : "No onchain tx is visible yet, so batch and item progression are still the main truth source.",
      "This is the kind of state that should be read alongside the timeline and execution items.",
    ],
    status: detail.payment.status,
  };
}

export default function PaymentDetailPage() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const paymentId = params.id;

  const [detail, setDetail] = useState<PaymentDetailResponse | null>(null);
  const [timeline, setTimeline] = useState<CommandTimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actorId, setActorId] = useState<string | null>(null);
  const [hasAccessSession, setHasAccessSession] = useState(false);
  const [sessionChecked, setSessionChecked] = useState(false);
  const [redirectingToAccess, setRedirectingToAccess] = useState(false);

  useEffect(() => {
    const session = getRememberedAccessSession();
    setActorId(session?.user.id || null);
    setHasAccessSession(Boolean(session?.access_token));
    setSessionChecked(true);
  }, []);

  useEffect(() => {
    let active = true;
    async function loadData() {
      if (!paymentId) return;
      if (!sessionChecked) return;
      if (!actorId) {
        if (active) {
          setRedirectingToAccess(true);
          setLoading(false);
          router.replace(`/access?next=/payments/${paymentId}`);
        }
        return;
      }
      if (active) setRedirectingToAccess(false);
      setLoading(true);
      setError(null);
      try {
        const paymentDetail = await getPaymentDetail(paymentId, actorId);
        if (!active) return;
        setDetail(paymentDetail);

        const commandId = paymentDetail.command?.id;
        if (commandId) {
          try {
            const timelineData = await getCommandTimeline(commandId, actorId);
            if (!active) return;
            setTimeline(timelineData);
          } catch {
            if (!active) return;
            setTimeline(null);
          }
        } else {
          setTimeline(null);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : t("common.error");
        if (active) setError(message);
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadData();
    return () => {
      active = false;
    };
  }, [actorId, paymentId, router, sessionChecked, t]);

  const timelineItems = useMemo(() => {
    if (timeline?.items?.length) return timeline.items;
    return detail?.audit.items ?? [];
  }, [timeline, detail]);
  const auditNarrative = useMemo(() => {
    if (!detail) return null;
    return buildAuditNarrative(detail, lang);
  }, [detail, lang]);

  return (
    <main className="space-y-6 pb-20 motion-scale-in">
      <section className="relative overflow-hidden rounded-[36px] border border-slate-900 bg-[linear-gradient(180deg,#0b1730_0%,#274a72_64%,#5d829a_100%)] p-6 text-white shadow-[0_32px_100px_rgba(9,18,34,0.22)] lg:p-8 motion-fade-up">
        <div className="absolute inset-0 opacity-35 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:124px_124px]" />
        <div className="absolute right-[-10%] top-[-6%] h-[320px] w-[320px] rounded-full border border-white/18" />
        <div className="absolute right-[14%] top-[22%] h-[160px] w-[160px] rounded-full border border-white/12" />
        <div className="relative grid gap-6 lg:grid-cols-[1fr_340px] lg:items-end">
          <div className="motion-fade-up">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d7d39a]">{t("payment.badge")}</p>
            <h1 className="mt-4 text-4xl font-medium tracking-[-0.04em] leading-[0.96] lg:text-6xl">{t("payment.title")}</h1>
            <p className="mt-5 max-w-4xl text-base leading-8 text-slate-100/90">{t("payment.intro")}</p>
          </div>
          <div className="grid gap-3">
            <div className="rounded-[22px] border border-white/10 bg-white/[0.06] px-4 py-4 backdrop-blur motion-fade-up motion-delay-1 surface-transition">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-300">{t("payment.summary")}</p>
              <p className="mt-2 text-sm leading-7 text-slate-100/88">
                {detail
                  ? `${detail.payment.amount} ${detail.payment.currency} · ${detail.beneficiary?.name || "-"}`
                  : t("payment.loading")}
              </p>
            </div>
            <div className="rounded-[22px] border border-white/10 bg-white/[0.06] px-4 py-4 backdrop-blur motion-fade-up motion-delay-2 surface-transition">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-300">{t("payment.aggregateExecution")}</p>
              <p className="mt-2 break-all font-mono text-xs leading-6 text-slate-100/82">{paymentId}</p>
            </div>
          </div>
        </div>
      </section>

      {loading ? (
        <section className="rounded-[24px] border border-[#c8d4ea] bg-white p-6 text-sm text-slate-600 shadow-sm motion-fade-up motion-delay-1">
          {t("payment.loading")}
        </section>
      ) : null}
      {redirectingToAccess ? (
        <section className="rounded-2xl border border-[#c8d4ea] bg-[#f7f9fd] p-4 text-sm text-slate-700 motion-fade-up motion-delay-1">
          <div className="space-y-3">
            <p>
              {lang === "zh"
                ? "当前浏览器还没有访问会话，正在跳转到访问页以继续查看这笔结算。"
                : "No access session is active yet. Redirecting to the access page so this settlement can be reopened."}
            </p>
            <Link
              href={`/access?next=/payments/${paymentId}`}
              className="inline-flex rounded-2xl bg-[#0f1b3d] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#162757]"
            >
              {lang === "zh" ? "前往访问页" : "Open access page"}
            </Link>
          </div>
        </section>
      ) : null}
      {error ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 motion-fade-up motion-delay-1">
          <div className="space-y-3">
            <p>{error}</p>
            {!hasAccessSession ? (
              <Link
                href={`/access?next=/payments/${paymentId}`}
                className="inline-flex rounded-2xl bg-[#0f1b3d] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#162757]"
              >
                {lang === "zh" ? "建立访问会话" : "Create access session"}
              </Link>
            ) : null}
          </div>
        </section>
      ) : null}

      {detail ? (
        <>
          <section className="grid gap-4 rounded-[30px] border border-[#c8d4ea] bg-white p-6 shadow-sm lg:grid-cols-[1.1fr_0.9fr] motion-fade-up motion-delay-1 surface-transition">
            <div className="space-y-3 text-sm">
              <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">{t("payment.summary")}</h2>
              <div className="flex flex-wrap gap-2">
                <StatusBadge status={detail.payment.status} />
                <StatusBadge status={detail.payment.execution_route || detail.payment.execution_mode} />
                <StatusBadge status={detail.payment.risk_level} />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3">
                  <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("common.amount")}</p>
                  <p className="mt-2 text-xl font-medium tracking-[-0.03em] text-slate-900">
                    {detail.payment.amount} {detail.payment.currency}
                  </p>
                </div>
                <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3">
                  <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.beneficiary")}</p>
                  <p className="mt-2 text-base font-medium text-slate-900">{detail.beneficiary?.name || "-"}</p>
                </div>
              </div>
              <div className="space-y-2 rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-slate-700">
                <p>
                  <span className="text-slate-500">{t("common.reference")}:</span> {detail.payment.reference || "-"}
                </p>
                <p>
                  <span className="text-slate-500">{t("common.mode")}:</span>{" "}
                  {detail.payment.execution_route || detail.payment.execution_mode}
                </p>
              </div>
            </div>
            <ExplorerLinkCard
              network={detail.execution.network}
              txHash={detail.execution.tx_hash}
              explorerUrl={detail.execution.explorer_url}
              onchainStatus={detail.execution.onchain_status}
              title={t("payment.aggregateExecution")}
            />
          </section>

          {auditNarrative ? (
            <section className="rounded-[24px] border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-5 motion-fade-up motion-delay-2 surface-transition">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#496896]">
                    {auditNarrative.title}
                  </p>
                  <p className="mt-3 text-sm leading-7 text-slate-700">{auditNarrative.summary}</p>
                </div>
                <StatusBadge status={auditNarrative.status} />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                {auditNarrative.bullets.map((bullet) => (
                  <div key={bullet} className="rounded-2xl border border-[#d8e1f0] bg-white px-4 py-4 text-sm leading-7 text-slate-700">
                    {bullet}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {detail.timeline_summary?.has_partial_failure ||
          detail.timeline_summary?.has_duplicate_rejection ||
          detail.timeline_summary?.has_reconciliation ? (
            <section className="rounded-[24px] border border-amber-300 bg-[linear-gradient(180deg,#fff9e9_0%,#fff6dd_100%)] p-4 motion-fade-up motion-delay-2 surface-transition">
              <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-amber-800">
                {t("payment.truthSignals")}
              </h2>
              <div className="mt-2 flex flex-wrap gap-2">
                {detail.timeline_summary?.has_partial_failure ? (
                  <>
                    <StatusBadge status="partially_executed" />
                    <span className="rounded-full border border-amber-300 bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
                      {t("payment.partialFailure")}
                    </span>
                  </>
                ) : null}
                {detail.timeline_summary?.has_duplicate_rejection ? (
                  <>
                    <StatusBadge status="duplicate_rejected" />
                    <span className="rounded-full border border-amber-300 bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
                      {t("payment.duplicateRejected")}
                    </span>
                  </>
                ) : null}
                {detail.timeline_summary?.has_reconciliation ? (
                  <>
                    <StatusBadge status="reconciled" />
                    <span className="rounded-full border border-cyan-300 bg-cyan-100 px-2.5 py-1 text-xs font-semibold text-cyan-800">
                      {t("payment.reconciled")}
                    </span>
                  </>
                ) : null}
              </div>
              <p className="mt-3 text-sm leading-7 text-amber-900">{t("payment.truthSignalDesc")}</p>
            </section>
          ) : null}

          <section className="space-y-4 motion-fade-up motion-delay-2">
            <details className="rounded-[24px] border border-[#c8d4ea] bg-white p-4 shadow-sm surface-transition">
              <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                {t("payment.executionItems")}
              </summary>
              <div className="mt-3">
                <ExecutionItemTable items={detail.execution_items} />
              </div>
            </details>

            <details className="rounded-[24px] border border-[#c8d4ea] bg-white p-4 shadow-sm surface-transition">
              <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                {t("payment.splits")}
              </summary>
              {detail.splits.length === 0 ? (
                <div className="mt-3">
                  <EmptyStateCard title={t("payment.splits")} description={t("payment.noSplits")} />
                </div>
              ) : (
                <div className="mt-3 space-y-2">
                  {detail.splits.map((split) => (
                    <div key={split.id} className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-2 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p>
                          #{split.sequence} · {split.amount} {split.currency}
                        </p>
                        <StatusBadge status={split.status} />
                      </div>
                      {split.tx_hash ? <p className="mt-1 font-mono text-xs text-slate-600">{split.tx_hash}</p> : null}
                    </div>
                  ))}
                </div>
              )}
            </details>

            <details className="rounded-[24px] border border-[#c8d4ea] bg-white p-4 shadow-sm surface-transition">
              <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                {timeline ? t("payment.commandTimeline") : t("payment.auditTimeline")}
              </summary>
              <div className="mt-3">
                <TimelineView
                  title={timeline ? t("payment.commandTimeline") : t("payment.auditTimeline")}
                  items={timelineItems}
                  emptyText={t("component.noTimeline")}
                />
              </div>
            </details>

            <details className="rounded-[24px] border border-[#d8e1f0] bg-[#f8fbff] p-4 shadow-sm surface-transition">
              <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                {t("payment.supportingTitle")}
              </summary>
              <p className="mt-2 text-sm leading-7 text-slate-600">{t("payment.supportingBody")}</p>
              <div className="mt-4 space-y-4">
                <details className="rounded-[20px] border border-[#c8d4ea] bg-white p-4 shadow-sm surface-transition" open={false}>
                  <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                    {t("payment.technicalBatch")}
                  </summary>
                  {detail.execution_batch ? (
                    <div className="mt-3 space-y-2 text-sm text-slate-700">
                      <p className="break-all font-mono text-xs text-slate-600">{detail.execution_batch.id}</p>
                      <div className="flex flex-wrap gap-2">
                        <StatusBadge status={detail.execution_batch.status} />
                        <StatusBadge status={detail.execution_batch.execution_mode} />
                      </div>
                      <p>
                        <span className="text-slate-500">{t("payment.idempotencyKey")}:</span>{" "}
                        <span className="font-mono text-xs">{detail.execution_batch.idempotency_key}</span>
                      </p>
                      <p>
                        <span className="text-slate-500">{t("common.items")}:</span> {detail.execution_batch.confirmed_items}/
                        {detail.execution_batch.total_items} {t("payment.itemsConfirmed")} · {detail.execution_batch.failed_items}{" "}
                        {t("payment.itemsFailed")}
                      </p>
                      <p>
                        <span className="text-slate-500">{t("payment.itemsSubmitted")}:</span> {detail.execution_batch.submitted_items}
                      </p>
                      <p>
                        <span className="text-slate-500">{t("payment.startedAt")}:</span>{" "}
                        {formatTime(detail.execution_batch.started_at)}
                      </p>
                      <p>
                        <span className="text-slate-500">{t("payment.finishedAt")}:</span>{" "}
                        {formatTime(detail.execution_batch.finished_at)}
                      </p>
                    </div>
                  ) : (
                    <div className="mt-3">
                      <EmptyStateCard title={t("payment.batchSummary")} description={t("payment.noBatch")} />
                    </div>
                  )}
                </details>

                <details className="rounded-[20px] border border-[#c8d4ea] bg-white p-4 shadow-sm surface-transition">
                  <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                    {t("payment.riskChecks")}
                  </summary>
                  {detail.risk_checks.length === 0 ? (
                    <div className="mt-3">
                      <EmptyStateCard title={t("payment.riskChecks")} description={t("payment.noRisk")} />
                    </div>
                  ) : (
                    <div className="mt-3 space-y-2">
                      {detail.risk_checks.map((riskCheck) => (
                        <div key={riskCheck.id} className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] p-3">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-medium text-slate-900">{riskCheck.check_type}</p>
                            <StatusBadge status={riskCheck.result} />
                          </div>
                          <p className="mt-1 text-xs text-slate-600">
                            {riskCheck.normalized_reason_codes.join(", ") || t("component.noReasonCodes")}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </details>

                <details className="rounded-[20px] border border-[#c8d4ea] bg-white p-4 shadow-sm surface-transition">
                  <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
                    {t("payment.executionPayload")}
                  </summary>
                  <div className="mt-3">
                    <JsonView title={t("payment.executionPayload")} data={detail.execution} emptyText={t("common.noData")} />
                  </div>
                </details>
              </div>
            </details>
          </section>
        </>
      ) : null}
    </main>
  );
}
