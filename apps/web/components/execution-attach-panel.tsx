"use client";

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../lib/i18n-provider";
import { StatusBadge } from "./status-badge";

type ExecutionMode = "operator" | "user_wallet" | "safe";

type ExecutionItemLite = {
  execution_item_id?: string;
  id?: string;
  sequence: number;
  status: string;
  tx_hash?: string | null;
  onchain_status?: string | null;
  pending_action?: string | null;
  unsigned_tx_request?: Record<string, unknown> | null;
  safe_proposal_request?: Record<string, unknown> | null;
};

type ExecutionAttachPanelProps = {
  mode: ExecutionMode;
  items: ExecutionItemLite[];
  loading: boolean;
  onOperatorSubmit?: () => Promise<void> | void;
  onAttachTx: (input: {
    executionItemId: string;
    txHash: string;
    walletAddress?: string;
  }) => Promise<void> | void;
  onAttachSafeProposal: (input: {
    executionItemId: string;
    safeAddress?: string;
    proposalId?: string;
    proposalUrl?: string;
    proposerWallet?: string;
  }) => Promise<void> | void;
  onSyncReceipt: (executionItemId: string) => Promise<void> | void;
};

export function ExecutionAttachPanel({
  mode,
  items,
  loading,
  onOperatorSubmit,
  onAttachTx,
  onAttachSafeProposal,
  onSyncReceipt,
}: ExecutionAttachPanelProps) {
  const { t } = useI18n();
  const [selectedItemId, setSelectedItemId] = useState("");
  const [txHash, setTxHash] = useState("");
  const [walletAddress, setWalletAddress] = useState("");
  const [safeAddress, setSafeAddress] = useState("");
  const [proposalId, setProposalId] = useState("");
  const [proposalUrl, setProposalUrl] = useState("");
  const [proposerWallet, setProposerWallet] = useState("");

  const normalizedItems = useMemo(
    () =>
      items.map((item) => ({
        ...item,
        execution_item_id: item.execution_item_id || item.id || "",
      })),
    [items],
  );

  useEffect(() => {
    if (!normalizedItems.length) {
      setSelectedItemId("");
      return;
    }
    setSelectedItemId((current) =>
      current && normalizedItems.some((item) => item.execution_item_id === current)
        ? current
        : normalizedItems[0].execution_item_id,
    );
  }, [normalizedItems]);

  const selectedItem = useMemo(
    () => normalizedItems.find((item) => item.execution_item_id === selectedItemId) || null,
    [normalizedItems, selectedItemId],
  );
  const canSyncReceipt = Boolean(selectedItem?.tx_hash || txHash.trim());
  const modePayload =
    mode === "safe" ? selectedItem?.safe_proposal_request : selectedItem?.unsigned_tx_request;
  const modePayloadTitle = mode === "safe" ? t("command.safePayload") : t("command.userWalletPayload");
  const copyPayloadLabel = mode === "safe" ? t("command.copySafeProposal") : t("command.copyUnsigned");

  async function handleCopyPayload() {
    if (!modePayload) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(modePayload, null, 2));
    } catch {
      // ignore clipboard failures
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-700">
        {t("command.attachPanelTitle")}
      </h3>
      <p className="mt-2 text-sm text-slate-600">{t("command.attachPanelHint")}</p>

      {mode === "operator" ? (
        <div className="mt-3 rounded-xl border border-teal-200 bg-teal-50 p-3">
          <p className="text-sm text-teal-800">{t("command.operatorAttachHint")}</p>
          <button
            type="button"
            disabled={loading || !onOperatorSubmit}
          onClick={() => {
              if (onOperatorSubmit) void onOperatorSubmit();
            }}
            className="mt-2 rounded-lg bg-teal-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-600 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {t("command.ctaOperator")}
          </button>
        </div>
      ) : null}

      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
          {t("command.attachStepSelect")}
        </p>
        <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
          <label className="space-y-1">
            <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
              {t("command.attachExecutionItem")}
            </span>
            <select
              value={selectedItemId}
              onChange={(event) => setSelectedItemId(event.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none ring-teal-500 focus:ring-2"
            >
              {normalizedItems.map((item) => (
                <option key={item.execution_item_id} value={item.execution_item_id}>
                  item #{item.sequence} · {item.execution_item_id}
                </option>
              ))}
            </select>
          </label>
          {selectedItem ? (
            <div className="flex items-center gap-2">
              <StatusBadge status={selectedItem.status} />
              <StatusBadge status={selectedItem.onchain_status || "unknown"} />
            </div>
          ) : null}
        </div>
      </div>

      {mode !== "operator" ? (
        <details className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
            {modePayloadTitle}
          </summary>
          <div className="mt-2 space-y-2">
            {modePayload ? (
              <>
                <button
                  type="button"
                  onClick={() => void handleCopyPayload()}
                  className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                >
                  {copyPayloadLabel}
                </button>
                <pre className="max-h-52 overflow-auto rounded-lg border border-slate-200 bg-white p-2 text-[11px] leading-5 text-slate-700">
                  {JSON.stringify(modePayload, null, 2)}
                </pre>
              </>
            ) : (
              <p className="text-xs text-slate-500">{t("common.noData")}</p>
            )}
            {selectedItem?.pending_action ? (
              <p className="text-xs text-slate-600">
                {t("common.pendingAction")}:{" "}
                <span className="font-semibold">{selectedItem.pending_action}</span>
              </p>
            ) : null}
          </div>
        </details>
      ) : null}

      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
          {mode === "safe"
            ? t("command.attachStepBindSafeTx")
            : t("command.attachStepBindWalletTx")}
        </p>
        <p className="mt-1 text-xs text-slate-500">{t("command.attachStepBindHint")}</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <label className="space-y-1 sm:col-span-2">
            <span className="text-xs uppercase tracking-[0.1em] text-slate-500">tx_hash</span>
            <input
              value={txHash}
              onChange={(event) => setTxHash(event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm outline-none ring-teal-500 focus:ring-2"
              placeholder="0x..."
            />
          </label>
          <label className="space-y-1 sm:col-span-2">
            <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
              {t("command.attachWalletAddress")}
            </span>
            <input
              value={walletAddress}
              onChange={(event) => setWalletAddress(event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm outline-none ring-teal-500 focus:ring-2"
              placeholder="0x..."
            />
          </label>
        </div>
        <button
          type="button"
          disabled={loading || !selectedItemId || !txHash.trim()}
          onClick={() =>
            onAttachTx({
              executionItemId: selectedItemId,
              txHash: txHash.trim(),
              walletAddress: walletAddress.trim() || undefined,
            })
          }
          className="mt-2 rounded-lg bg-teal-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-600 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {t("command.attachTx")}
        </button>
      </div>

      {mode === "safe" ? (
        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
            {t("command.attachStepSafeProposal")}
          </p>
          <p className="mt-1 text-xs text-slate-500">{t("command.attachStepSafeHint")}</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                {t("command.attachSafeAddress")}
              </span>
              <input
                value={safeAddress}
                onChange={(event) => setSafeAddress(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm outline-none ring-teal-500 focus:ring-2"
                placeholder="0x..."
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                {t("command.attachProposalId")}
              </span>
              <input
                value={proposalId}
                onChange={(event) => setProposalId(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none ring-teal-500 focus:ring-2"
                placeholder="proposal-id"
              />
            </label>
            <label className="space-y-1 sm:col-span-2">
              <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                {t("command.attachProposalUrl")}
              </span>
              <input
                value={proposalUrl}
                onChange={(event) => setProposalUrl(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none ring-teal-500 focus:ring-2"
                placeholder="https://..."
              />
            </label>
            <label className="space-y-1 sm:col-span-2">
              <span className="text-xs uppercase tracking-[0.1em] text-slate-500">
                {t("command.attachProposerWallet")}
              </span>
              <input
                value={proposerWallet}
                onChange={(event) => setProposerWallet(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm outline-none ring-teal-500 focus:ring-2"
                placeholder="0x..."
              />
            </label>
          </div>
          <button
            type="button"
            disabled={loading || !selectedItemId}
            onClick={() =>
              onAttachSafeProposal({
                executionItemId: selectedItemId,
                safeAddress: safeAddress.trim() || undefined,
                proposalId: proposalId.trim() || undefined,
                proposalUrl: proposalUrl.trim() || undefined,
                proposerWallet: proposerWallet.trim() || undefined,
              })
            }
            className="mt-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            {t("command.attachProposal")}
          </button>
        </div>
      ) : null}

      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">
          {t("command.attachStepSync")}
        </p>
        <p className="mt-1 text-xs text-slate-500">{t("command.attachStepSyncHint")}</p>
        <button
          type="button"
          disabled={loading || !selectedItemId || !canSyncReceipt}
          onClick={() => onSyncReceipt(selectedItemId)}
          className="mt-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-400"
        >
          {t("command.syncReceipt")}
        </button>
      </div>

      {selectedItem?.tx_hash ? (
        <p className="mt-2 text-xs text-slate-500">
          tx_hash: <span className="font-mono">{selectedItem.tx_hash}</span>
        </p>
      ) : null}
    </section>
  );
}
