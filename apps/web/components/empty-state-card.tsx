"use client";

import type { ReactNode } from "react";

type EmptyStateCardProps = {
  title: string;
  description: string;
  action?: ReactNode;
};

export function EmptyStateCard({ title, description, action }: EmptyStateCardProps) {
  return (
    <div className="rounded-[24px] border border-dashed border-[#c8d4ea] bg-gradient-to-b from-[#f7f9fd] to-white p-5">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-full border border-[#c8d4ea] bg-white text-[#496896]">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            className="h-4 w-4"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <p className="mt-1 text-sm text-slate-600">{description}</p>
          {action ? <div className="mt-3">{action}</div> : null}
        </div>
      </div>
    </div>
  );
}
