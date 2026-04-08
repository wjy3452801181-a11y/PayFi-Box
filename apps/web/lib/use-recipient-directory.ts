"use client";

import { useEffect, useMemo, useState } from "react";

import { loadRecipientDirectory } from "./recipient-directory";
import {
  createCustomRecipient,
  saveCustomRecipients,
  type RecipientRecord,
} from "./recipient-book";

export function useRecipientDirectory(limit = 30) {
  const [recipients, setRecipients] = useState<RecipientRecord[]>([]);
  const [selectedRecipientId, setSelectedRecipientId] = useState("");

  useEffect(() => {
    let active = true;
    async function loadRecipients() {
      try {
        const merged = await loadRecipientDirectory(limit);
        if (!active) return;
        setRecipients(merged);
        setSelectedRecipientId((current) => current || merged[0]?.id || "");
      } catch {
        if (!active) return;
        setRecipients([]);
        setSelectedRecipientId("");
      }
    }
    void loadRecipients();
    return () => {
      active = false;
    };
  }, [limit]);

  const selectedRecipient = useMemo(
    () => recipients.find((recipient) => recipient.id === selectedRecipientId) || null,
    [recipients, selectedRecipientId],
  );

  function addRecipient(payload: {
    name: string;
    address: string;
    network: string;
    note?: string;
  }) {
    const recipient = createCustomRecipient(payload);
    setRecipients((current) => {
      const next = [...current, recipient];
      saveCustomRecipients(next);
      return next;
    });
    setSelectedRecipientId(recipient.id);
  }

  return {
    recipients,
    selectedRecipientId,
    setSelectedRecipientId,
    selectedRecipient,
    addRecipient,
  };
}
