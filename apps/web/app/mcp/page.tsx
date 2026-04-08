"use client";

import Link from "next/link";
import { useState } from "react";

import { useI18n } from "../../lib/i18n-provider";

const ENDPOINT = "http://127.0.0.1:8000/mcp/";

type ToolGroup = {
  title: string;
  tools: string[];
};

type ToolDescriptor = {
  name: string;
  summary: string;
};

type ResponseExample = {
  key: string;
  label: string;
  tool: string;
  title: string;
  body: string;
  snippet: string;
};

function CodeBlock({ children }: { children: string }) {
  const { t } = useI18n();
  return (
    <div className="overflow-hidden rounded-[24px] border border-[#203456]/12 bg-[#081221] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
      <div className="flex items-center justify-between border-b border-white/6 px-5 py-2.5">
        <span className="text-[10px] uppercase tracking-[0.22em] text-slate-500">{t("mcp.codeBlockLabel")}</span>
        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-400">
          json
        </span>
      </div>
      <pre className="overflow-x-auto px-5 py-4 text-sm leading-6 text-slate-200">
        <code>{children}</code>
      </pre>
    </div>
  );
}

function SnippetCard({
  title,
  body,
  snippet,
  actionLabel,
  copiedLabel,
  copied,
  onCopy,
}: {
  title: string;
  body: string;
  snippet: string;
  actionLabel: string;
  copiedLabel: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="surface-transition rounded-[24px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-950">{title}</p>
          <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">{body}</p>
        </div>
        <button
          type="button"
          onClick={onCopy}
          className="rounded-full border border-[#c7d7ee] bg-white px-3 py-1.5 text-xs font-medium text-[#163358] transition hover:bg-[#edf3ff]"
        >
          {copied ? copiedLabel : actionLabel}
        </button>
      </div>
      <div className="mt-4">
        <CodeBlock>{snippet}</CodeBlock>
      </div>
    </div>
  );
}

