"use client";

import { StatusBadge } from "./status-badge";
import { useI18n } from "../lib/i18n-provider";

type RiskSummary = {
  decision?: string | null;
  risk_level?: string | null;
  reason_codes?: string[] | null;
  user_message?: string | null;
};

type RiskSummaryCardProps = {
  risk: RiskSummary | null | undefined;
  title?: string;
};

export function RiskSummaryCard({ risk, title }: RiskSummaryCardProps) {
  const { t } = useI18n();
  if (!risk) {
    return (
      <section className="rounded-[24px] border border-[#d8e1f0] bg-white p-4 shadow-sm motion-scale-in surface-transition">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#496896]">
          {title ?? t("component.riskSummary")}
        </p>
        <p className="mt-3 text-sm text-slate-500">{t("component.noRiskPreview")}</p>
      </section>
    );
  }

  const codes = (risk.reason_codes || []).filter(Boolean);
  const decision = (risk.decision || "unknown").toLowerCase();
  const tone =
    decision === "block"
      ? {
          outer: "border-rose-200 bg-[linear-gradient(180deg,#fff5f5_0%,#ffffff_100%)]",
          panel: "border-rose-200 bg-rose-50",
          label: "text-rose-700",
        }
      : decision === "review"
        ? {
            outer: "border-amber-200 bg-[linear-gradient(180deg,#fff9eb_0%,#ffffff_100%)]",
            panel: "border-amber-200 bg-amber-50",
            label: "text-amber-700",
          }
        : {
            outer: "border-[#d8e1f0] bg-white",
            panel: "border-[#d8e1f0] bg-[#f7f9fd]",
            label: "text-[#496896]",
          };

  return (
    <section className={`rounded-[24px] border p-4 shadow-sm motion-scale-in surface-transition ${tone.outer}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className={`text-xs font-semibold uppercase tracking-[0.18em] ${tone.label}`}>
            {title ?? t("component.riskSummary")}
          </p>
          <p className="mt-2 text-sm leading-7 text-slate-700">
            {risk.user_message || t("component.noRiskPreview")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={risk.decision || "unknown"} />
          <StatusBadge status={risk.risk_level || "unknown"} />
        </div>
      </div>

      <div className={`mt-4 rounded-xl border p-3 ${tone.panel}`}>
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
          {t("common.reasonCodes")}
        </p>
        {codes.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {codes.map((code) => (
              <span
                key={code}
                className="rounded-full border border-slate-300 bg-white px-2.5 py-1 text-xs font-mono text-slate-700"
              >
                {code}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-500">{t("component.noReasonCodes")}</p>
        )}
      </div>

      {decision === "block" || decision === "review" ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
              {t("common.status")}
            </p>
            <p className="mt-2 font-semibold text-slate-900">{risk.decision || "-"}</p>
          </div>
          <div className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm text-slate-700">
            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
              {t("command.aiConfidence")}
            </p>
            <p className="mt-2 font-semibold text-slate-900">{risk.risk_level || "-"}</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
