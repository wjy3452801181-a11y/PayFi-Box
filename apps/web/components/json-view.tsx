"use client";

import { useI18n } from "../lib/i18n-provider";

type JsonViewProps = {
  title?: string;
  data: unknown;
  emptyText?: string;
};

export function JsonView({ title, data, emptyText }: JsonViewProps) {
  const { t } = useI18n();
  const hasData = data !== null && data !== undefined;
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-slate-50/80 p-4">
      {title ? (
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">
          {title}
        </h4>
      ) : null}
      {hasData ? (
        <pre className="max-h-72 overflow-auto rounded-xl bg-slate-900 p-3 text-xs leading-6 text-slate-100">
          {JSON.stringify(data, null, 2)}
        </pre>
      ) : (
        <p className="text-sm text-slate-500">{emptyText || t("common.noData")}</p>
      )}
    </section>
  );
}
