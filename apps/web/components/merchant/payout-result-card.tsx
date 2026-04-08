"use client";

import Link from "next/link";
import { useI18n } from "../../lib/i18n-provider";
import { ExplorerLinkCard } from "../explorer-link-card";
import { EmptyStateCard } from "../empty-state-card";
import { StatusBadge } from "../status-badge";

type PayoutResultCardProps = {
  paymentOrderId?: string | null;
  executionBatchId?: string | null;
  payoutStatus?: string | null;
  onchainStatus?: string | null;
  txHash?: string | null;
  explorerUrl?: string | null;
  network?: string | null;
  blocked: boolean;
  noOnchainPayoutCreated: boolean;
};

export function PayoutResultCard({
  paymentOrderId,
  executionBatchId,
  payoutStatus,
  onchainStatus,
  txHash,
  explorerUrl,
  network,
  blocked,
  noOnchainPayoutCreated,
}: PayoutResultCardProps) {
  const { t } = useI18n();
  const hasPayout = Boolean(paymentOrderId);
  const isConfirmed = Boolean(txHash) && !blocked && (onchainStatus || payoutStatus);
  const spotlightTitle = blocked
    ? t("merchant.settlementBlockedTitle")
    : isConfirmed
      ? t("merchant.settlementCompletedTitle")
      : t("merchant.settlementPendingTitle");
  const spotlightBody = blocked
    ? noOnchainPayoutCreated
      ? t("merchant.blockedNoOnchain")
      : t("merchant.blockedWithPayout")
    : isConfirmed
      ? t("merchant.settlementCompletedBody")
      : t("merchant.settlementPendingBody");

  return (
    <section className="space-y-4 rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm motion-scale-in surface-transition">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
        {t("merchant.payoutResultTitle")}
      </h2>

      <div
        className={`rounded-[24px] border p-4 ${
          blocked
            ? "border-rose-200 bg-[linear-gradient(180deg,#fff1f2_0%,#fff8f8_100%)]"
            : isConfirmed
              ? "border-emerald-200 bg-[linear-gradient(180deg,#ecfdf5_0%,#f7fffb_100%)]"
              : "border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)]"
        }`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={blocked ? "blocked" : isConfirmed ? "completed" : payoutStatus || "pending"} />
          {onchainStatus ? <StatusBadge status={onchainStatus} /> : null}
          {noOnchainPayoutCreated ? <StatusBadge status="blocked" /> : null}
        </div>
        <p className="mt-3 text-xl font-semibold tracking-[-0.03em] text-slate-950">{spotlightTitle}</p>
        <p className="mt-2 text-sm leading-7 text-slate-700">{spotlightBody}</p>
      </div>

      {hasPayout ? (
        <div className="space-y-4 rounded-[24px] border border-[#d8e1f0] bg-[#f7f9fd] p-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={payoutStatus || "pending"} />
            <StatusBadge status={onchainStatus || "pending"} />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-white bg-white px-3 py-3">
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("merchant.paymentOrderId")}</p>
              <Link
                href={`/payments/${paymentOrderId}`}
                className="mt-2 block break-all text-sm font-medium text-[#32527f] hover:text-[#203a61]"
              >
                {paymentOrderId}
              </Link>
            </div>
            <div className="rounded-xl border border-white bg-white px-3 py-3">
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("merchant.executionBatchId")}</p>
              <p className="mt-2 break-all font-mono text-xs text-slate-700">{executionBatchId || "-"}</p>
            </div>
            <div className="rounded-xl border border-white bg-white px-3 py-3">
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("common.txHash")}</p>
              <p className="mt-2 break-all font-mono text-xs text-slate-700">{txHash || "-"}</p>
            </div>
          </div>

          <ExplorerLinkCard
            title={t("merchant.payoutExecution")}
            network={network}
            txHash={txHash}
            explorerUrl={explorerUrl}
            onchainStatus={onchainStatus}
          />
        </div>
      ) : (
        <EmptyStateCard title={t("merchant.payoutResultTitle")} description={t("merchant.noPayoutYet")} />
      )}
    </section>
  );
}
