"use client";

import { useI18n } from "../lib/i18n-provider";

type ExecutionMode = "operator" | "user_wallet" | "safe";

type PrimaryActionCardProps = {
  mode: ExecutionMode;
  canConfirm: boolean;
  loading: boolean;
  onConfirm: () => void;
  summary?: string;
  guidance?: string;
};

function getPrimaryLabel(t: (key: string) => string, mode: ExecutionMode): string {
  if (mode === "operator") return t("command.ctaOperator");
  if (mode === "user_wallet") return t("command.ctaUserWallet");
  return t("command.ctaSafe");
}

function getPrimaryHint(t: (key: string) => string, mode: ExecutionMode): string {
  if (mode === "operator") return t("command.modeOperator");
  if (mode === "user_wallet") return t("command.modeUserWallet");
  return t("command.modeSafe");
}

export function PrimaryActionCard({
  mode,
  canConfirm,
  loading,
  onConfirm,
  summary,
  guidance,
}: PrimaryActionCardProps) {
  const { t } = useI18n();
  const label = getPrimaryLabel(t, mode);
  return (
    <section className="rounded-[24px] border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-4 shadow-sm motion-scale-in surface-transition">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
            {t("command.primaryAction")}
          </h3>
          <p className="mt-2 text-sm text-slate-700">{summary || getPrimaryHint(t, mode)}</p>
        </div>
        <span className="rounded-full border border-[#c8d4ea] bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.08em] text-[#32527f]">
          {mode}
        </span>
      </div>
      {guidance ? (
        <div className="mt-3 rounded-xl border border-[#d8e1f0] bg-white px-3 py-3 text-sm leading-7 text-slate-700">
          {guidance}
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs leading-6 text-slate-500">
          {canConfirm
            ? t("command.aiRouteRationale")
            : t("command.previewLoading")}
        </p>
        <button
          type="button"
          onClick={onConfirm}
          disabled={!canConfirm || loading}
          className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#203a61] disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {loading ? t("command.confirming") : label}
        </button>
      </div>
    </section>
  );
}
