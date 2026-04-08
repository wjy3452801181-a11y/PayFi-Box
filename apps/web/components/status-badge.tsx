"use client";

import { useI18n } from "../lib/i18n-provider";

const STATUS_STYLES: Record<string, string> = {
  executed: "bg-emerald-100 text-emerald-800 border-emerald-300",
  confirmed: "bg-emerald-100 text-emerald-800 border-emerald-300",
  confirmed_onchain: "bg-emerald-100 text-emerald-800 border-emerald-300",
  partially_executed: "bg-amber-100 text-amber-800 border-amber-300",
  partially_confirmed: "bg-amber-100 text-amber-800 border-amber-300",
  submitted: "bg-blue-100 text-blue-800 border-blue-300",
  submitted_onchain: "bg-blue-100 text-blue-800 border-blue-300",
  submitting: "bg-blue-100 text-blue-800 border-blue-300",
  in_progress: "bg-blue-100 text-blue-800 border-blue-300",
  pending: "bg-slate-100 text-slate-700 border-slate-300",
  awaiting_fiat: "bg-blue-100 text-blue-800 border-blue-300",
  awaiting_channel_payment: "bg-blue-100 text-blue-800 border-blue-300",
  payment_processing: "bg-blue-100 text-blue-800 border-blue-300",
  awaiting_wallet_signature: "bg-violet-100 text-violet-800 border-violet-300",
  awaiting_safe_approval: "bg-violet-100 text-violet-800 border-violet-300",
  duplicate_rejected: "bg-amber-100 text-amber-800 border-amber-300",
  reconciled: "bg-cyan-100 text-cyan-800 border-cyan-300",
  blocked: "bg-rose-100 text-rose-800 border-rose-300",
  blocked_kyc_required: "bg-rose-100 text-rose-800 border-rose-300",
  failed: "bg-rose-100 text-rose-800 border-rose-300",
  failed_onchain: "bg-rose-100 text-rose-800 border-rose-300",
  bridge_failed_recoverable: "bg-rose-100 text-rose-800 border-rose-300",
  declined: "bg-slate-200 text-slate-700 border-slate-300",
  cancelled: "bg-slate-200 text-slate-700 border-slate-300",
};

type StatusBadgeProps = {
  status: string | null | undefined;
  className?: string;
};

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const { statusLabel } = useI18n();
  const value = (status || "unknown").toLowerCase();
  const style = STATUS_STYLES[value] ?? "bg-slate-100 text-slate-700 border-slate-300";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.08em] ${style} ${className}`}
    >
      {statusLabel(value)}
    </span>
  );
}
