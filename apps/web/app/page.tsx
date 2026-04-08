"use client";

import Link from "next/link";

import { useI18n } from "../lib/i18n-provider";

const FEATURE_TONES = [
  "from-[#07123d] via-[#10266a] to-[#173f8c]",
  "from-[#07133f] via-[#11295f] to-[#21577b]",
  "from-[#0a1647] via-[#182d7d] to-[#3051b4]",
  "from-[#07133f] via-[#10245d] to-[#1a3d8c]",
];

const FEATURE_STATS = ["$0.01", "VISIBLE", "FIAT → USDT", "3 MODES"];

export default function HomePage() {
  const { t, lang } = useI18n();

  const featureMicro = lang === "zh"
    ? ["费用可预期", "按需可见", "结算桥接", "多路径路由"]
    : ["Predictable fees", "Selective visibility", "Bridge settlement", "Flexible routing"];

  const featureVisualBody = lang === "zh"
    ? [
        "执行前先看到清晰费用，不把支付成本留到最后一刻。",
        "把需要公开的信息留给流程，把需要克制的信息留给权限。",
        "法币收款与稳定币出金，被接到同一条执行轨道上。",
        "同一支付对象，可以切到 operator、wallet、Safe 三条路径。",
      ]
    : [
        "See fee expectations before execution instead of learning cost at the last step.",
        "Keep the workflow visible while exposing only the right level of detail.",
        "Fiat collection and stablecoin payout share one settlement rail.",
        "The same payment object can route through operator, wallet, or Safe paths.",
      ];

  const features = [
    { title: t("home.sidePointA"), body: t("home.featureOneBody") },
    { title: t("home.sidePointB"), body: t("home.featureThreeBody") },
    { title: t("home.sidePointC"), body: t("home.featureTwoBody") },
    { title: t("home.storyThreeTitle"), body: t("home.storyThreeBody") },
  ];

  const useCases = [
    { title: t("home.storyOneTitle"), body: t("home.storyOneBody"), href: "/command-center" },
    { title: t("home.storyTwoTitle"), body: t("home.storyTwoBody"), href: "/merchant" },
    { title: t("home.storyThreeTitle"), body: t("home.modeOperatorBody"), href: "/modes" },
    { title: t("home.useCaseThreeTitle"), body: t("home.modeWalletBody"), href: "/modes" },
    { title: t("home.useCaseFourTitle"), body: t("home.modeSafeBody"), href: "/modes" },
    { title: t("home.processTitle"), body: t("home.processBody"), href: "/command-center" },
  ];

  return (
    <main className="relative left-1/2 right-1/2 -mx-[50vw] w-screen overflow-hidden bg-[#f7f7f2] motion-scale-in">
      <section className="relative min-h-[88vh] overflow-hidden bg-[linear-gradient(180deg,#0a1324_0%,#203c63_48%,#5d8aa0_82%,#efe2bf_100%)] text-white">
        <div className="absolute inset-0 opacity-45 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:132px_132px]" />
        <div className="absolute inset-x-0 top-12 h-[460px] bg-[radial-gradient(circle_at_18%_24%,rgba(125,211,252,0.12),transparent_22%),radial-gradient(circle_at_72%_68%,rgba(255,255,255,0.08),transparent_18%)]" />
        <div className="absolute right-[-24%] top-[8%] h-[760px] w-[760px] rounded-full border border-white/32" />
        <div className="absolute right-[-8%] top-[36%] h-[560px] w-[560px] rounded-full border border-white/22" />
        <div className="absolute left-[67%] top-[15%] h-[380px] w-px bg-white/18" />
        <div className="absolute left-[67%] top-[15%] h-px w-[28vw] bg-white/12" />
        <div className="absolute bottom-[-7vw] left-[-3vw] h-[18vw] w-[34vw] rounded-[100%] bg-white/48 blur-[1px]" />

        <div className="relative mx-auto flex min-h-[88vh] w-full max-w-7xl items-center px-6 pb-24 pt-28 lg:px-10">
          <div className="max-w-4xl motion-fade-up">
            <p className="text-[12px] uppercase tracking-[0.34em] text-[#d7d39a]">{t("home.badge")}</p>
            <h1 className="mt-6 max-w-5xl whitespace-pre-line text-5xl font-medium tracking-[-0.04em] leading-[0.94] text-white lg:text-[96px]">
              {t("home.heroTitle")}
            </h1>
            <p className="mt-8 max-w-3xl text-lg leading-8 text-slate-100/90 lg:text-[29px] lg:leading-[1.34]">
              {t("home.heroBody")}
            </p>

            <div className="mt-10 flex flex-wrap gap-4 motion-fade-up motion-delay-1">
              <Link
                href="/command-center"
                prefetch={false}
                className="inline-flex items-center rounded-xl bg-[#c6d3f1] px-6 py-3 text-sm font-semibold text-slate-900 shadow-[0_10px_24px_rgba(198,211,241,0.18)] transition hover:bg-[#d7e0f7]"
              >
                {t("home.primaryCta")}
              </Link>
              <Link
                href="/merchant"
                prefetch={false}
                className="inline-flex items-center rounded-xl border border-white/55 bg-transparent px-6 py-3 text-sm font-semibold text-white transition hover:bg-white/8"
              >
                {t("home.secondaryCta")}
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 py-20 lg:px-8 lg:py-28 motion-fade-up motion-delay-1">
        <div className="max-w-4xl">
          <p className="text-[12px] uppercase tracking-[0.34em] text-[#9a7a3b]">{t("home.statementEyebrow")}</p>
          <h2 className="mt-5 text-5xl font-medium leading-[0.96] text-slate-950 lg:text-[72px]">
            {t("home.statementTitle")}
          </h2>
          <p className="mt-8 max-w-4xl text-lg leading-8 text-slate-700 lg:text-[28px] lg:leading-[1.35]">
            {t("home.statementBody")}
          </p>
        </div>

        <div className="mt-16 grid gap-5 md:grid-cols-2">
          {features.map((feature, index) => (
            <article
              key={feature.title}
              className={`motion-fade-up surface-transition rounded-[30px] border border-[#d7e0ef] bg-white p-4 shadow-[0_24px_60px_rgba(15,23,42,0.08)] ${
                index === 0
                  ? "motion-delay-1"
                  : index === 1
                    ? "motion-delay-2"
                    : index === 2
                      ? "motion-delay-3"
                      : "motion-delay-4"
              }`}
            >
              <div className={`relative h-52 overflow-hidden rounded-[24px] bg-gradient-to-br ${FEATURE_TONES[index]} p-6 text-white shadow-[0_20px_48px_rgba(12,21,68,0.16)]`}>
                <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] [background-size:72px_72px]" />
                <div className="absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-white/6 to-transparent" />
                <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/10 to-transparent" />
                <div className="relative flex h-full flex-col justify-between">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1.5">
                        <span className="h-2 w-4 rounded-sm bg-white/18" />
                        <span className="h-2 w-6 rounded-sm bg-white/12" />
                      </div>
                      <div>
                        <p className="text-[10px] uppercase tracking-[0.26em] text-white/55">PAYFI</p>
                        <p className="mt-1 text-xs tracking-[0.16em] text-white/70">{featureMicro[index]}</p>
                      </div>
                    </div>
                    <div className="h-px w-20 bg-white/15" />
                  </div>

                  <div className="grid gap-4">
                    <div className="flex items-end justify-between gap-4">
                      <div>
                        <p className="text-3xl font-medium tracking-[-0.04em] text-white/95">{FEATURE_STATS[index]}</p>
                        <p className="mt-2 max-w-[220px] text-sm leading-6 text-white/70">{featureVisualBody[index]}</p>
                      </div>
                      {index === 0 ? (
                        <div className="w-[220px] rounded-2xl border border-white/12 bg-[#081427]/45 px-4 py-3 backdrop-blur-sm">
                          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-white/45">
                            <span>{lang === "zh" ? "预览报价" : "preview quote"}</span>
                            <span>operator</span>
                          </div>
                          <div className="mt-3 space-y-2">
                            <div className="flex items-center justify-between rounded-xl bg-white/[0.05] px-3 py-2 text-sm text-white/88">
                              <span>{lang === "zh" ? "预计费用" : "estimated fee"}</span>
                              <span>$0.01</span>
                            </div>
                            <div className="flex items-center justify-between rounded-xl bg-white/[0.05] px-3 py-2 text-sm text-white/88">
                              <span>{lang === "zh" ? "净出款" : "net transfer"}</span>
                              <span>$455.99</span>
                            </div>
                          </div>
                          <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-3">
                            <span className="text-xs uppercase tracking-[0.22em] text-white/45">usd</span>
                            <span className="text-2xl text-white/92">$456</span>
                          </div>
                        </div>
                      ) : index === 1 ? (
                        <div className="w-[220px] rounded-2xl border border-white/12 bg-[#081427]/45 px-4 py-4 backdrop-blur-sm">
                          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-white/45">
                            <span>{lang === "zh" ? "信息权限" : "visibility policy"}</span>
                            <span>active</span>
                          </div>
                          <div className="mt-3 space-y-2">
                            <div className="flex items-center justify-between rounded-xl bg-white/[0.05] px-3 py-2 text-xs text-white/75">
                              <span>{lang === "zh" ? "对手方名称" : "counterparty name"}</span>
                              <span className="rounded-md bg-emerald-300/15 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-emerald-100">visible</span>
                            </div>
                            <div className="flex items-center justify-between rounded-xl bg-white/[0.05] px-3 py-2 text-xs text-white/75">
                              <span>{lang === "zh" ? "内部批次号" : "internal batch id"}</span>
                              <span className="rounded-md bg-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-white/65">restricted</span>
                            </div>
                          </div>
                          <div className="mt-3 flex items-center justify-between gap-4">
                            <span className="text-xs tracking-[0.18em] text-white/50">{lang === "zh" ? "按需显示" : "private when needed"}</span>
                            <div className="grid h-7 w-16 grid-cols-2 rounded-lg bg-lime-300/90 p-1 shadow-[0_0_18px_rgba(163,230,53,0.42)]">
                              <div />
                              <div className="h-5 rounded-md bg-white" />
                            </div>
                          </div>
                        </div>
                      ) : index === 2 ? (
                        <div className="w-[220px] rounded-2xl border border-white/12 bg-[#081427]/45 px-4 py-4 backdrop-blur-sm">
                          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-white/45">
                            <span>{lang === "zh" ? "充值入账" : "funding credit"}</span>
                            <span>stripe</span>
                          </div>
                          <div className="mt-3 grid gap-2">
                            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-xs tracking-[0.18em] text-white/55">
                              <span className="rounded-lg border border-white/12 px-3 py-1 text-center">{lang === "zh" ? "法币" : "Fiat"}</span>
                              <span className="text-white/30">→</span>
                              <span className="rounded-lg border border-white/12 px-3 py-1 text-center">USDT</span>
                            </div>
                            <div className="rounded-xl bg-white/[0.05] px-3 py-2 text-xs text-white/75">
                              <div className="flex items-center justify-between">
                                <span>{lang === "zh" ? "状态" : "status"}</span>
                                <span>{lang === "zh" ? "已确认入账" : "credited"}</span>
                              </div>
                            </div>
                          </div>
                          <div className="mt-4 h-2 rounded-md bg-white/10">
                            <div className="h-2 w-[78%] rounded-md bg-sky-200/70" />
                          </div>
                        </div>
                      ) : (
                        <div className="w-[220px] rounded-2xl border border-white/12 bg-[#081427]/45 px-4 py-4 backdrop-blur-sm">
                          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-white/45">
                            <span>{lang === "zh" ? "路由建议" : "route recommendation"}</span>
                            <span>live</span>
                          </div>
                          <div className="mt-3 grid gap-2">
                            {["operator", "wallet", "safe"].map((item) => (
                              <div
                                key={item}
                                className="grid grid-cols-[1fr_auto] items-center rounded-lg border border-white/14 bg-white/[0.07] px-3 py-1.5 text-xs tracking-[0.18em] text-white/78"
                              >
                                <span>{item}</span>
                                <span className="text-[10px] text-white/45">{item === "operator" ? "ready" : item === "wallet" ? "attach" : "approve"}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-[10px] uppercase tracking-[0.18em] text-white/42">
                      {index === 0 ? (
                        <>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "费用" : "fee"}</div>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "净额" : "net"}</div>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "确认" : "confirm"}</div>
                        </>
                      ) : index === 1 ? (
                        <>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "可见" : "visible"}</div>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "受限" : "restricted"}</div>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "审计" : "audit"}</div>
                        </>
                      ) : index === 2 ? (
                        <>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "收款" : "fiat in"}</div>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "换汇" : "fx"}</div>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">{lang === "zh" ? "出金" : "payout"}</div>
                        </>
                      ) : (
                        <>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">operator</div>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">wallet</div>
                          <div className="rounded-md bg-white/[0.06] px-2 py-1">safe</div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>
              <div className="px-1 pb-1 pt-5">
                <h3 className="text-[29px] font-medium leading-[1.06] tracking-[-0.035em] text-slate-950">
                  {feature.title}
                </h3>
                <p className="mt-3 text-[15px] leading-7 text-slate-600">{feature.body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 pb-24 lg:px-8 lg:pb-28 motion-fade-up motion-delay-2">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-4xl">
            <p className="text-[12px] uppercase tracking-[0.34em] text-[#9a7a3b]">{t("home.pathEyebrow")}</p>
            <h2 className="mt-5 text-5xl font-medium leading-[0.96] text-slate-950 lg:text-[72px]">
              {t("home.pathTitle")}
            </h2>
            <p className="mt-7 max-w-3xl text-lg leading-8 text-slate-700">{t("home.pathBody")}</p>
          </div>
          <div className="flex gap-3">
            <span className="rounded-md bg-[#47679b] px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-white">
              {t("home.primaryCta")}
            </span>
            <span className="rounded-md border border-[#9cb3d5] px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-[#5a76a4]">
              {t("home.secondaryCta")}
            </span>
          </div>
        </div>

        <div className="mt-10 grid border border-[#c8d4ea] md:grid-cols-3">
          {useCases.map((item, index) => (
            <Link
              key={`${item.title}-${index}`}
              href={item.href}
              prefetch={false}
              className={`min-h-[250px] border-b border-r border-[#c8d4ea] bg-white p-6 transition hover:bg-[#f7f9fd] hover:shadow-[inset_0_0_0_1px_rgba(97,126,181,0.14)] md:[&:nth-child(3n)]:border-r-0 md:[&:nth-last-child(-n+3)]:border-b-0 motion-fade-up surface-transition ${
                index < 2
                  ? "motion-delay-1"
                  : index < 4
                    ? "motion-delay-2"
                    : "motion-delay-3"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="h-6 w-6 text-[#d49435]">⌁</div>
                <div className="h-px w-10 bg-[#c8d4ea]" />
              </div>
              <h3 className="mt-5 text-[24px] font-medium leading-tight tracking-[-0.02em] text-slate-950">{item.title}</h3>
              <p className="mt-4 text-sm leading-7 text-slate-700">{item.body}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="border-t border-slate-200 bg-[#111418] motion-fade-up motion-delay-3">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>
            <p className="text-[11px] uppercase tracking-[0.32em] text-white/55">{t("home.ctaEyebrow")}</p>
            <p className="mt-2 text-lg font-medium text-white">{t("home.ctaTitle")}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/command-center"
              prefetch={false}
              className="inline-flex items-center rounded-xl bg-[#c6d3f1] px-5 py-2.5 text-sm font-semibold text-slate-900 transition hover:bg-[#d7e0f7]"
            >
              {t("home.primaryCta")}
            </Link>
            <Link
              href="/merchant"
              prefetch={false}
              className="inline-flex items-center rounded-xl border border-white/30 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              {t("home.secondaryCta")}
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
