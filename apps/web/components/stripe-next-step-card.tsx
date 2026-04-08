"use client";

import Link from "next/link";

type StripeNextAction = "complete_kyc" | "open_checkout" | "none";
type StripeKycStatus = "awaiting" | "completed" | "blocked";
type CardLanguage = "zh" | "en";

type StripeNextStepCardProps = {
  fiatPaymentId: string;
  kycStatus: StripeKycStatus;
  stripeCheckoutUrl?: string;
  nextAction: StripeNextAction;
  language: CardLanguage;
  stripeSessionId?: string;
  paymentIntentId?: string;
  loading?: boolean;
  kycHref?: string;
};

type Copy = {
  badge: string;
  title: string;
  subtitle: string;
  kycStatus: string;
  sessionStatus: string;
  kycAwaiting: string;
  kycCompleted: string;
  kycBlocked: string;
  sessionNeedsKyc: string;
  sessionReady: string;
  sessionWaiting: string;
  ctaCompleteKyc: string;
  ctaOpenCheckout: string;
  ctaWaiting: string;
  openingInNewTab: string;
  debugTitle: string;
  paymentId: string;
  sessionId: string;
  paymentIntentId: string;
};

const COPY: Record<CardLanguage, Copy> = {
  zh: {
    badge: "下一步",
    title: "Stripe 支付下一步",
    subtitle: "请按当前状态完成后续动作，系统将通过 webhook 自动推进结算。",
    kycStatus: "KYC 状态",
    sessionStatus: "Stripe 会话状态",
    kycAwaiting: "待完成",
    kycCompleted: "已完成",
    kycBlocked: "已拦截",
    sessionNeedsKyc: "需先完成 KYC",
    sessionReady: "会话已就绪，可前往支付",
    sessionWaiting: "等待支付完成",
    ctaCompleteKyc: "去完成 KYC",
    ctaOpenCheckout: "打开 Stripe Checkout",
    ctaWaiting: "等待支付完成",
    openingInNewTab: "将在新标签页打开",
    debugTitle: "补充信息",
    paymentId: "fiat_payment_id",
    sessionId: "session_id",
    paymentIntentId: "payment_intent_id",
  },
  en: {
    badge: "Next Step",
    title: "Stripe Payment Next Step",
    subtitle:
      "Follow the current action. Settlement progression is driven by Stripe webhook updates.",
    kycStatus: "KYC Status",
    sessionStatus: "Stripe Session Status",
    kycAwaiting: "Awaiting",
    kycCompleted: "Completed",
    kycBlocked: "Blocked",
    sessionNeedsKyc: "KYC required before checkout",
    sessionReady: "Session ready, continue to checkout",
    sessionWaiting: "Waiting for payment to complete",
    ctaCompleteKyc: "Complete KYC",
    ctaOpenCheckout: "Open Stripe Checkout",
    ctaWaiting: "Waiting for payment to complete",
    openingInNewTab: "Opens in a new tab",
    debugTitle: "Supporting Details",
    paymentId: "fiat_payment_id",
    sessionId: "session_id",
    paymentIntentId: "payment_intent_id",
  },
};

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/70 border-t-white"
    />
  );
}

export function StripeNextStepCard({
  fiatPaymentId,
  kycStatus,
  stripeCheckoutUrl,
  nextAction,
  language,
  stripeSessionId,
  paymentIntentId,
  loading = false,
  kycHref,
}: StripeNextStepCardProps) {
  const copy = COPY[language];
  const resolvedKycHref = kycHref || "/merchant";

  const kycLabel =
    kycStatus === "completed"
      ? copy.kycCompleted
      : kycStatus === "blocked"
        ? copy.kycBlocked
        : copy.kycAwaiting;

  const sessionLabel =
    nextAction === "complete_kyc"
      ? copy.sessionNeedsKyc
      : nextAction === "open_checkout"
        ? copy.sessionReady
        : copy.sessionWaiting;

  return (
    <section className="rounded-[30px] border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#496896]">
        {copy.badge}
      </p>
      <h3 className="mt-1 text-lg font-semibold text-slate-900">{copy.title}</h3>
      <p className="mt-1 text-sm leading-7 text-slate-700">{copy.subtitle}</p>

      <div className="mt-4 grid gap-2 rounded-2xl border border-[#d8e1f0] bg-white/80 p-4 text-sm text-slate-700 sm:grid-cols-2">
        <p>
          {copy.kycStatus}:{" "}
          <span className="font-semibold text-slate-900">{kycLabel}</span>
        </p>
        <p>
          {copy.sessionStatus}:{" "}
          <span className="font-semibold text-slate-900">{sessionLabel}</span>
        </p>
      </div>

      <div className="mt-3">
        {nextAction === "complete_kyc" ? (
          <Link
            href={resolvedKycHref}
            aria-label={copy.ctaCompleteKyc}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium text-white shadow-sm transition ${
              loading
                ? "cursor-not-allowed bg-slate-400"
                : "bg-slate-950 hover:bg-[#203a61]"
            }`}
          >
            {loading ? <Spinner /> : null}
            {copy.ctaCompleteKyc}
          </Link>
        ) : null}

        {nextAction === "open_checkout" ? (
          stripeCheckoutUrl ? (
            <a
              href={stripeCheckoutUrl}
              target="_blank"
              rel="noreferrer"
              aria-label={copy.ctaOpenCheckout}
              className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium text-white shadow-sm transition ${
                loading
                  ? "cursor-not-allowed bg-slate-400"
                  : "bg-slate-950 hover:bg-[#203a61]"
              }`}
            >
              {loading ? <Spinner /> : null}
              {copy.ctaOpenCheckout}
            </a>
          ) : (
            <button
              type="button"
              aria-label={copy.ctaOpenCheckout}
              disabled
              className="inline-flex cursor-not-allowed items-center rounded-xl bg-slate-300 px-4 py-2.5 text-sm font-medium text-slate-600"
            >
              {copy.ctaOpenCheckout}
            </button>
          )
        ) : null}

        {nextAction === "none" ? (
          <button
            type="button"
            aria-label={copy.ctaWaiting}
            disabled
            className="inline-flex cursor-not-allowed items-center gap-2 rounded-xl border border-[#c8d4ea] bg-white px-4 py-2.5 text-sm font-medium text-slate-600"
          >
            {loading ? <Spinner /> : null}
            {copy.ctaWaiting}
          </button>
        ) : null}
      </div>

      {nextAction === "open_checkout" && stripeCheckoutUrl ? (
        <p className="mt-2 text-xs text-slate-500">{copy.openingInNewTab}</p>
      ) : null}

      <details className="mt-4 rounded-xl border border-[#d8e1f0] bg-white p-3">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.12em] text-slate-600">
          {copy.debugTitle}
        </summary>
        <div className="mt-2 space-y-1 text-xs text-slate-600">
          <p>
            {copy.paymentId}: <span className="font-mono">{fiatPaymentId}</span>
          </p>
          <p>
            {copy.sessionId}: <span className="font-mono">{stripeSessionId || "-"}</span>
          </p>
          <p>
            {copy.paymentIntentId}:{" "}
            <span className="font-mono">{paymentIntentId || "-"}</span>
          </p>
        </div>
      </details>
    </section>
  );
}
