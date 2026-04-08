"use client";

import type { ExecutionItemSummary } from "../lib/api";
import { JsonView } from "./json-view";
import { StatusBadge } from "./status-badge";
import { useI18n } from "../lib/i18n-provider";

type ExecutionItemTableProps = {
  items: ExecutionItemSummary[];
  title?: string;
  emptyText?: string;
};

function shortenHash(hash: string): string {
  if (hash.length < 16) return hash;
  return `${hash.slice(0, 8)}...${hash.slice(-8)}`;
}

export function ExecutionItemTable({
  items,
  title,
  emptyText,
}: ExecutionItemTableProps) {
  const { t, statusLabel } = useI18n();
  return (
    <section className="rounded-[24px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
          {title ?? t("component.executionItems")}
        </h3>
        <span className="text-xs text-slate-500">
          {items.length} {t("common.items")}
        </span>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">{emptyText ?? t("component.noExecutionItems")}</p>
      ) : (
        <div className="space-y-3">
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-[#d8e1f0] text-left text-xs uppercase tracking-[0.12em] text-slate-500">
                  <th className="px-2 py-2">{t("common.sequence")}</th>
                  <th className="px-2 py-2">{t("common.amount")}</th>
                  <th className="px-2 py-2">{t("common.status")}</th>
                  <th className="px-2 py-2">{t("common.onchain")}</th>
                  <th className="px-2 py-2">{t("common.pendingAction")}</th>
                  <th className="px-2 py-2">{t("common.txHash")}</th>
                  <th className="px-2 py-2">{t("common.explorer")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-[#eef3fb] align-top">
                    <td className="px-2 py-3 font-mono text-xs text-slate-700">{item.sequence}</td>
                    <td className="px-2 py-3 text-slate-900">
                      {item.amount} {item.currency}
                    </td>
                    <td className="px-2 py-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-2 py-3">
                      <StatusBadge status={item.onchain_status || "unknown"} />
                    </td>
                    <td className="px-2 py-3 text-xs text-slate-600">
                      {item.pending_action ? statusLabel(item.pending_action) : "-"}
                    </td>
                    <td className="px-2 py-3 font-mono text-xs text-slate-700">
                      {item.tx_hash ? shortenHash(item.tx_hash) : "-"}
                    </td>
                    <td className="px-2 py-3">
                      {item.explorer_url ? (
                        <a
                          className="text-xs font-medium text-[#32527f] hover:text-[#203a61]"
                          href={item.explorer_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {t("common.openExplorer")}
                        </a>
                      ) : (
                        <span className="text-xs text-slate-400">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {items.map((item) => {
            const hasAttachment =
              item.safe_proposal_attachment ||
              item.safe_proposal_request ||
              item.unsigned_tx_request ||
              item.tx_attachment ||
              item.failure_reason ||
              item.is_duplicate_rejected;
            if (!hasAttachment) return null;

            return (
              <div key={`${item.id}-meta`} className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] p-3">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-slate-600">item {item.sequence}</span>
                  {item.is_duplicate_rejected ? (
                    <span className="rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                      {statusLabel("duplicate_rejected")}
                    </span>
                  ) : null}
                  {item.failure_reason ? (
                    <span className="rounded-full border border-rose-300 bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700">
                      {statusLabel("failed")}: {item.failure_reason}
                    </span>
                  ) : null}
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  {item.unsigned_tx_request ? (
                    <JsonView title={t("component.unsignedTxRequest")} data={item.unsigned_tx_request} />
                  ) : null}
                  {item.safe_proposal_request ? (
                    <JsonView title={t("component.safeProposalRequest")} data={item.safe_proposal_request} />
                  ) : null}
                  {item.safe_proposal_attachment ? (
                    <JsonView title={t("component.safeProposalAttachment")} data={item.safe_proposal_attachment} />
                  ) : null}
                  {item.tx_attachment ? <JsonView title={t("component.txAttachment")} data={item.tx_attachment} /> : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
