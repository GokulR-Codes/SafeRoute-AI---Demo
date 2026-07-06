"use client";

import { useSafeRouteStore } from "@/lib/store";

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-route" : "bg-danger"}`} />;
}

export default function TopBar() {
  const status = useSafeRouteStore((s) => s.status);

  return (
    <div className="pointer-events-auto flex items-center justify-between rounded-card border border-line bg-surface/95 px-4 py-2.5 shadow-floating backdrop-blur">
      <span className="font-display text-lg font-bold tracking-tight text-ink">SafeRoute</span>

      {status && (
        <div className="hidden items-center gap-3 text-[11px] text-muted sm:flex">
          <span className="flex items-center gap-1.5">
            <StatusDot ok={status.graph_loaded} /> Graph
          </span>
          <span className="flex items-center gap-1.5">
            <StatusDot ok={status.routing_engine_ready} /> Routing
          </span>
          <span className="flex items-center gap-1.5">
            <StatusDot ok={status.risk_engine_ready} /> Risk
          </span>
          <span className="flex items-center gap-1.5">
            <StatusDot ok={status.backend_connected} /> Backend
          </span>
        </div>
      )}
    </div>
  );
}