export default function McpPage() {
  const { t } = useI18n();
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [activeResponseKey, setActiveResponseKey] = useState("capability_ok");
  const [activeToolFilter, setActiveToolFilter] = useState("all");

  const groups: ToolGroup[] = [
    {
      title: t("mcp.toolGroupAccess"),
      tools: ["mcp_capability_status", "start_user_kyc", "get_kyc_status"],
    },
    {
      title: t("mcp.toolGroupBalance"),
      tools: ["get_balance", "get_balance_ledger"],
    },
    {
      title: t("mcp.toolGroupDeposit"),
      tools: [
        "create_balance_deposit",
        "start_balance_deposit_checkout",
        "sync_balance_deposit_status",
        "get_balance_deposit_detail",
      ],
    },
    {
      title: t("mcp.toolGroupSettlement"),
      tools: ["payment_preview_from_balance", "payment_confirm_from_balance"],
    },
  ];
  const groupDelayClasses = ["motion-delay-100", "motion-delay-200", "motion-delay-300", "motion-delay-300"];
  const toolDescriptors: ToolDescriptor[] = [
    { name: "mcp_capability_status", summary: t("mcp.toolCapabilitySummary") },
    { name: "start_user_kyc", summary: t("mcp.toolKycSummary") },
    { name: "get_balance", summary: t("mcp.toolBalanceSummary") },
    { name: "create_balance_deposit", summary: t("mcp.toolDepositSummary") },
    { name: "sync_balance_deposit_status", summary: t("mcp.toolSyncSummary") },
    { name: "payment_preview_from_balance", summary: t("mcp.toolPreviewSummary") },
    { name: "payment_confirm_from_balance", summary: t("mcp.toolConfirmSummary") },
  ];

  const exampleOne = `{
  "tool": "mcp_capability_status",
  "arguments": {
    "user_id": "deaa3ed3-c910-53d0-8796-755d9c82add6"
  }
}`;

  const exampleTwo = `{
  "tool": "create_balance_deposit",
  "arguments": {
    "user_id": "deaa3ed3-c910-53d0-8796-755d9c82add6",
    "source_currency": "HKD",
    "source_amount": 1000,
    "target_currency": "USDT",
    "reference": "MCP-DEP-001"
  }
}`;

  const exampleThree = `{
  "tool": "payment_preview_from_balance",
  "arguments": {
    "user_id": "deaa3ed3-c910-53d0-8796-755d9c82add6",
    "prompt": "从平台余额给 Alice 支付 150 USDT，今晚到账",
    "execution_mode": "operator"
  }
}`;

  const exampleFour = `{
  "status": "validation_error",
  "message": "invalid user_id",
  "next_action": "none",
  "summary": {
    "user_id": "not-a-uuid"
  },
  "technical_details": {
    "http_status": 400,
    "detail": {
      "user_id": "must be a valid UUID"
    }
  }
}`;

  const exampleCapabilityOk = `{
  "status": "ok",
  "message": "MCP settlement tools are enabled for this user.",
  "next_action": "none",
  "summary": {
    "user_id": "deaa3ed3-c910-53d0-8796-755d9c82add6",
    "kyc_status": "verified",
    "mcp_access": "enabled"
  },
  "technical_details": {
    "available_tools": [
      "get_balance",
      "get_balance_ledger",
      "create_balance_deposit",
      "start_balance_deposit_checkout",
      "sync_balance_deposit_status",
      "get_balance_deposit_detail",
      "payment_preview_from_balance",
      "payment_confirm_from_balance"
    ]
  }
}`;

  const exampleBlockedKyc = `{
  "status": "blocked_kyc_required",
  "message": "Complete identity verification before using PayFi Box MCP payment tools.",
  "next_action": "start_kyc",
  "summary": {
    "user_id": "75b5c428-5d54-5bf7-838c-65cdee34f68b",
    "kyc_status": "required"
  },
  "technical_details": {
    "subject_type": "user",
    "subject_id": "75b5c428-5d54-5bf7-838c-65cdee34f68b"
  }
}`;

  const exampleDepositCredited = `{
  "status": "ok",
  "message": "Deposit status synchronized.",
  "next_action": "use_balance",
  "summary": {
    "deposit_order_id": "56171e04-454a-4bd2-89fc-ca23c30a7236",
    "status": "credited",
    "channel_status": "payment_confirmed",
    "target_currency": "USDT",
    "target_amount": 38.49312,
    "available_balance": 115.6064,
    "locked_balance": 0
  }
}`;

  const clientConfig = `{
  "name": "payfi-box",
  "transport": {
    "type": "streamable_http",
    "url": "${ENDPOINT}"
  }
}`;

  const claudeDesktopConfig = `{
  "mcpServers": {
    "payfi-box": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "${ENDPOINT}"
      ]
    }
  }
}`;

  const cursorConfig = `{
  "mcpServers": {
    "payfi-box": {
      "url": "${ENDPOINT}",
      "transport": "streamable_http"
    }
  }
}`;

  const callSequence = `1. mcp_capability_status
2. start_user_kyc
3. create_balance_deposit
4. start_balance_deposit_checkout
5. sync_balance_deposit_status
6. get_balance
7. payment_preview_from_balance
8. payment_confirm_from_balance`;

  const responseExamples: ResponseExample[] = [
    {
      key: "capability_ok",
      label: t("mcp.responseTabCapability"),
      tool: "mcp_capability_status",
      title: t("mcp.responseCapabilityTitle"),
      body: t("mcp.responseCapabilityBody"),
      snippet: exampleCapabilityOk,
    },
    {
      key: "kyc_blocked",
      label: t("mcp.responseTabBlocked"),
      tool: "start_user_kyc",
      title: t("mcp.responseBlockedTitle"),
      body: t("mcp.responseBlockedBody"),
      snippet: exampleBlockedKyc,
    },
    {
      key: "deposit_credited",
      label: t("mcp.responseTabDeposit"),
      tool: "sync_balance_deposit_status",
      title: t("mcp.responseDepositTitle"),
      body: t("mcp.responseDepositBody"),
      snippet: exampleDepositCredited,
    },
    {
      key: "validation_error",
      label: t("mcp.responseTabValidation"),
      tool: "payment_preview_from_balance",
      title: t("mcp.responseValidationTitle"),
      body: t("mcp.responseValidationBody"),
      snippet: exampleFour,
    },
  ];
  const toolFilterOptions = [
    { key: "all", label: t("mcp.filterAll") },
    { key: "mcp_capability_status", label: "mcp_capability_status" },
    { key: "start_user_kyc", label: "start_user_kyc" },
    { key: "sync_balance_deposit_status", label: "sync_balance_deposit_status" },
    { key: "payment_preview_from_balance", label: "payment_preview_from_balance" },
  ];
  const filteredResponseExamples =
    activeToolFilter === "all"
      ? responseExamples
      : responseExamples.filter((item) => item.tool === activeToolFilter);
  const activeResponse =
    filteredResponseExamples.find((item) => item.key === activeResponseKey) ??
    filteredResponseExamples[0] ??
    responseExamples[0];
  const accessFacts = [
    { label: t("mcp.readinessEndpoint"), value: ENDPOINT, mono: true },
    { label: t("mcp.accessTransportLabel"), value: "streamable_http" },
    { label: t("mcp.readinessGate"), value: t("mcp.readinessGateValue") },
    { label: t("mcp.readinessFirstTool"), value: "mcp_capability_status", mono: true },
    { label: t("mcp.accessContractLabel"), value: "status / message / next_action", mono: true },
    { label: t("mcp.readinessPath"), value: t("mcp.readinessPathValue") },
  ];
  const requestExamples = [
    {
      key: "capability",
      title: t("mcp.requestCapabilityTitle"),
      body: t("mcp.requestCapabilityBody"),
      snippet: exampleOne,
    },
    {
      key: "deposit",
      title: t("mcp.requestDepositTitle"),
      body: t("mcp.requestDepositBody"),
      snippet: exampleTwo,
    },
    {
      key: "preview",
      title: t("mcp.requestPreviewTitle"),
      body: t("mcp.requestPreviewBody"),
      snippet: exampleThree,
    },
  ];
  const sectionLinks = [
    { href: "#mcp-quick-start", label: t("mcp.navQuickStart") },
    { href: "#mcp-access-model", label: t("mcp.navAccessModel") },
    { href: "#mcp-tools", label: t("mcp.navTools") },
    { href: "#mcp-requests", label: t("mcp.navRequests") },
    { href: "#mcp-responses", label: t("mcp.navResponses") },
    { href: "#mcp-client-setup", label: t("mcp.navClientSetup") },
  ];

  function handleCopy(key: string, value: string) {
    void navigator.clipboard.writeText(value).then(() => {
      setCopiedKey(key);
      window.setTimeout(() => {
        setCopiedKey((current) => (current === key ? null : current));
      }, 1600);
    });
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#eff6ff,white_46%)] pb-20 text-slate-950">
      <section className="mx-auto max-w-7xl px-4 pb-8 pt-8 lg:px-8">
        <div className="motion-fade-up rounded-[34px] border border-[#d7e4f4] bg-[linear-gradient(180deg,#0c1931_0%,#173156_58%,#6e8eaf_100%)] px-8 py-10 text-white shadow-[0_30px_80px_rgba(8,18,33,0.16)] lg:px-10 lg:py-12">
          <div className="grid gap-8 lg:grid-cols-[1.35fr_0.85fr] lg:items-end">
            <div className="space-y-5">
              <p className="text-[11px] uppercase tracking-[0.32em] text-slate-300">{t("mcp.badge")}</p>
              <h1 className="max-w-3xl text-5xl font-light tracking-[-0.05em] text-white lg:text-6xl">{t("mcp.title")}</h1>
              <p className="max-w-3xl text-base leading-7 text-slate-200 lg:text-lg">{t("mcp.intro")}</p>
              <div className="flex flex-wrap gap-3">
                <Link
                  href="/balance"
                  className="inline-flex items-center rounded-full bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:-translate-y-0.5 hover:bg-slate-100"
                >
                  {t("mcp.ctaPrimary")}
                </Link>
                <Link
                  href="/command-center"
                  className="inline-flex items-center rounded-full border border-white/20 px-5 py-3 text-sm font-semibold text-white transition hover:-translate-y-0.5 hover:bg-white/10"
                >
                  {t("mcp.ctaSecondary")}
                </Link>
              </div>
            </div>

            <div className="motion-scale-in rounded-[28px] border border-white/12 bg-white/[0.08] p-6 backdrop-blur-sm">
              <p className="text-xs uppercase tracking-[0.26em] text-slate-300">{t("mcp.endpointLabel")}</p>
              <p className="mt-3 break-all rounded-2xl border border-white/10 bg-[#081221]/45 px-4 py-3 font-mono text-sm text-white">
                {ENDPOINT}
              </p>
              <p className="mt-4 text-sm leading-6 text-slate-200">{t("mcp.endpointHint")}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 pt-2 lg:px-8">
        <div className="motion-fade-up motion-delay-100 rounded-[24px] border border-[#d8e3f2] bg-white/90 px-4 py-4 shadow-sm backdrop-blur-sm">
          <div className="flex flex-wrap gap-2">
            {sectionLinks.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-full border border-[#c7d7ee] bg-[#f8fbff] px-3 py-1.5 text-xs font-medium text-[#163358] transition hover:bg-[#edf3ff]"
              >
                {item.label}
              </a>
            ))}
          </div>
        </div>
      </section>

      <section id="mcp-quick-start" className="mx-auto grid max-w-7xl gap-6 px-4 pt-6 lg:grid-cols-[1.02fr_0.98fr] lg:px-8">
        <div className="motion-fade-up motion-delay-100 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm scroll-mt-24">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.quickStartLabel")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.quickStartTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.readinessBody")}</p>
          <div className="mt-6 space-y-4">
            {[
              [t("mcp.flowOneTitle"), t("mcp.flowOneBody")],
              [t("mcp.flowTwoTitle"), t("mcp.flowTwoBody")],
              [t("mcp.flowThreeTitle"), t("mcp.flowThreeBody")],
            ].map(([title, body], index) => (
              <div key={title} className="rounded-[24px] border border-[#d8e3f2] bg-[#f8fbff] px-5 py-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Step {index + 1}</p>
                <h3 className="mt-2 text-lg font-semibold text-slate-950">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
              </div>
            ))}
          </div>
        </div>

        <div id="mcp-access-model" className="motion-fade-up motion-delay-200 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm scroll-mt-24">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.accessModelLabel")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.accessModelTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.accessModelBody")}</p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {accessFacts.map((fact) => (
              <div key={fact.label} className="rounded-[22px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] px-4 py-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{fact.label}</p>
                <p className={`mt-3 text-sm font-semibold text-slate-900 ${fact.mono ? "break-all font-mono text-[13px]" : ""}`}>
                  {fact.value}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-4 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
        <div className="motion-fade-up motion-delay-100 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.requirementTitle")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.requirementTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.requirementBody")}</p>
          <div className="mt-6 grid gap-3">
            {[t("mcp.requirementA"), t("mcp.requirementB"), t("mcp.requirementC")].map((item) => (
              <div
                key={item}
                className="surface-transition rounded-[22px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-3 text-sm font-medium text-slate-700"
              >
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="motion-fade-up motion-delay-200 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.demoPathTitle")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.demoPathTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.examplesBody")}</p>
          <div className="mt-6 grid gap-3">
            {[t("mcp.demoPathA"), t("mcp.demoPathB"), t("mcp.demoPathC"), t("mcp.demoPathD"), t("mcp.demoPathE"), t("mcp.demoPathF")].map(
              (item) => (
                <div key={item} className="rounded-[22px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] px-4 py-4 text-sm leading-6 text-slate-700">
                  {item}
                </div>
              ),
            )}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-4 pt-6 lg:grid-cols-[1.04fr_0.96fr] lg:px-8">
        <div className="motion-fade-up motion-delay-200 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.clientConfigLabel")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.clientConfigTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.clientConfigBody")}</p>
          <div className="mt-6 space-y-4">
            <SnippetCard
              title={t("mcp.clientConfigCard")}
              body={t("mcp.clientConfigCardBody")}
              snippet={clientConfig}
              actionLabel={t("mcp.copyConfig")}
              copiedLabel={t("mcp.copiedConfig")}
              copied={copiedKey === "config"}
              onCopy={() => handleCopy("config", clientConfig)}
            />
            <SnippetCard
              title={t("mcp.clientSequenceCard")}
              body={t("mcp.clientSequenceCardBody")}
              snippet={callSequence}
              actionLabel={t("mcp.copyConfig")}
              copiedLabel={t("mcp.copiedConfig")}
              copied={copiedKey === "sequence"}
              onCopy={() => handleCopy("sequence", callSequence)}
            />
            <div className="grid gap-4 xl:grid-cols-2">
              <SnippetCard
                title={t("mcp.clientConfigClaude")}
                body={t("mcp.clientConfigClaudeBody")}
                snippet={claudeDesktopConfig}
                actionLabel={t("mcp.copyConfig")}
                copiedLabel={t("mcp.copiedConfig")}
                copied={copiedKey === "claude"}
                onCopy={() => handleCopy("claude", claudeDesktopConfig)}
              />
              <SnippetCard
                title={t("mcp.clientConfigCursor")}
                body={t("mcp.clientConfigCursorBody")}
                snippet={cursorConfig}
                actionLabel={t("mcp.copyConfig")}
                copiedLabel={t("mcp.copiedConfig")}
                copied={copiedKey === "cursor"}
                onCopy={() => handleCopy("cursor", cursorConfig)}
              />
            </div>
          </div>
        </div>

        <div className="motion-fade-up motion-delay-300 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.clientNotesLabel")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.clientNotesTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.clientNotesBody")}</p>
          <div className="mt-6 grid gap-3">
            {[t("mcp.clientNoteA"), t("mcp.clientNoteB"), t("mcp.clientNoteC"), t("mcp.clientNoteD")].map((item) => (
              <div key={item} className="rounded-[20px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-3 text-sm text-slate-700">
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="mcp-tools" className="mx-auto max-w-7xl px-4 pt-6 lg:px-8">
        <div className="motion-fade-up motion-delay-300 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm scroll-mt-24">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.toolMatrixLabel")}</p>
              <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.toolMatrixTitle")}</h2>
            </div>
            <p className="max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.toolMatrixBody")}</p>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {groups.map((group, index) => (
              <div
                key={group.title}
                className={`surface-transition motion-fade-up rounded-[26px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f2f7ff_100%)] p-6 shadow-sm ${groupDelayClasses[index]}`}
              >
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{group.title}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {group.tools.map((tool) => (
                    <span
                      key={tool}
                      className="rounded-full border border-[#c7d7ee] bg-white px-3 py-1.5 font-mono text-xs text-[#163358]"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-4 pt-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
        <div id="mcp-requests" className="motion-fade-up motion-delay-200 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm scroll-mt-24">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.examplesTitle")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.requestExamplesTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.requestExamplesBody")}</p>
          <div className="mt-6 space-y-3">
            {requestExamples.map((item) => (
              <SnippetCard
                key={item.key}
                title={item.title}
                body={item.body}
                snippet={item.snippet}
                actionLabel={t("mcp.copyConfig")}
                copiedLabel={t("mcp.copiedConfig")}
                copied={copiedKey === item.key}
                onCopy={() => handleCopy(item.key, item.snippet)}
              />
            ))}
          </div>
        </div>

        <div id="mcp-responses" className="motion-fade-up motion-delay-300 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm scroll-mt-24">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.responseExamplesLabel")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.responseExamplesTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.responseExamplesBody")}</p>
          <div className="mt-6 flex flex-wrap gap-2">
            {toolFilterOptions.map((option) => {
              const active = option.key === activeToolFilter;
              return (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => {
                    setActiveToolFilter(option.key);
                    const nextExample =
                      option.key === "all" ? responseExamples[0] : responseExamples.find((item) => item.tool === option.key);
                    if (nextExample) setActiveResponseKey(nextExample.key);
                  }}
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                    active
                      ? "border-[#163358] bg-[#163358] text-white"
                      : "border-[#c7d7ee] bg-white text-[#163358] hover:bg-[#edf3ff]"
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {filteredResponseExamples.map((item) => {
              const active = item.key === activeResponse.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveResponseKey(item.key)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                    active
                      ? "border-[#163358] bg-[#163358] text-white"
                      : "border-[#c7d7ee] bg-white text-[#163358] hover:bg-[#edf3ff]"
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
          <div className="mt-6">
            <div className="rounded-[20px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-4">
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm font-semibold text-slate-950">{activeResponse.title}</p>
                <code className="rounded-full border border-[#c7d7ee] bg-white px-3 py-1 text-xs text-[#163358]">
                  {activeResponse.tool}
                </code>
                <span
                  className={`rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${
                    activeResponse.key === "capability_ok"
                      ? "bg-emerald-50 text-emerald-700"
                      : activeResponse.key === "kyc_blocked"
                        ? "bg-amber-50 text-amber-700"
                        : activeResponse.key === "deposit_credited"
                          ? "bg-sky-50 text-sky-700"
                          : "bg-rose-50 text-rose-700"
                  }`}
                >
                  {activeResponse.key === "capability_ok"
                    ? "ok"
                    : activeResponse.key === "kyc_blocked"
                      ? "blocked_kyc_required"
                      : activeResponse.key === "deposit_credited"
                        ? "credited"
                        : "validation_error"}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-600">{activeResponse.body}</p>
            </div>
            <div className="mt-4 rounded-[20px] border border-[#d8e3f2] bg-[linear-gradient(180deg,#fbfdff_0%,#f5f8fe_100%)] p-4">
              <div className="mb-4 grid gap-3 sm:grid-cols-3">
                <div className="rounded-[16px] border border-[#d8e3f2] bg-white px-3 py-3">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-slate-400">{t("mcp.responseMetaTool")}</p>
                  <p className="mt-2 font-mono text-xs text-slate-900">{activeResponse.tool}</p>
                </div>
                <div className="rounded-[16px] border border-[#d8e3f2] bg-white px-3 py-3">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-slate-400">{t("mcp.responseMetaState")}</p>
                  <p className="mt-2 text-xs font-semibold text-slate-900">{activeResponse.label}</p>
                </div>
                <div className="rounded-[16px] border border-[#d8e3f2] bg-white px-3 py-3">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-slate-400">{t("mcp.responseMetaContract")}</p>
                  <p className="mt-2 text-xs font-semibold text-slate-900">status / message / next_action</p>
                </div>
              </div>
              <CodeBlock>{activeResponse.snippet}</CodeBlock>
            </div>
          </div>
          <div className="mt-6 grid gap-3">
            {[t("mcp.errorContractA"), t("mcp.errorContractB"), t("mcp.errorContractC")].map((item) => (
              <div key={item} className="rounded-[20px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-3 text-sm text-slate-700">
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="mcp-client-setup" className="mx-auto grid max-w-7xl gap-6 px-4 pt-6 lg:grid-cols-[0.9fr_1.1fr] lg:px-8">
        <div className="motion-fade-up motion-delay-200 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.errorContractLabel")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.errorContractTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.errorContractBody")}</p>
          <div className="mt-5 space-y-3 text-sm leading-7 text-slate-700">
            {[t("mcp.errorContractA"), t("mcp.errorContractB"), t("mcp.errorContractC")].map((item) => (
              <div key={item} className="rounded-[20px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-3">
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="motion-fade-up motion-delay-300 rounded-[30px] border border-[#c8d4ea] bg-white p-7 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{t("mcp.clientNotesLabel")}</p>
          <h2 className="mt-3 text-3xl font-light tracking-[-0.04em] text-slate-950">{t("mcp.clientNotesTitle")}</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">{t("mcp.clientNotesBody")}</p>
          <div className="mt-5 space-y-3 text-sm leading-7 text-slate-700">
            {[t("mcp.clientNoteA"), t("mcp.clientNoteB"), t("mcp.clientNoteC"), t("mcp.clientNoteD")].map(
              (item) => (
                <div key={item} className="rounded-[20px] border border-[#d8e3f2] bg-[#f8fbff] px-4 py-3">
                  {item}
                </div>
              ),
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
