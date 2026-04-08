"use client";

import { StatusBadge } from "./status-badge";
import { useI18n } from "../lib/i18n-provider";

type ExplorerLinkCardProps = {
  network?: string | null;
  txHash?: string | null;
  explorerUrl?: string | null;
  onchainStatus?: string | null;
  title?: string;
};

function shortenHash(hash: string): string {
  if (hash.length < 18) return hash;
  return `${hash.slice(0, 10)}...${hash.slice(-8)}`;
}

export function ExplorerLinkCard({
  network,
  txHash,
  explorerUrl,
  onchainStatus,
  title,
}: ExplorerLinkCardProps) {
  const { t } = useI18n();
  return (
    <section className="rounded-[24px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#496896]">
        {title ?? t("component.onchainExecution")}
      </p>
      <div className="mt-3 space-y-2 text-sm text-slate-700">
        <div className="flex items-center justify-between gap-3">
          <span className="text-slate-500">{t("common.network")}</span>
          <span className="font-medium text-slate-900">{network || "-"}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-slate-500">{t("common.txHash")}</span>
          <span className="font-mono text-xs text-slate-900">{txHash ? shortenHash(txHash) : "-"}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-slate-500">{t("common.status")}</span>
          <StatusBadge status={onchainStatus || "unknown"} />
        </div>
      </div>
      <div className="mt-4">
        {explorerUrl ? (
          <a
            className="inline-flex items-center rounded-xl border border-[#c8d4ea] bg-[#f7f9fd] px-3 py-2 text-sm font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
            href={explorerUrl}
            target="_blank"
            rel="noreferrer"
          >
            {t("common.openExplorer")}
          </a>
        ) : (
          <p className="text-xs text-slate-500">{t("common.noExplorer")}</p>
        )}
      </div>
    </section>
  );
}
