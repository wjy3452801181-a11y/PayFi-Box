"use client";

import { FormEvent } from "react";
import type { RecipientRecord } from "../../lib/recipient-book";
import { RecipientSelector } from "../recipient-selector";
import { EmptyStateCard } from "../empty-state-card";
import { useI18n } from "../../lib/i18n-provider";

type QuotePreview = {
  source_amount: number;
  source_currency: string;
  target_amount: number;
  target_currency: string;
  fx_rate: number;
  platform_fee: number;
  network_fee: number;
  total_fee_amount: number;
  expires_at?: string | null;
} | null;

type QuoteCardProps = {
  loading: boolean;
  merchantId: string;
  sourceCurrency: string;
  sourceAmount: string;
  targetCurrency: string;
  targetNetwork: string;
  recipients: RecipientRecord[];
  selectedRecipientId: string;
  onMerchantIdChange: (value: string) => void;
  onSourceCurrencyChange: (value: string) => void;
  onSourceAmountChange: (value: string) => void;
  onTargetCurrencyChange: (value: string) => void;
  onTargetNetworkChange: (value: string) => void;
  onSelectRecipient: (id: string) => void;
  onCreateRecipient: (payload: {
    name: string;
    address: string;
    network: string;
    note?: string;
  }) => void;
  onSubmit: (event: FormEvent) => void;
  quote: QuotePreview;
};

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatAmount(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 }).format(value);
}

export function QuoteCard({
  loading,
  merchantId,
  sourceCurrency,
  sourceAmount,
  targetCurrency,
  targetNetwork,
  recipients,
  selectedRecipientId,
  onMerchantIdChange,
  onSourceCurrencyChange,
  onSourceAmountChange,
  onTargetCurrencyChange,
  onTargetNetworkChange,
  onSelectRecipient,
  onCreateRecipient,
  onSubmit,
  quote,
}: QuoteCardProps) {
  const { t } = useI18n();

  return (
    <section className="space-y-4 rounded-[30px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
        {t("merchant.panelA")}
      </h2>

      <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-2">
        <label className="space-y-1">
          <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
            {t("merchant.merchantId")}
          </span>
          <input
            value={merchantId}
            onChange={(event) => onMerchantIdChange(event.target.value)}
            className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
          />
        </label>

        <RecipientSelector
          recipients={recipients}
          selectedRecipientId={selectedRecipientId}
          onSelectRecipient={onSelectRecipient}
          onCreateRecipient={onCreateRecipient}
          labelKey="merchant.beneficiaryId"
        />

        <label className="space-y-1">
          <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
            {t("merchant.sourceCurrency")}
          </span>
          <input
            value={sourceCurrency}
            onChange={(event) => onSourceCurrencyChange(event.target.value)}
            className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
            {t("merchant.sourceAmount")}
          </span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={sourceAmount}
            onChange={(event) => onSourceAmountChange(event.target.value)}
            className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
            {t("merchant.targetCurrency")}
          </span>
          <input
            value={targetCurrency}
            onChange={(event) => onTargetCurrencyChange(event.target.value)}
            className="w-full rounded-xl border border-[#c8d4ea] px-3 py-2.5 text-sm outline-none ring-[#496896] focus:ring-2"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
            {t("merchant.targetNetwork")}
          </span>
          <input
            value={targetNetwork}
            onChange={(event) => onTargetNetworkChange(event.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none ring-teal-500 focus:ring-2"
          />
        </label>

        <div className="md:col-span-2">
          <button
            type="submit"
            disabled={loading}
            className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#203a61] disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {loading ? t("merchant.creatingQuote") : t("merchant.createQuote")}
          </button>
        </div>
      </form>

      <section className="rounded-[28px] border border-slate-900 bg-[linear-gradient(180deg,#091427_0%,#163358_100%)] p-5 text-white shadow-[0_24px_60px_rgba(10,19,38,0.18)]">
        <p className="text-xs uppercase tracking-[0.16em] text-teal-200">
          {t("merchant.quoteSummaryTitle")}
        </p>
        {quote ? (
          <>
            <div className="mt-3 grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-end">
              <div>
                <p className="text-xs uppercase tracking-[0.1em] text-teal-200">
                  {t("merchant.merchantPays")}
                </p>
                <p className="mt-1 text-3xl font-semibold">
                  {formatAmount(quote.source_amount)} {quote.source_currency}
                </p>
              </div>
              <div className="text-center text-2xl text-teal-200">→</div>
              <div>
                <p className="text-xs uppercase tracking-[0.1em] text-teal-200">
                  {t("merchant.recipientGets")}
                </p>
                <p className="mt-1 text-3xl font-semibold">
                  {formatAmount(quote.target_amount)} {quote.target_currency}
                </p>
              </div>
            </div>
            <div className="mt-4 grid gap-2 rounded-2xl border border-white/14 bg-white/[0.07] p-3 text-sm md:grid-cols-2">
              <p>
                {t("merchant.fxRate")}: <span className="font-semibold">{formatAmount(quote.fx_rate)}</span>
              </p>
              <p>
                {t("merchant.platformFee")}:{" "}
                <span className="font-semibold">{formatAmount(quote.platform_fee)}</span>
              </p>
              <p>
                {t("merchant.networkFee")}:{" "}
                <span className="font-semibold">{formatAmount(quote.network_fee)}</span>
              </p>
              <p>
                {t("merchant.totalFee")}:{" "}
                <span className="font-semibold">{formatAmount(quote.total_fee_amount)}</span>
              </p>
              <p className="md:col-span-2">
                {t("merchant.expiresAt")}:{" "}
                <span className="font-semibold">{formatTime(quote.expires_at)}</span>
              </p>
            </div>
          </>
        ) : (
          <div className="mt-3">
            <EmptyStateCard title={t("merchant.quoteSummaryTitle")} description={t("merchant.quoteEmpty")} />
          </div>
        )}
      </section>
    </section>
  );
}
