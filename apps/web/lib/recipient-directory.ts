"use client";

import {
  getBeneficiaries,
  getBeneficiaryDetail,
  type BeneficiaryListResponse,
} from "./api";
import { loadCustomRecipients, type RecipientRecord } from "./recipient-book";

let backendRecipientCache: RecipientRecord[] | null = null;
let backendRecipientPromise: Promise<RecipientRecord[]> | null = null;
let cachedLimit = 0;

async function fetchBackendRecipients(
  beneficiaries: BeneficiaryListResponse["items"],
): Promise<RecipientRecord[]> {
  const loaded: Array<RecipientRecord | null> = await Promise.all(
    beneficiaries.map(async (beneficiary) => {
      if (beneficiary.is_blacklisted) return null;
      try {
        const detail = await getBeneficiaryDetail(beneficiary.beneficiary_id);
        const walletAddress = detail.beneficiary.wallet_address?.trim();
        if (!walletAddress) return null;
        return {
          id: `backend-${beneficiary.beneficiary_id}`,
          beneficiaryId: beneficiary.beneficiary_id,
          name: beneficiary.name,
          address: walletAddress,
          network: "hashkey_testnet",
          note: beneficiary.country,
          source: "backend" as const,
        };
      } catch {
        return null;
      }
    }),
  );
  return loaded.filter((item): item is RecipientRecord => Boolean(item));
}

async function loadBackendRecipients(limit: number): Promise<RecipientRecord[]> {
  const beneficiaryList = await getBeneficiaries({ limit, is_blacklisted: false });
  return fetchBackendRecipients(beneficiaryList.items);
}

export async function loadRecipientDirectory(limit = 30): Promise<RecipientRecord[]> {
  const normalizedLimit = Math.max(1, limit);
  const customRecipients = loadCustomRecipients();

  try {
    if (!backendRecipientCache || normalizedLimit > cachedLimit) {
      if (!backendRecipientPromise || normalizedLimit > cachedLimit) {
        backendRecipientPromise = loadBackendRecipients(normalizedLimit)
          .then((recipients) => {
            backendRecipientCache = recipients;
            cachedLimit = normalizedLimit;
            return recipients;
          })
          .finally(() => {
            backendRecipientPromise = null;
          });
      }
      await backendRecipientPromise;
    }
  } catch {
    return customRecipients;
  }

  return [...(backendRecipientCache ?? []), ...customRecipients];
}

export function resetRecipientDirectoryCache(): void {
  backendRecipientCache = null;
  backendRecipientPromise = null;
  cachedLimit = 0;
}
