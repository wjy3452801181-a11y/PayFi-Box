"use client";

import type {
  CreateFiatPaymentResponse,
  KycStartResponse,
  MarkFiatReceivedResponse,
  MerchantFiatPaymentDetailResponse,
  SettlementQuoteResponse,
  StripeSessionResponse,
} from "../../lib/api";
import { useI18n } from "../../lib/i18n-provider";
import { JsonView } from "../json-view";

type TechnicalDetailsAccordionProps = {
  quoteResult: SettlementQuoteResponse | null;
  fiatIntentResult: CreateFiatPaymentResponse | null;
  kycResult: KycStartResponse | null;
  stripeSessionResult: StripeSessionResponse | null;
  markReceivedResult: MarkFiatReceivedResponse | null;
  detailResult: MerchantFiatPaymentDetailResponse | null;
  paymentOrderId?: string | null;
  executionBatchId?: string | null;
  txHash?: string | null;
};

export function TechnicalDetailsAccordion({
  quoteResult,
  fiatIntentResult,
  kycResult,
  stripeSessionResult,
  markReceivedResult,
  detailResult,
  paymentOrderId,
  executionBatchId,
  txHash,
}: TechnicalDetailsAccordionProps) {
  const { t } = useI18n();
  return (
    <details className="rounded-[20px] border border-[#d8e1f0] bg-white p-4 shadow-sm">
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.14em] text-slate-600">
        {t("merchant.debugSection")}
      </summary>
      <div className="mt-3 space-y-3">
        <div className="rounded-xl border border-[#d8e1f0] bg-[#f7f9fd] p-3 text-xs text-slate-600">
          <p>payment_order_id: <span className="font-mono">{paymentOrderId || "-"}</span></p>
          <p>execution_batch_id: <span className="font-mono">{executionBatchId || "-"}</span></p>
          <p>tx_hash: <span className="font-mono">{txHash || "-"}</span></p>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <JsonView title="quote_response" data={quoteResult} />
          <JsonView title="fiat_intent_response" data={fiatIntentResult} />
          <JsonView title="kyc_response" data={kycResult} />
          <JsonView title="stripe_session_response" data={stripeSessionResult} />
          <JsonView title="mark_received_response" data={markReceivedResult} />
          <JsonView title="detail_response" data={detailResult} />
        </div>
      </div>
    </details>
  );
}
