"use client";

export const PAYFI_RECIPIENTS_STORAGE_KEY = "payfi_recipients";

export type RecipientRecord = {
  id: string;
  name: string;
  address: string;
  network: string;
  note?: string;
  beneficiaryId?: string | null;
  source: "backend" | "custom";
};

type RecipientPersisted = Omit<RecipientRecord, "source"> & {
  source?: "backend" | "custom";
};

export function shortenAddress(address: string): string {
  if (!address) return "-";
  if (address.length < 14) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function formatRecipientLabel(recipient: RecipientRecord): string {
  return `${recipient.name} (${shortenAddress(recipient.address)})`;
}

export function loadCustomRecipients(): RecipientRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(PAYFI_RECIPIENTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as RecipientPersisted[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item.id === "string")
      .map((item) => ({
        id: item.id,
        name: item.name || "Unnamed Recipient",
        address: item.address || "-",
        network: item.network || "hashkey_testnet",
        note: item.note || "",
        beneficiaryId: item.beneficiaryId || null,
        source: "custom",
      }));
  } catch {
    return [];
  }
}

export function saveCustomRecipients(recipients: RecipientRecord[]): void {
  if (typeof window === "undefined") return;
  try {
    const payload = recipients
      .filter((recipient) => recipient.source === "custom")
      .map((recipient) => ({
        id: recipient.id,
        name: recipient.name,
        address: recipient.address,
        network: recipient.network,
        note: recipient.note || "",
        beneficiaryId: recipient.beneficiaryId || null,
        source: "custom" as const,
      }));
    window.localStorage.setItem(PAYFI_RECIPIENTS_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // ignore localStorage write failures
  }
}

export function createCustomRecipient(input: {
  name: string;
  address: string;
  network: string;
  note?: string;
}): RecipientRecord {
  return {
    id: `custom-${crypto.randomUUID()}`,
    name: input.name.trim(),
    address: input.address.trim(),
    network: input.network.trim(),
    note: input.note?.trim() || "",
    beneficiaryId: null,
    source: "custom",
  };
}
