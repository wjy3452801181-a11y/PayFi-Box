"use client";

import { Suspense } from "react";
import { FormEvent, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { postAccessSession, rememberAccessSession } from "../../lib/api";
import { useI18n } from "../../lib/i18n-provider";

const DEFAULT_EMAILS = [
  "lin.retail@payfi.demo",
  "chen.trade@payfi.demo",
  "wang.analyst@payfi.demo",
];

function AccessPageContent() {
  const { lang } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get("next") || "/command-center";
  const [email, setEmail] = useState(DEFAULT_EMAILS[1]);
  const [accessCode, setAccessCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy = useMemo(
    () =>
      lang === "zh"
        ? {
            eyebrow: "ACCESS",
            title: "建立访问会话",
            body: "输入访问邮箱和访问码，建立当前浏览器会话。建立后，结算发起、平台余额、结算运营、MCP 接入和结算详情都会沿用这一身份上下文。",
            emailLabel: "访问邮箱",
            codeLabel: "访问码",
            submit: "进入平台",
            helper: "本地 seed 账号邮箱已预填；访问码使用当前环境生成的本地访问码。",
            quick: "快速选择",
          }
        : {
            eyebrow: "ACCESS",
            title: "Create an access session",
            body: "Enter an access email and access code to establish the current browser session. Settlement initiation, balance, operations, MCP access, and settlement detail will reuse this identity context.",
            emailLabel: "Access email",
            codeLabel: "Access code",
            submit: "Enter platform",
            helper: "Seed account emails are prefilled for local use. Use the access code generated for the current environment.",
            quick: "Quick select",
          },
    [lang],
  );

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const session = await postAccessSession({
        email: email.trim(),
        access_code: accessCode.trim(),
      });
      rememberAccessSession(session);
      router.push(nextPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : lang === "zh" ? "访问失败" : "Access failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="space-y-8">
      <section className="overflow-hidden rounded-[32px] border border-[#d7deea] bg-[linear-gradient(180deg,#ffffff_0%,#f4f7fc_100%)] px-6 py-8 shadow-[0_20px_60px_rgba(15,23,42,0.06)] lg:px-10">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{copy.eyebrow}</p>
        <div className="mt-4 max-w-2xl space-y-3">
          <h1 className="text-4xl font-semibold tracking-[-0.03em] text-slate-950 lg:text-5xl">{copy.title}</h1>
          <p className="text-base leading-8 text-slate-600">{copy.body}</p>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <form
          onSubmit={handleSubmit}
          className="rounded-[30px] border border-[#c8d4ea] bg-white p-6 shadow-sm surface-transition lg:p-8"
        >
          <div className="space-y-5">
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">{copy.emailLabel}</label>
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-2xl border border-[#cfd9ea] bg-[#fbfdff] px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-[#203456]/30 focus:ring-4 focus:ring-[#dbe8ff]"
                placeholder="chen.trade@payfi.demo"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">{copy.codeLabel}</label>
              <input
                type="password"
                value={accessCode}
                onChange={(event) => setAccessCode(event.target.value)}
                className="w-full rounded-2xl border border-[#cfd9ea] bg-[#fbfdff] px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-[#203456]/30 focus:ring-4 focus:ring-[#dbe8ff]"
                placeholder="payfi-xxxxxx-xxxxxx"
              />
            </div>
            {error ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
            ) : null}
            <button
              type="submit"
              disabled={loading}
              className="rounded-2xl bg-[#0f1b3d] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#162757] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (lang === "zh" ? "连接中..." : "Connecting...") : copy.submit}
            </button>
          </div>
        </form>

        <aside className="rounded-[30px] border border-[#c8d4ea] bg-[linear-gradient(180deg,#f8fbff_0%,#eef4ff_100%)] p-6 shadow-sm surface-transition lg:p-8">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{copy.quick}</p>
          <div className="mt-4 space-y-3">
            {DEFAULT_EMAILS.map((candidate) => (
              <button
                key={candidate}
                type="button"
                onClick={() => setEmail(candidate)}
                className="flex w-full items-center justify-between rounded-2xl border border-[#d3dded] bg-white px-4 py-3 text-left text-sm text-slate-700 transition hover:border-[#b9cae3] hover:bg-[#f8fbff]"
              >
                <span>{candidate}</span>
                <span className="text-xs uppercase tracking-[0.22em] text-slate-400">
                  {lang === "zh" ? "使用" : "Use"}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-5 text-sm leading-7 text-slate-600">{copy.helper}</p>
        </aside>
      </section>
    </main>
  );
}

export default function AccessPage() {
  return (
    <Suspense fallback={<main className="rounded-[30px] border border-[#c8d4ea] bg-white p-6 text-sm text-slate-600 shadow-sm">Loading access…</main>}>
      <AccessPageContent />
    </Suspense>
  );
}
