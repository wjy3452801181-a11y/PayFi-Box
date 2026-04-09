"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { clearRememberedAccessSession, getRememberedAccessSession, type AccessSession } from "../lib/api";
import { useI18n } from "../lib/i18n-provider";

const LINKS = [
  { href: "/", labelKey: "nav.home" },
  { href: "/command-center", labelKey: "nav.commandCenter" },
  { href: "/balance", labelKey: "nav.balance" },
  { href: "/merchant", labelKey: "nav.merchant" },
  { href: "/mcp", labelKey: "nav.mcp" },
  { href: "/modes", labelKey: "nav.modes" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function TopNav() {
  const pathname = usePathname();
  const { lang, setLang, t } = useI18n();
  const isHome = pathname === "/";
  const [session, setSession] = useState<AccessSession | null>(null);

  useEffect(() => {
    setSession(getRememberedAccessSession());
  }, [pathname]);

  return (
    <header
      className={`sticky top-0 z-30 backdrop-blur-xl ${
        isHome
          ? "border-b border-white/10 bg-[#081221]/70 shadow-[0_12px_40px_rgba(8,18,33,0.14)]"
          : "border-b border-slate-200/70 bg-white/80 shadow-[0_12px_30px_rgba(15,23,42,0.05)]"
      }`}
    >
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-3 lg:px-8">
        <div>
          <p
            className={`text-[11px] uppercase tracking-[0.28em] ${
              isHome ? "text-slate-400" : "text-slate-500"
            }`}
          >
            PayFi Orchestration Layer
          </p>
          <p className={`text-sm font-semibold ${isHome ? "text-white" : "text-slate-950"}`}>{t("nav.title")}</p>
        </div>
        <div className="flex items-center gap-4">
          <nav className="flex items-center gap-1 lg:gap-2">
            {LINKS.map((link) => {
              const active = isActive(pathname, link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  prefetch={false}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-200 ${
                    isHome
                      ? active
                        ? "bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]"
                        : "text-slate-300 hover:bg-white/6 hover:text-white"
                      : active
                        ? "bg-slate-950 text-white shadow-sm"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
                  }`}
                >
                  {t(link.labelKey)}
                </Link>
              );
            })}
          </nav>
          <div className="hidden items-center gap-2 lg:flex">
            {session ? (
              <>
                <div
                  className={`rounded-lg px-3 py-1.5 text-xs ${
                    isHome
                      ? "border border-white/10 bg-white/[0.04] text-slate-200"
                      : "border border-slate-200 bg-slate-50 text-slate-600"
                  }`}
                >
                  {session.user.email}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    clearRememberedAccessSession();
                    setSession(null);
                  }}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                    isHome
                      ? "text-slate-300 hover:bg-white/6 hover:text-white"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
                  }`}
                >
                  {t("nav.signOut")}
                </button>
              </>
            ) : (
              <Link
                href="/access"
                prefetch={false}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-200 ${
                  isHome
                    ? "border border-white/12 bg-white/[0.04] text-slate-200 hover:bg-white/8 hover:text-white"
                    : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:text-slate-950"
                }`}
              >
                {t("nav.access")}
              </Link>
            )}
          </div>
          <div
            className={`flex items-center gap-1 rounded-lg p-1 ${
              isHome ? "border border-white/10 bg-white/[0.04]" : "border border-slate-200 bg-slate-50"
            }`}
          >
            <button
              type="button"
              onClick={() => setLang("zh")}
              className={`rounded px-2 py-1 text-xs font-semibold transition-all duration-200 ${
                lang === "zh"
                  ? isHome
                    ? "bg-white text-slate-950"
                    : "bg-slate-900 text-white"
                  : isHome
                    ? "text-slate-300 hover:bg-white/10 hover:text-white"
                    : "text-slate-600 hover:bg-white hover:text-slate-900"
              }`}
            >
              {t("nav.lang.zh")}
            </button>
            <button
              type="button"
              onClick={() => setLang("en")}
              className={`rounded px-2 py-1 text-xs font-semibold transition-all duration-200 ${
                lang === "en"
                  ? isHome
                    ? "bg-white text-slate-950"
                    : "bg-slate-900 text-white"
                  : isHome
                    ? "text-slate-300 hover:bg-white/10 hover:text-white"
                    : "text-slate-600 hover:bg-white hover:text-slate-900"
              }`}
            >
              {t("nav.lang.en")}
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
