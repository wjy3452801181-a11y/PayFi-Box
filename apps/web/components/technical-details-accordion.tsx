"use client";

import Link from "next/link";
import type { CommandResponse, ConfirmResponse } from "../lib/api";
import { JsonView } from "./json-view";
import { useI18n } from "../lib/i18n-provider";

type TechnicalDetailsAccordionProps = {
  preview: CommandResponse | null;
  confirmResult: ConfirmResponse | null;
};

export function TechnicalDetailsAccordion({
  preview,
  confirmResult,
}: TechnicalDetailsAccordionProps) {
  const { t } = useI18n();

  return (
    <details className="rounded-[20px] border border-[#d8e1f0] bg-white p-4 shadow-sm" open={false}>
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.12em] text-slate-600">
        {t("command.technicalDetails")}
      </summary>
      <p className="mt-2 text-xs leading-6 text-slate-500">{t("command.technicalHint")}</p>

      <div className="mt-3 space-y-3">
        <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
          <p className="font-semibold text-slate-900">command_id</p>
          <p className="mt-1 break-all font-mono">{preview?.command_id || "-"}</p>
          <p className="mt-2 font-semibold text-slate-900">payment_order_id</p>
          <p className="mt-1 break-all font-mono">{confirmResult?.payment_order_id || "-"}</p>
          <p className="mt-2 font-semibold text-slate-900">execution_batch_id</p>
          <p className="mt-1 break-all font-mono">{confirmResult?.execution_batch_id || "-"}</p>
          <p className="mt-2 font-semibold text-slate-900">tx_hash</p>
          <p className="mt-1 break-all font-mono">{confirmResult?.execution?.tx_hash || "-"}</p>
        </div>

        {confirmResult?.payment_order_id ? (
          <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
            <p className="font-semibold text-slate-900">{t("command.timelineLink")}</p>
            <Link
              href={`/payments/${confirmResult.payment_order_id}`}
              className="mt-1 inline-block text-blue-700 hover:text-blue-900"
            >
              /payments/{confirmResult.payment_order_id}
            </Link>
          </div>
        ) : null}

        <div className="grid gap-3 lg:grid-cols-2">
          <JsonView title={t("command.quoteTechnical")} data={preview?.quote ?? null} />
          <JsonView title={t("command.executionTechnical")} data={confirmResult?.execution ?? null} />
          <JsonView title={t("command.executionItemsTechnical")} data={confirmResult?.execution_items ?? []} />
          <JsonView title={t("command.splitsTechnical")} data={confirmResult?.splits ?? []} />
          <JsonView title={t("command.rawPreviewResponse")} data={preview ?? null} />
          <JsonView title={t("command.rawConfirmResponse")} data={confirmResult ?? null} />
        </div>
      </div>
    </details>
  );
}
