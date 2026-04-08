export function DeferredPanelShell() {
  return (
    <div className="rounded-[24px] border border-[#d8e1f0] bg-white/90 p-5 shadow-sm">
      <div className="h-4 w-40 animate-pulse rounded bg-[#dfe7f6]" />
      <div className="mt-4 space-y-3">
        <div className="h-16 animate-pulse rounded-2xl bg-[#eef3fb]" />
        <div className="h-16 animate-pulse rounded-2xl bg-[#eef3fb]" />
      </div>
    </div>
  );
}
