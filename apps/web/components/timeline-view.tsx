"use client";

import type { TimelineItem } from "../lib/api";
import { useI18n } from "../lib/i18n-provider";

type TimelineViewProps = {
  items: TimelineItem[];
  title?: string;
  emptyText?: string;
};

function toLocalTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function TimelineView({
  items,
  title,
  emptyText,
}: TimelineViewProps) {
  const { t } = useI18n();
  return (
    <section className="rounded-[24px] border border-[#c8d4ea] bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
          {title ?? t("component.timeline")}
        </h3>
        <span className="text-xs text-slate-500">
          {items.length} {t("component.eventCount")}
        </span>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">{emptyText ?? t("component.noTimeline")}</p>
      ) : (
        <ol className="space-y-3">
          {items.map((item) => (
            <li
              key={`${item.entity_id}-${item.action}-${item.timestamp}`}
              className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                <span className="text-xs text-slate-500">{toLocalTime(item.timestamp)}</span>
              </div>
              <p className="mt-1 text-xs uppercase tracking-[0.1em] text-slate-500">
                {item.action} · {item.entity_type}
              </p>
              {item.details ? (
                <pre className="mt-2 max-h-52 overflow-auto rounded-lg bg-slate-900 p-2 text-xs leading-5 text-slate-100">
                  {JSON.stringify(item.details, null, 2)}
                </pre>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
