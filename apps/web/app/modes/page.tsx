"use client";

import { useMemo } from "react";

import { useI18n } from "../../lib/i18n-provider";
import { StatusBadge } from "../../components/status-badge";

type ModeCard = {
  mode: "operator" | "user_wallet" | "safe";
  title: string;
  summary: string;
  bestFor: string;
  nextAction: string;
  strengths: string[];
  tradeoffs: string[];
};

function buildModeCards(lang: "zh" | "en"): ModeCard[] {
  if (lang === "zh") {
    return [
      {
        mode: "operator",
        title: "Operator 模式",
        summary: "平台代表用户直接提交链上交易，适合希望最快完成结算并立即看到链上结果的场景。",
        bestFor: "运营主导、追求最快确认、希望把流程尽量缩短的日常结算。",
        nextAction: "completed",
        strengths: ["确认路径最短", "最快返回 tx_hash 与 explorer", "最适合日常运营推进"],
        tradeoffs: ["需要接受平台代提交", "不适合必须自签或多签审批的结算"],
      },
      {
        mode: "user_wallet",
        title: "User Wallet 模式",
        summary: "平台只生成待签名交易，最终签名和提交动作由用户在自己的钱包里完成。",
        bestFor: "希望保留私钥控制权、但仍需要完整结算追踪的自托管场景。",
        nextAction: "sign_in_wallet",
        strengths: ["平台不接触用户签名", "仍保留 execution item 跟踪", "适合钱包自签与企业热钱包流程"],
        tradeoffs: ["依赖外部钱包完成最后一步", "最终完成时间取决于回填 tx 与回执同步"],
      },
      {
        mode: "safe",
        title: "Safe 模式",
        summary: "平台生成 Safe proposal，由外部多签审批通过后再执行最终链上交易。",
        bestFor: "机构金库、财务审批和多角色共签的结算流程。",
        nextAction: "approve_in_safe",
        strengths: ["保留多签审批链路", "proposal 与执行记录保持对齐", "最适合机构治理要求"],
        tradeoffs: ["流程最慢", "仍需在 Safe 外部完成审批并回填执行结果"],
      },
    ];
  }

  return [
    {
      mode: "operator",
      title: "Operator Mode",
      summary:
        "The platform submits the onchain transaction directly, making this the fastest path from confirmation to visible settlement.",
      bestFor: "Operationally managed settlement where speed and a short execution path matter most.",
      nextAction: "completed",
      strengths: ["Shortest route to completion", "Fastest tx hash and explorer visibility", "Best fit for day-to-day operational flow"],
      tradeoffs: ["Requires platform-operated submission", "Not suitable for self-signing or approval-heavy flows"],
    },
    {
      mode: "user_wallet",
      title: "User Wallet Mode",
      summary:
        "The platform prepares unsigned transactions, while the user keeps signing authority inside their own wallet.",
      bestFor: "Self-custody users who want wallet control without giving up settlement tracking.",
      nextAction: "sign_in_wallet",
      strengths: ["No platform-side signing", "Execution items remain fully traceable", "Good fit for wallet-driven treasury or user flows"],
      tradeoffs: ["Requires an external wallet interaction", "Completion depends on tx attachment and receipt sync"],
    },
    {
      mode: "safe",
      title: "Safe Mode",
      summary:
        "The platform prepares a Safe proposal first, then waits for the external multi-signature process to approve and execute.",
      bestFor: "Treasury, finance, and institution workflows that require shared approval before settlement.",
      nextAction: "approve_in_safe",
      strengths: ["Preserves multi-signature governance", "Proposal state stays aligned with execution records", "Best fit for institution-grade approval controls"],
      tradeoffs: ["Slowest path to final settlement", "Still depends on the external Safe flow and result attachment"],
    },
  ];
}

