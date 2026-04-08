"use client";

import { FormEvent, useState } from "react";
import { formatRecipientLabel, type RecipientRecord } from "../lib/recipient-book";
import { useI18n } from "../lib/i18n-provider";

type RecipientSelectorProps = {
  recipients: RecipientRecord[];
  selectedRecipientId: string;
  onSelectRecipient: (recipientId: string) => void;
  onCreateRecipient: (payload: {
    name: string;
    address: string;
    network: string;
    note?: string;
  }) => void;
  className?: string;
  labelKey?: string;
};

export function RecipientSelector({
  recipients,
  selectedRecipientId,
  onSelectRecipient,
  onCreateRecipient,
  className = "",
  labelKey = "recipient.label",
}: RecipientSelectorProps) {
  const { t } = useI18n();
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [network, setNetwork] = useState("hashkey_testnet");
  const [note, setNote] = useState("");

  function resetModal() {
    setName("");
    setAddress("");
    setNetwork("hashkey_testnet");
    setNote("");
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !address.trim() || !network.trim()) return;
    onCreateRecipient({
      name: name.trim(),
      address: address.trim(),
      network: network.trim(),
      note: note.trim() || undefined,
    });
    resetModal();
    setShowModal(false);
  }

  return (
    <>
      <div className={className}>
        <label className="space-y-1">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{t(labelKey)}</span>
          <select
            value={selectedRecipientId}
            onChange={(event) => onSelectRecipient(event.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none ring-teal-500 focus:ring-2"
          >
            {recipients.map((recipient) => (
              <option key={recipient.id} value={recipient.id}>
                {formatRecipientLabel(recipient)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="mt-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
        >
          + {t("recipient.add")}
        </button>
      </div>

      {showModal ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-lg font-semibold text-slate-900">{t("recipient.modalTitle")}</h3>
              <button
                type="button"
                onClick={() => {
                  resetModal();
                  setShowModal(false);
                }}
                className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
              >
                {t("recipient.cancel")}
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3">
              <label className="space-y-1">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">{t("recipient.name")}</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none ring-teal-500 focus:ring-2"
                  placeholder={t("recipient.namePlaceholder")}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">{t("recipient.address")}</span>
                <input
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm outline-none ring-teal-500 focus:ring-2"
                  placeholder="0xabc...1234"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">{t("recipient.network")}</span>
                <input
                  value={network}
                  onChange={(event) => setNetwork(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none ring-teal-500 focus:ring-2"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase tracking-[0.1em] text-slate-500">{t("recipient.note")}</span>
                <textarea
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  rows={3}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none ring-teal-500 focus:ring-2"
                  placeholder={t("recipient.notePlaceholder")}
                />
              </label>
              <div className="flex items-center gap-2">
                <button
                  type="submit"
                  disabled={!name.trim() || !address.trim() || !network.trim()}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                >
                  {t("recipient.save")}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    resetModal();
                    setShowModal(false);
                  }}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                >
                  {t("recipient.cancel")}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
