"use client";

import type { CreateFiatPaymentResponse } from "../../lib/api";
import { useI18n } from "../../lib/i18n-provider";
import { StatusBadge } from "../status-badge";

type FiatIntentCardProps = {
  quoteReady: boolean;
  intent: CreateFiatPaymentResponse["fiat_payment"] | null;
  loading: boolean;
  onCreateIntent: () => void;
  reference: string;
  onReferenceChange: (value: string) => void;
};

export function FiatIntentCard({
  quoteReady,
  intent,
  loading,
  onCreateIntent,
  reference,
  onReferenceChange,
}: FiatIntentCardProps) {
  const { t } = useI18n();

  return (
    <section className="space-y-4 rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
        {t("merchant.intentCardTitle")}
      </h2>
      <label className="space-y-1">
        <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
          {t("merchant.reference")}
        </span>
        <input
          value={reference}
          onChange={(event) => onReferenceChange(event.target.value)}
          className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
        />
      </label>
      <button
        type="button"
        onClick={onCreateIntent}
        disabled={!quoteReady || loading}
        className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#203a61] disabled:cursor-not-allowed disabled:bg-slate-400"
      >
        {loading ? t("merchant.creatingIntent") : t("merchant.createIntent")}
      </button>

      {intent ? (
        <div className="rounded-2xl border border-[#d8e1f0] bg-[#f7f9fd] p-3 text-sm text-slate-700">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={intent.status} />
            <StatusBadge status={intent.payment_channel} />
            <StatusBadge status={intent.channel_status || "channel_not_started"} />
          </div>
          <p className="mt-2">
            {t("merchant.fiatPaymentId")}: <span className="font-mono text-xs">{intent.id}</span>
          </p>
          <p className="mt-1">
            {t("merchant.reference")}: {intent.reference || "-"}
          </p>
        </div>
      ) : null}
    </section>
  );
}
