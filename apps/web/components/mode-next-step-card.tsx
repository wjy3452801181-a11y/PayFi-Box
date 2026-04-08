"use client";

import type { ConfirmResponse } from "../lib/api";
import { useI18n } from "../lib/i18n-provider";

type ExecutionMode = "operator" | "user_wallet" | "safe";

type ModeNextStepCardProps = {
  mode: ExecutionMode;
  previewReady: boolean;
  confirmResult: ConfirmResponse | null;
  onCopyUnsigned: () => void;
  onAttachTx: () => void;
  onCopySafeProposal: () => void;
  onAttachSafe: () => void;
};

function getTitle(t: (key: string) => string, mode: ExecutionMode): string {
  if (mode === "operator") return t("command.nextOperatorTitle");
  if (mode === "user_wallet") return t("command.nextUserWalletTitle");
  return t("command.nextSafeTitle");
}

function getMessage(t: (key: string) => string, mode: ExecutionMode): string {
  if (mode === "operator") return t("command.nextOperatorMessage");
  if (mode === "user_wallet") return t("command.nextWalletSign");
  return t("command.nextSafeApprove");
}

export function ModeNextStepCard({
  mode,
  previewReady,
  confirmResult,
  onCopyUnsigned,
  onAttachTx,
  onCopySafeProposal,
  onAttachSafe,
}: ModeNextStepCardProps) {
  const { t } = useI18n();
  const isCurrentResult = confirmResult?.execution_mode === mode;
  const showWalletActions = isCurrentResult && mode === "user_wallet";
  const showSafeActions = isCurrentResult && mode === "safe";

  return (
    <section className="motion-scale-in rounded-[24px] border border-[#bfd0ec] bg-[linear-gradient(180deg,#edf3ff_0%,#ffffff_100%)] p-4">
      <p className="text-xs uppercase tracking-[0.12em] text-[#496896]">
        {t("common.nextAction")}
      </p>
      <p className="mt-1 text-sm font-semibold text-slate-900">{getTitle(t, mode)}</p>
      <p className="mt-1 text-sm leading-7 text-slate-700">{getMessage(t, mode)}</p>
      {!previewReady ? (
        <p className="mt-2 text-xs text-[#496896]">{t("command.nextRequiresPreview")}</p>
      ) : null}

      {showWalletActions ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onCopyUnsigned}
            className="rounded-xl border border-[#c8d4ea] bg-white px-3 py-2 text-xs font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
          >
            {t("command.copyUnsigned")}
          </button>
          <button
            type="button"
            onClick={onAttachTx}
            className="rounded-xl border border-[#c8d4ea] bg-white px-3 py-2 text-xs font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
          >
            {t("command.attachTx")}
          </button>
        </div>
      ) : null}

      {showSafeActions ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onCopySafeProposal}
            className="rounded-xl border border-[#c8d4ea] bg-white px-3 py-2 text-xs font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
          >
            {t("command.copySafeProposal")}
          </button>
          <button
            type="button"
            onClick={onAttachSafe}
            className="rounded-xl border border-[#c8d4ea] bg-white px-3 py-2 text-xs font-medium text-[#32527f] transition hover:border-[#a8bddf] hover:bg-[#edf3ff]"
          >
            {t("command.attachProposal")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