export default function ExecutionModesPage() {
  const { lang, t } = useI18n();
  const cards = useMemo(() => buildModeCards(lang), [lang]);

  return (
    <main className="space-y-6 pb-20 motion-scale-in">
      <section className="relative overflow-hidden rounded-[36px] border border-slate-900 bg-[linear-gradient(180deg,#0b1730_0%,#274a72_64%,#5d829a_100%)] p-6 text-white shadow-[0_32px_100px_rgba(9,18,34,0.22)] lg:p-8 motion-fade-up">
        <div className="absolute inset-0 opacity-35 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:124px_124px]" />
        <div className="absolute right-[-10%] top-[-6%] h-[320px] w-[320px] rounded-full border border-white/18" />
        <div className="absolute right-[14%] top-[22%] h-[160px] w-[160px] rounded-full border border-white/12" />
        <div className="relative grid gap-6 lg:grid-cols-[1fr_320px] lg:items-end">
          <div className="motion-fade-up">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d7d39a]">{t("modes.badge")}</p>
            <h1 className="mt-4 text-4xl font-medium tracking-[-0.04em] leading-[0.96] lg:text-6xl">
              {t("modes.title")}
            </h1>
            <p className="mt-5 max-w-4xl text-base leading-8 text-slate-100/90">{t("modes.intro")}</p>
          </div>
          <div className="grid gap-3">
            <div className="rounded-[22px] border border-white/10 bg-white/[0.06] px-4 py-4 backdrop-blur motion-fade-up motion-delay-1 surface-transition">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-300">{t("modes.bestFor")}</p>
                <p className="mt-2 text-sm leading-7 text-slate-100/88">
                  {lang === "zh"
                  ? "三种模式背后用的是同一套结算对象与时间线，所以切换模式不会改变资金流本身，只会改变最后由谁来提交。"
                  : "All three modes share the same settlement objects and timeline, so the funds flow stays the same while the final submitter changes."}
                </p>
              </div>
              <div className="rounded-[22px] border border-white/10 bg-white/[0.06] px-4 py-4 backdrop-blur motion-fade-up motion-delay-2 surface-transition">
                <p className="text-[11px] uppercase tracking-[0.22em] text-slate-300">{t("modes.nextAction")}</p>
                <p className="mt-2 text-sm leading-7 text-slate-100/88">
                  {lang === "zh"
                  ? "Operator 直接上链，User Wallet 交给钱包签名，Safe 交给多签审批。页面的重点不是技术实现，而是帮你判断应该把最终提交动作交给谁。"
                  : "Operator submits onchain, User Wallet hands off to wallet signing, and Safe hands off to multi-signature approval. The goal here is to decide who should control the final submission step."}
                </p>
              </div>
            </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-3 motion-fade-up motion-delay-1">
        {cards.map((card) => (
          <article
            key={card.mode}
            className={`rounded-[30px] border border-[#c8d4ea] bg-white p-6 shadow-sm motion-fade-up surface-transition ${
              card.mode === "operator"
                ? "motion-delay-1"
                : card.mode === "user_wallet"
                  ? "motion-delay-2"
                  : "motion-delay-3"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-slate-900">{card.title}</h2>
              <StatusBadge status={card.mode} />
            </div>
            <p className="mt-3 text-sm leading-7 text-slate-600">{card.summary}</p>
            <p className="mt-4 text-sm leading-7 text-slate-700">
              <span className="font-semibold">{t("modes.bestFor")}:</span> {card.bestFor}
            </p>
            <div className="mt-4 rounded-2xl border border-slate-900 bg-[linear-gradient(180deg,#091427_0%,#163358_100%)] px-4 py-3 text-white">
              <p className="text-[11px] uppercase tracking-[0.2em] text-slate-300">{t("modes.nextAction")}</p>
              <p className="mt-2 text-sm font-semibold text-white">{card.nextAction}</p>
            </div>
            <div className="mt-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#496896]">{t("modes.pros")}</p>
              {card.strengths.map((item) => (
                <p
                  key={item}
                  className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] px-3 py-2 text-sm text-slate-700"
                >
                  {item}
                </p>
              ))}
            </div>
            <div className="mt-3 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#496896]">{t("modes.notes")}</p>
              {card.tradeoffs.map((item) => (
                <p
                  key={item}
                  className="rounded-xl border border-[#d8e1f0] bg-white px-3 py-2 text-sm text-slate-600"
                >
                  {item}
                </p>
              ))}
            </div>
          </article>
        ))}
      </section>

      <section className="rounded-[30px] border border-[#c8d4ea] bg-white p-6 shadow-sm motion-fade-up motion-delay-2 surface-transition">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">{t("modes.sampleFlow")}</h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">
          {lang === "zh"
            ? "无论选择哪种模式，状态都会落回同一套结算语义里。这样运营、审计和外部协作者看到的是同一条真实结算轨迹。"
            : "No matter which mode you choose, status rolls back into the same settlement semantics. Operations, audit, and external collaborators all see the same truthful settlement trail."}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StatusBadge status="planned" />
          <span className="text-slate-400">→</span>
          <StatusBadge status="in_progress" />
          <span className="text-slate-400">→</span>
          <StatusBadge status="submitted_onchain" />
          <span className="text-slate-400">→</span>
          <StatusBadge status="confirmed_onchain" />
          <span className="text-slate-400">{t("common.or")}</span>
          <StatusBadge status="partially_executed" />
        </div>
      </section>
    </main>
  );
}
