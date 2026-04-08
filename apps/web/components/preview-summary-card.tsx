"use client";

import type { CommandResponse } from "../lib/api";
import { useI18n } from "../lib/i18n-provider";

type ParsedPreview = {
  beneficiaryName?: string;
  amount?: number;
  currency?: string;
  splitCount?: number;
  reference?: string;
};

type PreviewSummaryCardProps = {
  preview: CommandResponse | null;
  parsedPreview: ParsedPreview | null;
  fallbackRecipient?: string | null;
  fallbackAmount: string;
  fallbackCurrency: string;
  fallbackReference?: string;
  executionModeLabel?: string;
  confidenceLabel?: string;
};

function formatNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString();
}

export function PreviewSummaryCard({
  preview,
  parsedPreview,
  fallbackRecipient,
  fallbackAmount,
  fallbackCurrency,
  fallbackReference,
  executionModeLabel,
  confidenceLabel,
}: PreviewSummaryCardProps) {
  const { t } = useI18n();
  const amountValue =
    typeof parsedPreview?.amount === "number"
      ? parsedPreview.amount
      : Number.parseFloat(fallbackAmount);
  const normalizedAmount = Number.isFinite(amountValue) ? amountValue : null;
  const estimatedFee =
    typeof preview?.quote?.estimated_fee === "number"
      ? preview.quote.estimated_fee
      : null;
  const netTransfer =
    normalizedAmount !== null && estimatedFee !== null
      ? normalizedAmount - estimatedFee
      : null;
  const recipientLabel = parsedPreview?.beneficiaryName || fallbackRecipient || "-";
  const amountLabel =
    normalizedAmount !== null
      ? `${formatNumber(normalizedAmount)} ${parsedPreview?.currency || fallbackCurrency}`
      : `${fallbackAmount} ${fallbackCurrency}`;

  return (
    <section className="rounded-[24px] border border-[#cfe0f7] bg-[linear-gradient(180deg,#f6faff_0%,#ffffff_100%)] p-4 shadow-sm motion-scale-in surface-transition">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#496896]">
            {t("command.previewSummary")}
          </p>
          <h3 className="mt-1 text-lg font-semibold tracking-[-0.02em] text-slate-950">
            {recipientLabel}
          </h3>
        </div>
        <div className="rounded-2xl border border-[#d8e1f0] bg-white px-4 py-3 text-right">
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("common.amount")}</p>
          <p className="mt-1 text-lg font-semibold tracking-[-0.03em] text-slate-950">{amountLabel}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3 text-sm text-slate-700">
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.beneficiary")}</p>
          <p className="mt-2 font-semibold text-slate-900">{recipientLabel}</p>
        </div>
        <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-3 text-sm text-slate-700">
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("common.amount")}</p>
          <p className="mt-2 font-semibold text-slate-900">{amountLabel}</p>
        </div>
        <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.splitCount")}</p>
          <p className="mt-2 font-semibold text-slate-900">{parsedPreview?.splitCount ?? "-"}</p>
        </div>
        <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("common.reference")}</p>
          <p className="mt-2 font-semibold text-slate-900">{parsedPreview?.reference || fallbackReference || "-"}</p>
        </div>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.aiConfidence")}</p>
          <p className="mt-2 font-semibold text-slate-900">{confidenceLabel || "-"}</p>
        </div>
        <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.aiRecommendedMode")}</p>
          <p className="mt-2 font-semibold text-slate-900">{executionModeLabel || "-"}</p>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[#496896]">
          {t("command.feeSummary")}
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.estimatedFee")}</p>
            <p className="mt-2 font-semibold text-slate-900">{estimatedFee !== null ? formatNumber(estimatedFee) : "-"}</p>
          </div>
          <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.netTransfer")}</p>
            <p className="mt-2 font-semibold text-slate-900">{netTransfer !== null ? formatNumber(netTransfer) : "-"}</p>
          </div>
          <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{t("command.totalAmount")}</p>
            <p className="mt-2 font-semibold text-slate-900">{normalizedAmount !== null ? formatNumber(normalizedAmount) : "-"}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
